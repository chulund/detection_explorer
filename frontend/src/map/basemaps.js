/**
 * Background maps, all keyless.
 *
 * The reference frontend picks its basemaps from Mapbox with an access token. This one
 * cannot: MapLibre was chosen over Mapbox precisely so that a repository intended to
 * become public needs no credentials, and a basemap picker that goes blank without
 * someone's token would quietly undo that.
 *
 * So these are plain raster XYZ services that need no key. Every one was requested once
 * and confirmed to return an image before being written down, which is the same rule
 * `contextLayers.js` holds itself to: a catalogue of plausible-looking dead URLs fails
 * silently and teaches people the tool is broken.
 *
 * Dark is the default. Thermal footprints and warm detection colours read far better
 * against a dark ground, which is the entire argument for the theme.
 */

const CARTO_ATTRIB = '© OpenStreetMap contributors © CARTO';
const ESRI_ATTRIB = 'Tiles © Esri';

export const BASEMAPS = [
  {
    id: 'dark',
    label: 'Dark',
    hint: 'High contrast for thermal footprints',
    tiles: ['https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'],
    attribution: CARTO_ATTRIB,
    maxzoom: 20,
    // Near-opaque: this one is the ground the detections sit on, not a hint of it.
    opacity: 0.9,
  },
  {
    id: 'satellite',
    label: 'Satellite',
    hint: 'Aerial imagery',
    // Esri serves {z}/{y}/{x}, with row before column. Writing it the XYZ way round
    // produces tiles from somewhere else entirely rather than an error.
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/'
            + 'MapServer/tile/{z}/{y}/{x}'],
    attribution: `${ESRI_ATTRIB}, Maxar, Earthstar Geographics`,
    maxzoom: 19,
    opacity: 1,
  },
  {
    id: 'terrain',
    label: 'Terrain',
    hint: 'Topographic relief and contours',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/'
            + 'MapServer/tile/{z}/{y}/{x}'],
    attribution: `${ESRI_ATTRIB}, USGS, NGA, NASA, CGIAR`,
    maxzoom: 19,
    opacity: 0.85,
  },
  {
    id: 'light',
    label: 'Light',
    hint: 'Neutral road reference',
    tiles: ['https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'],
    attribution: CARTO_ATTRIB,
    maxzoom: 20,
    opacity: 0.9,
  },
];

export const DEFAULT_BASEMAP = 'dark';

export function basemapById(id) {
  return BASEMAPS.find((basemap) => basemap.id === id)
    ?? BASEMAPS.find((basemap) => basemap.id === DEFAULT_BASEMAP);
}

/** A MapLibre raster source spec for one basemap. */
export function basemapSource(basemap) {
  return {
    type: 'raster',
    tiles: basemap.tiles,
    tileSize: 256,
    maxzoom: basemap.maxzoom,
    attribution: basemap.attribution,
  };
}
