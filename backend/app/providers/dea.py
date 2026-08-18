"""Digital Earth Australia Hotspots, via the WFS.

Ported from the July feed's `dea_live.py`, with two changes. The window is a parameter
rather than a hard-coded 70 minutes, so the same code serves the current scene as `live` and
the April scene as `static`. And the hard-coded `process_algorithm = 'BRIGHT AHI'` filter is
gone, because the polar platforms are the point now.

No footprints, ever. The WFS schema carries `satellite`, `sensor`, `orbit`, `datetime`,
`power`, `confidence` and more, but neither `scan` nor `track`, so the ground geometry of a
DEA pixel is not recoverable from a DEA row. The record says so with an explicit null rather
than by staying silent.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from ..models import Detection
from ..scenes import Scene

WFS_URL = "https://hotspots.dea.ga.gov.au/geoserver/public/wfs"
WFS_NS = {
    "wfs": "http://www.opengis.net/wfs/2.0",
    "public": "http://sentinel.ga.gov.au/geoserver/public",
}
AUS_BBOX = (110.0, -45.0, 155.0, -10.0)
#: New South Wales and a margin. Fixed scenes are about one fire, and an
#: Australia-wide query returns thousands of unrelated points around it.
NSW_BBOX = (140.0, -38.0, 154.0, -28.0)
TIMEOUT_S = 180
MAX_FEATURES = 4000
SOURCE = "dea"

#: DEA writes platform names in its own casing. Normalise to the identifiers the rest of
#: the system uses, so that a platform can be matched across DEA, FIRMS and BRIGHT.
PLATFORMS = {
    "HIMAWARI-8": "Himawari-8",
    "HIMAWARI-9": "Himawari-9",
    "SUOMI NPP": "Suomi-NPP",
    "NOAA 20": "NOAA-20",
    "NOAA 21": "NOAA-21",
    "AQUA": "Aqua",
    "TERRA": "Terra",
    "SENTINEL-3A": "Sentinel-3A",
    "SENTINEL-3B": "Sentinel-3B",
}


def normalise_platform(raw: str) -> str:
    return PLATFORMS.get(raw.strip().upper(), raw.strip().title())


def build_wfs_body(start: datetime, end: datetime,
                   bbox: tuple[float, float, float, float] = AUS_BBOX,
                   count: int = 4000) -> str:
    minx, miny, maxx, maxy = bbox
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<wfs:GetFeature service="WFS" version="2.0.0" count="{count}"
 xmlns:wfs="http://www.opengis.net/wfs/2.0"
 xmlns:fes="http://www.opengis.net/fes/2.0"
 xmlns:gml="http://www.opengis.net/gml/3.2"
 xmlns:public="http://sentinel.ga.gov.au/geoserver/public">
  <wfs:Query typeNames="public:hotspots">
    <fes:Filter><fes:And>
      <fes:During>
        <fes:ValueReference>datetime</fes:ValueReference>
        <gml:TimePeriod gml:id="tp1">
          <gml:beginPosition>{start.strftime("%Y-%m-%dT%H:%M:%SZ")}</gml:beginPosition>
          <gml:endPosition>{end.strftime("%Y-%m-%dT%H:%M:%SZ")}</gml:endPosition>
        </gml:TimePeriod>
      </fes:During>
      <fes:BBOX>
        <fes:ValueReference>geometry</fes:ValueReference>
        <gml:Envelope srsName="EPSG:4326">
          <gml:lowerCorner>{minx} {miny}</gml:lowerCorner>
          <gml:upperCorner>{maxx} {maxy}</gml:upperCorner>
        </gml:Envelope>
      </fes:BBOX>
    </fes:And></fes:Filter>
  </wfs:Query>
</wfs:GetFeature>'''


def _num(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_wfs_xml(xml_bytes: bytes, published_at: str, data_nature: str,
                  window: dict[str, str] | None = None) -> list[Detection]:
    root = ET.fromstring(xml_bytes)
    window = window or {"start": published_at, "end": published_at}
    out: list[Detection] = []
    for member in root.findall("wfs:member", WFS_NS):
        feature = member.find("public:hotspots", WFS_NS)
        if feature is None:
            continue

        def text(field: str) -> str:
            return feature.findtext(f"public:{field}", default="", namespaces=WFS_NS)

        lat, lon = _num(text("latitude")), _num(text("longitude"))
        if lat is None or lon is None:
            continue

        raw_satellite = text("satellite")
        algorithm = text("process_algorithm")
        confidence = _num(text("confidence"))
        # The WFS gives a Kelvin value and never says which band produced it. Naming a
        # wavelength here would be a guess dressed as a measurement, so the channel says
        # what is actually known: where the number came from, and nothing more.
        brightness_k = _num(text("temp_kelvin"))
        brightness_channel = (
            "unspecified (DEA temp_kelvin)" if brightness_k is not None else None)
        out.append(Detection.point(
            id=f"{SOURCE}:{text('id')}",
            source=SOURCE,
            data_nature=data_nature,
            detected_at=text("datetime"),
            published_at=published_at,
            lat=lat,
            lon=lon,
            frp_mw=_num(text("power")),
            confidence=confidence,
            confidence_native=confidence,
            confidence_scheme="dea_percent",
            brightness_k=brightness_k,
            brightness_channel=brightness_channel,
            satellite=raw_satellite,
            platform=normalise_platform(raw_satellite),
            instrument=text("sensor").strip().upper() or "UNKNOWN",
            product=algorithm or "UNKNOWN",
            algorithm=algorithm or "UNKNOWN",
            algorithm_version=text("process_algorithm_version") or "unknown",
            computation="retrieved",
            input_window=window,
        ))
    return out


class DeaProvider:
    """Retrieval only. Serves either scene; the scene decides the label."""

    name = "dea"
    provides_footprints = False

    def __init__(self, fixture: Path | None = None) -> None:
        self._fixture = fixture
        #: Set when a response came back at exactly the feature cap, meaning the service
        #: returned as much as it was willing to and there is very likely more. Silent
        #: truncation would misrepresent the data, so callers are told.
        self.last_truncated: bool = False
        self.last_fallback_reason: str | None = None

    def available(self, scene: Scene) -> bool:
        # DEA is a live operational service with a usable archive, so it can honestly
        # serve both a rolling and a fixed scene.
        return True

    def nature_for(self, scene: Scene) -> str:
        return "live" if scene.admits("live") else "static"

    @staticmethod
    def products_for(scene: Scene) -> list[str]:
        """DEA has no product parameter: one query, whatever algorithms it holds.

        Reported as `*` rather than as a guessed list, because the set of algorithms in
        the response is a property of the service on the day, not of the request. The
        demo hour alone comes back carrying five.
        """
        return ["*"]

    @staticmethod
    def bbox_for(scene: Scene) -> tuple[float, float, float, float]:
        """Australia-wide for the rolling scene; NSW for a fixed one.

        A fixed scene is a single fire in New South Wales. Querying the whole continent
        for it returns thousands of unrelated detections, pushes the response into the
        service's feature cap, and buries the thing the scene is about.
        """
        return AUS_BBOX if scene.admits("live") else NSW_BBOX

    def fetch(self, scene: Scene, window: tuple[datetime, datetime] | None = None
              ) -> list[Detection]:
        start, end = window or scene.window()
        published_at = end.strftime("%Y-%m-%dT%H:%M:%SZ")
        window_dict = {"start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": published_at}

        self.last_truncated = False
        self.last_fallback_reason = None

        if self._fixture is not None:
            xml_bytes = self._fixture.read_bytes()
        else:
            body = build_wfs_body(start, end, self.bbox_for(scene),
                                  count=MAX_FEATURES).encode("utf-8")
            request = Request(WFS_URL, data=body, headers={"Content-Type": "text/xml"})
            with urlopen(request, timeout=TIMEOUT_S) as response:
                xml_bytes = response.read()

        records = parse_wfs_xml(xml_bytes, published_at=published_at,
                                data_nature=self.nature_for(scene), window=window_dict)

        if len(records) >= MAX_FEATURES:
            self.last_truncated = True
            self.last_fallback_reason = (
                f"the service returned its maximum of {MAX_FEATURES} features, so this "
                f"is a partial result"
            )
        return records
