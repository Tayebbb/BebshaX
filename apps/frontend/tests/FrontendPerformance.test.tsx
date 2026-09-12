import { act, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BoundedReadCache } from '../src/services/readCache';
import { clearRouteTimings, readRouteTimings, setRouteTimingEnabled, startRouteTiming, useRouteReady, beginOperationTiming } from '../src/performance/routeTiming';
import * as timing from '../src/performance/routeTiming';

describe('Frontend bounded caching and privacy-safe timing', () => {
  afterEach(() => { setRouteTimingEnabled(false); clearRouteTimings(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it('coalesces matching saved reads and returns independent copies', async () => {
    const cache = new BoundedReadCache<{ values: string[] }>();
    const read = vi.fn(async () => ({ values: ['complete saved value'] }));
    const [first, second] = await Promise.all([cache.read('tenant:revision1', read), cache.read('tenant:revision1', read)]);
    first.values.push('local change');
    expect(second.values).toEqual(['complete saved value']);
    expect(read).toHaveBeenCalledTimes(1);
    await cache.read('tenant:revision2', read);
    expect(read).toHaveBeenCalledTimes(2);
  });

  it('does not install an invalidated in-flight read and evicts within entry and byte bounds', async () => {
    const cache = new BoundedReadCache<string>(2, 32);
    let finish!: (value: string) => void;
    const pending = cache.read('old', () => new Promise((resolve) => { finish = resolve; }));
    cache.invalidate();
    finish('old');
    await pending;
    expect(cache.stats().entries).toBe(0);
    for (const key of ['first', 'second', 'third']) await cache.read(key, async () => key);
    expect(cache.stats().entries).toBe(2);
    await cache.read('oversize', async () => 'x'.repeat(100));
    expect(cache.stats().bytes).toBeLessThanOrEqual(32);
  });

  it('records only explicit primary readiness and bounded route groups without identifiers or queries', () => {
    let frameId = 0;
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.push(callback); return ++frameId; });
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    const Ready = ({ ready }: { ready: boolean }) => { useRouteReady(ready); return null; };
    setRouteTimingEnabled(true);
    startRouteTiming('/research/private-study-identifier/step3?private=never-record');
    const view = render(<Ready ready={false} />);
    expect(readRouteTimings()).toEqual([]);
    view.rerender(<Ready ready />);
    act(() => { frames.shift()?.(0); frames.shift()?.(0); });
    expect(readRouteTimings()).toHaveLength(1);
    expect(readRouteTimings()[0]).toMatchObject({ route: 'workflow-3', stage: 'primary-content' });
    expect(JSON.stringify(readRouteTimings())).not.toMatch(/private-study|never-record/);
    const operation = beginOperationTiming();
    operation('ai-first-text');
    operation('canonical-response');
    expect(readRouteTimings().map((sample) => sample.stage)).toEqual(['primary-content', 'ai-first-text', 'canonical-response']);
    expect(readRouteTimings().some((sample) => sample.stage === 'saved-completion')).toBe(false);
  });

  it('can enable primary-content instrumentation after the view has already mounted', () => {
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.push(callback); return frames.length; });
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    const Ready = () => { useRouteReady(true); return null; };
    render(<Ready />);

    act(() => { setRouteTimingEnabled(true); });
    act(() => { frames.shift()?.(0); frames.shift()?.(0); });

    expect(readRouteTimings()).toHaveLength(1);
    expect(readRouteTimings()[0].stage).toBe('primary-content');
  });

  it('counts route starts, abandoned loads, and settled outcomes separately without retaining resource IDs', () => {
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.push(callback); return frames.length; });
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    const Ready = ({ outcome }: { outcome: 'empty' | 'error' }) => { useRouteReady(true, outcome); return null; };
    setRouteTimingEnabled(true);
    clearRouteTimings();
    startRouteTiming('/research/private-first/step2');
    startRouteTiming('/research/private-second/step3');
    const view = render(<Ready outcome="empty" />);
    act(() => { frames.shift()?.(0); frames.shift()?.(0); });
    const first = readRouteTimings()[0] as typeof readRouteTimings extends () => (infer Sample)[] ? Sample & { navigationId?: number } : never;
    expect(first.navigationId).toEqual(expect.any(Number));
    startRouteTiming('/research/private-second/step5');
    view.rerender(<Ready outcome="error" />);
    act(() => { frames.shift()?.(0); frames.shift()?.(0); });

    expect(timing).toHaveProperty('readRouteTimingCounters');
    const counters = (timing as typeof timing & { readRouteTimingCounters: () => Record<string, unknown> }).readRouteTimingCounters();
    expect(counters).toMatchObject({
      'workflow-2': { started: 1, content: 0, empty: 0, error: 0, abandoned: 1 },
      'workflow-3': { started: 1, content: 0, empty: 1, error: 0, abandoned: 0 },
      'workflow-5': { started: 1, content: 0, empty: 0, error: 1, abandoned: 0 },
    });
    expect(JSON.stringify(counters)).not.toContain('private-');
    expect(readRouteTimings()[1]).toHaveProperty('navigationId', (first.navigationId ?? 0) + 1);
  });

  it('measures cold primary content from navigation start when opted in before module loading', async () => {
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.push(callback); return frames.length; });
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    vi.stubGlobal('__bebshaxMeasureRoutes', true);
    vi.spyOn(performance, 'now').mockReturnValue(1250);
    vi.resetModules();
    const coldTiming = await import('../src/performance/routeTiming');
    const Ready = () => { coldTiming.useRouteReady(true); return null; };
    const view = render(<Ready />);
    act(() => { frames.shift()?.(0); frames.shift()?.(0); });

    try {
      expect(coldTiming.readRouteTimings()).toEqual([expect.objectContaining({ stage: 'primary-content', durationMs: 1250 })]);
    } finally {
      view.unmount();
      coldTiming.setRouteTimingEnabled(false);
      coldTiming.clearRouteTimings();
    }
  });
});