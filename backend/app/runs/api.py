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
from .store import RunStore
from .worker import RunQueue, default_runner

STATE_ROOT = Path(os.environ.get("DETECTION_EXPLORER_STATE", "runs"))
MANIFEST_DIR = Path(__file__).resolve().parents[3] / "manifests"

STATE_ROOT.mkdir(parents=True, exist_ok=True)
STORE = RunStore(STATE_ROOT / "runs.sqlite")
JOURNAL = Journal(STATE_ROOT / "journals")
QUEUE: RunQueue | None = None


class RunRequest(BaseModel):
    scene: str = Field(..., description="Scene id; the interval comes from the scene")


def pipeline_sha() -> str:
    """Identity of the pipeline that would compute a frame, for the cache key."""
    return os.environ.get("BRIGHT_PIPELINE_SHA", "unpinned")


def effective_config() -> dict:
    return {
        "detection_nweeks": int(os.environ.get("DETECTION_NWEEKS", "4")),
        "period": "both",
    }


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

    QUEUE = RunQueue(STORE, runner, cache_dir=STATE_ROOT / "frames", emit=emit)
    return QUEUE


def keys_for(scene_id: str) -> tuple[str, list[str], list[str]]:
    scene = get_scene(scene_id)
    manifest = MANIFEST_DIR / f"{scene_id}.json"
    config = config_hash(effective_config())
    frames = list(scene.frames)
    frame_keys = [
        frame_key(
            scene=scene_id, frame_ts=frame, pipeline_sha=pipeline_sha(),
            config_hash=config,
            manifest_checksum=(manifest_checksum(manifest, frame)
                               if manifest.exists() else "absent"),
            schema_version=SCHEMA_VERSION,
        )
        for frame in frames
    ]
    return run_key(frame_keys), frame_keys, frames


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

        key, frame_keys, frames = keys_for(body.scene)
        existing = STORE.find_by_run_key(key)

        if existing is not None and existing.state in ("queued", "running"):
            return {"run_id": existing.id, "state": existing.state,
                    "delivery": "in_flight", "attempt": existing.attempt}
        if existing is not None and existing.state == "succeeded":
            return {"run_id": existing.id, "state": "succeeded",
                    "delivery": "cached", "attempt": existing.attempt}

        queue = build_queue()
        if queue is None:
            raise HTTPException(
                503, "BRIGHT_PIPELINE_PATH is not set, so no run can be executed. "
                     "The fixture profile serves reference outputs instead.")

        run = (STORE.next_attempt(key) if existing is not None
               else STORE.create(run_key=key, scene=body.scene,
                                 frame_keys=frame_keys, frames=frames))
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
            return STORE.set_state(run_id, "cancelled", "cancelled by request").to_dict()
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
                    if event.kind in ("run.done", "run.error"):
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
        path = STATE_ROOT / "frames" / f"{key}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["detections"] = attach_row_footprints(payload.get("detections") or [])
        out.append(payload)
    return out


def recover_orphans() -> list:
    """Called from the app lifespan: nothing can still be running after a restart."""
    return STORE.recover_orphans()
