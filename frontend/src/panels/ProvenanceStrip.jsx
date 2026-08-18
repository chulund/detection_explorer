import { Badge, Tooltip } from './ui.jsx';

/**
 * Source status, compressed to chips in the header.
 *
 * This used to be a full-width strip of cards restating each source's nature, count,
 * fixture flag and the scene window. All of that is still reachable — the counts are in
 * the layer panel, the rest is on the chip and in the About sheet — but it no longer
 * takes a band across the top of a dashboard whose subject is the map.
 */

const NATURE = {
  live: ['ok', 'live'],
  static: ['tech', 'historical'],
  replay: ['fire', 'replay'],
};

export default function ProvenanceStrip({ sources, detections }) {
  const entries = Object.entries(sources ?? {});
  if (!entries.length) return null;

  const naturesFor = (name) => [...new Set(
    (detections ?? [])
      .filter((d) => d.properties?.source === name)
      .map((d) => d.properties?.data_nature),
  )];

  return (
    <div className="chip-row" style={{ margin: 0 }}>
      {entries.map(([name, info]) => {
        const [nature] = naturesFor(name);
        const [tone, label] = NATURE[nature] ?? [undefined, null];
        const detail = info.available
          ? [`${info.count ?? 0} records`,
             label && `nature: ${label}`,
             info.used_fixture && 'served from a committed fixture',
             info.truncated && 'truncated at the service cap',
             info.products_queried?.length && info.products_queried[0] !== '*'
               && `queried ${info.products_queried.join(', ')}`,
            ].filter(Boolean).join(' · ')
          : `unavailable${info.reason ? ` — ${info.reason}` : ''}`;

        return (
          <Tooltip key={name} text={detail}>
            <Badge tone={info.available ? tone : 'bad'}>
              {name}
              {info.used_fixture && ' ·  fixture'}
            </Badge>
          </Tooltip>
        );
      })}
    </div>
  );
}
