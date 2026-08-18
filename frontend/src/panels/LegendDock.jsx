import { useState } from 'react';
import { detectionLegend, legendFor } from '../map/legends.js';

/**
 * The colour keys, bottom-left of the map, one card per active layer.
 *
 * A card appears only while its layer is switched on. Eleven permanent legends would
 * cover the map; none at all leaves a reader looking at a fractional-cover raster with
 * nine colours in it and no way to know what any of them mean.
 */

function Card({ title, caption, note, children }) {
  return (
    <section className="hud legend-card">
      <div className="legend-title">{title}</div>
      {caption && <div className="legend-caption">{caption}</div>}
      {children}
      {note && <div className="legend-note">{note}</div>}
    </section>
  );
}

function Rows({ items }) {
  return (
    <div className="legend-rows">
      {items.map((item) => (
        <div className="legend-row" key={item.label} title={item.hint}>
          <span
            className="legend-swatch"
            style={{
              background: item.colour,
              border: item.border ?? (item.outline
                ? '1px dashed rgba(255,255,255,0.35)' : undefined),
            }}
          />
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  );
}

function ContextLegend({ layer }) {
  const legend = legendFor(layer.id);
  if (!legend) return null;

  if (legend.kind === 'gradient') {
    return (
      <Card title={layer.label} caption={legend.caption} note={legend.note}>
        <div
          className="legend-gradient"
          style={{ background: `linear-gradient(90deg, ${legend.stops.join(', ')})` }}
        />
        <div className="legend-scale">
          {legend.ticks.map((tick) => <span key={tick}>{tick}</span>)}
        </div>
      </Card>
    );
  }
  return (
    <Card title={layer.label} caption={legend.caption} note={legend.note}>
      <Rows items={legend.items} />
    </Card>
  );
}

/** Which algorithm is which colour, grouped by the comparison that matters. */
function DetectionKey({ groups }) {
  if (!groups.length) return null;
  return (
    <Card title="Detections" note="Warm: geostationary. Cool: polar-orbiting.">
      {groups.map((group) => (
        <div key={group.orbit}>
          <div className="legend-group-label">{group.label}</div>
          <div className="legend-rows">
            {group.items.map((item) => (
              <div className="legend-row" key={item.label + item.hint} title={item.hint}>
                <span className="legend-swatch round" style={{ background: item.colour }} />
                <span>{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </Card>
  );
}

export default function LegendDock({
  taxonomy, colours, enabledKeys, contextLayers, contextEnabled,
}) {
  const [open, setOpen] = useState(true);
  const active = (contextLayers ?? []).filter((layer) => contextEnabled[layer.id]);
  const detections = detectionLegend(taxonomy, colours, enabledKeys);
  const anything = active.length > 0 || detections.length > 0;
  if (!anything) return null;

  return (
    <div className="map-overlay-bl">
      <button
        type="button"
        className="chip legend-dock-toggle"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        {open ? '▾' : '▸'} Legend · {active.length + (detections.length ? 1 : 0)}
      </button>
      {open && (
        <>
          {active.map((layer) => <ContextLegend key={layer.id} layer={layer} />)}
          <DetectionKey groups={detections} />
        </>
      )}
    </div>
  );
}
