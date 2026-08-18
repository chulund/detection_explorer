import { describe, expect, test } from 'vitest';
import {
  activeSceneFrame, formatAge, inSelectedSceneFrame, overpassMarkers, visibleOverpasses,
} from './overpass.js';

const pass = (platform, product, at) => ({ platform, product, detected_at: at });

describe('visibleOverpasses', () => {
  test('a detection within five minutes renders solid', () => {
    const out = visibleOverpasses(
      [pass('NOAA-20', 'VIIRS_NOAA20_SP', '2026-04-09T04:47:00Z')],
      '2026-04-09T04:50:00Z',
    );
    expect(out[0].state).toBe('solid');
  });

  test('an older pass renders dimmed and carries its age', () => {
    const out = visibleOverpasses(
      [pass('NOAA-20', 'VIIRS_NOAA20_SP', '2026-04-09T04:47:00Z')],
      '2026-04-09T05:25:00Z',
    );
    expect(out[0].state).toBe('dimmed');
    expect(out[0].ageSeconds).toBe(2280);
  });

  test('retention is per platform, so one pass never hides another', () => {
    // The real scene: Suomi-NPP at 04:27, NOAA-20 at 04:47.
    const out = visibleOverpasses(
      [
        pass('Suomi-NPP', 'VIIRS_SNPP_SP', '2026-04-09T04:27:00Z'),
        pass('NOAA-20', 'VIIRS_NOAA20_SP', '2026-04-09T04:47:00Z'),
      ],
      '2026-04-09T04:50:00Z',
    );
    expect(out).toHaveLength(2);
    expect(out.find((o) => o.platform === 'Suomi-NPP').state).toBe('dimmed');
    expect(out.find((o) => o.platform === 'NOAA-20').state).toBe('solid');
  });

  test('a pass in the future is not shown', () => {
    const out = visibleOverpasses(
      [pass('NOAA-20', 'VIIRS_NOAA20_SP', '2026-04-09T04:47:00Z')],
      '2026-04-09T04:10:00Z',
    );
    expect(out).toHaveLength(0);
  });

  test('all detections from the retained pass survive, not just one', () => {
    const out = visibleOverpasses(
      [
        pass('NOAA-20', 'VIIRS_NOAA20_SP', '2026-04-09T04:47:00Z'),
        pass('NOAA-20', 'VIIRS_NOAA20_SP', '2026-04-09T04:47:00Z'),
      ],
      '2026-04-09T04:48:00Z',
    );
    expect(out).toHaveLength(2);
  });

  test('adjacent scan-line timestamps remain part of the same retained pass', () => {
    const out = visibleOverpasses(
      [
        pass('NOAA-20', 'VIIRS_NOAA20_SP', '2026-04-09T04:47:00Z'),
        pass('NOAA-20', 'VIIRS_NOAA20_SP', '2026-04-09T04:48:00Z'),
        pass('NOAA-20', 'VIIRS_NOAA20_SP', '2026-04-09T04:49:00Z'),
      ],
      '2026-04-09T04:50:00Z',
    );
    expect(out).toHaveLength(3);
  });

  test('an earlier pass by the same platform is superseded', () => {
    const out = visibleOverpasses(
      [
        pass('NOAA-20', 'VIIRS_NOAA20_SP', '2026-04-09T02:00:00Z'),
        pass('NOAA-20', 'VIIRS_NOAA20_SP', '2026-04-09T04:47:00Z'),
      ],
      '2026-04-09T04:50:00Z',
    );
    expect(out).toHaveLength(1);
    expect(out[0].detected_at).toBe('2026-04-09T04:47:00Z');
  });
});

describe('selected geostationary frame', () => {
  const frames = ['20260409040000', '20260409041000', '20260409042000'];

  test('uses the latest frame at or before the cursor', () => {
    expect(activeSceneFrame(frames, '2026-04-09T04:18:00Z')).toBe('20260409041000');
  });

  test('keeps only geostationary detections in that ten-minute frame', () => {
    const ahi = (detected_at) => ({ instrument: 'AHI', detected_at });
    expect(inSelectedSceneFrame(ahi('2026-04-09T04:10:00Z'), frames,
      '2026-04-09T04:18:00Z')).toBe(true);
    expect(inSelectedSceneFrame(ahi('2026-04-09T04:19:59Z'), frames,
      '2026-04-09T04:18:00Z')).toBe(true);
    expect(inSelectedSceneFrame(ahi('2026-04-09T04:20:00Z'), frames,
      '2026-04-09T04:18:00Z')).toBe(false);
    expect(inSelectedSceneFrame(ahi('2026-04-09T04:08:21Z'), frames,
      '2026-04-09T04:18:00Z')).toBe(false);
  });

  test('does not apply geostationary frame windows to point-only polar records', () => {
    expect(inSelectedSceneFrame({ instrument: 'VIIRS', detected_at: '2026-04-09T04:08:21Z' },
      frames, '2026-04-09T04:18:00Z')).toBe(true);
  });
});

describe('overpassMarkers', () => {
  test('collapses detections to distinct instants, in order', () => {
    const marks = overpassMarkers([
      pass('NOAA-20', 'VIIRS_NOAA20_SP', '2026-04-09T04:47:00Z'),
      pass('NOAA-20', 'VIIRS_NOAA20_SP', '2026-04-09T04:47:00Z'),
      pass('Suomi-NPP', 'VIIRS_SNPP_SP', '2026-04-09T04:27:00Z'),
    ]);
    expect(marks.map((m) => m.at)).toEqual([
      '2026-04-09T04:27:00Z',
      '2026-04-09T04:47:00Z',
    ]);
    expect(marks[1].count).toBe(2);
  });
});

describe('formatAge', () => {
  test('reads naturally at each scale', () => {
    expect(formatAge(30)).toBe('30s ago');
    expect(formatAge(2280)).toBe('38 min ago');
    expect(formatAge(7200)).toBe('2.0 h ago');
  });
});
