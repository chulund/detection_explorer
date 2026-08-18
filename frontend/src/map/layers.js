/**
 * The detection layers, as data.
 *
 * They live here rather than inline in the component so their paint can be validated
 * against the MapLibre style specification in a test. That is not bureaucracy: an invalid
 * paint expression makes `addLayer` throw, which abandons the rest of the layer setup and
 * leaves a map that looks merely empty. It cost a layer once already, when a zoom
 * interpolation was nested inside a multiplication and MapLibre refused it with "zoom
 * expression may only be used as input to a top-level step or interpolate expression".
 *
 * Every detection shares one source and one set of layers, whatever algorithm produced
 * it. Colour comes from the feature (`_colour`), so twelve algorithm and sensor pairings
 * cost six layers rather than thirty-six, and switching one on is a filter update rather
 * than a rebuild.
 */

/**
 * The zoom at which each footprint stops being a rumour.
 *
 * True scale is the argument of this interface, and true scale is also why the footprint
 * layers were once invisible: at a state-wide view the ground resolution is about 3.4 km
 * per screen pixel, so a 375 m polar pixel spans 0.14 of a pixel and a 2 km AHI pixel
 * spans 0.59. They were drawn correctly and could not be seen.
 *
 * Each sensor class therefore gets a marker that carries it until the polygon is legible,
 * then fades out. The marker never shares the screen with a footprint big enough to read,
 * which is what stops it misrepresenting pixel size. Thresholds are where a footprint
 * reaches roughly four screen pixels at New South Wales latitudes.
 *
 * Three marker layers rather than one because the fade is a zoom expression, and a zoom
 * expression is only legal as the outermost expression of a property. Per-feature fade
 * stops are therefore impossible; per-class layers are how the thresholds can differ.
 */
export const DOT_FADE = {
  geostationary: [8, 9.5],   // 2 km
  polar1km: [9.2, 10.7],     // 1 km
  polar375: [10.5, 12],      // 375 m
};

export const RENDER_MODES = ['auto', 'footprints', 'points'];

/** Contextual rasters are inserted beneath this, so they stay below every detection. */
export const FIRST_DETECTION_LAYER = 'det-fill';

export const DETECTION_SOURCES = ['detections', 'detection-dots',
                                  'selection', 'selection-dot'];

export const SELECTABLE_LAYERS = ['det-fill', 'det-dot-geostationary',
                                  'det-dot-polar1km', 'det-dot-polar375'];

const SELECTION_ACCENT = '#ffe066';

/** Solid below the fade, gone above it. `solid` may itself be a data expression. */
const fadeOut = ([from, to], solid) =>
  ['interpolate', ['linear'], ['zoom'], from, solid, to, 0];

/** Dimmed means the pass is stale: observed earlier, not observed now. */
const whenDimmed = (dimmed, solid) => ['case', ['get', '_dimmed'], dimmed, solid];

const IS_POLYGON = ['any', ['==', ['geometry-type'], 'Polygon'],
                    ['==', ['geometry-type'], 'MultiPolygon']];

const dotRadius = ['interpolate', ['linear'], ['zoom'], 4, 2.6, 8, 3.8, 12, 5.5];

function dotLayer(sensorClass, mode) {
  const solid = whenDimmed(0.5, 1);
  return {
    id: `det-dot-${sensorClass}`,
    type: 'circle',
    source: 'detection-dots',
    paint: {
      'circle-radius': dotRadius,
      'circle-color': ['get', '_colour'],
      // In `points` the marker is the whole answer, so it never fades. In `auto` it hands
      // over to the polygon. In `footprints` only records that have no geometry keep one.
      'circle-opacity': mode === 'auto' ? fadeOut(DOT_FADE[sensorClass], solid) : solid,
      'circle-stroke-width': 1,
      'circle-stroke-color': 'rgba(255,255,255,0.85)',
      'circle-stroke-opacity': mode === 'auto'
        ? fadeOut(DOT_FADE[sensorClass], 0.9)
        : 0.9,
    },
  };
}

