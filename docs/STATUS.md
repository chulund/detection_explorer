# Detection Explorer — status, 18 August 2026

Written for someone picking this up cold. Backend and frontend are built, tested, and have
passed a pinned cold-run acceptance check through the production HTTP path. Three items still
need a person: the walkthrough video, Karin's localhost approval quoted in
`decisions/DEV-01-localhost.md`, and **a foreground look at this final build**. The in-app
Browser connection was unavailable during the 18 August pass, so the new AHI/timeline/layer
behaviour has not been signed off by eye. It is covered by style validation, DOM integration
tests, a production build, and live API acceptance; that is strong evidence, but it is not a
substitute for looking at the rendered map.

An earlier version of this document said the AHI footprint layer was done. It was not: the
join existed and nothing called it, so the layer had a feature count of zero. That is
recorded in full below rather than quietly corrected, because a status document that
overstates completion is the failure mode this project is meant to avoid.

## Where it stands

| Stage | Tasks | State |
|---|---|---|
| 0. Prerequisites and spikes | 1–4 | **done** |
| 1. Backend | 5–13 | **done** |
| 2. Frontend | 14–18 | **done** |
| 3. Delivery | 19–21 | **done except foreground visual acceptance and video** |

**186 backend tests and 169 frontend tests pass**, and the production frontend build succeeds.
The backend was additionally verified from a genuine clean clone under both run profiles.

## The dashboard revamp, 17 August

The interface is now a dark telemetry dashboard. The functional patterns come from the
XPRIZE finals frontend at `20260224_BRIGHT_delivery/web/frontend`; two of them could not be
copied, because that codebase is Mapbox-with-a-token and Himawari-only, with no polar
sensors and therefore no geostationary-versus-polar distinction anywhere in it.

**Layers are named by what produced them.** Three toggles named after data sources became
one row per algorithm, version, sensor and platform, derived from the records rather than
declared. That was not cosmetic: the demo hour carries **ten pairings with records**, plus one
queried product that returned none, and the old panel left 1660 of the 1785 DEA records
with no label at all. DEA alone serves AFIMG 6, AFMOD 6, Landgate Daytime VIIRS 6,
Landgate AHI 1.0.0 and BRIGHT AHI 1.86, across Suomi-NPP, NOAA-20 and Himawari-9.

A product that was queried and returned nothing keeps its row, greyed and reading zero.
`MODIS_SP` is queried for this scene and has no records in the hour, and omitting it would
let a reader conclude MODIS was never consulted. Providers now report `products_queried`
alongside their count for exactly this.

**Colour is spread across a hue band, not drawn from a list.** Warm hues are geostationary,
cool are polar. The first attempt used a fixed eight-entry cool ramp against nine polar
layers, so the ninth wrapped onto the first and AFIMG on NOAA-20 was painted identically to
VIIRS_SNPP_SP on Suomi-NPP. Found by running the live payload through the real pipeline
rather than by a test — the unit test only had three keys. There is now a test with more
layers than any ramp would hold.

**Rendering is Auto, Footprints or Points.** Auto keeps the marker until the polygon is
legible. Footprints forces true scale everywhere, and deliberately keeps markers for
records that carry no geometry at all, or the 1785 DEA hotspots would vanish from the mode
that claims to show everything. Auto now makes the same distinction: a point-only record
never fades merely because the map crossed a footprint zoom threshold. Points drops the
polygons entirely.

Every detection now shares one source, with colour and sensor class travelling on the
feature, so eleven pairings cost six layers rather than thirty-three and toggling one is a
filter update. The marker fade still needs three layers, because a zoom expression is only
legal as the outermost expression of a property and the fade differs per pixel size.

**Legends appear only for active layers**, in a collapsible dock bottom-left. The ramps come
from the reference's rendered variants: it carries two versions of several scales and they
disagree, so the three-class fractional cover array it declares was ignored in favour of
the nine-class one it draws. The DEA layers are now requested with a named style rather
than the service default, because a legend describes one specific rendering; checked over a
populated extent, the named style and the default return byte-identical tiles today.
The scale control is bottom-right, so it cannot occupy the same corner as the legend.

**The timeline selects one geostationary frame.** The active frame is the latest declared
scene frame at or before the cursor, and AHI records are restricted to its ten-minute
half-open interval. Polar observations retain the complete latest pass per platform and
product, including point-only DEA records; adjacent scan-line timestamps stay together
instead of all but the last minute disappearing. A selection is cleared when its frame or
layer is no longer visible.

