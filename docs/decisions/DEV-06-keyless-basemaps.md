# DEV-06 — Basemaps stay keyless

**Date:** 17 August 2026
**Status:** accepted

## Context

The dashboard revamp added a background map picker: dark, satellite, terrain and a light
road reference. The obvious source is the XPRIZE finals frontend at
`20260224_BRIGHT_delivery/web/frontend`, which is where the rest of the layer and legend
work came from. It picks its basemaps from Mapbox:

```js
const BASEMAPS = [
  { id: 'satellite', label: 'Satellite', style: 'mapbox://styles/mapbox/satellite-streets-v12' },
  { id: 'dark', label: 'Dark', style: 'mapbox://styles/mapbox/dark-v11' },
  ...
];
```

That needs `VITE_MAPBOX_TOKEN`, and it needs `map.setStyle()` plus a `style.load` hook to
put every custom source and layer back after each switch.

## Decision

Keyless raster XYZ services only. CARTO `dark_all` and `light_all`, Esri World Imagery and
Esri World Topo. No Mapbox, no token, no `setStyle`.

## Why

**The repository is meant to become public.** MapLibre was chosen over Mapbox in the first
place so that no access token is required. A basemap picker that goes blank until someone
supplies their own credentials would reverse that decision quietly, through a file nobody
would think to check.

**It is also the simpler implementation here.** This map already starts from a local style
with no sources and attaches its basemap as an ordinary raster source, so that a stalled
tile service cannot stop detections from drawing. Switching is therefore a source swap,
and none of the reference's re-hydration machinery is needed.

**Every endpoint was requested before being written down**, the rule `contextLayers.js`
already holds itself to. All four returned an image of the correct content type.

## Consequences

- No vector basemap, so no label styling or feature querying against the base map. Nothing
  in this interface wants either.
- Esri serves `{z}/{y}/{x}`, row before column, unlike the XYZ convention. Written the
  other way round it returns tiles of somewhere else rather than an error, so
  `basemaps.test.js` asserts the axis order per host.
- Attribution is ours to carry, since there is no Mapbox control doing it. Each entry
  declares its own and MapLibre's attribution control renders it.
- If a token is ever wanted — for terrain, or for a styled vector base — this decision is
  the thing to revisit first, and it should be revisited explicitly.
