import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { dotsFrom } from './features.js';
import {
  DETECTION_LAYERS, DETECTION_SOURCES, FIRST_DETECTION_LAYER, SELECTABLE_LAYERS,
} from './layers.js';

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

function syncContextLayers(map, layers, enabled) {
  for (const layer of layers) {
    const sourceId = `ctx-${layer.id}`;
    const layerId = `ctx-${layer.id}-raster`;
    const wanted = !!enabled[layer.id];

    if (wanted && !map.getSource(sourceId)) {
      map.addSource(sourceId, {
        type: 'raster',
        tiles: [layer.url],
        tileSize: 256,
        attribution: layer.attribution,
      });
      map.addLayer({
        id: layerId,
        type: 'raster',
        source: sourceId,
        paint: { 'raster-opacity': layer.opacity ?? 0.5 },
      }, map.getLayer(FIRST_DETECTION_LAYER) ? FIRST_DETECTION_LAYER : undefined);
    }

    if (map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, 'visibility', wanted ? 'visible' : 'none');
    }
  }
}

export default function MapView({ ahi, polar, points, onSelect, dimmedIds, fitKey,
                                  contextLayers = [], contextEnabled = {} }) {
  const container = useRef(null);
  const map = useRef(null);
  const ready = useRef(false);
  const fitted = useRef(null);

  // `ready` has to exist twice, and the reason is a bug this cost an afternoon.
  //
  // The ref is what the map's own callbacks read, because they fire outside React's
  // render cycle. But a ref changing does not re-run an effect, so when the layers were
  // finally created the data effect had already bailed out and never ran again: React
  // held 505 detections while the map held none.
  //
  // The state mirror gives the data effect something to depend on, and `latest` gives the
  // layer-creation callback the current props rather than the empty ones it closed over
  // at mount.
  const [layersReady, setLayersReady] = useState(false);
  const latest = useRef(null);
  latest.current = { ahi, polar, points, dimmedIds, contextLayers, contextEnabled, fitKey };

  // Fit once per scene, on the first update that has anything to frame. Data arrives in
  // more than one instalment — a run adds AHI footprints long after retrieval has
  // settled — and refitting then would yank the view out from under whoever is reading
  // it. Reads refs only, so the mount effect can safely close over the first instance.
  const maybeFit = (data) => {
    if (!map.current || fitted.current === data.fitKey) return;
    if (fitToData(map.current, data)) fitted.current = data.fitKey;
  };

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

      for (const id of DETECTION_SOURCES) {
        map.current.addSource(id, { type: 'geojson', data: EMPTY });
      }
      for (const layer of DETECTION_LAYERS) {
        map.current.addLayer(layer);
      }

      for (const layer of SELECTABLE_LAYERS) {
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
      setLayersReady(true);
      const now = latest.current;
      setData(map.current, now, now.dimmedIds);
      maybeFit(now);
      syncContextLayers(map.current, now.contextLayers ?? [], now.contextEnabled ?? {});
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
    if (!layersReady || !map.current) return;
    setData(map.current, { ahi, polar, points }, dimmedIds);
    maybeFit({ ahi, polar, points, fitKey });
  }, [layersReady, ahi, polar, points, dimmedIds, fitKey]);

  // Contextual layers are added on first use rather than up front, so a catalogue of
  // seven WMS services costs nothing until someone actually asks for one.
  useEffect(() => {
    if (!layersReady || !map.current) return;
    syncContextLayers(map.current, contextLayers, contextEnabled);
  }, [layersReady, contextLayers, contextEnabled]);

  return <div className="map" ref={container} />;
}

function setData(map, collections, dimmedIds) {
  const dim = dimmedIds ?? new Set();
  for (const [id, collection] of Object.entries(collections)) {
    const source = map.getSource(id);
    if (!source) continue;
    const marked = {
      type: 'FeatureCollection',
      features: (collection?.features ?? []).map((feature) => ({
        ...feature,
        properties: { ...feature.properties, dimmed: dim.has(feature.properties?.id) },
      })),
    };
    source.setData(marked);

    // The footprint layers each carry a marker source alongside them. A circle layer over
    // a polygon would draw one circle per vertex, so the markers are their own points.
    const dots = map.getSource(`${id}-dots`);
    if (dots) dots.setData(dotsFrom(marked));
  }
}

/**
 * Open on the detections rather than on a fixed rectangle.
 *
 * The state-wide opening view was chosen before there was any data to look at, and it puts
 * every footprint below the size of a screen pixel. Framing the detections is a better
 * default and costs nothing: the user can still zoom out to the state.
 *
 * Footprints decide the frame, and points are used only when there are no footprints.
 * DEA's 1785 hotspots are scattered across the whole state, so including them would fit
 * back to roughly the rectangle this is replacing.
 */
function fitToData(map, { ahi, polar, points }) {
  const preferred = [...(ahi?.features ?? []), ...(polar?.features ?? [])];
  const features = preferred.length ? preferred : (points?.features ?? []);
  if (!features.length) return false;

  const bounds = new maplibregl.LngLatBounds();
  let extended = 0;
  for (const feature of features) {
    const lon = Number(feature.properties?.lon);
    const lat = Number(feature.properties?.lat);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    bounds.extend([lon, lat]);
    extended += 1;
  }
  if (!extended) return false;

  map.fitBounds(bounds, { padding: 60, maxZoom: 11, duration: 0 });
  return true;
}
