import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

/**
 * Does the interface render at all?
 *
 * The unit tests cover the logic and the style validator covers the paint, and between
 * them they would still pass with a component that throws on its first render. A build
 * would pass too: it type-checks nothing and executes nothing. This renders the real tree
 * once, which is the cheapest way to catch a missing export, a bad prop shape or a crash
 * in a panel.
 *
 * Effects do not run under server rendering, so no map is constructed and no request is
 * made. That is the point: it exercises everything up to the point where a browser is
 * genuinely required.
 */

// MapLibre reaches for browser globals when it loads, and it is not what is under test.
vi.mock('maplibre-gl', () => {
  class Fake { constructor() {} addControl() {} on() {} remove() {} }
  return {
    default: {
      Map: Fake, Popup: Fake, NavigationControl: Fake, ScaleControl: Fake,
      FullscreenControl: Fake, LngLatBounds: class { extend() {} },
    },
  };
});

const { default: App } = await import('./App.jsx');
const { default: LayerPanel } = await import('./panels/LayerPanel.jsx');
const { default: DetailCard } = await import('./panels/DetailCard.jsx');
const { default: LegendDock } = await import('./panels/LegendDock.jsx');
const { default: AboutSheet } = await import('./panels/AboutSheet.jsx');
const { buildTaxonomy, taxonomyKeys } = await import('./map/taxonomy.js');
const { colourMap } = await import('./map/palette.js');
const { availableContextLayers, groupedContextLayers } =
  await import('./map/contextLayers.js');

const feature = (props) => ({
  type: 'Feature',
  geometry: { type: 'Point', coordinates: [148, -32] },
  properties: {
    id: `dea:${Math.random()}`, source: 'dea', product: 'AFIMG', algorithm: 'AFIMG',
    algorithm_version: '6', instrument: 'VIIRS', platform: 'Suomi-NPP',
    lat: -32, lon: 148, detected_at: '2026-04-09T04:29:00Z',
    frp_mw: 6.5, brightness_k: 334.4, brightness_channel: 'VIIRS I4 3.74 um',
    ...props,
  },
});

const SOURCES = {
  dea: { available: true, count: 1, products_queried: ['*'] },
  firms: { available: true, count: 0, products_queried: ['MODIS_SP', 'VIIRS_SNPP_SP'] },
};

const taxonomy = buildTaxonomy([feature({})], SOURCES);
const colours = colourMap(taxonomyKeys(taxonomy));

describe('the interface renders', () => {
  it('renders the whole app without throwing', () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain('Detection Explorer');
    expect(html).toContain('class="map"');
  });

  it('renders the layer panel with a real taxonomy', () => {
    const html = renderToStaticMarkup(
      <LayerPanel
        taxonomy={taxonomy}
        colours={colours}
        enabledKeys={new Set(taxonomyKeys(taxonomy))}
        onToggleKey={() => {}}
        onToggleGroup={() => {}}
        renderMode="auto"
        onRenderMode={() => {}}
        basemap="dark"
        onBasemap={() => {}}
        contextGroups={groupedContextLayers(null)}
        contextEnabled={{}}
        onContextToggle={() => {}}
        weatherConfigured={false}
      />,
    );
    expect(html).toContain('AFIMG');
    expect(html).toContain('Suomi-NPP');
    expect(html).toContain('Footprints');       // the render-mode control
    expect(html).toContain('Dark');             // the basemap picker
  });

  // The row that would otherwise vanish. It is the whole reason `products_queried` exists.
  it('shows a queried product that returned nothing', () => {
    const html = renderToStaticMarkup(
      <LayerPanel
        taxonomy={taxonomy} colours={colours} enabledKeys={new Set()}
        onToggleKey={() => {}} onToggleGroup={() => {}}
        renderMode="auto" onRenderMode={() => {}}
        basemap="dark" onBasemap={() => {}}
        contextGroups={[]} contextEnabled={{}} onContextToggle={() => {}}
        weatherConfigured
      />,
    );
    expect(html).toContain('MODIS_SP');
    expect(html).toContain('none in window');
  });

  it('renders the detail card empty and populated', () => {
    expect(renderToStaticMarkup(<DetailCard detection={null} />))
      .toContain('Select a detection');
    const html = renderToStaticMarkup(
      <DetailCard detection={feature({ footprint_side: 'ambiguous',
                                       footprint_status: 'experimental',
                                       footprint_kind: 'satellite_pixel_footprint' }).properties} />,
    );
    expect(html).toContain('334.4 K');
    expect(html).toContain('2 candidates');
    expect(html).toContain('experimental');
  });

  it('renders a legend dock for the active layers only', () => {
    const layers = availableContextLayers('key');
    const html = renderToStaticMarkup(
      <LegendDock taxonomy={taxonomy} colours={colours}
                  contextLayers={layers} contextEnabled={{ fmc: true }} />,
    );
    expect(html).toContain('Fuel moisture content');
    expect(html).not.toContain('Land cover');      // switched off, so no card
  });

  it('renders the about sheet with the caveats intact', () => {
    const html = renderToStaticMarkup(
      <AboutSheet open onClose={() => {}}
                  scene={{ description: 'Six BRIGHT frames.', window: {
                    start: 'a', end: 'b', half_open: true } }}
                  sources={SOURCES} />,
    );
    expect(html).toContain('892');     // the measured orientation discrepancy
    expect(html).toContain('476');     // the measured corner separation
    expect(html).toContain('Six BRIGHT frames.');
  });

  it('renders nothing for a closed sheet', () => {
    expect(renderToStaticMarkup(<AboutSheet open={false} onClose={() => {}} />)).toBe('');
  });
});
