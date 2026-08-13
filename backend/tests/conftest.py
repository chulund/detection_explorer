"""Shared fixtures.

Declared in one place so no task invents a second name for the same thing. Everything here
works offline and without credentials: the provider tests read committed fixtures, so the
suite never depends on FIRMS, DEA or a MAP_KEY being reachable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.compat import LEGACY_STORE, LegacyDetection  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Detection  # noqa: E402


@pytest.fixture
def anyio_backend() -> str:
    """anyio's pytest plugin drives the async tests; pytest-asyncio is not installed."""
    return "asyncio"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def make_detection():
    """A v2 Detection with sensible defaults; override any field by keyword."""
    def _make(**overrides) -> Detection:
        base = dict(
            id="dea:1", source="dea", data_nature="static",
            detected_at="2026-04-09T04:20:00Z", published_at="2026-04-09T04:30:00Z",
            lat=-33.0, lon=150.0, frp_mw=12.0,
            confidence=None, confidence_native="n", confidence_scheme="viirs_categorical",
            satellite="NOAA 20", platform="NOAA-20", instrument="VIIRS",
            product="AFIMG", algorithm="AFIMG", algorithm_version="6",
            computation="retrieved",
            input_window={"start": "2026-04-09T04:00:00Z",
                          "end": "2026-04-09T05:00:00Z"},
        )
        base.update(overrides)
        return Detection.point(**base)
    return _make


@pytest.fixture
def seeded_legacy_store():
    """Put one D2-shaped record in the legacy store so the compat routes have output."""
    LEGACY_STORE.reset()
    LEGACY_STORE.upsert([
        LegacyDetection(
            id="dea_live:1", source="dea_live", data_nature="live",
            detected_at="2026-04-09T04:20:00Z", published_at="2026-04-09T04:30:00Z",
            lat=-33.0, lon=150.0, frp_mw=12.0, confidence=80.0,
            satellite="HIMAWARI-9", algorithm="BRIGHT AHI v1.86", replay_of=None,
        )
    ])
    LEGACY_STORE.log_tick("dea_live", "2026-04-09T04:30:00Z", True, 1)
    yield LEGACY_STORE
    LEGACY_STORE.reset()


@pytest.fixture
def fixtures_dir() -> Path:
    return BACKEND.parent / "fixtures"
