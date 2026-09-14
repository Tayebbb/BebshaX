import { readFileSync } from 'node:fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { InterviewWorkspace } from '../src/components/interview/InterviewWorkspace';
import { api } from '../src/services/api';
import type { Interview, InterviewInsight, InterviewTurn, SyntheticPersona } from '../src/types';

const interviewCss = readFileSync('src/components/interview/interview.css', 'utf8');

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

  it.each(['loading', 'unavailable', 'loaded'] as const)(
    'does not mount decorative ambient layers while the interview is %s',
    async (state) => {
      if (state === 'loading') {
        vi.mocked(api.getStudyInterviewDetail).mockReturnValueOnce(deferred<InterviewDetail>().promise);
      } else if (state === 'unavailable') {
        vi.mocked(api.getStudyInterviewDetail).mockRejectedValueOnce(new Error('Interview unavailable'));
      }
      const view = render(workspace(detailA));
      if (state === 'unavailable') await screen.findByText('Back to interviews');
      if (state === 'loaded') await screen.findByText('Saved A answer.');

      expect(view.container.querySelector('.iv-root')).toBeInTheDocument();
      expect(view.container.querySelector('.iv-ambient')).not.toBeInTheDocument();
    },
  );

  it('inherits the neutral canvas and keeps content visible without decorative scene animation', () => {
    const stylesheet = document.createElement('style');
    stylesheet.textContent = interviewCss;
    document.head.appendChild(stylesheet);
    try {
      const rules = Array.from(stylesheet.sheet?.cssRules ?? []).filter(
        (rule): rule is CSSStyleRule => rule.type === CSSRule.STYLE_RULE,
      );
      const declaration = (selector: string, property: string) => (
        rules.find((rule) => rule.selectorText === selector)?.style.getPropertyValue(property) ?? ''
      );
      expect(declaration('.iv-root', '--iv-bg')).toBe('var(--bg-pure)');
      expect(declaration("[data-theme='light'] .iv-root", '--iv-bg')).toBe('');
      expect(declaration('.iv-header', 'background')).toBe('var(--iv-bg)');
      expect(declaration('.iv-rail', 'background')).toBe('var(--iv-bg)');
      for (const token of ['--iv-accent-soft', '--iv-gold-soft', '--iv-danger-soft']) {
        expect(declaration('.iv-root', token)).toBe('var(--bg-card)');
      }
      for (const selector of ['.iv-chip', '.iv-insight']) {
        expect(declaration(selector, 'background')).toBe('var(--bg-card)');
      }
      expect(declaration('.iv-ghost-btn.iv-primary:hover:not(:disabled)', 'background')).toBe('var(--bg-card-hover)');
      for (const selector of ['.iv-orb', '.iv-empty-orb']) {
        expect(declaration(selector, 'background')).toBe('var(--bg-card)');
        expect(declaration(selector, 'box-shadow')).toBe('');
      }
      for (const selector of ['.iv-turn', '.iv-thinking', '.iv-empty', '.iv-rail-block', '.iv-error', '.iv-loading']) {
        expect(declaration(selector, 'animation')).toBe('');
      }
      expect(interviewCss).not.toContain('iv-ambient');
      expect(interviewCss).not.toContain('iv-drift');
      expect(interviewCss).not.toContain('iv-orb-breathe');
    } finally {
      stylesheet.remove();
    }
  });

  it.each(['active', 'awaiting synthesis'] as const)(
    'keeps the header synthesis action named and described when its visible label is hidden while %s',
    async (state) => {
      const synthesis = deferred<{ summary: string }>();
      const label = state === 'active' ? 'Complete & synthesize' : 'Retry synthesis';
      if (state === 'awaiting synthesis') {
        vi.mocked(api.getStudyInterviewDetail).mockResolvedValueOnce({
          ...detailA, status: 'completed', summary: undefined,
          configuration: { synthesis: { source: 'unavailable' } },
        });
      }
      vi.mocked(api.completeStudyInterview).mockReturnValueOnce(synthesis.promise);
      render(workspace(detailA));
      await screen.findByText('Saved A answer.');
      const header = screen.getByRole('banner');
      const action = within(header).getByRole('button', { name: label });
      const visibleLabel = action.querySelector<HTMLElement>('.iv-label');
      expect(visibleLabel).not.toBeNull();
      if (visibleLabel) visibleLabel.style.display = 'none';

      expect(within(header).getByRole('button', { name: label })).toBe(action);
      expect(action).toHaveAttribute('aria-label', label);
      expect(action).toHaveAttribute('title', label);
      fireEvent.click(action);
      expect(action).toBeDisabled();
      expect(action).toHaveAccessibleName('Synthesizing interview');
      expect(action).toHaveAttribute('title', 'Synthesizing interview');
      expect(action).toHaveAttribute('aria-busy', 'true');
      fireEvent.click(action);
      expect(api.completeStudyInterview).toHaveBeenCalledTimes(1);

      await act(async () => { synthesis.resolve({ summary: 'Synthesis from the header action.' }); });
      expect(screen.getByText('Synthesis from the header action.')).toBeInTheDocument();
    },
  );

  it('keeps touch targets stable and long interview content usable on phones', () => {
    const stylesheet = document.createElement('style');
    stylesheet.textContent = interviewCss;
    document.head.appendChild(stylesheet);
    try {
      const rules = Array.from(stylesheet.sheet?.cssRules ?? []);
      const styles = rules.filter((rule): rule is CSSStyleRule => rule.type === CSSRule.STYLE_RULE);
      const buttonStyle = styles.find((rule) => rule.selectorText === '.iv-ghost-btn')?.style;
      expect(buttonStyle?.getPropertyValue('min-height')).toBe('44px');
      expect(buttonStyle?.getPropertyValue('min-width')).toBe('44px');
      expect(styles.find((rule) => rule.selectorText === '.iv-header-actions .iv-primary')?.style.width).toBe('12rem');
      for (const selector of ['.iv-back', '.iv-mini-btn', '.iv-turn-ref', '.iv-chip', '.iv-suggestion']) {
        const control = styles.find((rule) => rule.selectorText === selector)?.style;
        expect(control?.getPropertyValue('min-height')).toBe('44px');
        expect(control?.getPropertyValue('min-width')).toBe('44px');
      }
      expect(styles.find((rule) => rule.selectorText === '.iv-id-name')?.style.getPropertyValue('white-space')).toBe('normal');
      expect(styles.find((rule) => rule.selectorText === '.iv-id-name')?.style.getPropertyValue('overflow-wrap')).toBe('anywhere');
      expect(styles.find((rule) => rule.selectorText === '.iv-rail')?.style.getPropertyValue('overflow-wrap')).toBe('anywhere');
      expect(styles.find((rule) => rule.selectorText === '.iv-error-actions')?.style.getPropertyValue('flex-wrap')).toBe('wrap');
      const compact = rules.find((rule): rule is CSSMediaRule => (
        rule.type === CSSRule.MEDIA_RULE && (rule as CSSMediaRule).media.mediaText === '(max-width: 720px)'
      ));
      const compactStyles = Array.from(compact?.cssRules ?? []).filter(
        (rule): rule is CSSStyleRule => rule.type === CSSRule.STYLE_RULE,
      );
      const compactButtons = compactStyles.find((rule) => rule.selectorText === '.iv-header-actions .iv-ghost-btn')?.style;
      expect(compactButtons?.width).toBe('44px');
      expect(compactButtons?.height).toBe('44px');
      expect(compactStyles.find((rule) => rule.selectorText === '.iv-root')?.style.height).toBe('calc(100dvh - 64px)');
      const touch = rules.find((rule): rule is CSSMediaRule => (
        rule.type === CSSRule.MEDIA_RULE && (rule as CSSMediaRule).media.mediaText === '(hover: none)'
      ));
      const touchStyles = Array.from(touch?.cssRules ?? []).filter(
        (rule): rule is CSSStyleRule => rule.type === CSSRule.STYLE_RULE,
      );
      expect(touchStyles.find((rule) => rule.selectorText.includes('.iv-turn-actions'))?.style.opacity).toBe('1');
    } finally {
      stylesheet.remove();
    }
  });

  it.each(['active', 'empty', 'completed'] as const)(
    'provides exactly one participant page heading in the header of an %s interview',
    async (state) => {
      vi.mocked(api.getStudyInterviewDetail).mockResolvedValueOnce({
        ...detailA,
        status: state === 'completed' ? 'completed' : 'active',
        turns: state === 'empty' ? [] : detailA.turns,
      });
      render(workspace(detailA));
      await screen.findByText('Synthetic office manager');

      const headings = screen.queryAllByRole('heading', { level: 1 });
      expect(headings).toHaveLength(1);
      expect(headings[0]).toHaveTextContent('Synthetic A');
      expect(screen.getByRole('banner')).toContainElement(headings[0]);
    },
  );

  it('announces a failed interview load with a page heading and a working reload action', async () => {
    vi.mocked(api.getStudyInterviewDetail).mockRejectedValueOnce(new Error('The saved interview could not be loaded'));
    render(workspace(detailA));
    await screen.findByText('Back to interviews');

    expect(screen.queryByRole('alert')).not.toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: 'Interview unavailable' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    expect(api.getStudyInterviewDetail).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('links the phone context toggle to its dialog and closes it before profile navigation', async () => {
    const matchMedia = window.matchMedia;
    vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({ ...matchMedia(query), matches: query.includes('1120px') }));
    const onNavigateToPersona = vi.fn();
    render(<InterviewWorkspace studyId={detailA.study_id} interviewId={detailA.id} onBackToInterviews={vi.fn()} onNavigateToPersona={onNavigateToPersona} />);
    await screen.findByText(`Location for ${detailA.id}`);
    const trigger = screen.getByRole('button', { name: 'Toggle persona context panel' });
    const rail = document.querySelector<HTMLElement>('.iv-rail');
    expect(trigger).toHaveAttribute('aria-controls', rail?.id);
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole('dialog', { name: 'Interview context' });
    expect(dialog.id).not.toBe('');
    expect(within(dialog).getByRole('heading', { name: 'Interview', level: 2 })).toBeInTheDocument();
    expect(within(dialog).getByRole('heading', { name: 'Participant', level: 2 })).toBeInTheDocument();
    const close = within(dialog).getByRole('button', { name: 'Close interview context' });
    expect(close).toHaveAttribute('title', 'Close interview context');
    fireEvent.click(close);
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(rail?.inert).toBe(true);

    fireEvent.click(trigger);
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Interview context' })).getByRole('button', { name: 'Full profile' }));
    expect(onNavigateToPersona).toHaveBeenCalledExactlyOnceWith(detailA.persona_id);
    expect(screen.queryByRole('dialog', { name: 'Interview context' })).not.toBeInTheDocument();
    expect(rail?.inert).toBe(true);
    expect(screen.getByText('Saved A answer.')).toBeInTheDocument();
  });

  it.each(['', '   \n  '])('does not submit an empty or whitespace-only question %j', async (draft) => {
    render(workspace(detailA));
    await screen.findByText('Saved A answer.');
    const input = screen.getByRole('textbox', { name: /Interview question for/i });
    fireEvent.change(input, { target: { value: draft } });
    expect(screen.getByRole('button', { name: 'Send question' })).toBeDisabled();
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    fireEvent.click(screen.getByRole('button', { name: 'Send question' }));

    expect(input).toHaveValue(draft);
    expect(api.sendInterviewMessageStream).not.toHaveBeenCalled();
    expect(api.sendInterviewMessage).not.toHaveBeenCalled();
    expect(api.completeStudyInterview).not.toHaveBeenCalled();
  });

  it('keeps Shift+Enter in the composer and sends only once for a subsequent plain Enter', async () => {
    const reply = deferred<typeof replyFixture>();
    vi.mocked(api.sendInterviewMessageStream).mockReturnValueOnce(reply.promise);
    render(workspace(detailA));
    await screen.findByText('Saved A answer.');
    const input = screen.getByRole('textbox', { name: /Interview question for/i });
    fireEvent.change(input, { target: { value: 'A multiline question.' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter', shiftKey: true });
    expect(input).toHaveValue('A multiline question.');
    expect(api.sendInterviewMessageStream).not.toHaveBeenCalled();

    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    expect(input).toBeDisabled();
    expect(api.sendInterviewMessageStream).toHaveBeenCalledTimes(1);
    expect(api.sendInterviewMessage).not.toHaveBeenCalled();
    await act(async () => { reply.resolve(replyFixture); });
    expect(screen.getByText(replyFixture.reply)).toBeInTheDocument();
  });

  it('retries a failed question without requesting synthesis', async () => {
    vi.mocked(api.sendInterviewMessageStream)
      .mockRejectedValueOnce(new Error('Question temporarily unavailable'))
      .mockResolvedValueOnce(replyFixture);
    render(workspace(detailA));
    await screen.findByText('Saved A answer.');
    sendQuestion('Preserve the question for retry.');
    const failure = await screen.findByRole('alert');
    expect(screen.getByRole('textbox', { name: /Interview question for/i })).toHaveValue('Preserve the question for retry.');
    fireEvent.click(within(failure).getByRole('button', { name: 'Retry question' }));

    expect(await screen.findByText(replyFixture.reply)).toBeInTheDocument();
    expect(api.sendInterviewMessageStream).toHaveBeenCalledTimes(2);
    expect(api.sendInterviewMessageStream).toHaveBeenLastCalledWith(
      detailA.study_id, detailA.id, 'Preserve the question for retry.', expect.any(Function), expect.any(AbortSignal),
    );
    expect(api.completeStudyInterview).not.toHaveBeenCalled();
  });

  it('synthesizes automatically when the final in-cap turn lands instead of faking completion', async () => {
    // Live 2026-09-14: the client flipped status to "completed" at the cap without
    // calling /complete; after a reload the row was still active and accepted turns.
    vi.mocked(api.sendInterviewMessageStream).mockResolvedValueOnce({
      ...replyFixture, turn_number: 14, turn_count: 14, max_turns: 14, is_finished: true,
    });
    vi.mocked(api.completeStudyInterview).mockResolvedValueOnce({
      summary: 'Refill purchasing is a chore the persona delegates.',
      key_findings: ['Delegates refills'],
      structured_insights: [],
      source: 'llm',
    } as never);
    render(workspace(detailA));
    await screen.findByText('Saved A answer.');
    sendQuestion('Last question within the cap.');

    await waitFor(() => expect(api.completeStudyInterview).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Simulation complete')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /Interview question for/i })).not.toBeInTheDocument();
  });

  it('closes the composer for a reloaded interview at its cap and offers synthesis', async () => {
    vi.mocked(api.getStudyInterviewDetail).mockResolvedValueOnce({ ...detailA, turn_count: 14, max_turns: 14, status: 'active' });
    render(workspace(detailA));
    await screen.findByText('Saved A answer.');

    expect(screen.getByText('Turn limit reached')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /Interview question for/i })).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Turn limit reached (14 of 14). Complete the interview to synthesize its insights.');
    expect(screen.getAllByRole('button', { name: /Complete & synthesize/i }).length).toBeGreaterThan(0);
    expect(api.completeStudyInterview).not.toHaveBeenCalled();
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

  it('closes the interview honestly when no route wrote the synthesis and offers a retry', async () => {
    vi.mocked(api.completeStudyInterview)
      .mockResolvedValueOnce({
        id: detailA.id, status: 'completed', summary: null, key_findings: [], structured_insights: [],
        source: 'unavailable', served_by: null, error_code: 'llm_error:AllCandidatesFailed', insights_dropped: 0,
      })
      .mockResolvedValueOnce({
        id: detailA.id, status: 'completed', summary: 'Written on the second attempt.',
        key_findings: ['Refills are bought in bulk.'], structured_insights: [], source: 'llm',
        served_by: 'test/synthetic-fixture', error_code: null, insights_dropped: 0,
      });
    render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Complete & synthesize' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Interview closed — synthesis not written');
    expect(alert).toHaveTextContent('Nothing was invented in its place');
    expect(screen.getByText('Simulation complete')).toBeInTheDocument();
    // The composer is closed: turns are final even though the analysis is pending.
    expect(screen.queryByRole('textbox', { name: /Interview question for/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Complete & synthesize' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Written on the second attempt/)).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: 'Retry synthesis' })[0]);
    expect(await screen.findByText('Written on the second attempt.')).toBeInTheDocument();
    expect(screen.getByText('Refills are bought in bulk.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry synthesis' })).not.toBeInTheDocument();
    expect(api.completeStudyInterview).toHaveBeenCalledTimes(2);
  });

  it('retries synthesis after a rejected retry without reopening or changing the saved transcript', async () => {
    const rejectedRetry = deferred<{ summary: string }>();
    const successfulRetry = deferred<{ summary: string }>();
    vi.mocked(api.completeStudyInterview)
      .mockResolvedValueOnce({
        id: detailA.id, status: 'completed', summary: null, key_findings: [], structured_insights: [],
        source: 'unavailable', served_by: null, error_code: 'llm_error:AllCandidatesFailed', insights_dropped: 0,
      })
      .mockReturnValueOnce(rejectedRetry.promise)
      .mockReturnValueOnce(successfulRetry.promise);
    render(workspace(detailA));
    await screen.findByText('Saved A answer.');
    const transcript = screen.getByRole('log', { name: 'Interview with Synthetic A' });
    const savedTranscript = transcript.textContent;
    fireEvent.click(screen.getByRole('button', { name: 'Complete & synthesize' }));

    const unavailable = await screen.findByRole('alert');
    expect(api.completeStudyInterview).toHaveBeenCalledTimes(1);
    fireEvent.click(within(unavailable).getByRole('button', { name: 'Retry synthesis' }));
    expect(api.completeStudyInterview).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('textbox', { name: /Interview question for/i })).not.toBeInTheDocument();

    await act(async () => { rejectedRetry.reject(new Error('Synthesis service temporarily unavailable')); });

    const failure = await screen.findByRole('alert');
    const retry = within(failure).getByRole('button', { name: 'Retry synthesis' });
    expect(failure).toHaveTextContent('Synthesis failed');
    expect(within(failure).queryByRole('button', { name: 'Retry question' })).not.toBeInTheDocument();
    expect(screen.getByText('Simulation complete')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /Interview question for/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export transcript as markdown' })).toBeEnabled();
    expect(transcript.textContent).toBe(savedTranscript);
    fireEvent.click(retry);
    fireEvent.click(retry);
    expect(api.completeStudyInterview).toHaveBeenCalledTimes(3);

    await act(async () => { successfulRetry.resolve({ summary: 'Synthesis recovered after retry.' }); });

    expect(screen.getByText('Synthesis recovered after retry.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry synthesis' })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /Interview question for/i })).not.toBeInTheDocument();
    expect(transcript.textContent).toBe(savedTranscript);
    expect(api.completeStudyInterview).toHaveBeenCalledTimes(3);
    expect(api.sendInterviewMessageStream).not.toHaveBeenCalled();
    expect(api.sendInterviewMessage).not.toHaveBeenCalled();
  });

  it('restores the pending-synthesis state from a saved interview after a reload', async () => {
    vi.mocked(api.getStudyInterviewDetail).mockResolvedValueOnce({
      ...detailA, status: 'completed', summary: undefined,
      configuration: { synthesis: { source: 'unavailable', error_code: 'llm_error:AllCandidatesFailed', served_by: null } },
    });
    render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    expect(screen.getByText('Simulation complete')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Retry synthesis' }).length).toBeGreaterThan(0);
    expect(screen.getByLabelText('Synthesis not written')).toHaveTextContent('no model route could write the analysis');
    expect(api.completeStudyInterview).not.toHaveBeenCalled();
  });

  it('renders the entire buffered reply immediately without a timed word reveal', async () => {
    vi.mocked(api.sendInterviewMessageStream).mockRejectedValueOnce(
      Object.assign(new Error('Stream route unavailable'), { status: 405 }),
    );
    vi.mocked(api.sendInterviewMessage).mockResolvedValueOnce(replyFixture);
    render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();

    await act(async () => { sendQuestion('A question with a buffered reply.'); });

    expect(screen.getByText(replyFixture.reply)).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /Interview question for/i })).toBeEnabled();
  });

  it.each([
    { status: 503, errorCode: 'database_unavailable' },
    { kind: 'constructor' },
  ])('keeps non-routing failures distinct from unavailable model capacity', async (failure) => {
    vi.mocked(api.sendInterviewMessageStream).mockRejectedValueOnce(Object.assign(new Error('Storage operation unavailable'), failure));
    render(workspace(detailA));
    await screen.findByText('Saved A answer.');
    await act(async () => { sendQuestion('Keep this failed question.'); });

    expect(screen.getByText('Turn failed')).toBeInTheDocument();
    expect(screen.queryByText('No model route available')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /Interview question for/i })).toHaveValue('Keep this failed question.');
  });

  it('makes the closed mobile context rail inert and restores focus when the open dialog is dismissed', async () => {
    const matchMedia = window.matchMedia;
    vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({ ...matchMedia(query), matches: query.includes('1120px') }));
    render(<InterviewWorkspace studyId={detailA.study_id} interviewId={detailA.id} onBackToInterviews={vi.fn()} onNavigateToPersona={vi.fn()} />);
    await screen.findByText('Saved A answer.');
    const rail = document.querySelector('.iv-rail') as HTMLElement;
    expect(rail.inert).toBe(true);
    expect(rail).toHaveAttribute('aria-hidden', 'true');
    const trigger = screen.getByRole('button', { name: 'Toggle persona context panel' });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole('dialog', { name: 'Interview context' });
    await waitFor(() => expect(dialog).toContainElement(document.activeElement as HTMLElement));
    expect(rail.inert).toBe(false);
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(rail.inert).toBe(true);
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

  it.each(['success', 'failure'] as const)(
    'keeps the current detail loading after an abandoned detail %s',
    async (outcome) => {
      const abandoned = deferred<InterviewDetail>();
      const current = deferred<InterviewDetail>();
      vi.mocked(api.getStudyInterviewDetail)
        .mockReturnValueOnce(abandoned.promise)
        .mockReturnValueOnce(current.promise);
      const view = render(workspace(detailA));
      view.rerender(workspace(detailB));

      await act(async () => {
        if (outcome === 'success') abandoned.resolve(detailA);
        else abandoned.reject(new Error('Abandoned detail failure'));
      });

      expect(screen.getByRole('status')).toHaveTextContent('Preparing the simulation');
      expect(screen.queryByText('Saved A answer.')).not.toBeInTheDocument();
      expect(screen.queryByText('Interview unavailable')).not.toBeInTheDocument();
      expect(api.getStudyPersonaDetail).not.toHaveBeenCalled();

      await act(async () => { current.resolve(detailB); });
      expect(screen.getByText('Saved B answer.')).toBeInTheDocument();
      expect(screen.getByRole('textbox', { name: /Interview question for/i })).toBeEnabled();
    },
  );

  it('keeps revisited persona enrichment when the first visit to the same interview resolves late', async () => {
    const abandoned = deferred<SyntheticPersona>();
    const revisitedPersona = {
      ...personaFixture(detailA),
      demographics: { location: 'Current A location' },
    };
    vi.mocked(api.getStudyPersonaDetail)
      .mockReturnValueOnce(abandoned.promise)
      .mockResolvedValueOnce(personaFixture(detailB))
      .mockResolvedValueOnce(revisitedPersona);
    const view = render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    view.rerender(workspace(detailB));
    expect(await screen.findByText(`Location for ${detailB.id}`)).toBeInTheDocument();
    view.rerender(workspace(detailA));
    expect(await screen.findByText('Current A location')).toBeInTheDocument();

    await act(async () => { abandoned.resolve(personaFixture(detailA)); });

    expect(screen.getByText('Current A location')).toBeInTheDocument();
    expect(screen.queryByText(`Location for ${detailA.id}`)).not.toBeInTheDocument();
  });

  it('keeps the new transcript usable while optional enrichment is pending or fails', async () => {
    const enrichment = deferred<SyntheticPersona>();
    vi.mocked(api.getStudyPersonaDetail)
      .mockResolvedValueOnce(personaFixture(detailA))
      .mockReturnValueOnce(enrichment.promise);
    const view = render(workspace(detailA));
    expect(await screen.findByText(`Location for ${detailA.id}`)).toBeInTheDocument();
    view.rerender(workspace(detailB));
    expect(await screen.findByText('Saved B answer.')).toBeInTheDocument();
    expect(screen.queryByText(`Location for ${detailA.id}`)).not.toBeInTheDocument();
    const input = screen.getByRole('textbox', { name: /Interview question for/i });
    expect(input).toBeEnabled();
    fireEvent.change(input, { target: { value: 'Draft during enrichment.' } });

    await act(async () => { enrichment.reject(new Error('Optional enrichment unavailable')); });

    expect(screen.getByText('Saved B answer.')).toBeInTheDocument();
    expect(input).toBeEnabled();
    expect(input).toHaveValue('Draft during enrichment.');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it.each(['success', 'failure'] as const)(
    'keeps the current synthesis locked after an abandoned synthesis %s on a revisited interview',
    async (outcome) => {
      const abandoned = deferred<{ summary: string }>();
      const current = deferred<{ summary: string }>();
      vi.mocked(api.completeStudyInterview)
        .mockReturnValueOnce(abandoned.promise)
        .mockReturnValueOnce(current.promise);
      const view = render(workspace(detailA));
      expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Complete & synthesize' }));
      view.rerender(workspace(detailB));
      expect(await screen.findByText('Saved B answer.')).toBeInTheDocument();
      view.rerender(workspace(detailA));
      expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Complete & synthesize' }));

      await act(async () => {
        if (outcome === 'success') abandoned.resolve({ summary: 'Abandoned synthesis.' });
        else abandoned.reject(new Error('Abandoned synthesis failure'));
      });

      expect(api.completeStudyInterview).toHaveBeenCalledTimes(2);
      expect(screen.getByRole('textbox', { name: /Interview question for/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /Synthesizing/ })).toBeDisabled();
      expect(screen.getByText('Simulation active')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Toggle persona context panel' })).toHaveAttribute('aria-expanded', 'false');
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();

      await act(async () => { current.resolve({ summary: 'Current synthesis.' }); });
      expect(screen.getByText('Simulation complete')).toBeInTheDocument();
      expect(screen.getByText('Current synthesis.')).toBeInTheDocument();
      expect(screen.queryByText('Abandoned synthesis.')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Toggle persona context panel' })).toHaveAttribute('aria-expanded', 'true');
    },
  );

  it('ignores completed-send callbacks without clearing a newer send frame in the same visit', async () => {
    const completed = deferred<typeof replyFixture>();
    const current = deferred<typeof replyFixture>();
    vi.mocked(api.sendInterviewMessageStream)
      .mockReturnValueOnce(completed.promise)
      .mockReturnValueOnce(current.promise);
    render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    sendQuestion('The first question.');
    const completedDelta = vi.mocked(api.sendInterviewMessageStream).mock.calls[0][3];
    act(() => { completedDelta('The first draft.'); });
    const completedFrame = vi.mocked(requestAnimationFrame).mock.calls[0][0];
    await act(async () => {
      completed.resolve({ ...replyFixture, reply: 'The first canonical answer.' });
    });
    expect(cancelAnimationFrame).toHaveBeenCalledTimes(1);
    sendQuestion('The second question.');
    const [, , , currentDelta, currentSignal] = vi.mocked(api.sendInterviewMessageStream).mock.calls[1];
    act(() => { currentDelta('The current draft'); });
    const currentFrame = vi.mocked(requestAnimationFrame).mock.calls[1][0];

    act(() => {
      completedDelta('A late completed-send delta.');
      completedFrame(0);
      currentDelta(' continues.');
    });

    expect(requestAnimationFrame).toHaveBeenCalledTimes(2);
    expect(cancelAnimationFrame).toHaveBeenCalledTimes(1);
    act(() => { currentFrame(0); });
    expect(screen.getByText('The current draft continues.')).toBeInTheDocument();
    expect(screen.queryByText(/late completed-send delta/)).not.toBeInTheDocument();
    expect(screen.getByText('The first canonical answer.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Waiting for reply' })).toBeDisabled();
    expect(currentSignal?.aborted).toBe(false);

    await act(async () => {
      current.resolve({ ...replyFixture, turn_number: 6, reply: 'The second canonical answer.' });
    });
    expect(screen.getByText('The second canonical answer.')).toBeInTheDocument();
    expect(screen.queryByText('The current draft continues.')).not.toBeInTheDocument();
  });

  it.each([404, 405])('uses the blocking fallback for a current %s before any stream text', async (status) => {
    vi.mocked(api.sendInterviewMessageStream).mockRejectedValueOnce(
      Object.assign(new Error('Stream route unavailable'), { status }),
    );
    vi.mocked(api.sendInterviewMessage).mockResolvedValueOnce(replyFixture);
    render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    sendQuestion('A current fallback question.');

    expect(await screen.findByText(replyFixture.reply)).toBeInTheDocument();
    expect(api.sendInterviewMessage).toHaveBeenCalledTimes(1);
    expect(api.sendInterviewMessage).toHaveBeenCalledWith(
      detailA.study_id, detailA.id, { content: 'A current fallback question.' }, expect.any(AbortSignal),
    );
    expect(screen.getByText('A current fallback question.')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /Interview question for/i })).toBeEnabled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it.each([404, 405])('does not start a fallback after visible stream text followed by %s', async (status) => {
    const stream = deferred<typeof replyFixture>();
    vi.mocked(api.sendInterviewMessageStream).mockReturnValueOnce(stream.promise);
    render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    sendQuestion('Preserve the interrupted question.');
    const onDelta = vi.mocked(api.sendInterviewMessageStream).mock.calls[0][3];
    act(() => { onDelta('A visible partial reply.'); });
    const frame = vi.mocked(requestAnimationFrame).mock.calls[0][0];
    act(() => { frame(0); });
    expect(screen.getByText('A visible partial reply.')).toBeInTheDocument();

    await act(async () => {
      stream.reject(Object.assign(new Error('Stream route unavailable'), { status }));
    });

    expect(api.sendInterviewMessage).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Saved A answer.')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /Interview question for/i }))
      .toHaveValue('Preserve the interrupted question.');
    expect(screen.getByRole('button', { name: 'Send question' })).toBeEnabled();
  });

  it('preserves the current draft after an abandoned stream fails on a revisited interview', async () => {
    const abandoned = deferred<typeof replyFixture>();
    vi.mocked(api.sendInterviewMessageStream).mockReturnValueOnce(abandoned.promise);
    const view = render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    sendQuestion('The abandoned question.');
    view.rerender(workspace(detailB));
    expect(await screen.findByText('Saved B answer.')).toBeInTheDocument();
    view.rerender(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    const input = screen.getByRole('textbox', { name: /Interview question for/i });
    fireEvent.change(input, { target: { value: 'The current draft.' } });

    await act(async () => { abandoned.reject(new Error('Abandoned stream failure')); });

    expect(input).toHaveValue('The current draft.');
    expect(input).toBeEnabled();
    expect(screen.queryByText('The abandoned question.')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(api.sendInterviewMessage).not.toHaveBeenCalled();
  });

  it('aborts detail loading and synthesis when leaving the workspace', async () => {
    const synthesis = deferred<{ summary: string }>();
    vi.mocked(api.completeStudyInterview).mockReturnValueOnce(synthesis.promise);
    const view = render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    const detailSignal = vi.mocked(api.getStudyInterviewDetail).mock.calls[0][2];
    fireEvent.click(screen.getByRole('button', { name: 'Complete & synthesize' }));
    const synthesisSignal = vi.mocked(api.completeStudyInterview).mock.calls[0][2];
    expect(detailSignal?.aborted).toBe(false);
    expect(synthesisSignal?.aborted).toBe(false);
    view.unmount();
    expect(detailSignal?.aborted).toBe(true);
    expect(synthesisSignal?.aborted).toBe(true);
    await act(async () => { synthesis.resolve({ summary: 'Abandoned' }); });
  });

  it('passes the owned abort signal to an active blocking fallback', async () => {
    const fallback = deferred<typeof replyFixture>();
    vi.mocked(api.sendInterviewMessageStream).mockRejectedValueOnce(Object.assign(new Error('Missing route'), { status: 405 }));
    vi.mocked(api.sendInterviewMessage).mockReturnValueOnce(fallback.promise);
    const view = render(workspace(detailA));
    expect(await screen.findByText('Saved A answer.')).toBeInTheDocument();
    sendQuestion('Fallback ownership');
    await waitFor(() => expect(api.sendInterviewMessage).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(api.sendInterviewMessage).mock.calls[0][3];
    expect(signal?.aborted).toBe(false);
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => { fallback.resolve(replyFixture); });
  });
});