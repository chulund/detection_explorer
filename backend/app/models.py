"""The v2 detection record: an additive superset of the July feed's.

Every field D2 published keeps its name, type and meaning. That continuity is deliberate
rather than sentimental: D3's first acceptance criterion is an interface *consuming the D2
feed*, so an examiner must be able to diff the two payloads and see July's work carried
forward rather than quietly replaced.

Three properties are kept in three separate fields because conflating them misrepresents the
data. `data_nature` says what the observation scientifically is. `computation` says where the
record came from. Whether a response was served fresh or from cache is a property of the run,
not of the observation, so it lives on the run and not here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any

from shapely.geometry import mapping

# CONTEXT.md section 5. `simulated` and `synthetic` are defined by the project but
# unused here: D3 ships no model output and invents no records.
DATA_NATURES = frozenset({"live", "replay", "static", "simulated", "synthetic"})
COMPUTATIONS = frozenset({"retrieved", "computed"})
FOOTPRINT_METHODS = frozenset({"ahi_grid", "polar_reconstructed"})
FOOTPRINT_STATUSES = frozenset({"validated", "experimental"})
FOOTPRINT_SIDES = frozenset({"ambiguous", "assumed_right", "assumed_left"})

#: The only value `footprint_kind` ever takes. It exists so that no consumer can
#: mistake a satellite pixel footprint for a fire perimeter.
FOOTPRINT_KIND = "satellite_pixel_footprint"

SCHEMA_VERSION = "2.0"


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Detection:
    # --- D2 fields, unchanged -------------------------------------------------
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

    # --- provenance, split apart ----------------------------------------------
    platform: str
    instrument: str
    product: str
    algorithm_version: str
    computation: str

    # --- measurement, with its own semantics preserved ------------------------
    confidence_native: str | float | None
    confidence_scheme: str | None

    # --- geometry: these six stand or fall together ---------------------------
    footprint: dict[str, Any] | None
    footprint_kind: str | None
    footprint_method: str | None
    footprint_model_version: str | None
    footprint_status: str | None
    footprint_side: str | None

    # --- reproducibility ------------------------------------------------------
    input_window: dict[str, str]

    def __post_init__(self) -> None:
        if self.data_nature not in DATA_NATURES:
            raise ValueError(
                f"data_nature {self.data_nature!r} is outside the project vocabulary "
                f"{sorted(DATA_NATURES)}"
            )
        if self.computation not in COMPUTATIONS:
            raise ValueError(
                f"computation {self.computation!r} must be one of {sorted(COMPUTATIONS)}"
            )
        block = (self.footprint, self.footprint_kind, self.footprint_method,
                 self.footprint_model_version, self.footprint_status)
        if any(v is None for v in block) and any(v is not None for v in block):
            raise ValueError(
                "the footprint block is all-or-nothing; got a partially populated record"
            )

    @classmethod
    def point(cls, **fields: Any) -> "Detection":
        """A detection with no footprint. All six geometry fields default to None."""
        fields.setdefault("replay_of", None)
        for name in ("footprint", "footprint_kind", "footprint_method",
                     "footprint_model_version", "footprint_status", "footprint_side"):
            fields.setdefault(name, None)
        return cls(**fields)

    def with_footprint(self, geometry, *, method: str, model_version: str,
                       status: str, side: str | None) -> "Detection":
        """Attach geometry and its provenance together, returning a new record."""
        if method not in FOOTPRINT_METHODS:
            raise ValueError(f"footprint_method {method!r} not in {sorted(FOOTPRINT_METHODS)}")
        if status not in FOOTPRINT_STATUSES:
            raise ValueError(f"footprint_status {status!r} not in {sorted(FOOTPRINT_STATUSES)}")
        if side is not None and side not in FOOTPRINT_SIDES:
            raise ValueError(f"footprint_side {side!r} not in {sorted(FOOTPRINT_SIDES)}")
        return replace(
            self,
            footprint=mapping(geometry),
            footprint_kind=FOOTPRINT_KIND,
            footprint_method=method,
            footprint_model_version=model_version,
            footprint_status=status,
            footprint_side=side,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FEED_INFO_V2 = {
    "name": "RMIT Detection Explorer",
    "schema_version": SCHEMA_VERSION,
    "disclaimer": (
        "A demonstration interface running locally. The BRIGHT near-real-time pipeline "
        "used during the XPRIZE Wildfire finals no longer runs; detection here recomputes "
        "real April 2026 inputs and is labelled 'replay'. Polygons are satellite pixel "
        "footprints, never fire perimeters."
    ),
    "footprint_caveats": {
        "experimental": (
            "Experimental footprint: high-latitude orientation validation pending. Model "
            "comparisons have shown discrepancies of up to 892 m; this is not a measured "
            "error bound for this detection."
        ),
        "ambiguous": (
            "Two candidates shown. A FIRMS record cannot say which side of the satellite's "
            "ground track the pixel lay on, and at this latitude the two possibilities "
            "differ materially (measured: 0.78 overlap, up to 476 m at the corners)."
        ),
    },
}
