"""FastAPI application: D2's routes preserved, v2 mounted alongside."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI

from . import compat
from .models import FEED_INFO_V2, SCHEMA_VERSION
from .scenes import SCENES

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


def _provider_availability() -> dict[str, dict]:
    """What the service can actually do right now, and why not where it cannot.

    Reported here rather than on /api/status, which is a D2 route and must keep its
    D2 body. Task 6 to 8 replace these stubs with the providers themselves.
    """
    has_key = bool(os.environ.get("FIRMS_MAP_KEY"))
    pipeline = os.environ.get("BRIGHT_PIPELINE_PATH")
    return {
        "dea": {
            "available": True,
            "reason": None,
            "footprints": False,
            "note": "DEA's WFS carries no scan or track column, so no footprints.",
        },
        "firms": {
            "available": True,
            "reason": None if has_key else "no FIRMS_MAP_KEY; fixtures only",
            "footprints": True,
            "note": "Fixtures serve historical scenes only; never the current scene.",
        },
        "bright": {
            "available": bool(pipeline),
            "reason": None if pipeline else "BRIGHT_PIPELINE_PATH unset",
            "footprints": True,
            "note": "Optional. Absent it, the interface runs on DEA and FIRMS alone.",
        },
    }


@app.get("/api/v2/status", tags=["v2"])
def status_v2() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "feed_info": FEED_INFO_V2,
        "server_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "providers": _provider_availability(),
        "scenes": sorted(SCENES),
    }


@app.get("/api/v2/scenes", tags=["v2"])
def scenes_v2() -> dict:
    return {"schema_version": SCHEMA_VERSION,
            "scenes": [scene.to_dict() for scene in SCENES.values()]}
