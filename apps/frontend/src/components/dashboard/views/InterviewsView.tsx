import React, { useState, useEffect, useRef } from 'react';
import {
  MessageSquare,
  Search,
  Filter,
  Plus,
  CheckCircle2,
  RefreshCw,
  Layers,
  Activity,
  Award,
  ChevronRight,
} from 'lucide-react';
import { Interview, InterviewMetrics } from '../../../types';
import { api } from '../../../services/api';
import { CountUp } from '../../../motion/CountUp';
import { useRouteReady } from '../../../performance/routeTiming';
import { synthesisUnavailable } from '../../../utils/interviewSynthesis';

interface InterviewsViewProps {
  studyId: string;
  onOpenInterview: (interviewId: string) => void;
  onNavigateToPersonas: () => void;
}

const OBJECTIVE_LABELS: Record<string, string> = {
  problem_discovery: 'Problem Discovery',
  pricing_wtp: 'Pricing & WTP',
  feature_reaction: 'Feature Reaction',
  objections: 'Objections',
};

// Known keys get their label; a snake_case key is humanised; free text (a batch
// script's own wording) is shown verbatim rather than re-cased into a headline.
const objectiveLabel = (objective?: string, custom?: string) => {
  if (custom) return custom;
  if (!objective) return 'General Discovery';
  if (OBJECTIVE_LABELS[objective]) return OBJECTIVE_LABELS[objective];
  return /^[a-z0-9_]+$/.test(objective)
    ? objective.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
    : objective;
};

