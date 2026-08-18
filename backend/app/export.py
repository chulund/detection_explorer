"""Export: GeoJSON and CSV, from parameters the caller states explicitly.

FR-EXPORT asked for "any spatial or temporal selection". The temptation is an endpoint that
exports "the current selection", but a stateless HTTP API has no current selection, and
guessing one would silently produce a different file from the one on screen. So everything is
named: the scene, the format, and either a run or a set of sources with a time range.

GeoJSON uses the footprint as the feature geometry where a record has one and falls back to
the point where it does not, so DEA points and VIIRS footprints can share a file without
either pretending to geometry it lacks. CSV flattens the footprint to WKT and keeps every
provenance column, because a spreadsheet that loses `footprint_status` would let an
experimental polygon be mistaken for a validated one.

One interoperability note, deliberate rather than accidental. A polar footprint is a
MultiPolygon of two overlapping candidates, because a FIRMS row cannot say which side of the
ground track the pixel lay on. RFC 7946, the GeoJSON standard, allows that: it requires only
that each element be a valid Polygon. OGC Simple Features does not, since it expects a
MultiPolygon's parts to have disjoint interiors, so strict GIS tooling may flag these. The
alternative, exporting the union, would be OGC-valid and would overstate pixel area by 5 to
12 per cent, quietly corrupting the size comparison the whole interface exists to make. The
`footprint_side` column says `ambiguous` on every such record.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from shapely.geometry import mapping, shape

from .models import SCHEMA_VERSION, Detection

CSV_COLUMNS = (
    "id", "source", "data_nature", "computation",
    "detected_at", "published_at", "replay_of",
    "lat", "lon", "frp_mw",
    "confidence", "confidence_native", "confidence_scheme",
    "brightness_k", "brightness_channel",
    "platform", "instrument", "product", "algorithm", "algorithm_version",
    "footprint_kind", "footprint_method", "footprint_model_version",
    "footprint_status", "footprint_side", "footprint_wkt",
)


def in_bbox(record: Detection, bbox: tuple[float, float, float, float]) -> bool:
    west, south, east, north = bbox
    return west <= record.lon <= east and south <= record.lat <= north


def parse_bbox(raw: str) -> tuple[float, float, float, float]:
    parts = [float(p) for p in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be west,south,east,north")
    west, south, east, north = parts
    if west > east or south > north:
        raise ValueError("bbox must be west,south,east,north with west<=east, south<=north")
    return west, south, east, north


def to_geojson(records: list[Detection], scene: dict) -> dict:
    return {
        "type": "FeatureCollection",
        "schema_version": SCHEMA_VERSION,
        "scene": scene,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "features": [_feature(r) for r in records],
    }


def _feature(record: Detection) -> dict:
    body = record.to_dict()
    geometry = body.pop("footprint", None)
    if geometry is None:
        geometry = {"type": "Point", "coordinates": [record.lon, record.lat]}
    else:
        # Normalise through shapely so exported geometry is always valid GeoJSON.
        geometry = mapping(shape(geometry))
    return {"type": "Feature", "geometry": geometry, "properties": body}


def to_csv(records: list[Detection]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(CSV_COLUMNS),
                            extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for record in records:
        row = record.to_dict()
        footprint = row.pop("footprint", None)
        row["footprint_wkt"] = shape(footprint).wkt if footprint else ""
        writer.writerow(row)
    return buffer.getvalue()
