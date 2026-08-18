import { describe, expect, it } from 'vitest';
import { BASEMAPS, DEFAULT_BASEMAP, basemapById, basemapSource } from './basemaps.js';

describe('the basemap catalogue', () => {
  it('offers the four kinds a fire analyst needs', () => {
    expect(BASEMAPS.map((b) => b.id)).toEqual(['dark', 'satellite', 'terrain', 'light']);
  });

  it('opens dark, because thermal footprints need the contrast', () => {
    expect(DEFAULT_BASEMAP).toBe('dark');
  });

  // The point of using MapLibre at all. A token here would mean a public clone shows no
  // basemap until someone supplies their own credentials.
  it('needs no api key or access token', () => {
    for (const basemap of BASEMAPS) {
      for (const url of basemap.tiles) {
        expect(url).not.toMatch(/appid|api_?key|access_?token|apikey/i);
        expect(url).not.toMatch(/^mapbox:/);
      }
    }
  });

  it('credits every source', () => {
    for (const basemap of BASEMAPS) {
      expect(basemap.attribution).toBeTruthy();
      expect(basemap.opacity).toBeGreaterThan(0);
      expect(basemap.maxzoom).toBeGreaterThan(0);
    }
  });

  // Esri puts row before column. Written the XYZ way round it returns tiles of somewhere
  // else rather than failing, so the mistake is invisible until someone reads the map.
  it('uses Esri axis order for the Esri services', () => {
    for (const basemap of BASEMAPS) {
      for (const url of basemap.tiles) {
        if (url.includes('arcgisonline.com')) expect(url).toContain('{z}/{y}/{x}');
        else expect(url).toContain('{z}/{x}/{y}');
      }
    }
  });

  it('serves every tile over https', () => {
    for (const basemap of BASEMAPS) {
      for (const url of basemap.tiles) expect(url.startsWith('https://')).toBe(true);
    }
  });
});

describe('basemapById', () => {
  it('finds one by id', () => {
    expect(basemapById('satellite').label).toBe('Satellite');
  });

  it('falls back to the default rather than returning nothing', () => {
    expect(basemapById('nonsense').id).toBe(DEFAULT_BASEMAP);
    expect(basemapById(undefined).id).toBe(DEFAULT_BASEMAP);
  });
});

describe('basemapSource', () => {
  it('builds a raster source MapLibre will accept', () => {
    const source = basemapSource(basemapById('dark'));
    expect(source.type).toBe('raster');
    expect(source.tileSize).toBe(256);
    expect(source.tiles).toHaveLength(1);
    expect(source.attribution).toBeTruthy();
  });
});