export const InterviewsView: React.FC<InterviewsViewProps> = ({
  studyId,
  onOpenInterview,
  onNavigateToPersonas,
}) => {
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [metrics, setMetrics] = useState<InterviewMetrics | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  useRouteReady(!isLoading, error ? 'error' : interviews.length ? 'content' : 'empty');
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const requestGeneration = useRef(0);

  // Filters
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [selectedObjective, setSelectedObjective] = useState<string>('all');

  const fetchInterviews = async () => {
    const generation = ++requestGeneration.current;
    const isCurrent = () => generation === requestGeneration.current;
    setIsLoading(true);
    setError(null);
    setMetricsError(null);
    setMetrics(null);

    void api.getStudyInterviewMetrics(studyId).then((result) => {
      if (isCurrent()) setMetrics(result);
    }).catch((err: unknown) => {
      if (isCurrent()) {
        setMetricsError(`Failed to load interview metrics: ${err instanceof Error ? err.message : 'Please retry.'}`);
      }
    });
    try {
      const listRes = await api.listStudyInterviews(studyId, {
        status: selectedStatus !== 'all' ? selectedStatus : undefined,
        objective: selectedObjective !== 'all' ? selectedObjective : undefined,
        search: searchQuery.trim() || undefined,
      });

      if (isCurrent()) setInterviews(listRes.interviews || []);
    } catch (err: unknown) {
      if (isCurrent()) {
        setInterviews([]);
        setError(`Failed to load interviews: ${err instanceof Error ? err.message : 'Please retry.'}`);
      }
    } finally {
      if (isCurrent()) setIsLoading(false);
    }
  };

  useEffect(() => {
    void fetchInterviews();
    return () => { requestGeneration.current += 1; };
  }, [studyId, selectedStatus, selectedObjective]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void fetchInterviews();
  };

  const navigateToPersonas = () => {
    requestGeneration.current += 1;
    onNavigateToPersonas();
  };

  const openInterview = (interviewId: string) => {
    requestGeneration.current += 1;
    onOpenInterview(interviewId);
  };

  const filteredInterviews = interviews.filter((item) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    // Topics are printed on every card, so they must be searchable too
    // (live 2026-09-14: "pricing" found nothing).
    const topics = Object.keys(item.topics_explored ?? {}).map((topic) => topic.replace(/_/g, ' ').toLowerCase());
    return (
      item.persona_name?.toLowerCase().includes(query) ||
      item.persona_occupation?.toLowerCase().includes(query) ||
      item.objective?.toLowerCase().includes(query) ||
      item.custom_objective?.toLowerCase().includes(query) ||
      topics.some((topic) => topic.includes(query))
    );
  });

  return (
    <div className="w-full min-w-0 p-6 md:p-8 max-w-7xl mx-auto space-y-8 animate-fade-in text-[var(--text-primary)]">
      {[error, metricsError].map((message, index) => message && (
        <div
          key={index}
          role="alert"
          className="flex items-center justify-between gap-3 rounded-xl px-5 py-3 text-sm font-medium"
          style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.4)', color: 'var(--status-error-text)' }}
        >
          <span>{message}</span>
          <button
            type="button"
            onClick={fetchInterviews}
            style={{ background: 'transparent', border: '1px solid currentColor', borderRadius: '6px', padding: '4px 12px', color: 'inherit', cursor: 'pointer', fontWeight: 600, fontSize: '0.82rem', whiteSpace: 'nowrap' }}
          >
            Retry
          </button>
        </div>
      ))}
      {/* 1. Header & Quick Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-[var(--text-primary)] tracking-normal">
            Customer Interview Lab
          </h1>
          <p className="text-xs md:text-sm text-[var(--text-secondary)] mt-1">
            Engage with synthetic personas to pressure-test pricing, discover friction,
            and extract structured behavioral insights with turn-level provenance.
          </p>
        </div>

        <button
          onClick={navigateToPersonas}
          className="bx-btn bx-btn--primary shrink-0 self-start md:self-auto"
        >
          <Plus className="w-4 h-4" aria-hidden="true" />
          <span>New Persona Interview</span>
        </button>
      </div>

      {/* 2. Metrics Cards */}
      {!metrics && !metricsError && <p role="status" className="text-xs text-[var(--text-secondary)]">Loading interview metrics...</p>}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-2xl p-5 space-y-2 shadow-md">
          <div className="flex items-center justify-between text-[var(--text-muted)]">
            <span className="text-xs font-semibold uppercase tracking-wider">Total Interviews</span>
            <MessageSquare className="w-4 h-4 text-[var(--accent-primary)]" />
          </div>
          <div className="text-2xl font-black text-white">{metrics ? <CountUp value={metrics.total_interviews} /> : <span aria-label="Total interviews unavailable">--</span>}</div>
          <p className="text-[0.72rem] text-[var(--text-muted)]">Recorded research sessions</p>
        </div>

        <div className="bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-2xl p-5 space-y-2 shadow-md">
          <div className="flex items-center justify-between text-[var(--text-muted)]">
            <span className="text-xs font-semibold uppercase tracking-wider">Active Sessions</span>
            <Activity className="w-4 h-4 text-[var(--accent-primary)]" />
          </div>
          <div className="text-2xl font-black text-[var(--accent-primary)]">{metrics ? <CountUp value={metrics.active_interviews} /> : <span aria-label="Active sessions unavailable">--</span>}</div>
          <p className="text-[0.72rem] text-[var(--text-muted)]">Conversations in progress</p>
        </div>

        <div className="bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-2xl p-5 space-y-2 shadow-md">
          <div className="flex items-center justify-between text-[var(--text-muted)]">
            <span className="text-xs font-semibold uppercase tracking-wider">Completed</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-black text-emerald-400">{metrics ? <CountUp value={metrics.completed_interviews} /> : <span aria-label="Completed interviews unavailable">--</span>}</div>
          <p className="text-[0.72rem] text-[var(--text-muted)]">Synthesized sessions</p>
        </div>

        <div className="bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-2xl p-5 space-y-2 shadow-md">
          <div className="flex items-center justify-between text-[var(--text-muted)]">
            <span className="text-xs font-semibold uppercase tracking-wider">Structured Insights</span>
            <Award className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-black text-amber-400">
            {metrics ? <CountUp value={metrics.total_insights_generated} /> : <span aria-label="Structured insights unavailable">--</span>}
          </div>
          <p className="text-[0.72rem] text-[var(--text-muted)]">Turn-provenance claims</p>
        </div>
      </div>

      {/* 3. Search and Filters */}
      <div className="bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-2xl p-4 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Search Input */}
        <form onSubmit={handleSearchSubmit} className="flex-1 relative">
          <Search className="w-4 h-4 text-[var(--text-muted)] absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
                        aria-label="Search interviews"
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by persona name, objective, or topic..."
            className="w-full bg-[var(--bg-card-hover)] border border-[var(--border-medium)] focus:border-[var(--focus-ring)] rounded-xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-[var(--text-muted)] focus:outline-none transition-colors"
          />
        </form>

        {/* Filters */}
        <div className="flex items-center gap-3 shrink-0">
          <button
            type="button"
            onClick={fetchInterviews}
            disabled={isLoading}
            aria-label="Refresh interviews"
            title="Refresh interviews"
            className="w-8 h-8 flex items-center justify-center text-[var(--text-label)] disabled:opacity-50 disabled:cursor-wait"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <div className="flex items-center gap-1.5 bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-xl px-3 py-1.5 text-xs">
            <Filter className="w-3.5 h-3.5 text-[var(--text-muted)]" />
            <select
              aria-label="Interview status"
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="bg-transparent border-0 pr-6 text-[var(--text-label)] text-xs font-medium focus:outline-none cursor-pointer"
            >
              <option value="all" className="bg-[var(--bg-card-hover)]">All Statuses</option>
              <option value="active" className="bg-[var(--bg-card-hover)]">Active</option>
              <option value="completed" className="bg-[var(--bg-card-hover)]">Completed</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5 bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-xl px-3 py-1.5 text-xs">
            <select
              aria-label="Interview objective"
              value={selectedObjective}
              onChange={(e) => setSelectedObjective(e.target.value)}
              className="bg-transparent border-0 pr-6 text-[var(--text-label)] text-xs font-medium focus:outline-none cursor-pointer"
            >
              <option value="all" className="bg-[var(--bg-card-hover)]">All Objectives</option>
              <option value="problem_discovery" className="bg-[var(--bg-card-hover)]">Problem Discovery</option>
              <option value="pricing_wtp" className="bg-[var(--bg-card-hover)]">Pricing & WTP</option>
              <option value="feature_reaction" className="bg-[var(--bg-card-hover)]">Feature Reaction</option>
              <option value="objections" className="bg-[var(--bg-card-hover)]">Objections</option>
            </select>
          </div>
        </div>
      </div>

      {/* 4. Interviews List Grid */}
      {isLoading ? (
        <div className="p-16 text-center text-[var(--text-secondary)] space-y-4">
          <div className="w-8 h-8 border-3 border-[var(--accent-primary)] border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-xs">Loading study interviews...</p>
        </div>
      ) : error ? null : filteredInterviews.length === 0 ? (
        <div className="p-12 text-center bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-2xl space-y-4">
          <div className="w-14 h-14 rounded-2xl bg-[var(--accent-subtle)] border border-[var(--border-subtle)] flex items-center justify-center text-[var(--accent-primary)] mx-auto">
            <MessageSquare className="w-7 h-7" />
          </div>
          <div className="space-y-1">
            <h3 className="text-base font-bold text-white">No Interviews Found</h3>
            <p className="text-xs text-[var(--text-secondary)] max-w-md mx-auto">
              {searchQuery || selectedStatus !== 'all'
                ? 'No interview sessions match your active filters. Try clearing your search.'
                : 'You have not conducted any persona interviews yet. Launch your first adaptive interview from the Persona Library!'}
            </p>
          </div>
          <button
            onClick={navigateToPersonas}
            className="bx-btn bx-btn--primary"
          >
            Go to Persona Library
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredInterviews.map((item) => {
            const isCompleted = item.status === 'completed';
            const awaitingSynthesis = synthesisUnavailable(item);
            const turnsCount = item.turn_count || 0;
            // A missing max_turns is unknown, not "14" — the bar and label say so.
            const maxTurns = typeof item.max_turns === 'number' && item.max_turns > 0 ? item.max_turns : null;
            // Every turn is spent: the persona will not answer again, only the synthesis is left.
            const turnCapReached = !isCompleted && maxTurns !== null && turnsCount >= maxTurns;
            const exploredCount = Object.values(item.topics_explored || {}).filter(
              (v) => v === 'explored'
            ).length;
            const insightsCount = item.structured_insights?.length || 0;

            return (
              <div
                key={item.id}
                role="button"
                tabIndex={0}
                aria-label={`Open interview with ${item.persona_name || 'synthetic persona'}`}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    openInterview(item.id);
                  }
                }}
                onClick={() => openInterview(item.id)}
                className="bg-[var(--bg-card)] border border-[var(--border-medium)] hover:border-[var(--border-hover)] rounded-2xl p-5 flex flex-col justify-between space-y-4 transition-colors duration-200 cursor-pointer group"
              >
                {/* Card Top: Persona & Status */}
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-[var(--accent-subtle)] border border-[var(--border-subtle)] flex items-center justify-center text-[var(--accent-primary)] font-bold text-sm shrink-0">
                        {item.persona_avatar ? (
                          <img
                            src={item.persona_avatar}
                            alt={item.persona_name || 'Persona'}
                            loading="lazy"
                            decoding="async"
                            className="w-full h-full rounded-xl object-cover"
                          />
                        ) : (
                          (item.persona_name || 'P').charAt(0)
                        )}
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-white transition-colors line-clamp-1">
                          {item.persona_name || 'Synthetic Persona'}
                        </h3>
                        <p className="text-[0.72rem] text-[var(--text-secondary)] line-clamp-1">
                          {item.persona_occupation || 'Target Customer Archetype'}
                        </p>
                      </div>
                    </div>

                    <span
                      className={`px-2 py-0.5 rounded-full text-[0.72rem] font-bold border shrink-0 ${
                        isCompleted
                          ? awaitingSynthesis
                            ? 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                            : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          : 'bg-[var(--accent-subtle)] text-[var(--accent-primary)] border-[var(--border-subtle)] flex items-center gap-1'
                      }`}
                    >
                      {!isCompleted && !turnCapReached && (
                        <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent-primary)]" />
                      )}
                      {isCompleted ? (awaitingSynthesis ? 'Synthesis pending' : 'Completed') : turnCapReached ? 'Ready to synthesize' : 'Active'}
                    </span>
                  </div>

                  {/* Objective & Tier */}
                  <div className="bg-[var(--bg-card-hover)] border border-[var(--border-subtle)] rounded-xl p-2.5 text-xs space-y-1">
                    <div className="text-[0.72rem] text-[var(--text-muted)] font-semibold uppercase tracking-wider">
                      Research Objective
                    </div>
                    <div className="text-white font-medium text-xs line-clamp-1">
                      {objectiveLabel(item.objective, item.custom_objective)}
                    </div>
                  </div>
                </div>

                {/* Card Middle: Progress & Topics */}
                <div className="space-y-3 pt-2 border-t border-white/5 text-xs text-[var(--text-secondary)]">
                  {/* Turn Progress */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[0.72rem]">
                      <span>
                        Turns: <strong className="text-white">{turnsCount}</strong>
                        {maxTurns !== null ? ` / ${maxTurns}` : ''}
                      </span>
                      <span className="text-[var(--text-secondary)] capitalize font-medium">{item.length_tier} Tier</span>
                    </div>
                    <div className="w-full h-1.5 bg-[var(--border-subtle)] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[var(--accent-primary)]"
                        style={{ width: maxTurns !== null ? `${Math.min(100, (turnsCount / maxTurns) * 100)}%` : '0%' }}
                      />
                    </div>
                  </div>

                  {/* Explored Topics & Insights Badges */}
                  <div className="flex items-center justify-between text-[0.72rem] pt-1">
                    <span className="flex items-center gap-1 text-[var(--text-secondary)]">
                      <Layers className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                      {exploredCount} topics explored
                    </span>
                    {insightsCount > 0 && (
                      <span className="flex items-center gap-1 text-amber-400 font-semibold">
                        <Award className="w-3.5 h-3.5" />
                        {insightsCount} insights
                      </span>
                    )}
                  </div>
                </div>

                {/* Card Bottom: Action CTA */}
                <div className="pt-2 flex items-center justify-between text-xs font-semibold text-[var(--accent-primary)]">
                  <span>{isCompleted ? (awaitingSynthesis ? 'Retry synthesis & view transcript' : 'View Analysis & Transcript') : turnCapReached ? 'Generate synthesis' : 'Continue Interview'}</span>
                  <ChevronRight className="w-4 h-4" />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
