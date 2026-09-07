/** Display helpers for the Routing & Provenance view. Nulls become "—", never 0. */

export const DASH = '—';

export const fmtNum = (v: number | null | undefined, digits = 0): string =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : DASH;

export const fmtMs = (v: number | null | undefined): string =>
  typeof v === 'number' && Number.isFinite(v) ? `${Math.round(v)}ms` : DASH;

/** Ratio 0–1 → "72%"; null → "—". 0 is a real measurement and renders as "0%". */
export const fmtPct = (v: number | null | undefined): string =>
  typeof v === 'number' && Number.isFinite(v) ? `${Math.round(v * 100)}%` : DASH;

export const fmtCount = (v: number | null | undefined): string =>
  typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString() : DASH;

export interface RoutingPathEntry {
  raw: string;
  kind: 'annotation' | 'candidate' | 'skipped';
  route: string | null;
  reason: string | null;
}

/** routing_path entries are `provider/model`, `provider/model [skipped: reason]`
 * or bracketed router annotations (`[context estimate …]`). */
export const parseRoutingPath = (path: string[] | null | undefined): RoutingPathEntry[] =>
  (path || []).map((raw) => {
    const trimmed = raw.trim();
    if (trimmed.startsWith('[')) {
      return { raw, kind: 'annotation', route: null, reason: trimmed.replace(/^\[|\]$/g, '') };
    }
    const skipped = trimmed.match(/^(.*?)\s*\[skipped:\s*(.*)\]$/);
    if (skipped) {
      return { raw, kind: 'skipped', route: skipped[1].trim(), reason: skipped[2].trim() };
    }
    return { raw, kind: 'candidate', route: trimmed, reason: null };
  });

/** Colour for a failure kind chip — closed taxonomy, unknown kinds fall back to neutral. */
export const failureKindTone = (kind: string | null | undefined): { fg: string; bg: string } => {
  switch (kind) {
    case 'RATE_LIMITED':
    case 'QUOTA_EXHAUSTED':
      return { fg: '#F59E0B', bg: 'rgba(245, 158, 11, 0.12)' };
    case 'CONTEXT_WINDOW_EXCEEDED':
    case 'CAPABILITY_UNSUPPORTED':
      return { fg: 'var(--accent-cyan)', bg: 'rgba(34, 211, 238, 0.12)' };
    case 'INTERNAL_ERROR':
    case 'AUTH_INVALID':
      return { fg: '#EF4444', bg: 'rgba(239, 68, 68, 0.12)' };
    case null:
    case undefined:
      return { fg: 'var(--accent-emerald)', bg: 'rgba(16, 185, 129, 0.12)' };
    default:
      return { fg: 'var(--status-error-text)', bg: 'rgba(239, 68, 68, 0.1)' };
  }
};
