import { useCallback, useEffect, useMemo, useState } from 'react';
import { exportUrl, getDetections, getScenes, getStatus } from './api.js';
import MapView from './map/MapView.jsx';
import { DEFAULT_BASEMAP } from './map/basemaps.js';
import { availableContextLayers, groupedContextLayers } from './map/contextLayers.js';
import { brightFeatures, decorateFeatures, isoFromStamp } from './map/features.js';
import { colourMap } from './map/palette.js';
import { buildTaxonomy, taxonomyKeys } from './map/taxonomy.js';
import AboutSheet from './panels/AboutSheet.jsx';
import DetailCard from './panels/DetailCard.jsx';
import LayerPanel from './panels/LayerPanel.jsx';
import LegendDock from './panels/LegendDock.jsx';
import ProvenanceStrip from './panels/ProvenanceStrip.jsx';
import RunPanel from './panels/RunPanel.jsx';
import { Chip, Collapsible } from './panels/ui.jsx';
import { formatAge, overpassMarkers, visibleOverpasses } from './time/overpass.js';

/**
 * Header, sidebar, map, legend dock, timeline.
 *
 * Switching scenes clears every layer before loading the new one, so no record from one
 * epoch can survive into another. That is enforced on the server too; doing it here as
 * well means a slow response cannot leave April detections on screen under a live label.
 */

