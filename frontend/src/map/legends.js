/**
 * What the colours on a contextual layer mean.
 *
 * Every ramp here describes one specific rendering of one specific service, which is why
 * `contextLayers.js` now names the DEA style instead of asking for the default: a legend
 * that has drifted from the tiles beneath it is worse than no legend, because it is
 * confidently wrong rather than merely absent.
 *
 * The values come from the XPRIZE frontend's map legends. That codebase carries two
 * versions of several ramps — a short array it declares and a longer one it actually
 * renders — and they disagree. The rendered ones are authoritative and are what is here.
 */

/** A continuous scale, drawn as a gradient bar with ticks. */
const gradient = (stops, ticks, caption, note) =>
  ({ kind: 'gradient', stops, ticks, caption, note });

/** A discrete scale, drawn as swatch rows. */
const classes = (items, note, caption) => ({ kind: 'classes', items, note, caption });

const DEA_NOTE = 'Digital Earth Australia';
const OWM_NOTE = 'OpenWeatherMap · current conditions, not the scene time';

export const LEGENDS = {
  // ---------------------------------------------------------------- fuel and ground
  fmc: gradient(
    ['#d00032', '#e97966', '#f7d8b5', '#f9f7bc', '#c9d9bb', '#7eaeb6', '#2580b8'],
    ['0%', '50%', '100%', '150%'],
    'Fuel moisture, weight percent. Below about 150% is elevated fire risk.',
    `${DEA_NOTE} · Sentinel-2 mosaic`,
  ),

  landcover: classes([
    { colour: '#347834', label: 'Woody vegetation' },
    { colour: '#80b040', label: 'Herbaceous vegetation' },
    { colour: '#22d3ee', label: 'Aquatic vegetation' },
    { colour: '#c8a040', label: 'Cultivated' },
    { colour: '#9ca3af', label: 'Bare or sparse' },
    { colour: '#3b82f6', label: 'Water' },
    { colour: '#ef4444', label: 'Artificial surface' },
  ], `${DEA_NOTE} · Landsat annual land cover`),

  // Nine classes, not three: this is the ternary green / non-green / bare triangle, and
  // the mixtures between them are most of the continent.
  fractional_cover: classes([
    { colour: '#2f2df4', label: 'Non-green', hint: 'More than two thirds non-green cover.' },
    { colour: '#7a4ca5', label: 'Non-green mix', hint: 'All fractions, non-green dominant.' },
    { colour: '#cc2f7a', label: 'Non-green and bare', hint: 'Minimal green cover.' },
    { colour: '#67a894', label: 'Non-green and green', hint: 'Minimal bare ground.' },
    { colour: '#ff4208', label: 'Bare', hint: 'More than two thirds bare ground.' },
    { colour: '#f06212', label: 'Bare mix', hint: 'All fractions, bare dominant.' },
    { colour: '#a8f000', label: 'Bare and green', hint: 'Minimal non-green vegetation.' },
    { colour: '#39da75', label: 'Green mix', hint: 'All fractions, green dominant.' },
    { colour: '#15f000', label: 'Green', hint: 'More than two thirds green cover.' },
  ], `${DEA_NOTE} · Landsat annual fractional cover`),

  water: classes([
    { colour: '#08306b', label: '100%', hint: 'Permanent water.' },
    { colour: '#2171b5', label: '50–99%', hint: 'Frequent.' },
    { colour: '#6baed6', label: '20–49%', hint: 'Moderate.' },
    { colour: '#bdd7e7', label: '1–19%', hint: 'Infrequent.' },
    { colour: 'transparent', label: '0%', outline: true, hint: 'Never wet.' },
  ], `${DEA_NOTE} · Landsat annual water observations`,
     'Share of annual observations classified as wet'),

  // ---------------------------------------------------------------- fire history
  fire_history: classes([
    { colour: 'rgba(220,38,38,0.10)', border: '2px solid #dc2626', label: 'Wildfire' },
    { colour: 'rgba(250,204,21,0.16)', border: '2px dashed #f59e0b',
      label: 'Prescribed burn' },
  ], 'NSW NPWS fire history'),

  // ---------------------------------------------------------------- boundaries
  lga: classes([
    { colour: 'transparent', border: '2px solid #fff3b0', label: 'Council boundary' },
  ], 'NSW Administrative Boundaries'),

  reserves: classes([
    { colour: 'rgba(52,211,153,0.18)', border: '1px solid #34d399',
      label: 'National park or reserve' },
  ], 'NSW Administrative Boundaries'),

  // ---------------------------------------------------------------- weather
  wx_temp: classes([
    { colour: '#3f51b5', label: '−20 °C' },
    { colour: '#00bcd4', label: '−10 °C' },
    { colour: '#009688', label: '0 °C' },
    { colour: '#4caf50', label: '10 °C' },
    { colour: '#ffeb3b', label: '20 °C' },
    { colour: '#ff9800', label: '30 °C' },
    { colour: '#f44336', label: '40 °C' },
    { colour: '#880e4f', label: 'above 50 °C' },
  ], OWM_NOTE),

  wx_wind: classes([
    { colour: '#ffffcc', label: 'under 5 m/s' },
    { colour: '#a1dab4', label: '5–10' },
    { colour: '#41b6c4', label: '10–15' },
    { colour: '#2c7fb8', label: '15–20' },
    { colour: '#253494', label: 'over 20 m/s' },
  ], OWM_NOTE),

  wx_precip: classes([
    { colour: 'rgba(0,130,255,0.4)', label: 'Light' },
    { colour: 'rgba(0,200,0,0.6)', label: 'Moderate' },
    { colour: 'rgba(255,255,0,0.7)', label: 'Heavy' },
    { colour: 'rgba(255,130,0,0.8)', label: 'Very heavy' },
    { colour: 'rgba(255,0,0,0.9)', label: 'Extreme' },
  ], OWM_NOTE),

  wx_clouds: classes([
    { colour: 'rgba(255,255,255,0.0)', outline: true, label: 'Clear' },
    { colour: 'rgba(255,255,255,0.25)', label: '25%' },
    { colour: 'rgba(255,255,255,0.5)', label: '50%' },
    { colour: 'rgba(255,255,255,0.75)', label: '75%' },
    { colour: 'rgba(255,255,255,1.0)', label: '100%' },
  ], OWM_NOTE),
};

export const legendFor = (layerId) => LEGENDS[layerId] ?? null;

/**
 * The detection key, built from whatever is on screen rather than declared in advance.
 *
 * This one has no counterpart in the reference frontend, which is Himawari-only and has
 * no polar sensors to distinguish. Grouping by orbit is the comparison this interface
 * exists to make, so the key leads with it.
 */
export function detectionLegend(groups, colours) {
  const byOrbit = new Map();
  for (const group of groups ?? []) {
    for (const row of group.rows) {
      if (!row.count) continue;
      const orbit = row.sensorClass.orbit;
      if (!byOrbit.has(orbit)) byOrbit.set(orbit, []);
      byOrbit.get(orbit).push({
        colour: colours?.[row.key] ?? '#9aa0a6',
        label: `${row.algorithm}${row.version ? ` ${row.version}` : ''}`,
        hint: `${row.instrument} · ${row.platform} · ${row.sensorClass.resolution}`,
      });
    }
  }
  const order = ['geostationary', 'polar-orbiting', 'unknown'];
  return [...byOrbit.entries()]
    .sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]))
    .map(([orbit, items]) => ({
      orbit,
      label: orbit === 'geostationary' ? 'Geostationary'
        : orbit === 'polar-orbiting' ? 'Polar-orbiting' : 'Unclassified',
      items,
    }));
}