**Brightness temperature reaches the interface.** It was in every source and in none of the
responses: DEA sends `temp_kelvin`, FIRMS sends `bright_ti4`/`bright_ti5`, and the pipeline
emits `mir`, `tir` and `back_bt`, which a nine-column filter in the worker was discarding.
It travels with `brightness_channel`, because VIIRS I4 at 3.74 µm, MODIS T21 at 4 µm and
AHI B07 at 3.9 µm are not one quantity. DEA names no band, so its channel says so.

**Prose became chips.** The scene banner, both footprint caveats and the layer footnotes
moved into an About sheet and hover tooltips. The caveats still read their field rather
than being hardcoded, and still quote the measured figures.

Four keyless basemaps, a click popup with a selection halo, and zoom-to-extent,
reset-north, scale and fullscreen controls. See `decisions/DEV-06-keyless-basemaps.md`.

## The footprint layers were invisible, and the reasons were unrelated

Reported on 17 August: neither the BRIGHT / AHI footprints nor the VIIRS / MODIS
footprints could be seen. Two separate causes, one per layer, plus a third that had been
hiding both.

**Nothing ever attached an AHI footprint.** `footprints/ahi.py` had `attach_ahi_footprint`,
`test_footprints.py` exercised it, and `registry.py` imported the module and re-exported
it — and no application code called it. Only the polar attachment was wired in. The layer
was not failing to draw; it had a feature count of zero, and the layer panel said so.

The retrieval path could not have used it anyway. DEA is the only AHI-class source there
and its WFS carries no `x`,`y` pixel index to join the grid on, which is why
`provides_footprints` is False. AHI footprints can only come from a BRIGHT run, and that
path was broken twice over: the run emitted `region,x,y,lon,lat,frp,...` with no polygon,
and the frontend turned each row into a **Point** and handed it to a fill layer, which
cannot draw a point. So even a successful run would have rendered nothing.

The join now happens in `_frames_payload`, at read-out rather than at compute time, so
runs cached before the join existed gain their polygons too. Verified against the six
frames of real output still on disk from the August run: **342 of 342 detections join to
the sensor grid**, and every polygon contains its own row's reported position.

**Polar footprints were drawn correctly and could not be seen.** At the opening view the
ground resolution is about 3.4 km per screen pixel, so a measured 478 m footprint spans
**0.14 of a screen pixel**. At the default cursor both passes are past the 300 s tolerance,
so they draw dimmed. MapLibre's own tiler keeps every footprint at every zoom from 5 to 14,
checked offline against `@maplibre/geojson-vt`, so this was never a data or tiling problem.
It was arithmetic. A separate timeline bug retained only the final timestamp of a multi-minute
pass; the pass clustering described above now keeps all 505 FIRMS footprints.

Two changes. The map now opens on the detections rather than on a fixed state-wide
rectangle, which lands at about zoom 7. And each footprint layer gained a marker that
carries it until the polygon is legible and then fades out: zoom 8 to 9.5 for a 2 km AHI
pixel, 10.5 to 12 for a 375 m polar pixel, being roughly where each reaches four screen
pixels. The marker and the readable polygon are never on screen together, so true scale
still means what it says, and the layer panel says the same thing in words.

**`.env` was never read.** No `load_dotenv`, no `python-dotenv` dependency, nothing. So
the research profile did not exist: FIRMS served fixtures with a valid key sitting in
`.env`, and BRIGHT reported `BRIGHT_PIPELINE_PATH unset` on a machine holding the
pipeline. `app/__init__.py` now reads it, in the package initialiser because provider
availability is decided at import time. The shell wins over the file, and an absent file
is not an error.

The test suite opts out through `DETECTION_EXPLORER_SKIP_ENV`, and that is not tidiness:
a developer's real FIRMS key sends the provider to the network instead of to the committed
fixtures, so loading `.env` would have quietly put an offline suite on the internet.

**A layer went missing while fixing this, which is worth recording.** The polar marker's
opacity multiplied a zoom interpolation by a data expression, and MapLibre rejects a zoom
expression anywhere but the outermost position. `addLayer` threw, which abandoned the rest
of the setup, and the result looked like an empty map rather than an error — the same
failure shape as the bugs below. The layer definitions now live in `map/layers.js` and are
validated against the MapLibre style specification in `map/layers.test.js`, with the
rejected expression kept as a live example.

