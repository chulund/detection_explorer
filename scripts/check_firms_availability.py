"""Close the FIRMS availability gate before any Himawari staging happens.

The demonstration scene is worth staging only if FIRMS can actually serve its polar half.
Staging costs roughly 149 daily Himawari slots, so this check runs first: an interval whose
polar data cannot be retrieved reproducibly is not worth the download.

Two questions, in order:

    1. Does FIRMS hold April 2026 at all, for the Standard Processing products the scene
       needs? Answered by /api/data_availability/.
    2. Does an actual Area API query for the scene date return records over New South Wales?
       That is the definitive answer, and its response doubles as the Task 7 fixture.

Standard Processing is required for historical scenes because it is reproducible. NOAA-21
publishes no SP product and is therefore excluded here; it remains available to the `current`
scene through VIIRS_NOAA21_NRT.

Usage:
    python scripts/check_firms_availability.py
    python scripts/check_firms_availability.py --save-fixtures
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://firms.modaps.eosdis.nasa.gov/api"

SCENE_DATE = date(2026, 4, 9)
SCENE_HOUR_UTC = 4
NSW_AREA = "140,-38,154,-28"          # west,south,east,north
SP_PRODUCTS = ("MODIS_SP", "VIIRS_SNPP_SP", "VIIRS_NOAA20_SP")
DAY_RANGE = 1                          # API accepts 1..5


def _map_key() -> str:
    key = os.environ.get("FIRMS_MAP_KEY")
    if not key:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("FIRMS_MAP_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        sys.exit("FIRMS_MAP_KEY not set. Copy .env.example to .env and fill it in.")
    return key


def _get(url: str) -> str:
    with urlopen(url, timeout=120) as response:
        return response.read().decode("utf-8", "replace")


def check_availability(key: str) -> dict[str, tuple[str, str]]:
    """Date span FIRMS holds per product, from the availability endpoint."""
    text = _get(f"{BASE}/data_availability/csv/{key}/ALL")
    spans: dict[str, tuple[str, str]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        data_id = (row.get("data_id") or "").strip()
        if data_id:
            spans[data_id] = ((row.get("min_date") or "").strip(),
                              (row.get("max_date") or "").strip())
    return spans


def area_url(key: str, product: str, area: str, day_range: int, day: date) -> str:
    if not 1 <= day_range <= 5:
        raise ValueError(f"day_range must be 1 to 5, got {day_range}")
    return f"{BASE}/area/csv/{key}/{product}/{area}/{day_range}/{day:%Y-%m-%d}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save-fixtures", action="store_true",
                        help="write responses to fixtures/ for offline tests")
    args = parser.parse_args()
    key = _map_key()

    print("=" * 78)
    print("1. Product availability (does FIRMS hold April 2026 at all?)")
    print("=" * 78)
    try:
        spans = check_availability(key)
    except HTTPError as exc:
        sys.exit(f"  availability endpoint failed: HTTP {exc.code} {exc.reason}")

    scene_iso = SCENE_DATE.isoformat()
    all_ok = True
    for product in SP_PRODUCTS:
        span = spans.get(product)
        if not span:
            print(f"  {product:<18} NOT LISTED")
            all_ok = False
            continue
        lo, hi = span
        covered = bool(lo) and bool(hi) and lo <= scene_iso <= hi
        all_ok &= covered
        print(f"  {product:<18} {lo} .. {hi}   {'covers' if covered else 'DOES NOT COVER'}"
              f" {scene_iso}")

    if "VIIRS_NOAA21_SP" in spans:
        print("  note: VIIRS_NOAA21_SP now exists; the scene could be widened.")
    else:
        print("  VIIRS_NOAA21_SP    absent, as expected; NOAA-21 stays out of historical scenes.")

    print()
    print("=" * 78)
    print(f"2. Actual records over NSW for {scene_iso} (the definitive check)")
    print("=" * 78)
    fixtures = ROOT / "fixtures"
    if args.save_fixtures:
        fixtures.mkdir(exist_ok=True)

    total_in_hour = 0
    for product in SP_PRODUCTS:
        url = area_url(key, product, NSW_AREA, DAY_RANGE, SCENE_DATE)
        try:
            text = _get(url)
        except HTTPError as exc:
            print(f"  {product:<18} HTTP {exc.code} {exc.reason}")
            all_ok = False
            continue

        rows = list(csv.DictReader(io.StringIO(text)))
        in_hour = [r for r in rows
                   if (r.get("acq_time") or "").zfill(4)[:2] == f"{SCENE_HOUR_UTC:02d}"]
        total_in_hour += len(in_hour)
        sats = sorted({r.get("satellite", "?") for r in in_hour})
        has_geometry = all(k in (rows[0] if rows else {}) for k in ("scan", "track", "daynight"))
        print(f"  {product:<18} {len(rows):5d} records that day, {len(in_hour):4d} in "
              f"{SCENE_HOUR_UTC:02d}:00Z hour  satellites={sats or '-'}")
        if rows and not has_geometry:
            print(f"    WARNING: response lacks scan/track/daynight; footprints impossible")
            all_ok = False

        if args.save_fixtures and rows:
            out = fixtures / f"firms_{product.lower()}_{SCENE_DATE:%Y%m%d}.csv"
            out.write_text(text, encoding="utf-8")
            print(f"    saved {out.relative_to(ROOT)}")

    print()
    print("=" * 78)
    print("Gate verdict")
    print("=" * 78)
    if all_ok and total_in_hour > 0:
        print(f"  PASS. {total_in_hour} SP records inside the {SCENE_HOUR_UTC:02d}:00Z hour.")
        print("  Staging may proceed.")
    else:
        print("  FAIL. Do not stage; revisit scene selection.")
        sys.exit(1)


if __name__ == "__main__":
    main()
