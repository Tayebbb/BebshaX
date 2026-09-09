import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { InterviewWorkspace } from '../src/components/interview/InterviewWorkspace';
import { api } from '../src/services/api';
import type { Interview, InterviewInsight, InterviewTurn, SyntheticPersona } from '../src/types';

type InterviewDetail = Interview & {
  turns: InterviewTurn[];
  structured_insights: InterviewInsight[];
  suggested_questions: string[];
};

const timestamp = '2026-09-09T10:00:00Z';
const deferred = <Value,>() => {
  let resolve!: (value: Value) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<Value>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
};

const detailFixture = (suffix: string): InterviewDetail => ({
  id: `interview_lifecycle_${suffix}`,
  study_id: 'study_lifecycle',
  persona_id: `persona_lifecycle_${suffix}`,
  persona_version: 1,
  persona_name: `Synthetic ${suffix}`,
  persona_occupation: 'Synthetic office manager',
  objective: 'Refill purchasing research',
  interview_type: 'adaptive_persona',
  length_tier: 'standard',
  max_turns: 14,
  status: 'active',
  topics_explored: {},
  question_count: 1,
  turn_count: 2,
  created_at: timestamp,
  turns: [
    { id: `${suffix}_question`, turn_number: 1, role: 'interviewer', content: `Saved ${suffix} question.`, created_at: timestamp },
    { id: `${suffix}_answer`, turn_number: 2, role: 'persona', content: `Saved ${suffix} answer.`, created_at: timestamp },
  ],
  structured_insights: [],
  suggested_questions: [`Follow-up for ${suffix}?`],
});

const personaFixture = (detail: InterviewDetail): SyntheticPersona => ({
  id: detail.persona_id,
  name: detail.persona_name ?? 'Synthetic participant',
  status: 'ready',
  version: 1,
  demographics: { location: `Location for ${detail.id}` },
  goals: [],
  needs: [],
  pain_points: [],
  behaviors: [],
  preferences: [],
  motivations: [],
  objections: [],
  dataset_refs: [],
  commercial_profile: {},
  technology_profile: {},
  evidence_citations: [],
  grounding_score: 0,
  confidence: 0,
  validation_warnings: [],
  is_synthetic: true,
  created_at: timestamp,
});

