# Detection Explorer — status, 13 August 2026

Written for someone picking this up cold. The backend is complete and tested; the frontend has
not been started.

## Where it stands

| Stage | Tasks | State |
|---|---|---|
| 0. Prerequisites and spikes | 1–4 | **done** |
| 1. Backend | 5–13 | **done** |
| 2. Frontend | 14 done, 15–18 partial or not started | **map rendering unverified — see below** |
| 3. Delivery | 19–21 | not started |

**134 backend tests and 8 frontend tests pass.** The backend was verified from a genuine
clean clone under both profiles: 134 pass with the pipeline, 114 pass and 6 skip without it.

## The one thing that needs a human eye

**The map canvas did not paint during an automated browser session, and I could not
establish whether that is environmental or a real defect.** Everything around it verified
correctly, so the uncertainty is narrow but it is real.

What was confirmed working against live data: the API returned 4505 records, the provenance
strip showed DEA and FIRMS with correct natures and counts, the layer panel reported 505
polar footprints and 4000 points, and the slider showed per-platform overpass badges
("Suomi-NPP: 31 min ago", "NOAA-20: 11 min ago") with all six acquisition markers at 04:27,
04:28, 04:29, 04:47, 04:48 and 04:49. The overpass logic is visibly correct end to end.

What did not: MapLibre reported `isStyleLoaded() === false` indefinitely, with zero rendered
features. Our three layers were confirmed present in the style and their sources confirmed
populated, so the data reaches the map. The Carto style JSON, its TileJSON and its sprites
all returned 200; no vector tile request was observed, though MapLibre fetches those from Web
Workers where the tooling may not see them. WebGL is available and hardware-backed.

Three fixes came out of the investigation and are committed, all genuine improvements
regardless of the cause. Two of them were real bugs that would have bitten a user: the canvas
never resized after the panels settled, and layers were gated on a `load` event that a slow
basemap prevents from ever firing.

**Next step: open `http://localhost:5173` in an ordinary browser window and look.** If the
map draws, the blank canvas was an artifact of the automation environment and Task 15 can
proceed. If it does not, the offline-style fallback at `MapView.jsx` is the place to start,
and the question is why `styledata` fires but the style never completes.

Plan: `C:\Users\nurfa\.claude\plans\sleepy-squishing-dawn.md`.
Spec: `RMIT_internal/docs/superpowers/specs/2026-08-13-detection-explorer-design.md`.

## Run it

```powershell
cd backend
& "C:\Users\nurfa\.conda\envs\bright\python.exe" -m uvicorn app.main:app --reload --port 8000
# Swagger at http://localhost:8000/api/docs
```

Two profiles, both supported and both tested.

**Fixture profile** is a clean clone with no `.env`, no pipeline and no staged data. Both
scenes serve from committed fixtures; `/api/v2/status` reports `bright` unavailable. This is
what proves the repository is publishable.

**Research profile** adds `.env` with `FIRMS_MAP_KEY` and `BRIGHT_PIPELINE_PATH`, plus the
staged parquet. This is what proves the computation genuinely runs.

## What was proven, with numbers

**BRIGHT genuinely recomputes.** Frame `20260409042000` ran through the worker end to end —
staged parquet, subprocess, CLI, parsed output, cached, events emitted — producing **54
detections in 26.7 s**. Note that figure: the plan assumed 15.5 s from an old NRT log, so a
six-frame animation is nearer **2.5 minutes than 90 seconds**.

**Staging is complete and verified.** 174 of 174 day-slots across all six frames, 593 MB,
manifest verified clean. Downloads ran at 7.5 s per day-slot, so the whole thing took about 18
minutes rather than the hours the plan allowed.

**The scene had to be corrected.** The spec named 04:00–05:00Z on the strength of BRIGHT
richness. Screening found that hour has **no polar overpass at all**, as do three others; five
of eight hours screened have zero polar coverage over NSW. 04:00Z carries 1618 polar records
from two platforms on two passes, 0.1 km from the BRIGHT detections. See
`decisions/scene-selection.md`.

**The side-of-track ambiguity is real and material.** Measured IoU 0.7802 with corners up to
476 m apart at NSW latitudes, against 0.9956 uncorrected. 503 of the 505 detections in the
scene fall below the 0.95 threshold, so two-candidate footprints are the normal case here, not
an exception. See `polar_footprint/report/20260813_side_divergence.md`.

**The D2 frames are not an oracle.** The recomputation finds the same fires — median 1.1 km
against a 2 km pixel — but differs in spatial extent, carries a systematic sub-pixel offset
probably from JAXA-versus-NCI catalogues, and has no recorded provenance. Not promoted. See
`decisions/reference-baseline.md`.

## Decisions a reader might otherwise question

**Polar footprints are two overlapping polygons.** A FIRMS row cannot say which side of the
ground track the pixel lay on. The MultiPolygon is valid under RFC 7946, which is what this
API emits, but not under OGC Simple Features, which expects disjoint interiors, so strict GIS
tooling may flag it. Exporting the union instead would be OGC-valid and would overstate pixel
area by 5 to 12 per cent, corrupting the size comparison the interface exists for.

**Confidence is stored twice.** VIIRS Standard Processing reports `n`, `l` or `h`; MODIS
reports a percentage. `confidence` keeps D2's float, `confidence_native` and
`confidence_scheme` carry the real meaning. Coercing `n` to a number would invent information.

**Fixtures never serve the `current` scene.** Absent means absent. A cached April response
labelled `live` would be a lie, and there is a test for it.

**D2's routes are frozen.** `/api/status`, `/api/detections/latest` and
`/api/detections/history` stay unversioned exactly where July left them, with `/api/v1`
mirroring them from the same handler objects so they cannot drift. `/api/v2` carries schema
2.0. Provider availability is on `/api/v2/status`, never the D2 route.

## Two bugs found and fixed along the way

**`.gitignore` swallowed the run package.** A bare `runs/` matches at any depth, so
`backend/app/runs/` — keys, store, worker, journal, API — was never committed despite three
commits claiming to add it. The working tree and tests were fine; a clean clone would have had
no run lifecycle at all. Found by noticing a staged file list was shorter than the change
warranted. Fixed by anchoring the pattern.

**The AHI grid raised instead of degrading.** The clean-clone check passed only because this
machine happens to hold the BRIGHT pipeline at the default path — precisely the false positive
a clean-clone check should catch. `ahi.py` now reports availability and returns an empty
lookup, and the AHI tests skip rather than fail when the pipeline is absent.

## A known data defect, not yet fixed

**DEA is being silently truncated.** A live call for the demo scene returned exactly 4000
records, which is the WFS `count` cap in `providers/dea.py`. Silent truncation is precisely
the kind of quiet dishonesty this project guards against everywhere else, so it should not
ship as it stands.

Two things to decide. The provider should detect `len(records) == count` and report
`truncated: true` in the source notes, so the interface can say so. And the demo scene
probably wants a New South Wales bounding box rather than the Australia-wide `AUS_BBOX`,
which is what pushes the count over the cap in the first place; the scene is about one fire
in NSW, and 4000 Australia-wide points are noise around it.

## Next

Task 15 continues the frontend, once the map question above is settled.

Four things remain outstanding.

- The 26.7 s per frame figure should replace the plan's 15.5 s wherever the animation budget
  is discussed.
- `BRIGHT_PIPELINE_SHA` is unset, so cache keys record `unpinned`. Set it before any run whose
  output is meant to be reproducible.
- Decision records DEV-01 to DEV-05 are still to be written, and DEV-01 needs Karin's
  localhost approval quoted with its date.
