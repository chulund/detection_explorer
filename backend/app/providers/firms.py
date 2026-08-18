"""NASA FIRMS Area API: MODIS and VIIRS detections, with the geometry footprints need.

Unlike DEA, a FIRMS row carries `scan` and `track`, which is what makes pixel footprint
reconstruction possible at all. Those two columns are retained alongside the `Detection` and
handed to `app.footprints.polar` in Task 8.

Two rules shape this provider.

Historical scenes use **Standard Processing** products, because they are reproducible.
NOAA-21 is therefore excluded from history: FIRMS publishes no `VIIRS_NOAA21_SP`, only NRT.
That single fact is what disqualified the nominally richer 03:00Z candidate during scene
selection.

Fixtures serve historical scenes and never the current one. A cached April response is still
a set of April observations, so labelling it `static` stays true; dropping those same records
into a feed labelled `live` would not. When the current scene cannot be served, the provider
reports itself unavailable and returns nothing.

Verified API limits: MAP_KEY required, 1 to 5 days per request, 5000 transactions per
10-minute interval.
"""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

from ..models import Detection
from ..scenes import Scene

BASE = "https://firms.modaps.eosdis.nasa.gov/api"
NSW_AREA = "140,-38,154,-28"
TIMEOUT_S = 180
SOURCE = "firms"
MAX_DAY_RANGE = 5

#: Reproducible products, for any scene fixed in the past.
STANDARD_PRODUCTS = ("MODIS_SP", "VIIRS_SNPP_SP", "VIIRS_NOAA20_SP")
#: Near-real-time products, for the rolling scene. NOAA-21 exists only here.
NRT_PRODUCTS = ("MODIS_NRT", "VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")

#: FIRMS `satellite` codes to the platform identifiers used across the system.
PLATFORMS = {"N": "Suomi-NPP", "1": "Terra", "Terra": "Terra", "Aqua": "Aqua",
             "N20": "NOAA-20", "N21": "NOAA-21"}

INSTRUMENTS = {"MODIS": "MODIS", "VIIRS": "VIIRS"}


def _instrument_for(product: str) -> str:
    return "MODIS" if product.startswith("MODIS") else "VIIRS"


def _confidence(raw: str, instrument: str) -> tuple[float | None, str | float, str]:
    """MODIS reports a percentage; VIIRS reports a category. Keep both truthfully.

    Coercing 'n' to a number would invent information, so the legacy float stays None
    for VIIRS and the native value carries the meaning.
    """
    raw = (raw or "").strip()
    if instrument == "MODIS":
        try:
            value = float(raw)
        except ValueError:
            return None, raw, "modis_percent"
        return value, value, "modis_percent"
    return None, raw, "viirs_categorical"


#: The fire channel each instrument reports, and what to call it.
#:
#: Both instruments also carry a longwave window band (`bright_ti5`, `bright_t31`) used for
#: cloud and background screening rather than for the fire itself. The fire channel is the
#: one worth surfacing, and it is named so that nobody compares 3.74 um against 4 um as
#: though they were the same measurement.
BRIGHTNESS_CHANNELS = {
    "VIIRS": ("bright_ti4", "VIIRS I4 3.74 um"),
    "MODIS": ("brightness", "MODIS T21 4 um"),
}


def _brightness(row: dict, instrument: str) -> tuple[float | None, str | None]:
    """Kelvin and its band, or nothing at all. An absent reading is not a zero."""
    column, label = BRIGHTNESS_CHANNELS.get(instrument, (None, None))
    if column is None:
        return None, None
    try:
        return float(row.get(column) or ""), label
    except (TypeError, ValueError):
        return None, None


def parse_firms_csv(text: str, product: str, published_at: str, data_nature: str,
                    window: dict[str, str]) -> list[Detection]:
    instrument = _instrument_for(product)
    out: list[Detection] = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (KeyError, ValueError):
            continue
        acq_time = (row.get("acq_time") or "").zfill(4)
        detected_at = f"{row.get('acq_date', '')}T{acq_time[:2]}:{acq_time[2:]}:00Z"
        satellite = (row.get("satellite") or "").strip()
        confidence, native, scheme = _confidence(row.get("confidence", ""), instrument)
        brightness_k, brightness_channel = _brightness(row, instrument)
        try:
            frp = float(row.get("frp") or "nan")
        except ValueError:
            frp = None

        out.append(Detection.point(
            id=f"{SOURCE}:{product}:{row.get('acq_date')}:{acq_time}:{lat:.5f}:{lon:.5f}",
            source=SOURCE,
            data_nature=data_nature,
            detected_at=detected_at,
            published_at=published_at,
            lat=lat,
            lon=lon,
            frp_mw=None if frp != frp else frp,   # NaN check
            confidence=confidence,
            confidence_native=native,
            confidence_scheme=scheme,
            brightness_k=brightness_k,
            brightness_channel=brightness_channel,
            satellite=satellite,
            platform=PLATFORMS.get(satellite, satellite or "unknown"),
            instrument=INSTRUMENTS.get(instrument, instrument),
            product=product,
            algorithm=product,
            algorithm_version=(row.get("version") or "unknown").strip(),
            computation="retrieved",
            input_window=window,
        ))
    return out


