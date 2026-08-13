"""Schema v2 must extend D2's record without disturbing it.

D3's first acceptance criterion is an interface *consuming the D2 feed*, so an examiner has
to be able to diff the two payloads and see July's work carried forward rather than replaced.
That makes the D2 field set a contract, not an implementation detail.
"""

from __future__ import annotations

import pytest

from app.models import Detection

D2_FIELDS = {
    "id", "source", "data_nature", "detected_at", "published_at",
    "lat", "lon", "frp_mw", "confidence", "satellite", "algorithm", "replay_of",
}

SAMPLE = dict(
    id="dea:1", source="dea", data_nature="live",
    detected_at="2026-04-09T04:20:00Z", published_at="2026-04-09T04:30:00Z",
    lat=-33.0, lon=150.0, frp_mw=12.0,
    satellite="NOAA 20", platform="NOAA-20", instrument="VIIRS", product="AFIMG",
    algorithm="AFIMG", algorithm_version="6",
    computation="retrieved",
    input_window={"start": "2026-04-09T04:00:00Z", "end": "2026-04-09T05:00:00Z"},
)


def test_d2_field_names_survive_unchanged():
    assert D2_FIELDS <= set(Detection.__dataclass_fields__)


def test_point_leaves_every_footprint_field_null():
    """A caller must not be able to half-populate the footprint block."""
    d = Detection.point(**SAMPLE, confidence=80.0,
                        confidence_native="80", confidence_scheme="dea_percent")
    assert d.footprint is None
    assert d.footprint_kind is None
    assert d.footprint_method is None
    assert d.footprint_model_version is None
    assert d.footprint_status is None
    assert d.footprint_side is None


def test_categorical_confidence_is_preserved_not_coerced():
    """Real VIIRS SP rows carry confidence 'n' for nominal. Forcing that to a float
    would invent information the source does not carry."""
    d = Detection.point(**SAMPLE, confidence=None,
                        confidence_native="n", confidence_scheme="viirs_categorical")
    assert d.confidence is None
    assert d.confidence_native == "n"
    assert d.confidence_scheme == "viirs_categorical"


def test_data_nature_is_restricted_to_the_project_vocabulary():
    """CONTEXT.md section 5 defines the vocabulary; inventing a value breaks the
    honesty labelling the whole deliverable rests on."""
    with pytest.raises(ValueError, match="data_nature"):
        Detection.point(**{**SAMPLE, "data_nature": "archive"}, confidence=None,
                        confidence_native=None, confidence_scheme=None)


def test_computation_is_restricted():
    with pytest.raises(ValueError, match="computation"):
        Detection.point(**{**SAMPLE, "computation": "guessed"}, confidence=None,
                        confidence_native=None, confidence_scheme=None)


def test_with_footprint_sets_the_whole_block_together():
    from shapely.geometry import Polygon

    d = Detection.point(**SAMPLE, confidence=None,
                        confidence_native="n", confidence_scheme="viirs_categorical")
    poly = Polygon([(150, -33), (150.01, -33), (150.01, -33.01), (150, -33.01)])
    e = d.with_footprint(poly, method="polar_reconstructed", model_version="918c0c0",
                         status="experimental", side="ambiguous")
    assert e.footprint["type"] == "Polygon"
    assert e.footprint_kind == "satellite_pixel_footprint"
    assert e.footprint_method == "polar_reconstructed"
    assert e.footprint_status == "experimental"
    assert e.footprint_side == "ambiguous"
    assert d.footprint is None, "with_footprint must not mutate the original"


def test_to_dict_round_trips_through_json():
    import json

    d = Detection.point(**SAMPLE, confidence=None,
                        confidence_native="n", confidence_scheme="viirs_categorical")
    assert json.loads(json.dumps(d.to_dict()))["confidence_native"] == "n"
