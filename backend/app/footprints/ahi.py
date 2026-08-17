"""Himawari AHI footprints: exact, not reconstructed.

Every AHI pixel already has a polygon in the sensor grid shipped with the BRIGHT pipeline,
and a detection row carries the `x`, `y` that index it. So there is no modelling here, only
a join and a reprojection: the grid stores its polygons in geostationary metres, and a web
map wants degrees.

The projection is read from the sensor NetCDF's CF grid-mapping attributes rather than
hardcoded, because a wrong constant would shift every footprint silently and plausibly. The
centroid test in `test_footprints.py` is what proves the derivation right: a reprojected
pixel centre must land on the latitude and longitude the grid itself records for that pixel.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pyproj import Transformer
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon, mapping
from shapely.ops import transform as shapely_transform

from ..models import FOOTPRINT_KIND, Detection

#: Where the BRIGHT pipeline keeps its ancillary files. Overridable so a clean clone
#: without the pipeline can still start; the grid is simply unavailable then.
DEFAULT_PIPELINE = Path(r"D:\Orang\Mark\20260224_BRIGHT_delivery\xprize_finals_nsw_bright")

GRID_RELATIVE = Path("ancillary") / "himawari_pixel_grid_nsw.parquet"
SENSOR_RELATIVE = Path("ancillary") / (
    "00000000000000-P1S-ABOM_GEOM_SENSOR-PRJ_GEOS141_2000-HIMAWARI8-AHI_subset_nsw.nc"
)

MODEL_VERSION = "ahi_pixel_grid_nsw"


def pipeline_root() -> Path:
    return Path(os.environ.get("BRIGHT_PIPELINE_PATH") or DEFAULT_PIPELINE)


def available() -> bool:
    """Whether the AHI pixel grid and sensor file are actually reachable.

    They ship with the BRIGHT pipeline, which is an optional dependency, so the
    fixture profile runs without them. AHI footprints are simply absent there, and
    the interface reports that rather than failing.
    """
    root = pipeline_root()
    return (root / GRID_RELATIVE).exists() and (root / SENSOR_RELATIVE).exists()


@lru_cache(maxsize=1)
def geostationary_proj4() -> str:
    """Build the projection from the sensor file's CF attributes.

    The file carries a `proj4` attribute, but it omits the sweep axis, which for AHI is
    `y`. Getting that wrong rotates every footprint, so it is taken from
    `sweep_angle_axis` explicitly rather than assumed.
    """
    import netCDF4

    path = pipeline_root() / SENSOR_RELATIVE
    with netCDF4.Dataset(path) as dataset:
        attrs = dataset.variables["geostationary"]
        get = attrs.getncattr
        return (
            f"+proj=geos +lon_0={get('longitude_of_projection_origin')} "
            f"+h={get('perspective_point_height')} "
            f"+a={get('semi_major_axis')} +b={get('semi_minor_axis')} "
            f"+x_0={get('false_easting')} +y_0={get('false_northing')} "
            f"+sweep={get('sweep_angle_axis')} +units=m +no_defs"
        )


@lru_cache(maxsize=1)
def _to_wgs84():
    return Transformer.from_crs(geostationary_proj4(), "EPSG:4326",
                                always_xy=True).transform


@lru_cache(maxsize=1)
def grid_lookup() -> dict[tuple[int, int], dict]:
    """(x_subset, y_subset) -> {wkt, lat, lon} for every NSW Himawari pixel.

    Empty when the pipeline is not installed, so callers degrade rather than raise.
    """
    if not available():
        return {}

    import pandas as pd

    frame = pd.read_parquet(pipeline_root() / GRID_RELATIVE)
    return {
        (int(row.x_subset), int(row.y_subset)):
            {"wkt": row.pixel_wkt, "lat": float(row.latitude), "lon": float(row.longitude)}
        for row in frame.itertuples(index=False)
    }


@lru_cache(maxsize=100_000)
def pixel_footprint(x: int, y: int) -> Polygon | None:
    """The pixel's ground footprint in EPSG:4326, or None if the pixel is off-grid."""
    entry = grid_lookup().get((int(x), int(y)))
    if entry is None:
        return None
    return shapely_transform(_to_wgs84(), shapely_wkt.loads(entry["wkt"]))


def attach_ahi_footprint(detection: Detection, x: int, y: int) -> Detection:
    """Attach the exact pixel polygon. Validated, and no side ambiguity to declare."""
    poly = pixel_footprint(x, y)
    if poly is None:
        return detection
    return detection.with_footprint(
        poly,
        method="ahi_grid",
        model_version=MODEL_VERSION,
        status="validated",
        side=None,
    )


def attach_row_footprints(rows: list[dict]) -> list[dict]:
    """The same join, for the CSV rows a BRIGHT run produces.

    A run does not go through `Detection`; it emits rows straight from the pipeline's
    output file, and those rows are what the browser draws. They carry the same `x`,`y`
    that index the grid, so they can carry the same exact polygon rather than being
    reduced to a point.

    A row whose pixel is not in the grid, or which predates the join and has no `x`,`y`
    at all, comes back with `footprint: None`. Absent is absent: deriving a polygon from
    the row's own latitude and longitude would move the detection somewhere the sensor
    never looked.
    """
    out = []
    for row in rows:
        enriched = dict(row)
        poly = None
        try:
            poly = pixel_footprint(int(row["x"]), int(row["y"]))
        except (KeyError, TypeError, ValueError):
            poly = None
        enriched.update(
            footprint=mapping(poly) if poly is not None else None,
            footprint_kind=FOOTPRINT_KIND if poly is not None else None,
            footprint_method="ahi_grid" if poly is not None else None,
            footprint_model_version=MODEL_VERSION if poly is not None else None,
            footprint_status="validated" if poly is not None else None,
            footprint_side=None,
        )
        out.append(enriched)
    return out
