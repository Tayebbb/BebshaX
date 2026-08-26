import React, { useState, useEffect, useRef } from 'react';
import {
  Send,
  Sparkles,
  Bot,
  User,
  CheckCircle2,
  AlertCircle,
  Clock,
  Layers,
  ChevronLeft,
  Bookmark,
  Award,
  TrendingUp,
  FileText,
  Copy,
  Check,
  Download,
  AlertTriangle,
  Info,
} from 'lucide-react';
import {
  Interview,
  InterviewTurn,
  InterviewInsight,
  InterviewDetailResponse,
  SyntheticPersona,
} from '../../../types';
import { api } from '../../../services/api';

interface InterviewWorkspaceViewProps {
  studyId: string;
  interviewId: string;
  onBackToInterviews: () => void;
  onNavigateToPersona?: (personaId: string) => void;
}

export const InterviewWorkspaceView: React.FC<InterviewWorkspaceViewProps> = ({
  studyId,
  interviewId,
  onBackToInterviews,
  onNavigateToPersona,
}) => {
  const [interview, setInterview] = useState<Interview | null>(null);
  const [persona, setPersona] = useState<SyntheticPersona | null>(null);
  const [turns, setTurns] = useState<InterviewTurn[]>([]);
  const [insights, setInsights] = useState<InterviewInsight[]>([]);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [topics, setTopics] = useState<{ id: string; label: string; status: 'explored' | 'not_explored' }[]>([]);

  const [inputMessage, setInputMessage] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSending, setIsSending] = useState<boolean>(false);
  const [isCompleting, setIsCompleting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [highlightedTurnNumber, setHighlightedTurnNumber] = useState<number | null>(null);
  const [copiedTurnId, setCopiedTurnId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'chat' | 'synthesis'>('chat');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const turnRefs = useRef<{ [turnNum: number]: HTMLDivElement | null }>({});

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const fetchInterviewData = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data: InterviewDetailResponse = await api.getStudyInterviewDetail(studyId, interviewId);
      setInterview(data.interview);
      setTurns(data.turns);
      setInsights(data.insights || []);
      setSuggestedQuestions(data.suggested_questions || []);
      setTopics(data.topics || []);

      if (data.interview.status === 'completed') {
        setActiveTab('synthesis');
      }

      // Fetch persona details if persona_id is present
      if (data.interview.persona_id) {
        try {
          const personaData = await api.getStudyPersonaDetail(studyId, data.interview.persona_id);
          setPersona(personaData);
        } catch {
          // Non-critical if persona detail fails
        }
      }
    } catch (err: any) {
      console.error('Failed to load interview details:', err);
      setError(err.message || 'Failed to load interview.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchInterviewData();
  }, [studyId, interviewId]);

  useEffect(() => {
    if (activeTab === 'chat') {
      scrollToBottom();
    }
  }, [turns, activeTab]);

  const handleSendMessage = async (customText?: string) => {
    const textToSend = (customText || inputMessage).trim();
    if (!textToSend || isSending || !interview || interview.status === 'completed') return;

    try {
      setIsSending(true);
      setError(null);
      setInputMessage('');

      // Optimistic user turn
      const optimisticTurnNumber = turns.length + 1;
      const optimisticTurn: InterviewTurn = {
        id: `temp_${Date.now()}`,
        turn_number: optimisticTurnNumber,
        role: 'interviewer',
        content: textToSend,
        created_at: new Date().toISOString(),
      };
      setTurns((prev) => [...prev, optimisticTurn]);

      const res = await api.sendInterviewMessage(studyId, interviewId, {
        content: textToSend,
      });

      // Update transcript with real reply
      const personaTurn: InterviewTurn = {
        id: `turn_${Date.now()}`,
        turn_number: res.turn_number,
        role: 'persona',
        content: res.reply,
        topic: res.topic,
        latency_ms: res.latency_ms,
        served_by: res.served_by,
        created_at: new Date().toISOString(),
      };

      setTurns((prev) => [...prev.filter((t) => t.id !== optimisticTurn.id), optimisticTurn, personaTurn]);
      setSuggestedQuestions(res.suggested_questions || []);

      // Update interview status and turn counts
      setInterview((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          turn_count: res.total_turns,
          max_turns: res.max_turns,
          status: res.is_finished ? 'completed' : prev.status,
          topics_explored: res.topics_explored || prev.topics_explored,
        };
      });

      // Update topics status
      if (res.topics_explored) {
        setTopics((prev) =>
          prev.map((t) => ({
            ...t,
            status: res.topics_explored[t.id] === 'explored' ? 'explored' : 'not_explored',
          }))
        );
      }

      if (res.is_finished) {
        // Auto-complete synthesis
        handleCompleteInterview();
      }
    } catch (err: any) {
      console.error('Failed to send interview message:', err);
      setError(err.message || 'Failed to generate persona response.');
    } finally {
      setIsSending(false);
    }
  };

  const handleCompleteInterview = async () => {
    if (isCompleting || !interview) return;
    try {
      setIsCompleting(true);
      setError(null);
      const res = await api.completeStudyInterview(studyId, interviewId);

      setInterview((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          status: 'completed',
          summary: res.summary,
          key_findings: res.key_findings,
          structured_insights: res.structured_insights,
        };
      });
      setInsights(res.structured_insights || []);
      setActiveTab('synthesis');
    } catch (err: any) {
      console.error('Failed to complete interview:', err);
      setError(err.message || 'Failed to synthesize interview insights.');
    } finally {
      setIsCompleting(false);
    }
  };

  const handleCopyTurn = (turn: InterviewTurn) => {
    navigator.clipboard.writeText(`${turn.role.toUpperCase()}: ${turn.content}`);
    setCopiedTurnId(turn.id);
    setTimeout(() => setCopiedTurnId(null), 2000);
  };

  const handleScrollToTurn = (turnNum: number) => {
    setActiveTab('chat');
    setHighlightedTurnNumber(turnNum);
    setTimeout(() => {
      const el = turnRefs.current[turnNum];
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 100);
    setTimeout(() => setHighlightedTurnNumber(null), 4000);
  };

  const handleExportTranscript = () => {
    if (!interview) return;
    const header = `# Interview Transcript: ${interview.persona_name || 'Synthetic Persona'}\nObjective: ${interview.objective}\nDate: ${new Date(interview.created_at).toLocaleString()}\n\n---\n\n`;
    const body = turns
      .map((t) => `[Turn ${t.turn_number}] ${t.role.toUpperCase()}:\n${t.content}\n`)
      .join('\n');
    const blob = new Blob([header + body], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `interview_${interview.id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[600px] text-[#8D9999] space-y-4">
        <div className="w-10 h-10 border-3 border-teal-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-medium">Loading persona interview workspace...</p>
      </div>
    );
  }

  if (!interview) {
    return (
      <div className="p-8 text-center bg-[#141A1A] border border-[#202E2E] rounded-2xl max-w-xl mx-auto my-12 space-y-4">
        <AlertCircle className="w-12 h-12 text-red-400 mx-auto" />
        <h3 className="text-lg font-bold text-white">Interview Not Found</h3>
        <p className="text-xs text-[#8D9999]">This interview session could not be loaded or you do not have permission.</p>
        <button
          onClick={onBackToInterviews}
          className="px-4 py-2 bg-[#1C2626] hover:bg-[#253333] text-white rounded-xl text-xs font-semibold"
        >
          Back to Interviews
        </button>
      </div>
    );
  }

  const exploredCount = Object.values(interview.topics_explored || {}).filter(
    (v) => v === 'explored'
  ).length;
  const totalTopicsCount = Math.max(topics.length, 9);
  const currentTurn = interview.turn_count || turns.length;
  const maxTurns = interview.max_turns || 14;
  const isCompleted = interview.status === 'completed';

  return (
    <div className="flex flex-col h-[calc(100vh-80px)] overflow-hidden bg-[#0A0E0E] text-[#E0E6E6]">
      {/* 1. Header Toolbar */}
      <div className="px-6 py-4 bg-[#101616] border-b border-[#1D2727] flex items-center justify-between shrink-0 shadow-md">
        <div className="flex items-center gap-4">
          <button
            onClick={onBackToInterviews}
            className="p-2 rounded-xl bg-[#172020] hover:bg-[#202C2C] text-[#8D9999] hover:text-white transition-colors flex items-center gap-1.5 text-xs font-medium"
          >
            <ChevronLeft className="w-4 h-4" />
            <span>Interviews</span>
          </button>

          <div className="h-6 w-px bg-[#202C2C]" />

          {/* Persona Avatar and Details */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-teal-500/20 to-cyan-500/20 border border-teal-500/40 flex items-center justify-center text-teal-300 font-bold text-base shadow-inner">
              {persona?.avatar_url || interview.persona_avatar ? (
                <img
                  src={persona?.avatar_url || interview.persona_avatar}
                  alt={interview.persona_name || 'Persona'}
                  className="w-full h-full rounded-xl object-cover"
                />
              ) : (
                (interview.persona_name || 'P').charAt(0)
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold text-white">
                  {interview.persona_name || persona?.name || 'Synthetic Persona'}
                </h1>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                  <Bot className="w-3 h-3" />
                  Synthetic Persona
                </span>
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                    isCompleted
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : 'bg-teal-500/10 text-teal-400 border border-teal-500/20'
                  }`}
                >
                  {isCompleted ? 'Completed' : 'Live Interview'}
                </span>
              </div>
              <p className="text-xs text-[#8D9999] flex items-center gap-2 mt-0.5">
                <span>Objective: <strong className="text-[#B5C4C4] font-medium">{interview.objective}</strong></span>
                <span>•</span>
                <span>Tier: <strong className="text-teal-400 uppercase text-[10px]">{interview.length_tier}</strong></span>
              </p>
            </div>
          </div>
        </div>

        {/* Header Right Actions */}
        <div className="flex items-center gap-3">
          {/* Turn Progress Indicator */}
          <div className="hidden sm:flex items-center gap-2.5 px-3.5 py-1.5 rounded-xl bg-[#172020] border border-[#233131]">
            <Clock className="w-4 h-4 text-teal-400" />
            <div className="text-xs">
              <span className="text-[#8D9999]">Turn </span>
              <strong className="text-white">{currentTurn}</strong>
              <span className="text-[#8D9999]"> / {maxTurns}</span>
            </div>
            <div className="w-16 h-1.5 bg-[#233131] rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-teal-500 to-cyan-400 transition-all duration-300"
                style={{ width: `${Math.min(100, (currentTurn / maxTurns) * 100)}%` }}
              />
            </div>
          </div>

          {/* View Mode Switcher */}
          <div className="flex p-1 rounded-xl bg-[#172020] border border-[#233131]">
            <button
              onClick={() => setActiveTab('chat')}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'chat'
                  ? 'bg-teal-500 text-black shadow-sm'
                  : 'text-[#8D9999] hover:text-white'
              }`}
            >
              Conversation
            </button>
            <button
              onClick={() => setActiveTab('synthesis')}
              className={`px-3 py-1 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all ${
                activeTab === 'synthesis'
                  ? 'bg-teal-500 text-black shadow-sm'
                  : 'text-[#8D9999] hover:text-white'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Synthesis & Insights</span>
              {insights.length > 0 && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-black/40 text-teal-300 font-bold">
                  {insights.length}
                </span>
              )}
            </button>
          </div>

          {/* Complete / Export Action */}
          {!isCompleted ? (
            <button
              onClick={handleCompleteInterview}
              disabled={isCompleting || turns.length < 2}
              className="px-4 py-2 rounded-xl bg-teal-500/10 hover:bg-teal-500/20 border border-teal-500/30 text-teal-300 text-xs font-bold transition-all flex items-center gap-2 cursor-pointer disabled:opacity-40"
            >
              {isCompleting ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-teal-400 border-t-transparent rounded-full animate-spin" />
                  <span>Synthesizing...</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4 text-teal-400" />
                  <span>Finish & Synthesize</span>
                </>
              )}
            </button>
          ) : (
            <button
              onClick={handleExportTranscript}
              className="p-2 rounded-xl bg-[#172020] hover:bg-[#222E2E] border border-[#233131] text-[#8D9999] hover:text-white transition-colors"
              title="Export Markdown Transcript"
            >
              <Download className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* 2. Main Body: Split View (Sidebar + Content) */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Grounding Context Sidebar */}
        <div className="w-80 border-r border-[#1D2727] bg-[#0D1212] overflow-y-auto p-5 space-y-6 shrink-0 hidden lg:block">
          {/* Persona Grounding Card */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <User className="w-3.5 h-3.5 text-teal-400" />
                Persona Profile
              </h3>
              {persona?.id && onNavigateToPersona && (
                <button
                  onClick={() => onNavigateToPersona(persona.id)}
                  className="text-[11px] text-teal-400 hover:underline"
                >
                  View Details
                </button>
              )}
            </div>

            <div className="bg-[#131A1A] border border-[#202C2C] rounded-xl p-3.5 space-y-2.5 text-xs">
              {persona?.tagline && (
                <div className="text-[11px] font-semibold text-teal-400 border-b border-[#202C2C] pb-1.5">
                  {persona.tagline}
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-[#7D8C8C]">Occupation:</span>
                <span className="text-white font-medium">
                  {persona?.demographics?.occupation || interview.persona_occupation || 'Archetype'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#7D8C8C]">Age / Edu:</span>
                <span className="text-white font-medium">
                  {persona?.demographics?.age || 24} yrs • {persona?.demographics?.education || 'Graduate'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#7D8C8C]">Location:</span>
                <span className="text-white font-medium">
                  {persona?.demographics?.location || 'Dhaka, Bangladesh'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#7D8C8C]">Monthly Budget:</span>
                <span className="text-teal-400 font-bold">
                  ৳{persona?.commercial_profile?.monthly_budget_bdt || '300–600'} BDT
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#7D8C8C]">Price Sensitivity:</span>
                <span className="text-amber-400 font-medium">
                  {persona?.commercial_profile?.price_sensitivity || 'High'}
                </span>
              </div>

              {/* Big Five Indicators */}
              {persona?.personality && (
                <div className="pt-2 border-t border-[#202C2C] space-y-1.5">
                  <div className="text-[10px] font-bold text-[#7D8C8C] uppercase tracking-wider">Big Five Personality</div>
                  <div className="grid grid-cols-5 gap-1 text-center">
                    {[
                      { l: 'O', v: persona.personality.openness, c: 'text-sky-400' },
                      { l: 'C', v: persona.personality.conscientiousness, c: 'text-emerald-400' },
                      { l: 'E', v: persona.personality.extroversion, c: 'text-amber-400' },
                      { l: 'A', v: persona.personality.agreeableness, c: 'text-purple-400' },
                      { l: 'N', v: persona.personality.neuroticism, c: 'text-pink-400' },
                    ].map((t) => (
                      <div key={t.l} className="bg-[#0D1212] p-1 rounded border border-[#202C2C]">
                        <div className={`text-[11px] font-bold ${t.c}`}>{t.v}</div>
                        <div className="text-[9px] text-[#7D8C8C]">{t.l}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Communication Style */}
              {persona?.detailed_attributes?.communication_style && (
                <div className="pt-1 text-[11px] text-[#A2B3B3] leading-relaxed">
                  <span className="text-[#7D8C8C]">Style: </span>
                  {persona.detailed_attributes.communication_style}
                </div>
              )}
            </div>
          </div>

          {/* Topics Explored Progress */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-cyan-400" />
                Topics Explored ({exploredCount}/{totalTopicsCount})
              </h3>
            </div>

            <div className="space-y-1.5">
              {topics.map((t) => {
                const isExplored = t.status === 'explored';
                return (
                  <div
                    key={t.id}
                    className={`px-3 py-2 rounded-lg border text-xs flex items-center justify-between transition-colors ${
                      isExplored
                        ? 'bg-teal-500/10 border-teal-500/30 text-teal-300 font-medium'
                        : 'bg-[#131A1A] border-[#1C2626] text-[#6B7A7A]'
                    }`}
                  >
                    <span>{t.label}</span>
                    {isExplored ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-teal-400 shrink-0" />
                    ) : (
                      <div className="w-2 h-2 rounded-full bg-[#253333] shrink-0" />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Key Pain Points & Quotes */}
          {persona?.pain_points && persona.pain_points.length > 0 && (
            <div className="space-y-2.5">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                Grounded Pain Points
              </h3>
              <div className="space-y-1.5">
                {persona.pain_points.slice(0, 3).map((pp, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded-lg bg-[#131A1A] border border-[#202C2C] text-xs text-[#A2B3B3] leading-relaxed"
                  >
                    • {pp}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Empirical Citations */}
          {persona?.evidence_citations && persona.evidence_citations.length > 0 && (
            <div className="space-y-2.5">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <Bookmark className="w-3.5 h-3.5 text-cyan-400" />
                Study Evidence Grounding
              </h3>
              <div className="space-y-1.5">
                {persona.evidence_citations.slice(0, 2).map((ev: any, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded-lg bg-[#131A1A] border border-[#202C2C] text-[11px] text-[#869696] leading-relaxed"
                  >
                    <span className="text-cyan-400 font-semibold">
                      [{ev.source || ev.publisher || 'Evidence'}]:{' '}
                    </span>
                    {ev.claim || ev.text}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Main Panel */}
        <div className="flex-1 flex flex-col overflow-hidden bg-[#0A0E0E]">
          {activeTab === 'chat' ? (
            /* CONVERSATION TRANSCRIPT VIEW */
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* Transcript Scroll Area */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* Notice Banner */}
                <div className="max-w-3xl mx-auto bg-[#121919] border border-[#202D2D] rounded-xl p-4 flex items-start gap-3 text-xs text-[#8D9999]">
                  <Sparkles className="w-4 h-4 text-teal-400 shrink-0 mt-0.5" />
                  <div>
                    <strong className="text-white">Live Synthetic Interview Session: </strong>
                    Ask questions conversationally. The persona behaves realistically according to
                    their budget, habits, and objections in Bangladesh.
                  </div>
                </div>

                {error && (
                  <div className="max-w-3xl mx-auto bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-center gap-3 text-red-400 text-xs">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span>{error}</span>
                  </div>
                )}

                {/* Turns List */}
                <div className="max-w-3xl mx-auto space-y-5">
                  {turns.map((turn) => {
                    const isInterviewer = turn.role === 'interviewer' || turn.role === 'researcher' || turn.role === 'user';
                    const isHighlighted = highlightedTurnNumber === turn.turn_number;

                    return (
                      <div
                        key={turn.id || turn.turn_number}
                        ref={(el) => (turnRefs.current[turn.turn_number] = el)}
                        className={`flex gap-3 group transition-all duration-300 ${
                          isInterviewer ? 'justify-end' : 'justify-start'
                        } ${isHighlighted ? 'ring-2 ring-teal-400 rounded-2xl p-2 bg-teal-500/5' : ''}`}
                      >
                        {/* Persona Avatar */}
                        {!isInterviewer && (
                          <div className="w-8 h-8 rounded-xl bg-teal-500/10 border border-teal-500/30 flex items-center justify-center text-teal-400 font-bold text-xs shrink-0 mt-1">
                            {persona?.avatar_url || interview.persona_avatar ? (
                              <img
                                src={persona?.avatar_url || interview.persona_avatar}
                                alt={interview.persona_name || 'Persona'}
                                className="w-full h-full rounded-xl object-cover"
                              />
                            ) : (
                              (interview.persona_name || 'P').charAt(0)
                            )}
                          </div>
                        )}

                        {/* Bubble Content */}
                        <div
                          className={`max-w-[80%] rounded-2xl p-4 text-xs leading-relaxed space-y-2 relative shadow-md ${
                            isInterviewer
                              ? 'bg-[#182626] border border-[#2A3E3E] text-[#F0F5F5] rounded-tr-sm'
                              : 'bg-[#121818] border border-[#1E2929] text-[#E0EBEB] rounded-tl-sm'
                          }`}
                        >
                          {/* Bubble Header */}
                          <div className="flex items-center justify-between gap-4 text-[10px] text-[#718282] border-b border-white/5 pb-1.5">
                            <div className="flex items-center gap-1.5 font-semibold">
                              {isInterviewer ? (
                                <span className="text-teal-400">Researcher</span>
                              ) : (
                                <>
                                  <span className="text-cyan-400">
                                    {interview.persona_name || 'Synthetic Persona'}
                                  </span>
                                  <span className="text-[9px] px-1.5 py-0.2 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                                    Simulated
                                  </span>
                                </>
                              )}
                            </div>
                            <div className="flex items-center gap-2">
                              {turn.topic && (
                                <span className="px-1.5 py-0.2 rounded bg-[#1D2828] text-[#869999] capitalize">
                                  {turn.topic.replace('_', ' ')}
                                </span>
                              )}
                              <span>Turn #{turn.turn_number}</span>
                              <button
                                onClick={() => handleCopyTurn(turn)}
                                className="opacity-0 group-hover:opacity-100 hover:text-white transition-opacity"
                                title="Copy response"
                              >
                                {copiedTurnId === turn.id ? (
                                  <Check className="w-3 h-3 text-teal-400" />
                                ) : (
                                  <Copy className="w-3 h-3" />
                                )}
                              </button>
                            </div>
                          </div>

                          {/* Message Body */}
                          <div className="whitespace-pre-wrap text-sm text-[#D7E3E3]">
                            {turn.content}
                          </div>

                          {/* Persona Turn Metadata */}
                          {!isInterviewer && turn.served_by && (
                            <div className="text-[9px] text-[#556666] pt-1 flex items-center justify-between">
                              <span>Model: {turn.served_by}</span>
                              {turn.latency_ms && (
                                <span>{Math.round(turn.latency_ms)}ms</span>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Interviewer Avatar */}
                        {isInterviewer && (
                          <div className="w-8 h-8 rounded-xl bg-[#233333] border border-[#354B4B] flex items-center justify-center text-teal-400 font-bold text-xs shrink-0 mt-1">
                            <User className="w-4 h-4" />
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {/* Sending Spinner */}
                  {isSending && (
                    <div className="flex gap-3 justify-start items-center">
                      <div className="w-8 h-8 rounded-xl bg-teal-500/10 border border-teal-500/30 flex items-center justify-center text-teal-400 font-bold text-xs shrink-0">
                        <Bot className="w-4 h-4" />
                      </div>
                      <div className="bg-[#121818] border border-[#1E2929] rounded-2xl rounded-tl-sm p-4 flex items-center gap-3">
                        <div className="flex gap-1">
                          <div className="w-2 h-2 bg-teal-400 rounded-full animate-bounce" />
                          <div className="w-2 h-2 bg-teal-400 rounded-full animate-bounce [animation-delay:0.2s]" />
                          <div className="w-2 h-2 bg-teal-400 rounded-full animate-bounce [animation-delay:0.4s]" />
                        </div>
                        <span className="text-xs text-[#718282]">Persona is considering and typing...</span>
                      </div>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </div>
              </div>

              {/* Suggested Questions Pill Bar */}
              {!isCompleted && suggestedQuestions.length > 0 && (
                <div className="px-6 py-2 bg-[#0E1414] border-t border-[#1B2525] shrink-0">
                  <div className="max-w-3xl mx-auto flex items-center gap-2 overflow-x-auto no-scrollbar py-1">
                    <span className="text-[11px] font-bold text-teal-400 flex items-center gap-1 shrink-0">
                      <Sparkles className="w-3 h-3" />
                      Suggested Next:
                    </span>
                    {suggestedQuestions.map((q, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleSendMessage(q)}
                        disabled={isSending}
                        className="px-3 py-1.5 rounded-full bg-[#162020] hover:bg-[#202E2E] border border-[#243333] hover:border-teal-500/50 text-[11px] text-[#A6B8B8] hover:text-white whitespace-nowrap transition-all shrink-0 cursor-pointer disabled:opacity-40"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Sticky Composer */}
              <div className="p-4 bg-[#101616] border-t border-[#1D2727] shrink-0">
                <div className="max-w-3xl mx-auto">
                  {!isCompleted ? (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        handleSendMessage();
                      }}
                      className="flex items-end gap-3"
                    >
                      <div className="flex-1 bg-[#151D1D] border border-[#243333] focus-within:border-teal-500 rounded-2xl p-3 shadow-inner transition-colors">
                        <textarea
                          value={inputMessage}
                          onChange={(e) => setInputMessage(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                              e.preventDefault();
                              handleSendMessage();
                            }
                          }}
                          placeholder={`Ask ${interview.persona_name || 'persona'} a question (e.g. How much do you spend monthly on this?)...`}
                          rows={2}
                          disabled={isSending}
                          className="w-full bg-transparent text-white text-xs placeholder-[#5A6C6C] focus:outline-none resize-none leading-relaxed"
                        />
                        <div className="flex items-center justify-between pt-1 border-t border-white/5 text-[10px] text-[#556666]">
                          <span>Press <strong className="text-[#889999]">Enter</strong> to send, <strong className="text-[#889999]">Shift+Enter</strong> for newline</span>
                          <span>{inputMessage.length} chars</span>
                        </div>
                      </div>

                      <button
                        type="submit"
                        disabled={!inputMessage.trim() || isSending}
                        className="h-12 px-5 rounded-2xl bg-teal-500 hover:bg-teal-400 disabled:opacity-40 text-black font-bold text-xs flex items-center gap-2 shadow-lg shadow-teal-500/20 transition-all cursor-pointer shrink-0"
                      >
                        <Send className="w-4 h-4" />
                        <span className="hidden sm:inline">Send</span>
                      </button>
                    </form>
                  ) : (
                    <div className="bg-[#151D1D] border border-teal-500/20 rounded-2xl p-4 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <CheckCircle2 className="w-5 h-5 text-teal-400" />
                        <div>
                          <h4 className="text-xs font-bold text-white">Interview Completed</h4>
                          <p className="text-[11px] text-[#8D9999]">
                            {turns.length} turns recorded. View the structured insights in the Synthesis tab.
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={() => setActiveTab('synthesis')}
                        className="px-4 py-2 bg-teal-500 hover:bg-teal-400 text-black rounded-xl text-xs font-bold transition-colors cursor-pointer"
                      >
                        View Synthesis
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            /* STRUCTURED SYNTHESIS & INSIGHTS TAB */
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              <div className="max-w-4xl mx-auto space-y-6">
                {/* Synthesis Header Banner */}
                <div className="bg-gradient-to-r from-teal-950/40 via-[#131A1A] to-[#131A1A] border border-teal-500/30 rounded-2xl p-6 relative overflow-hidden shadow-xl">
                  <div className="flex items-start justify-between">
                    <div className="space-y-2">
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-teal-500/10 text-teal-300 border border-teal-500/30">
                        <Sparkles className="w-3.5 h-3.5" />
                        Structured Interview Synthesis
                      </div>
                      <h2 className="text-xl font-bold text-white tracking-tight">
                        Research Findings: {interview.persona_name || 'Synthetic Persona'}
                      </h2>
                      <p className="text-xs text-[#8D9999]">
                        Derived from {turns.length} interview turns across {exploredCount} explored topic dimensions.
                      </p>
                    </div>
                    <button
                      onClick={handleExportTranscript}
                      className="px-3.5 py-2 rounded-xl bg-[#1A2424] hover:bg-[#223030] border border-[#2B3C3C] text-xs font-semibold text-white flex items-center gap-2 transition-colors cursor-pointer"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Export Analysis</span>
                    </button>
                  </div>
                </div>

                {/* Grounding / Synthetic Insight Disclaimer */}
                <div className="bg-[#121818] border border-cyan-500/20 rounded-xl p-4 flex items-start gap-3 text-xs text-[#95A8A8]">
                  <Info className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-white">Synthetic Interview Insight: </span>
                    These findings are synthesized from agent simulation. Cross-reference with
                    Real Customer Evidence before finalizing capital allocations.
                  </div>
                </div>

                {/* Executive Summary */}
                {interview.summary && (
                  <div className="bg-[#111717] border border-[#1E2A2A] rounded-2xl p-6 space-y-3 shadow-md">
                    <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                      <FileText className="w-4 h-4 text-teal-400" />
                      Executive Summary
                    </h3>
                    <p className="text-xs text-[#C5D4D4] leading-relaxed">
                      {interview.summary}
                    </p>
                  </div>
                )}

                {/* Key Findings List */}
                {interview.key_findings && interview.key_findings.length > 0 && (
                  <div className="bg-[#111717] border border-[#1E2A2A] rounded-2xl p-6 space-y-3 shadow-md">
                    <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-cyan-400" />
                      Key Findings & Behavioral Takeaways
                    </h3>
                    <div className="grid grid-cols-1 gap-2.5">
                      {interview.key_findings.map((finding, idx) => (
                        <div
                          key={idx}
                          className="p-3 rounded-xl bg-[#151D1D] border border-[#202E2E] text-xs text-[#B2C4C4] flex items-start gap-3 leading-relaxed"
                        >
                          <span className="w-5 h-5 rounded-full bg-teal-500/10 text-teal-400 font-bold flex items-center justify-center text-[10px] shrink-0 mt-0.5">
                            {idx + 1}
                          </span>
                          <span>{finding}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Structured Insights Grid with Turn Provenance */}
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                      <Award className="w-4 h-4 text-teal-400" />
                      Structured Insights & Evidence Citations ({insights.length})
                    </h3>
                    <span className="text-[11px] text-[#718282]">
                      Click supporting turn badges to inspect dialogue
                    </span>
                  </div>

                  {insights.length === 0 ? (
                    <div className="p-8 text-center bg-[#111717] border border-[#1E2A2A] rounded-2xl space-y-3">
                      <Sparkles className="w-8 h-8 text-[#556666] mx-auto" />
                      <p className="text-xs text-[#8D9999]">
                        No structured insights have been extracted yet. Complete the interview to generate insights.
                      </p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {insights.map((insight) => {
                        const typeBadgeColor =
                          insight.type === 'pricing'
                            ? 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                            : insight.type === 'pain_point'
                            ? 'bg-red-500/10 text-red-300 border-red-500/30'
                            : insight.type === 'objection'
                            ? 'bg-purple-500/10 text-purple-300 border-purple-500/30'
                            : 'bg-teal-500/10 text-teal-300 border-teal-500/30';

                        return (
                          <div
                            key={insight.id}
                            className="bg-[#111717] border border-[#1F2C2C] hover:border-[#2D3E3E] rounded-2xl p-5 space-y-3 transition-all flex flex-col justify-between shadow-md"
                          >
                            <div className="space-y-2">
                              <div className="flex items-center justify-between">
                                <span
                                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold border uppercase tracking-wider ${typeBadgeColor}`}
                                >
                                  {insight.type.replace('_', ' ')}
                                </span>
                                <span className="text-[10px] text-[#718282] font-semibold">
                                  {Math.round((insight.confidence || 0.85) * 100)}% Confidence
                                </span>
                              </div>

                              <h4 className="text-sm font-bold text-white leading-snug">
                                {insight.title}
                              </h4>

                              <p className="text-xs text-[#9BB0B0] leading-relaxed">
                                {insight.description}
                              </p>
                            </div>

                            {/* Supporting Turn Badges */}
                            {insight.supporting_turn_numbers && insight.supporting_turn_numbers.length > 0 && (
                              <div className="pt-3 border-t border-white/5 flex items-center justify-between text-[11px]">
                                <span className="text-[#657777]">Supporting Dialogue:</span>
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  {insight.supporting_turn_numbers.map((tNum) => (
                                    <button
                                      key={tNum}
                                      onClick={() => handleScrollToTurn(tNum)}
                                      className="px-2 py-0.5 rounded-md bg-[#182323] hover:bg-teal-500/20 border border-[#253636] hover:border-teal-500 text-teal-300 text-[10px] font-bold transition-all cursor-pointer"
                                      title={`Jump to Turn ${tNum}`}
                                    >
                                      Turn #{tNum}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
