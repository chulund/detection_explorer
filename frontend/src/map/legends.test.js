import { describe, expect, it } from 'vitest';
import { LEGENDS, detectionLegend, legendFor } from './legends.js';
import { availableContextLayers } from './contextLayers.js';
import { buildTaxonomy } from './taxonomy.js';
import { colourMap } from './palette.js';

const CSS_COLOUR = /^(#[0-9a-f]{3,8}|rgba?\(|transparent$)/i;

describe('coverage', () => {
  // A layer a user can switch on and then cannot interpret is the gap this closes.
  it('every contextual layer on offer has a legend', () => {
    const layers = availableContextLayers('a-key-so-weather-is-offered');
    for (const layer of layers) {
      expect(legendFor(layer.id), `no legend for ${layer.id}`).toBeTruthy();
    }
  });

  // The other direction matters too: a legend with no layer is a card that can never
  // appear, and a rename would leave one behind silently.
  it('every legend belongs to a layer that exists', () => {
    const ids = new Set(availableContextLayers('key').map((l) => l.id));
    for (const id of Object.keys(LEGENDS)) expect(ids.has(id), `orphan ${id}`).toBe(true);
  });

  it('returns nothing rather than guessing for an unknown layer', () => {
    expect(legendFor('not-a-layer')).toBeNull();
  });
});

describe('the ramps are drawable', () => {
  for (const [id, legend] of Object.entries(LEGENDS)) {
    it(id, () => {
      expect(['gradient', 'classes']).toContain(legend.kind);
      if (legend.kind === 'gradient') {
        expect(legend.stops.length).toBeGreaterThan(1);
        for (const stop of legend.stops) expect(stop).toMatch(CSS_COLOUR);
        expect(legend.ticks.length).toBeGreaterThan(1);
      } else {
        expect(legend.items.length).toBeGreaterThan(0);
        for (const item of legend.items) {
          expect(item.colour).toMatch(CSS_COLOUR);
          expect(item.label).toBeTruthy();
        }
      }
      expect(legend.note).toBeTruthy();   // every scale credits its source
    });
  }
});

describe('specific scales', () => {
  it('reads fuel moisture dry to wet, not the other way round', () => {
    expect(LEGENDS.fmc.stops[0]).toBe('#d00032');            // dry
    expect(LEGENDS.fmc.stops.at(-1)).toBe('#2580b8');        // wet
  });

  // The reference declares a three-class fractional cover array and renders a nine-class
  // one. Copying the short version would have described a picture that is not on screen.
  it('uses the nine-class fractional cover the service actually renders', () => {
    expect(LEGENDS.fractional_cover.items).toHaveLength(9);
  });

  it('distinguishes a wildfire from a prescribed burn by outline, as the map does', () => {
    const [wildfire, prescribed] = LEGENDS.fire_history.items;
    expect(wildfire.border).toContain('solid');
    expect(prescribed.border).toContain('dashed');
  });
});

describe('detectionLegend', () => {
  const feature = (props) => ({
    properties: {
      source: 'dea', product: 'AFIMG', algorithm: 'AFIMG', algorithm_version: '6',
      instrument: 'VIIRS', platform: 'Suomi-NPP', ...props,
    },
  });
  const features = [
    feature({}),
    feature({ product: 'BRIGHT AHI', algorithm: 'BRIGHT AHI', algorithm_version: '1.86',
              instrument: 'AHI', platform: 'Himawari-9' }),
  ];
  const groups = buildTaxonomy(features, {});
  const colours = colourMap(groups.flatMap((g) => g.rows.map((r) => r.key)));
  const legend = detectionLegend(groups, colours);

  it('leads with geostationary, then polar', () => {
    expect(legend.map((g) => g.orbit)).toEqual(['geostationary', 'polar-orbiting']);
  });

  it('labels each entry with its algorithm and version', () => {
    const geo = legend.find((g) => g.orbit === 'geostationary');
    expect(geo.items[0].label).toBe('BRIGHT AHI 1.86');
    expect(geo.items[0].hint).toContain('Himawari-9');
    expect(geo.items[0].hint).toContain('2 km');
  });

  // The swatch and the polygon have to be the same colour or the key is useless.
  it('takes its swatch from the same colour map the map paints from', () => {
    const polar = legend.find((g) => g.orbit === 'polar-orbiting');
    const key = groups.flatMap((g) => g.rows).find((r) => r.instrument === 'VIIRS').key;
    expect(polar.items[0].colour).toBe(colours[key]);
  });

  it('omits a product that returned nothing, because there is no colour on screen', () => {
    const withEmpty = buildTaxonomy([], {
      firms: { available: true, products_queried: ['MODIS_SP'] },
    });
    expect(detectionLegend(withEmpty, {})).toEqual([]);
  });

  it('survives an empty scene', () => {
    expect(detectionLegend(undefined, undefined)).toEqual([]);
  });
});
