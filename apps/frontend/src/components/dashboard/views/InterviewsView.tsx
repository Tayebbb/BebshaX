import React, { useState, useEffect } from 'react';
import {
  MessageSquare,
  Search,
  Filter,
  Plus,
  CheckCircle2,
  AlertCircle,
  Layers,
  Bot,
  Activity,
  Award,
  ChevronRight,
} from 'lucide-react';
import { Interview, InterviewMetrics } from '../../../types';
import { api } from '../../../services/api';
import { CountUp } from '../../../motion/CountUp';

interface InterviewsViewProps {
  studyId: string;
  onOpenInterview: (interviewId: string) => void;
  onNavigateToPersonas: () => void;
}

export const InterviewsView: React.FC<InterviewsViewProps> = ({
  studyId,
  onOpenInterview,
  onNavigateToPersonas,
}) => {
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [metrics, setMetrics] = useState<InterviewMetrics>({
    total_interviews: 0,
    active_interviews: 0,
    completed_interviews: 0,
    total_insights_generated: 0,
  });
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [selectedObjective, setSelectedObjective] = useState<string>('all');

  const fetchInterviews = async () => {
    try {
      setIsLoading(true);
      setError(null);

      const [listRes, metricsRes] = await Promise.all([
        api.listStudyInterviews(studyId, {
          status: selectedStatus !== 'all' ? selectedStatus : undefined,
          objective: selectedObjective !== 'all' ? selectedObjective : undefined,
          search: searchQuery.trim() || undefined,
        }),
        api.getStudyInterviewMetrics(studyId),
      ]);

      setInterviews(listRes.interviews || []);
      setMetrics(metricsRes);
    } catch (err: any) {
      console.error('Failed to load study interviews:', err);
      setError(err.message || 'Failed to load interviews.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchInterviews();
  }, [studyId, selectedStatus, selectedObjective]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchInterviews();
  };

  const filteredInterviews = interviews.filter((item) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      item.persona_name?.toLowerCase().includes(query) ||
      item.objective?.toLowerCase().includes(query) ||
      item.custom_objective?.toLowerCase().includes(query)
    );
  });

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8 animate-fade-in text-[#E0EBEB]">
      {/* 1. Header & Quick Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-teal-500/10 text-teal-300 border border-teal-500/30 flex items-center gap-1">
              <Bot className="w-3 h-3" />
              Adaptive Persona Interviews
            </span>
            <span className="text-xs text-[var(--text-secondary)]">Part 6 Research Layer</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-white tracking-tight">
            Customer Interview Lab
          </h1>
          <p className="text-xs md:text-sm text-[var(--text-secondary)] mt-1">
            Engage with grounded synthetic personas to pressure-test pricing, discover friction,
            and extract structured behavioral insights with turn-level provenance.
          </p>
        </div>

        <button
          onClick={onNavigateToPersonas}
          className="px-5 py-2.5 rounded-xl bg-teal-500 hover:bg-teal-400 text-black font-bold text-xs flex items-center gap-2 shadow-lg shadow-teal-500/20 transition-all cursor-pointer shrink-0 self-start md:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span>New Persona Interview</span>
        </button>
      </div>

      {/* 2. Metrics Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-2xl p-5 space-y-2 shadow-md">
          <div className="flex items-center justify-between text-[var(--text-muted)]">
            <span className="text-xs font-semibold uppercase tracking-wider">Total Interviews</span>
            <MessageSquare className="w-4 h-4 text-teal-400" />
          </div>
          <div className="text-2xl font-black text-white"><CountUp value={metrics.total_interviews} /></div>
          <p className="text-[11px] text-[var(--text-muted)]">Recorded research sessions</p>
        </div>

        <div className="bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-2xl p-5 space-y-2 shadow-md">
          <div className="flex items-center justify-between text-[var(--text-muted)]">
            <span className="text-xs font-semibold uppercase tracking-wider">Active Sessions</span>
            <Activity className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-black text-cyan-400"><CountUp value={metrics.active_interviews} /></div>
          <p className="text-[11px] text-[var(--text-muted)]">Conversations in progress</p>
        </div>

        <div className="bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-2xl p-5 space-y-2 shadow-md">
          <div className="flex items-center justify-between text-[var(--text-muted)]">
            <span className="text-xs font-semibold uppercase tracking-wider">Completed</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-black text-emerald-400"><CountUp value={metrics.completed_interviews} /></div>
          <p className="text-[11px] text-[var(--text-muted)]">Synthesized sessions</p>
        </div>

        <div className="bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-2xl p-5 space-y-2 shadow-md">
          <div className="flex items-center justify-between text-[var(--text-muted)]">
            <span className="text-xs font-semibold uppercase tracking-wider">Structured Insights</span>
            <Award className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-black text-amber-400">
            <CountUp value={metrics.total_insights_generated} />
          </div>
          <p className="text-[11px] text-[var(--text-muted)]">Turn-provenance claims</p>
        </div>
      </div>

      {/* 3. Search and Filters */}
      <div className="bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-2xl p-4 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Search Input */}
        <form onSubmit={handleSearchSubmit} className="flex-1 relative">
          <Search className="w-4 h-4 text-[#5D6F6F] absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by persona name, objective, or topic..."
            className="w-full bg-[var(--bg-card-hover)] border border-[var(--border-medium)] focus:border-teal-500 rounded-xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-[#5D6F6F] focus:outline-none transition-colors"
          />
        </form>

        {/* Filters */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="flex items-center gap-1.5 bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-xl px-3 py-1.5 text-xs">
            <Filter className="w-3.5 h-3.5 text-[var(--text-muted)]" />
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="bg-transparent text-[#B5C7C7] text-xs font-medium focus:outline-none cursor-pointer"
            >
              <option value="all" className="bg-[var(--bg-card-hover)]">All Statuses</option>
              <option value="active" className="bg-[var(--bg-card-hover)]">Active</option>
              <option value="completed" className="bg-[var(--bg-card-hover)]">Completed</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5 bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-xl px-3 py-1.5 text-xs">
            <select
              value={selectedObjective}
              onChange={(e) => setSelectedObjective(e.target.value)}
              className="bg-transparent text-[#B5C7C7] text-xs font-medium focus:outline-none cursor-pointer"
            >
              <option value="all" className="bg-[var(--bg-card-hover)]">All Objectives</option>
              <option value="Problem" className="bg-[var(--bg-card-hover)]">Problem Discovery</option>
              <option value="Pricing" className="bg-[var(--bg-card-hover)]">Pricing & WTP</option>
              <option value="Feature" className="bg-[var(--bg-card-hover)]">Feature Reaction</option>
              <option value="Objection" className="bg-[var(--bg-card-hover)]">Objections</option>
            </select>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-center gap-3 text-red-400 text-xs">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 4. Interviews List Grid */}
      {isLoading ? (
        <div className="p-16 text-center text-[var(--text-secondary)] space-y-4">
          <div className="w-8 h-8 border-3 border-teal-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-xs">Loading study interviews...</p>
        </div>
      ) : filteredInterviews.length === 0 ? (
        <div className="p-12 text-center bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-2xl space-y-4">
          <div className="w-14 h-14 rounded-2xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center text-teal-400 mx-auto">
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
            onClick={onNavigateToPersonas}
            className="px-5 py-2.5 bg-teal-500 hover:bg-teal-400 text-black font-bold rounded-xl text-xs transition-colors cursor-pointer"
          >
            Go to Persona Library
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredInterviews.map((item) => {
            const isCompleted = item.status === 'completed';
            const turnsCount = item.turn_count || 0;
            const maxTurns = item.max_turns || 14;
            const exploredCount = Object.values(item.topics_explored || {}).filter(
              (v) => v === 'explored'
            ).length;
            const insightsCount = item.structured_insights?.length || 0;

            return (
              <div
                key={item.id}
                onClick={() => onOpenInterview(item.id)}
                className="bg-[var(--bg-card-hover)] border border-[var(--border-medium)] hover:border-teal-500/40 rounded-2xl p-5 flex flex-col justify-between space-y-4 transition-all duration-200 cursor-pointer shadow-md hover:shadow-teal-500/5 group"
              >
                {/* Card Top: Persona & Status */}
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-teal-500/20 to-cyan-500/20 border border-teal-500/30 flex items-center justify-center text-teal-300 font-bold text-sm shrink-0">
                        {item.persona_avatar ? (
                          <img
                            src={item.persona_avatar}
                            alt={item.persona_name || 'Persona'}
                            className="w-full h-full rounded-xl object-cover"
                          />
                        ) : (
                          (item.persona_name || 'P').charAt(0)
                        )}
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-white group-hover:text-teal-300 transition-colors line-clamp-1">
                          {item.persona_name || 'Synthetic Persona'}
                        </h3>
                        <p className="text-[11px] text-[#7E8F8F] line-clamp-1">
                          {item.persona_occupation || 'Target Customer Archetype'}
                        </p>
                      </div>
                    </div>

                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold border shrink-0 ${
                        isCompleted
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          : 'bg-teal-500/10 text-teal-400 border-teal-500/30 flex items-center gap-1'
                      }`}
                    >
                      {!isCompleted && <span className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-pulse" />}
                      {isCompleted ? 'Completed' : 'Active'}
                    </span>
                  </div>

                  {/* Objective & Tier */}
                  <div className="bg-[var(--bg-card-hover)] border border-[#213030] rounded-xl p-2.5 text-xs space-y-1">
                    <div className="text-[10px] text-[#6E8080] font-semibold uppercase tracking-wider">
                      Research Objective
                    </div>
                    <div className="text-white font-medium text-xs line-clamp-1">
                      {item.objective}
                    </div>
                  </div>
                </div>

                {/* Card Middle: Progress & Topics */}
                <div className="space-y-3 pt-2 border-t border-white/5 text-xs text-[var(--text-secondary)]">
                  {/* Turn Progress */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[11px]">
                      <span>Turns: <strong className="text-white">{turnsCount}</strong> / {maxTurns}</span>
                      <span className="text-teal-400 capitalize font-medium">{item.length_tier} Tier</span>
                    </div>
                    <div className="w-full h-1.5 bg-[#1B2525] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-teal-500 to-cyan-400"
                        style={{ width: `${Math.min(100, (turnsCount / maxTurns) * 100)}%` }}
                      />
                    </div>
                  </div>

                  {/* Explored Topics & Insights Badges */}
                  <div className="flex items-center justify-between text-[11px] pt-1">
                    <span className="flex items-center gap-1 text-[var(--text-secondary)]">
                      <Layers className="w-3.5 h-3.5 text-cyan-400" />
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
                <div className="pt-2 flex items-center justify-between text-xs font-semibold text-teal-400 group-hover:translate-x-0.5 transition-transform">
                  <span>{isCompleted ? 'View Analysis & Transcript' : 'Continue Interview'}</span>
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
