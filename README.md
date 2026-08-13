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

Under construction. See `docs/decisions/` for the decision record and the design spec it
implements.

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

To be written once the backend and frontend land. Two profiles are planned: a fixture profile
that runs from a clean clone with no credentials and no staged data, and a research profile
that additionally recomputes BRIGHT from staged inputs.
