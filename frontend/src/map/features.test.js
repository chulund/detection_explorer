import { describe, expect, it } from 'vitest';
import { brightFeatures, decorateFeatures, dotsFrom } from './features.js';

const FOOTPRINT = {
  type: 'Polygon',
  coordinates: [[[148.0, -32.0], [148.02, -32.0], [148.02, -31.98], [148.0, -31.98],
                 [148.0, -32.0]]],
};

const row = (extra = {}) => ({
  region: 'nsw', x: '671', y: '287', lon: '148.0', lat: '-32.0',
  frp: '12.5', confidence: '80', ...extra,
});

const frames = (extra = {}) => [{ frame: '20260409040000', detections: [row(extra)] }];

describe('brightFeatures', () => {
  it('draws the pixel polygon the run supplied', () => {
    const [feature] = brightFeatures(frames({ footprint: FOOTPRINT }));
    expect(feature.geometry).toEqual(FOOTPRINT);
  });

  // The whole reason the BRIGHT layer was blank: a point cannot be drawn by a fill layer,
  // so a run's output has to arrive with area or it is invisible.
  it('does not reduce a footprinted detection to a point', () => {
    const [feature] = brightFeatures(frames({ footprint: FOOTPRINT }));
    expect(feature.geometry.type).not.toBe('Point');
  });

  it('claims ahi_grid only when there is actually a polygon', () => {
    const [withPoly] = brightFeatures(frames({ footprint: FOOTPRINT }));
    const [without] = brightFeatures(frames());
    expect(withPoly.properties.footprint_method).toBe('ahi_grid');
    expect(withPoly.properties.footprint_status).toBe('validated');
    expect(without.properties.footprint_method).toBeNull();
    expect(without.properties.footprint_status).toBeNull();
  });

  it('falls back to the row position when the pixel is off-grid', () => {
    const [feature] = brightFeatures(frames());
    expect(feature.geometry).toEqual({ type: 'Point', coordinates: [148.0, -32.0] });
  });

  it('labels a run as computed replay, never live', () => {
    const [feature] = brightFeatures(frames({ footprint: FOOTPRINT }));
    expect(feature.properties.data_nature).toBe('replay');
    expect(feature.properties.computation).toBe('computed');
    expect(feature.properties.detected_at).toBe('2026-04-09T04:00:00Z');
  });

  it('skips rows with no usable position rather than placing them at null island', () => {
    expect(brightFeatures([{ frame: '20260409040000', detections: [row({ lon: '' })] }]))
      .toHaveLength(0);
  });

  it('tolerates an empty or absent run', () => {
    expect(brightFeatures([])).toEqual([]);
    expect(brightFeatures(undefined)).toEqual([]);
    expect(brightFeatures([{ frame: '20260409040000' }])).toEqual([]);
  });

  // The channel the detection is actually made on. Reporting it unlabelled alongside a
  // VIIRS 3.74 um reading would present two different measurements as one quantity.
  it('carries the mid-infrared brightness temperature with its band', () => {
    const [feature] = brightFeatures(frames({ mir: '320.75', tir: '303.56' }));
    expect(feature.properties.brightness_k).toBe(320.75);
    expect(feature.properties.brightness_channel).toContain('B07');
    expect(feature.properties.brightness_channel).toContain('3.9');
  });

  it('leaves brightness absent when the run did not report it', () => {
    const [feature] = brightFeatures(frames());
    expect(feature.properties.brightness_k).toBeNull();
    expect(feature.properties.brightness_channel).toBeNull();
  });

  it('takes its version from configuration rather than a literal in the code', () => {
    const [feature] = brightFeatures(frames(), { algorithmVersion: '2.1' });
    expect(feature.properties.algorithm_version).toBe('2.1');
    expect(brightFeatures(frames())[0].properties.algorithm_version).toBe('2.0');
  });
});

