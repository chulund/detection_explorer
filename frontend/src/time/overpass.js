/**
 * Which polar observations to show at a given slider time, and how.
 *
 * This is the piece of the interface where honesty is easiest to lose. BRIGHT produces a
 * frame every ten minutes; the polar sensors deliver one or two passes in the whole hour.
 * Interpolating a polar detection across the slider would imply continuous coverage that
 * does not exist, so a pass is solid only near its own acquisition instant, and afterwards
 * it is dimmed and carries its age.
 *
 * Retention is per platform and product. Suomi-NPP crossing at 04:27 must not be erased
 * from the display by NOAA-20 crossing at 04:47; they are separate observations of the same
 * fire twenty minutes apart, and that gap is the point.
 */

import { sensorClassFor } from '../map/taxonomy.js';

/** Half the AHI cadence: within this, a polar detection is contemporaneous with the frame. */
export const TOLERANCE_SECONDS = 300;
export const PASS_GAP_SECONDS = 900;

const key = (d) => `${d.platform ?? 'unknown'}::${d.product ?? 'unknown'}`;

const seconds = (iso) => Date.parse(iso) / 1000;

const stampSeconds = (stamp) => Date.UTC(
  Number(stamp.slice(0, 4)), Number(stamp.slice(4, 6)) - 1,
  Number(stamp.slice(6, 8)), Number(stamp.slice(8, 10)),
  Number(stamp.slice(10, 12)), Number(stamp.slice(12, 14) || 0),
) / 1000;

/** Latest declared scene frame at or before the cursor. */
export function activeSceneFrame(frames, cursor) {
  const now = seconds(cursor);
  if (!Number.isFinite(now)) return null;
  return [...(frames ?? [])]
    .filter((frame) => stampSeconds(frame) <= now)
    .sort((a, b) => stampSeconds(a) - stampSeconds(b))
    .at(-1) ?? null;
}

/**
 * Geostationary detections belong to one selected ten-minute frame. Other orbits use
 * overpass retention instead and pass through here, including point-only polar records.
 */
export function inSelectedSceneFrame(detection, frames, cursor) {
  if (sensorClassFor(detection?.instrument).orbit !== 'geostationary') return true;
  if (!(frames ?? []).length || !cursor) return true;
  const active = activeSceneFrame(frames, cursor);
  if (!active) return false;
  const start = stampSeconds(active);
  const later = [...frames]
    .map(stampSeconds)
    .filter((at) => at > start)
    .sort((a, b) => a - b)[0];
  const end = later ?? start + 600;
  const at = seconds(detection?.detected_at);
  return Number.isFinite(at) && at >= start && at < end;
}

/**
 * @param {Array<{platform: string, product: string, detected_at: string}>} detections
 * @param {string} sliderTime ISO-8601
 * @returns {Array<object>} each with `state` ('solid' | 'dimmed') and `ageSeconds`
 */
export function visibleOverpasses(detections, sliderTime) {
  const now = seconds(sliderTime);
  const groups = new Map();

  for (const detection of detections) {
    const at = seconds(detection.detected_at);
    if (at > now + TOLERANCE_SECONDS) continue; // the future is not yet observed

    const groupKey = key(detection);
    const group = groups.get(groupKey) ?? [];
    group.push({ detection, at });
    groups.set(groupKey, group);
  }

  const out = [];
  for (const group of groups.values()) {
    // A pass spans several scan-line timestamps. Cluster adjacent observations, then
    // retain the newest whole cluster rather than only its final minute.
    const ordered = [...group].sort((a, b) => a.at - b.at);
    const passes = [];
    for (const item of ordered) {
      const current = passes.at(-1);
      if (!current || item.at - current.at(-1).at > PASS_GAP_SECONDS) {
        passes.push([item]);
      } else {
        current.push(item);
      }
    }
    for (const { detection, at } of passes.at(-1) ?? []) {
      const age = Math.max(0, Math.round(now - at));
      out.push({
        ...detection,
        state: Math.abs(now - at) <= TOLERANCE_SECONDS ? 'solid' : 'dimmed',
        ageSeconds: age,
      });
    }
  }
  return out;
}

/** Distinct acquisition instants, for drawing pass markers on the slider itself. */
export function overpassMarkers(detections) {
  const marks = new Map();
  for (const detection of detections) {
    const stamp = detection.detected_at;
    const existing = marks.get(stamp) ?? { at: stamp, platforms: new Set(), count: 0 };
    existing.platforms.add(detection.platform);
    existing.count += 1;
    marks.set(stamp, existing);
  }
  return [...marks.values()]
    .map((m) => ({ at: m.at, platforms: [...m.platforms], count: m.count }))
    .sort((a, b) => a.at.localeCompare(b.at));
}

/** Human-readable age, for the label beside a dimmed pass. */
export function formatAge(ageSeconds) {
  if (ageSeconds < 60) return `${ageSeconds}s ago`;
  const minutes = Math.round(ageSeconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  return `${(minutes / 60).toFixed(1)} h ago`;
}
