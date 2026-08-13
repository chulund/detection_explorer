/**
 * What each source is, when it last observed, and where its records came from.
 *
 * Three separate facts, deliberately not merged into one badge. `data_nature` is what the
 * observation scientifically is. `computation` is where the record came from. Delivery,
 * whether a run was fresh or cached, belongs to the run and is shown by the run panel, not
 * here, because it describes delivery rather than the observation.
 */

const NATURE_LABEL = {
  live: 'Current external feed',
  static: 'Historical observation',
  replay: 'BRIGHT recomputed from staged inputs',
};

const NATURE_CLASS = { live: 'nature-live', static: 'nature-static', replay: 'nature-replay' };

export default function ProvenanceStrip({ sources, detections, sceneWindow }) {
  const entries = Object.entries(sources ?? {});
  if (!entries.length) return null;

  const naturesFor = (name) => {
    const set = new Set(
      (detections ?? [])
        .filter((d) => d.properties?.source === name)
        .map((d) => d.properties?.data_nature),
    );
    return [...set];
  };

  return (
    <div className="provenance">
      {entries.map(([name, info]) => {
        const natures = naturesFor(name);
        return (
          <div key={name} className={`prov-card ${info.available ? '' : 'prov-off'}`}>
            <div className="prov-name">{name}</div>
            {info.available ? (
              <>
                {natures.map((n) => (
                  <span key={n} className={`badge ${NATURE_CLASS[n] ?? ''}`}>
                    {NATURE_LABEL[n] ?? n}
                  </span>
                ))}
                {info.used_fixture && <span className="badge badge-warn">from cached fixture</span>}
                <div className="prov-count">{info.count ?? 0} detections</div>
              </>
            ) : (
              <div className="prov-count muted">
                unavailable{info.reason ? ` — ${info.reason}` : ''}
              </div>
            )}
          </div>
        );
      })}
      {sceneWindow && (
        <div className="prov-card prov-window">
          <div className="prov-name">Window</div>
          <div className="prov-count">
            {sceneWindow.start} to {sceneWindow.end}
            {sceneWindow.half_open ? ' (end exclusive)' : ''}
          </div>
        </div>
      )}
    </div>
  );
}
