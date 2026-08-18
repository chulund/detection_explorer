import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { collection, dotsFrom } from './features.js';
import {
  DETECTION_SOURCES, FIRST_DETECTION_LAYER, SELECTABLE_LAYERS, detectionLayers, filterFor,
} from './layers.js';
import { DEFAULT_BASEMAP, basemapById, basemapSource } from './basemaps.js';
import { renderPopup } from './popup.js';

/**
 * The map.
 *
 * MapLibre rather than Mapbox, so no access token is needed in a repository intended to
 * become public. That decision is also what makes the basemap picker simple: the map
 * starts from a local style with no sources and every basemap is an ordinary raster
 * source, so switching one is a source swap rather than `setStyle`. The reference
 * frontend, which does call `setStyle`, needs a whole re-hydration hook to put its layers
 * back afterwards. Nothing here does.
 *
 * Every detection shares one source. Colour, sensor class and staleness travel on the
 * feature, so twelve algorithm and sensor pairings cost six layers, and switching one on
 * is a filter update.
 */

const NSW = { center: [147.5, -32.5], zoom: 5.2 };

const EMPTY = { type: 'FeatureCollection', features: [] };

/**
 * The map starts with a style that needs no network, then adds a basemap on top.
 *
 * This ordering is deliberate and was arrived at the hard way. The obvious approach —
 * point MapLibre at a hosted style — makes the detections hostage to a third party. A
 * hosted vector style pulls in a sprite sheet, a glyph server and worker-side tile
 * parsing, and if any of those stalls the style never reaches a loaded state.
 *
 * Starting local inverts the dependency. This style has no sources, so it loads
 * immediately and the detection layers can be added straight away. The basemap is then
 * attached as an ordinary source; if its tiles never arrive, the map shows detections on
 * a plain ground rather than showing nothing at all.
 */
const BASE_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#0e1116' } }],
};

const BASEMAP_LAYER = 'basemap';

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
        bounds: layer.bounds,
        attribution: layer.attribution,
      });
      map.addLayer({
        id: layerId,
        type: 'raster',
        source: sourceId,
        paint: { 'raster-opacity': layer.opacity ?? 0.5, ...(layer.paint ?? {}) },
      }, map.getLayer(FIRST_DETECTION_LAYER) ? FIRST_DETECTION_LAYER : undefined);
    }

    if (map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, 'visibility', wanted ? 'visible' : 'none');
    }
  }
}

/** A plain button in the control column, for the things MapLibre does not ship. */
class ButtonControl {
  constructor(label, title, onClick) {
    Object.assign(this, { label, title, onClick });
  }

  onAdd() {
    this.container = document.createElement('div');
    this.container.className = 'maplibregl-ctrl maplibregl-ctrl-group';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'map-btn';
    button.title = this.title;
    button.setAttribute('aria-label', this.title);
    button.textContent = this.label;
    button.addEventListener('click', () => this.onClick());
    this.container.appendChild(button);
    return this.container;
  }

  onRemove() {
    this.container?.remove();
    this.container = null;
  }
}

