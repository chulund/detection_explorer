"""D2's routes are a permanent contract.

The July feed shipped `/api/status`, `/api/detections/latest` and `/api/detections/history`
unversioned. Moving them under `/api/v1` would break any existing consumer even with an
identical response body, so the originals stay exactly where they are and `/api/v1` mirrors
them. Schema 2.0 lives only under `/api/v2`.
"""

from __future__ import annotations

D2_ROUTES = ("/api/status", "/api/detections/latest", "/api/detections/history")


def test_d2_routes_answer_unversioned(client):
    for route in D2_ROUTES:
        assert client.get(route).status_code == 200, route


def test_v1_mirrors_the_unversioned_routes(client):
    for route in D2_ROUTES:
        assert client.get(route).json() == client.get(f"/api/v1{route[4:]}").json()


def test_d2_status_carries_the_d2_shape(client):
    body = client.get("/api/status").json()
    assert set(body) == {"feed_info", "cadence_seconds", "server_time", "sources"}


def test_d2_status_does_not_leak_v2_providers(client):
    """The D2 handler reports D2 source status and nothing else."""
    body = client.get("/api/status").json()
    assert set(body["sources"]) <= {"dea_live", "bright_replay"}
    assert "providers" not in body


def test_d2_detections_carry_only_d2_fields(client, seeded_legacy_store):
    """A v2 field appearing here would change a payload July already published."""
    d2_fields = {"id", "source", "data_nature", "detected_at", "published_at",
                 "lat", "lon", "frp_mw", "confidence", "satellite", "algorithm",
                 "replay_of"}
    rows = client.get("/api/detections/latest").json()["detections"]
    assert rows
    for row in rows:
        assert set(row) == d2_fields


def test_d2_geojson_format_still_offered(client, seeded_legacy_store):
    body = client.get("/api/detections/latest?format=geojson").json()
    assert body["type"] == "FeatureCollection"
    assert body["features"][0]["geometry"]["type"] == "Point"


def test_v2_status_reports_providers_separately(client):
    body = client.get("/api/v2/status").json()
    assert set(body["providers"]) == {"dea", "firms", "bright"}
    assert body["schema_version"] == "2.0"
