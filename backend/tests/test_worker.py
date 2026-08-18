"""The run queue: caching, isolation, cancellation, and one job at a time.

Runs against a stub FrameRunner rather than the real pipeline, so the suite stays fast and
needs neither staged parquet nor a BRIGHT checkout. What is being tested is the orchestration,
which is where the interesting failure modes live.
"""

from __future__ import annotations

import asyncio

import pytest

from app.runs import worker as worker_module
from app.runs.store import RunStore
from app.runs.worker import FrameFailed, RunQueue, SubprocessFrameRunner

pytestmark = pytest.mark.anyio


class StubRunner:
    """Records what it was asked to compute; can be told to fail or stall."""

    def __init__(self, fail_on: set[str] | None = None, delay: float = 0.0) -> None:
        self.calls: list[str] = []
        self.fail_on = fail_on or set()
        self.delay = delay

    async def run(self, frame_ts: str, output_root=None) -> list[dict]:
        self.calls.append(frame_ts)
        if self.delay:
            await asyncio.sleep(self.delay)
        if frame_ts in self.fail_on:
            raise FrameFailed(f"boom at {frame_ts}")
        return [{"lat": -33.0, "lon": 150.0, "frp": "12.0", "dt": frame_ts}]


class IsolatedRunner(StubRunner):
    def __init__(self) -> None:
        super().__init__()
        self.output_roots = []

    async def run(self, frame_ts: str, output_root) -> list[dict]:
        self.output_roots.append(output_root)
        return await super().run(frame_ts, output_root)


class CancellableRunner(StubRunner):
    def __init__(self) -> None:
        super().__init__(delay=0.05)
        self.started = asyncio.Event()
        self.cancel_called = False

    async def run(self, frame_ts: str, output_root=None) -> list[dict]:
        self.started.set()
        return await super().run(frame_ts, output_root)

    async def cancel(self) -> None:
        self.cancel_called = True


@pytest.fixture
def store(tmp_path) -> RunStore:
    return RunStore(tmp_path / "runs.sqlite")


@pytest.fixture
def events() -> list[tuple[str, str, dict]]:
    return []


@pytest.fixture
def queue_factory(store, tmp_path, events):
    def _factory(runner) -> RunQueue:
        async def emit(run_id, kind, payload):
            events.append((run_id, kind, payload))
        return RunQueue(store, runner, cache_dir=tmp_path / "cache", emit=emit,
                        work_dir=tmp_path / "pipeline-output")
    return _factory


def _run(store, frames, keys, run_key="k1"):
    return store.create(run_key=run_key, scene="april-9-demo",
                        frame_keys=keys, frames=frames)


# ------------------------------------------------------------------ happy path

async def test_a_run_succeeds_and_computes_every_frame(store, queue_factory):
    runner = StubRunner()
    queue = queue_factory(runner)
    run = _run(store, ["t1", "t2", "t3"], ["k1", "k2", "k3"])
    finished = await queue.run_to_completion(run)
    await queue.stop()

    assert finished.state == "succeeded"
    assert runner.calls == ["t1", "t2", "t3"]


async def test_each_run_computes_inside_its_own_output_directory(
        store, queue_factory, tmp_path):
    runner = IsolatedRunner()
    queue = queue_factory(runner)
    run = _run(store, ["t1", "t2"], ["k1", "k2"])

    await queue.run_to_completion(run)
    await queue.stop()

    assert runner.output_roots == [
        tmp_path / "pipeline-output" / run.id,
        tmp_path / "pipeline-output" / run.id,
    ]


