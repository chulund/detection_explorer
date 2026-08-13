# Detection Explorer — status, 13 August 2026

Written for someone picking this up cold. The backend is complete and tested; the frontend has
not been started.

## Where it stands

| Stage | Tasks | State |
|---|---|---|
| 0. Prerequisites and spikes | 1–4 | **done** |
| 1. Backend | 5–13 | **done** |
| 2. Frontend | 14–17 done, 18 skipped as low priority | **done** |
| 3. Delivery | 19–21 | **done except the video** |

**134 backend tests and 8 frontend tests pass.** The backend was verified from a genuine
clean clone under both profiles: 134 pass with the pipeline, 114 pass and 6 skip without it.

## The map: working, after five real bugs

**The map renders.** Verified visually against the production build: OpenStreetMap basemap,
DEA detections across New South Wales, scale bar, both provenance cards, and the full timeline
with six overpass markers and six frame buttons.

**A correction, because an earlier version of this document got it wrong.** It concluded the
blank canvas was environmental, on the strength of a test showing that a bare MapLibre map
with an empty style also failed. That test was run inside the same page that was serving
HMR-poisoned modules, so it proved nothing. The cause was in this project's code, twice over,
and the two defects below are the reason the map appeared blank.

The moral is worth keeping: a control experiment run inside the broken environment is not a
control. Testing against the production build, where HMR is out of the picture, settled in one
step what six rounds of instrumentation could not.

**The map never received its data.** The one that would have shipped an empty map. `ready` was
a ref, so flipping it did not re-run the effect that pushes GeoJSON into the map's sources, and
that effect had already bailed out before the layers existed. Meanwhile the layer-creation
callback had closed over the props as they were at mount, which was empty. React held 505 polar
footprints and 4000 points while the map's sources held none. `ready` now exists twice on
purpose: a ref for the map's own callbacks, which fire outside React's render cycle, and a
state mirror for the data effect to depend on, with a `latest` ref supplying current props.

**The dev server was serving HMR-poisoned modules.** Several confusing readings, including
`ReferenceError`s for identifiers that no longer existed, came from Vite caching broken
intermediate modules while edits were part-applied. Clearing `node_modules/.vite` and
restarting resolved it. When frontend behaviour stops matching the source, suspect this before
suspecting the library.

**The canvas never resized after the panels settled.** MapLibre sized itself at construction,
before the provenance strip rendered, and kept a stale canvas. A `ResizeObserver` now drives
`map.resize()`. The body region also gained a `min-height`, because a wrapped provenance strip
on a short window had squeezed the map to 209 px.

**Layers were gated on the `load` event.** `load` waits for every source to finish, including
the basemap's tiles. A slow or unreachable CDN therefore meant the detection layers were never
added at all, and the data this interface exists to show was hidden behind an unrelated third
party. They are now added on `styledata`.

**A timeout fallback made things worse.** An attempt to swap in an offline style after six
seconds called `setStyle` while the first style was still in flight, and MapLibre discarded
both: "Unable to perform style diff: Style is not done loading. Rebuilding the style from
scratch." Removed, and replaced by the inverted dependency described next.

**The basemap is now an enhancement rather than a foundation.** The map starts with a local
style that has no sources and therefore loads immediately, and the raster basemap is attached
afterwards as an ordinary source. If tiles never arrive, detections draw on a plain ground
instead of nothing drawing at all. Raster rather than vector, too: no sprite sheet, no glyph
server, no worker-side parsing, so there is far less that can stall. For a deliverable that
runs on localhost, possibly with no route out, that is the right way round.

`npm run preview` now proxies `/api` as well. `server.proxy` covers only `npm run dev`, and
serving the production build is the honest way to check behaviour without HMR involved.

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

**BRIGHT genuinely recomputes, through the full HTTP path.** A six-frame run completed in
**135 seconds and produced 342 detections** (71, 61, 54, 59, 59, 38). A repeat request returned
`delivery: "cached"` with the same `run_id`, and the SSE endpoint replayed the journal with
monotonic ids. Frame 04:20 returned 54, matching an earlier direct worker run exactly.

Note the timing: the plan assumed 15.5 s per frame from an old NRT log. The real figure is
about 27 s, so the animation is **two and a quarter minutes, not ninety seconds**.

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
