"""Stage the Himawari AHI inputs the demonstration scene needs, and record what was staged.

BRIGHT builds its statistical window from the same time-of-day slot on each of the previous
28 days, so every animation frame carries its own 29-day stack. Six frames is therefore about
147 day-slots once the existing 04:30 material is counted, roughly 880 MB.

The parquet itself stays out of git. What is tracked is the manifest this writes: a rolled-up
digest per day-slot directory, which is what `frame_key` hashes so that a configuration or
input change invalidates a cached detection frame. Hashing every one of the ~35,000 parquet
files individually would make the manifest unusable in review, so each day-slot directory
collapses to one digest over its sorted (name, size, content-hash) triples.

Usage:
    python scripts/stage_event.py --download      # fetch missing slots
    python scripts/stage_event.py                 # write the manifest from what is on disk
    python scripts/stage_event.py --verify        # re-hash and compare
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIGHT_REPO = Path(r"D:\Orang\Mark\20260224_BRIGHT_delivery\xprize_finals_nsw_bright")
PARQUET_ROOT = BRIGHT_REPO / "data" / "parquet" / "xymta"
PYTHON = Path(r"C:\Users\nurfa\.conda\envs\bright\python.exe")

SCENE_ID = "april-9-demo"
# [2026-04-09T04:00:00Z, 2026-04-09T05:00:00Z), ten-minute cadence, end exclusive.
FRAMES = [
    "20260409040000", "20260409041000", "20260409042000",
    "20260409043000", "20260409044000", "20260409045000",
]
BACKFILL_DAYS = 28
DETECTION_NWEEKS = 4
AHI_SOURCE = "arc"
MANIFEST = ROOT / "manifests" / f"{SCENE_ID}.json"


def window_days(frame: str) -> list[str]:
    """The 29 day-slots BRIGHT reads for one frame, oldest first."""
    target = datetime.strptime(frame, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    start = target - timedelta(days=BACKFILL_DAYS)
    return [(start + timedelta(days=i)).strftime("%Y%m%d%H%M%S")
            for i in range(BACKFILL_DAYS + 1)]


def slot_dir(stamp: str) -> Path:
    return (PARQUET_ROOT / f"dt={stamp[:8]}" / f"hour={stamp[8:10]}"
            / f"hhmm={stamp[8:12]}")


def digest_slot(path: Path) -> tuple[str, int, int] | None:
    """One digest over a day-slot directory: (sha256, file_count, total_bytes)."""
    if not path.is_dir():
        return None
    roll = hashlib.sha256()
    count = total = 0
    for file in sorted(path.rglob("*"), key=lambda p: str(p).lower()):
        if not file.is_file():
            continue
        body = hashlib.sha256(file.read_bytes()).hexdigest()
        roll.update(file.relative_to(path).as_posix().encode())
        roll.update(str(file.stat().st_size).encode())
        roll.update(body.encode())
        count += 1
        total += file.stat().st_size
    return (roll.hexdigest(), count, total) if count else None


def missing_slots() -> list[str]:
    needed: set[str] = set()
    for frame in FRAMES:
        needed.update(window_days(frame))
    return sorted(s for s in needed if not slot_dir(s).is_dir())


def download() -> None:
    before = missing_slots()
    print(f"{len(before)} day-slots missing across {len(FRAMES)} frames.")
    for index, frame in enumerate(FRAMES, start=1):
        gaps = [s for s in window_days(frame) if not slot_dir(s).is_dir()]
        if not gaps:
            print(f"  ({index}/{len(FRAMES)}) {frame}: complete already")
            continue
        print(f"  ({index}/{len(FRAMES)}) {frame}: {len(gaps)} day-slots to fetch")
        started = time.time()
        result = subprocess.run(
            [str(PYTHON), "-m", "src.download_module.orchestrate_downloads",
             "--dt", frame, "--ahi-source", AHI_SOURCE, "--workers", "1"],
            cwd=BRIGHT_REPO, capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(result.stdout[-2000:])
            print(result.stderr[-2000:])
            sys.exit(f"  download failed for {frame} (exit {result.returncode})")
        print(f"      done in {time.time() - started:.0f}s")


def build_manifest() -> dict:
    frames = []
    for frame in FRAMES:
        days = []
        for stamp in window_days(frame):
            entry = digest_slot(slot_dir(stamp))
            days.append({
                "slot": stamp,
                "present": entry is not None,
                "sha256": entry[0] if entry else None,
                "files": entry[1] if entry else 0,
                "bytes": entry[2] if entry else 0,
            })
        present = sum(1 for d in days if d["present"])
        frames.append({
            "frame": frame,
            "window_days_present": present,
            "window_days_required": len(days),
            "bytes": sum(d["bytes"] for d in days),
            "days": days,
        })
    return {
        "scene_id": SCENE_ID,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "detection_nweeks": DETECTION_NWEEKS,
        "backfill_days": BACKFILL_DAYS,
        "ahi_source": AHI_SOURCE,
        "parquet_root": str(PARQUET_ROOT),
        "frames": frames,
    }


def verify() -> int:
    if not MANIFEST.exists():
        sys.exit(f"no manifest at {MANIFEST}")
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    problems = 0
    for frame in recorded["frames"]:
        for day in frame["days"]:
            if not day["present"]:
                continue
            entry = digest_slot(slot_dir(day["slot"]))
            if entry is None:
                print(f"  MISSING  {frame['frame']} <- {day['slot']}")
                problems += 1
            elif entry[0] != day["sha256"]:
                print(f"  CHANGED  {frame['frame']} <- {day['slot']}")
                problems += 1
    print(f"verify: {problems} problem(s)")
    return 1 if problems else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true", help="fetch missing day-slots")
    parser.add_argument("--verify", action="store_true", help="re-hash against the manifest")
    args = parser.parse_args()

    if args.verify:
        sys.exit(verify())

    if args.download:
        download()

    manifest = build_manifest()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print()
    print(f"scene {manifest['scene_id']}")
    for frame in manifest["frames"]:
        print(f"  {frame['frame']}  {frame['window_days_present']:2d}/"
              f"{frame['window_days_required']} day-slots  "
              f"{frame['bytes'] / 1e6:7.1f} MB")
    total = sum(f["bytes"] for f in manifest["frames"])
    print(f"  total {total / 1e6:.0f} MB (day-slots shared between frames counted once each)")
    print(f"  wrote {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
