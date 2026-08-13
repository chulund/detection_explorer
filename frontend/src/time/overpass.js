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

/** Half the AHI cadence: within this, a polar detection is contemporaneous with the frame. */
export const TOLERANCE_SECONDS = 300;

const key = (d) => `${d.platform ?? 'unknown'}::${d.product ?? 'unknown'}`;

const seconds = (iso) => Date.parse(iso) / 1000;

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
    // Within a platform and product, keep the most recent pass at or before the cursor.
    const latest = Math.max(...group.map((g) => g.at));
    for (const { detection, at } of group) {
      if (at !== latest) continue;
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
