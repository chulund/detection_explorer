import { describe, expect, it } from 'vitest';
import {
  buildTaxonomy, detectionKey, effectiveTaxonomyKeys, sensorClassFor,
} from './taxonomy.js';
import { colourFor } from './palette.js';

const feature = (props) => ({
  type: 'Feature',
  geometry: { type: 'Point', coordinates: [148, -32] },
  properties: {
    source: 'dea', product: 'AFIMG', algorithm: 'AFIMG', algorithm_version: '6',
    instrument: 'VIIRS', platform: 'Suomi-NPP', lat: -32, lon: 148, ...props,
  },
});

const SOURCES = {
  dea: { available: true, count: 2, products_queried: ['*'] },
  firms: { available: true, count: 1,
           products_queried: ['MODIS_SP', 'VIIRS_SNPP_SP', 'VIIRS_NOAA20_SP'] },
};

describe('detectionKey', () => {
  it('separates two algorithms on the same sensor and platform', () => {
    const a = detectionKey(feature({ product: 'AFIMG' }).properties);
    const b = detectionKey(feature({ product: 'AFMOD' }).properties);
    expect(a).not.toBe(b);
  });

  it('separates two platforms running the same algorithm', () => {
    const a = detectionKey(feature({ platform: 'Suomi-NPP' }).properties);
    const b = detectionKey(feature({ platform: 'NOAA-20' }).properties);
    expect(a).not.toBe(b);
  });

  // BRIGHT AHI 1.86 from DEA and BRIGHT 2.0 from a run are the same algorithm family on
  // the same sensor, and the whole point of the demo is telling them apart.
  it('separates two versions of one algorithm', () => {
    const a = detectionKey(feature({ product: 'BRIGHT AHI', algorithm_version: '1.86' }).properties);
    const b = detectionKey(feature({ product: 'BRIGHT AHI', algorithm_version: '2.0' }).properties);
    expect(a).not.toBe(b);
  });
});

describe('sensorClassFor', () => {
  it('knows AHI is geostationary at 2 km', () => {
    const ahi = sensorClassFor('AHI');
    expect(ahi.orbit).toBe('geostationary');
    expect(ahi.resolutionM).toBe(2000);
  });

  it('separates the two polar resolutions, because their markers fade differently', () => {
    expect(sensorClassFor('VIIRS').resolutionM).toBe(375);
    expect(sensorClassFor('MODIS').resolutionM).toBe(1000);
    expect(sensorClassFor('VIIRS').id).not.toBe(sensorClassFor('MODIS').id);
  });

  it('does not invent a class for an instrument it does not know', () => {
    expect(sensorClassFor('SLSTR').orbit).toBe('unknown');
  });
});

describe('buildTaxonomy', () => {
  const features = [
    feature({ product: 'AFIMG', platform: 'Suomi-NPP' }),
    feature({ product: 'AFIMG', platform: 'Suomi-NPP' }),
    feature({ product: 'AFIMG', platform: 'NOAA-20' }),
    feature({ source: 'firms', product: 'VIIRS_SNPP_SP', algorithm: 'VIIRS_SNPP_SP',
              algorithm_version: '2', platform: 'Suomi-NPP' }),
    feature({ source: 'bright', product: 'BRIGHT AHI', algorithm: 'BRIGHT',
              algorithm_version: '2.0', instrument: 'AHI', platform: 'Himawari-9' }),
  ];
  const groups = buildTaxonomy(features, SOURCES);
  const rows = groups.flatMap((g) => g.rows);
  const row = (product, platform) =>
    rows.find((r) => r.product === product && (!platform || r.platform === platform));

  it('counts each algorithm and platform pairing separately', () => {
    expect(row('AFIMG', 'Suomi-NPP').count).toBe(2);
    expect(row('AFIMG', 'NOAA-20').count).toBe(1);
  });

  it('groups by source, recomputed first and archival last', () => {
    expect(groups.map((g) => g.source)).toEqual(['bright', 'firms', 'dea']);
  });

  // Without this a queried product that returned nothing simply disappears, and a reader
  // cannot tell "no MODIS detections" from "MODIS was never consulted".
  it('keeps a row for a product that was queried and returned nothing', () => {
    const modis = row('MODIS_SP');
    expect(modis).toBeDefined();
    expect(modis.count).toBe(0);
    expect(modis.status).toBe('empty');
    expect(modis.instrument).toBe('MODIS');
  });

  it('does not invent zero rows for a source that reports a wildcard query', () => {
    const dea = groups.find((g) => g.source === 'dea');
    expect(dea.rows.every((r) => r.count > 0)).toBe(true);
  });

  it('marks rows from an unavailable source rather than dropping them', () => {
    const [group] = buildTaxonomy([], {
      firms: { available: false, reason: 'no key', products_queried: ['MODIS_SP'] },
    });
    expect(group.available).toBe(false);
    expect(group.rows[0].status).toBe('unavailable');
  });

  it('carries the sensor class onto every row, for the marker fade', () => {
    expect(rows.every((r) => r.sensorClass)).toBe(true);
    expect(row('BRIGHT AHI').sensorClass.orbit).toBe('geostationary');
  });

  it('totals each group', () => {
    expect(groups.find((g) => g.source === 'dea').count).toBe(3);
  });

  it('survives an empty scene', () => {
    expect(buildTaxonomy([], {})).toEqual([]);
    expect(buildTaxonomy(undefined, undefined)).toEqual([]);
  });
});

