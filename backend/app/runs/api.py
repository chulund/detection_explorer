"""Run endpoints: create, inspect, cancel, and follow.

Creation is idempotent on the run key, and what "idempotent" means depends on the state of
the run it matches. A queued or running match returns that run, so a double-click does not
start a second computation. A succeeded match returns it flagged as cached delivery. A failed
or cancelled match starts a **new attempt** rather than resurrecting the old one, so the
record of the failure survives.

Progress is a separate endpoint from results. The stream carries only what is happening;
`GET /api/v2/runs/{id}` carries what happened. Mixing them would make a reconnecting client
re-download the payload it already had.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..footprints.ahi import attach_row_footprints
from ..models import SCHEMA_VERSION
from ..scenes import get_scene
from .journal import Journal
from .keys import config_hash, frame_key, manifest_checksum, run_key
from .provenance import PipelinePreflightError, inspect_pipeline
from .store import RunStore
from .worker import RunQueue, default_runner

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_DIR = PROJECT_ROOT / "manifests"


def resolve_state_root(value: str | os.PathLike[str] | None = None) -> Path:
    configured = Path(value or os.environ.get("DETECTION_EXPLORER_STATE", "runs"))
    if not configured.is_absolute():
        configured = PROJECT_ROOT / configured
    return configured.resolve()


STATE_ROOT = resolve_state_root()

STATE_ROOT.mkdir(parents=True, exist_ok=True)
STORE = RunStore(STATE_ROOT / "runs.sqlite")
JOURNAL = Journal(STATE_ROOT / "journals")
QUEUE: RunQueue | None = None


class RunRequest(BaseModel):
    scene: str = Field(..., description="Scene id; the interval comes from the scene")


def _is_terminal_event(kind: str, payload: dict) -> bool:
    return (kind in ("run.done", "run.error")
            or (kind == "run.state"
                and payload.get("state") in ("succeeded", "failed", "cancelled")))


def _read_frame_cache(frame: str, key: str) -> dict | None:
    path = STATE_ROOT / "frames" / f"{key}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if (not isinstance(payload, dict)
            or payload.get("frame") != frame
            or payload.get("frame_key") != key
            or not isinstance(payload.get("detections"), list)):
        return None
    return payload


def _run_cache_complete(run) -> bool:
    return all(
        _read_frame_cache(frame, key) is not None
        for frame, key in zip(run.frames, run.frame_keys)
    ) and len(run.frames) == len(run.frame_keys)


def build_queue() -> RunQueue | None:
    """The queue, or None when no pipeline is configured to run."""
    global QUEUE
    if QUEUE is not None:
        return QUEUE
    runner = default_runner()
    if runner is None:
        return None

    async def emit(run_id: str, kind: str, payload: dict) -> None:
        await JOURNAL.append(run_id, kind, payload)

    QUEUE = RunQueue(
        STORE, runner, cache_dir=STATE_ROOT / "frames", emit=emit,
        work_dir=STATE_ROOT / "pipeline-output",
    )
    return QUEUE


def keys_for(scene_id: str) -> tuple[str, list[str], list[str], dict]:
    scene = get_scene(scene_id)
    manifest = MANIFEST_DIR / f"{scene_id}.json"
    frames = list(scene.frames)
    if os.environ.get("BRIGHT_PIPELINE_PATH"):
        provenance = inspect_pipeline()
    else:
        provenance = inspect_pipeline(require_reproducible=False)
    manifest_digests = {
        frame: (manifest_checksum(manifest, frame) if manifest.exists() else "absent")
        for frame in frames
    }
    provenance = {
        **provenance,
        "schema_version": SCHEMA_VERSION,
        "inputs": {"manifest_sha256_by_frame": manifest_digests},
    }
    pipeline_identity = provenance.get("pipeline", {}).get("actual_sha", "unconfigured")
    config = config_hash({
        "configuration": provenance.get("configuration", {"period": "both"}),
        "ancillary": provenance.get("ancillary", {}),
    })
    frame_keys = [
        frame_key(
            scene=scene_id, frame_ts=frame, pipeline_sha=pipeline_identity,
            config_hash=config,
            manifest_checksum=manifest_digests[frame],
            schema_version=SCHEMA_VERSION,
        )
        for frame in frames
    ]
    return run_key(frame_keys), frame_keys, frames, provenance


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v2/runs", tags=["v2 runs"])

    @router.post("", status_code=202)
    async def create_run(body: RunRequest) -> dict:
        try:
            scene = get_scene(body.scene)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from None
        if scene.admits("live"):
            raise HTTPException(
                400, "the current scene is retrieved, not computed; "
                     "BRIGHT runs apply to fixed historical scenes only")

        try:
            key, frame_keys, frames, provenance = keys_for(body.scene)
        except PipelinePreflightError as exc:
            raise HTTPException(503, str(exc)) from None
        existing = STORE.find_by_run_key(key)

        if existing is not None and existing.state in ("queued", "running"):
            return {"run_id": existing.id, "state": existing.state,
                    "delivery": "in_flight", "attempt": existing.attempt}
        if (existing is not None and existing.state == "succeeded"
                and _run_cache_complete(existing)):
            return {"run_id": existing.id, "state": "succeeded",
                    "delivery": "cached", "attempt": existing.attempt}

        queue = build_queue()
        if queue is None:
            raise HTTPException(
                503, "BRIGHT_PIPELINE_PATH is not set, so no run can be executed. "
                     "The fixture profile serves reference outputs instead.")

        run = (STORE.next_attempt(key) if existing is not None
               else STORE.create(run_key=key, scene=body.scene,
                                 frame_keys=frame_keys, frames=frames,
                                 provenance=provenance))
        await JOURNAL.append(run.id, "run.state",
                             {"state": "queued", "frames": len(frames)})
        await queue.submit(run)
        return {"run_id": run.id, "state": "queued", "delivery": "fresh",
                "attempt": run.attempt,
                "parent_run_id": run.parent_run_id}

    @router.get("/{run_id}")
    def get_run(run_id: str) -> dict:
        try:
            run = STORE.get(run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from None
        if run.state == "succeeded" and not _run_cache_complete(run):
            raise HTTPException(
                409, "run is marked succeeded but its frame cache is incomplete"
            )
        body = run.to_dict()
        body["detections"] = _frames_payload(run)
        return body

    @router.post("/{run_id}/cancel")
    async def cancel_run(run_id: str) -> dict:
        try:
            run = STORE.get(run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from None

        # A finished run stays finished. Cancelling it would rewrite the record of
        # what actually happened, which is the opposite of what cancel is for.
        if run.terminal:
            return run.to_dict()

        queue = build_queue()
        if queue is None:
            updated = STORE.set_state(run_id, "cancelled", "cancelled by request")
            await JOURNAL.append(run_id, "run.state", {"state": "cancelled"})
            return updated.to_dict()
        return (await queue.cancel(run_id)).to_dict()

    @router.get("/{run_id}/events")
    async def stream_events(run_id: str, request: Request) -> EventSourceResponse:
        try:
            STORE.get(run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from None

        last_seen = int(request.headers.get("Last-Event-ID") or 0)

        async def generator():
            queue = JOURNAL.subscribe(run_id)
            try:
                # Replay what the client missed, then continue live from the same cursor.
                cursor = last_seen
                for event in JOURNAL.read(run_id, after=last_seen):
                    cursor = event.id
                    yield {"id": str(event.id), "event": event.kind,
                           "data": json.dumps(event.payload)}
                if STORE.get(run_id).terminal:
                    return
                while not await request.is_disconnected():
                    event = await queue.get()
                    if event.id <= cursor:
                        continue
                    cursor = event.id
                    yield {"id": str(event.id), "event": event.kind,
                           "data": json.dumps(event.payload)}
                    if _is_terminal_event(event.kind, event.payload):
                        return
            finally:
                JOURNAL.unsubscribe(run_id, queue)

        return EventSourceResponse(generator())

    return router


def _frames_payload(run) -> list[dict]:
    """Cached detections per frame, for a finished run.

    Footprints are joined here rather than when the frame was computed, so that runs
    cached before the join existed gain their polygons too. The reprojected grid is
    memoised, so the join costs a dictionary lookup per row.
    """
    out = []
    for frame, key in zip(run.frames, run.frame_keys):
        payload = _read_frame_cache(frame, key)
        if payload is None:
            continue
        payload["detections"] = attach_row_footprints(payload.get("detections") or [])
        out.append(payload)
    return out


def recover_orphans() -> list:
    """Called from the app lifespan: nothing can still be running after a restart."""
    return STORE.recover_orphans()


async def recover_orphans_and_journal() -> list:
    recovered = recover_orphans()
    for run in recovered:
        await JOURNAL.append(
            run.id, "run.error", {"reason": "interrupted", "state": "failed"}
        )
    return recovered
