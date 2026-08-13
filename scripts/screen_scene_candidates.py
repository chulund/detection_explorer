"""Rank candidate demonstration intervals against the gates that make a scene worth staging.

Staging one frame costs a 29-day Himawari backfill, so an interval has to earn its download.
Four gates decide it, and BRIGHT activity alone is not enough: an hour full of geostationary
detections with no polar overpass inside it cannot show the comparison this interface exists
to make.

    1. BRIGHT richness      - enough detections to animate.
    2. Polar co-occurrence  - at least one MODIS or VIIRS pass inside the interval.
    3. Spatial overlap      - the polar pass over the same fire, not a different one.
    4. AHI history          - 29 daily slots available at every frame time.

Gate 1 reads D2's precomputed frames. Those are screening data, not an oracle: they narrow
the search, they do not certify the result (spec section 13). Gate 2 and 3 query the DEA
Hotspots WFS, which carries the same polar platforms FIRMS does and so stands in as a free
proxy. The FIRMS availability check itself needs a MAP_KEY and is deferred to Task 4, before
any download happens.

Usage:
    python scripts/screen_scene_candidates.py
    python scripts/screen_scene_candidates.py --top 5
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

BRIGHT_REPO = Path(r"D:\Orang\Mark\20260224_BRIGHT_delivery")
REPLAY_DIR = (BRIGHT_REPO / "others" / "RMIT internal grant" / "RMIT_internal"
              / "deliverable_2_july" / "feed" / "replay_data")
PARQUET_ROOT = BRIGHT_REPO / "xprize_finals_nsw_bright" / "data" / "parquet" / "xymta"

WFS_URL = "https://hotspots.dea.ga.gov.au/geoserver/public/wfs"
WFS_NS = {
    "wfs": "http://www.opengis.net/wfs/2.0",
    "public": "http://sentinel.ga.gov.au/geoserver/public",
}
NSW_BBOX = (140.0, -38.0, 154.0, -28.0)
POLAR_INSTRUMENTS = {"VIIRS", "MODIS"}

FRAME_CADENCE_MINUTES = 10
FRAMES_PER_INTERVAL = 6
BACKFILL_DAYS = 28
OVERLAP_LIMIT_KM = 20.0


# --------------------------------------------------------------------------- gate 1

def bright_frames_by_hour() -> dict[str, list[tuple[str, int, list[tuple[float, float]]]]]:
    """Group D2's precomputed BRIGHT frames by UTC hour, keeping feature positions."""
    by_hour: dict[str, list] = collections.defaultdict(list)
    for path in sorted(REPLAY_DIR.glob("*_bright_mixed.geojson")):
        stamp = path.name[:14]
        features = json.loads(path.read_text(encoding="utf-8")).get("features", [])
        points = []
        for feature in features:
            geom = feature.get("geometry") or {}
            if geom.get("type") == "Point":
                lon, lat = geom["coordinates"][:2]
                points.append((float(lon), float(lat)))
        by_hour[stamp[:10]].append((stamp, len(features), points))
    return by_hour


# --------------------------------------------------------------------------- gate 2/3

def _wfs_body(start: datetime, end: datetime) -> str:
    minx, miny, maxx, maxy = NSW_BBOX
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<wfs:GetFeature service="WFS" version="2.0.0" count="4000"
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


def dea_records(start: datetime, end: datetime) -> list[dict]:
    body = _wfs_body(start, end).encode("utf-8")
    request = Request(WFS_URL, data=body, headers={"Content-Type": "text/xml"})
    with urlopen(request, timeout=120) as response:
        xml = response.read()
    root = ET.fromstring(xml)
    out = []
    for member in root.findall("wfs:member", WFS_NS):
        feature = member.find("public:hotspots", WFS_NS)
        if feature is None:
            continue

        def text(field: str) -> str:
            return feature.findtext(f"public:{field}", default="", namespaces=WFS_NS)

        try:
            out.append({
                "satellite": text("satellite"),
                "instrument": text("sensor"),
                "algorithm": text("process_algorithm"),
                "datetime": text("datetime"),
                "lat": float(text("latitude")),
                "lon": float(text("longitude")),
            })
        except ValueError:
            continue
    return out


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


# --------------------------------------------------------------------------- gate 4

def ahi_history_present(frame_stamps: list[str]) -> dict[str, tuple[int, int]]:
    """Daily slots present, out of 29, for each frame's statistical window."""
    coverage = {}
    for stamp in frame_stamps:
        target = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        present = 0
        for offset in range(BACKFILL_DAYS + 1):
            day = target - timedelta(days=BACKFILL_DAYS - offset)
            path = (PARQUET_ROOT / f"dt={day:%Y%m%d}" / f"hour={day:%H}"
                    / f"hhmm={day:%H%M}")
            if path.is_dir():
                present += 1
        coverage[stamp] = (present, BACKFILL_DAYS + 1)
    return coverage


