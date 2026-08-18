import { describe, expect, it } from 'vitest';
import spec from '@maplibre/maplibre-gl-style-spec';
import {
  DETECTION_SOURCES, DOT_FADE, FIRST_DETECTION_LAYER, RENDER_MODES, SELECTABLE_LAYERS,
  detectionLayers, filterFor,
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

const messages = (style) => validateStyleMin(style).map((error) => error.message);

/**
 * The test that matters.
 *
 * MapLibre throws on an invalid paint expression, and `addLayer` throwing abandons every
 * layer after it. The failure looks like an empty map rather than like an error, which is
 * exactly how a marker layer once went missing: a zoom interpolation nested inside a
 * multiplication, which the specification does not allow.
 */
describe('every render mode produces valid MapLibre', () => {
  for (const mode of RENDER_MODES) {
    for (const layer of detectionLayers(mode)) {
      it(`${mode} / ${layer.id}`, () => {
        expect(messages(asStyle([layer]))).toEqual([]);
      });
    }

    it(`${mode} / all layers as one style`, () => {
      expect(messages(asStyle(detectionLayers(mode)))).toEqual([]);
    });
  }

  // The specific mistake, kept as a live example so the guard cannot be weakened by
  // accident: this is what the polar marker looked like when it silently failed to load.
  it('rejects a zoom expression nested inside another expression', () => {
    const broken = {
      id: 'broken', type: 'circle', source: 'detection-dots',
      paint: {
        'circle-opacity': ['*', ['case', ['get', '_dimmed'], 0.45, 1],
                           ['interpolate', ['linear'], ['zoom'], 10.5, 1, 12, 0]],
      },
    };
    expect(messages(asStyle([broken])).length).toBeGreaterThan(0);
  });
});

describe('render modes say different things', () => {
  const paint = (mode, id, property) =>
    detectionLayers(mode).find((l) => l.id === id).paint[property];

  it('auto fades the marker out as the polygon becomes legible', () => {
    expect(paint('auto', 'det-dot-polar375', 'circle-opacity')[0]).toBe('interpolate');
  });

  it('points keeps every marker at every zoom', () => {
    expect(paint('points', 'det-dot-polar375', 'circle-opacity')[0]).toBe('case');
  });

  it('points hides the polygons rather than shrinking them', () => {
    expect(paint('points', 'det-fill', 'fill-opacity')).toBe(0);
    expect(paint('points', 'det-line', 'line-opacity')).toBe(0);
  });

  it('footprints keeps the polygons and stops the markers fading', () => {
    expect(paint('footprints', 'det-fill', 'fill-opacity')[0]).toBe('case');
    expect(paint('footprints', 'det-dot-geostationary', 'circle-opacity')[0]).toBe('case');
  });
});

describe('filters', () => {
  const keys = ['dea|AFIMG|6|VIIRS|Suomi-NPP'];

  it('shows only the layers that are switched on', () => {
    const filter = filterFor('det-fill', 'auto', keys);
    expect(JSON.stringify(filter)).toContain('dea|AFIMG|6|VIIRS|Suomi-NPP');
  });

  it('shows nothing when nothing is switched on', () => {
    const filter = filterFor('det-fill', 'auto', []);
    expect(JSON.stringify(filter)).toContain('[]');
  });

  it('sends each marker layer only its own sensor class', () => {
    expect(JSON.stringify(filterFor('det-dot-polar375', 'auto', keys)))
      .toContain('polar375');
    expect(JSON.stringify(filterFor('det-dot-geostationary', 'auto', keys)))
      .toContain('geostationary');
  });

  // Forcing true scale must not erase the DEA hotspots, which have no geometry to scale
  // and would otherwise disappear from a mode that claims to show everything at once.
  it('keeps markers for records with no footprint when footprints are forced', () => {
    const forced = JSON.stringify(filterFor('det-dot-polar375', 'footprints', keys));
    expect(forced).toContain('_hasFootprint');
    const auto = JSON.stringify(filterFor('det-dot-polar375', 'auto', keys));
    expect(auto).not.toContain('_hasFootprint');
  });

  it('splits the ambiguous outline off, so it can stay dashed', () => {
    const plain = JSON.stringify(filterFor('det-line', 'auto', keys));
    const ambiguous = JSON.stringify(filterFor('det-line-ambiguous', 'auto', keys));
    expect(plain).toContain('!=');
    expect(ambiguous).toContain('_ambiguous');
    expect(plain).not.toBe(ambiguous);
  });

  it('leaves the selection layers to their source', () => {
    expect(filterFor('sel-fill', 'auto', keys)).toBeNull();
  });

  it('accepts a Set as readily as an array', () => {
    const filter = filterFor('det-fill', 'auto', new Set(keys));
    expect(JSON.stringify(filter)).toContain('dea|AFIMG');
  });
});

describe('marker fade thresholds', () => {
  it('always fades upward', () => {
    for (const [from, to] of Object.values(DOT_FADE)) expect(from).toBeLessThan(to);
  });

  // A 375 m pixel needs far more zoom to resolve than a 2 km one, so its marker has to
  // survive longer. Getting this ordering backwards would hide the smallest footprints.
  it('keeps the smaller footprint marked for longer', () => {
    expect(DOT_FADE.polar375[0]).toBeGreaterThan(DOT_FADE.polar1km[0]);
    expect(DOT_FADE.polar1km[0]).toBeGreaterThan(DOT_FADE.geostationary[0]);
  });

  it('has a marker layer for every class it defines a fade for', () => {
    const ids = detectionLayers('auto').map((l) => l.id);
    for (const sensorClass of Object.keys(DOT_FADE)) {
      expect(ids).toContain(`det-dot-${sensorClass}`);
    }
  });
});

describe('wiring', () => {
  it('lists every source its layers draw from', () => {
    for (const layer of detectionLayers('auto')) {
      expect(DETECTION_SOURCES).toContain(layer.source);
    }
  });

  it('names only layers that exist as selectable', () => {
    const ids = detectionLayers('auto').map((l) => l.id);
    for (const id of SELECTABLE_LAYERS) expect(ids).toContain(id);
  });

  it('makes a marker clickable, or a detection is unreachable when zoomed out', () => {
    expect(SELECTABLE_LAYERS).toContain('det-dot-polar375');
  });

  it('anchors contextual rasters below the first detection layer', () => {
    expect(FIRST_DETECTION_LAYER).toBe(detectionLayers('auto')[0].id);
  });

  it('draws the selection above every detection', () => {
    const order = detectionLayers('auto').map((l) => l.id);
    expect(order.indexOf('sel-line')).toBeGreaterThan(order.indexOf('det-dot-polar375'));
  });

  it('keeps the same layer ids in every mode, so switching is a repaint', () => {
    const auto = detectionLayers('auto').map((l) => l.id);
    for (const mode of RENDER_MODES) {
      expect(detectionLayers(mode).map((l) => l.id)).toEqual(auto);
    }
  });
});
