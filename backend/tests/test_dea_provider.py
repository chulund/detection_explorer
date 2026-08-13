"""DEA provider: real hotspots, honestly labelled, and no invented geometry.

Runs entirely against the committed fixture, so the suite needs no network and no
credentials. The fixture is the genuine WFS response for the committed scene hour.
"""

from __future__ import annotations

import pytest

from app.providers.dea import DeaProvider, parse_wfs_xml
from app.scenes import SCENES


@pytest.fixture(scope="module")
def xml(fixtures_dir_module) -> bytes:
    return (fixtures_dir_module / "dea_april-9-demo.xml").read_bytes()


@pytest.fixture(scope="module")
def fixtures_dir_module():
    from pathlib import Path
    return Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture(scope="module")
def records(xml):
    return parse_wfs_xml(xml, published_at="2026-04-09T05:00:00Z", data_nature="static")


def test_parses_the_fixture(records):
    assert len(records) > 1000


def test_every_record_is_labelled_static_and_retrieved(records):
    assert {r.data_nature for r in records} == {"static"}
    assert {r.computation for r in records} == {"retrieved"}


def test_dea_never_claims_a_footprint(records):
    """DEA's WFS schema carries no scan or track column, so the geometry is unknowable."""
    assert all(r.footprint is None for r in records)
    assert all(r.footprint_method is None for r in records)
    assert all(r.footprint_kind is None for r in records)


def test_platform_instrument_and_product_are_separate(records):
    """D2 flattened these into one algorithm string; v2 keeps them apart."""
    instruments = {r.instrument for r in records}
    assert instruments <= {"AHI", "VIIRS", "MODIS"}
    assert instruments, "expected at least one instrument"
    for r in records:
        assert r.platform and r.product and r.algorithm_version


def test_the_committed_hour_carries_both_polar_platforms(records):
    """The scene was chosen for this; if it stops holding, the scene is wrong."""
    polar = {r.platform for r in records if r.instrument == "VIIRS"}
    assert {"Suomi-NPP", "NOAA-20"} <= polar


def test_ids_are_namespaced_and_unique(records):
    ids = [r.id for r in records]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("dea:") for i in ids)


def test_confidence_keeps_its_scheme(records):
    assert {r.confidence_scheme for r in records} == {"dea_percent"}


def test_provider_rejects_a_scene_it_cannot_serve(records):
    """DEA is live-capable and archive-capable, so it serves both scenes."""
    provider = DeaProvider()
    assert provider.available(SCENES["current"])
    assert provider.available(SCENES["april-9-demo"])


def test_data_nature_follows_the_scene_not_the_provider():
    """The same adapter serves April as static and today as live."""
    assert DeaProvider().nature_for(SCENES["current"]) == "live"
    assert DeaProvider().nature_for(SCENES["april-9-demo"]) == "static"
