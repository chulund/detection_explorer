"""The July feed's routes, preserved exactly.

D2 shipped `/api/status`, `/api/detections/latest` and `/api/detections/history` unversioned,
and something may already be consuming them. Moving those paths under `/api/v1` would be a
breaking change even with a byte-identical body, so the originals stay where they are and
`/api/v1` mirrors them. Schema 2.0 lives only under `/api/v2`.

The record shape, the `feed_info` block and the GeoJSON projection are carried over from
`deliverable_2_july/feed/` rather than reimplemented, so that a diff between the two payloads
shows continuity. Nothing here learns about v2 providers: `/api/status` reports D2 source
status and nothing else.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

TICK_SECONDS = 600

D2_COLUMNS = ("id", "source", "data_nature", "detected_at", "published_at",
              "lat", "lon", "frp_mw", "confidence", "satellite", "algorithm", "replay_of")


@dataclass(frozen=True)
class LegacyDetection:
    """D2's record, unchanged. Deliberately not the v2 `Detection`."""
    id: str
    source: str
    data_nature: str
    detected_at: str
    published_at: str
    lat: float
    lon: float
    frp_mw: float | None
    confidence: float | None
    satellite: str
    algorithm: str
    replay_of: str | None

    def to_dict(self) -> dict:
        return asdict(self)


FEED_INFO = {
    "name": "RMIT BRIGHT wildfire detection feed (grant deliverable D2, July 2026)",
    "cadence_minutes": 10,
    "disclaimer": (
        "This feed is a demonstration running on local infrastructure. It does NOT "
        "represent a live BRIGHT v2.0 detection pipeline. It can be deployed unchanged "
        "to a cloud instance (e.g. AWS EC2/Lightsail) if operational hosting is required."
    ),
    "sources": {
        "dea_live": {
            "data_nature": "live",
            "description": (
                "Current hotspots from Digital Earth Australia's operational Hotspots "
                "service (process_algorithm 'BRIGHT AHI'), which carries the research "
                "team's earlier BRIGHT algorithm generation. Australia-wide."
            ),
        },
        "bright_replay": {
            "data_nature": "replay",
            "description": (
                "Real BRIGHT v2.0 detections produced during the XPRIZE Wildfire finals "
                "(NSW, 2026-04-09), republished on a schedule as a replay. detected_at is "
                "the original April 2026 detection time; replay_of is the original "
                "10-minute slot."
            ),
        },
    },
}


class LegacyStore:
    """In-memory stand-in for D2's SQLite store, with the same query semantics."""

    def __init__(self) -> None:
        self._rows: list[LegacyDetection] = []
        self._ticks: list[tuple[str, str, bool, int]] = []

    def reset(self) -> None:
        self._rows.clear()
        self._ticks.clear()

    def upsert(self, records: list[LegacyDetection]) -> int:
        by_id = {r.id: r for r in self._rows}
        for record in records:
            by_id[record.id] = record
        self._rows = list(by_id.values())
        return len(records)

    def log_tick(self, source: str, tick_iso: str, ok: bool, n_records: int) -> None:
        self._ticks.append((tick_iso, source, ok, n_records))

    def latest(self, source: str | None = None) -> list[dict]:
        sources = [source] if source else sorted({r.source for r in self._rows})
        out: list[dict] = []
        for src in sources:
            rows = [r for r in self._rows if r.source == src]
            if not rows:
                continue
            newest = max(r.published_at for r in rows)
            out += [r.to_dict() for r in sorted(rows, key=lambda r: r.id)
                    if r.published_at == newest]
        return out

    def history(self, hours: float) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        return [r.to_dict() for r in sorted(self._rows, key=lambda r: (r.published_at, r.id))
                if r.published_at >= cutoff]

    def source_status(self) -> dict:
        status: dict = {}
        for src in sorted({t[1] for t in self._ticks}):
            oks = [t for t in self._ticks if t[1] == src and t[2]]
            last_ok = max(oks, key=lambda t: t[0]) if oks else None
            status[src] = {
                "last_ok_tick": last_ok[0] if last_ok else None,
                "last_tick_records": last_ok[3] if last_ok else 0,
                "consecutive_failures": sum(
                    1 for t in self._ticks
                    if t[1] == src and t[0] > (last_ok[0] if last_ok else "")),
                "total_records": sum(1 for r in self._rows if r.source == src),
            }
        return status


LEGACY_STORE = LegacyStore()


def _next_tick() -> str:
    now = datetime.now(timezone.utc)
    boundary = (now.timestamp() // TICK_SECONDS + 1) * TICK_SECONDS
    return datetime.fromtimestamp(boundary, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _payload(rows: list[dict], fmt: str) -> dict:
    if fmt == "geojson":
        return {
            "type": "FeatureCollection",
            "feed_info": FEED_INFO,
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
                "properties": {k: v for k, v in r.items() if k not in ("lat", "lon")},
            } for r in rows],
        }
    return {"feed_info": FEED_INFO, "count": len(rows), "detections": rows}


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/status")
    def status() -> dict:
        nxt = _next_tick()
        sources = LEGACY_STORE.source_status()
        for entry in sources.values():
            entry["next_tick_at"] = nxt
        return {
            "feed_info": FEED_INFO,
            "cadence_seconds": TICK_SECONDS,
            "server_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sources": sources,
        }

    @router.get("/detections/latest")
    def latest(source: str | None = None,
               format: str = Query("json", pattern="^(json|geojson)$")) -> dict:
        if source is not None and source not in FEED_INFO["sources"]:
            raise HTTPException(404, f"unknown source '{source}'")
        return _payload(LEGACY_STORE.latest(source), format)

    @router.get("/detections/history")
    def history(hours: float = Query(24, gt=0, le=168),
                format: str = Query("json", pattern="^(json|geojson)$")) -> dict:
        return _payload(LEGACY_STORE.history(hours), format)

    return router
