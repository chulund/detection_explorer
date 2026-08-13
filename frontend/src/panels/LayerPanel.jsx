/**
 * FR-LAYERS: every layer independently toggleable, each with its status.
 *
 * Detection layers come first and carry their counts, because they are what the interface is
 * for. Contextual layers follow, grouped by the question they answer: what can burn, what
 * burnt before, who it affects, and what the weather is doing.
 *
 * Weather appears only when a key is configured. An offered-but-broken checkbox is a worse
 * answer than an honest absence, so the group is omitted rather than disabled.
 */

function Row({ id, label, hint, checked, onChange, count }) {
  return (
    <label className="layer-row" key={id}>
      <input type="checkbox" checked={!!checked} onChange={(e) => onChange(id, e.target.checked)} />
      <span>
        {label}
        {count !== undefined && <small className="muted"> — {count}</small>}
        {hint && <small className="muted layer-hint">{hint}</small>}
      </span>
    </label>
  );
}

export default function LayerPanel({
  detectionLayers, detectionEnabled, onDetectionToggle,
  contextGroups, contextEnabled, onContextToggle, weatherConfigured,
}) {
  return (
    <div className="panel">
      <h2>Layers</h2>

      <h3>Detections</h3>
      {detectionLayers.map((layer) => (
        <Row
          key={layer.id}
          id={layer.id}
          label={layer.label}
          hint={layer.hint}
          count={layer.count}
          checked={detectionEnabled[layer.id]}
          onChange={onDetectionToggle}
        />
      ))}

      {contextGroups.map(({ group, layers }) => (
        <div key={group}>
          <h3>{group}</h3>
          {layers.map((layer) => (
            <Row
              key={layer.id}
              id={layer.id}
              label={layer.label}
              hint={layer.hint}
              checked={contextEnabled[layer.id]}
              onChange={onContextToggle}
            />
          ))}
        </div>
      ))}

      {!weatherConfigured && (
        <p className="muted small layer-note">
          Weather layers need an OpenWeatherMap key in <code>OPENWEATHER_API_KEY</code>. They
          are hidden rather than shown broken.
        </p>
      )}

      <p className="muted small layer-note">
        Contextual layers describe the ground and the season, not the fire. They are drawn
        beneath every detection.
      </p>
    </div>
  );
}
