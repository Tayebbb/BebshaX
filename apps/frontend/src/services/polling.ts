import { isRecord } from './interviewProtocol';
import { sessionSignal } from './session';

export interface PollOptions<Value> {
  signal?: AbortSignal;
  intervalMs?: number;
  timeoutMs?: number;
  idleTimeoutMs?: number;
  pauseWhenHidden?: boolean;
  complete: (value: Value) => boolean;
  progress?: (value: Value) => string;
  onUpdate?: (value: Value) => void;
}

function stopped(): Error {
  return Object.assign(new Error('Stopped waiting for updates. The accepted job may still be running.'), { jobContinues: true, isJobFailure: true });
}

function delay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, milliseconds);
    if (signal.aborted) abort();
    else signal.addEventListener('abort', abort, { once: true });
  });
}

function visible(signal: AbortSignal): Promise<void> {
  if (!document.hidden) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const cleanup = () => { document.removeEventListener('visibilitychange', change); signal.removeEventListener('abort', abort); };
    const change = () => { if (!document.hidden) { cleanup(); resolve(); } };
    const abort = () => { cleanup(); reject(signal.reason); };
    document.addEventListener('visibilitychange', change);
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
  });
}

export async function pollSerial<Value>(read: (signal: AbortSignal) => Promise<Value>, options: PollOptions<Value>): Promise<Value> {
  const controller = new AbortController();
  const forwardAbort = () => controller.abort(options.signal?.reason);
  if (options.signal?.aborted) forwardAbort();
  else options.signal?.addEventListener('abort', forwardAbort, { once: true });
  const signal = sessionSignal(controller.signal);
  signal.throwIfAborted();
  const timeout = setTimeout(() => controller.abort(stopped()), options.timeoutMs ?? 600000);
  let idleTimer: ReturnType<typeof setTimeout> | undefined;
  let rejectAbort!: (reason: unknown) => void;
  const aborted = new Promise<never>((_resolve, reject) => { rejectAbort = reject; });
  void aborted.catch(() => {});
  const abort = () => rejectAbort(signal.reason);
  signal.addEventListener('abort', abort, { once: true });
  let failures = 0;
  let previousProgress: string | undefined;
  try {
    for (;;) {
      signal.throwIfAborted();
      if (options.pauseWhenHidden) await visible(signal);
      let value: Value;
      try {
        value = await Promise.race([read(signal), aborted]);
        signal.throwIfAborted();
        failures = 0;
      } catch (error) {
        signal.throwIfAborted();
        const status = isRecord(error) && typeof error.status === 'number' ? error.status : undefined;
        if (!(error instanceof TypeError) && status !== 429 && !(status && status >= 500)) throw error;
        if (++failures >= 4) throw Object.assign(error instanceof Error ? error : new Error('Job updates unavailable'), { jobContinues: true });
        await delay(options.intervalMs ?? 2500, signal);
        continue;
      }
      options.onUpdate?.(value);
      if (options.complete(value)) return value;
      const progress = options.progress?.(value);
      if (idleTimer === undefined || progress !== previousProgress) {
        clearTimeout(idleTimer);
        idleTimer = setTimeout(() => controller.abort(stopped()), options.idleTimeoutMs ?? 300000);
        previousProgress = progress;
      }
      await delay(options.intervalMs ?? 2500, signal);
    }
  } finally {
    clearTimeout(timeout);
    clearTimeout(idleTimer);
    options.signal?.removeEventListener('abort', forwardAbort);
    signal.removeEventListener('abort', abort);
  }
}