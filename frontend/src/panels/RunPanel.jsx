import { useEffect, useRef, useState } from 'react';
import { cancelRun, followRun, getRun, startRun } from '../api.js';

/**
 * Run BRIGHT and watch it work.
 *
 * The per-frame wait is left visible rather than hidden behind a spinner. A frame takes
 * around 27 seconds of real detection over a 29-day statistical window, and watching that
 * happen is the point of the exercise: it is the difference between an interface that
 * claims a computation and one that performs it.
 *
 * Delivery is shown separately from the data's nature. A cached run replays the identical
 * event sequence, so the demonstration never depends on a cold start, but it says it was
 * cached rather than passing the replay off as fresh work.
 */

const STATE_LABEL = {
  queued: 'queued',
  running: 'computing',
  succeeded: 'complete',
  failed: 'failed',
  cancelled: 'cancelled',
};

export default function RunPanel({ scene, onFrames }) {
  const [run, setRun] = useState(null);
  const [frames, setFrames] = useState([]);
  const [state, setState] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const unfollow = useRef(null);

  useEffect(() => () => unfollow.current?.(), []);

  // A run belongs to a scene; switching scene abandons any view of the old one.
  useEffect(() => {
    unfollow.current?.();
    setRun(null); setFrames([]); setState(null); setError(null);
  }, [scene]);

  const begin = async () => {
    setBusy(true); setError(null); setFrames([]);
    try {
      const started = await startRun(scene);
      setRun(started);
      setState(started.state);
      if (started.delivery === 'cached') {
        const finished = await getRun(started.run_id);
        setState(finished.state);
        setFrames((finished.detections ?? []).map((d, i) => ({
          frame: d.frame, index: i + 1, of: finished.frames.length,
          detections: d.detections?.length ?? 0, cached: true,
        })));
        onFrames?.(finished.detections ?? []);
        return;
      }
      unfollow.current = followRun(started.run_id, {
        onEvent: ({ kind, payload }) => {
          if (kind === 'run.state') setState(payload.state);
          if (kind === 'run.frame') setFrames((prev) => [...prev, payload]);
        },
        onDone: async () => {
          setState('succeeded');
          const finished = await getRun(started.run_id);
          onFrames?.(finished.detections ?? []);
        },
        onError: (payload) => { setState('failed'); setError(payload?.reason ?? 'failed'); },
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    if (!run) return;
    unfollow.current?.();
    const cancelled = await cancelRun(run.run_id);
    setState(cancelled.state);
  };

  const active = state === 'queued' || state === 'running';

  return (
    <div>

      <div className="run-actions">
        <button className="chip" onClick={begin} disabled={busy || active}
                title="Recomputes six frames from staged Himawari inputs. Each frame is a
real run over its own 29-day statistical window and takes roughly half a minute.">
          {active ? 'Running…' : 'Run BRIGHT'}
        </button>
        {active && <button className="chip" onClick={stop}>Cancel</button>}
        {state && <span className="badge">{STATE_LABEL[state] ?? state}</span>}
        {run?.delivery === 'cached' && <span className="badge badge-warn">cached</span>}
        {run?.attempt > 1 && <span className="badge">attempt {run.attempt}</span>}
      </div>

      {error && <p className="caveat">{error}</p>}

      {frames.length > 0 && (
        <ol className="frames">
          {frames.map((f) => (
            <li key={`${f.frame}-${f.index}`}>
              <span className="frame-ts">{f.frame?.slice(8, 10)}:{f.frame?.slice(10, 12)}</span>
              <span>{f.detections} detections</span>
              {f.cached
                ? <span className="badge badge-warn">cached</span>
                : <span className="muted small">{f.elapsed_s}s</span>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
