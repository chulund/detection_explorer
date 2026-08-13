/**
 * Contextual map layers: what was burning before, what can burn now, and who it affects.
 *
 * Detections say where heat is. They say nothing about whether the ground is dry, whether it
 * burnt last season, or whose council area it falls in, and those are the questions a person
 * looking at a fire map actually has. These layers answer them.
 *
 * Every endpoint here was checked before being written down, because a layer catalogue full
 * of plausible-looking dead URLs is worse than no catalogue: it fails silently and quietly
 * teaches people the tool is broken. The two things that bit during that check are recorded
 * on the layers they affected.
 *
 * All of these are raster WMS tiles. That is deliberate, for the same reason the basemap is
 * raster: images have no sprite sheet, no glyph server and no worker-side parsing, so there
 * is far less that can stall.
 */

const DEA_WMS = 'https://ows.dea.ga.gov.au/';
const NPWS_FIRE_WMS =
  'https://mapprod3.environment.nsw.gov.au/arcgis/services/Fire/NPWS_Fire_History/MapServer/WMSServer';
const NSW_ADMIN_WMS =
  'https://maps.six.nsw.gov.au/arcgis/services/public/NSW_Administrative_Boundaries/MapServer/WMSServer';
const OWM_TILES = 'https://tile.openweathermap.org/map';

/**
 * WMS 1.1.1 GetMap as an XYZ template.
 *
 * `styles` is always sent, even empty. Omitting it is legal per the spec but the NSW ArcGIS
 * services reject the request outright with `StylesNotDefined`, which is how an hour gets
 * lost to a layer that returns XML instead of a picture.
 */
function wmsTemplate(base, layer, { styles = '', extra = {} } = {}) {
  const params = new URLSearchParams({
    service: 'WMS',
    version: '1.1.1',
    request: 'GetMap',
    layers: layer,
    styles,
    width: '256',
    height: '256',
    srs: 'EPSG:3857',
    format: 'image/png',
    transparent: 'true',
    ...extra,
  });
  // bbox is a MapLibre placeholder, so it must not be URL-encoded by URLSearchParams.
  return `${base}?${params.toString()}&bbox={bbox-epsg-3857}`;
}

const DEA_ATTRIB = '© Digital Earth Australia / Geoscience Australia';
const NSW_ATTRIB = '© NSW Government';

export const CONTEXT_LAYERS = [
  // ---------------------------------------------------------------- fuel and ground
  {
    id: 'fmc',
    label: 'Fuel moisture content',
    hint: 'Sentinel-2 mosaic. Below about 150% indicates elevated fire risk.',
    group: 'Fuel and ground cover',
    url: wmsTemplate(DEA_WMS, 'ga_s2m_fmc_mosaic'),
    opacity: 0.6,
    attribution: DEA_ATTRIB,
  },
  {
    id: 'landcover',
    label: 'Land cover',
    hint: 'What is on the ground, and therefore what is available to burn.',
    group: 'Fuel and ground cover',
    url: wmsTemplate(DEA_WMS, 'ga_ls_landcover'),
    opacity: 0.55,
    attribution: DEA_ATTRIB,
  },
  {
    id: 'fractional_cover',
    label: 'Fractional cover',
    hint: 'Green vegetation, dry vegetation and bare soil, from annual Landsat composites.',
    group: 'Fuel and ground cover',
    url: wmsTemplate(DEA_WMS, 'ga_ls_fc_pc_cyear_3'),
    opacity: 0.5,
    attribution: DEA_ATTRIB,
  },
  {
    id: 'water',
    label: 'Water observations',
    hint: 'How often surface water is present. Persistent water is both a barrier and a '
        + 'resource.',
    group: 'Fuel and ground cover',
    url: wmsTemplate(DEA_WMS, 'ga_ls_wo_fq_cyear_3'),
    opacity: 0.5,
    attribution: DEA_ATTRIB,
  },

  // ---------------------------------------------------------------- fire history
  {
    id: 'fire_history',
    label: 'NPWS fire history',
    hint: 'Wildfires and prescribed burns recorded by NSW NPWS. Recently burnt ground '
        + 'carries less fuel.',
    group: 'Fire history',
    url: wmsTemplate(NPWS_FIRE_WMS, '0'),
    opacity: 0.55,
    attribution: `${NSW_ATTRIB} / NPWS`,
  },

  // ---------------------------------------------------------------- who it affects
  {
    id: 'lga',
    label: 'Local government areas',
    hint: 'Which council a detection falls in, which is usually the first question asked.',
    group: 'Boundaries',
    url: wmsTemplate(NSW_ADMIN_WMS, '1'),
    opacity: 0.7,
    attribution: NSW_ATTRIB,
  },
  {
    id: 'reserves',
    label: 'NPWS reserves',
    hint: 'National parks and reserves.',
    group: 'Boundaries',
    url: wmsTemplate(NSW_ADMIN_WMS, '6'),
    opacity: 0.5,
    attribution: NSW_ATTRIB,
  },
];

/**
 * Weather layers, which need a key.
 *
 * Kept apart from the rest because they are the only layers here that can be unavailable.
 * When no key is configured they are not offered at all, rather than being offered and then
 * failing: a checkbox that does nothing is a worse answer than an honest absence.
 */
export const WEATHER_LAYERS = [
  { id: 'wx_temp', label: 'Temperature', tile: 'temp_new', group: 'Weather', opacity: 0.5 },
  { id: 'wx_wind', label: 'Wind speed', tile: 'wind_new', group: 'Weather', opacity: 0.5 },
  { id: 'wx_precip', label: 'Precipitation', tile: 'precipitation_new', group: 'Weather',
    opacity: 0.55 },
  { id: 'wx_clouds', label: 'Cloud cover', tile: 'clouds_new', group: 'Weather',
    opacity: 0.45 },
];

export function weatherLayers(apiKey) {
  if (!apiKey) return [];
  return WEATHER_LAYERS.map((layer) => ({
    ...layer,
    hint: 'Current conditions, not conditions at the time of the detections.',
    url: `${OWM_TILES}/${layer.tile}/{z}/{x}/{y}.png?appid=${apiKey}`,
    attribution: '© OpenWeatherMap',
    liveWhileSceneIsHistorical: true,
  }));
}

/** Everything on offer, given what is configured. */
export function availableContextLayers(weatherKey) {
  return [...CONTEXT_LAYERS, ...weatherLayers(weatherKey)];
}

/** Catalogue grouped for the layer panel, in declaration order. */
export function groupedContextLayers(weatherKey) {
  const groups = new Map();
  for (const layer of availableContextLayers(weatherKey)) {
    if (!groups.has(layer.group)) groups.set(layer.group, []);
    groups.get(layer.group).push(layer);
  }
  return [...groups.entries()].map(([group, layers]) => ({ group, layers }));
}