describe('effectiveTaxonomyKeys', () => {
  it('defaults a newly completed run layer on while preserving explicit opt-outs', () => {
    const before = buildTaxonomy([feature({})], SOURCES);
    const deaKey = before.flatMap((g) => g.rows).find((r) => r.count > 0).key;
    const overrides = { [deaKey]: false };
    const after = buildTaxonomy([
      feature({}),
      feature({ source: 'bright', product: 'BRIGHT AHI', algorithm: 'BRIGHT',
                algorithm_version: '2.0', instrument: 'AHI', platform: 'Himawari-9' }),
    ], SOURCES);

    const enabled = effectiveTaxonomyKeys(after, overrides);
    const brightKey = after.flatMap((g) => g.rows).find((r) => r.source === 'bright').key;
    expect(enabled.has(deaKey)).toBe(false);
    expect(enabled.has(brightKey)).toBe(true);
  });
});

describe('colourFor', () => {
  const keys = ['dea|AFIMG|6|VIIRS|Suomi-NPP', 'dea|BRIGHT AHI|1.86|AHI|Himawari-9',
                'firms|VIIRS_SNPP_SP|2|VIIRS|Suomi-NPP'];

  it('gives every layer its own colour', () => {
    const colours = keys.map((k) => colourFor(k, keys));
    expect(new Set(colours).size).toBe(keys.length);
  });

  // The demo scene alone puts nine layers in the polar family. A fixed ramp shorter than
  // that wraps, and two different algorithms end up painted the same colour — which is
  // exactly what happened: AFIMG on NOAA-20 collided with VIIRS_SNPP_SP on Suomi-NPP.
  it('does not repeat a colour when there are more layers than a ramp has entries', () => {
    const many = [];
    for (let i = 0; i < 14; i += 1) many.push(`dea|P${i}|6|VIIRS|Suomi-NPP`);
    for (let i = 0; i < 6; i += 1) many.push(`dea|A${i}|1|AHI|Himawari-9`);
    const colours = many.map((k) => colourFor(k, many));
    expect(new Set(colours).size).toBe(many.length);
  });

  it('keeps the two families apart however many layers there are', () => {
    const many = [];
    for (let i = 0; i < 14; i += 1) many.push(`dea|P${i}|6|VIIRS|Suomi-NPP`);
    for (let i = 0; i < 6; i += 1) many.push(`dea|A${i}|1|AHI|Himawari-9`);
    const hue = (hex) => {
      const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
      const max = Math.max(r, g, b); const min = Math.min(r, g, b);
      if (max === min) return 0;
      const d = max - min;
      const h = max === r ? ((g - b) / d + (g < b ? 6 : 0))
        : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
      return h * 60;
    };
    for (const key of many) {
      const h = hue(colourFor(key, many));
      if (key.includes('|AHI|')) expect(h).toBeLessThan(60);          // warm
      else expect(h).toBeGreaterThan(150);                            // cool
    }
  });

  it('is stable regardless of the order the keys arrive in', () => {
    const forward = colourFor(keys[0], keys);
    const backward = colourFor(keys[0], [...keys].reverse());
    expect(forward).toBe(backward);
  });

  // Colour is how the map says geostationary from polar at a glance, so the two families
  // must not draw from the same ramp.
  it('gives geostationary a warm colour and polar a cool one', () => {
    const geo = colourFor('dea|BRIGHT AHI|1.86|AHI|Himawari-9', keys);
    const polar = colourFor('firms|VIIRS_SNPP_SP|2|VIIRS|Suomi-NPP', keys);
    expect(geo).not.toBe(polar);
    const red = (hex) => parseInt(hex.slice(1, 3), 16);
    const blue = (hex) => parseInt(hex.slice(5, 7), 16);
    expect(red(geo)).toBeGreaterThan(blue(geo));
    expect(blue(polar)).toBeGreaterThan(red(polar));
  });

  it('reserves the fire accent for a live BRIGHT run', () => {
    expect(colourFor('bright|BRIGHT AHI|2.0|AHI|Himawari-9', keys)).toBe('#ff6b35');
  });

  it('always returns a colour, even for a key it has never seen', () => {
    expect(colourFor('mystery', [])).toMatch(/^#[0-9a-f]{6}$/i);
  });
});
