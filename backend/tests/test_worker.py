"""The run queue: caching, isolation, cancellation, and one job at a time.

Runs against a stub FrameRunner rather than the real pipeline, so the suite stays fast and
needs neither staged parquet nor a BRIGHT checkout. What is being tested is the orchestration,
which is where the interesting failure modes live.
"""

from __future__ import annotations

import asyncio

import pytest

from app.runs.store import RunStore
from app.runs.worker import FrameFailed, RunQueue

pytestmark = pytest.mark.anyio


class StubRunner:
    """Records what it was asked to compute; can be told to fail or stall."""

    def __init__(self, fail_on: set[str] | None = None, delay: float = 0.0) -> None:
        self.calls: list[str] = []
        self.fail_on = fail_on or set()
        self.delay = delay

    async def run(self, frame_ts: str) -> list[dict]:
        self.calls.append(frame_ts)
        if self.delay:
            await asyncio.sleep(self.delay)
        if frame_ts in self.fail_on:
            raise FrameFailed(f"boom at {frame_ts}")
        return [{"lat": -33.0, "lon": 150.0, "frp": "12.0", "dt": frame_ts}]


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
        return RunQueue(store, runner, cache_dir=tmp_path / "cache", emit=emit)
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


async def test_run_timeout_cancels_rather_than_hanging(store, tmp_path, events):
    async def emit(run_id, kind, payload):
        events.append((run_id, kind, payload))

    queue = RunQueue(store, StubRunner(delay=0.5), cache_dir=tmp_path / "c",
                     emit=emit, run_timeout_s=0.05)
    run = _run(store, ["t1"], ["k1"])
    finished = await queue.run_to_completion(run)
    await queue.stop()
    assert finished.state == "cancelled"
    assert "exceeded" in finished.error


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
