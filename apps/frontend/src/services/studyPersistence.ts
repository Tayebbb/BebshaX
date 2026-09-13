import type { Study } from '../types/study';
import { assertSession, getSessionEpoch } from './session';
import { isRecord } from './interviewProtocol';

const editable = ['title', 'type', 'goal', 'prompt', 'step', 'copilot_messages', 'suggested_roles', 'script_questions'] as const;
export type StudyDraft = Pick<Partial<Study>, typeof editable[number]>;
export const STUDY_SAVE_CHANGED = 'bebshax:study-save';
export interface StudySaveState {
  studyId: string;
  epoch: number;
  state: 'saving' | 'saved' | 'unsaved' | 'conflict';
  message?: string;
}
interface PendingDraft { revision?: number; updates: StudyDraft; }
interface Entry {
  owner?: string;
  revision?: number;
  /** Client-owned fields as last seen from the server, for safe rebases. */
  base?: StudyDraft;
  tail?: Promise<Study>;
  pending: number;
  draft?: StudyDraft;
  failure?: unknown;
  retry?: (draft: StudyDraft, signal: AbortSignal) => Promise<Study>;
}
const entries = new Map<string, Entry>();
let scope = -1;
const storageKey = (owner: string, id: string) => `bebshax_draft_${encodeURIComponent(owner)}_${encodeURIComponent(id)}`;

export function studyDraft(value: Partial<Study>): StudyDraft {
  return structuredClone(Object.fromEntries(editable.filter((key) => value[key] !== undefined).map((key) => [key, value[key]]))) as StudyDraft;
}

function entryFor(id: string): Entry {
  if (scope !== getSessionEpoch()) { entries.clear(); scope = getSessionEpoch(); }
  let entry = entries.get(id);
  if (!entry) {
    if (entries.size >= 64) {
      for (const [key, candidate] of entries) {
        if (!candidate.pending) { entries.delete(key); break; }
      }
    }
    if (entries.size >= 64) throw new Error('Too many studies have pending saves');
    entry = { pending: 0 };
    entries.set(id, entry);
  }
  return entry;
}

function backup(owner: string, id: string): PendingDraft | undefined {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(storageKey(owner, id)) ?? 'null');
    if (isRecord(value) && isRecord(value.updates)) {
      return { revision: Number.isInteger(value.revision) ? value.revision as number : undefined, updates: studyDraft(value.updates) };
    }
  } catch { return undefined; }
  return undefined;
}

export function pendingStudyDraft(owner: string, id: string): StudyDraft | undefined {
  return entryFor(id).draft ?? backup(owner, id)?.updates;
}

export function rememberStudyRevision(study: Study): void {
  if (!Number.isInteger(study.revision) || !study.revision || study.revision < 1) return;
  const entry = entryFor(study.id);
  // With a draft pending, the base must keep describing the revision the draft
  // targets; adopting a newer server copy here would turn a real conflict into a rebase.
  if (!entry.draft && study.revision >= (entry.revision ?? 0)) {
    entry.revision = study.revision;
    entry.base = studyDraft(study);
  }
}

const sameDraft = (left: StudyDraft | undefined, right: StudyDraft | undefined): boolean =>
  left !== undefined && right !== undefined
  && JSON.stringify(studyDraft(left)) === JSON.stringify(studyDraft(right));

/** A server-side operation this tab started (persona generation, script
 * generation) advanced the study revision. Adopt it so the next queued save
 * targets the current row, and fold the fields the server wrote into the base. */
export function adoptStudyRevision(id: string, revision: number | null | undefined, written: StudyDraft = {}): void {
  if (!Number.isInteger(revision) || !revision || revision < 1) return;
  const entry = entryFor(id);
  if (revision <= (entry.revision ?? 0)) return;
  entry.revision = revision;
  entry.base = { ...entry.base, ...studyDraft(written) };
  entry.failure = undefined;
}

function publish(id: string, state: StudySaveState['state'], message?: string): void {
  window.dispatchEvent(new CustomEvent<StudySaveState>(STUDY_SAVE_CHANGED, { detail: { studyId: id, epoch: scope, state, message } }));
}

const isRevisionConflict = (error: unknown): boolean => isRecord(error) && (error.status === 412 || error.status === 409);

export async function queueStudyWrite(
  id: string, owner: string, changes: Partial<Study>,
  load: () => Promise<Study | null>,
  write: (draft: StudyDraft, revision: number) => Promise<Study>,
): Promise<Study> {
  return enqueueStudyWrite(id, owner, changes, load, write);
}

