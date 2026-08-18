/**
 * Which algorithm, on which sensor, from which platform.
 *
 * The interface used to offer three toggles named after data sources. That understated
 * what it was showing: the demo hour carries nine distinct algorithm and sensor pairings,
 * and DEA alone serves five of them. Naming the source told a reader almost nothing —
 * "DEA" covers a VIIRS product, a MODIS-named product, and two generations of BRIGHT on
 * Himawari, which are not the same observation in any useful sense.
 *
 * So the taxonomy is derived from the records rather than declared in advance. A product
 * that appears in the feed gets a row whether or not anyone anticipated it.
 */

/**
 * Orbit, cadence and pixel size per instrument.
 *
 * `resolutionM` is load-bearing: it decides the zoom at which a footprint becomes big
 * enough to read, and therefore when the marker standing in for it fades out.
 */
export const SENSOR_CLASSES = {
  AHI: {
    id: 'geostationary', orbit: 'geostationary', label: 'Geostationary',
    cadence: '10 min', resolution: '2 km', resolutionM: 2000,
  },
  VIIRS: {
    id: 'polar375', orbit: 'polar-orbiting', label: 'Polar',
    cadence: 'overpass', resolution: '375 m', resolutionM: 375,
  },
  MODIS: {
    id: 'polar1km', orbit: 'polar-orbiting', label: 'Polar',
    cadence: 'overpass', resolution: '1 km', resolutionM: 1000,
  },
};

const UNKNOWN_SENSOR = {
  id: 'unknown', orbit: 'unknown', label: 'Unknown',
  cadence: '—', resolution: '—', resolutionM: null,
};

export function sensorClassFor(instrument) {
  return SENSOR_CLASSES[String(instrument ?? '').toUpperCase()] ?? UNKNOWN_SENSOR;
}

/** Recomputed first, then the live feed, then the archive. */
export const SOURCE_ORDER = ['bright', 'firms', 'dea'];

export const SOURCE_LABELS = {
  bright: { label: 'BRIGHT', qualifier: 'recomputed' },
  firms: { label: 'FIRMS Active Fire', qualifier: null },
  dea: { label: 'DEA Hotspots', qualifier: 'archival' },
};

/**
 * What a FIRMS product id means, for rows that have no records to read it from.
 *
 * Only consulted when a product was queried and came back empty, which is the one case
 * where the answer cannot be derived from the data. It mirrors `PLATFORMS` and
 * `_instrument_for` in `backend/app/providers/firms.py`; the backend stays authoritative
 * for anything that actually arrived.
 */
const FIRMS_PRODUCTS = {
  MODIS_SP: { instrument: 'MODIS', platform: 'Terra / Aqua' },
  MODIS_NRT: { instrument: 'MODIS', platform: 'Terra / Aqua' },
  VIIRS_SNPP_SP: { instrument: 'VIIRS', platform: 'Suomi-NPP' },
  VIIRS_SNPP_NRT: { instrument: 'VIIRS', platform: 'Suomi-NPP' },
  VIIRS_NOAA20_SP: { instrument: 'VIIRS', platform: 'NOAA-20' },
  VIIRS_NOAA20_NRT: { instrument: 'VIIRS', platform: 'NOAA-20' },
  VIIRS_NOAA21_NRT: { instrument: 'VIIRS', platform: 'NOAA-21' },
};

/** Stable identity for one algorithm/sensor/platform combination. */
export function detectionKey(properties = {}) {
  const part = (value) => String(value ?? 'unknown');
  return [
    part(properties.source),
    part(properties.product ?? properties.algorithm),
    part(properties.algorithm_version),
    part(properties.instrument),
    part(properties.platform),
  ].join('|');
}

function rowFrom(properties) {
  return {
    key: detectionKey(properties),
    source: String(properties.source ?? 'unknown'),
    product: String(properties.product ?? properties.algorithm ?? 'unknown'),
    algorithm: String(properties.algorithm ?? properties.product ?? 'unknown'),
    version: properties.algorithm_version ? String(properties.algorithm_version) : null,
    instrument: String(properties.instrument ?? 'unknown'),
    platform: String(properties.platform ?? 'unknown'),
    sensorClass: sensorClassFor(properties.instrument),
    count: 0,
    status: 'present',
  };
}

/**
 * Group the scene's records into a layer catalogue.
 *
 * @param features GeoJSON features as served, plus any folded-in run output
 * @param sources  the `sources` block from the detections response, which says what was
 *                 queried as well as what came back
 */
export function buildTaxonomy(features, sources) {
  const byKey = new Map();

  for (const feature of features ?? []) {
    const properties = feature?.properties;
    if (!properties) continue;
    const key = detectionKey(properties);
    if (!byKey.has(key)) byKey.set(key, rowFrom(properties));
    byKey.get(key).count += 1;
  }

  // A product that was asked for and returned nothing still gets a row. Dropping it would
  // let a reader conclude the sensor was never consulted, which is a different claim.
  for (const [source, info] of Object.entries(sources ?? {})) {
    for (const product of info?.products_queried ?? []) {
      if (product === '*') continue;
      const known = [...byKey.values()].some(
        (row) => row.source === source && row.product === product);
      if (known) continue;
      const guess = FIRMS_PRODUCTS[product] ?? { instrument: 'unknown', platform: '—' };
      const key = [source, product, 'unknown', guess.instrument, guess.platform].join('|');
      byKey.set(key, {
        key,
        source,
        product,
        algorithm: product,
        version: null,
        instrument: guess.instrument,
        platform: guess.platform,
        sensorClass: sensorClassFor(guess.instrument),
        count: 0,
        status: info?.available === false ? 'unavailable' : 'empty',
      });
    }
  }

  const groups = new Map();
  for (const row of byKey.values()) {
    const info = sources?.[row.source];
    if (info?.available === false) row.status = 'unavailable';
    if (!groups.has(row.source)) {
      groups.set(row.source, {
        source: row.source,
        ...(SOURCE_LABELS[row.source] ?? { label: row.source, qualifier: null }),
        available: info?.available !== false,
        reason: info?.reason ?? null,
        usedFixture: info?.used_fixture ?? false,
        truncated: info?.truncated ?? false,
        count: 0,
        rows: [],
      });
    }
    const group = groups.get(row.source);
    group.rows.push(row);
    group.count += row.count;
  }

  for (const group of groups.values()) {
    // Busiest first, then alphabetically, so the ordering is deterministic when counts tie.
    group.rows.sort((a, b) => b.count - a.count
      || a.product.localeCompare(b.product)
      || a.platform.localeCompare(b.platform));
  }

  const rank = (source) => {
    const index = SOURCE_ORDER.indexOf(source);
    return index < 0 ? SOURCE_ORDER.length : index;
  };
  return [...groups.values()].sort((a, b) => rank(a.source) - rank(b.source));
}

/** Every key in a taxonomy, in display order. */
export function taxonomyKeys(groups) {
  return (groups ?? []).flatMap((group) => group.rows.map((row) => row.key));
}