## The map: working, after five real bugs

**The map baseline rendered on 17 August.** That earlier production-build check showed the
OpenStreetMap basemap, DEA detections across New South Wales, scale bar, both provenance cards,
and the full timeline. It predates the final AHI, pass-clustering and layer-state changes, which
is why the foreground pass in **Next** still matters.

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
C:\Users\nurfa\.conda\envs\bright\python.exe -m uvicorn app.main:app --reload --port 8000
# Swagger at http://localhost:8000/api/docs
```

Two profiles, both supported and both tested.

**Fixture profile** is a clean clone with no `.env`, no pipeline and no staged data. Both
scenes serve from committed fixtures; `/api/v2/status` reports `bright` unavailable. This is
what proves the repository is publishable.

**Research profile** adds `.env` with `FIRMS_MAP_KEY`, `BRIGHT_PIPELINE_PATH` and the matching
`BRIGHT_PIPELINE_SHA`, plus the staged parquet. This is what proves the computation genuinely
runs reproducibly.

## What was proven, with numbers

**BRIGHT genuinely recomputes, through the full HTTP path.** The retained pipeline checkout
is clean and pinned at `245517f8fb409b53783be9ac8388c702ca26a09c`. The worker now gives
each attempt its own `runs/pipeline-output/<run_id>` root, sets that as `SDIR`, passes
`--force`, and accepts output only from that directory. This matters because the earlier
135-second claim was not a valid cold-run proof: an Explorer cache miss could still let the
pipeline reuse files already present under its canonical `data/streamed/` tree.

The corrected cold run (`7d980edc68fa42438e1d50b1af8b985d`) completed all six uncached
frames in **76.58–77.95 seconds per frame** and produced **342 detections**
(71, 61, 54, 59, 59, 38). All 342 gained validated AHI polygons. The run response records the
configured and actual pipeline commit, the real `config.yaml` digest, both AHI ancillary
digests, every staged-input manifest digest, and the API schema version. A repeat request
returned `delivery: "cached"`, attempt 1, and the identical `run_id`, with no BRIGHT child
process. Budget roughly **eight minutes** for a cold six-frame run on this workstation.

**Run state is now deterministic and terminal.** A relative `DETECTION_EXPLORER_STATE`
resolves from this repository rather than the process working directory, eliminating the
split `runs/` and `backend/runs/` stores. Frame caches publish atomically and a succeeded run
is reusable only when all expected cache files parse and match their frame identities.
Cancellation terminates the active subprocess, rechecks before publishing output, and emits
a terminal event; timeouts fail rather than masquerading as user cancellation. Graceful
shutdown and startup recovery both journal interrupted runs as terminal failures, so SSE
followers can reconnect and finish instead of hanging.

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

**Ten contextual layers, every endpoint verified before being written down.** DEA fuel
moisture, land cover, fractional cover and water observations; NPWS fire history; NSW local
government areas and reserves; four OpenWeatherMap layers. Two things bit during that check
and are recorded in `map/contextLayers.js`: the NSW ArcGIS services reject a request without a
`styles` parameter and return XML rather than an image, and their boundary layers are numbered
rather than named, so the LGA layer had to be identified through the ArcGIS REST endpoint.

**DEA is no longer silently truncated.** A response arriving at the service's feature cap is
reported as partial rather than presented as complete, and fixed scenes query a New South
Wales box instead of the continent. That took the demo scene from 4000 records, exactly the
cap, to 1785 genuinely inside the area of interest.

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

Three human delivery steps remain; the reproducibility setting and cold run are complete.

- **Foreground visual acceptance of this final build.** Open the production preview at
  `http://127.0.0.1:4173` and check both 1440×900 and 1280×720. Inspect AHI and polar
  footprints at several zooms, point-only markers in Auto mode, all three render modes,
  frame buttons, complete polar passes, layer/legend synchronisation, selection clearing,
  context layers, popup/detail content, the Current scene, sidebar/timeline overflow, and
  the browser console. The automated in-app Browser was unavailable on 18 August, so this
  step is deliberately not marked done.
- Record the walkthrough video after that visual acceptance pass.
- Add Karin's localhost approval to `decisions/DEV-01-localhost.md`, quoted with its date.

The accepted six-frame result is now cached under `runs/frames/` and repeats immediately.
Changing the pinned commit, real pipeline configuration, AHI ancillaries, staged manifests,
or API schema invalidates the relevant keys and forces a new isolated computation.
