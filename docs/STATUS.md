# Detection Explorer — status, 13 August 2026

Written for someone picking this up cold. The backend is complete and tested; the frontend has
not been started.

## Where it stands

| Stage | Tasks | State |
|---|---|---|
| 0. Prerequisites and spikes | 1–4 | **done** |
| 1. Backend | 5–13 | **done** |
| 2. Frontend | 14–18 | not started |
| 3. Delivery | 19–21 | not started |

**134 tests pass** under the research profile; 114 pass and 6 skip under the fixture profile.
Both were verified from a genuine clean clone.

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

## Next

Task 14 starts the frontend: Vite plus React plus MapLibre, no Mapbox token. Before writing
map code, confirm a keyless basemap style actually loads; the plan assumes one exists but does
not name a verified URL.

Three things remain outstanding and none of them block Task 14.

- The 26.7 s per frame figure should replace the plan's 15.5 s wherever the animation budget
  is discussed.
- `BRIGHT_PIPELINE_SHA` is unset, so cache keys record `unpinned`. Set it before any run whose
  output is meant to be reproducible.
- Decision records DEV-01 to DEV-05 are still to be written, and DEV-01 needs Karin's
  localhost approval quoted with its date.