export default function App() {
  const [scenes, setScenes] = useState([]);
  const [sceneId, setSceneId] = useState('april-9-demo');
  const [payload, setPayload] = useState(null);
  const [status, setStatus] = useState(null);
  const [selected, setSelected] = useState(null);
  const [enabledKeys, setEnabledKeys] = useState(null);   // null: nothing chosen yet
  const [renderMode, setRenderMode] = useState('auto');
  const [basemap, setBasemap] = useState(DEFAULT_BASEMAP);
  const [cursor, setCursor] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [runFrames, setRunFrames] = useState([]);
  const [contextEnabled, setContextEnabled] = useState({});
  const [about, setAbout] = useState(false);
  const [detailOpen, setDetailOpen] = useState(true);
  const [runOpen, setRunOpen] = useState(true);

  // The weather key is supplied to the browser by the API rather than baked into the
  // bundle, so a build can be shared without carrying anyone's credentials.
  const weatherKey = status?.context?.weather?.key ?? null;
  const brightVersion = status?.providers?.bright?.algorithm_version ?? '2.0';
  const contextLayers = useMemo(() => availableContextLayers(weatherKey), [weatherKey]);
  const contextGroups = useMemo(() => groupedContextLayers(weatherKey), [weatherKey]);
  const toggleContext = (id, on) => setContextEnabled((prev) => ({ ...prev, [id]: on }));

  useEffect(() => {
    getScenes().then((b) => setScenes(b.scenes)).catch((e) => setError(e.message));
    getStatus().then(setStatus).catch(() => {});
  }, []);

  useEffect(() => {
    // Clear before fetching: nothing from the previous epoch may linger on screen.
    setPayload(null);
    setSelected(null);
    setEnabledKeys(null);
    setLoading(true);
    setError(null);
    getDetections(sceneId)
      .then((body) => {
        setPayload(body);
        setCursor(body.scene?.window?.end ?? null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [sceneId]);

  const scene = useMemo(
    () => scenes.find((s) => s.id === sceneId) ?? payload?.scene ?? null,
    [scenes, sceneId, payload],
  );

  // Retrieved records, plus whatever a run has recomputed. BRIGHT output arrives from a
  // run rather than from retrieval, carrying the exact pixel polygons the backend joined
  // from the sensor grid.
  const allFeatures = useMemo(() => [
    ...(payload?.features ?? []),
    ...brightFeatures(runFrames, { algorithmVersion: brightVersion }),
  ], [payload, runFrames, brightVersion]);

  const taxonomy = useMemo(
    () => buildTaxonomy(allFeatures, payload?.sources),
    [allFeatures, payload],
  );
  const colours = useMemo(() => colourMap(taxonomyKeys(taxonomy)), [taxonomy]);

  // Everything with records is on by default. A row that returned nothing stays off,
  // because switching it on would do nothing and look broken.
  const effectiveKeys = useMemo(() => {
    if (enabledKeys) return enabledKeys;
    return new Set(taxonomy.flatMap(
      (group) => group.rows.filter((row) => row.count > 0).map((row) => row.key)));
  }, [enabledKeys, taxonomy]);

  // Which polar passes are visible at the cursor, and which are stale.
  const overpassState = useMemo(() => {
    if (!cursor) return { visible: [], dimmed: new Set() };
    const polar = allFeatures
      .filter((f) => f.properties?.footprint_method === 'polar_reconstructed')
      .map((f) => f.properties);
    const visible = visibleOverpasses(polar, cursor);
    return {
      visible,
      keep: new Set(visible.map((v) => v.id)),
      dimmed: new Set(visible.filter((v) => v.state === 'dimmed').map((v) => v.id)),
    };
  }, [allFeatures, cursor]);

  /**
   * What the map is given: enabled layers only, past overpasses dropped, and every
   * feature tagged with the colour and sensor class its layer paints from.
   */
  const shown = useMemo(() => {
    const kept = allFeatures.filter((feature) => {
      const properties = feature.properties ?? {};
      if (properties.footprint_method === 'polar_reconstructed' && overpassState.keep) {
        if (!overpassState.keep.has(properties.id)) return false;
      }
      return true;
    });
    return decorateFeatures(kept, { colours, dimmedIds: overpassState.dimmed });
  }, [allFeatures, colours, overpassState]);

  const markers = useMemo(() => overpassMarkers(
    allFeatures
      .filter((f) => f.properties?.footprint_method === 'polar_reconstructed')
      .map((f) => f.properties),
  ), [allFeatures]);

  const toggleKey = useCallback((key, on) => {
    setEnabledKeys((prev) => {
      const next = new Set(prev ?? effectiveKeys);
      if (on) next.add(key); else next.delete(key);
      return next;
    });
  }, [effectiveKeys]);

  const toggleGroup = useCallback((group, on) => {
    setEnabledKeys((prev) => {
      const next = new Set(prev ?? effectiveKeys);
      for (const row of group.rows) {
        if (!row.count) continue;
        if (on) next.add(row.key); else next.delete(row.key);
      }
      return next;
    });
  }, [effectiveKeys]);

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          Detection Explorer
          <span className="brand-sub">RMIT wildfire telemetry</span>
        </div>

        <div className="scene-picker">
          {scenes.map((s) => (
            <Chip key={s.id} on={s.id === sceneId} onClick={() => setSceneId(s.id)}>
              {s.title}
            </Chip>
          ))}
        </div>

        <ProvenanceStrip sources={payload?.sources} detections={allFeatures} />

        <div className="tools">
          <Chip onClick={() => setAbout(true)}>About this data</Chip>
          <a className="chip" href={exportUrl(sceneId, 'geojson')}>GeoJSON</a>
          <a className="chip" href={exportUrl(sceneId, 'csv')}>CSV</a>
        </div>
      </header>

      <div className="body">
        <aside className="sidebar">
          {sceneId !== 'current' && (
            <Collapsible
              title="BRIGHT run"
              open={runOpen}
              onToggle={() => setRunOpen((was) => !was)}
            >
              <RunPanel scene={sceneId} onFrames={setRunFrames} />
            </Collapsible>
          )}

          <Collapsible
            title="Detection"
            open={detailOpen}
            onToggle={() => setDetailOpen((was) => !was)}
          >
            <DetailCard detection={selected} />
          </Collapsible>

          <LayerPanel
            taxonomy={taxonomy}
            colours={colours}
            enabledKeys={effectiveKeys}
            onToggleKey={toggleKey}
            onToggleGroup={toggleGroup}
            renderMode={renderMode}
            onRenderMode={setRenderMode}
            basemap={basemap}
            onBasemap={setBasemap}
            contextGroups={contextGroups}
            contextEnabled={contextEnabled}
            onContextToggle={toggleContext}
            weatherConfigured={!!weatherKey}
          />
        </aside>

        <main className="main">
          {error && <div className="error">{error}</div>}
          {loading && <div className="loading">Loading…</div>}
          <MapView
            features={shown}
            enabledKeys={effectiveKeys}
            renderMode={renderMode}
            basemap={basemap}
            selected={selected}
            onSelect={setSelected}
            fitKey={sceneId}
            contextLayers={contextLayers}
            contextEnabled={contextEnabled}
          />
          <LegendDock
            taxonomy={taxonomy}
            colours={colours}
            contextLayers={contextLayers}
            contextEnabled={contextEnabled}
          />
        </main>
      </div>

      <footer className="slider-bar">
        <div className="slider-label">
          {cursor ? new Date(cursor).toISOString().replace('.000Z', 'Z') : '—'}
        </div>
        <div className="overpasses">
          {overpassState.visible.length === 0 && (
            <span className="faint small">no polar observation at this time</span>
          )}
          {[...new Map(overpassState.visible.map((v) => [v.platform, v])).values()].map((v) => (
            <span key={v.platform}
                  className={`badge ${v.state === 'solid' ? 'badge-ok' : ''}`}>
              {v.platform}: {v.state === 'solid' ? 'observing now' : formatAge(v.ageSeconds)}
            </span>
          ))}
        </div>
        <div className="markers">
          {markers.map((m) => (
            <Chip key={m.at} onClick={() => setCursor(m.at)}>
              {m.at.slice(11, 16)}Z · {m.platforms.join(', ')} ({m.count})
            </Chip>
          ))}
          {scene?.frames?.map((f) => (
            <button key={f} className="chip chip-frame"
                    onClick={() => setCursor(isoFromStamp(f))}>
              {f.slice(8, 10)}:{f.slice(10, 12)}
            </button>
          ))}
        </div>
      </footer>

      <AboutSheet
        open={about}
        onClose={() => setAbout(false)}
        scene={scene}
        sources={payload?.sources}
      />
    </div>
  );
}
