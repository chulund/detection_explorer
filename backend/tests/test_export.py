"""Export: nothing inferred, nothing lost.

FR-EXPORT from the May design deck. The two things worth guarding are that the caller must
state its selection rather than rely on the server guessing one, and that provenance survives
the trip into a spreadsheet, since a CSV that loses footprint_status would let an experimental
polygon pass for a validated one.
"""

from __future__ import annotations

import csv
import io

import pytest


@pytest.fixture(autouse=True)
def no_map_key(monkeypatch):
    """Force the fixture path so the suite stays offline and deterministic."""
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)


def test_format_is_required(client):
    assert client.get("/api/v2/export?scene=april-9-demo").status_code == 422


def test_scene_is_required(client):
    assert client.get("/api/v2/export?format=csv").status_code == 422


def test_unknown_scene_is_404(client):
    assert client.get("/api/v2/export?scene=nope&format=csv").status_code == 404


def test_bad_format_is_rejected(client):
    assert client.get(
        "/api/v2/export?scene=april-9-demo&format=shapefile").status_code == 422


def test_geojson_uses_footprints_as_geometry(client):
    body = client.get(
        "/api/v2/export?scene=april-9-demo&sources=firms&format=geojson").json()
    kinds = {f["geometry"]["type"] for f in body["features"]}
    assert "MultiPolygon" in kinds
    assert body["schema_version"] == "2.0"


def test_geojson_records_the_scene_it_came_from(client):
    body = client.get(
        "/api/v2/export?scene=april-9-demo&sources=firms&format=geojson").json()
    assert body["scene"]["id"] == "april-9-demo"
    assert body["scene"]["window"]["half_open"] is True


def test_csv_header_keeps_every_provenance_column(client):
    text = client.get(
        "/api/v2/export?scene=april-9-demo&sources=firms&format=csv").text
    header = next(csv.reader(io.StringIO(text)))
    for column in ("data_nature", "computation", "footprint_status", "footprint_side",
                   "confidence_native", "confidence_scheme", "platform", "instrument",
                   "footprint_model_version"):
        assert column in header


def test_csv_flattens_the_footprint_to_wkt(client):
    text = client.get(
        "/api/v2/export?scene=april-9-demo&sources=firms&format=csv").text
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows
    assert rows[0]["footprint_wkt"].startswith("MULTIPOLYGON")


def test_csv_is_offered_as_a_download(client):
    response = client.get(
        "/api/v2/export?scene=april-9-demo&sources=firms&format=csv")
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]


def test_a_time_range_narrows_the_export(client):
    everything = client.get(
        "/api/v2/export?scene=april-9-demo&sources=firms&format=geojson").json()
    narrowed = client.get(
        "/api/v2/export?scene=april-9-demo&sources=firms&format=geojson"
        "&start=2026-04-09T04:40:00Z&end=2026-04-09T05:00:00Z").json()
    assert 0 < len(narrowed["features"]) < len(everything["features"])


def test_a_bbox_narrows_the_export(client):
    everything = client.get(
        "/api/v2/export?scene=april-9-demo&sources=firms&format=geojson").json()
    narrowed = client.get(
        "/api/v2/export?scene=april-9-demo&sources=firms&format=geojson"
        "&bbox=140,-38,146,-34").json()
    assert 0 < len(narrowed["features"]) < len(everything["features"])


def test_a_malformed_bbox_is_refused(client):
    assert client.get(
        "/api/v2/export?scene=april-9-demo&format=geojson&bbox=1,2,3").status_code == 422
    assert client.get(
        "/api/v2/export?scene=april-9-demo&format=geojson"
        "&bbox=150,-30,140,-40").status_code == 422


def test_every_exported_polygon_is_individually_valid(client):
    """Each candidate must be a sound ring.

    Note what is *not* asserted: that the MultiPolygon is OGC-valid. OGC Simple
    Features requires a MultiPolygon's parts to have disjoint interiors, and the two
    side candidates deliberately overlap, because they are alternative positions for
    one pixel rather than parts of one object. RFC 7946, the GeoJSON standard this API
    emits, imposes no such requirement. Collapsing them to their union would produce an
    OGC-valid polygon that overstates pixel area by 5 to 12 per cent, which would
    quietly corrupt the AHI-against-VIIRS size comparison the interface exists to make.
    """
    from shapely.geometry import shape

    body = client.get(
        "/api/v2/export?scene=april-9-demo&sources=firms&format=geojson").json()
    checked = 0
    for feature in body["features"][:20]:
        geometry = shape(feature["geometry"])
        parts = list(getattr(geometry, "geoms", [geometry]))
        for part in parts:
            assert part.is_valid and part.area > 0
            checked += 1
    assert checked >= 20


def test_ambiguous_footprints_carry_exactly_two_candidates(client):
    body = client.get(
        "/api/v2/export?scene=april-9-demo&sources=firms&format=geojson").json()
    ambiguous = [f for f in body["features"]
                 if f["properties"]["footprint_side"] == "ambiguous"]
    assert ambiguous
    for feature in ambiguous[:20]:
        assert feature["geometry"]["type"] == "MultiPolygon"
        assert len(feature["geometry"]["coordinates"]) == 2
