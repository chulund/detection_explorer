import { afterEach, describe, expect, it, vi } from 'vitest';
import { followRun } from './api.js';

class FakeEventSource {
  static CLOSED = 2;
  static last = null;

  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.readyState = 1;
    FakeEventSource.last = this;
  }

  addEventListener(kind, listener) {
    this.listeners[kind] = listener;
  }

  emit(kind, payload) {
    this.listeners[kind]?.({ data: JSON.stringify(payload), lastEventId: '1' });
  }

  close() {
    this.readyState = FakeEventSource.CLOSED;
  }
}

describe('followRun', () => {
  afterEach(() => { delete globalThis.EventSource; });

  it('closes a cancelled stream without relabelling cancellation as failure', () => {
    globalThis.EventSource = FakeEventSource;
    const onCancelled = vi.fn();
    const onError = vi.fn();
    followRun('run-1', { onCancelled, onError });

    FakeEventSource.last.emit('run.state', { state: 'cancelled' });

    expect(FakeEventSource.last.readyState).toBe(FakeEventSource.CLOSED);
    expect(onCancelled).toHaveBeenCalledWith({ state: 'cancelled' });
    expect(onError).not.toHaveBeenCalled();
  });
});
