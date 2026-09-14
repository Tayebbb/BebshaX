import React, { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  ChevronLeft,
  Copy,
  Download,
  PanelRight,
  Sparkles,
  X,
} from 'lucide-react';
import {
  Interview,
  InterviewInsight,
  InterviewTurn,
  SyntheticPersona,
} from '../../types';
import { api } from '../../services/api';
import type { SendInterviewMessageResponse } from '../../types/interview';
import { beginOperationTiming, useRouteReady } from '../../performance/routeTiming';
import { fromUnknownError } from '../../utils/apiError';
import { synthesisUnavailable } from '../../utils/interviewSynthesis';
import { useDialogA11y } from '../../utils/useDialogA11y';
import { ConsistencyFlags, MemoryDisclosure, RouteDisclosure } from '../common/MemoryDisclosure';
import { RequestIdTag } from '../common/RequestIdTag';
import { PromptInputBox } from '../ui/PromptInputBox';
import './interview.css';

interface InterviewWorkspaceProps {
  studyId: string;
  interviewId: string;
  onBackToInterviews: () => void;
  onNavigateToPersona?: (personaId: string) => void;
}

/** Failure classes surfaced by the backend (RULES R2/R6: never blur them). */
type FailureKindUI = 'context_window' | 'no_route' | 'finished' | 'not_found' | 'synthesis_unavailable' | 'generic';

function classifyFailure(message: string, status?: number, errorCode?: string): FailureKindUI {
  if (errorCode === 'database_unavailable') return 'generic';
  if (status === 413 || /context/i.test(message)) return 'context_window';
  if (status === 503 || /no llm route/i.test(message)) return 'no_route';
  if (status === 400 && /finish/i.test(message)) return 'finished';
  if (status === 404) return 'not_found';
  return 'generic';
}

const FAILURE_COPY: Record<FailureKindUI, { title: string; body: string }> = {
  context_window: {
    title: 'Simulation unavailable',
    body:
      'This interview needs more context than the currently available model capacity can hold. ' +
      'Your persona and transcript were NOT silently degraded — nothing was truncated.',
  },
  no_route: {
    title: 'No model route available',
    body:
      'Every eligible free-tier route failed or is cooling down. The question was not answered — ' +
      'wait a moment and try again.',
  },
  finished: {
    title: 'Interview complete',
    body: 'This interview has reached its final turn. Generate the synthesis to extract insights.',
  },
  not_found: {
    title: 'Interview unavailable',
    body: 'This interview or its persona could not be found — it may have been removed. Nothing was answered.',
  },
  synthesis_unavailable: {
    title: 'Interview closed — synthesis not written',
    body:
      'Every turn is saved and the interview is complete, but no model route could write the analysis right now. ' +
      'Nothing was invented in its place — retry the synthesis once routes recover.',
  },
  generic: {
    title: 'Turn failed',
    body: 'The persona did not answer this question. You can retry — your question is preserved below.',
  },
};

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const DEPTH_LABELS: Record<string, string> = {
  short: 'Short pulse (6 turns)',
  standard: 'Standard (14 turns)',
  deep: 'Deep dive (24 turns)',
};

const initialsOf = (name?: string) =>
  (name || 'P')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join('');