# --------------------------------------------------------------------------- driver

def interval_frames(day: str, hour: str) -> list[str]:
    base = datetime.strptime(f"{day}{hour}0000", "%Y%m%d%H%M%S")
    return [(base + timedelta(minutes=FRAME_CADENCE_MINUTES * i)).strftime("%Y%m%d%H%M%S")
            for i in range(FRAMES_PER_INTERVAL)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=3, help="candidates to evaluate fully")
    args = parser.parse_args()

    by_hour = bright_frames_by_hour()
    ranked = sorted(
        ((key, sum(n for _, n, _ in frames), frames) for key, frames in by_hour.items()),
        key=lambda item: -item[1],
    )

    print("=" * 78)
    print("Gate 1: BRIGHT richness by UTC hour (D2 precomputed frames, screening only)")
    print("=" * 78)
    for key, total, frames in ranked[:8]:
        peak = max(n for _, n, _ in frames)
        print(f"  {key[:8]} {key[8:10]}:00Z   {total:5d} features across {len(frames):2d} "
              f"frames, peak {peak}")

    results = []
    for key, total, frames in ranked[: args.top]:
        day, hour = key[:8], key[8:10]
        print()
        print("=" * 78)
        print(f"Candidate {day} {hour}:00Z  ({total} BRIGHT features)")
        print("=" * 78)

        start = datetime.strptime(f"{day}{hour}0000", "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc)
        end = start + timedelta(hours=1)

        bright_points = [p for _, _, points in frames for p in points]

        try:
            records = dea_records(start, end)
        except Exception as exc:  # network is the only realistic failure here
            print(f"  gate 2: DEA query FAILED ({type(exc).__name__}: {exc})")
            results.append({"day": day, "hour": hour, "bright_features": total,
                            "polar": None, "error": str(exc)})
            continue

        polar = [r for r in records if r["instrument"].upper() in POLAR_INSTRUMENTS]
        tally = collections.Counter((r["satellite"], r["instrument"]) for r in polar)
        print(f"  gate 2: {len(records)} DEA records in NSW box, {len(polar)} polar")
        for (satellite, instrument), count in tally.most_common():
            times = sorted({r["datetime"][11:19] for r in polar
                            if r["satellite"] == satellite})
            print(f"          {count:5d}  {satellite:<12} {instrument:<6} at {', '.join(times[:4])}")

        if polar and bright_points:
            nearest = min(
                haversine_km((r["lon"], r["lat"]), p)
                for r in polar for p in bright_points
            )
            print(f"  gate 3: nearest polar detection to a BRIGHT detection: {nearest:.1f} km"
                  f"  ({'PASS' if nearest <= OVERLAP_LIMIT_KM else 'FAIL'}"
                  f", limit {OVERLAP_LIMIT_KM:.0f} km)")
        else:
            nearest = float("nan")
            print("  gate 3: no polar detections to compare")

        coverage = ahi_history_present(interval_frames(day, hour))
        complete = sum(1 for got, want in coverage.values() if got == want)
        print(f"  gate 4: AHI history, {complete}/{len(coverage)} frames fully staged")
        for stamp, (got, want) in coverage.items():
            print(f"          {stamp}  {got:2d}/{want} daily slots present")

        results.append({
            "day": day, "hour": hour, "bright_features": total,
            "polar_records": len(polar),
            "polar_platforms": {f"{s}/{i}": c for (s, i), c in tally.items()},
            "nearest_km": None if math.isnan(nearest) else round(nearest, 1),
            "ahi_frames_complete": complete,
            "ahi_frames_total": len(coverage),
        })

    print()
    print("=" * 78)
    print("Shortlist")
    print("=" * 78)
    for r in sorted(results, key=lambda r: -(r.get("polar_records") or 0)):
        verdict = "viable" if (r.get("polar_records") and r.get("nearest_km") is not None
                               and r["nearest_km"] <= OVERLAP_LIMIT_KM) else "rejected"
        print(f"  {r['day']} {r['hour']}:00Z  bright={r['bright_features']:4d}  "
              f"polar={r.get('polar_records')}  nearest={r.get('nearest_km')} km  -> {verdict}")
    print()
    print("  FIRMS availability gate is NOT checked here: it needs a MAP_KEY and is")
    print("  deferred to Task 4 Step 0, before any download.")

    out = Path(__file__).resolve().parents[1] / "docs" / "decisions" / "scene_screening.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n  wrote {out}")


if __name__ == "__main__":
    main()
