"""FastAPI application: D2's routes preserved, v2 mounted alongside."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query

from . import compat
from .models import FEED_INFO_V2, SCHEMA_VERSION
from .registry import fetch_scene, provider_status
from .scenes import SCENES, get_scene

app = FastAPI(
    title="RMIT Detection Explorer",
    description=FEED_INFO_V2["disclaimer"],
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
)

# D2's paths, exactly where July left them, plus an identical mirror under /api/v1.
# Both are served by the same handlers, so they cannot drift apart.
app.include_router(compat.build_router(), prefix="/api", tags=["d2 (legacy)"])
app.include_router(compat.build_router(), prefix="/api/v1", tags=["v1 (alias of d2)"])


@app.get("/api/v2/status", tags=["v2"])
def status_v2() -> dict:
    """Provider availability lives here, never on /api/status, which is a D2 route."""
    return {
        "schema_version": SCHEMA_VERSION,
        "feed_info": FEED_INFO_V2,
        "server_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "providers": provider_status(),
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
