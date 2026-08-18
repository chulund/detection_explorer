import { describe, expect, it, vi } from 'vitest';
import { popupFields, popupTitle, renderPopup } from './popup.js';

const detection = (extra = {}) => ({
  id: 'firms:VIIRS_SNPP_SP:2026-04-09:0429:-32.20620:145.57617',
  source: 'firms', data_nature: 'static', computation: 'retrieved',
  detected_at: '2026-04-09T04:29:00Z',
  lat: -32.2062, lon: 145.57617,
  frp_mw: 6.58, confidence_native: 'n', confidence_scheme: 'viirs_categorical',
  brightness_k: 334.45, brightness_channel: 'VIIRS I4 3.74 um',
  platform: 'Suomi-NPP', instrument: 'VIIRS', product: 'VIIRS_SNPP_SP',
  algorithm: 'VIIRS_SNPP_SP', algorithm_version: '2',
  footprint_method: 'polar_reconstructed', footprint_side: 'ambiguous',
  footprint_status: 'experimental',
  ...extra,
});

const value = (fields, label) => fields.find((f) => f.label === label)?.value;

describe('popupFields', () => {
  const fields = popupFields(detection());

  it('names the sensor and the platform', () => {
    expect(value(fields, 'Sensor')).toBe('VIIRS');
    expect(value(fields, 'Platform')).toBe('Suomi-NPP');
  });

  it('names the algorithm with its version', () => {
    expect(value(fields, 'Algorithm')).toBe('VIIRS_SNPP_SP 2');
  });

  it('gives the detection time in UTC', () => {
    expect(value(fields, 'Observed (UTC)')).toBe('2026-04-09 04:29:00Z');
  });

  // 04:29Z on 9 April is 14:29 in Sydney, which is AEST rather than daylight time.
  it('gives the same instant in local time, so nobody has to convert it', () => {
    expect(value(fields, 'Observed (local)')).toContain('14:29');
  });

  it('gives FRP in megawatts', () => {
    expect(value(fields, 'FRP')).toBe('6.6 MW');
  });

  // The channel is the point. Four sources report a Kelvin number from four different
  // bands, and an unlabelled figure would invite comparing 3.74 um against 4 um.
  it('gives brightness temperature with the band it was measured in', () => {
    expect(value(fields, 'Brightness')).toBe('334.4 K · VIIRS I4 3.74 um');
  });

  it('keeps the native confidence and says which scheme it is on', () => {
    expect(value(fields, 'Confidence')).toBe('n (viirs_categorical)');
  });

  it('gives the position to five decimals', () => {
    expect(value(fields, 'Position')).toBe('-32.20620, 145.57617');
  });

  it('omits a field rather than printing a dash for it', () => {
    const bare = popupFields(detection({ frp_mw: null, brightness_k: null }));
    expect(value(bare, 'FRP')).toBeUndefined();
    expect(value(bare, 'Brightness')).toBeUndefined();
  });

  it('treats an FRP of -1 as absent, which is how DEA says unknown', () => {
    expect(value(popupFields(detection({ frp_mw: -1 })), 'FRP')).toBeUndefined();
  });

  it('returns nothing at all for nothing at all', () => {
    expect(popupFields(null)).toEqual([]);
  });

  it('marks numeric fields, so they can be set in a monospace column', () => {
    const frp = fields.find((f) => f.label === 'FRP');
    const sensor = fields.find((f) => f.label === 'Sensor');
    expect(frp.numeric).toBe(true);
    expect(sensor.numeric).toBeFalsy();
  });
});

describe('popupTitle', () => {
  it('leads with the algorithm and the sensor', () => {
    expect(popupTitle(detection())).toBe('VIIRS_SNPP_SP · VIIRS');
  });

  it('carries the caveat chips the record earns', () => {
    expect(popupTitle(detection(), true)).toBeTruthy();
  });
});

describe('renderPopup', () => {
  /** A document just real enough to record what the renderer does to it. */
  const fakeDocument = () => {
    const made = [];
    const create = (tag) => {
      const node = {
        tag, className: '', children: [], _text: undefined,
        setAttribute: vi.fn(),
        appendChild(child) { this.children.push(child); return child; },
        set textContent(v) { this._text = v; },
        get textContent() { return this._text; },
      };
      made.push(node);
      return node;
    };
    return { createElement: vi.fn(create), _made: made };
  };

  it('builds the fields as elements', () => {
    const doc = fakeDocument();
    renderPopup(doc, detection());
    expect(doc.createElement).toHaveBeenCalled();
    const texts = doc._made.map((n) => n.textContent).filter(Boolean);
    expect(texts.join(' ')).toContain('Suomi-NPP');
  });

  // Every value here originates in an external feed. Assigning one to innerHTML would let
  // a feed put markup into the page, so the renderer must never reach for it.
  it('writes values as text and never as markup', () => {
    const doc = fakeDocument();
    renderPopup(doc, detection({ platform: '<img src=x onerror=alert(1)>' }));
    for (const node of doc._made) {
      expect(node.innerHTML).toBeUndefined();
    }
    const texts = doc._made.map((n) => n.textContent).filter(Boolean);
    expect(texts).toContain('<img src=x onerror=alert(1)>');   // text, not parsed
  });

  it('renders nothing for no detection', () => {
    const doc = fakeDocument();
    expect(renderPopup(doc, null)).toBeNull();
  });
});
