import { useEffect, useMemo, useState } from 'react';
import { exportUrl, getDetections, getScenes, getStatus } from './api.js';
import MapView from './map/MapView.jsx';
import { availableContextLayers, groupedContextLayers } from './map/contextLayers.js';
import DetailCard from './panels/DetailCard.jsx';
import LayerPanel from './panels/LayerPanel.jsx';
import ProvenanceStrip from './panels/ProvenanceStrip.jsx';
import RunPanel from './panels/RunPanel.jsx';
import { formatAge, overpassMarkers, visibleOverpasses } from './time/overpass.js';

/**
 * FR-LAYOUT: header, sidebar, map, layer panel, time slider.
 *
 * Switching scenes clears every layer before loading the new one, so no record from one
 * epoch can survive into another. That is enforced on the server too; doing it here as well
 * means a slow response cannot leave April detections on screen under a live label.
 */

/** "20260409040000" -> "2026-04-09T04:00:00Z" */
const isoFromStamp = (s) =>
  `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}T` +
  `${s.slice(8, 10)}:${s.slice(10, 12)}:${s.slice(12, 14) || '00'}Z`;

const LAYERS = [
  { id: 'ahi', label: 'BRIGHT / AHI footprints', hint: '2 km geostationary pixels' },
  { id: 'polar', label: 'VIIRS / MODIS footprints', hint: '375 m polar pixels, two candidates each' },
  { id: 'points', label: 'Points without geometry', hint: 'DEA hotspots carry no scan geometry' },
];

