"""The retrieval endpoint, and the epoch separation it must never break."""

from __future__ import annotations

import pytest


def test_scene_is_required_not_defaulted(client):
    """A default would let a caller retrieve records without saying which epoch
    they belong to, which is the mistake scenes exist to prevent."""
    assert client.get("/api/v2/detections").status_code == 422


def test_unknown_scene_is_a_404(client):
    assert client.get("/api/v2/detections?scene=nope").status_code == 404


def test_demo_scene_returns_records(client, monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    body = client.get("/api/v2/detections?scene=april-9-demo&sources=firms").json()
    assert body["count"] == 505
    assert body["schema_version"] == "2.0"


def test_demo_scene_admits_no_live_records(client, monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    body = client.get("/api/v2/detections?scene=april-9-demo&sources=firms").json()
    assert {d["data_nature"] for d in body["detections"]} == {"static"}


def test_source_notes_explain_absence(client, monkeypatch):
    """An examiner must be able to see why a source is missing, not just that it is."""
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    body = client.get("/api/v2/detections?scene=current&sources=firms").json()
    note = body["sources"]["firms"]
    assert note["available"] is False
    assert note["reason"]


def test_geojson_uses_the_footprint_as_geometry(client, monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    body = client.get(
        "/api/v2/detections?scene=april-9-demo&sources=firms&format=geojson").json()
    kinds = {f["geometry"]["type"] for f in body["features"]}
    assert "MultiPolygon" in kinds


def test_geojson_features_keep_their_provenance(client, monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    body = client.get(
        "/api/v2/detections?scene=april-9-demo&sources=firms&format=geojson").json()
    props = body["features"][0]["properties"]
    for field in ("data_nature", "computation", "footprint_status", "footprint_side",
                  "confidence_native", "confidence_scheme", "platform", "instrument"):
        assert field in props


def test_polar_records_are_labelled_experimental_and_ambiguous(client, monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    body = client.get("/api/v2/detections?scene=april-9-demo&sources=firms").json()
    statuses = {d["footprint_status"] for d in body["detections"]}
    sides = {d["footprint_side"] for d in body["detections"]}
    assert statuses == {"experimental"}
    assert sides == {"ambiguous"}


def test_v2_status_reports_all_three_providers(client):
    body = client.get("/api/v2/status").json()
    assert set(body["providers"]) == {"dea", "firms", "bright"}
    for entry in body["providers"].values():
        assert "available" in entry and "footprints" in entry
    assert body["providers"]["bright"]["reproducible"] is False


def test_scenes_endpoint_declares_the_half_open_window(client):
    scenes = {s["id"]: s for s in client.get("/api/v2/scenes").json()["scenes"]}
    demo = scenes["april-9-demo"]
    assert demo["window"]["half_open"] is True
    assert demo["window"]["start"] == "2026-04-09T04:00:00Z"
    assert len(demo["frames"]) == 6
    assert scenes["current"]["rolling"] is True


def test_weather_is_reported_apart_from_detection_providers(client):
    """Weather is contextual, not a detection source. Putting it among the providers
    would muddle what "provider" means in this API."""
    body = client.get("/api/v2/status").json()
    assert "weather" not in body["providers"]
    assert set(body["context"]) == {"weather"}


def test_weather_key_absence_is_stated_rather_than_implied(client, monkeypatch):
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    weather = client.get("/api/v2/status").json()["context"]["weather"]
    assert weather["available"] is False
    assert "OPENWEATHER_API_KEY" in weather["reason"]
    assert weather["key"] is None
