import { useEffect, useSyncExternalStore } from 'react';
import { parseDashboardPath, isDashboardPath } from '../utils/dashboardRoute';
import { useNavigation } from '../context/NavigationContext';

export type TimingStage = 'primary-content' | 'ai-first-text' | 'canonical-response' | 'saved-completion';
export interface RouteTimingSample {
  navigationId: number;
  operationId?: number;
  route: string;
  stage: TimingStage;
  durationMs: number;
  outcome: 'content' | 'empty' | 'error';
  mode: 'mock' | 'live';
}
export interface RouteTimingCounters { started: number; content: number; empty: number; error: number; abandoned: number; }
interface Measurement { id: number; operationId?: number; route: string; started: number; stages: Set<TimingStage>; }
let enabled = false;
let sequence = 0;
let operationSequence = 0;
let active: Measurement | null = null;
let samples: RouteTimingSample[] = [];
let counters: Record<string, RouteTimingCounters> = {};
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
const isEnabled = () => enabled;

function abandonActive(): void {
  if (active && !active.stages.has('primary-content')) counters[active.route].abandoned += 1;
}

function routeGroup(path: string): string {
  const pathname = new URL(path, 'https://timing.invalid').pathname;
  if (/^\/(auth(?:\/|$)|signin$|signup$|login$|register$)/.test(pathname)) return 'auth';
  if (!isDashboardPath(pathname)) return 'landing';
  const route = parseDashboardPath(path);
  return route.tab === 'study-workflow' ? `workflow-${route.step ?? 'saved'}` : route.tab;
}

export function startRouteTiming(path: string, startedAtMs = performance.now()): void {
  if (!enabled) return;
  abandonActive();
  active = { id: ++sequence, route: routeGroup(path), started: startedAtMs, stages: new Set() };
  counters[active.route] ??= { started: 0, content: 0, empty: 0, error: 0, abandoned: 0 };
  counters[active.route].started += 1;
}

export function setRouteTimingEnabled(value: boolean): void {
  if (enabled === value) return;
  if (!value) abandonActive();
  enabled = value;
  active = null;
  if (value) startRouteTiming(`${window.location.pathname}${window.location.search}`);
  listeners.forEach((listener) => listener());
}

export function readRouteTimings(): RouteTimingSample[] { return samples.map((sample) => ({ ...sample })); }
export function readRouteTimingCounters(): Record<string, RouteTimingCounters> {
  return Object.fromEntries(Object.entries(counters).map(([route, value]) => [route, { ...value }]));
}
export function clearRouteTimings(): void { samples = []; counters = {}; active = null; }

function record(measurement: Measurement | null, stage: TimingStage, outcome: RouteTimingSample['outcome']): void {
  if (!enabled || !measurement || active?.id !== measurement.id || measurement.stages.has(stage)) return;
  measurement.stages.add(stage);
  const durationMs = Math.max(0, performance.now() - measurement.started);
  if (stage === 'primary-content') counters[measurement.route][outcome] += 1;
  samples.push({ navigationId: measurement.id, ...(measurement.operationId ? { operationId: measurement.operationId } : {}), route: measurement.route, stage, durationMs, outcome, mode: import.meta.env.VITE_MOCK === '1' || import.meta.env.MODE === 'test' ? 'mock' : 'live' });
  if (samples.length > 200) samples.shift();
  const name = `bebshax:${measurement.route}:${stage}`;
  performance.clearMarks?.(name);
  performance.mark?.(name);
}

export function beginOperationTiming(): (stage: Exclude<TimingStage, 'primary-content'>) => void {
  const measurement = active ? { ...active, operationId: ++operationSequence, started: performance.now(), stages: new Set<TimingStage>() } : null;
  return (stage) => record(measurement, stage, 'content');
}

export function useRouteReady(ready: boolean, outcome: RouteTimingSample['outcome'] = 'content'): void {
  const { currentPath, currentSearch } = useNavigation();
  const tracking = useSyncExternalStore(subscribe, isEnabled, () => false);
  useEffect(() => {
    if (!ready || !tracking) return;
    const measurement = active;
    let secondFrame = 0;
    const firstFrame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(() => record(measurement, 'primary-content', outcome));
    });
    return () => { cancelAnimationFrame(firstFrame); cancelAnimationFrame(secondFrame); };
  }, [ready, outcome, currentPath, currentSearch, tracking]);
}

declare global {
  interface Window {
    __bebshaxMeasureRoutes?: boolean;
    __bebshaxTiming?: { enable: typeof setRouteTimingEnabled; read: typeof readRouteTimings; clear: typeof clearRouteTimings; counters: typeof readRouteTimingCounters };
  }
}
if (typeof window !== 'undefined') {
  window.__bebshaxTiming = { enable: setRouteTimingEnabled, read: readRouteTimings, clear: clearRouteTimings, counters: readRouteTimingCounters };
  if (window.__bebshaxMeasureRoutes === true) {
    enabled = true;
    startRouteTiming(`${window.location.pathname}${window.location.search}`, 0);
  }
}