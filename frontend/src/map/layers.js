/**
 * The detection layers, as data.
 *
 * They live here rather than inline in the component so their paint can be validated
 * against the MapLibre style specification in a test. That is not bureaucracy: an invalid
 * paint expression makes `addLayer` throw, which abandons the rest of the layer setup and
 * leaves a map that looks merely empty. It cost a layer once already, when a zoom
 * interpolation was nested inside a multiplication and MapLibre refused it with "zoom
 * expression may only be used as input to a top-level step or interpolate expression".
 */

/**
 * The zoom at which each footprint stops being a rumour.
 *
 * True scale is the argument of this interface, and true scale is also why both footprint
 * layers were invisible: at a state-wide view the ground resolution is about 3.4 km per
 * screen pixel, so a 375 m polar pixel spans 0.14 of a pixel and a 2 km AHI pixel spans
 * 0.59. They were being drawn correctly and could not be seen.
 *
 * So each footprint layer gets a marker that carries it until the polygon is legible,
 * then fades out. The marker never shares the screen with a footprint big enough to read,
 * which is what stops it misrepresenting pixel size: below the threshold no shape was
 * visible anyway, and above it the real polygon has taken over. The layer panel says the
 * same thing in words.
 *
 * Thresholds are where a footprint reaches roughly four screen pixels at NSW latitudes.
 */
export const DOT_FADE = {
  ahi: [8, 9.5],     // 2 km
  polar: [10.5, 12], // 375 m
};

/**
 * Solid below the fade, gone above it.
 *
 * `solid` may itself be a data expression. It has to be an output stop rather than a
 * factor applied to the result, because a zoom expression is only legal as the outermost
 * expression of a property.
 */
const fadeOut = ([from, to], solid = 1) =>
  ['interpolate', ['linear'], ['zoom'], from, solid, to, 0];

/** Dimmed means the pass is stale: observed earlier, not observed now. */
const whenDimmed = (dimmed, solid) => ['case', ['get', 'dimmed'], dimmed, solid];

const AHI_COLOUR = '#d95f02';
const POLAR_COLOUR = '#1b6ca8';
const POINT_COLOUR = '#6a3d9a';

/**
 * Draw order, bottom to top: footprints first, then the markers that stand in for them.
 *
 * `ahi-fill` is also the anchor contextual layers are inserted beneath, so every
 * contextual raster stays below every detection.
 */
export const DETECTION_LAYERS = [
  // AHI: 2 km pixels, warm fill.
  {
    id: 'ahi-fill', type: 'fill', source: 'ahi',
    paint: { 'fill-color': AHI_COLOUR, 'fill-opacity': 0.35 },
  },
  {
    id: 'ahi-line', type: 'line', source: 'ahi',
    paint: { 'line-color': AHI_COLOUR, 'line-width': 1 },
  },

  // Polar: 375 m pixels, cool fill, dimmed when the pass is stale.
  {
    id: 'polar-fill', type: 'fill', source: 'polar',
    paint: {
      'fill-color': POLAR_COLOUR,
      'fill-opacity': whenDimmed(0.12, 0.45),
    },
  },
  {
    id: 'polar-line', type: 'line', source: 'polar',
    paint: {
      'line-color': POLAR_COLOUR,
      'line-width': whenDimmed(0.6, 1.2),
      'line-dasharray': [2, 1], // dashed: the position is one of two candidates
    },
  },

  // Sources with no recoverable geometry, drawn honestly as points.
  {
    id: 'points-circle', type: 'circle', source: 'points',
    paint: {
      'circle-radius': 3.5,
      'circle-color': POINT_COLOUR,
      'circle-stroke-width': 1,
      'circle-stroke-color': '#ffffff',
    },
  },

  // The markers. They share their layer's colour, so the eye reads them as the same
  // thing seen from further away rather than as a separate kind of record.
  {
    id: 'ahi-dot', type: 'circle', source: 'ahi-dots',
    paint: {
      'circle-radius': 4,
      'circle-color': AHI_COLOUR,
      'circle-opacity': fadeOut(DOT_FADE.ahi),
      'circle-stroke-width': 1,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-opacity': fadeOut(DOT_FADE.ahi),
    },
  },
  {
    id: 'polar-dot', type: 'circle', source: 'polar-dots',
    paint: {
      'circle-radius': 3,
      'circle-color': POLAR_COLOUR,
      // Staleness dims the marker exactly as it dims the footprint, so the slider still
      // says which passes are contemporaneous and which are being remembered.
      'circle-opacity': fadeOut(DOT_FADE.polar, whenDimmed(0.45, 1)),
      'circle-stroke-width': 1,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-opacity': fadeOut(DOT_FADE.polar, whenDimmed(0.45, 1)),
    },
  },
];

/** Every GeoJSON source the detection layers draw from. */
export const DETECTION_SOURCES = [...new Set(DETECTION_LAYERS.map((l) => l.source))];

/** The layers a click selects a detection from. */
export const SELECTABLE_LAYERS = ['ahi-fill', 'polar-fill', 'points-circle',
                                  'ahi-dot', 'polar-dot'];

/** Contextual rasters are inserted beneath this, so they stay below every detection. */
export const FIRST_DETECTION_LAYER = DETECTION_LAYERS[0].id;
