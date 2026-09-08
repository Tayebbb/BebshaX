import React, { useRef, useState } from 'react';
import {
  X,
  Sparkles,
  MessageSquare,
  Bot,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { SyntheticPersona, InterviewLengthTier } from '../../../types';
import { api } from '../../../services/api';
import { isEvidenceBacked } from '../../../utils/personaEvidence';
import { useDialogA11y } from '../../../utils/useDialogA11y';

interface StartInterviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  persona: SyntheticPersona;
  studyId: string;
  onInterviewStarted: (interviewId: string) => void;
}

const OBJECTIVE_PRESETS = [
  {
    id: 'problem_discovery',
    title: 'Problem & Pain Point Discovery',
    description: 'Explore daily frustrations, unaddressed friction, and existing workarounds.',
    recommendedTier: 'standard' as InterviewLengthTier,
  },
  {
    id: 'pricing_wtp',
    title: 'Pricing & Willingness to Pay',
    description: 'Test pricing thresholds, budget constraints, and payment preferences in BDT.',
    recommendedTier: 'short' as InterviewLengthTier,
  },
  {
    id: 'feature_reaction',
    title: 'Feature & Solution Reaction',
    description: 'Pitch your value proposition to test genuine utility and anti-sycophantic skepticism.',
    recommendedTier: 'standard' as InterviewLengthTier,
  },
  {
    id: 'objection_deep_dive',
    title: 'Objections & Hesitations',
    description: 'Uncover trust barriers, inertia, and reasons this persona might decline or churn.',
    recommendedTier: 'deep' as InterviewLengthTier,
  },
  {
    id: 'custom',
    title: 'Custom Research Objective',
    description: 'Define your own specific hypothesis or questioning direction.',
    recommendedTier: 'standard' as InterviewLengthTier,
  },
];

