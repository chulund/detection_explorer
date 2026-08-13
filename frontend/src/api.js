/** Backend client. One place that knows about URLs. */

const json = async (response) => {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${body.slice(0, 300)}`);
  }
  return response.json();
};

export const getScenes = () => fetch('/api/v2/scenes').then(json);

export const getStatus = () => fetch('/api/v2/status').then(json);

export const getDetections = (scene, { sources } = {}) => {
  const params = new URLSearchParams({ scene, format: 'geojson' });
  if (sources?.length) params.set('sources', sources.join(','));
  return fetch(`/api/v2/detections?${params}`).then(json);
};

export const exportUrl = (scene, format, { sources, start, end, bbox } = {}) => {
  const params = new URLSearchParams({ scene, format });
  if (sources?.length) params.set('sources', sources.join(','));
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (bbox) params.set('bbox', bbox);
  return `/api/v2/export?${params}`;
};

export const startRun = (scene) =>
  fetch('/api/v2/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scene }),
  }).then(json);

export const getRun = (runId) => fetch(`/api/v2/runs/${runId}`).then(json);

export const cancelRun = (runId) =>
  fetch(`/api/v2/runs/${runId}/cancel`, { method: 'POST' }).then(json);

/**
 * Follow a run's progress.
 *
 * EventSource resends Last-Event-ID on reconnect by itself, and the server replays from
 * the journal, so a dropped connection resumes rather than restarting.
 */
export function followRun(runId, { onEvent, onDone, onError }) {
  const source = new EventSource(`/api/v2/runs/${runId}/events`);
  for (const kind of ['run.state', 'run.frame', 'run.error', 'run.done']) {
    source.addEventListener(kind, (event) => {
      const payload = JSON.parse(event.data);
      onEvent?.({ kind, payload, id: event.lastEventId });
      if (kind === 'run.done') { source.close(); onDone?.(payload); }
      if (kind === 'run.error') { source.close(); onError?.(payload); }
    });
  }
  source.onerror = () => {
    // EventSource retries on its own. Only a closed stream is terminal.
    if (source.readyState === EventSource.CLOSED) onError?.({ reason: 'stream closed' });
  };
  return () => source.close();
}
