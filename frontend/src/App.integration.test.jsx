/** @vitest-environment jsdom */

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  getScenes: vi.fn(), getStatus: vi.fn(), getDetections: vi.fn(),
}));

vi.mock('./api.js', () => ({
  ...api,
  exportUrl: (scene, format) => `/export/${scene}.${format}`,
}));

vi.mock('./map/MapView.jsx', () => ({
  default: ({ features, onSelect }) => (
    <div className="map" data-testid="map">
      {(features ?? []).map((feature) => feature.properties.id).join(',')}
      <button type="button" onClick={() => onSelect(features?.[0]?.properties ?? null)}>
        Select first
      </button>
    </div>
  ),
}));

vi.mock('./panels/RunPanel.jsx', () => ({
  default: ({ onFrames }) => (
    <button type="button" onClick={() => onFrames([{
      frame: '20260409045000',
      detections: [{ x: '1', y: '2', lon: '148', lat: '-32', mir: '330' }],
    }])}>
      Inject run
    </button>
  ),
}));

const { default: App } = await import('./App.jsx');

const scenes = [
  {
    id: 'april-9-demo', title: 'April 9 demo', frames: ['20260409045000'],
    window: { start: '2026-04-09T04:00:00Z', end: '2026-04-09T05:00:00Z' },
  },
  {
    id: 'current', title: 'Current', frames: [],
    window: { start: '2026-08-18T00:00:00Z', end: '2026-08-18T00:30:00Z' },
  },
];

const payload = (scene, feature) => ({
  scene,
  sources: { dea: { available: true, count: 1, products_queried: ['*'] } },
  features: [feature],
});

const feature = (id, detectedAt) => ({
  type: 'Feature', geometry: { type: 'Point', coordinates: [148, -32] },
  properties: {
    id, source: 'dea', product: 'AFIMG', algorithm: 'AFIMG', algorithm_version: '6',
    instrument: 'VIIRS', platform: 'Suomi-NPP', lat: -32, lon: 148,
    detected_at: detectedAt,
  },
});

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
const click = (element) => element.dispatchEvent(
  new MouseEvent('click', { bubbles: true, cancelable: true }),
);

describe('App scene isolation', () => {
  let container;
  let root;

  beforeEach(async () => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    api.getScenes.mockResolvedValue({ scenes });
    api.getStatus.mockResolvedValue({ context: {}, providers: { bright: {} } });
    api.getDetections.mockImplementation((id) => Promise.resolve(
      id === 'current'
        ? payload(scenes[1], feature('current:1', '2026-08-18T00:20:00Z'))
        : payload(scenes[0], feature('april:1', '2026-04-09T04:47:00Z')),
    ));
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => { root.render(<App />); await flush(); });
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.clearAllMocks();
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  });

  it('drops completed BRIGHT frames before showing another scene', async () => {
    const runButton = [...container.querySelectorAll('button')]
      .find((button) => button.textContent.includes('Inject run'));
    await act(async () => click(runButton));
    expect(container.querySelector('[data-testid="map"]').textContent).toContain('bright:');

    const currentButton = [...container.querySelectorAll('button')]
      .find((button) => button.textContent.trim() === 'Current');
    await act(async () => { click(currentButton); await flush(); });

    const ids = container.querySelector('[data-testid="map"]').textContent;
    expect(ids).toContain('current:1');
    expect(ids).not.toContain('bright:');
    expect(ids).not.toContain('april:1');
  });

  it('clears a selection when its detection layer is switched off', async () => {
    const selectButton = [...container.querySelectorAll('button')]
      .find((button) => button.textContent.trim() === 'Select first');
    await act(async () => click(selectButton));
    expect(container.textContent).not.toContain('Select a detection on the map');

    const layerToggle = container.querySelector('.layer-row input[type="checkbox"]');
    await act(async () => click(layerToggle));

    expect(container.textContent).toContain('Select a detection on the map');
  });

  it('ignores a slower response from a scene that is no longer selected', async () => {
    let resolveCurrent;
    api.getDetections.mockImplementation((id) => {
      if (id === 'current') {
        return new Promise((resolve) => { resolveCurrent = resolve; });
      }
      return Promise.resolve(payload(
        scenes[0], feature('april:new', '2026-04-09T04:47:00Z'),
      ));
    });
    const button = (label) => [...container.querySelectorAll('button')]
      .find((candidate) => candidate.textContent.trim() === label);

    await act(async () => click(button('Current')));
    await act(async () => { click(button('April 9 demo')); await flush(); });
    await act(async () => {
      resolveCurrent(payload(
        scenes[1], feature('current:late', '2026-08-18T00:20:00Z'),
      ));
      await flush();
    });

    const ids = container.querySelector('[data-testid="map"]').textContent;
    expect(ids).toContain('april:new');
    expect(ids).not.toContain('current:late');
  });
});
