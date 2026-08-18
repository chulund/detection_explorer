"""Executing BRIGHT runs: one at a time, in isolated subprocesses.

BRIGHT is not imported. The pipeline carries global configuration, environment state and its
own multiprocessing, so importing it into the web service would couple its failure modes to
FastAPI's event loop. Instead each frame is a subprocess invoking the pinned interpreter and
the pinned pipeline commit through the CLI the pipeline already exposes. A crash, a hang or a
cancellation then stops at the process boundary.

FastAPI's `BackgroundTasks` is deliberately not used either: the framework documentation
recommends an external execution mechanism for heavy computation, and a detection frame takes
around 75 seconds on the research workstation.

Concurrency is one. The queue serialises work and the subprocess provides the isolation;
between them there is never a second BRIGHT process competing for the same staged inputs.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from .store import Run, RunStore

FRAME_TIMEOUT_S = 120
RUN_TIMEOUT_S = 1200

#: The pipeline's output file carries 27 columns; these are the ones the interface uses.
#:
#: `mir` is the AHI B07 mid-infrared brightness temperature, which is the channel the
#: detection is actually made on, and `tir` is the B13 longwave window. `back_bt` is the
#: background estimate the threshold was set against, which is what makes `mir` mean
#: something. The rest are thresholds and quality flags belonging to the pipeline's own
#: diagnostics rather than to a detection record.
DETECTION_COLUMNS = ("region", "x", "y", "lon", "lat", "frp", "confidence", "period", "dt",
                     "mir", "tir", "back_bt")


class FrameRunner(Protocol):
    async def run(self, frame_ts: str, output_root: Path) -> list[dict]:
        """Detections for one frame, or raise."""


class FrameFailed(RuntimeError):
    pass


@dataclass
class SubprocessFrameRunner:
    """Runs the real pipeline. One process per frame, killed on timeout."""

    pipeline_path: Path
    python: Path
    timeout_s: int = FRAME_TIMEOUT_S
    calls: list[str] = field(default_factory=list)
    _process: asyncio.subprocess.Process | None = field(
        default=None, init=False, repr=False
    )

    async def run(self, frame_ts: str, output_root: Path) -> list[dict]:
        self.calls.append(frame_ts)
        output_root = Path(output_root).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment["SDIR"] = str(output_root)
        process = await asyncio.create_subprocess_exec(
            str(self.python), "-m", "src.detection_module.run_parquet_detection",
            "--dt", frame_ts, "--period", "both", "--workers", "1",
            "--force",
            cwd=str(self.pipeline_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        self._process = process
        try:
            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.timeout_s
                )
            except asyncio.TimeoutError:
                await self.cancel()
                raise FrameFailed(
                    f"frame {frame_ts} exceeded {self.timeout_s}s"
                ) from None
            except asyncio.CancelledError:
                await self.cancel()
                raise

            if process.returncode != 0:
                tail = (stderr or b"").decode(
                    "utf-8", "replace"
                ).strip().splitlines()[-20:]
                raise FrameFailed(f"exit {process.returncode}: " + "\n".join(tail))

            return self.read_frame_output(frame_ts, output_root)
        finally:
            if self._process is process:
                self._process = None

    async def cancel(self) -> None:
        process = self._process
        if process is None or process.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            with contextlib.suppress(ProcessLookupError):
                await process.wait()

    def read_frame_output(self, frame_ts: str, output_root: Path) -> list[dict]:
        directory = output_root / frame_ts
        path = directory / f"{frame_ts}_bright_mixed.txt"
        if not path.exists():
            raise FrameFailed(f"frame {frame_ts} produced no expected output: {path.name}")
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            missing = sorted(set(DETECTION_COLUMNS) - set(reader.fieldnames or []))
            if missing:
                raise FrameFailed(
                    f"frame {frame_ts} output is missing columns: {', '.join(missing)}"
                )
            return [
                {k: row.get(k) for k in DETECTION_COLUMNS if k in row}
                for row in reader
            ]


class RunQueue:
    """Single-consumer queue over a FrameRunner, with per-frame caching."""

    def __init__(self, store: RunStore, runner: FrameRunner, cache_dir: Path,
                 emit: Callable[[str, str, dict], Awaitable[None]] | None = None,
                 run_timeout_s: int = RUN_TIMEOUT_S,
                 work_dir: Path | None = None) -> None:
        self.store = store
        self.runner = runner
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir = Path(work_dir or self.cache_dir.parent / "pipeline-output")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._emit = emit
        self.run_timeout_s = run_timeout_s
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._consumer: asyncio.Task | None = None
        self._current: str | None = None
        self._cancelled: set[str] = set()
        self.observed_concurrency: list[int] = []
        self._in_flight = 0

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        if self._consumer is None:
            self._consumer = asyncio.create_task(self._consume())

    async def stop(self) -> None:
        if self._consumer is not None:
            if self._current is not None:
                run_id = self._current
                run = self.store.get(run_id)
                if not run.terminal:
                    self._cancelled.add(run_id)
                    self.store.set_state(run_id, "failed", "interrupted")
                    await self._event(
                        run_id, "run.error",
                        {"reason": "interrupted", "state": "failed"},
                    )
                cancel_runner = getattr(self.runner, "cancel", None)
                if cancel_runner is not None:
                    await cancel_runner()
            self._consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer
            self._consumer = None

    async def submit(self, run: Run) -> None:
        await self._queue.put(run.id)
        await self.start()

    async def cancel(self, run_id: str) -> Run:
        """A no-op on a run that has already finished."""
        run = self.store.get(run_id)
        if run.terminal:
            return run
        self._cancelled.add(run_id)
        updated = self.store.set_state(run_id, "cancelled", "cancelled by request")
        await self._event(run_id, "run.state", {"state": "cancelled"})
        if self._current == run_id:
            cancel_runner = getattr(self.runner, "cancel", None)
            if cancel_runner is not None:
                await cancel_runner()
        return updated

    async def drain(self) -> None:
        """Wait for the queue to empty. Test convenience, not used in production."""
        await self._queue.join()

    async def run_to_completion(self, run: Run) -> Run:
        await self.submit(run)
        await self.drain()
        return self.store.get(run.id)

    # ------------------------------------------------------------------ caching

    def _cache_path(self, frame_key: str) -> Path:
        return self.cache_dir / f"{frame_key}.json"

    def cached(self, frame_key: str) -> list[dict] | None:
        path = self._cache_path(frame_key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        if (not isinstance(payload, dict)
                or payload.get("frame_key") != frame_key
                or not isinstance(payload.get("detections"), list)):
            return None
        return payload["detections"]

    def _store_cache(self, frame_key: str, frame_ts: str, rows: list[dict]) -> None:
        target = self._cache_path(frame_key)
        temporary = target.with_name(f"{target.name}.tmp")
        temporary.write_text(json.dumps({
            "frame": frame_ts,
            "frame_key": frame_key,
            "computed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "detections": rows,
        }, indent=2), encoding="utf-8")
        os.replace(temporary, target)

    # ------------------------------------------------------------------ execution

    async def _event(self, run_id: str, kind: str, payload: dict) -> None:
        if self._emit is not None:
            await self._emit(run_id, kind, payload)

    async def _consume(self) -> None:
        while True:
            run_id = await self._queue.get()
            try:
                await self._execute(run_id)
            finally:
                self._queue.task_done()

    async def _execute(self, run_id: str) -> None:
        run = self.store.get(run_id)
        if run_id in self._cancelled or run.terminal:
            return

        self._in_flight += 1
        self.observed_concurrency.append(self._in_flight)
        self._current = run_id
        try:
            self.store.set_state(run_id, "running")
            await self._event(run_id, "run.state", {"state": "running",
                                                    "frames": len(run.frames)})
            await asyncio.wait_for(self._frames(run), timeout=self.run_timeout_s)
        except asyncio.TimeoutError:
            self.store.set_state(run_id, "failed",
                                 f"run exceeded {self.run_timeout_s}s")
            await self._event(run_id, "run.error",
                              {"reason": "run_timeout", "state": "failed"})
        except FrameFailed as exc:
            if run_id in self._cancelled:
                return
            self.store.set_state(run_id, "failed", str(exc))
            await self._event(run_id, "run.error",
                              {"reason": str(exc), "state": "failed"})
        except Exception as exc:                                  # noqa: BLE001
            if run_id in self._cancelled:
                return
            self.store.set_state(run_id, "failed", f"{type(exc).__name__}: {exc}")
            await self._event(run_id, "run.error",
                              {"reason": str(exc), "state": "failed"})
        else:
            if run_id not in self._cancelled:
                self.store.set_state(run_id, "succeeded")
                await self._event(run_id, "run.done", {"state": "succeeded"})
        finally:
            self._in_flight -= 1
            self._current = None

    async def _frames(self, run: Run) -> None:
        for index, (frame_ts, frame_key) in enumerate(zip(run.frames, run.frame_keys), 1):
            if run.id in self._cancelled:
                return
            started = asyncio.get_running_loop().time()
            rows = self.cached(frame_key)
            was_cached = rows is not None
            if rows is None:
                rows = await self.runner.run(frame_ts, self.work_dir / run.id)
                if run.id in self._cancelled:
                    return
                self._store_cache(frame_key, frame_ts, rows)
            elapsed = asyncio.get_running_loop().time() - started
            await self._event(run.id, "run.frame", {
                "frame": frame_ts,
                "index": index,
                "of": len(run.frames),
                "detections": len(rows),
                "cached": was_cached,
                "elapsed_s": round(elapsed, 2),
            })


def default_runner() -> SubprocessFrameRunner | None:
    """The real runner, or None when the pipeline is not configured."""
    pipeline = os.environ.get("BRIGHT_PIPELINE_PATH")
    if not pipeline:
        return None
    return SubprocessFrameRunner(
        pipeline_path=Path(pipeline),
        python=Path(os.environ.get("BRIGHT_PYTHON")
                    or r"C:\Users\nurfa\.conda\envs\bright\python.exe"),
    )