export default function MapView({
  features, enabledKeys, renderMode = 'auto', basemap = DEFAULT_BASEMAP,
  selected, onSelect, fitKey, contextLayers = [], contextEnabled = {},
}) {
  const container = useRef(null);
  const map = useRef(null);
  const ready = useRef(false);
  const fitted = useRef(null);
  const popup = useRef(null);
  const appliedBasemap = useRef(null);

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
  latest.current = { features, enabledKeys, renderMode, basemap, contextLayers,
                     contextEnabled, fitKey };

  // Fit once per scene, on the first update that has anything to frame. Data arrives in
  // more than one instalment — a run adds AHI footprints long after retrieval has
  // settled — and refitting then would yank the view out from under whoever is reading it.
  const maybeFit = (data) => {
    if (!map.current || fitted.current === data.fitKey) return;
    if (fitToData(map.current, data.features)) fitted.current = data.fitKey;
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

    // The compass is what resets bearing to north, so it is shown rather than hidden.
    map.current.addControl(new maplibregl.NavigationControl({ showCompass: true }));
    map.current.addControl(new ButtonControl('⤢', 'Zoom to all detections', () => {
      fitToData(map.current, latest.current.features);
    }));
    map.current.addControl(new maplibregl.FullscreenControl());
    map.current.addControl(new maplibregl.ScaleControl({ unit: 'metric' }));

    popup.current = new maplibregl.Popup({
      closeButton: true, closeOnClick: false, offset: 12, maxWidth: '320px',
    });

    // Add our layers as soon as a style exists, rather than waiting for 'load'.
    //
    // 'load' fires only once every source has finished loading, which includes the
    // basemap's tiles. If those are slow or blocked, 'load' never fires and the
    // detections never appear — the data this interface exists to show would be hidden
    // by an unrelated third-party dependency. 'styledata' fires as soon as the style is
    // parsed, which is all that is needed to add sources.
    const addOurLayers = () => {
      if (ready.current || !map.current) return;

      for (const id of DETECTION_SOURCES) {
        map.current.addSource(id, { type: 'geojson', data: EMPTY });
      }
      for (const layer of detectionLayers(latest.current.renderMode)) {
        map.current.addLayer(layer);
        const filter = filterFor(layer.id, latest.current.renderMode,
                                 latest.current.enabledKeys);
        if (filter) map.current.setFilter(layer.id, filter);
      }

      for (const layer of SELECTABLE_LAYERS) {
        map.current.on('click', layer, (event) => {
          const properties = event.features?.[0]?.properties ?? null;
          onSelect?.(properties);
          showPopup(map.current, popup.current, event.lngLat, properties);
        });
        map.current.on('mouseenter', layer, () => {
          map.current.getCanvas().style.cursor = 'pointer';
        });
        map.current.on('mouseleave', layer, () => {
          map.current.getCanvas().style.cursor = '';
        });
      }

      // Clicking bare ground clears the selection, which is the only way back out of it.
      map.current.on('click', (event) => {
        const hits = map.current.queryRenderedFeatures(event.point, {
          layers: SELECTABLE_LAYERS.filter((id) => map.current.getLayer(id)),
        });
        if (!hits.length) { onSelect?.(null); popup.current?.remove(); }
      });

      ready.current = true;
      setLayersReady(true);
      const now = latest.current;
      applyBasemap(map.current, now.basemap, appliedBasemap);
      setData(map.current, now.features);
      maybeFit(now);
      syncContextLayers(map.current, now.contextLayers ?? [], now.contextEnabled ?? {});
    };

    if (map.current.isStyleLoaded()) addOurLayers();
    else map.current.on('styledata', addOurLayers);

    // Surface style or tile failures instead of leaving a silently blank canvas.
    map.current.on('error', (event) => {
      console.error('[map]', event?.error?.message ?? event);
    });
    if (import.meta.env.DEV) window.__map = map.current;

    // The panels above the map settle after the first render, so the container is a
    // different size by the time data arrives than it was at construction. Without this
    // the canvas keeps its initial dimensions and the map appears blank.
    const observer = new ResizeObserver(() => map.current?.resize());
    observer.observe(container.current);

    return () => {
      observer.disconnect();
      popup.current?.remove();
      map.current?.remove();
      map.current = null;
      ready.current = false;
    };
  }, []);

  useEffect(() => {
    if (!layersReady || !map.current) return;
    setData(map.current, features);
    maybeFit({ features, fitKey });
  }, [layersReady, features, fitKey]);

  // A mode change repaints and refilters. The layer ids are the same in every mode, so
  // nothing is added or removed and the map does not flicker.
  useEffect(() => {
    if (!layersReady || !map.current) return;
    for (const layer of detectionLayers(renderMode)) {
      if (!map.current.getLayer(layer.id)) continue;
      for (const [property, value] of Object.entries(layer.paint)) {
        map.current.setPaintProperty(layer.id, property, value);
      }
      const filter = filterFor(layer.id, renderMode, enabledKeys);
      if (filter) map.current.setFilter(layer.id, filter);
    }
  }, [layersReady, renderMode, enabledKeys]);

  useEffect(() => {
    if (!layersReady || !map.current) return;
    applyBasemap(map.current, basemap, appliedBasemap);
  }, [layersReady, basemap]);

  useEffect(() => {
    if (!layersReady || !map.current) return;
    const one = selected
      ? (features ?? []).filter((f) => f.properties?.id === selected.id)
      : [];
    map.current.getSource('selection')?.setData(collection(one));
    map.current.getSource('selection-dot')?.setData(dotsFrom(one));
    if (!selected) popup.current?.remove();
  }, [layersReady, selected, features]);

  // Contextual layers are added on first use rather than up front, so a catalogue of
  // eleven services costs nothing until someone actually asks for one.
  useEffect(() => {
    if (!layersReady || !map.current) return;
    syncContextLayers(map.current, contextLayers, contextEnabled);
  }, [layersReady, contextLayers, contextEnabled]);

  return <div className="map" ref={container} />;
}

function setData(map, features) {
  map.getSource('detections')?.setData(collection(features));
  map.getSource('detection-dots')?.setData(dotsFrom(features));
}

/**
 * Swap the basemap without touching the style.
 *
 * Removed and re-added below the first detection layer, so detections always draw on top
 * whichever ground is underneath them.
 */
function applyBasemap(map, id, applied) {
  if (applied.current === id) return;
  const basemap = basemapById(id);
  if (map.getLayer(BASEMAP_LAYER)) map.removeLayer(BASEMAP_LAYER);
  if (map.getSource(BASEMAP_LAYER)) map.removeSource(BASEMAP_LAYER);
  map.addSource(BASEMAP_LAYER, basemapSource(basemap));
  map.addLayer({
    id: BASEMAP_LAYER,
    type: 'raster',
    source: BASEMAP_LAYER,
    paint: { 'raster-opacity': basemap.opacity },
  }, map.getLayer(FIRST_DETECTION_LAYER) ? FIRST_DETECTION_LAYER : undefined);
  applied.current = id;
}

function showPopup(map, popup, lngLat, properties) {
  if (!properties) { popup.remove(); return; }
  const content = renderPopup(document, properties);
  if (!content) { popup.remove(); return; }
  popup.setLngLat(lngLat).setDOMContent(content).addTo(map);
}

/**
 * Frame the detections rather than a fixed rectangle.
 *
 * The state-wide opening view was chosen before there was any data to look at, and it
 * puts every footprint below the size of a screen pixel. Footprints decide the frame and
 * points are used only when there are none: DEA's hotspots are scattered across the whole
 * state, so including them would fit back to roughly the rectangle this replaces.
 */
export function fitToData(map, features) {
  if (!map || !features?.length) return false;
  const withGeometry = features.filter(
    (f) => f.geometry?.type === 'Polygon' || f.geometry?.type === 'MultiPolygon');
  const chosen = withGeometry.length ? withGeometry : features;

  const bounds = new maplibregl.LngLatBounds();
  let extended = 0;
  for (const feature of chosen) {
    const lon = Number(feature.properties?.lon);
    const lat = Number(feature.properties?.lat);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    bounds.extend([lon, lat]);
    extended += 1;
  }
  if (!extended) return false;

  map.fitBounds(bounds, { padding: 70, maxZoom: 11, duration: 0 });
  return true;
}
