# Scene selection for the April 2026 demonstration

**Date:** 2026-08-13
**Status:** **committed.** All four gates passed, plus FIRMS availability.
**Scripts:** `scripts/screen_scene_candidates.py`, `scripts/check_firms_availability.py`
**Raw results:** `scene_screening.json`, `fixtures/firms_*_20260409.csv`

## Recommendation

**`2026-04-09T04:00:00Z` to `2026-04-09T05:00:00Z`**, six frames at ten-minute cadence:
04:00, 04:10, 04:20, 04:30, 04:40, 04:50. Interval end exclusive.

Subject to the FIRMS availability check in Task 4 Step 0, which needs a MAP_KEY.

## The finding that changed the plan

The design spec named 05:00Z as the candidate, chosen on BRIGHT detection richness alone: it
holds 214 features across six frames, the most of any hour that day.

**05:00Z contains no polar observations at all.** Neither does 07:00Z, 08:00Z or 01:00Z. Five
of the eight hours screened have zero polar coverage over New South Wales.

Building the demonstration on 05:00Z would have produced an interface whose entire argument —
geostationary cadence set against polar resolution — had only one side present. The four-gate
screen exists precisely to catch that, and it did.

## Results

| Hour (UTC) | BRIGHT | Polar | Platforms | Nearest | Verdict |
|---|---|---|---|---|---|
| **04:00Z** | **144** | **1618** | **S-NPP VIIRS 1074, NOAA-20 VIIRS 544** | **0.1 km** | **selected** |
| 03:00Z | 98 | 1835 | NOAA-20 VIIRS 682, NOAA-21 VIIRS 1153 | 0.1 km | viable, not chosen |
| 06:00Z | 120 | 55 | Aqua MODIS 55 | 0.1 km | viable, not chosen |
| 02:00Z | 80 | 37 | S-NPP VIIRS 37 | 86.7 km | rejected, gate 3 |
| 05:00Z | 214 | 0 | — | — | rejected, gate 2 |
| 07:00Z | 142 | 0 | — | — | rejected, gate 2 |
| 08:00Z | 94 | 0 | — | — | rejected, gate 2 |
| 01:00Z | 71 | 0 | — | — | rejected, gate 2 |

## Why 04:00Z, and why not the alternatives

**04:00Z carries two platforms on two separate passes inside one hour.** Suomi-NPP crosses at
04:20 to 04:29 and NOAA-20 at 04:40 to 04:49. That is the ideal shape for this interface: the
time slider runs six geostationary frames across the hour while two polar passes appear, each
at its own instant, each ageing independently. A single-pass interval would demonstrate the
sparsity but not the per-platform retention.

Its nearest polar detection sits 0.1 km from a BRIGHT detection, so both sensors are looking
at the same fire rather than at unrelated events in the same state.

**03:00Z was rejected despite more polar records**, and the reason is reproducibility. Of its
1835 records, 1153 are NOAA-21. NASA FIRMS publishes no `VIIRS_NOAA21_SP` product: NOAA-21
exists only as near-real-time. Historical scenes use Standard Processing for reproducibility,
so almost two-thirds of 03:00Z's apparent advantage cannot be served reproducibly. 04:00Z's
platforms, Suomi-NPP and NOAA-20, both have SP products.

**06:00Z was rejected on thinness.** Fifty-five Aqua MODIS records from a single pass, against
1618 from two passes.

**02:00Z passed gate 2 and failed gate 3.** Its Suomi-NPP pass sits 86.7 km from the BRIGHT
cluster, which is a different fire. Two unrelated events on one map would misrepresent the
comparison rather than make it.

## Gate 4: staging is required either way

No frame in any candidate hour has its full 29-day statistical window on disk. For 04:00Z the
04:30 frame has 25 of 29 daily slots, inherited from the existing 04:30 stack that runs
2026-03-08 to 2026-04-05; it is missing 2026-04-06 through 2026-04-09. The other five frames
have none.

Staging therefore needs roughly 149 day-slots rather than the 174 a cold six-frame interval
would cost. Task 4 measures the per-slot download before committing.

## Method and its limits

Gate 1 counts features in D2's precomputed BRIGHT frames at
`deliverable_2_july/feed/replay_data/`. These are **screening data, not an oracle**: they
narrow the search, they do not certify that a recomputation will reproduce them. Spec §13
governs their promotion.

Gates 2 and 3 query the DEA Hotspots WFS over a New South Wales bounding box, filtered by the
interval. DEA carries the same polar platforms FIRMS does, so it stands in as a free proxy for
co-occurrence. It is a proxy and not a substitute: DEA and FIRMS run different algorithms and
will not agree record for record. What transfers is the fact of an overpass, not its contents.

The largest response was 1962 records against a query cap of 4000, so no candidate was
truncated.

Gate 4 walks the staged parquet tree. The window is the same time-of-day slot on each of the
previous 28 days, per `run_parquet_detection.py:228`.

## FIRMS availability: gate closed, 2026-08-13

Checked before any staging, as planned. All three Standard Processing products hold the scene
date:

| Product | FIRMS holds | Records on 2026-04-09 | In the 04:00Z hour |
|---|---|---|---|
| `VIIRS_SNPP_SP` | 2012-01-20 .. 2026-04-27 | 386 | **293** (Suomi-NPP, 04:27–04:29) |
| `VIIRS_NOAA20_SP` | 2018-04-01 .. 2026-05-31 | 582 | **212** (NOAA-20, 04:47–04:49) |
| `MODIS_SP` | 2000-11-01 .. 2026-04-30 | 66 | 0 |

505 Standard Processing records inside the hour. `VIIRS_NOAA21_SP` is confirmed absent from
the availability listing, which is what disqualified 03:00Z above.

MODIS contributes nothing to this hour, matching the DEA screen, so the scene is a two-VIIRS
comparison. That is no loss: the two passes are on different platforms twenty minutes apart,
which is exactly what the per-platform overpass retention needs to demonstrate.

Every row carries `scan`, `track`, `satellite` and `daynight`, so `polar_footprint` can
reconstruct footprints directly. An end-to-end check on a real row produced a valid polygon of
150,242 m², correct for a near-nadir VIIRS 375 m pixel. Responses are saved as fixtures for
Task 7.

### Two consequences for the interface

**Confidence is categorical, not numeric.** VIIRS SP rows carry `confidence` values like `n`
for nominal. D2's `confidence: float | None` cannot hold that. The schema's split into
`confidence` (legacy float), `confidence_native` and `confidence_scheme` is therefore load
bearing rather than defensive: coercing `n` to a number would invent information.

**The side ambiguity applies to nearly every detection here, not to a few.** Measured across
all 505 records in the hour:

| Platform | n | Scan | Latitude | Side IoU (min / median / max) | Below 0.95 |
|---|---|---|---|---|---|
| Suomi-NPP | 293 | 0.32–0.57 km | −37.0 .. −28.2 | 0.842 / 0.906 / 0.962 | 291 / 293 |
| NOAA-20 | 212 | 0.35–0.75 km | −36.1 .. −28.5 | 0.814 / 0.831 / 0.845 | 212 / 212 |

**503 of 505 fall below the threshold.** Scan angles here are modest, close to nadir, so it is
latitude rather than swath position driving this. The two-candidate rendering is the normal
case for this scene, not an exception, and Task 16 should treat its explanation as a standing
legend item rather than a rare per-feature warning.
