# Detection Explorer

A map-centric interface over three fire-detection sources: the BRIGHT algorithm recomputed
from staged Himawari AHI inputs, polar-orbiting MODIS and VIIRS detections from NASA FIRMS
rendered as reconstructed pixel footprints, and hotspots from the Digital Earth Australia
Hotspots service.

It exists to make one comparison legible. Within a single hour, BRIGHT produces a detection
every ten minutes from geostationary orbit, while the polar sensors deliver one or two
overpasses at far finer spatial resolution. Drawing both at true pixel scale on one map, each
carrying its own observation time, states the cadence-against-resolution trade directly.

Built as deliverable D3 of an RMIT internal translation grant, August 2026.

## Status

Implementation, automated verification, and a pinned six-frame cold-run acceptance pass are
complete. A foreground visual acceptance pass and the walkthrough video still remain; see
`docs/STATUS.md` for the exact handoff state and `docs/decisions/` for the decision record.

## What this is not

It is not a live detection system. The BRIGHT near-real-time pipeline used during the XPRIZE
Wildfire finals no longer runs, so detection here recomputes real April 2026 inputs and is
labelled `replay` throughout. Nothing in this interface claims to be current except the
Digital Earth Australia feed, which genuinely is.

Polygons are satellite pixel footprints, never fire perimeters.

Polar footprints are labelled experimental. Their orientation has not been validated against a
geolocation granule at Australian latitudes, and a FIRMS record cannot say which side of the
satellite ground track a pixel lay on, so two candidates are drawn rather than one.

## Licensing

**Private. All rights reserved.**

No open-source licence has been chosen. The repository depends on unpublished work belonging
to the research team, and no release decision has been made. Do not redistribute.

## Running it

Two profiles. The **fixture profile** is a clean clone with no credentials and no staged
data: both scenes serve from committed fixtures, and `/api/v2/status` reports which
providers are unavailable and why. The **research profile** adds a `.env` and recomputes
BRIGHT from staged inputs.

Configuration is a `.env` at the repository root, read at startup. Copy `.env.example` and
fill in what you have. Providers without configuration degrade honestly rather than stopping
the service; when `BRIGHT_PIPELINE_PATH` is set, `BRIGHT_PIPELINE_SHA` is also required and
must match a clean checkout. A variable already exported in the shell wins over the file.

```powershell
cd backend
C:\Users\nurfa\.conda\envs\bright\python.exe -m uvicorn app.main:app --reload --port 8000
# Swagger at http://localhost:8000/api/docs

cd ../frontend
npm install && npm run dev      # http://localhost:5173, proxies /api to port 8000
```

`BRIGHT_PIPELINE_PATH` is what separates the profiles. Without it the BRIGHT provider
reports unavailable, a run is refused with 503, and the AHI footprint layer stays empty:
the AHI pixel polygons come from the sensor grid that ships with the pipeline, joined on
the `x`,`y` a run emits, and DEA's hotspot feed carries no pixel index to join on.

Research runs are tied to the configured commit, the real pipeline configuration, both AHI
ancillaries, staged-input manifests, and the API schema. Each attempt computes with `--force`
inside its own state directory; it never treats the pipeline's pre-existing `data/streamed`
files as a fresh result. The accepted cold six-frame run took about eight minutes on the
research workstation, while an identical repeat returned the validated cache immediately.

`OPENWEATHER_API_KEY` enables the four weather layers. It is served to the browser by
`/api/v2/status` rather than baked into the bundle, so a built frontend can be shared
without carrying it. Absent, the layers are not offered at all: a checkbox that does
nothing is a worse answer than an honest absence.

Basemaps need no key of any kind, which is deliberate — see
`docs/decisions/DEV-06-keyless-basemaps.md`.

## Reading the map

Detection layers are named by what produced them: one row per algorithm, version, sensor
and platform, derived from the records rather than declared in advance. Warm colours are
geostationary, cool are polar-orbiting. A row reading zero was queried and returned nothing
for the window, which is not the same as never having been consulted.

Footprints are drawn at true scale, so at a state-wide view a 375 m polar pixel is a
fraction of a screen pixel. Each detection therefore also carries a marker that hands over
to the real polygon once it is large enough to read. The **Rendering** control forces the
question either way: *Footprints* keeps true scale at every zoom, *Points* marks every
detection regardless of pixel size.

Everything else — what the caveats mean, why confidence is stored twice, which band a
brightness temperature came from — is in **About this data** in the header.