/**
 * Layer definitions for one render mode.
 *
 * `auto` shows a marker until the true-scale polygon can be read, then the polygon.
 * `footprints` forces true scale everywhere, keeping markers only for records that carry
 * no geometry at all — every DEA hotspot, which would otherwise vanish. `points` drops
 * the polygons and marks every detection, which is the honest way to compare counts
 * rather than areas.
 */
export function detectionLayers(mode = 'auto') {
  const polygonsHidden = mode === 'points';
  return [
    {
      id: 'det-fill',
      type: 'fill',
      source: 'detections',
      paint: {
        'fill-color': ['get', '_colour'],
        'fill-opacity': polygonsHidden ? 0 : whenDimmed(0.15, 0.4),
      },
    },
    {
      // A clean boundary is what keeps a footprint readable against a dark basemap, so
      // the stroke is deliberately stronger than the fill.
      id: 'det-line',
      type: 'line',
      source: 'detections',
      paint: {
        'line-color': ['get', '_colour'],
        'line-width': whenDimmed(0.8, 1.4),
        'line-opacity': polygonsHidden ? 0 : whenDimmed(0.55, 0.95),
      },
    },
    {
      // Dashed, because a FIRMS record cannot say which side of the ground track the
      // pixel lay on and both candidates are drawn. `line-dasharray` takes no data
      // expression, so the ambiguous case needs its own layer to stay distinguishable.
      id: 'det-line-ambiguous',
      type: 'line',
      source: 'detections',
      paint: {
        'line-color': ['get', '_colour'],
        'line-width': whenDimmed(0.8, 1.2),
        'line-opacity': polygonsHidden ? 0 : whenDimmed(0.5, 0.9),
        'line-dasharray': [2, 1.4],
      },
    },
    dotLayer('geostationary', mode),
    dotLayer('polar1km', mode),
    dotLayer('polar375', mode),

    // The selection, above everything. A halo rather than a colour change, so the
    // detection keeps saying which algorithm produced it while it is selected.
    {
      id: 'sel-fill',
      type: 'fill',
      source: 'selection',
      paint: { 'fill-color': SELECTION_ACCENT, 'fill-opacity': 0.2 },
    },
    {
      id: 'sel-line',
      type: 'line',
      source: 'selection',
      paint: { 'line-color': SELECTION_ACCENT, 'line-width': 2.4 },
    },
    {
      id: 'sel-halo',
      type: 'circle',
      source: 'selection-dot',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 7, 12, 12],
        'circle-color': 'rgba(0,0,0,0)',
        'circle-stroke-width': 2,
        'circle-stroke-color': SELECTION_ACCENT,
      },
    },
  ];
}

/**
 * The filter for one layer, given the mode and which taxonomy keys are switched on.
 *
 * Toggling a layer is a filter update rather than an add and remove, which keeps a
 * twelve-row layer panel responsive.
 */
export function filterFor(layerId, mode, enabledKeys) {
  const keys = ['in', ['get', '_key'], ['literal', [...(enabledKeys ?? [])]]];

  if (layerId === 'det-fill') return ['all', IS_POLYGON, keys];
  if (layerId === 'det-line') {
    return ['all', IS_POLYGON, ['!=', ['get', '_ambiguous'], true], keys];
  }
  if (layerId === 'det-line-ambiguous') {
    return ['all', IS_POLYGON, ['==', ['get', '_ambiguous'], true], keys];
  }
  if (layerId.startsWith('det-dot-')) {
    const sensorClass = layerId.slice('det-dot-'.length);
    const clauses = ['all', ['==', ['get', '_class'], sensorClass], keys];
    // Forcing true scale must not erase the 1785 records that have no geometry to scale.
    if (mode === 'footprints') clauses.push(['==', ['get', '_hasFootprint'], false]);
    return clauses;
  }
  return null;   // the selection layers are driven by their source, not by a filter
}

/** Draw order is the array order, so this is also the anchor for contextual rasters. */
export const DETECTION_LAYER_IDS = detectionLayers('auto').map((layer) => layer.id);
