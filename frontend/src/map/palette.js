/**
 * One authority for detection colour.
 *
 * The map, the layer panel swatches and the legend all read from here, so they cannot
 * disagree about what a colour means. Colour also carries information rather than just
 * distinguishing rows: warm hues are geostationary, cool hues are polar-orbiting, which
 * is the comparison this whole interface exists to make.
 *
 * Colours are spread across a hue band rather than drawn from a fixed list, because a
 * list runs out. An earlier version had an eight-entry cool ramp and the demo scene has
 * nine polar layers, so the ninth wrapped onto the first and two unrelated algorithms
 * were painted identically. A band divides itself into however many layers there are.
 */

import { sensorClassFor } from './taxonomy.js';

/** Geostationary: orange through amber. Himawari AHI, whoever computed the detection. */
export const WARM_BAND = { from: 18, to: 48, saturation: 92, lightness: 60 };

/**
 * Polar-orbiting: cyan through blue to indigo. VIIRS and MODIS, every platform.
 *
 * Stopped short of violet deliberately. The band has to stay unmistakably cool against
 * the warm one, and a magenta at the far end starts reading as a third category.
 */
export const COOL_BAND = { from: 184, to: 258, saturation: 78, lightness: 62 };

/** Reserved: a live BRIGHT run, the one thing on the map that was computed just now. */
export const BRIGHT_RUN_COLOUR = '#ff6b35';

const FALLBACK = '#9aa0a6';

const instrumentOf = (key) => String(key).split('|')[3] ?? '';

const isBrightRun = (key) => String(key).startsWith('bright|');

function hslToHex(h, s, l) {
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
  const channel = (n) => {
    const k = (n + h / 30) % 12;
    const value = l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(255 * value).toString(16).padStart(2, '0');
  };
  return `#${channel(0)}${channel(8)}${channel(4)}`;
}

/**
 * The colour for one taxonomy key, given the full set of keys on screen.
 *
 * Position comes from the sorted key list rather than arrival order, so the same scene
 * always paints the same way and a legend screenshot stays true. Adding a genuinely new
 * product reshuffles the band; that is the price of guaranteeing no two layers collide,
 * and a collision is much worse than a shift.
 */
export function colourFor(key, keys = []) {
  if (isBrightRun(key)) return BRIGHT_RUN_COLOUR;

  const orbit = sensorClassFor(instrumentOf(key)).orbit;
  const band = orbit === 'geostationary' ? WARM_BAND
    : orbit === 'polar-orbiting' ? COOL_BAND
      : null;
  if (!band) return FALLBACK;

  const family = [...new Set(keys)]
    .filter((k) => !isBrightRun(k))
    .filter((k) => sensorClassFor(instrumentOf(k)).orbit === orbit)
    .sort();
  const index = Math.max(0, family.indexOf(key));
  const span = Math.max(1, family.length - 1);
  const hue = band.from + ((band.to - band.from) * index) / span;

  // Alternate the lightness a little as well as the hue. Adjacent steps in a narrow band
  // are hard to tell apart on their own, and the warm band is deliberately narrow so it
  // never strays into the cool one.
  const lightness = band.lightness + (index % 2 === 0 ? 0 : -9);
  return hslToHex(hue, band.saturation, lightness);
}

/** `{ key: colour }` for a whole scene, which is what the map and legend consume. */
export function colourMap(keys) {
  return Object.fromEntries((keys ?? []).map((key) => [key, colourFor(key, keys)]));
}
