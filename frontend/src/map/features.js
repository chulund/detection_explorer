/**
 * Turning API and run output into things the map can draw.
 *
 * Kept out of the component because these are the two places the map has silently shown
 * nothing. A run's rows used to become Point features and were handed to a fill layer,
 * which cannot draw a point, so a genuine computation rendered as an empty map. And a
 * 375 m footprint at a state-wide zoom is a tenth of a screen pixel, so the footprint
 * layers need a companion that can be seen before the polygon can.
 */

import { detectionKey, sensorClassFor } from './taxonomy.js';

/** "20260409040000" -> "2026-04-09T04:00:00Z" */
export const isoFromStamp = (s) =>
  `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}T` +
  `${s.slice(8, 10)}:${s.slice(10, 12)}:${s.slice(12, 14) || '00'}Z`;

/** Fallback colour: grey, and visible, so a missing assignment shows rather than hides. */
const NO_COLOUR = '#9aa0a6';

/** The AHI band BRIGHT detects on. Named, because 3.9 um is not VIIRS' 3.74 um. */
const AHI_FIRE_CHANNEL = 'AHI B07 3.9 um';

const number = (value) => {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

/**
 * BRIGHT run output as map features.
 *
 * The row's own pixel polygon is used when the backend could join it to the sensor grid.
 * When it could not, the detection still appears, at its reported position and saying so:
 * `footprint_method` stays null rather than claiming a grid join that did not happen.
 *
 * Marked `replay` and `computed`, never `live`. It is a real computation over real April
 * inputs, which is not the same thing as a current observation.
 */
export function brightFeatures(runFrames, { algorithmVersion = '2.0' } = {}) {
  const out = [];
  for (const frame of runFrames ?? []) {
    for (const row of frame.detections ?? []) {
      const lon = number(row.lon);
      const lat = number(row.lat);
      if (lon === null || lat === null) continue;
      const footprint = row.footprint ?? null;
      const brightness = number(row.mir);
      out.push({
        type: 'Feature',
        geometry: footprint ?? { type: 'Point', coordinates: [lon, lat] },
        properties: {
          id: `bright:${frame.frame}:${row.x}:${row.y}`,
          source: 'bright', data_nature: 'replay', computation: 'computed',
          detected_at: isoFromStamp(frame.frame),
          platform: 'Himawari-9', instrument: 'AHI', product: 'BRIGHT AHI',
          algorithm: 'BRIGHT', algorithm_version: algorithmVersion,
          lat, lon,
          frp_mw: number(row.frp),
          confidence_native: row.confidence, confidence_scheme: 'bright_percent',
          brightness_k: brightness,
          brightness_channel: brightness === null ? null : AHI_FIRE_CHANNEL,
          region: row.region,
          footprint_method: footprint ? 'ahi_grid' : null,
          footprint_status: footprint ? 'validated' : null,
          footprint_kind: footprint ? 'satellite_pixel_footprint' : null,
        },
      });
    }
  }
  return out;
}

/**
 * Tag every feature with what the map needs to draw it.
 *
 * One source carries every detection whatever produced it, so the things that used to be
 * decided by which source a feature sat in — colour, marker fade, dashed outline — have
 * to travel on the feature itself. The underscore prefix marks them as presentation,
 * added here and never coming from a provider.
 */
export function decorateFeatures(features, { colours = {}, dimmedIds } = {}) {
  const dim = dimmedIds ?? new Set();
  return (features ?? []).map((feature) => {
    const properties = feature.properties ?? {};
    const key = detectionKey(properties);
    const geometryType = feature.geometry?.type;
    return {
      ...feature,
      properties: {
        ...properties,
        _key: key,
        _colour: colours[key] ?? NO_COLOUR,
        _class: sensorClassFor(properties.instrument).id,
        _hasFootprint: geometryType === 'Polygon' || geometryType === 'MultiPolygon',
        _ambiguous: properties.footprint_side === 'ambiguous',
        _dimmed: dim.has(properties.id),
      },
    };
  });
}

/**
 * One point per detection, for the marker that stands in for a footprint too small to see.
 *
 * Taken from the record's reported latitude and longitude rather than from a polygon
 * centroid, so the marker sits where the source says the detection was. A circle layer
 * over a polygon would otherwise draw one circle per vertex.
 */
export function dotsFrom(collection) {
  const features = Array.isArray(collection) ? collection : collection?.features;
  return {
    type: 'FeatureCollection',
    features: (features ?? []).flatMap((feature) => {
      const lon = Number(feature.properties?.lon);
      const lat = Number(feature.properties?.lat);
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) return [];
      return [{
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [lon, lat] },
        properties: feature.properties,
      }];
    }),
  };
}

/** A FeatureCollection wrapper, because MapLibre sources want one. */
export const collection = (features) => ({
  type: 'FeatureCollection', features: features ?? [],
});
