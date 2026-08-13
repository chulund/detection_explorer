/**
 * FR-DETAIL, plus the two footprint caveats.
 *
 * Both caveats read their field rather than being hardcoded. If the orientation is ever
 * validated, or the side ever recovered, the badge changes because the data changed, not
 * because someone remembered to edit a string.
 */

const CAVEATS = {
  experimental:
    'Experimental footprint: high-latitude orientation validation pending. Model ' +
    'comparisons have shown discrepancies of up to 892 m; this is not a measured error ' +
    'bound for this detection.',
  ambiguous:
    'Two candidates shown. A FIRMS record cannot say which side of the satellite’s ' +
    'ground track the pixel lay on, and at this latitude the two possibilities differ ' +
    'materially (measured: 0.78 overlap, up to 476 m at the corners).',
};

const Row = ({ label, value }) =>
  value === null || value === undefined || value === '' ? null : (
    <div className="detail-row">
      <span className="detail-label">{label}</span>
      <span className="detail-value">{String(value)}</span>
    </div>
  );

export default function DetailCard({ detection }) {
  if (!detection) {
    return (
      <div className="panel">
        <h2>Detection</h2>
        <p className="muted">Click a footprint or point on the map.</p>
      </div>
    );
  }

  const d = detection;
  const confidence = d.confidence_native ?? d.confidence;

  return (
    <div className="panel">
      <h2>Detection</h2>

      <Row label="Observed" value={d.detected_at} />
      <Row label="Nature" value={d.data_nature} />
      <Row label="Origin" value={d.computation} />

      <h3>Instrument</h3>
      <Row label="Platform" value={d.platform} />
      <Row label="Instrument" value={d.instrument} />
      <Row label="Product" value={d.product} />
      <Row label="Algorithm" value={`${d.algorithm ?? ''} ${d.algorithm_version ?? ''}`.trim()} />

      <h3>Measurement</h3>
      <Row label="Position" value={`${Number(d.lat).toFixed(4)}, ${Number(d.lon).toFixed(4)}`} />
      <Row label="FRP" value={d.frp_mw ? `${Number(d.frp_mw).toFixed(1)} MW` : null} />
      <Row
        label="Confidence"
        value={confidence != null ? `${confidence}${d.confidence_scheme ? ` (${d.confidence_scheme})` : ''}` : null}
      />

      {d.footprint_kind && (
        <>
          <h3>Footprint</h3>
          <Row label="Kind" value="satellite pixel footprint, not a fire perimeter" />
          <Row label="Method" value={d.footprint_method} />
          <Row label="Model" value={d.footprint_model_version} />
          <Row label="Status" value={d.footprint_status} />
          <Row label="Side" value={d.footprint_side} />
        </>
      )}

      {d.footprint_status === 'experimental' && (
        <p className="caveat">{CAVEATS.experimental}</p>
      )}
      {d.footprint_side === 'ambiguous' && (
        <p className="caveat">{CAVEATS.ambiguous}</p>
      )}
    </div>
  );
}
