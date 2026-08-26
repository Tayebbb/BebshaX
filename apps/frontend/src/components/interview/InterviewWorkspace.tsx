import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowUp,
  Check,
  ChevronLeft,
  Copy,
  Download,
  PanelRight,
  Sparkles,
} from 'lucide-react';
import {
  Interview,
  InterviewInsight,
  InterviewTurn,
  SyntheticPersona,
} from '../../types';
import { api } from '../../services/api';
import './interview.css';

interface InterviewWorkspaceProps {
  studyId: string;
  interviewId: string;
  onBackToInterviews: () => void;
  onNavigateToPersona?: (personaId: string) => void;
}

/** Failure classes surfaced by the backend (RULES R2/R6: never blur them). */
type FailureKindUI = 'context_window' | 'no_route' | 'finished' | 'not_found' | 'generic';

function classifyFailure(message: string, status?: number): FailureKindUI {
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
  generic: {
    title: 'Turn failed',
    body: 'The persona did not answer this question. You can retry — your question is preserved below.',
  },
};

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Progressive word reveal of an ALREADY-received reply (presentation only). */
const RevealText: React.FC<{ text: string; animate: boolean }> = ({ text, animate }) => {
  const words = useMemo(() => text.split(/(\s+)/), [text]);
  const [count, setCount] = useState(animate ? 0 : words.length);
  useEffect(() => {
    if (!animate || prefersReducedMotion()) {
      setCount(words.length);
      return;
    }
    setCount(0);
    const step = Math.max(1, Math.ceil(words.length / 26)); // ~600ms total
    const timer = setInterval(() => {
      setCount((c) => {
        if (c >= words.length) {
          clearInterval(timer);
          return words.length;
        }
        return c + step;
      });
    }, 24);
    return () => clearInterval(timer);
  }, [text, animate, words.length]);
  return <>{words.slice(0, count).join('')}</>;
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
  const [isSending, setIsSending] = useState(false);
  const [elapsedS, setElapsedS] = useState(0);
  const [isCompleting, setIsCompleting] = useState(false);
  const [sendError, setSendError] = useState<{ kind: FailureKindUI; detail: string } | null>(null);
  const [copiedTurnId, setCopiedTurnId] = useState<string | null>(null);
  const [flashTurn, setFlashTurn] = useState<number | null>(null);
  const [railOpen, setRailOpen] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [lastRevealId, setLastRevealId] = useState<string | null>(null);
  const [streamText, setStreamText] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const turnRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const pendingQuestionRef = useRef<string>('');

  // Pause ambient motion when the tab is hidden (performance §33).
  useEffect(() => {
    const onVis = () => setHidden(document.hidden);
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
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
    setIsLoading(true);
    setLoadError(null);
    try {
      // Backend returns the interview FLAT (id/status/turns at top level).
      const data = await api.getStudyInterviewDetail(studyId, interviewId);
      setInterview(data as Interview);
      setTurns(data.turns || []);
      setInsights(data.structured_insights || []);
      setSuggested(data.suggested_questions || []);
      if (data.persona_id) {
        api
          .getStudyPersonaDetail(studyId, data.persona_id)
          .then(setPersona)
          .catch(() => {}); // profile rail is optional enrichment
      }
    } catch (err: any) {
      setLoadError(err?.message || 'Failed to load this interview.');
    } finally {
      setIsLoading(false);
    }
  }, [studyId, interviewId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  }, [turns.length, isSending, streamText]);

  const personaName = interview?.persona_name || persona?.name || 'Synthetic Persona';
  const personaRole =
    persona?.archetype ||
    (persona?.demographics as any)?.occupation ||
    interview?.persona_occupation ||
    'Customer persona';
  const isCompleted = interview?.status === 'completed';

  const send = async (raw?: string) => {
    const text = (raw ?? input).trim();
    if (!text || isSending || !interview || isCompleted) return;
    setSendError(null);
    setInput('');
    pendingQuestionRef.current = text;
    setIsSending(true);
    setStreamText(null);

    const optimistic: InterviewTurn = {
      id: `pending_${Date.now()}`,
      turn_number: turns.length + 1,
      role: 'interviewer',
      content: text,
      created_at: new Date().toISOString(),
    };
    setTurns((prev) => [...prev, optimistic]);

    const applyDone = (res: any, streamed: boolean) => {
      const personaTurn: InterviewTurn = {
        id: `turn_${res.turn_number}_${Date.now()}`,
        turn_number: res.turn_number,
        role: 'persona',
        content: res.reply,
        topic: res.topic,
        latency_ms: res.latency_ms,
        served_by: res.served_by,
        retrieved_memories: res.retrieved_memories || res.persona_reply?.retrieved_memories || [],
        created_at: new Date().toISOString(),
      };
      // Streamed text was already read live — don't re-animate the canonical swap.
      setLastRevealId(streamed ? null : personaTurn.id);
      setTurns((prev) => [...prev, personaTurn]);
      setSuggested(res.suggested_questions || []);
      setInterview((prev) =>
        prev
          ? {
              ...prev,
              turn_count: res.turn_count ?? prev.turn_count,
              max_turns: res.max_turns ?? prev.max_turns,
              status: res.is_finished ? 'completed' : prev.status,
              topics_explored: res.topics_explored || prev.topics_explored,
            }
          : prev
      );
      pendingQuestionRef.current = '';
    };

    try {
      let streamedAny = false;
      try {
        const res = await api.sendInterviewMessageStream(studyId, interviewId, text, (chunk) => {
          streamedAny = true;
          setStreamText((prev) => (prev ?? '') + chunk);
        });
        applyDone(res, streamedAny);
      } catch (streamErr: any) {
        // Older backend without the stream route — or transport-level failure
        // before anything streamed — falls back to the blocking endpoint.
        if (!streamedAny && (streamErr?.status === 404 || streamErr?.status === 405)) {
          const res = await api.sendInterviewMessage(studyId, interviewId, { content: text });
          applyDone(res, false);
        } else {
          throw streamErr;
        }
      }
    } catch (err: any) {
      // Honest failure: remove the unanswered question from the transcript,
      // return it to the composer, and classify the failure.
      setTurns((prev) => prev.filter((t) => t.id !== optimistic.id));
      setInput(text);
      // Backend-emitted kinds are only trusted when we have copy for them.
      const kind: FailureKindUI =
        err?.kind && err.kind in FAILURE_COPY
          ? (err.kind as FailureKindUI)
          : classifyFailure(err?.message || '', err?.status);
      setSendError({ kind, detail: err?.message || 'Unknown failure' });
    } finally {
      setStreamText(null);
      setIsSending(false);
    }
  };

  const completeInterview = async () => {
    if (isCompleting || !interview) return;
    setIsCompleting(true);
    setSendError(null);
    try {
      const res = await api.completeStudyInterview(studyId, interviewId);
      setInterview((prev) =>
        prev
          ? {
              ...prev,
              status: 'completed',
              summary: res.summary ?? prev.summary,
              key_findings: res.key_findings ?? prev.key_findings,
            }
          : prev
      );
      if (Array.isArray(res.structured_insights)) setInsights(res.structured_insights);
      setRailOpen(true);
    } catch (err: any) {
      setSendError({ kind: 'generic', detail: err?.message || 'Synthesis failed' });
    } finally {
      setIsCompleting(false);
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
    turnRefs.current[turnNumber]?.scrollIntoView({
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
      block: 'center',
    });
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

  const onComposerKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
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
        <div className="iv-ambient" aria-hidden="true" />
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
        <div className="iv-ambient" aria-hidden="true" />
        <div className="iv-loading">
          <div className="iv-error" style={{ maxWidth: 460 }}>
            <div className="iv-error-title">Interview unavailable</div>
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

  return (
    <div className={`iv-root${hidden ? ' iv-paused' : ''}${isCompleted ? ' iv-complete' : ''}`}>
      <div className="iv-ambient" aria-hidden="true" />

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
            <div className="iv-id-name">{personaName}</div>
            <div className="iv-id-role">{personaRole}</div>
          </div>
        </div>

        <span className={`iv-sim-status${isCompleted ? ' iv-done' : ''}`}>
          <span className="iv-dot" aria-hidden="true" />
          {isCompleted ? 'Simulation complete' : 'Simulation active'}
        </span>

        <div className="iv-header-actions">
          {!isCompleted && hasTurns && (
            <button
              type="button"
              className="iv-ghost-btn iv-primary"
              onClick={completeInterview}
              disabled={isCompleting || isSending}
            >
              <Sparkles size={13} aria-hidden="true" />
              <span className="iv-label">{isCompleting ? 'Synthesizing…' : 'Complete & synthesize'}</span>
            </button>
          )}
          <button
            type="button"
            className="iv-ghost-btn"
            onClick={exportTranscript}
            disabled={!hasTurns}
            aria-label="Export transcript as markdown"
          >
            <Download size={13} aria-hidden="true" />
            <span className="iv-label">Export</span>
          </button>
          <button
            type="button"
            className="iv-ghost-btn iv-rail-toggle"
            onClick={() => setRailOpen((v) => !v)}
            aria-label="Toggle persona context panel"
            aria-expanded={railOpen}
          >
            <PanelRight size={14} aria-hidden="true" />
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
              <div className="iv-empty-kicker">Simulated participant</div>
              <h1 className="iv-empty-title">{personaName}</h1>
              <p className="iv-empty-sub">
                Your simulated customer is ready to talk. Every answer is generated live and
                grounded in this persona's evidence — nothing is scripted.
              </p>
              {suggested.length > 0 && (
                <div className="iv-suggestions">
                  {suggested.slice(0, 3).map((q) => (
                    <button
                      key={q}
                      type="button"
                      className="iv-suggestion"
                      onClick={() => send(q)}
                      disabled={isSending}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="iv-scroll" ref={scrollRef}>
              <div className="iv-thread" role="log" aria-label={`Interview with ${personaName}`}>
                {turns.map((turn) => {
                  const isPersona = turn.role === 'persona' || turn.role === 'assistant';
                  return (
                    <div
                      key={turn.id}
                      ref={(el) => {
                        turnRefs.current[turn.turn_number] = el;
                      }}
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
                          {isPersona && turn.served_by ? ` · ${turn.served_by}` : ''}
                        </span>
                      </div>
                      <div className="iv-turn-body">
                        {isPersona ? (
                          <RevealText text={turn.content} animate={turn.id === lastRevealId} />
                        ) : (
                          turn.content
                        )}
                      </div>
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
                <div className="iv-error-title">{FAILURE_COPY[sendError.kind].title}</div>
                <div className="iv-error-body">{FAILURE_COPY[sendError.kind].body}</div>
                <div className="iv-error-actions">
                  {sendError.kind !== 'finished' && (
                    <button
                      type="button"
                      className="iv-ghost-btn iv-primary"
                      onClick={() => send(pendingQuestionRef.current || input)}
                      disabled={isSending}
                    >
                      Retry question
                    </button>
                  )}
                  {sendError.kind === 'finished' && (
                    <button
                      type="button"
                      className="iv-ghost-btn iv-primary"
                      onClick={completeInterview}
                      disabled={isCompleting}
                    >
                      Generate synthesis
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
                    disabled={isSending}
                    title={q}
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}

            {!isCompleted ? (
              <>
                <div className="iv-composer">
                  <textarea
                    ref={inputRef}
                    className="iv-input"
                    rows={1}
                    placeholder={`Ask ${personaName.split(' ')[0]} about their world…`}
                    value={input}
                    onChange={(e) => {
                      setInput(e.target.value);
                      e.target.style.height = 'auto';
                      e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
                    }}
                    onKeyDown={onComposerKey}
                    disabled={isSending}
                    aria-label={`Interview question for ${personaName}`}
                  />
                  <button
                    type="button"
                    className="iv-send"
                    onClick={() => send()}
                    disabled={!input.trim() || isSending}
                    aria-label="Send question"
                  >
                    <ArrowUp size={17} aria-hidden="true" />
                  </button>
                </div>
                <div className="iv-composer-note">
                  {maxTurns > 0
                    ? `Turn ${Math.min(turnCount + 1, maxTurns)} of ${maxTurns} · every reply carries its real model route`
                    : 'Every reply carries its real model route'}
                </div>
              </>
            ) : (
              <div className="iv-composer-note">
                Interview complete — the transcript is read-only. Insights are in the panel.
              </div>
            )}
          </div>
        </div>

        {/* Context rail */}
        {railOpen && (
          <button
            type="button"
            className="iv-scrim"
            aria-label="Close persona context panel"
            onClick={() => setRailOpen(false)}
          />
        )}
        <aside className={`iv-rail${railOpen ? ' iv-open' : ''}`} aria-label="Interview context">
          <section className="iv-rail-block">
            <div className="iv-rail-section-title">Interview</div>
            <div className="iv-kv">
              <div className="iv-kv-row">
                <span className="iv-kv-k">Objective</span>
                <span className="iv-kv-v">{interview.objective}</span>
              </div>
              <div className="iv-kv-row">
                <span className="iv-kv-k">Depth</span>
                <span className="iv-kv-v iv-mono">{interview.length_tier}</span>
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
              <div className="iv-rail-section-title">Topic coverage</div>
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
              <div className="iv-rail-section-title">Participant</div>
              <div className="iv-kv" style={{ marginBottom: 12 }}>
                {(persona.demographics as any)?.age != null && (
                  <div className="iv-kv-row">
                    <span className="iv-kv-k">Age</span>
                    <span className="iv-kv-v">{(persona.demographics as any).age}</span>
                  </div>
                )}
                {(persona.demographics as any)?.location && (
                  <div className="iv-kv-row">
                    <span className="iv-kv-k">Location</span>
                    <span className="iv-kv-v">{(persona.demographics as any).location}</span>
                  </div>
                )}
                {(persona.demographics as any)?.income_bracket && (
                  <div className="iv-kv-row">
                    <span className="iv-kv-k">Income</span>
                    <span className="iv-kv-v">{(persona.demographics as any).income_bracket}</span>
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
                  <div className="iv-rail-section-title" style={{ marginTop: 16 }}>
                    Pain points
                  </div>
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
                  onClick={() => onNavigateToPersona(interview.persona_id)}
                >
                  Full profile
                </button>
              )}
            </section>
          )}

          {isCompleted && (interview.summary || (interview.key_findings?.length ?? 0) > 0) && (
            <section className="iv-rail-block">
              <div className="iv-rail-section-title">Synthesis</div>
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

          {insights.length > 0 && (
            <section className="iv-rail-block">
              <div className="iv-rail-section-title">Structured insights</div>
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
