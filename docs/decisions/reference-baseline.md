# The D2 frames are a reference baseline, not an oracle

**Date:** 2026-08-13
**Status:** decided — **not promoted**
**Governs:** spec §13

## Question

D2's `feed/replay_data/` holds 92 precomputed BRIGHT frames for 2026-04-09. The spec called
them a reference baseline and set a condition for promoting them to an exact regression
oracle: their algorithm commit, configuration and input dataset must be known and must match
the recomputation. Otherwise a difference is legitimate drift rather than a defect.

The staged inputs now exist, so the comparison can be made.

## What was compared

Frame `20260409042000`, recomputed through the run worker against the newly staged 29-day
window, against the same frame in `replay_data/`.

| | Reference | Recomputed |
|---|---|---|
| Detections | 25 | 54 |
| Longitude range | 147.300 – 150.480 | 146.023 – 150.813 |
| Latitude range | −35.300 – −29.400 | −38.946 – −23.728 |
| Exact coordinate matches | — | 0 of 25 |
| Nearest recomputed to each reference point | — | min 0.0 km, **median 1.1 km**, max 3.1 km |

## Reading

**The recomputation finds the same fires.** A median separation of 1.1 km against a 2 km AHI
pixel is sub-pixel agreement. The initial "0 of 25 exact matches" was an artifact of comparing
rounded coordinates; it measured pixel-centre identity, not detection agreement, and it was
the wrong test.

**But three differences rule out exact regression.**

*Spatial extent.* The recomputation spans −38.9 to −23.7 degrees, reaching into Victoria and
Queensland. The reference spans −35.3 to −29.4, consistent with a New South Wales clip. These
are not the same query area, so counts cannot be compared directly.

*A systematic sub-pixel offset.* A median 1.1 km displacement between otherwise-matching
detections points at a different pixel grid rather than a different algorithm. The most likely
cause is the source catalogue: `config.yaml` defaults to `ahi_data_source: jaxa`, and this
staging run used `--ahi-source arc`, the NCI archive. Those are different distributions of the
same Himawari observations and need not share pixel-centre conventions exactly.

*Provenance is unrecorded.* Neither the algorithm commit nor the configuration that produced
the reference frames was captured at the time. Without them, no difference can be attributed
with confidence, which is the condition §13 set.

## Decision

**Not promoted.** The frames remain a reference baseline and the demonstration fallback. They
are useful for three things and unsuitable for a fourth:

- Screening candidate scenes, which is what they were used for.
- Sanity-checking that a recomputation finds fire in the right places.
- Serving the fixture profile when no pipeline is installed.
- **Not** asserting that a recomputation is correct or regressed.

The D3 report must describe them in those terms and must not claim the recomputation
reproduces them.

## Worth doing later, out of scope for D3

Recomputing a frame with `ahi_data_source: jaxa` would test the offset hypothesis directly. If
the offset vanishes, the cause is the catalogue rather than the algorithm, and the reference
becomes comparable after a documented reprojection. That is a half-day of work and no new
data, but it is not needed for the deliverable, and the honest position without it is simply
that the baseline is not an oracle.