export default function App() {
  const [scenes, setScenes] = useState([]);
  const [sceneId, setSceneId] = useState('april-9-demo');
  const [payload, setPayload] = useState(null);
  const [status, setStatus] = useState(null);
  const [selected, setSelected] = useState(null);
  const [enabled, setEnabled] = useState({ ahi: true, polar: true, points: true });
  const [cursor, setCursor] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [runFrames, setRunFrames] = useState([]);
  const [contextEnabled, setContextEnabled] = useState({});

  // The weather key is supplied to the browser by the API rather than baked into the
  // bundle, so a build can be shared without carrying anyone's credentials.
  const weatherKey = status?.context?.weather?.key ?? null;
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

  const features = payload?.features ?? [];

  const split = useMemo(() => {
    const ahi = { type: 'FeatureCollection', features: [] };
    const polar = { type: 'FeatureCollection', features: [] };
    const points = { type: 'FeatureCollection', features: [] };
    for (const f of features) {
      const method = f.properties?.footprint_method;
      if (method === 'ahi_grid') ahi.features.push(f);
      else if (method === 'polar_reconstructed') polar.features.push(f);
      else points.features.push(f);
    }
    // BRIGHT output arrives from a run rather than from retrieval, so it is folded in
    // here. Marked `replay` and `computed`, never `live`: it is a real computation over
    // real April inputs, which is not the same thing as a current observation.
    for (const frame of runFrames) {
      for (const row of frame.detections ?? []) {
        const lon = Number(row.lon);
        const lat = Number(row.lat);
        if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
        ahi.features.push({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [lon, lat] },
          properties: {
            id: `bright:${frame.frame}:${row.x}:${row.y}`,
            source: 'bright', data_nature: 'replay', computation: 'computed',
            detected_at: isoFromStamp(frame.frame),
            platform: 'Himawari-9', instrument: 'AHI', product: 'BRIGHT AHI',
            algorithm: 'BRIGHT', lat, lon,
            frp_mw: row.frp ? Number(row.frp) : null,
            confidence_native: row.confidence, confidence_scheme: 'bright_percent',
            region: row.region, footprint_method: 'ahi_grid',
            footprint_status: 'validated', footprint_kind: 'satellite_pixel_footprint',
          },
        });
      }
    }
    return { ahi, polar, points };
  }, [features, runFrames]);

  // Which polar passes are visible at the cursor, and which are stale.
  const overpassState = useMemo(() => {
    if (!cursor) return { visible: [], dimmed: new Set() };
    const polarProps = split.polar.features.map((f) => f.properties);
    const visible = visibleOverpasses(polarProps, cursor);
    const keep = new Set(visible.map((v) => v.id));
    const dimmed = new Set(visible.filter((v) => v.state === 'dimmed').map((v) => v.id));
    return { visible, dimmed, keep };
  }, [split.polar, cursor]);

  const shown = useMemo(() => ({
    ahi: enabled.ahi ? split.ahi : { type: 'FeatureCollection', features: [] },
    polar: enabled.polar
      ? {
          type: 'FeatureCollection',
          features: overpassState.keep
            ? split.polar.features.filter((f) => overpassState.keep.has(f.properties.id))
            : split.polar.features,
        }
      : { type: 'FeatureCollection', features: [] },
    points: enabled.points ? split.points : { type: 'FeatureCollection', features: [] },
  }), [split, enabled, overpassState]);

  const markers = useMemo(
    () => overpassMarkers(split.polar.features.map((f) => f.properties)),
    [split.polar],
  );

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <strong>Detection Explorer</strong>
          <span className="muted"> — RMIT wildfire detection interface</span>
        </div>
        <div className="scene-picker">
          {scenes.map((s) => (
            <button
              key={s.id}
              className={s.id === sceneId ? 'chip chip-on' : 'chip'}
              onClick={() => setSceneId(s.id)}
              title={s.description}
            >
              {s.title}
            </button>
          ))}
        </div>
        <div className="tools">
          <a className="chip" href={exportUrl(sceneId, 'geojson')}>Export GeoJSON</a>
          <a className="chip" href={exportUrl(sceneId, 'csv')}>Export CSV</a>
        </div>
      </header>

      {scene?.description && <div className="scene-note">{scene.description}</div>}

      <ProvenanceStrip
        sources={payload?.sources}
        detections={features}
        sceneWindow={scene?.window}
      />

      <div className="body">
        <aside className="sidebar">
          {sceneId !== 'current' && (
            <RunPanel scene={sceneId} onFrames={setRunFrames} />
          )}
          <DetailCard detection={selected} />
          <LayerPanel
            detectionLayers={LAYERS.map((l) => ({
              ...l, count: split[l.id]?.features.length ?? 0,
            }))}
            detectionEnabled={enabled}
            onDetectionToggle={(id, on) => setEnabled((prev) => ({ ...prev, [id]: on }))}
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
            ahi={shown.ahi}
            polar={shown.polar}
            points={shown.points}
            dimmedIds={overpassState.dimmed}
            contextLayers={contextLayers}
            contextEnabled={contextEnabled}
            onSelect={setSelected}
          />
        </main>
      </div>

      <footer className="slider-bar">
        <div className="slider-label">
          {cursor ? new Date(cursor).toISOString().replace('.000Z', 'Z') : '—'}
        </div>
        <div className="overpasses">
          {overpassState.visible.length === 0 && (
            <span className="muted">no polar observation at this time</span>
          )}
          {[...new Map(overpassState.visible.map((v) => [v.platform, v])).values()].map((v) => (
            <span key={v.platform} className={`badge ${v.state === 'solid' ? 'nature-live' : ''}`}>
              {v.platform}: {v.state === 'solid' ? 'observing now' : formatAge(v.ageSeconds)}
            </span>
          ))}
        </div>
        <div className="markers">
          {markers.map((m) => (
            <button key={m.at} className="chip chip-small" onClick={() => setCursor(m.at)}>
              {m.at.slice(11, 16)}Z · {m.platforms.join(', ')} ({m.count})
            </button>
          ))}
          {scene?.frames?.map((f) => {
            const iso = `${f.slice(0, 4)}-${f.slice(4, 6)}-${f.slice(6, 8)}T${f.slice(8, 10)}:${f.slice(10, 12)}:00Z`;
            return (
              <button key={f} className="chip chip-small chip-frame" onClick={() => setCursor(iso)}>
                {f.slice(8, 10)}:{f.slice(10, 12)}
              </button>
            );
          })}
        </div>
      </footer>
    </div>
  );
}