export const InterviewWorkspace: React.FC<InterviewWorkspaceProps> = ({
  studyId,
  interviewId,
  onBackToInterviews,
  onNavigateToPersona,
}) => {
  const [interview, setInterview] = useState<Interview | null>(null);
  const [persona, setPersona] = useState<SyntheticPersona | null>(null);
  const [turns, setTurns] = useState<InterviewTurn[]>([]);
  const [insights, setInsights] = useState<InterviewInsight[]>([]);
  const [suggested, setSuggested] = useState<string[]>([]);

  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  useRouteReady(!isLoading, loadError ? 'error' : 'content');
  const [isSending, setIsSending] = useState(false);
  const [elapsedS, setElapsedS] = useState(0);
  const [isCompleting, setIsCompleting] = useState(false);
  const [sendError, setSendError] = useState<{
    operation: 'question' | 'synthesis';
    kind: FailureKindUI;
    detail: string;
    requestId?: string | null;
  } | null>(null);
  const [copiedTurnId, setCopiedTurnId] = useState<string | null>(null);
  const [flashTurn, setFlashTurn] = useState<number | null>(null);
  const [railOpen, setRailOpen] = useState(false);
  /** Desktop only: the context rail hidden to give the transcript the width. */
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [compactRail, setCompactRail] = useState(() => window.matchMedia('(max-width: 1120px)').matches);
  const [streamText, setStreamText] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const railRef = useRef<HTMLElement>(null);
  const autoSynthesizeRef = useRef(false);
  const railId = useId();
  useDialogA11y(railRef, compactRail && railOpen, () => setRailOpen(false));
  useLayoutEffect(() => {
    if (railRef.current) railRef.current.inert = compactRail && !railOpen;
  }, [compactRail, railOpen, isLoading]);
  useEffect(() => {
    const query = window.matchMedia('(max-width: 1120px)');
    const sync = () => setCompactRail(query.matches);
    query.addEventListener('change', sync);
    return () => query.removeEventListener('change', sync);
  }, []);
  const turnRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const pendingQuestionRef = useRef<string>('');
  const requestEpochRef = useRef(0);
  const loadControllerRef = useRef<AbortController | null>(null);
  const streamControllerRef = useRef<AbortController | null>(null);
  // A streamed answer arrives as dozens of small SSE chunks. Committing each one
  // to state re-renders the entire workspace (every turn, both rails) per token,
  // so chunks are buffered and flushed at most once per frame.
  const streamBufferRef = useRef<string>('');
  const streamRafRef = useRef<number | null>(null);

  const cancelStreamFlush = useCallback(() => {
    if (streamRafRef.current !== null) {
      cancelAnimationFrame(streamRafRef.current);
      streamRafRef.current = null;
    }
  }, []);

  const pushStreamChunk = useCallback((chunk: string, isCurrent: () => boolean) => {
    if (!isCurrent()) return;
    streamBufferRef.current += chunk;
    if (streamRafRef.current !== null) return;
    streamRafRef.current = requestAnimationFrame(() => {
      if (!isCurrent()) return;
      streamRafRef.current = null;
      setStreamText(streamBufferRef.current);
    });
  }, []);

  // Elapsed-time counter: free-tier turns honestly take 60–190s.
  useEffect(() => {
    if (!isSending) {
      setElapsedS(0);
      return;
    }
    const t = setInterval(() => setElapsedS((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [isSending]);

  const load = useCallback(async () => {
    const requestEpoch = ++requestEpochRef.current;
    loadControllerRef.current?.abort();
    const controller = new AbortController();
    loadControllerRef.current = controller;
    const isCurrent = () => requestEpochRef.current === requestEpoch && !controller.signal.aborted;
    streamControllerRef.current?.abort();
    streamControllerRef.current = null;
    cancelStreamFlush();
    streamBufferRef.current = '';
    pendingQuestionRef.current = '';
    setStreamText(null);
    setIsSending(false);
    setIsCompleting(false);
    setSendError(null);
    setInput('');
    setPersona(null);
    setRailOpen(false);
    setIsLoading(true);
    setLoadError(null);
    try {
      // Backend returns the interview FLAT (id/status/turns at top level).
      const data = await api.getStudyInterviewDetail(studyId, interviewId, controller.signal);
      if (!isCurrent()) return;
      setInterview(data);
      setTurns(data.turns || []);
      setInsights(data.structured_insights || []);
      setSuggested(data.suggested_questions || []);
      if (data.persona_id) {
        api
          .getStudyPersonaDetail(studyId, data.persona_id)
          .then((profile) => {
            if (isCurrent()) setPersona(profile);
          })
          .catch(() => {}); // profile rail is optional enrichment
      }
    } catch (err: unknown) {
      if (isCurrent()) setLoadError(fromUnknownError(err).message || 'Failed to load this interview.');
    } finally {
      if (isCurrent()) setIsLoading(false);
    }
  }, [studyId, interviewId, cancelStreamFlush]);

  useEffect(() => {
    void load();
    return () => {
      requestEpochRef.current += 1;
      loadControllerRef.current?.abort();
      streamControllerRef.current?.abort();
      streamControllerRef.current = null;
      cancelStreamFlush();
      streamBufferRef.current = '';
    };
  }, [load, cancelStreamFlush]);

  // The composer is the point of the page: focus it once the interview is in
  // and after each answer lands, unless the user is already typing somewhere
  // (live 2026-09-14: activeElement stayed on <body> on entry and after replies).
  const transcriptLength = turns.length;
  useEffect(() => {
    if (isLoading || isSending || isCompleting) return;
    const composer = inputRef.current;
    if (!composer || composer.disabled) return;
    const active = document.activeElement;
    const typingElsewhere = active instanceof HTMLElement && active !== document.body
      && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.isContentEditable) && active !== composer;
    if (!typingElsewhere && (active === document.body || active === null || active === composer)) {
      composer.focus({ preventScroll: true });
    }
  }, [isLoading, isSending, isCompleting, transcriptLength]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  }, [turns.length, isSending]);

  // While an answer streams, keep the transcript pinned without restarting a
  // smooth-scroll animation on every flush — that fights itself and stutters.
  useEffect(() => {
    if (streamText === null) return;
    endRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' });
  }, [streamText]);

  const personaName = interview?.persona_name || persona?.name || 'Synthetic Persona';
  const personaRole =
    persona?.archetype ||
    persona?.demographics?.occupation ||
    interview?.persona_occupation ||
    'Customer persona';
  const isCompleted = interview?.status === 'completed';
  // The cap is a persisted fact (turn_count/max_turns); the server refuses
  // further questions past it, so the composer must close on reload too.
  const capReached =
    !isCompleted && !!interview && (interview.max_turns || 0) > 0 && (interview.turn_count ?? 0) >= (interview.max_turns || 0);
  const awaitingSynthesis = synthesisUnavailable(interview);
  const synthesisActionLabel = isCompleting
    ? 'Synthesizing interview'
    : isCompleted ? 'Retry synthesis' : 'Complete & synthesize';

  const send = async (raw?: string) => {
    const text = (raw ?? input).trim();
    if (!text || isSending || isCompleting || isLoading || !interview || isCompleted || capReached || streamControllerRef.current) return;
    const requestEpoch = requestEpochRef.current;
    const controller = new AbortController();
    const markTiming = beginOperationTiming();
    streamControllerRef.current = controller;
    const isCurrent = () =>
      requestEpochRef.current === requestEpoch &&
      streamControllerRef.current === controller &&
      !controller.signal.aborted;
    setSendError(null);
    setInput('');
    pendingQuestionRef.current = text;
    setIsSending(true);
    cancelStreamFlush();
    streamBufferRef.current = '';
    setStreamText(null);

    const optimistic: InterviewTurn = {
      id: `pending_${Date.now()}`,
      turn_number: turns.length + 1,
      role: 'interviewer',
      content: text,
      created_at: new Date().toISOString(),
    };
    setTurns((prev) => [...prev, optimistic]);

    const applyDone = (res: SendInterviewMessageResponse) => {
      if (!isCurrent()) return;
      markTiming('canonical-response');
      const personaTurn: InterviewTurn = {
        id: `turn_${res.turn_number}_${Date.now()}`,
        turn_number: res.turn_number,
        role: 'persona',
        content: res.reply,
        topic: res.topic,
        latency_ms: res.latency_ms ?? undefined,
        served_by: res.served_by ?? undefined,
        retrieved_memories: res.retrieved_memories || res.persona_reply?.retrieved_memories || [],
        identity_drift: Boolean(res.identity_drift ?? res.persona_reply?.identity_drift),
        drift_notes: res.drift_notes ?? res.persona_reply?.drift_notes ?? [],
        contradiction_detected: Boolean(res.contradiction_detected ?? res.persona_reply?.contradiction_detected),
        contradiction_details: res.contradiction_details ?? res.persona_reply?.contradiction_details ?? null,
        created_at: new Date().toISOString(),
      };
      setTurns((prev) => [...prev, personaTurn]);
      setSuggested(res.suggested_questions || []);
      setInterview((prev) =>
        prev
          ? {
              ...prev,
              turn_count: res.turn_count ?? prev.turn_count,
              max_turns: res.max_turns ?? prev.max_turns,
              topics_explored: res.topics_explored || prev.topics_explored,
            }
          : prev
      );
      pendingQuestionRef.current = '';
      // The final in-cap exchange: the server will refuse more questions, so
      // write the synthesis now instead of showing a closed composer with no insights.
      if (res.is_finished) autoSynthesizeRef.current = true;
    };

    try {
      let streamedAny = false;
      try {
        const res = await api.sendInterviewMessageStream(
          studyId,
          interviewId,
          text,
          (chunk) => {
            if (!isCurrent()) return;
            if (chunk) markTiming('ai-first-text');
            streamedAny = true;
            pushStreamChunk(chunk, isCurrent);
          },
          controller.signal
        );
        applyDone(res);
      } catch (streamErr: unknown) {
        if (!isCurrent()) return;
        // Older backend without the stream route — or transport-level failure
        // before anything streamed — falls back to the blocking endpoint.
        const streamFailure = fromUnknownError(streamErr);
        if (!streamedAny && (streamFailure.status === 404 || streamFailure.status === 405)) {
          const res = await api.sendInterviewMessage(studyId, interviewId, { content: text }, controller.signal);
          applyDone(res);
        } else {
          throw streamErr;
        }
      }
    } catch (err: unknown) {
      if (!isCurrent()) return;
      // Honest failure: remove the unanswered question from the transcript,
      // return it to the composer, and classify the failure.
      setTurns((prev) => prev.filter((t) => t.id !== optimistic.id));
      setInput(text);
      // Backend-emitted kinds are only trusted when we have copy for them.
      const failure = fromUnknownError(err);
      const emittedKind = err && typeof err === 'object' && 'kind' in err ? err.kind : undefined;
      const kind: FailureKindUI =
        typeof emittedKind === 'string' && Object.prototype.hasOwnProperty.call(FAILURE_COPY, emittedKind)
          ? (emittedKind as FailureKindUI)
          : classifyFailure(failure.message || '', failure.status, failure.errorCode);
      setSendError({ operation: 'question', kind, detail: failure.message || 'Unknown failure', requestId: failure.requestId ?? null });
    } finally {
      if (isCurrent()) {
        cancelStreamFlush();
        streamBufferRef.current = '';
        setStreamText(null);
        setIsSending(false);
        streamControllerRef.current = null;
        if (autoSynthesizeRef.current) {
          autoSynthesizeRef.current = false;
          void completeInterview();
        }
      }
    }
  };

  const completeInterview = async () => {
    if (isCompleting || isSending || isLoading || !interview || streamControllerRef.current) return;
    const requestEpoch = requestEpochRef.current;
    const controller = new AbortController();
    streamControllerRef.current = controller;
    const isCurrent = () => requestEpochRef.current === requestEpoch &&
      streamControllerRef.current === controller && !controller.signal.aborted;
    setIsCompleting(true);
    setSendError(null);
    try {
      const res = await api.completeStudyInterview(studyId, interviewId, controller.signal);
      if (!isCurrent()) return;
      const closedWithoutSynthesis = res.source === 'unavailable' || !res.summary;
      setInterview((prev) =>
        prev
          ? {
              ...prev,
              status: 'completed',
              summary: res.summary ?? (closedWithoutSynthesis ? undefined : prev.summary),
              key_findings: res.key_findings ?? prev.key_findings,
              configuration: {
                ...prev.configuration,
                synthesis: {
                  source: res.source ?? (closedWithoutSynthesis ? 'unavailable' : 'llm'),
                  served_by: res.served_by ?? null,
                  error_code: res.error_code ?? null,
                  insights_dropped: res.insights_dropped ?? 0,
                },
              },
            }
          : prev
      );
      if (Array.isArray(res.structured_insights)) setInsights(res.structured_insights);
      if (closedWithoutSynthesis) {
        setSendError({ operation: 'synthesis', kind: 'synthesis_unavailable', detail: res.error_code || 'synthesis_unavailable', requestId: null });
      } else {
        setRailOpen(true);
      }
    } catch (err: unknown) {
      if (isCurrent()) {
        const failure = fromUnknownError(err);
        setSendError({ operation: 'synthesis', kind: 'generic', detail: failure.message || 'Synthesis failed', requestId: failure.requestId ?? null });
      }
    } finally {
      if (isCurrent()) {
        setIsCompleting(false);
        streamControllerRef.current = null;
      }
    }
  };

  const copyTurn = (turn: InterviewTurn) => {
    const speaker = turn.role === 'persona' ? personaName : 'You';
    navigator.clipboard.writeText(`${speaker}: ${turn.content}`);
    setCopiedTurnId(turn.id);
    setTimeout(() => setCopiedTurnId(null), 1800);
  };

  const jumpToTurn = (turnNumber: number) => {
    setRailOpen(false);
    setFlashTurn(turnNumber);
    const target = turnRefs.current[turnNumber];
    target?.scrollIntoView({
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
      block: 'center',
    });
    // Move focus with the highlight: keyboard and screen-reader users land on
    // the cited turn instead of staying on the insight chip (live 2026-09-14).
    target?.focus({ preventScroll: true });
    setTimeout(() => setFlashTurn(null), 2600);
  };

  const exportTranscript = () => {
    if (!interview) return;
    const header = `# Interview — ${personaName}\nObjective: ${interview.objective}\nDate: ${new Date(
      interview.created_at
    ).toLocaleString()}\n\n---\n\n`;
    const body = turns
      .map((t) => `[Turn ${t.turn_number}] ${t.role === 'persona' ? personaName : 'YOU'}:\n${t.content}\n`)
      .join('\n');
    const blob = new Blob([header + body], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `interview_${interview.id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exploredTopics = useMemo(() => {
    const map = interview?.topics_explored || {};
    return Object.entries(map).map(([id, status]) => ({
      id,
      label: id.replace(/_/g, ' '),
      explored: status === 'explored',
    }));
  }, [interview?.topics_explored]);

  const turnCount = interview?.turn_count ?? turns.length;
  const maxTurns = interview?.max_turns || 0;
  const progress = maxTurns > 0 ? Math.min(100, (turnCount / maxTurns) * 100) : 0;

  /* ------------------------------------------------------------------ */

  if (isLoading) {
    return (
      <div className="iv-root">
        <div className="iv-loading" role="status">
          <div className="iv-loading-ring" aria-hidden="true" />
          <span className="iv-loading-text">Preparing the simulation…</span>
        </div>
      </div>
    );
  }

  if (loadError || !interview) {
    return (
      <div className="iv-root">
        <div className="iv-loading">
          <div className="iv-error" role="alert" style={{ maxWidth: 460 }}>
            <h1 className="iv-error-title">Interview unavailable</h1>
            <div className="iv-error-body">
              {loadError || 'This interview could not be loaded, or you do not have access to it.'}
            </div>
            <div className="iv-error-actions">
              <button type="button" className="iv-ghost-btn" onClick={load}>
                Try again
              </button>
              <button type="button" className="iv-ghost-btn" onClick={onBackToInterviews}>
                Back to interviews
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const hasTurns = turns.length > 0;
  const failureCopy = sendError?.operation === 'synthesis' && sendError.kind !== 'synthesis_unavailable'
    ? {
        title: 'Synthesis failed',
        body: 'The synthesis could not be written. Your saved transcript is unchanged. You can retry the synthesis.',
      }
    : FAILURE_COPY[sendError?.kind ?? 'generic'];

  return (
    <div className={`iv-root${isCompleted ? ' iv-complete' : ''}`}>
      {/* ---------------------------------------------------------------- */}
      <header className="iv-header">
        <button type="button" className="iv-back" onClick={onBackToInterviews}>
          <ChevronLeft size={15} aria-hidden="true" />
          Interviews
        </button>

        <div className="iv-id">
          <div className="iv-orb" aria-hidden="true">
            {initialsOf(personaName)}
          </div>
          <div style={{ minWidth: 0 }}>
            <h1 className="iv-id-name">{personaName}</h1>
            <div className="iv-id-role">{personaRole}</div>
          </div>
        </div>

        <span className={`iv-sim-status${isCompleted ? ' iv-done' : ''}`}>
          <span className="iv-dot" aria-hidden="true" />
          {isCompleted ? 'Simulation complete' : capReached ? 'Turn limit reached' : 'Simulation active'}
        </span>

        <div className="iv-header-actions">
          {!isCompleted && hasTurns && (
            <button
              type="button"
              className="iv-ghost-btn iv-primary"
              onClick={completeInterview}
              disabled={isCompleting || isSending}
              aria-label={synthesisActionLabel}
              title={synthesisActionLabel}
              aria-busy={isCompleting}
            >
              <Sparkles size={16} aria-hidden="true" />
              <span className="iv-label">{isCompleting ? 'Synthesizing…' : 'Complete & synthesize'}</span>
            </button>
          )}
          {awaitingSynthesis && (
            <button
              type="button"
              className="iv-ghost-btn iv-primary"
              onClick={completeInterview}
              disabled={isCompleting || isSending}
              aria-label={synthesisActionLabel}
              title={synthesisActionLabel}
              aria-busy={isCompleting}
            >
              <Sparkles size={16} aria-hidden="true" />
              <span className="iv-label">{isCompleting ? 'Synthesizing…' : 'Retry synthesis'}</span>
            </button>
          )}
          <button
            type="button"
            className="iv-ghost-btn"
            onClick={exportTranscript}
            disabled={!hasTurns}
            aria-label="Export transcript as markdown"
            title="Export transcript as markdown"
          >
            <Download size={16} aria-hidden="true" />
            <span className="iv-label">Export</span>
          </button>
          <button
            type="button"
            className="iv-ghost-btn iv-rail-toggle"
            onClick={() => (compactRail ? setRailOpen((v) => !v) : setRailCollapsed((v) => !v))}
            aria-label="Toggle persona context panel"
            title={compactRail || railCollapsed ? 'Show persona context panel' : 'Hide persona context panel'}
            aria-controls={railId}
            aria-expanded={compactRail ? railOpen : !railCollapsed}
          >
            <PanelRight size={18} aria-hidden="true" />
          </button>
        </div>
      </header>

      {/* ---------------------------------------------------------------- */}
      <div className="iv-body">
        <div className="iv-stage">
          {!hasTurns && !isSending ? (
            <div className="iv-empty">
              <div className="iv-empty-orb" aria-hidden="true">
                {initialsOf(personaName)}
              </div>
              <h2 className="iv-empty-title">{personaName}</h2>
              <p className="iv-empty-sub">
                Your simulated customer is ready to talk. Every answer is generated live and
                drawn from this persona's profile and any evidence it cites — nothing is scripted.
              </p>
              {suggested.length > 0 && (
                <div className="iv-suggestions">
                  {suggested.slice(0, 3).map((q) => (
                    <button
                      key={q}
                      type="button"
                      className="iv-suggestion"
                      onClick={() => send(q)}
                      disabled={isSending || isCompleting}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="iv-scroll" ref={scrollRef}>
              <div className="iv-thread" role="log" aria-label={`Interview with ${personaName}`} aria-live="polite" aria-relevant="additions">
                {turns.map((turn) => {
                  const isPersona = turn.role === 'persona' || turn.role === 'assistant';
                  return (
                    <div
                      key={turn.id}
                      ref={(el) => {
                        turnRefs.current[turn.turn_number] = el;
                      }}
                      tabIndex={-1}
                      aria-label={`Turn ${turn.turn_number}, ${isPersona ? personaName : 'you'}`}
                      className={`iv-turn ${isPersona ? 'iv-persona' : 'iv-you'}${
                        flashTurn === turn.turn_number ? ' iv-flash' : ''
                      }`}
                    >
                      <div className="iv-turn-head">
                        <span className="iv-speaker">{isPersona ? personaName : 'You'}</span>
                        <span className="iv-turn-meta">
                          {`T${turn.turn_number}`}
                          {isPersona && turn.latency_ms != null
                            ? ` · ${(turn.latency_ms / 1000).toFixed(1)}s`
                            : ''}
                        </span>
                      </div>
                      <div className="iv-turn-body">
                        {turn.content}
                      </div>
                      {isPersona && (
                        <>
                          <ConsistencyFlags
                            identityDrift={turn.identity_drift}
                            driftNotes={turn.drift_notes}
                            contradictionDetected={turn.contradiction_detected}
                            contradictionDetails={turn.contradiction_details}
                            compact
                          />
                          <MemoryDisclosure memories={turn.retrieved_memories} compact />
                          <RouteDisclosure servedBy={turn.served_by} latencyMs={turn.latency_ms} compact />
                        </>
                      )}
                      <div className="iv-turn-actions">
                        <button
                          type="button"
                          className="iv-mini-btn"
                          onClick={() => copyTurn(turn)}
                          aria-label={`Copy turn ${turn.turn_number}`}
                        >
                          {copiedTurnId === turn.id ? (
                            <Check size={11} aria-hidden="true" />
                          ) : (
                            <Copy size={11} aria-hidden="true" />
                          )}{' '}
                          {copiedTurnId === turn.id ? 'Copied' : 'Copy'}
                        </button>
                      </div>
                    </div>
                  );
                })}

                {isSending && streamText !== null && (
                  <div className="iv-turn iv-persona" aria-live="polite">
                    <div className="iv-turn-head">
                      <span className="iv-speaker">{personaName}</span>
                      <span className="iv-turn-meta" style={{ opacity: 1 }}>
                        speaking…
                      </span>
                    </div>
                    <div className="iv-turn-body">
                      {streamText}
                      <span className="iv-cursor" aria-hidden="true" style={{ marginLeft: 4 }} />
                    </div>
                  </div>
                )}

                {isSending && streamText === null && (
                  <div className="iv-thinking" role="status" aria-live="polite">
                    <div className="iv-thinking-line">
                      <span className="iv-cursor" aria-hidden="true" />
                      {personaName.split(' ')[0]} is thinking through your question…
                    </div>
                    <div className="iv-thinking-sub">
                      {elapsedS}s — routed across free-tier models; long answers are normal
                    </div>
                  </div>
                )}
                <div ref={endRef} />
              </div>
            </div>
          )}

          {/* Composer zone */}
          <div className="iv-composer-zone">
            {sendError && (
              <div className="iv-error" role="alert">
                <div className="iv-error-title">{failureCopy.title}</div>
                <div className="iv-error-body">{failureCopy.body}</div>
                {sendError.requestId && (
                  <div style={{ marginTop: '6px' }}>
                    <RequestIdTag requestId={sendError.requestId} />
                  </div>
                )}
                <div className="iv-error-actions">
                  {sendError.operation === 'question' && sendError.kind !== 'finished' && sendError.kind !== 'synthesis_unavailable' && (
                    <button
                      type="button"
                      className="iv-ghost-btn iv-primary"
                      onClick={() => send(pendingQuestionRef.current || input)}
                      disabled={isSending || isCompleting}
                    >
                      Retry question
                    </button>
                  )}
                  {sendError.kind === 'finished' && (
                    <button
                      type="button"
                      className="iv-ghost-btn iv-primary"
                      onClick={completeInterview}
                      disabled={isCompleting || isSending}
                    >
                      Generate synthesis
                    </button>
                  )}
                  {(sendError.operation === 'synthesis' || sendError.kind === 'synthesis_unavailable') && (
                    <button
                      type="button"
                      className="iv-ghost-btn iv-primary"
                      onClick={completeInterview}
                      disabled={isCompleting || isSending}
                    >
                      Retry synthesis
                    </button>
                  )}
                  <button type="button" className="iv-ghost-btn" onClick={() => setSendError(null)}>
                    Dismiss
                  </button>
                </div>
              </div>
            )}

            {!isCompleted && hasTurns && suggested.length > 0 && !isSending && (
              <div className="iv-chips" aria-label="Suggested follow-up questions">
                {suggested.slice(0, 3).map((q) => (
                  <button
                    key={q}
                    type="button"
                    className="iv-chip"
                    onClick={() => send(q)}
                    disabled={isSending || isCompleting}
                    title={q}
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}

            {!isCompleted && !capReached ? (
              <PromptInputBox
                textareaRef={inputRef}
                value={input}
                onValueChange={setInput}
                onSend={(text) => send(text)}
                isLoading={isSending}
                disabled={isSending || isCompleting}
                maxHeight={140}
                placeholder={`Ask ${personaName.split(' ')[0]} about their world…`}
                aria-label={`Interview question for ${personaName}`}
                sendLabel="Send question"
                leftActions={
                  maxTurns > 0 ? (
                    <span className="iv-turn-counter">
                      Turn {Math.min(turnCount + 1, maxTurns)} of {maxTurns}
                    </span>
                  ) : null
                }
                footer="Every reply carries its real model route"
              />
            ) : capReached ? (
              <div className="iv-composer-note" role="status">
                {isCompleting
                  ? 'Turn limit reached — synthesizing the insights…'
                  : `Turn limit reached (${turnCount} of ${maxTurns}). Complete the interview to synthesize its insights.`}
                {!isCompleting && (
                  <button type="button" className="iv-ghost-btn iv-primary" onClick={completeInterview} disabled={isSending} style={{ marginLeft: 12 }}>
                    <Sparkles size={14} aria-hidden="true" />
                    <span className="iv-label">Complete &amp; synthesize</span>
                  </button>
                )}
              </div>
            ) : (
              <div className="iv-composer-note">
                {awaitingSynthesis
                  ? 'Interview complete — the transcript is read-only. The synthesis has not been written yet; retry it from the panel.'
                  : 'Interview complete — the transcript is read-only. Insights are in the panel.'}
              </div>
            )}
          </div>
        </div>

        {/* Context rail */}
        {compactRail && railOpen && (
          <button
            type="button"
            className="iv-scrim"
            aria-label="Close persona context panel"
            onClick={() => setRailOpen(false)}
          />
        )}
        <aside id={railId} ref={railRef} className={`iv-rail${railOpen ? ' iv-open' : ''}${!compactRail && railCollapsed ? ' iv-collapsed' : ''}`} aria-label="Interview context"
          role={compactRail ? 'dialog' : undefined} aria-modal={compactRail && railOpen ? true : undefined}
          aria-hidden={compactRail && !railOpen ? true : undefined} tabIndex={-1}>
          {compactRail && (
            <button type="button" className="iv-ghost-btn" aria-label="Close interview context" title="Close interview context" onClick={() => setRailOpen(false)}>
              <X size={16} aria-hidden="true" />
            </button>
          )}
          <section className="iv-rail-block">
            <h2 className="iv-rail-section-title">Interview</h2>
            <div className="iv-kv">
              <div className="iv-kv-row">
                <span className="iv-kv-k">Objective</span>
                <span className="iv-kv-v">{interview.custom_objective?.trim() || interview.objective}</span>
              </div>
              <div className="iv-kv-row">
                <span className="iv-kv-k">Depth</span>
                <span className="iv-kv-v">{DEPTH_LABELS[interview.length_tier] ?? interview.length_tier}</span>
              </div>
              <div className="iv-kv-row">
                <span className="iv-kv-k">Turns</span>
                <span className="iv-kv-v iv-mono">
                  {turnCount}
                  {maxTurns > 0 ? ` / ${maxTurns}` : ''}
                </span>
              </div>
            </div>
            {maxTurns > 0 && (
              <div className="iv-progress-track" aria-hidden="true">
                <div className="iv-progress-fill" style={{ width: `${progress}%` }} />
              </div>
            )}
          </section>

          {exploredTopics.length > 0 && (
            <section className="iv-rail-block">
              <h2 className="iv-rail-section-title">Topic coverage</h2>
              <div className="iv-topic-chips">
                {exploredTopics.map((t) => (
                  <span key={t.id} className={`iv-topic${t.explored ? ' iv-explored' : ''}`}>
                    {t.label}
                  </span>
                ))}
              </div>
            </section>
          )}

          {persona && (
            <section className="iv-rail-block">
              <h2 className="iv-rail-section-title">Participant</h2>
              <div className="iv-kv" style={{ marginBottom: 12 }}>
                {persona.demographics?.age != null && (
                  <div className="iv-kv-row">
                    <span className="iv-kv-k">Age</span>
                    <span className="iv-kv-v">{persona.demographics.age}</span>
                  </div>
                )}
                {persona.demographics?.location && (
                  <div className="iv-kv-row">
                    <span className="iv-kv-k">Location</span>
                    <span className="iv-kv-v">{persona.demographics.location}</span>
                  </div>
                )}
                {persona.demographics?.income_or_budget && (
                  <div className="iv-kv-row">
                    <span className="iv-kv-k">Income</span>
                    <span className="iv-kv-v">{persona.demographics.income_or_budget}</span>
                  </div>
                )}
                {typeof persona.grounding_score === 'number' && persona.grounding_score > 0 && (
                  <div className="iv-kv-row">
                    <span className="iv-kv-k">Grounding</span>
                    <span className="iv-grounding">
                      {Math.round(persona.grounding_score * 100)}%
                    </span>
                  </div>
                )}
              </div>
              {persona.quote && <div className="iv-quote">“{persona.quote}”</div>}
              {(persona.pain_points?.length ?? 0) > 0 && (
                <>
                  <h3 className="iv-rail-section-title" style={{ marginTop: 16 }}>
                    Pain points
                  </h3>
                  <div className="iv-trait-list">
                    {persona.pain_points.slice(0, 4).map((p) => (
                      <div key={p} className="iv-trait">
                        {p}
                      </div>
                    ))}
                  </div>
                </>
              )}
              {onNavigateToPersona && (
                <button
                  type="button"
                  className="iv-ghost-btn"
                  style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}
                  onClick={() => {
                    setRailOpen(false);
                    onNavigateToPersona(interview.persona_id);
                  }}
                >
                  Full profile
                </button>
              )}
            </section>
          )}

          {isCompleted && (interview.summary || (interview.key_findings?.length ?? 0) > 0) && (
            <section className="iv-rail-block">
              <h2 className="iv-rail-section-title">Synthesis</h2>
              {interview.summary && <p className="iv-summary">{interview.summary}</p>}
              {(interview.key_findings?.length ?? 0) > 0 && (
                <div className="iv-trait-list" style={{ marginTop: 10 }}>
                  {interview.key_findings!.map((f) => (
                    <div key={f} className="iv-finding iv-trait">
                      {f}
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {awaitingSynthesis && (
            <section className="iv-rail-block" aria-label="Synthesis not written">
              <h2 className="iv-rail-section-title">Synthesis</h2>
              <p className="iv-summary">{FAILURE_COPY.synthesis_unavailable.body}</p>
              <button
                type="button"
                className="iv-ghost-btn"
                style={{ marginTop: 12, width: '100%', justifyContent: 'center' }}
                onClick={completeInterview}
                disabled={isCompleting || isSending}
              >
                {isCompleting ? 'Synthesizing…' : 'Retry synthesis'}
              </button>
            </section>
          )}

          {insights.length > 0 && (
            <section className="iv-rail-block">
              <h2 className="iv-rail-section-title">Structured insights</h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {insights.map((ins) => (
                  <div key={ins.id} className="iv-insight">
                    <span className="iv-insight-type">{ins.type.replace(/_/g, ' ')}</span>
                    <span className="iv-insight-title">{ins.title}</span>
                    <span className="iv-insight-desc">{ins.description}</span>
                    {(ins.supporting_turn_numbers?.length ?? 0) > 0 && (
                      <div className="iv-insight-turns">
                        {ins.supporting_turn_numbers.map((n) => (
                          <button
                            key={n}
                            type="button"
                            className="iv-turn-ref"
                            onClick={() => jumpToTurn(n)}
                            aria-label={`Jump to turn ${n}`}
                          >
                            T{n}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
};