async function enqueueStudyWrite(
  id: string, owner: string, changes: Partial<Study>,
  load: () => Promise<Study | null>,
  write: (draft: StudyDraft, revision: number) => Promise<Study>,
  retry?: { signal: AbortSignal; failure: unknown },
): Promise<Study> {
  const expectedSession = getSessionEpoch();
  const entry = entryFor(id);
  if (entry.owner !== undefined && entry.owner !== owner) throw new DOMException('Study owner changed', 'AbortError');
  entry.owner = owner;
  const stored = backup(owner, id);
  if (!entry.draft && stored) entry.revision = stored.revision;
  const patch = studyDraft({ ...(!entry.draft ? stored?.updates : undefined), ...changes });
  entry.draft = { ...stored?.updates, ...entry.draft, ...patch };
  entry.retry = (draft, signal) => enqueueStudyWrite(id, owner, draft, load, write, { signal, failure: entry.failure });
  let expectedRevision = entry.revision;
  const assertCurrent = () => {
    assertSession(expectedSession);
    retry?.signal.throwIfAborted();
    if (entries.get(id) !== entry || entry.owner !== owner || (retry && entry.revision !== expectedRevision)) {
      throw new DOMException('Study draft retry is no longer current', 'AbortError');
    }
  };
  const persist = () => {
    try { sessionStorage.setItem(storageKey(owner, id), JSON.stringify({ revision: entry.revision, updates: entry.draft })); }
    catch { publish(id, 'unsaved', 'Local backup unavailable. Keep this page open until changes are saved.'); }
  };
  persist();
  entry.pending += 1;
  const previous = entry.tail ?? Promise.resolve();
  const result = previous.catch(() => undefined).then(async () => {
    try {
      assertCurrent();
      if (entry.failure && (!retry || entry.failure !== retry.failure)) throw entry.failure;
      if (!entry.revision) {
        const loaded = await load();
        assertCurrent();
        entry.revision = loaded?.revision;
        expectedRevision = entry.revision;
        if (loaded) entry.base = studyDraft(loaded);
      }
      assertCurrent();
      if (!Number.isInteger(entry.revision) || !entry.revision) throw new Error('Study revision unavailable. Reload the saved study before editing.');
      persist();
      publish(id, 'saving');
      assertCurrent();
      let saved: Study;
      try {
        saved = await write(patch, entry.revision);
      } catch (error) {
        // Server-side operations (persona generation, reports) advance the
        // revision without editing client-owned fields. When the fresh copy
        // still matches what this tab last saw, replaying the draft overwrites
        // nobody; any other difference is a real conflict for the user.
        if (!isRevisionConflict(error)) throw error;
        assertCurrent();
        const fresh = await load().catch(() => null);
        assertCurrent();
        if (!fresh || !Number.isInteger(fresh.revision) || !fresh.revision || fresh.revision <= entry.revision
            || !sameDraft(studyDraft(fresh), entry.base)) {
          throw error;
        }
        entry.revision = fresh.revision;
        expectedRevision = entry.revision;
        persist();
        assertCurrent();
        saved = await write(patch, entry.revision);
      }
      assertCurrent();
      if (saved.id !== id || !Number.isInteger(saved.revision) || !saved.revision || saved.revision <= entry.revision) {
        throw new Error('The server did not acknowledge a newer study revision');
      }
      entry.revision = saved.revision;
      entry.base = studyDraft(saved);
      entry.failure = undefined;
      if (entry.pending === 1) {
        entry.draft = undefined;
        entry.retry = undefined;
        sessionStorage.removeItem(storageKey(owner, id));
        publish(id, 'saved');
      } else { persist(); }
      return saved;
    } catch (error) {
      const failure = retry?.signal.aborted ? new DOMException('Study draft retry cancelled', 'AbortError') : error;
      if (expectedSession === getSessionEpoch() && entries.get(id) === entry && entry.owner === owner) {
        entry.failure = failure;
        persist();
        const conflict = isRevisionConflict(failure);
        publish(id, conflict ? 'conflict' : 'unsaved', conflict
          ? 'This study changed elsewhere. Your unsaved draft is preserved; reload the saved version to resolve the conflict.'
          : retry?.signal.aborted
            ? 'Save confirmation was cancelled. Your draft is retained in this tab. The write may have reached the server; reload the saved version to recover.'
            : 'Changes are not saved. Your draft is retained in this tab.');
      }
      throw failure;
    } finally { entry.pending -= 1; }
  });
  entry.tail = result;
  return result;
}

export function getStudyDraftRetry(owner: string, id: string, signal: AbortSignal): (() => Promise<Study>) | undefined {
  const expectedSession = getSessionEpoch();
  if (scope !== expectedSession || signal.aborted) return undefined;
  const entry = entries.get(id);
  if (!entry || entry.owner !== owner || entry.pending || !entry.draft || !entry.failure || !entry.retry
      || isRevisionConflict(entry.failure) || (isRecord(entry.failure) && entry.failure.name === 'AbortError')) return undefined;
  const { draft, revision, tail, failure, retry } = entry;
  const retained = studyDraft(draft);
  return async () => {
    assertSession(expectedSession);
    signal.throwIfAborted();
    if (entries.get(id) !== entry || entry.owner !== owner || entry.pending || entry.revision !== revision
        || entry.tail !== tail || entry.failure !== failure || !sameDraft(entry.draft, retained)) {
      throw new DOMException('Study draft retry is no longer current', 'AbortError');
    }
    return retry(retained, signal);
  };
}

export function discardStudyDraft(owner: string, id: string): void {
  const entry = entryFor(id);
  if (entry.pending) throw new Error('Wait for the active save before reloading');
  sessionStorage.removeItem(storageKey(owner, id));
  entries.delete(id);
}

export async function waitForStudyWrites(id: string): Promise<void> {
  await entryFor(id).tail;
}

export function knownStudyRevision(id: string): number | undefined { return entryFor(id).revision; }