def _raw_geometry(text: str, product: str) -> dict[str, dict]:
    """scan/track/daynight per record id, kept for footprint reconstruction."""
    instrument = _instrument_for(product)
    geometry: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            scan, track = float(row["scan"]), float(row["track"])
        except (KeyError, ValueError):
            continue
        acq_time = (row.get("acq_time") or "").zfill(4)
        key = f"{SOURCE}:{product}:{row.get('acq_date')}:{acq_time}:{lat:.5f}:{lon:.5f}"
        geometry[key] = {
            "lat": lat, "lon": lon, "scan": scan, "track": track,
            "satellite": (row.get("satellite") or "").strip(),
            "daynight": (row.get("daynight") or "D").strip().upper()[:1],
            "instrument": instrument,
        }
    return geometry


class FirmsProvider:
    name = "firms"
    provides_footprints = True

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures = fixtures_dir
        self.last_fallback_reason: str | None = None
        self.last_used_fixture: bool = False
        self._geometry: dict[str, dict] = {}

    # ------------------------------------------------------------------ policy

    @staticmethod
    def sources_for(scene: Scene) -> tuple[str, ...]:
        return NRT_PRODUCTS if scene.admits("live") else STANDARD_PRODUCTS

    @classmethod
    def products_for(cls, scene: Scene) -> list[str]:
        """What was asked for, which is not the same as what came back.

        A product can be queried and return nothing for the window, as MODIS does in the
        demo hour. Reporting the query lets the interface say "no MODIS detections"
        rather than leaving a reader to conclude MODIS was never consulted.
        """
        return list(cls.sources_for(scene))

    @staticmethod
    def map_key() -> str | None:
        return os.environ.get("FIRMS_MAP_KEY") or None

    @staticmethod
    def build_url(key: str, product: str, area: str, day_range: int, day: str) -> str:
        if not 1 <= day_range <= MAX_DAY_RANGE:
            raise ValueError(f"day_range must be 1 to {MAX_DAY_RANGE}, got {day_range}")
        return f"{BASE}/area/csv/{key}/{product}/{area}/{day_range}/{day}"

    def available(self, scene: Scene) -> bool:
        if scene.admits("live"):
            # No key means no live data. A fixture would be historical, so it cannot
            # stand in here.
            return self.map_key() is not None
        return self.map_key() is not None or self._fixtures is not None

    def nature_for(self, scene: Scene) -> str:
        return "live" if scene.admits("live") else "static"

    # ------------------------------------------------------------------ fetch

    def _fixture_text(self, product: str, day: str) -> str | None:
        if self._fixtures is None:
            return None
        path = self._fixtures / f"firms_{product.lower()}_{day.replace('-', '')}.csv"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def fetch(self, scene: Scene, window: tuple[datetime, datetime] | None = None
              ) -> list[Detection]:
        self.last_fallback_reason = None
        self.last_used_fixture = False
        self._geometry = {}

        start, end = window or scene.window()
        published_at = end.strftime("%Y-%m-%dT%H:%M:%SZ")
        window_dict = {"start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": published_at}
        day = start.strftime("%Y-%m-%d")
        key = self.map_key()
        nature = self.nature_for(scene)

        if key is None and scene.admits("live"):
            self.last_fallback_reason = "no_map_key"
            return []

        records: list[Detection] = []
        for product in self.sources_for(scene):
            text: str | None = None
            if key is not None:
                try:
                    with urlopen(self.build_url(key, product, NSW_AREA, 1, day),
                                 timeout=TIMEOUT_S) as response:
                        text = response.read().decode("utf-8", "replace")
                except Exception as exc:                      # noqa: BLE001
                    self.last_fallback_reason = f"{type(exc).__name__}: {exc}"
            if text is None:
                if scene.admits("live"):
                    # Never substitute a historical fixture into a live scene.
                    continue
                text = self._fixture_text(product, day)
                if text is None:
                    continue
                self.last_used_fixture = True
                self.last_fallback_reason = self.last_fallback_reason or "no_map_key"

            records += parse_firms_csv(text, product, published_at, nature, window_dict)
            self._geometry.update(_raw_geometry(text, product))

        keep = [r for r in records if window_dict["start"] <= r.detected_at < window_dict["end"]]
        self._geometry = {k: v for k, v in self._geometry.items()
                          if k in {r.id for r in keep}}
        return keep

    def geometry_for(self, record_id: str) -> dict | None:
        """scan/track/daynight for a record from the last fetch, or None."""
        return self._geometry.get(record_id)
