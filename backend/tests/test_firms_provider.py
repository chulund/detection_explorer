"""FIRMS provider: reproducible history, and no fixture ever masquerading as live.

The interesting behaviour here is not parsing. It is that "unavailable" and "stale substitute"
are different answers, and the provider must give the first one in the current scene. Serving
April records into a feed labelled live would break the honesty rule the whole deliverable
rests on, so it is tested rather than merely intended.
"""

from __future__ import annotations

import pytest

from app.providers.firms import FirmsProvider, parse_firms_csv
from app.scenes import SCENES


@pytest.fixture
def provider(fixtures_dir) -> FirmsProvider:
    return FirmsProvider(fixtures_dir=fixtures_dir)


# --------------------------------------------------------------- product selection

def test_historical_scenes_use_standard_processing_only():
    sources = FirmsProvider.sources_for(SCENES["april-9-demo"])
    assert set(sources) == {"MODIS_SP", "VIIRS_SNPP_SP", "VIIRS_NOAA20_SP"}


def test_noaa21_is_excluded_from_history_but_available_now():
    """FIRMS publishes no VIIRS_NOAA21_SP, so NOAA-21 cannot be reproducible."""
    assert not any("NOAA21" in s for s in FirmsProvider.sources_for(SCENES["april-9-demo"]))
    assert any("NOAA21" in s for s in FirmsProvider.sources_for(SCENES["current"]))


def test_current_scene_uses_near_real_time_products():
    assert all(s.endswith("_NRT") for s in FirmsProvider.sources_for(SCENES["current"]))


# --------------------------------------------------------------- the honesty rule

def test_current_scene_is_unavailable_without_a_key(provider, monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    assert provider.available(SCENES["current"]) is False


def test_current_scene_never_serves_a_fixture(provider, monkeypatch):
    """Absent means absent. Substituting April records into a live feed is the one
    thing this provider must never do."""
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    assert provider.fetch(SCENES["current"]) == []
    assert provider.last_fallback_reason == "no_map_key"
    assert provider.last_used_fixture is False


def test_historical_scene_falls_back_to_fixtures_without_a_key(provider, monkeypatch):
    """A fixture of historical records is still historical, so the label stays true."""
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    records = provider.fetch(SCENES["april-9-demo"])
    assert records
    assert provider.last_used_fixture is True
    assert {r.data_nature for r in records} == {"static"}


# --------------------------------------------------------------- API contract

def test_day_range_outside_one_to_five_is_rejected():
    with pytest.raises(ValueError, match="1 to 5"):
        FirmsProvider.build_url("KEY", "MODIS_SP", "140,-38,154,-28", 9, "2026-04-09")


def test_build_url_shape():
    url = FirmsProvider.build_url("KEY", "VIIRS_SNPP_SP", "140,-38,154,-28", 1, "2026-04-09")
    assert url.endswith("/area/csv/KEY/VIIRS_SNPP_SP/140,-38,154,-28/1/2026-04-09")


# --------------------------------------------------------------- parsing

def test_parses_scan_track_and_daynight(fixtures_dir):
    rows = parse_firms_csv(
        (fixtures_dir / "firms_viirs_snpp_sp_20260409.csv").read_text(encoding="utf-8"),
        product="VIIRS_SNPP_SP", published_at="2026-04-09T05:00:00Z",
        data_nature="static", window={"start": "2026-04-09T04:00:00Z",
                                      "end": "2026-04-09T05:00:00Z"},
    )
    assert rows
    for record in rows:
        assert record.instrument == "VIIRS"
        assert record.platform == "Suomi-NPP"


def test_categorical_confidence_survives(fixtures_dir):
    """VIIRS SP confidence is 'n', 'l' or 'h'. A float column would destroy it."""
    rows = parse_firms_csv(
        (fixtures_dir / "firms_viirs_snpp_sp_20260409.csv").read_text(encoding="utf-8"),
        product="VIIRS_SNPP_SP", published_at="2026-04-09T05:00:00Z",
        data_nature="static", window={"start": "x", "end": "y"},
    )
    natives = {r.confidence_native for r in rows}
    assert natives <= {"n", "l", "h"}
    assert {r.confidence_scheme for r in rows} == {"viirs_categorical"}
    assert all(r.confidence is None for r in rows)


def test_modis_confidence_stays_numeric(fixtures_dir):
    """MODIS reports a percentage, so it keeps the legacy float too."""
    rows = parse_firms_csv(
        (fixtures_dir / "firms_modis_sp_20260409.csv").read_text(encoding="utf-8"),
        product="MODIS_SP", published_at="2026-04-09T05:00:00Z",
        data_nature="static", window={"start": "x", "end": "y"},
    )
    assert rows
    assert {r.confidence_scheme for r in rows} == {"modis_percent"}
    assert all(isinstance(r.confidence, float) for r in rows)


def test_fetch_restricts_records_to_the_scene_window(provider, monkeypatch):
    """The fixture holds a whole day; the scene is one hour."""
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    records = provider.fetch(SCENES["april-9-demo"])
    assert all(r.detected_at[11:13] == "04" for r in records)
    assert len(records) == 505


def test_the_scene_carries_both_expected_platforms(provider, monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    platforms = {r.platform for r in provider.fetch(SCENES["april-9-demo"])}
    assert platforms == {"Suomi-NPP", "NOAA-20"}


def test_raw_scan_geometry_is_retained_for_footprints(provider, monkeypatch):
    """Task 8 needs scan, track and daynight; losing them here would be silent."""
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    record = provider.fetch(SCENES["april-9-demo"])[0]
    geometry = provider.geometry_for(record.id)
    assert geometry["track"] > 0 and geometry["scan"] > 0
    assert geometry["daynight"] in {"D", "N"}
