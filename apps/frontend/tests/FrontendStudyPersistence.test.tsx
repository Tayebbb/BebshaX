import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../src/services/api';
import { StudyWorkflowView } from '../src/components/dashboard/views/StudyWorkflowView';
import type { Study } from '../src/types';
import { clearRouteTimings, readRouteTimings, setRouteTimingEnabled, startRouteTiming } from '../src/performance/routeTiming';
import { adoptStudyRevision, getStudyDraftRetry, STUDY_SAVE_CHANGED } from '../src/services/studyPersistence';

const study = {
  id: 'study-revision', revision: 1, user_id: 'study-owner', title: 'Revision study', type: 'interviews',
  status: 'in_progress', persona_count: 0, persona_ids: [], created_at: '2026-09-09', updated_at: '2026-09-09', step: 4,
} satisfies Study & { revision: number };
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

describe('Frontend canonical study persistence', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    api.setMockMode(false);
    api.setAuthToken('study-owner-fixture');
    api.setStoredUser({ id: 'study-owner', email: 'owner@example.test', full_name: 'Study owner', is_active: true, is_verified: true, auth_provider: 'email', created_at: '2026-09-09' });
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    api.clearSession();
    api.setMockMode(true);
    setRouteTimingEnabled(false);
    clearRouteTimings();
  });

  async function failDraftSave(changes: Partial<Study> = { prompt: 'Complete retained draft' }): Promise<void> {
    vi.mocked(fetch).mockResolvedValueOnce(response(study));
    await api.getStudy(study.id);
    vi.mocked(fetch).mockResolvedValueOnce(response({ detail: 'Save unavailable' }, 503));
    await expect(api.updateStudy(study.id, changes)).rejects.toMatchObject({ status: 503 });
  }

  it('serializes writes and advances If-Match without sending server-derived persona state', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response(study));
    await api.getStudy(study.id);
    let finishFirst!: (response: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise((resolve) => { finishFirst = resolve; }))
      .mockResolvedValueOnce(response({ ...study, revision: 3, prompt: 'Second draft' }));
    const first = api.updateStudy(study.id, { prompt: 'First draft', persona_count: 99, persona_ids: ['forged'], personas_data: [], status: 'completed' });
    const second = api.updateStudy(study.id, { prompt: 'Second draft' });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const firstInit = vi.mocked(fetch).mock.calls[1][1];
    expect(JSON.parse(firstInit?.body as string)).toEqual({ prompt: 'First draft', expected_revision: 1 });
    expect(firstInit?.headers).toMatchObject({ 'If-Match': '"1"' });
    finishFirst(response({ ...study, revision: 2, prompt: 'First draft' }));
    await Promise.all([first, second]);
    expect(JSON.parse(vi.mocked(fetch).mock.calls[2][1]?.body as string)).toEqual({ prompt: 'Second draft', expected_revision: 2 });
  });

  it('retries the complete pending draft at the adopted generation revision without regenerating personas', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response(study));
    await api.getStudy(study.id);
    adoptStudyRevision(study.id, 2);
    const generate = vi.spyOn(api, 'generateStudyPersonasDetailed');
    const events = vi.spyOn(window, 'dispatchEvent');
    const prompt = 'Complete synthetic study context. '.repeat(400);
    const messages = [{ id: 'accepted-generation', role: 'assistant' as const, content: 'Personas generated; preserve the complete context.', timestamp: '10:00 am' }];
    vi.mocked(fetch).mockResolvedValueOnce(response({ detail: 'Save unavailable' }, 503));
    await expect(api.updateStudy(study.id, { prompt, step: 2 })).rejects.toMatchObject({ status: 503 });
    await expect(api.updateStudy(study.id, { copilot_messages: messages })).rejects.toMatchObject({ status: 503 });

    const retry = getStudyDraftRetry(study.user_id, study.id, new AbortController().signal);
    expect(retry).toBeTypeOf('function');
    let finishRetry!: (value: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise((resolve) => { finishRetry = resolve; }));
    const saving = retry!();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(JSON.parse(vi.mocked(fetch).mock.calls[2][1]?.body as string)).toEqual({ prompt, step: 2, copilot_messages: messages, expected_revision: 2 });
    expect(vi.mocked(fetch).mock.calls[2][1]?.headers).toMatchObject({ 'If-Match': '"2"' });
    expect(events).not.toHaveBeenCalledWith(expect.objectContaining({ type: STUDY_SAVE_CHANGED, detail: expect.objectContaining({ state: 'saved' }) }));
    expect(api.getPendingStudyDraft(study.id)).toEqual({ prompt, step: 2, copilot_messages: messages });

    const saved = { ...study, revision: 3, persona_count: 3, prompt, step: 2, copilot_messages: messages };
    finishRetry(response(saved));
    await expect(saving).resolves.toEqual(saved);
    expect(api.getPendingStudyDraft(study.id)).toBeUndefined();
    expect(sessionStorage.getItem(`bebshax_draft_${study.user_id}_${study.id}`)).toBeNull();
    expect(api.getStoredUserStudies()).toContainEqual(saved);
    expect(events).toHaveBeenCalledWith(expect.objectContaining({ type: STUDY_SAVE_CHANGED, detail: expect.objectContaining({ state: 'saved' }) }));
    expect(getStudyDraftRetry(study.user_id, study.id, new AbortController().signal)).toBeUndefined();
    expect(generate).not.toHaveBeenCalled();
  });

  it('keeps a repeatedly failed retry latched and allows a fresh action to retry the same draft', async () => {
    await failDraftSave();
    const signal = new AbortController().signal;
    const retry = getStudyDraftRetry(study.user_id, study.id, signal)!;
    const events = vi.spyOn(window, 'dispatchEvent');
    vi.mocked(fetch).mockResolvedValueOnce(response({ detail: 'Still unavailable' }, 503));
    await expect(retry()).rejects.toMatchObject({ status: 503 });
    expect(api.getPendingStudyDraft(study.id)).toEqual({ prompt: 'Complete retained draft' });
    expect(events).not.toHaveBeenCalledWith(expect.objectContaining({ type: STUDY_SAVE_CHANGED, detail: expect.objectContaining({ state: 'saved' }) }));
    await expect(retry()).rejects.toMatchObject({ name: 'AbortError' });
    await expect(api.updateStudy(study.id, { step: 2 })).rejects.toMatchObject({ status: 503 });
    expect(fetch).toHaveBeenCalledTimes(3);

    const nextRetry = getStudyDraftRetry(study.user_id, study.id, signal)!;
    vi.mocked(fetch).mockResolvedValueOnce(response({ ...study, revision: 2, prompt: 'Complete retained draft', step: 2 }));
    await expect(nextRetry()).resolves.toMatchObject({ revision: 2 });
    expect(JSON.parse(vi.mocked(fetch).mock.calls[3][1]?.body as string)).toEqual({ prompt: 'Complete retained draft', step: 2, expected_revision: 1 });
    expect(api.getPendingStudyDraft(study.id)).toBeUndefined();
  });

  it.each(['other-owner', 'other-study'] as const)('does not expose a failed draft retry to %s', async (mismatch) => {
    await failDraftSave();
    const owner = mismatch === 'other-owner' ? 'other-owner' : study.user_id;
    const id = mismatch === 'other-study' ? 'other-study' : study.id;
    expect(getStudyDraftRetry(owner, id, new AbortController().signal)).toBeUndefined();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(api.getPendingStudyDraft(study.id)).toEqual({ prompt: 'Complete retained draft' });
  });

  it('does not manufacture a retry from storage without an active failed queue entry', async () => {
    sessionStorage.setItem(`bebshax_draft_${study.user_id}_${study.id}`, JSON.stringify({ revision: 1, updates: { prompt: 'Recovered context' } }));
    expect(getStudyDraftRetry(study.user_id, study.id, new AbortController().signal)).toBeUndefined();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('does not expose a retry while the original save is still in flight', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response(study));
    await api.getStudy(study.id);
    let finish!: (value: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const saving = api.updateStudy(study.id, { prompt: 'Pending original save' });
    const rejected = expect(saving).rejects.toMatchObject({ status: 503 });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(getStudyDraftRetry(study.user_id, study.id, new AbortController().signal)).toBeUndefined();
    finish(response({ detail: 'Save unavailable' }, 503));
    await rejected;
    expect(getStudyDraftRetry(study.user_id, study.id, new AbortController().signal)).toBeTypeOf('function');
  });

  it('rejects duplicate retry clicks and preserves later writes in revision order', async () => {
    await failDraftSave();
    const signal = new AbortController().signal;
    const retry = getStudyDraftRetry(study.user_id, study.id, signal)!;
    let finish!: (value: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }))
      .mockResolvedValueOnce(response({ ...study, revision: 3, prompt: 'Complete retained draft', step: 3 }));
    const saving = retry();
    await expect(retry()).rejects.toMatchObject({ name: 'AbortError' });
    expect(getStudyDraftRetry(study.user_id, study.id, signal)).toBeUndefined();
    const following = api.updateStudy(study.id, { step: 3 });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(JSON.parse(vi.mocked(fetch).mock.calls[2][1]?.body as string)).toEqual({ prompt: 'Complete retained draft', expected_revision: 1 });
    finish(response({ ...study, revision: 2, prompt: 'Complete retained draft' }));
    await Promise.all([saving, following]);
    expect(fetch).toHaveBeenCalledTimes(4);
    expect(JSON.parse(vi.mocked(fetch).mock.calls[3][1]?.body as string)).toEqual({ step: 3, expected_revision: 2 });
    expect(api.getPendingStudyDraft(study.id)).toBeUndefined();
    await expect(retry()).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).toHaveBeenCalledTimes(4);
  });

  it('invalidates a captured retry when a newer blocked draft replaces its payload', async () => {
    await failDraftSave();
    const signal = new AbortController().signal;
    const retry = getStudyDraftRetry(study.user_id, study.id, signal)!;
    await expect(api.updateStudy(study.id, { prompt: 'Newer complete draft' })).rejects.toMatchObject({ status: 503 });
    await expect(retry()).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).toHaveBeenCalledTimes(2);
    vi.mocked(fetch).mockResolvedValueOnce(response({ ...study, revision: 2, prompt: 'Newer complete draft' }));
    await getStudyDraftRetry(study.user_id, study.id, signal)!();
    expect(JSON.parse(vi.mocked(fetch).mock.calls[2][1]?.body as string)).toEqual({ prompt: 'Newer complete draft', expected_revision: 1 });
  });

  it('invalidates a captured retry after discard even if the same study and revision fail again', async () => {
    await failDraftSave();
    const signal = new AbortController().signal;
    const retry = getStudyDraftRetry(study.user_id, study.id, signal)!;
    api.discardStudyDraft(study.id);
    vi.mocked(fetch).mockResolvedValueOnce(response(study))
      .mockResolvedValueOnce(response({ detail: 'New draft unavailable' }, 503));
    await expect(api.updateStudy(study.id, { prompt: 'Replacement draft' })).rejects.toMatchObject({ status: 503 });
    const backup = sessionStorage.getItem(`bebshax_draft_${study.user_id}_${study.id}`);
    await expect(retry()).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).toHaveBeenCalledTimes(4);
    expect(sessionStorage.getItem(`bebshax_draft_${study.user_id}_${study.id}`)).toBe(backup);
    expect(api.getPendingStudyDraft(study.id)).toEqual({ prompt: 'Replacement draft' });
  });

  it.each(['same-owner', 'different-owner'] as const)('rejects a captured retry after a session reset to %s', async (replacement) => {
    await failDraftSave();
    const retry = getStudyDraftRetry(study.user_id, study.id, new AbortController().signal)!;
    const owner = replacement === 'same-owner' ? study.user_id : 'replacement-owner';
    api.clearSession();
    api.setAuthToken('replacement-session-fixture');
    api.setStoredUser({ id: owner, email: 'replacement@example.test', full_name: 'Replacement owner', is_active: true, is_verified: true, auth_provider: 'email', created_at: '2026-09-09' });
    const events = vi.spyOn(window, 'dispatchEvent');
    await expect(retry()).rejects.toMatchObject({ name: 'AbortError' });
    expect(getStudyDraftRetry(study.user_id, study.id, new AbortController().signal)).toBeUndefined();
    expect(getStudyDraftRetry(owner, study.id, new AbortController().signal)).toBeUndefined();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(sessionStorage.getItem(`bebshax_draft_${study.user_id}_${study.id}`)).toBeNull();
    expect(events).not.toHaveBeenCalledWith(expect.objectContaining({ type: STUDY_SAVE_CHANGED }));
  });

  it('invalidates a captured retry after a server operation advances the revision', async () => {
    await failDraftSave();
    const retry = getStudyDraftRetry(study.user_id, study.id, new AbortController().signal)!;
    adoptStudyRevision(study.id, 2);
    await expect(retry()).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(api.getPendingStudyDraft(study.id)).toEqual({ prompt: 'Complete retained draft' });
  });

  it('does not dispatch a queued retry when its revision changes before execution', async () => {
    await failDraftSave();
    const retry = getStudyDraftRetry(study.user_id, study.id, new AbortController().signal)!;
    const saving = retry();
    adoptStudyRevision(study.id, 2);
    await expect(saving).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('does not dispatch a retry after its route is dismissed or already aborted', async () => {
    await failDraftSave();
    const controller = new AbortController();
    const retry = getStudyDraftRetry(study.user_id, study.id, controller.signal)!;
    controller.abort();
    expect(getStudyDraftRetry(study.user_id, study.id, controller.signal)).toBeUndefined();
    await expect(retry()).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(api.getPendingStudyDraft(study.id)).toEqual({ prompt: 'Complete retained draft' });
  });

  it('does not dispatch a retry aborted before its queue turn', async () => {
    await failDraftSave();
    const controller = new AbortController();
    const retry = getStudyDraftRetry(study.user_id, study.id, controller.signal)!;
    const saving = retry();
    controller.abort();
    await expect(saving).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(api.getPendingStudyDraft(study.id)).toEqual({ prompt: 'Complete retained draft' });
    expect(getStudyDraftRetry(study.user_id, study.id, new AbortController().signal)).toBeUndefined();
  });

  it('does not replay a conflict after route ownership ends during the fresh revision load', async () => {
    await failDraftSave();
    const controller = new AbortController();
    const retry = getStudyDraftRetry(study.user_id, study.id, controller.signal)!;
    let finish!: (value: Response) => void;
    vi.mocked(fetch).mockResolvedValueOnce(response({ detail: 'Server-side revision bump' }, 412))
      .mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const saving = retry();
    const rejected = expect(saving).rejects.toMatchObject({ name: 'AbortError' });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(4));
    controller.abort();
    finish(response({ ...study, revision: 2, persona_count: 3 }));
    await rejected;
    expect(fetch).toHaveBeenCalledTimes(4);
    expect(api.getPendingStudyDraft(study.id)).toEqual({ prompt: 'Complete retained draft' });
  });

  it('does not publish saved or revive retry when an aborted in-flight response arrives', async () => {
    await failDraftSave();
    const controller = new AbortController();
    const retry = getStudyDraftRetry(study.user_id, study.id, controller.signal)!;
    const events = vi.spyOn(window, 'dispatchEvent');
    let finish!: (value: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const saving = retry();
    const rejected = expect(saving).rejects.toMatchObject({ name: 'AbortError' });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    controller.abort();
    finish(response({ ...study, revision: 2, prompt: 'Complete retained draft' }));
    await rejected;
    expect(events).not.toHaveBeenCalledWith(expect.objectContaining({ type: STUDY_SAVE_CHANGED, detail: expect.objectContaining({ state: 'saved' }) }));
    expect(api.getPendingStudyDraft(study.id)).toEqual({ prompt: 'Complete retained draft' });
    expect(getStudyDraftRetry(study.user_id, study.id, new AbortController().signal)).toBeUndefined();
  });

  it('does not restore private draft data or saved events after session reset during retry', async () => {
    await failDraftSave();
    const retry = getStudyDraftRetry(study.user_id, study.id, new AbortController().signal)!;
    let finish!: (value: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const saving = retry();
    const rejected = expect(saving).rejects.toMatchObject({ name: 'AbortError' });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    api.clearSession();
    const events = vi.spyOn(window, 'dispatchEvent');
    finish(response({ ...study, revision: 2, prompt: 'Complete retained draft' }));
    await rejected;
    expect(sessionStorage.getItem(`bebshax_draft_${study.user_id}_${study.id}`)).toBeNull();
    expect(api.getPendingStudyDraft(study.id)).toBeUndefined();
    expect(events).not.toHaveBeenCalledWith(expect.objectContaining({ type: STUDY_SAVE_CHANGED }));
  });

  it.each([409, 412])('keeps a retry conflict (HTTP %i) protected when another writer changed client fields', async (status) => {
    await failDraftSave();
    const signal = new AbortController().signal;
    const retry = getStudyDraftRetry(study.user_id, study.id, signal)!;
    vi.mocked(fetch).mockResolvedValueOnce(response({ detail: 'Concurrent edit' }, status))
      .mockResolvedValueOnce(response({ ...study, revision: 2, prompt: 'Other writer context' }));
    await expect(retry()).rejects.toMatchObject({ status });
    expect(fetch).toHaveBeenCalledTimes(4);
    expect(api.getPendingStudyDraft(study.id)).toEqual({ prompt: 'Complete retained draft' });
    expect(getStudyDraftRetry(study.user_id, study.id, signal)).toBeUndefined();
    await expect(api.updateStudy(study.id, { step: 3 })).rejects.toMatchObject({ status });
    expect(fetch).toHaveBeenCalledTimes(4);
  });

  it('does not treat an unacknowledged retry revision as a saved draft', async () => {
    await failDraftSave();
    const retry = getStudyDraftRetry(study.user_id, study.id, new AbortController().signal)!;
    const events = vi.spyOn(window, 'dispatchEvent');
    vi.mocked(fetch).mockResolvedValueOnce(response(study));
    await expect(retry()).rejects.toThrow(/newer study revision/);
    expect(api.getPendingStudyDraft(study.id)).toEqual({ prompt: 'Complete retained draft' });
    expect(api.getStoredUserStudies()).not.toContainEqual(study);
    expect(events).not.toHaveBeenCalledWith(expect.objectContaining({ type: STUDY_SAVE_CHANGED, detail: expect.objectContaining({ state: 'saved' }) }));
  });

  it('preserves the draft and does not replay a stale tab conflict as a blind overwrite', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response(study));
    await api.getStudy(study.id);
    // Another tab changed a client-owned field: the one reload shows a different
    // prompt, so the conflict stands and the draft is never replayed over it.
    vi.mocked(fetch)
      .mockResolvedValueOnce(response({ detail: 'Study changed. Reload before saving.' }, 409))
      .mockResolvedValueOnce(response({ ...study, revision: 2, prompt: 'Edited in another tab' }));
    await expect(api.updateStudy(study.id, { prompt: 'Keep the complete unsaved draft' })).rejects.toMatchObject({ status: 409 });
    expect(api.getPendingStudyDraft(study.id)?.prompt).toBe('Keep the complete unsaved draft');
    await expect(api.updateStudy(study.id, { prompt: 'Newer unsaved draft' })).rejects.toMatchObject({ status: 409 });
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'PATCH')).toHaveLength(1);
    expect(api.getPendingStudyDraft(study.id)?.prompt).toBe('Newer unsaved draft');
  });

  it.each([412, 409])('rebases onto a server-side revision bump (HTTP %i) when no client-owned field changed', async (status) => {
    vi.mocked(fetch).mockResolvedValueOnce(response(study));
    await api.getStudy(study.id);
    // e.g. persona generation saved a cohort: revision 1 -> 2, prompt/step untouched.
    vi.mocked(fetch)
      .mockResolvedValueOnce(response({ detail: 'Study changed; reload before saving.' }, status))
      .mockResolvedValueOnce(response({ ...study, revision: 2, persona_count: 3 }))
      .mockResolvedValueOnce(response({ ...study, revision: 3, persona_count: 3, prompt: 'Saved after the bump' }));

    await expect(api.updateStudy(study.id, { prompt: 'Saved after the bump' })).resolves.toMatchObject({ revision: 3 });

    const patches = vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'PATCH');
    expect(patches).toHaveLength(2);
    expect(patches[0][1]?.headers).toMatchObject({ 'If-Match': '"1"' });
    expect(patches[1][1]?.headers).toMatchObject({ 'If-Match': '"2"' });
    expect(api.getPendingStudyDraft(study.id)).toBeUndefined();
  });

  it('gives up the rebase when the reload itself fails and keeps the draft', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response(study));
    await api.getStudy(study.id);
    vi.mocked(fetch)
      .mockResolvedValueOnce(response({ detail: 'Study changed; reload before saving.' }, 412))
      .mockRejectedValueOnce(new TypeError('Connection lost'));
    await expect(api.updateStudy(study.id, { prompt: 'Draft survives' })).rejects.toMatchObject({ status: 412 });
    expect(api.getPendingStudyDraft(study.id)?.prompt).toBe('Draft survives');
  });

  it('does not install a stale revision acknowledgement into the saved study cache', async () => {
    api.saveStoredUserStudies([study]);
    vi.mocked(fetch).mockResolvedValueOnce(response(study));
    await api.getStudy(study.id);
    vi.mocked(fetch).mockResolvedValueOnce(response({ ...study, prompt: 'Unacknowledged server draft' }));

    await expect(api.updateStudy(study.id, { prompt: 'Keep my complete draft' })).rejects.toThrow(/newer study revision/);
    expect(api.getStoredUserStudies()).toEqual([study]);
    expect(api.getPendingStudyDraft(study.id)?.prompt).toBe('Keep my complete draft');
  });

  it.each([401, 500])('reports report-list HTTP %i instead of inventing an empty report history', async (status) => {
    vi.mocked(fetch).mockResolvedValueOnce(response({ detail: 'Reports unavailable' }, status));
    await expect(api.getStudyReports(study.id)).rejects.toMatchObject({ status });
  });

  it('accepts a valid empty report list', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response([]));
    await expect(api.getStudyReports(study.id)).resolves.toEqual([]);
  });

  it('honors explicit step one on initial load and when returning from another step', async () => {
    api.setMockMode(true);
    vi.spyOn(api, 'getStudy').mockResolvedValue(study);
    vi.spyOn(api, 'getStudyReports').mockResolvedValue([]);
    vi.spyOn(api, 'getEvidenceSummary').mockRejectedValue(new Error('Fixture evidence unavailable'));
    const view = render(<StudyWorkflowView studyId={study.id} initialStep={1} onExit={vi.fn()} />);
    await screen.findByText(study.title);
    expect(screen.getByRole('textbox', { name: 'Describe your idea or answer the copilot' })).toBeInTheDocument();
    view.rerender(<StudyWorkflowView studyId={study.id} initialStep={4} onExit={vi.fn()} />);
    await act(async () => {});
    expect(screen.queryByRole('textbox', { name: 'Describe your idea or answer the copilot' })).not.toBeInTheDocument();
    view.rerender(<StudyWorkflowView studyId={study.id} initialStep={1} onExit={vi.fn()} />);
    expect(await screen.findByRole('textbox', { name: 'Describe your idea or answer the copilot' })).toBeInTheDocument();
  });

  it.each(['missing', 'unavailable'] as const)('does not expose an editable phantom study when hydration is %s', async (failure) => {
    vi.spyOn(api, 'getStudy').mockImplementation(async () => {
      if (failure === 'missing') return null;
      throw new Error('Saved study service unavailable');
    });
    vi.spyOn(api, 'getStudyReports').mockResolvedValue([]);
    vi.spyOn(api, 'getEvidenceSummary').mockRejectedValue(new Error('Evidence unavailable'));
    const send = vi.spyOn(api, 'sendStudyCopilotMessage');
    const save = vi.spyOn(api, 'updateStudy');
    render(<StudyWorkflowView studyId={study.id} initialStep={1} onExit={vi.fn()} />);

    expect(await screen.findByRole('alert')).toHaveTextContent(/study.*(unavailable|not found)|could not be loaded/i);
    expect(screen.queryByRole('textbox', { name: 'Describe your idea or answer the copilot' })).not.toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
  });

  it('waits for saved history before accepting an initial prompt or starting inference', async () => {
    let finishStudy!: (value: Study) => void;
    vi.spyOn(api, 'getStudy').mockReturnValue(new Promise((resolve) => { finishStudy = resolve; }));
    vi.spyOn(api, 'getStudyReports').mockResolvedValue([]);
    vi.spyOn(api, 'getEvidenceSummary').mockRejectedValue(new Error('Evidence unavailable'));
    const send = vi.spyOn(api, 'sendStudyCopilotMessage').mockRejectedValue(new Error('No inference expected before hydration'));
    const save = vi.spyOn(api, 'updateStudy').mockResolvedValue(study);
    render(<StudyWorkflowView studyId={study.id} initialStep={1} initialPrompt="Unconfirmed URL context" onExit={vi.fn()} />);

    await act(async () => {});
    expect(screen.queryByRole('textbox', { name: 'Describe your idea or answer the copilot' })).not.toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
    await act(async () => { finishStudy({ ...study, copilot_messages: [{ id: 'saved-context', role: 'assistant', content: 'Complete saved study context.', timestamp: '10:00 am' }] }); });
    expect(screen.getByText('Complete saved study context.')).toBeInTheDocument();
    expect(screen.queryByText('Unconfirmed URL context')).not.toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
  });

  it('shows an unsaved state when a workflow navigation PATCH fails', async () => {
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      if (init?.method === 'PATCH') return response({ detail: 'Save unavailable' }, 503);
      if (String(input).endsWith(`/studies/${study.id}`)) return response(study);
      if (String(input).endsWith('/reports')) return response([]);
      return response({ detail: 'Optional evidence unavailable' }, 503);
    });
    render(<StudyWorkflowView studyId={study.id} initialStep={4} onExit={vi.fn()} />);
    await screen.findByText(study.title);

    fireEvent.click(screen.getByRole('button', { name: /Step 1: Context/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/Changes are not saved/);
    expect(api.getPendingStudyDraft(study.id)?.step).toBe(1);
  });

  it.each([2, 3] as const)('does not record step %i generation placeholders as primary content', async (step) => {
    api.setMockMode(true);
    vi.spyOn(api, 'getStudy').mockResolvedValue({ ...study, prompt: 'Full study context', suggested_roles: [{ id: 'role', role: 'Researcher', description: 'Synthetic source profile', count: 1, selected: true }] });
    vi.spyOn(api, 'getStudyReports').mockResolvedValue([]);
    vi.spyOn(api, 'getEvidenceSummary').mockRejectedValue(new Error('Evidence unavailable'));
    vi.spyOn(api, 'updateStudy').mockResolvedValue(study);
    let fail!: (error: Error) => void;
    const pending = new Promise<never>((_resolve, reject) => { fail = reject; });
    if (step === 2) vi.spyOn(api, 'generateStudyPersonasDetailed').mockReturnValue(pending);
    else vi.spyOn(api, 'generateStudyScriptQuestions').mockReturnValue(pending);
    const frames = new Map<number, FrameRequestCallback>();
    let frameId = 0;
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.set(++frameId, callback); return frameId; });
    vi.stubGlobal('cancelAnimationFrame', (id: number) => { frames.delete(id); });
    const paint = () => {
      for (let pass = 0; pass < 3; pass += 1) {
        const callbacks = [...frames.values()];
        frames.clear();
        callbacks.forEach((callback) => callback(0));
      }
    };
    setRouteTimingEnabled(true);
    startRouteTiming(`/research/${study.id}/step${step}`);
    render(<StudyWorkflowView studyId={study.id} initialStep={step} onExit={vi.fn()} />);
    await screen.findByText(study.title);
    fireEvent.click(screen.getByRole('button', { name: step === 2 ? 'Generate Personas' : 'Generate Questions' }));
    act(paint);
    expect(readRouteTimings()).toEqual([]);

    await act(async () => { fail(new Error('Generation temporarily unavailable')); });
    act(paint);
    expect(readRouteTimings()).toEqual([expect.objectContaining({ route: `workflow-${step}`, stage: 'primary-content', outcome: 'error' })]);
  });
});