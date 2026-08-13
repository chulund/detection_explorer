"""FastAPI application: D2's routes preserved, v2 mounted alongside."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Response

from . import compat, export
from .models import FEED_INFO_V2, SCHEMA_VERSION
from .registry import context_status, fetch_scene, provider_status
from .runs import api as runs_api
from .scenes import SCENES, get_scene


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Nothing can still be running after a restart, so any run left mid-flight is
    # marked failed with reason "interrupted". Its journal is preserved, so the
    # evidence of how far it got survives.
    interrupted = runs_api.recover_orphans()
    app.state.interrupted_on_startup = [r.id for r in interrupted]
    yield


app = FastAPI(
    title="RMIT Detection Explorer",
    description=FEED_INFO_V2["disclaimer"],
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    lifespan=lifespan,
)

# D2's paths, exactly where July left them, plus an identical mirror under /api/v1.
# Both are served by the same handlers, so they cannot drift apart.
app.include_router(compat.build_router(), prefix="/api", tags=["d2 (legacy)"])
app.include_router(compat.build_router(), prefix="/api/v1", tags=["v1 (alias of d2)"])
app.include_router(runs_api.build_router())


@app.get("/api/v2/status", tags=["v2"])
def status_v2() -> dict:
    """Provider availability lives here, never on /api/status, which is a D2 route."""
    return {
        "schema_version": SCHEMA_VERSION,
        "feed_info": FEED_INFO_V2,
        "server_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "providers": provider_status(),
        "context": context_status(),
        "scenes": sorted(SCENES),
    }


@app.get("/api/v2/scenes", tags=["v2"])
def scenes_v2() -> dict:
    return {"schema_version": SCHEMA_VERSION,
            "scenes": [scene.to_dict() for scene in SCENES.values()]}


@app.get("/api/v2/detections", tags=["v2"])
def detections_v2(
    scene: str = Query(..., description="Scene id; required, never inferred"),
    sources: str | None = Query(None, description="Comma-separated provider names"),
    format: str = Query("json", pattern="^(json|geojson)$"),
) -> dict:
    """Detections for one scene.

    `scene` is required rather than defaulted. A default would let a caller retrieve
    records without stating which epoch they belong to, which is the mistake scenes
    exist to prevent.
    """
    try:
        resolved = get_scene(scene)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None

    wanted = [s.strip() for s in sources.split(",")] if sources else None
    result = fetch_scene(resolved, wanted)
    records = result["detections"]
    start, end = resolved.window()

    envelope = {
        "schema_version": SCHEMA_VERSION,
        "scene": resolved.to_dict(),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": result["sources"],
        "count": len(records),
    }

    if format == "geojson":
        envelope["type"] = "FeatureCollection"
        envelope["features"] = [_as_feature(r) for r in records]
        return envelope

    envelope["detections"] = [r.to_dict() for r in records]
    return envelope


def _as_feature(record) -> dict:
    """Footprint as the geometry where one exists, falling back to the point."""
    body = record.to_dict()
    geometry = body.pop("footprint", None) or {
        "type": "Point", "coordinates": [record.lon, record.lat]
    }
    return {"type": "Feature", "geometry": geometry, "properties": body}


@app.get("/api/v2/export", tags=["v2"])
def export_v2(
    scene: str = Query(..., description="Scene id"),
    format: str = Query(..., pattern="^(geojson|csv)$"),
    sources: str | None = Query(None, description="Comma-separated provider names"),
    start: str | None = Query(None, description="ISO-8601 UTC, inclusive"),
    end: str | None = Query(None, description="ISO-8601 UTC, exclusive"),
    bbox: str | None = Query(None, description="west,south,east,north"),
):
    """Export a stated selection.

    There is no "current selection" on a stateless API, and guessing one would produce a
    different file from the one on screen. So the caller states what it wants: a scene, a
    format, and either a time range or the scene's own window.
    """
    try:
        resolved = get_scene(scene)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None

    wanted = [s.strip() for s in sources.split(",")] if sources else None
    records = fetch_scene(resolved, wanted)["detections"]

    if start or end:
        lo = start or ""
        hi = end or "9999"
        records = [r for r in records if lo <= r.detected_at < hi]

    if bbox:
        try:
            box = export.parse_bbox(bbox)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        records = [r for r in records if export.in_bbox(r, box)]

    if format == "csv":
        return Response(
            content=export.to_csv(records),
            media_type="text/csv",
            headers={"Content-Disposition":
                     f'attachment; filename="{scene}-detections.csv"'},
        )
    return export.to_geojson(records, resolved.to_dict())
