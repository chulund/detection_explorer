import { useState } from 'react';
import { BASEMAPS } from '../map/basemaps.js';
import { Badge, Collapsible, SegmentedControl, StatusDot, Swatch } from './ui.jsx';

/**
 * What is on the map, named by what produced it.
 *
 * The old panel offered three toggles named after data sources. That understated the
 * scene badly: "DEA" alone covers a VIIRS product, a MODIS-named product and two
 * generations of BRIGHT on Himawari, and 1660 of its 1785 records had no label at all.
 * Rows are now derived from the records, one per algorithm, version, sensor and platform.
 *
 * A row with no records still appears when its product was queried. Dropping it would let
 * a reader conclude the sensor was never consulted, which is a different claim.
 */

const RENDER_MODES = [
  { value: 'auto', label: 'Auto',
    hint: 'Marker until the pixel is big enough to read, then the true-scale footprint' },
  { value: 'footprints', label: 'Footprints',
    hint: 'True scale at every zoom. Records with no geometry keep a marker' },
  { value: 'points', label: 'Points',
    hint: 'One marker per detection, whatever its pixel size' },
];

function Row({ row, colour, checked, onToggle }) {
  const empty = row.count === 0;
  return (
    <label className={empty ? 'layer-row is-empty' : 'layer-row'}>
      <input type="checkbox" checked={!!checked} disabled={empty}
             onChange={(event) => onToggle(row.key, event.target.checked)} />
      <Swatch colour={empty ? 'transparent' : colour} />
      <span className="layer-row-main">
        <span className="layer-row-title">
          <span className="layer-name">
            {row.algorithm}{row.version ? ` ${row.version}` : ''}
          </span>
          <span className="layer-count">{row.count.toLocaleString()}</span>
        </span>
        <span className="layer-sub">
          {row.instrument} · {row.platform} · {row.sensorClass.resolution}
          {row.status === 'empty' && ' · none in window'}
        </span>
      </span>
      <StatusDot status={row.status} />
    </label>
  );
}

function DetectionGroup({ group, colours, enabled, onToggle, onToggleGroup }) {
  const live = group.rows.filter((row) => row.count > 0);
  const on = live.filter((row) => enabled.has(row.key)).length;
  const all = live.length > 0 && on === live.length;
  const some = on > 0 && !all;

  return (
    <div>
      <label className="group-head">
        <input
          type="checkbox"
          checked={all}
          disabled={!live.length}
          ref={(element) => { if (element) element.indeterminate = some; }}
          onChange={() => onToggleGroup(group, !all)}
        />
        <span className="group-label">
          {group.label}
          {group.qualifier && <span className="group-qualifier"> · {group.qualifier}</span>}
        </span>
        <span className="group-count">{group.count.toLocaleString()}</span>
      </label>
      {!group.available && (
        <div className="layer-sub" style={{ paddingLeft: 26 }}>
          unavailable{group.reason ? ` — ${group.reason}` : ''}
        </div>
      )}
      {group.rows.map((row) => (
        <Row key={row.key} row={row} colour={colours[row.key]}
             checked={enabled.has(row.key)} onToggle={onToggle} />
      ))}
    </div>
  );
}

export default function LayerPanel({
  taxonomy, colours, enabledKeys, onToggleKey, onToggleGroup,
  renderMode, onRenderMode, basemap, onBasemap,
  contextGroups, contextEnabled, onContextToggle, weatherConfigured,
}) {
  const [open, setOpen] = useState({
    detections: true, render: true, basemap: false, context: true,
  });
  const toggle = (id) => setOpen((was) => ({ ...was, [id]: !was[id] }));
  const total = taxonomy.reduce((sum, group) => sum + group.count, 0);

  return (
    <>
      <Collapsible
        title="Detections"
        aside={<Badge tone="fire">{total.toLocaleString()}</Badge>}
        open={open.detections}
        onToggle={() => toggle('detections')}
      >
        {taxonomy.length === 0 && <div className="empty-state">No detections loaded.</div>}
        {taxonomy.map((group) => (
          <DetectionGroup
            key={group.source}
            group={group}
            colours={colours}
            enabled={enabledKeys}
            onToggle={onToggleKey}
            onToggleGroup={onToggleGroup}
          />
        ))}
      </Collapsible>

      <Collapsible title="Rendering" open={open.render} onToggle={() => toggle('render')}>
        <SegmentedControl
          label="How detections are drawn"
          value={renderMode}
          options={RENDER_MODES}
          onChange={onRenderMode}
        />
        <p className="faint small" style={{ margin: '8px 0 0' }}>
          {RENDER_MODES.find((mode) => mode.value === renderMode)?.hint}
        </p>
      </Collapsible>

      <Collapsible
        title="Background"
        aside={<span className="faint small">{
          BASEMAPS.find((b) => b.id === basemap)?.label
        }</span>}
        open={open.basemap}
        onToggle={() => toggle('basemap')}
      >
        <div className="basemap-grid">
          {BASEMAPS.map((option) => (
            <label key={option.id} className="layer-row" title={option.hint}>
              <input type="radio" name="basemap" checked={basemap === option.id}
                     onChange={() => onBasemap(option.id)} />
              <span className="layer-name">{option.label}</span>
            </label>
          ))}
        </div>
      </Collapsible>

      <Collapsible title="Context" open={open.context} onToggle={() => toggle('context')}>
        {contextGroups.map(({ group, layers }) => (
          <div key={group}>
            <div className="group-head" style={{ cursor: 'default' }}>
              <span className="group-label">{group}</span>
            </div>
            {layers.map((layer) => (
              <label key={layer.id} className="layer-row" title={layer.hint}>
                <input type="checkbox" checked={!!contextEnabled[layer.id]}
                       onChange={(event) => onContextToggle(layer.id, event.target.checked)} />
                <span className="layer-row-main">
                  <span className="layer-name">{layer.label}</span>
                </span>
              </label>
            ))}
          </div>
        ))}
        {!weatherConfigured && (
          <div className="layer-sub" style={{ marginTop: 10 }}>
            Weather layers need <code>OPENWEATHER_API_KEY</code>. Hidden rather than broken.
          </div>
        )}
      </Collapsible>
    </>
  );
}
