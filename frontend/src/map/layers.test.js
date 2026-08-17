import { describe, expect, it } from 'vitest';
import spec from '@maplibre/maplibre-gl-style-spec';
import {
  DETECTION_LAYERS, DETECTION_SOURCES, DOT_FADE, FIRST_DETECTION_LAYER, SELECTABLE_LAYERS,
} from './layers.js';

const { validateStyleMin } = spec;

const EMPTY = { type: 'FeatureCollection', features: [] };

/** The layers in a style of their own, which is what MapLibre will be handed. */
const asStyle = (layers) => ({
  version: 8,
  sources: Object.fromEntries(
    DETECTION_SOURCES.map((id) => [id, { type: 'geojson', data: EMPTY }]),
  ),
  layers,
});

/**
 * The test that matters.
 *
 * MapLibre throws on an invalid paint expression, and `addLayer` throwing abandons every
 * layer after it. The failure looks like an empty map rather than like an error, which is
 * exactly how `polar-dot` went missing: a zoom interpolation nested inside a
 * multiplication, which the specification does not allow.
 */
describe('the detection layers are valid MapLibre', () => {
  for (const layer of DETECTION_LAYERS) {
    it(layer.id, () => {
      const errors = validateStyleMin(asStyle([layer])).map((e) => `${e.message}`);
      expect(errors).toEqual([]);
    });
  }

  it('validates as one style, sources and all', () => {
    expect(validateStyleMin(asStyle(DETECTION_LAYERS)).map((e) => e.message)).toEqual([]);
  });

  // The specific mistake, kept as a live example so the guard cannot be weakened by
  // accident: this is what `polar-dot` looked like when it silently failed to load.
  it('rejects a zoom expression nested inside another expression', () => {
    const broken = {
      id: 'broken', type: 'circle', source: 'polar-dots',
      paint: {
        'circle-opacity': ['*', ['case', ['get', 'dimmed'], 0.45, 1],
                           ['interpolate', ['linear'], ['zoom'], 10.5, 1, 12, 0]],
      },
    };
    expect(validateStyleMin(asStyle([broken])).length).toBeGreaterThan(0);
  });
});

describe('the marker layers stand in only while the footprint cannot be seen', () => {
  it('hands over to the polygon, rather than fading in alongside it', () => {
    for (const [, [from, to]] of Object.entries(DOT_FADE)) {
      expect(from).toBeLessThan(to);
    }
  });

  // A 375 m pixel needs far more zoom to resolve than a 2 km one, so its marker has to
  // survive longer. Getting this backwards would hide the smaller footprint again.
  it('keeps the smaller footprint marked for longer', () => {
    expect(DOT_FADE.polar[0]).toBeGreaterThan(DOT_FADE.ahi[0]);
    expect(DOT_FADE.polar[1]).toBeGreaterThan(DOT_FADE.ahi[1]);
  });

  it('gives each footprint layer a marker fed from its own source', () => {
    for (const id of ['ahi', 'polar']) {
      const dot = DETECTION_LAYERS.find((l) => l.id === `${id}-dot`);
      expect(dot.source).toBe(`${id}-dots`);
      expect(DETECTION_SOURCES).toContain(`${id}-dots`);
    }
  });
});

describe('wiring', () => {
  it('lists every source its layers draw from', () => {
    for (const layer of DETECTION_LAYERS) {
      expect(DETECTION_SOURCES).toContain(layer.source);
    }
  });

  it('names only layers that exist as selectable', () => {
    const ids = DETECTION_LAYERS.map((l) => l.id);
    for (const id of SELECTABLE_LAYERS) expect(ids).toContain(id);
  });

  it('makes a marker clickable, or a detection is unreachable when zoomed out', () => {
    expect(SELECTABLE_LAYERS).toContain('ahi-dot');
    expect(SELECTABLE_LAYERS).toContain('polar-dot');
  });

  it('anchors contextual rasters below the first detection layer', () => {
    expect(FIRST_DETECTION_LAYER).toBe(DETECTION_LAYERS[0].id);
  });

  it('draws markers above footprints', () => {
    const order = DETECTION_LAYERS.map((l) => l.id);
    expect(order.indexOf('polar-dot')).toBeGreaterThan(order.indexOf('polar-fill'));
    expect(order.indexOf('ahi-dot')).toBeGreaterThan(order.indexOf('ahi-fill'));
  });
});
