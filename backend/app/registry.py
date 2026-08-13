"""Where the providers are assembled and asked for data.

Kept apart from `main.py` so the wiring is testable without going through HTTP, and apart
from the providers so that none of them has to know the others exist.

The rule this module enforces: every record leaving here has passed `scenes.admit`. A
provider that returns the wrong `data_nature`, for whatever reason, cannot reach a caller.
That is deliberate belt and braces. The providers already label correctly; this is the layer
that stays correct when one of them stops doing so.
"""

from __future__ import annotations

import os
from pathlib import Path

from .footprints import ahi as ahi_footprints
from .footprints import polar as polar_footprints
from .models import Detection
from .providers.dea import DeaProvider
from .providers.firms import FirmsProvider
from .scenes import Scene, admit

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def build_providers() -> dict[str, object]:
    return {
        "dea": DeaProvider(),
        "firms": FirmsProvider(fixtures_dir=FIXTURES if FIXTURES.is_dir() else None),
    }


PROVIDERS = build_providers()


def provider_status() -> dict[str, dict]:
    """What each provider can do right now, and why not where it cannot."""
    pipeline = os.environ.get("BRIGHT_PIPELINE_PATH")
    firms = PROVIDERS["firms"]
    return {
        "dea": {
            "available": True,
            "reason": None,
            "footprints": False,
            "note": "DEA's WFS carries no scan or track column, so no footprints.",
        },
        "firms": {
            "available": firms.map_key() is not None or FIXTURES.is_dir(),
            "reason": None if firms.map_key() else "no FIRMS_MAP_KEY; fixtures serve "
                                                   "historical scenes only",
            "footprints": polar_footprints.available(),
            "note": "Fixtures never serve the current scene.",
        },
        "bright": {
            "available": bool(pipeline),
            "reason": None if pipeline else "BRIGHT_PIPELINE_PATH unset",
            "footprints": True,
            "note": "Optional. Absent it, the interface runs on DEA and FIRMS alone.",
        },
    }


def fetch_scene(scene: Scene, sources: list[str] | None = None) -> dict:
    """Every admitted record for a scene, with footprints attached where possible."""
    wanted = sources or list(PROVIDERS)
    records: list[Detection] = []
    notes: dict[str, dict] = {}

    for name in wanted:
        provider = PROVIDERS.get(name)
        if provider is None:
            notes[name] = {"available": False, "reason": "unknown provider", "count": 0}
            continue
        if not provider.available(scene):
            notes[name] = {"available": False, "count": 0,
                           "reason": getattr(provider, "last_fallback_reason", None)
                           or "unavailable for this scene"}
            continue

        fetched = provider.fetch(scene)
        if name == "firms" and polar_footprints.available():
            fetched = _attach_polar(fetched, provider)

        kept = admit(fetched, scene)
        notes[name] = {
            "available": True,
            "count": len(kept),
            "dropped_by_scene": len(fetched) - len(kept),
            "used_fixture": getattr(provider, "last_used_fixture", False),
            "reason": getattr(provider, "last_fallback_reason", None),
        }
        records += kept

    return {"detections": records, "sources": notes}


def _attach_polar(records: list[Detection], provider) -> list[Detection]:
    out = []
    for record in records:
        geometry = provider.geometry_for(record.id)
        if geometry is None:
            out.append(record)
            continue
        try:
            out.append(polar_footprints.attach_polar_footprint(record, geometry))
        except KeyError:
            # Unrecognised platform: keep the detection, drop the geometry claim.
            out.append(record)
    return out


__all__ = ["PROVIDERS", "fetch_scene", "provider_status", "ahi_footprints"]
