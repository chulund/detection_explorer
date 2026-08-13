"""MODIS and VIIRS footprints: reconstructed, experimental, and deliberately doubled.

A FIRMS row carries `scan` and `track`, and the whisk-broom relations of Ichoku and Kaufman
invert, so pixel dimensions are recoverable exactly. Orientation is the genuinely missing
quantity, and it is where the two known caveats live.

First, orientation. `polar_footprint.geometry` orients by the ground-track heading at the
pixel's own latitude, which is wrong away from the tropics because the scan arrives on a
different azimuth as meridians converge. `polar_footprint.corrected` fixes that, but the fix
has not been validated against a geolocation granule at Australian latitudes, so every
footprint here is labelled `experimental`.

Second, the side of the track. A FIRMS row cannot say whether the pixel lay left or right of
the ground track. In the uncorrected construction that scarcely mattered, agreeing to an IoU
of 0.997. Under the correction it matters a great deal: measured across the 505 detections in
the demonstration scene, agreement runs from 0.814 to 0.962, with 503 of them below 0.95 and
corner separations reaching 476 m. So both candidates are returned, and the record says
`ambiguous` rather than picking one and implying knowledge that does not exist.
"""

from __future__ import annotations

from functools import lru_cache

from shapely.geometry import MultiPolygon

from ..models import Detection

#: The polar_footprint commit whose geometry produced these polygons. Recorded on every
#: record so a footprint can be traced to the code that drew it.
MODEL_VERSION = "polar_footprint@918c0c0+corrected"

SIDE_AMBIGUOUS = "ambiguous"


@lru_cache(maxsize=1)
def _polar_footprint_module():
    """Import lazily so a clean clone without the optional dependency still starts."""
    from polar_footprint import SENSORS, is_ascending
    from polar_footprint.corrected import footprint_corrected

    return SENSORS, is_ascending, footprint_corrected


def available() -> bool:
    try:
        _polar_footprint_module()
    except ImportError:
        return False
    return True


def polar_footprint_for(row: dict) -> tuple[MultiPolygon, str]:
    """Both side candidates for one FIRMS row, as a two-member MultiPolygon.

    `row` needs `lat`, `lon`, `track`, `satellite` and `daynight`. The scan model is chosen
    from the satellite code rather than guessed, so an unrecognised platform raises instead
    of silently reconstructing with the wrong instrument geometry.
    """
    sensors, is_ascending, footprint_corrected = _polar_footprint_module()

    satellite = row["satellite"]
    if satellite not in sensors:
        raise KeyError(
            f"no scan model for satellite {satellite!r}; known: {sorted(sensors)}"
        )
    model = sensors[satellite]
    ascending = is_ascending(model, row["daynight"])

    candidates = [
        footprint_corrected(
            float(row["lat"]), float(row["lon"]), float(row["track"]), model,
            ascending=ascending, right_of_track=side,
        )
        for side in (True, False)
    ]
    return MultiPolygon(candidates), SIDE_AMBIGUOUS


def attach_polar_footprint(detection: Detection, row: dict) -> Detection:
    geometry, side = polar_footprint_for(row)
    return detection.with_footprint(
        geometry,
        method="polar_reconstructed",
        model_version=MODEL_VERSION,
        status="experimental",
        side=side,
    )
