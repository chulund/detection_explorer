/**
 * The card that opens where you clicked.
 *
 * Formatting is separated from rendering because the formatting is the part worth
 * testing, and because the rendering has one rule that must not be relaxed: every value
 * here came from an external feed, so it is written with `textContent` and never with
 * `innerHTML`. The reference frontend builds its popups from template-literal HTML
 * strings, which works only for as long as nobody puts a bracket in a place name.
 */

const LOCAL_ZONE = 'Australia/Sydney';

const isNumber = (value) => typeof value === 'number' && Number.isFinite(value);

/** "2026-04-09T04:29:00Z" -> "2026-04-09 04:29:00Z" */
function utc(iso) {
  if (!iso) return null;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return String(iso);
  return `${parsed.toISOString().slice(0, 19).replace('T', ' ')}Z`;
}

/** The same instant where the fire is, because that is the one people reason in. */
function local(iso) {
  if (!iso) return null;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return null;
  try {
    const text = new Intl.DateTimeFormat('en-AU', {
      timeZone: LOCAL_ZONE, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    }).format(parsed);
    const zone = new Intl.DateTimeFormat('en-AU', {
      timeZone: LOCAL_ZONE, timeZoneName: 'short',
    }).formatToParts(parsed).find((part) => part.type === 'timeZoneName')?.value ?? '';
    return `${text} ${zone}`.trim();
  } catch {
    return null;
  }
}

/** Algorithm and version, which is what distinguishes BRIGHT 2.0 from BRIGHT 1.86. */
export function popupTitle(properties) {
  if (!properties) return '';
  const algorithm = properties.algorithm ?? properties.product ?? 'Detection';
  return [algorithm, properties.instrument].filter(Boolean).join(' · ');
}

/**
 * The label and value pairs the popup shows, in order.
 *
 * A field with nothing to say is left out rather than printed as a dash. FRP of -1 is
 * how the DEA feed spells "not measured", so it counts as nothing to say.
 */
export function popupFields(properties) {
  if (!properties) return [];

  const frp = isNumber(properties.frp_mw) && properties.frp_mw >= 0
    ? `${properties.frp_mw.toFixed(1)} MW` : null;

  const brightness = isNumber(properties.brightness_k)
    ? [`${properties.brightness_k.toFixed(1)} K`, properties.brightness_channel]
      .filter(Boolean).join(' · ')
    : null;

  const confidence = properties.confidence_native ?? properties.confidence;
  const confidenceText = confidence === null || confidence === undefined || confidence === ''
    ? null
    : `${confidence}${properties.confidence_scheme ? ` (${properties.confidence_scheme})` : ''}`;

  const position = isNumber(Number(properties.lat)) && isNumber(Number(properties.lon))
    ? `${Number(properties.lat).toFixed(5)}, ${Number(properties.lon).toFixed(5)}`
    : null;

  const algorithm = [properties.algorithm ?? properties.product,
                     properties.algorithm_version].filter(Boolean).join(' ');

  return [
    { label: 'Sensor', value: properties.instrument },
    { label: 'Platform', value: properties.platform },
    { label: 'Algorithm', value: algorithm || null },
    { label: 'Observed (UTC)', value: utc(properties.detected_at), numeric: true },
    { label: 'Observed (local)', value: local(properties.detected_at), numeric: true },
    { label: 'FRP', value: frp, numeric: true },
    { label: 'Brightness', value: brightness, numeric: true },
    { label: 'Confidence', value: confidenceText },
    { label: 'Position', value: position, numeric: true },
  ].filter((field) => field.value !== null && field.value !== undefined
                      && field.value !== '');
}

/**
 * Build the popup body.
 *
 * Takes a document rather than reaching for the global one, so the no-markup rule can be
 * proven in a test without a browser.
 */
export function renderPopup(document, properties) {
  if (!properties) return null;

  const root = document.createElement('div');
  root.className = 'popup';

  const title = document.createElement('div');
  title.className = 'popup-title';
  title.textContent = popupTitle(properties);
  root.appendChild(title);

  const chips = document.createElement('div');
  chips.className = 'popup-chips';
  for (const [condition, text] of [
    [properties.footprint_status === 'experimental', 'experimental'],
    [properties.footprint_side === 'ambiguous', '2 candidates'],
    [properties.data_nature === 'replay', 'replay'],
  ]) {
    if (!condition) continue;
    const chip = document.createElement('span');
    chip.className = 'chip chip-tiny';
    chip.textContent = text;
    chips.appendChild(chip);
  }
  if (chips.children.length) root.appendChild(chips);

  const list = document.createElement('dl');
  list.className = 'popup-fields';
  for (const field of popupFields(properties)) {
    const label = document.createElement('dt');
    label.textContent = field.label;
    const value = document.createElement('dd');
    value.className = field.numeric ? 'mono' : '';
    value.textContent = String(field.value);
    list.appendChild(label);
    list.appendChild(value);
  }
  root.appendChild(list);
  return root;
}