const detailA = detailFixture('A');
const detailB = detailFixture('B');
const replyFixture = {
  reply: 'A canonical reply from an abandoned request.',
  turn_number: 4,
  turn_count: 4,
  max_turns: 14,
  is_finished: false,
  topics_explored: {},
  suggested_questions: [],
};
const workspace = (detail: InterviewDetail) => (
  <InterviewWorkspace
    studyId={detail.study_id}
    interviewId={detail.id}
    onBackToInterviews={vi.fn()}
  />
);
const sendQuestion = (question: string) => {
  fireEvent.change(screen.getByRole('textbox', { name: /Interview question for/i }), {
    target: { value: question },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Send question' }));
};

describe('Exhibition interview request lifecycles', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockRejectedValue(new Error('Unexpected network request')));
    vi.stubGlobal('requestAnimationFrame', vi.fn<typeof requestAnimationFrame>().mockReturnValue(1));
    vi.stubGlobal('cancelAnimationFrame', vi.fn<typeof cancelAnimationFrame>());
    vi.spyOn(api, 'getStudyInterviewDetail').mockImplementation(async (_studyId, interviewId) => (
      interviewId === detailB.id ? detailB : detailA
    ));
    vi.spyOn(api, 'getStudyPersonaDetail').mockImplementation(async (_studyId, personaId) => (
      personaFixture(personaId === detailB.persona_id ? detailB : detailA)
    ));
    vi.spyOn(api, 'sendInterviewMessageStream').mockRejectedValue(new Error('Unexpected stream request'));
    vi.spyOn(api, 'sendInterviewMessage').mockRejectedValue(new Error('Unexpected blocking request'));
    vi.spyOn(api, 'completeStudyInterview').mockRejectedValue(new Error('Unexpected synthesis request'));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('ignores an abandoned detail response after interview A to B to A without fetching its persona', async () => {
    const abandoned = deferred<InterviewDetail>();
    vi.mocked(api.getStudyInterviewDetail).mockReturnValueOnce(abandoned.promise);
    const view = render(workspace(detailA));
    view.rerender(workspace(detailB));
    expect(await screen.findByText('Saved B answer.')).toBeInTheDocument();
    view.rerender(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();

    await act(async () => {
      abandoned.resolve({
        ...detailA,
        persona_id: 'persona_abandoned_detail',
        turns: [{ ...detailA.turns[1], content: 'Abandoned detail answer.' }],
      });
    });

    expect(screen.getByText('Saved A answer.')).toBeInTheDocument();
    expect(screen.queryByText('Abandoned detail answer.')).not.toBeInTheDocument();
    expect(api.getStudyPersonaDetail).not.toHaveBeenCalledWith(detailA.study_id, 'persona_abandoned_detail');
  });

  it('ignores optional persona enrichment from the previous interview', async () => {
    const abandoned = deferred<SyntheticPersona>();
    vi.mocked(api.getStudyPersonaDetail).mockReturnValueOnce(abandoned.promise);
    const view = render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    view.rerender(workspace(detailB));
    const currentLocation = `Location for ${detailB.id}`;
    expect(await screen.findByText(currentLocation)).toBeInTheDocument();

    await act(async () => { abandoned.resolve(personaFixture(detailA)); });

    expect(screen.getByText(currentLocation)).toBeInTheDocument();
    expect(screen.queryByText(`Location for ${detailA.id}`)).not.toBeInTheDocument();
  });

  it.each(['done', 'missing-route'] as const)(
    'ignores late stream %s, deltas, and frame flushes without unlocking the current send',
    async (outcome) => {
      const abandoned = deferred<typeof replyFixture>();
      const current = deferred<typeof replyFixture>();
      vi.mocked(api.sendInterviewMessageStream)
        .mockReturnValueOnce(abandoned.promise)
        .mockReturnValueOnce(current.promise);
      const view = render(workspace(detailA));
      expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
      sendQuestion('An abandoned question.');
      const [, , , oldDelta, oldSignal] = vi.mocked(api.sendInterviewMessageStream).mock.calls[0];
      act(() => { oldDelta('An abandoned draft.'); });
      const oldFrame = vi.mocked(requestAnimationFrame).mock.calls[0][0];

      view.rerender(workspace(detailB));
      expect(oldSignal?.aborted).toBe(true);
      expect(await screen.findByText('Saved B answer.')).toBeInTheDocument();
      sendQuestion('The current question.');
      const [, , , currentDelta, currentSignal] = vi.mocked(api.sendInterviewMessageStream).mock.calls[1];

      await act(async () => {
        oldDelta('A late abandoned draft.');
        oldFrame(0);
        if (outcome === 'done') abandoned.resolve(replyFixture);
        else abandoned.reject(Object.assign(new Error('Stream route unavailable'), { status: 404 }));
      });

      expect(api.sendInterviewMessage).not.toHaveBeenCalled();
      expect(currentSignal?.aborted).toBe(false);
      expect(screen.getByRole('button', { name: 'Waiting for reply' })).toBeDisabled();
      expect(screen.getByRole('textbox', { name: /Interview question for/i })).toBeDisabled();
      expect(screen.getByText('The current question.')).toBeInTheDocument();
      expect(screen.queryByText(replyFixture.reply)).not.toBeInTheDocument();
      expect(screen.queryByText(/abandoned draft/)).not.toBeInTheDocument();
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();

      await act(async () => {
        currentDelta('The current canonical reply.');
        current.resolve({ ...replyFixture, reply: 'The current canonical reply.' });
      });
      expect(screen.getByText('The current canonical reply.')).toBeInTheDocument();
      expect(screen.getByRole('textbox', { name: /Interview question for/i })).toBeEnabled();
    },
  );

  it('aborts the active stream on unmount and never starts a late blocking fallback', async () => {
    const abandoned = deferred<typeof replyFixture>();
    vi.mocked(api.sendInterviewMessageStream).mockReturnValueOnce(abandoned.promise);
    const view = render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    sendQuestion('An unanswered question.');
    const signal = vi.mocked(api.sendInterviewMessageStream).mock.calls[0][4];
    expect(signal?.aborted).toBe(false);
    view.unmount();
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      abandoned.reject(Object.assign(new Error('Stream route unavailable'), { status: 405 }));
    });
    expect(api.sendInterviewMessage).not.toHaveBeenCalled();
  });

  it('ignores a blocking fallback reply after the active interview changes', async () => {
    const abandoned = deferred<typeof replyFixture>();
    vi.mocked(api.sendInterviewMessageStream).mockRejectedValueOnce(
      Object.assign(new Error('Stream route unavailable'), { status: 404 }),
    );
    vi.mocked(api.sendInterviewMessage).mockReturnValueOnce(abandoned.promise);
    const view = render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    sendQuestion('An abandoned fallback question.');
    await waitFor(() => expect(api.sendInterviewMessage).toHaveBeenCalledTimes(1));
    view.rerender(workspace(detailB));
    expect(await screen.findByText('Saved B answer.')).toBeInTheDocument();
    const input = screen.getByRole('textbox', { name: /Interview question for/i });
    fireEvent.change(input, { target: { value: 'The current draft.' } });

    await act(async () => { abandoned.resolve(replyFixture); });

    expect(input).toHaveValue('The current draft.');
    expect(screen.queryByText(replyFixture.reply)).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('blocks all composer entry points during synthesis and recovers the draft after failure', async () => {
    const synthesis = deferred<{ summary: string }>();
    vi.mocked(api.completeStudyInterview).mockReturnValueOnce(synthesis.promise);
    render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    const input = screen.getByRole('textbox', { name: /Interview question for/i });
    fireEvent.change(input, { target: { value: 'Preserve this draft.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Complete & synthesize' }));

    expect(input).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Send question' })).toBeDisabled();
    const suggestion = screen.getByRole('button', { name: 'Follow-up for A?' });
    expect(suggestion).toBeDisabled();
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    fireEvent.click(suggestion);
    expect(api.sendInterviewMessageStream).not.toHaveBeenCalled();
    expect(api.sendInterviewMessage).not.toHaveBeenCalled();

    await act(async () => { synthesis.reject(new Error('Synthesis unavailable')); });

    expect(input).toBeEnabled();
    expect(input).toHaveValue('Preserve this draft.');
    expect(screen.getByRole('button', { name: 'Complete & synthesize' })).toBeEnabled();
  });

  it('ignores an abandoned synthesis after interview A to B to A navigation', async () => {
    const synthesis = deferred<{ summary: string; structured_insights: InterviewInsight[] }>();
    vi.mocked(api.completeStudyInterview).mockReturnValueOnce(synthesis.promise);
    const view = render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Complete & synthesize' }));
    view.rerender(workspace(detailB));
    expect(await screen.findByText('Saved B answer.')).toBeInTheDocument();
    view.rerender(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();

    await act(async () => {
      synthesis.resolve({ summary: 'An abandoned synthesis.', structured_insights: [] });
    });

    expect(screen.getByText('Simulation active')).toBeInTheDocument();
    expect(screen.queryByText('An abandoned synthesis.')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /Interview question for/i })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Toggle persona context panel' })).toHaveAttribute('aria-expanded', 'false');
  });
});