export const StartInterviewModal: React.FC<StartInterviewModalProps> = ({
  isOpen,
  onClose,
  persona,
  studyId,
  onInterviewStarted,
}) => {
  const [selectedObjective, setSelectedObjective] = useState<string>('problem_discovery');
  const [customObjectiveText, setCustomObjectiveText] = useState<string>('');
  const [lengthTier, setLengthTier] = useState<InterviewLengthTier>('standard');
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  useDialogA11y(dialogRef, isOpen, onClose);

  // The grounding claim is only made when the persona actually carries one.
  const evidenceBacked = isEvidenceBacked(persona);

  if (!isOpen) return null;

  const handleStart = async () => {
    try {
      setIsStarting(true);
      setError(null);

      const objectiveTitle =
        OBJECTIVE_PRESETS.find((o) => o.id === selectedObjective)?.title || 'General Research';

      const payload = {
        objective: objectiveTitle,
        custom_objective:
          selectedObjective === 'custom' ? customObjectiveText.trim() : undefined,
        length_tier: lengthTier,
        generation_run_id: persona.generation_run_id,
      };

      const interview = await api.startPersonaInterview(studyId, persona.id, payload);
      onInterviewStarted(interview.id);
      onClose();
    } catch (err: any) {
      console.error('Failed to start interview:', err);
      setError(err.message || 'Failed to start interview. Please try again.');
    } finally {
      setIsStarting(false);
    }
  };

  // Never invent a detail the persona does not carry — an absent field is
  // simply not shown.
  const commProfile = persona.commercial_profile || {};
  const monthlyBudget = commProfile.monthly_budget_bdt || commProfile.budget_bdt;
  const summaryParts = [
    persona.demographics?.occupation || persona.archetype,
    persona.demographics?.location,
    monthlyBudget ? `Budget: ৳${monthlyBudget}/mo` : undefined,
  ].filter(Boolean) as string[];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[var(--scrim)] animate-fade-in bx-backdrop">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="start-interview-title"
        className="bg-[var(--bg-card)] border border-[var(--border-medium)] rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh] bx-modal"
      >
        {/* Modal Header */}
        <div className="p-6 border-b border-[var(--border-medium)] flex items-center justify-between bg-[var(--bg-secondary)]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-teal-500/10 border border-teal-500/30 flex items-center justify-center text-teal-400 font-bold text-lg">
              {persona.avatar_url ? (
                <img
                  src={persona.avatar_url}
                  alt={persona.name}
                  loading="lazy"
                  decoding="async"
                  className="w-full h-full rounded-xl object-cover"
                />
              ) : (
                persona.name.charAt(0)
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="start-interview-title" className="text-xl font-bold text-white tracking-tight">
                  Interview {persona.name}
                </h2>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                  <Bot className="w-3 h-3" />
                  Synthetic Persona
                </span>
              </div>
              {summaryParts.length > 0 && (
                <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                  {summaryParts.join(' • ')}
                </p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close interview setup dialog"
            className="text-[var(--text-secondary)] hover:text-[var(--text-main)] p-2 rounded-lg hover:bg-[var(--bg-card-hover)] transition-colors"
          >
            <X className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 text-sm text-[var(--text-secondary)]">
          {/* Grounding Context Alert */}
          <div className="bg-[var(--bg-card-hover)] border border-teal-500/20 rounded-xl p-4 flex items-start gap-3">
            <Sparkles className="w-5 h-5 text-teal-400 shrink-0 mt-0.5" />
            <div className="text-xs leading-relaxed text-[var(--text-label)]">
              <span className="font-semibold text-[var(--text-main)]">Adaptive Anti-Sycophantic Agent: </span>
              {evidenceBacked ? (
                <>
                  This persona&apos;s profile is backed by retrieved evidence, and it will realistically
                  push back on expensive pricing or irrelevant solutions. Answers represent synthetic
                  simulation insights.
                </>
              ) : (
                <>
                  No supporting evidence was retrieved for this persona — its profile is inferred from
                  your study description. It will still push back on expensive pricing or irrelevant
                  solutions, but treat every answer as a synthetic simulation, not a finding.
                </>
              )}
            </div>
          </div>

          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-center gap-3 text-red-400 text-xs">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Objective Selection */}
          <div className="space-y-3">
            <label className="block text-xs font-bold text-white uppercase tracking-wider">
              1. Select Interview Objective
            </label>
            <div className="grid grid-cols-1 gap-2.5">
              {OBJECTIVE_PRESETS.map((obj) => {
                const isSelected = selectedObjective === obj.id;
                return (
                  <div
                    key={obj.id}
                    onClick={() => {
                      setSelectedObjective(obj.id);
                      setLengthTier(obj.recommendedTier);
                    }}
                    className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-teal-500/10 border-teal-500 text-white'
                        : 'bg-[var(--bg-card-hover)] border-[var(--border-medium)] hover:border-[var(--border-hover)] text-[var(--text-label)]'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-sm">{obj.title}</span>
                      {isSelected && <CheckCircle2 className="w-4 h-4 text-teal-400" />}
                    </div>
                    <p className="text-xs text-[var(--text-secondary)] mt-1">{obj.description}</p>
                  </div>
                );
              })}
            </div>

            {selectedObjective === 'custom' && (
              <div className="mt-3">
                <textarea
                  value={customObjectiveText}
                  onChange={(e) => setCustomObjectiveText(e.target.value)}
                  placeholder="e.g. Ask about how they manage weekly budgeting and whether a ৳150 weekly fee works..."
                  rows={3}
                  className="w-full bg-[var(--bg-card-hover)] border border-[var(--border-medium)] rounded-xl p-3 text-white text-xs placeholder-[var(--text-muted)] focus:outline-none focus:border-teal-500"
                />
              </div>
            )}
          </div>

          {/* Length & Turn Limit Selection */}
          <div className="space-y-3">
            <label className="block text-xs font-bold text-white uppercase tracking-wider">
              2. Interview Depth & Length
            </label>
            <div className="grid grid-cols-3 gap-3">
              {[
                {
                  id: 'short' as InterviewLengthTier,
                  label: 'Short Pulse',
                  turns: '5–7 Turns',
                  desc: 'Quick pricing or feature validation',
                },
                {
                  id: 'standard' as InterviewLengthTier,
                  label: 'Standard Discovery',
                  turns: '10–15 Turns',
                  desc: 'Balanced deep dive across 3–4 topics',
                },
                {
                  id: 'deep' as InterviewLengthTier,
                  label: 'Deep Ethnography',
                  turns: '20+ Turns',
                  desc: 'Exhaustive exploratory investigation',
                },
              ].map((tier) => {
                const isSelected = lengthTier === tier.id;
                return (
                  <div
                    key={tier.id}
                    onClick={() => setLengthTier(tier.id)}
                    className={`p-3 rounded-xl border text-center cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-teal-500/10 border-teal-500 text-white'
                        : 'bg-[var(--bg-card-hover)] border-[var(--border-medium)] hover:border-[var(--border-hover)] text-[var(--text-label)]'
                    }`}
                  >
                    <div className="font-semibold text-xs text-white">{tier.label}</div>
                    <div className="text-teal-400 font-bold text-xs mt-0.5">{tier.turns}</div>
                    <div className="text-[0.72rem] text-[var(--text-secondary)] mt-1">{tier.desc}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-5 border-t border-[var(--border-medium)] bg-[var(--bg-secondary)] flex items-center justify-between">
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-xl border border-[var(--border-medium)] text-[var(--text-secondary)] hover:text-[var(--text-main)] hover:bg-[var(--bg-card-hover)] text-xs font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleStart}
            disabled={
              isStarting || (selectedObjective === 'custom' && !customObjectiveText.trim())
            }
            className="px-6 py-2.5 rounded-xl bg-teal-500 hover:bg-teal-400 disabled:opacity-50 text-black font-bold text-xs flex items-center gap-2 shadow-lg shadow-teal-500/20 transition-all cursor-pointer"
          >
            {isStarting ? (
              <>
                <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
                <span>Initializing Interview...</span>
              </>
            ) : (
              <>
                <MessageSquare className="w-4 h-4" />
                <span>Start Adaptive Interview</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