describe('decorateFeatures', () => {
  const polygon = {
    type: 'Feature',
    geometry: { type: 'MultiPolygon', coordinates: [[[[1, 2], [1, 3], [2, 3], [1, 2]]]] },
    properties: {
      id: 'firms:1', source: 'firms', product: 'VIIRS_SNPP_SP', algorithm_version: '2',
      instrument: 'VIIRS', platform: 'Suomi-NPP', lat: -32, lon: 148,
      footprint_method: 'polar_reconstructed', footprint_side: 'ambiguous',
    },
  };
  const point = {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [148, -32] },
    properties: {
      id: 'dea:1', source: 'dea', product: 'AFIMG', algorithm_version: '6',
      instrument: 'VIIRS', platform: 'NOAA-20', lat: -32, lon: 148,
    },
  };
  const colours = { 'firms|VIIRS_SNPP_SP|2|VIIRS|Suomi-NPP': '#4cc9f0' };
  const decorate = (features, options) => decorateFeatures(features, {
    colours, dimmedIds: new Set(['firms:1']), ...options,
  });

  it('tags each feature with the layer it belongs to', () => {
    const [first] = decorate([polygon]);
    expect(first.properties._key).toBe('firms|VIIRS_SNPP_SP|2|VIIRS|Suomi-NPP');
  });

  it('carries the colour onto the feature, so one source can paint every layer', () => {
    expect(decorate([polygon])[0].properties._colour).toBe('#4cc9f0');
  });

  it('falls back to a visible colour rather than an undefined one', () => {
    const [first] = decorate([point], { colours: {} });
    expect(first.properties._colour).toMatch(/^#|^rgb/);
  });

  it('records the sensor class, which decides when the marker fades', () => {
    expect(decorate([polygon])[0].properties._class).toBe('polar375');
    const modis = { ...point, properties: { ...point.properties, instrument: 'MODIS' } };
    expect(decorate([modis])[0].properties._class).toBe('polar1km');
  });

  // Forcing true scale hides markers, but only for records that actually have geometry.
  it('says whether the record has geometry at all', () => {
    expect(decorate([polygon])[0].properties._hasFootprint).toBe(true);
    expect(decorate([point])[0].properties._hasFootprint).toBe(false);
  });

  it('flags the two-candidate case, so its outline can stay dashed', () => {
    expect(decorate([polygon])[0].properties._ambiguous).toBe(true);
    expect(decorate([point])[0].properties._ambiguous).toBe(false);
  });

  it('marks a stale pass as dimmed', () => {
    expect(decorate([polygon])[0].properties._dimmed).toBe(true);
    expect(decorate([point])[0].properties._dimmed).toBe(false);
  });

  it('leaves the original properties intact', () => {
    const [first] = decorate([polygon]);
    expect(first.properties.id).toBe('firms:1');
    expect(first.geometry).toEqual(polygon.geometry);
    expect(polygon.properties._key).toBeUndefined();  // no mutation of the input
  });

  it('survives no features and no options', () => {
    expect(decorateFeatures(undefined, {})).toEqual([]);
    expect(decorateFeatures([point], {})).toHaveLength(1);
  });
});

describe('dotsFrom', () => {
  it('puts one point at each detection, whatever its footprint shape', () => {
    const collection = {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        geometry: { type: 'MultiPolygon', coordinates: [[[[1, 2], [1, 3], [2, 3], [1, 2]]]] },
        properties: { id: 'a', lat: -32.2, lon: 145.6 },
      }],
    };
    const dots = dotsFrom(collection);
    expect(dots.features).toHaveLength(1);
    expect(dots.features[0].geometry).toEqual({ type: 'Point', coordinates: [145.6, -32.2] });
  });

  it('carries the properties through, so a dot is clickable like its footprint', () => {
    const collection = {
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [1, 2] },
                   properties: { id: 'a', lat: 2, lon: 1, dimmed: true } }],
    };
    expect(dotsFrom(collection).features[0].properties.id).toBe('a');
    expect(dotsFrom(collection).features[0].properties.dimmed).toBe(true);
  });

  it('drops detections with no position instead of inventing one', () => {
    const collection = {
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: null, properties: { id: 'a' } }],
    };
    expect(dotsFrom(collection).features).toEqual([]);
  });

  it('survives an absent collection', () => {
    expect(dotsFrom(undefined)).toEqual({ type: 'FeatureCollection', features: [] });
  });
});
