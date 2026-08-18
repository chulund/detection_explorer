"""What was asked for, not only what came back.

The layer taxonomy is derived from the records present, which means a product that was
queried and returned nothing simply vanishes from the interface. `MODIS_SP` is queried for
the demo scene and has no records in that hour; silently omitting it would let a reader
conclude MODIS was never consulted. Reporting the query separately from the result is the
difference between "no MODIS detections" and "no MODIS".
"""

from __future__ import annotations

from app.registry import fetch_scene
from app.scenes import get_scene


def test_firms_reports_the_products_it_queried():
    scene = get_scene("april-9-demo")
    notes = fetch_scene(scene, sources=["firms"])["sources"]["firms"]
    assert "MODIS_SP" in notes["products_queried"]
    assert "VIIRS_SNPP_SP" in notes["products_queried"]
    assert "VIIRS_NOAA20_SP" in notes["products_queried"]


def test_the_current_scene_queries_the_near_real_time_products_instead():
    """A different scene asks different questions, and the report has to follow."""
    scene = get_scene("current")
    notes = fetch_scene(scene, sources=["firms"])["sources"]["firms"]
    assert all(p.endswith("_NRT") for p in notes["products_queried"])
    assert "VIIRS_NOAA21_NRT" in notes["products_queried"]


def test_dea_reports_its_single_query():
    """DEA has no product parameter; it returns whatever algorithms the service holds."""
    scene = get_scene("april-9-demo")
    notes = fetch_scene(scene, sources=["dea"])["sources"]["dea"]
    assert notes["products_queried"] == ["*"]


def test_an_unavailable_provider_still_says_what_it_would_have_asked_for(monkeypatch):
    """Absence of a key must not also mean absence of the catalogue."""
    from app.registry import PROVIDERS

    monkeypatch.setattr(PROVIDERS["firms"], "available", lambda scene: False)
    scene = get_scene("april-9-demo")
    notes = fetch_scene(scene, sources=["firms"])["sources"]["firms"]
    assert notes["available"] is False
    assert notes["products_queried"]