async def test_subprocess_forces_recomputation_into_the_isolated_directory(
        tmp_path, monkeypatch):
    frame = "20260409040000"
    output_root = tmp_path / "isolated"
    output = output_root / frame / f"{frame}_bright_mixed.txt"
    output.parent.mkdir(parents=True)
    output.write_text(
        "region,x,y,lon,lat,frp,confidence,period,dt,mir,tir,back_bt\n",
        encoding="utf-8",
    )
    captured = {}

    class CompletedProcess:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def create_process(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return CompletedProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    runner = SubprocessFrameRunner(tmp_path / "pipeline", tmp_path / "python.exe")

    assert await runner.run(frame, output_root) == []
    assert "--force" in captured["args"]
    assert captured["kwargs"]["env"]["SDIR"] == str(output_root.resolve())


async def test_success_exit_without_the_expected_output_fails_the_frame(
        tmp_path, monkeypatch):
    class CompletedProcess:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def create_process(*args, **kwargs):
        return CompletedProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    runner = SubprocessFrameRunner(tmp_path / "pipeline", tmp_path / "python.exe")

    with pytest.raises(FrameFailed, match="expected output"):
        await runner.run("20260409040000", tmp_path / "isolated")


def test_malformed_pipeline_output_fails_instead_of_becoming_an_empty_frame(tmp_path):
    frame = "20260409040000"
    output_root = tmp_path / "isolated"
    output = output_root / frame / f"{frame}_bright_mixed.txt"
    output.parent.mkdir(parents=True)
    output.write_text("not,the,bright,schema\n", encoding="utf-8")
    runner = SubprocessFrameRunner(tmp_path / "pipeline", tmp_path / "python.exe")

    with pytest.raises(FrameFailed, match="missing columns"):
        runner.read_frame_output(frame, output_root)


async def test_subprocess_runner_terminates_the_active_process_on_cancel(
        tmp_path, monkeypatch):
    started = asyncio.Event()
    stopped = asyncio.Event()

    class RunningProcess:
        returncode = None
        terminated = False

        async def communicate(self):
            started.set()
            await stopped.wait()
            return b"", b"cancelled"

        def terminate(self):
            self.terminated = True
            self.returncode = -15
            stopped.set()

        def kill(self):
            self.returncode = -9
            stopped.set()

        async def wait(self):
            await stopped.wait()
            return self.returncode

    process = RunningProcess()

    async def create_process(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    runner = SubprocessFrameRunner(tmp_path / "pipeline", tmp_path / "python.exe")
    task = asyncio.create_task(
        runner.run("20260409040000", tmp_path / "isolated")
    )
    await started.wait()

    await runner.cancel()

    with pytest.raises(FrameFailed, match="exit -15"):
        await task
    assert process.terminated is True


async def test_progress_is_emitted_per_frame(store, queue_factory, events):
    queue = queue_factory(StubRunner())
    run = _run(store, ["t1", "t2"], ["k1", "k2"])
    await queue.run_to_completion(run)
    await queue.stop()

    frames = [payload for _, kind, payload in events if kind == "run.frame"]
    assert [f["index"] for f in frames] == [1, 2]
    assert all(f["of"] == 2 for f in frames)
    assert [kind for _, kind, _ in events][-1] == "run.done"


# ------------------------------------------------------------------ caching

async def test_a_cached_frame_is_not_recomputed(store, queue_factory):
    """An interval overlapping an earlier run recomputes only what is new."""
    runner = StubRunner()
    queue = queue_factory(runner)
    await queue.run_to_completion(_run(store, ["t1", "t2"], ["k1", "k2"], "run-a"))
    assert runner.calls == ["t1", "t2"]

    await queue.run_to_completion(_run(store, ["t2", "t3"], ["k2", "k3"], "run-b"))
    await queue.stop()
    assert runner.calls == ["t1", "t2", "t3"], "t2 should have come from cache"


async def test_cached_frames_are_flagged_in_progress(store, queue_factory, events):
    queue = queue_factory(StubRunner())
    await queue.run_to_completion(_run(store, ["t1"], ["k1"], "run-a"))
    events.clear()
    await queue.run_to_completion(_run(store, ["t1"], ["k1"], "run-b"))
    await queue.stop()

    frames = [p for _, kind, p in events if kind == "run.frame"]
    assert frames[0]["cached"] is True


async def test_a_different_frame_key_forces_recomputation(store, queue_factory):
    """Same timestamp, changed inputs: the cache must not be reused."""
    runner = StubRunner()
    queue = queue_factory(runner)
    await queue.run_to_completion(_run(store, ["t1"], ["key-before"], "run-a"))
    await queue.run_to_completion(_run(store, ["t1"], ["key-after"], "run-b"))
    await queue.stop()
    assert runner.calls == ["t1", "t1"]


async def test_a_corrupt_frame_cache_is_recomputed(store, queue_factory):
    runner = StubRunner()
    queue = queue_factory(runner)
    (queue.cache_dir / "k1.json").write_text("{not-json", encoding="utf-8")

    finished = await queue.run_to_completion(_run(store, ["t1"], ["k1"]))
    await queue.stop()

    assert finished.state == "succeeded"
    assert runner.calls == ["t1"]
    assert queue.cached("k1")[0]["dt"] == "t1"


async def test_cache_is_published_with_an_atomic_replace(
        store, queue_factory, monkeypatch):
    replacements = []
    real_replace = worker_module.os.replace

    def record_replace(source, destination):
        replacements.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr(worker_module.os, "replace", record_replace)
    queue = queue_factory(StubRunner())

    await queue.run_to_completion(_run(store, ["t1"], ["k1"]))
    await queue.stop()

    assert len(replacements) == 1
    assert str(replacements[0][0]).endswith(".tmp")
    assert str(replacements[0][1]).endswith("k1.json")


# ------------------------------------------------------------------ failure

async def test_a_failing_frame_fails_the_run_and_records_why(store, queue_factory):
    queue = queue_factory(StubRunner(fail_on={"t2"}))
    run = _run(store, ["t1", "t2", "t3"], ["k1", "k2", "k3"])
    finished = await queue.run_to_completion(run)
    await queue.stop()

    assert finished.state == "failed"
    assert "boom at t2" in finished.error


async def test_a_failure_stops_the_remaining_frames(store, queue_factory):
    runner = StubRunner(fail_on={"t1"})
    queue = queue_factory(runner)
    await queue.run_to_completion(_run(store, ["t1", "t2"], ["k1", "k2"]))
    await queue.stop()
    assert runner.calls == ["t1"]


async def test_run_timeout_fails_rather_than_hanging(store, tmp_path, events):
    async def emit(run_id, kind, payload):
        events.append((run_id, kind, payload))

    queue = RunQueue(store, StubRunner(delay=0.5), cache_dir=tmp_path / "c",
                     emit=emit, run_timeout_s=0.05)
    run = _run(store, ["t1"], ["k1"])
    finished = await queue.run_to_completion(run)
    await queue.stop()
    assert finished.state == "failed"
    assert "exceeded" in finished.error
    assert events[-1][1:] == (
        "run.error", {"reason": "run_timeout", "state": "failed"}
    )


# ------------------------------------------------------------------ cancellation

async def test_cancel_marks_the_run_and_is_idempotent(store, queue_factory):
    queue = queue_factory(StubRunner())
    run = _run(store, ["t1"], ["k1"])
    await queue.cancel(run.id)
    assert store.get(run.id).state == "cancelled"
    await queue.cancel(run.id)          # must not raise
    await queue.stop()


async def test_cancel_on_a_finished_run_is_a_noop(store, queue_factory):
    queue = queue_factory(StubRunner())
    run = _run(store, ["t1"], ["k1"])
    await queue.run_to_completion(run)
    before = store.get(run.id)
    after = await queue.cancel(run.id)
    await queue.stop()
    assert after.state == before.state == "succeeded"


async def test_a_cancelled_run_is_not_executed(store, queue_factory):
    runner = StubRunner()
    queue = queue_factory(runner)
    run = _run(store, ["t1"], ["k1"])
    await queue.cancel(run.id)
    await queue.submit(run)
    await queue.drain()
    await queue.stop()
    assert runner.calls == []


async def test_cancelling_an_active_run_stops_the_runner_and_never_caches_its_frame(
        store, queue_factory):
    runner = CancellableRunner()
    queue = queue_factory(runner)
    run = _run(store, ["t1"], ["k1"])
    await queue.submit(run)
    await runner.started.wait()

    await queue.cancel(run.id)
    await queue.drain()
    await queue.stop()

    assert runner.cancel_called is True
    assert store.get(run.id).state == "cancelled"
    assert queue.cached("k1") is None


async def test_process_exit_caused_by_user_cancel_does_not_relabel_the_run_failed(
        store, queue_factory, events):
    class TerminatedRunner:
        def __init__(self):
            self.started = asyncio.Event()
            self.stopped = asyncio.Event()

        async def run(self, frame_ts, output_root):
            self.started.set()
            await self.stopped.wait()
            raise FrameFailed("exit -15: cancelled")

        async def cancel(self):
            self.stopped.set()

    runner = TerminatedRunner()
    queue = queue_factory(runner)
    run = _run(store, ["t1"], ["k1"])
    await queue.submit(run)
    await runner.started.wait()

    await queue.cancel(run.id)
    await queue.drain()
    await queue.stop()

    assert store.get(run.id).state == "cancelled"
    assert [kind for _, kind, _ in events][-1] == "run.state"


async def test_stopping_the_queue_terminates_and_journals_the_active_run(
        store, queue_factory, events):
    runner = CancellableRunner()
    queue = queue_factory(runner)
    run = _run(store, ["t1"], ["k1"])
    await queue.submit(run)
    await runner.started.wait()

    await queue.stop()

    finished = store.get(run.id)
    assert runner.cancel_called is True
    assert finished.state == "failed"
    assert finished.error == "interrupted"
    assert [kind for _, kind, _ in events][-1] == "run.error"


# ------------------------------------------------------------------ concurrency

async def test_only_one_run_executes_at_a_time(store, queue_factory):
    """Two BRIGHT processes competing for the same staged inputs is never wanted."""
    queue = queue_factory(StubRunner(delay=0.02))
    a = _run(store, ["t1"], ["k1"], "run-a")
    b = _run(store, ["t2"], ["k2"], "run-b")
    await queue.submit(a)
    await queue.submit(b)
    await queue.drain()
    await queue.stop()

    assert max(queue.observed_concurrency) == 1
    assert store.get(a.id).state == "succeeded"
    assert store.get(b.id).state == "succeeded"
