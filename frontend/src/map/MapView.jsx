import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

/**
 * The map.
 *
 * MapLibre rather than Mapbox, so no access token is needed in a repository intended to
 * become public. The basemap is Carto's positron style, which is keyless and was checked
 * before being relied on.
 *
 * Two detection layers, drawn at true scale, which is the whole argument of this interface:
 * an AHI pixel is roughly 2 km across and a VIIRS pixel roughly 375 m, and seeing them side
 * by side says more about the cadence-resolution trade than any caption could.
 *
 * Polar footprints arrive as a MultiPolygon of two candidates, because a FIRMS row cannot
 * say which side of the ground track the pixel lay on. Both are drawn, and they share one
 * style, because they are one detection's uncertainty rather than two detections.
 */

const NSW = { center: [147.5, -32.5], zoom: 5.2 };

const EMPTY = { type: 'FeatureCollection', features: [] };

/**
 * The map starts with a style that needs no network, then adds a basemap on top.
 *
 * This ordering is deliberate and was arrived at the hard way. The obvious approach —
 * point MapLibre at a hosted style — makes the detections hostage to a third party. A
 * hosted vector style pulls in a sprite sheet, a glyph server and worker-side tile
 * parsing, and if any of those stalls the style never reaches a loaded state. An earlier
 * attempt to paper over that with a timeout was worse still: it called `setStyle` while
 * the first style was mid-flight, and MapLibre discarded both ("Unable to perform style
 * diff: Style is not done loading").
 *
 * Starting local inverts the dependency. This style has no sources, so it loads
 * immediately and the detection layers can be added straight away. The basemap is then
 * attached as an ordinary source; if its tiles never arrive, the map shows detections on
 * a plain ground rather than showing nothing at all. For a deliverable that runs on
 * localhost, possibly with no route out, that is the right way round.
 */
const BASE_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#eef1f5' } }],
};

/** Raster rather than vector: plain images, no sprite, no glyphs, no worker parsing. */
const BASEMAP_SOURCE = {
  type: 'raster',
  tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
  tileSize: 256,
  maxzoom: 19,
  attribution: '© OpenStreetMap contributors',
};

export default function MapView({ ahi, polar, points, onSelect, dimmedIds }) {
  const container = useRef(null);
  const map = useRef(null);
  const ready = useRef(false);

  useEffect(() => {
    if (map.current) return;
    map.current = new maplibregl.Map({
      container: container.current,
      style: BASE_STYLE,
      center: NSW.center,
      zoom: NSW.zoom,
      attributionControl: { compact: true },
    });
    map.current.addControl(new maplibregl.NavigationControl({ showCompass: false }));
    map.current.addControl(new maplibregl.ScaleControl({ unit: 'metric' }));

    // Add our layers as soon as a style exists, rather than waiting for 'load'.
    //
    // 'load' fires only once every source has finished loading, which includes the
    // external basemap's vector tiles. If those are slow or blocked, 'load' never
    // fires and the detections never appear — the data this interface exists to show
    // would be hidden by an unrelated third-party dependency. 'styledata' fires as
    // soon as the style is parsed, which is all that is needed to add sources.
    const addOurLayers = () => {
      if (ready.current || !map.current) return;

      // Basemap first, so every detection layer draws above it. Added as a source on an
      // already-loaded style rather than being the style, so failure is survivable.
      if (!map.current.getSource('basemap')) {
        map.current.addSource('basemap', BASEMAP_SOURCE);
        map.current.addLayer({
          id: 'basemap', type: 'raster', source: 'basemap',
          paint: { 'raster-opacity': 0.55 },
        });
      }

      for (const id of ['ahi', 'polar', 'points']) {
        map.current.addSource(id, { type: 'geojson', data: EMPTY });
      }

      // AHI: 2 km pixels, warm fill.
      map.current.addLayer({
        id: 'ahi-fill', type: 'fill', source: 'ahi',
        paint: { 'fill-color': '#d95f02', 'fill-opacity': 0.35 },
      });
      map.current.addLayer({
        id: 'ahi-line', type: 'line', source: 'ahi',
        paint: { 'line-color': '#d95f02', 'line-width': 1 },
      });

      // Polar: 375 m pixels, cool fill, dimmed when the pass is stale.
      map.current.addLayer({
        id: 'polar-fill', type: 'fill', source: 'polar',
        paint: {
          'fill-color': '#1b6ca8',
          'fill-opacity': ['case', ['get', 'dimmed'], 0.12, 0.45],
        },
      });
      map.current.addLayer({
        id: 'polar-line', type: 'line', source: 'polar',
        paint: {
          'line-color': '#1b6ca8',
          'line-width': ['case', ['get', 'dimmed'], 0.6, 1.2],
          'line-dasharray': [2, 1], // dashed: the position is one of two candidates
        },
      });

      // Sources with no recoverable geometry, drawn honestly as points.
      map.current.addLayer({
        id: 'points-circle', type: 'circle', source: 'points',
        paint: {
          'circle-radius': 3.5,
          'circle-color': '#6a3d9a',
          'circle-stroke-width': 1,
          'circle-stroke-color': '#ffffff',
        },
      });

      for (const layer of ['ahi-fill', 'polar-fill', 'points-circle']) {
        map.current.on('click', layer, (event) => {
          onSelect?.(event.features?.[0]?.properties ?? null);
        });
        map.current.on('mouseenter', layer, () => {
          map.current.getCanvas().style.cursor = 'pointer';
        });
        map.current.on('mouseleave', layer, () => {
          map.current.getCanvas().style.cursor = '';
        });
      }
      ready.current = true;
      setData(map.current, { ahi, polar, points }, dimmedIds);
    };

    // `styledata` rather than `load`: `load` waits for every source to finish, which
    // includes basemap tiles that may never arrive. `styledata` fires as soon as the
    // style exists, which is all that is needed to add sources and layers.
    if (map.current.isStyleLoaded()) addOurLayers();
    else map.current.on('styledata', addOurLayers);

    // Surface style or tile failures instead of leaving a silently blank canvas.
    map.current.on('error', (event) => {
      console.error('[map]', event?.error?.message ?? event);
    });
    if (import.meta.env.DEV) window.__map = map.current;

    // The panels above the map settle after the first render, so the container is a
    // different size by the time data arrives than it was at construction. Without
    // this the canvas keeps its initial dimensions and the map appears blank.
    const observer = new ResizeObserver(() => map.current?.resize());
    observer.observe(container.current);

    return () => {
      observer.disconnect();
      map.current?.remove();
      map.current = null;
      ready.current = false;
    };
  }, []);

  useEffect(() => {
    if (!ready.current || !map.current) return;
    setData(map.current, { ahi, polar, points }, dimmedIds);
  }, [ahi, polar, points, dimmedIds]);

  return <div className="map" ref={container} />;
}

function setData(map, collections, dimmedIds) {
  const dim = dimmedIds ?? new Set();
  for (const [id, collection] of Object.entries(collections)) {
    const source = map.getSource(id);
    if (!source) continue;
    source.setData({
      type: 'FeatureCollection',
      features: (collection?.features ?? []).map((feature) => ({
        ...feature,
        properties: { ...feature.properties, dimmed: dim.has(feature.properties?.id) },
      })),
    });
  }
}
