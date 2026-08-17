import { describe, expect, it } from 'vitest';
import { brightFeatures, dotsFrom } from './features.js';

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
