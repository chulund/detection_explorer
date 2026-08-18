import { useState } from 'react';
import { popupFields } from '../map/popup.js';
import { Badge, Field, Tooltip } from './ui.jsx';

/**
 * The selected detection.
 *
 * Primary measurements are always visible; identifiers, model versions and the rest of
 * the provenance block sit behind one disclosure. The panel used to show all of it at
 * once, which made the two numbers a person actually reads — power and temperature —
 * take as much attention as `footprint_model_version`.
 *
 * Both caveats are chips now rather than paragraphs, and both still read their field
 * rather than being hardcoded. If the orientation is ever validated, or the side ever
 * recovered, the chip disappears because the data changed and not because someone
 * remembered to edit a string. The full wording is on the chip and in the About sheet.
 */

export const CAVEATS = {
  experimental:
    'Experimental footprint: high-latitude orientation validation pending. Model '
    + 'comparisons have shown discrepancies of up to 892 m; this is not a measured error '
    + 'bound for this detection.',
  ambiguous:
    'Two candidates shown. A FIRMS record cannot say which side of the satellite’s '
    + 'ground track the pixel lay on, and at this latitude the two possibilities differ '
    + 'materially (measured: 0.78 overlap, up to 476 m at the corners).',
};

const NATURE = {
  live: ['ok', 'live'],
  static: ['tech', 'historical'],
  replay: ['fire', 'replay'],
};

export default function DetailCard({ detection }) {
  const [technical, setTechnical] = useState(false);

  if (!detection) {
    return <div className="empty-state">Select a detection on the map.</div>;
  }

  const d = detection;
  const [tone, label] = NATURE[d.data_nature] ?? [undefined, d.data_nature];

  return (
    <>
      <div className="chip-row">
        {label && <Badge tone={tone}>{label}</Badge>}
        {d.computation && <Badge>{d.computation}</Badge>}
        {d.footprint_status === 'experimental' && (
          <Tooltip text={CAVEATS.experimental}>
            <Badge tone="warn">experimental</Badge>
          </Tooltip>
        )}
        {d.footprint_side === 'ambiguous' && (
          <Tooltip text={CAVEATS.ambiguous}>
            <Badge tone="warn">2 candidates</Badge>
          </Tooltip>
        )}
      </div>

      {popupFields(d).map((field) => (
        <Field key={field.label} label={field.label} value={field.value}
               text={!field.numeric} />
      ))}

      <button
        type="button"
        className="disclosure-toggle"
        aria-expanded={technical}
        onClick={() => setTechnical((was) => !was)}
      >
        {technical ? '▾ Hide technical fields' : '▸ Show technical fields'}
      </button>

      {technical && (
        <>
          <Field label="Record" value={d.id} />
          <Field label="Source" value={d.source} text />
          <Field label="Product" value={d.product} text />
          <Field label="Satellite" value={d.satellite} text />
          <Field label="Published" value={d.published_at} />
          {d.footprint_kind && (
            <>
              <Field label="Geometry" value="satellite pixel footprint" text />
              <Field label="Method" value={d.footprint_method} text />
              <Field label="Model" value={d.footprint_model_version} text />
              <Field label="Status" value={d.footprint_status} text />
              <Field label="Side" value={d.footprint_side} text />
            </>
          )}
        </>
      )}
    </>
  );
}
