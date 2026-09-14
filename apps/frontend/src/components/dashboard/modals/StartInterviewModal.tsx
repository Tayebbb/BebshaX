import React, { useEffect, useRef, useState } from 'react';
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
  /** The control that opened the dialog, captured at click time: the opener
   * loads the persona first, and that reload can re-render the trigger. */
  returnFocusTo?: React.RefObject<HTMLElement | null>;
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
  returnFocusTo,
}) => {
  const [selectedObjective, setSelectedObjective] = useState<string>('problem_discovery');
  const [customObjectiveText, setCustomObjectiveText] = useState<string>('');
  const [lengthTier, setLengthTier] = useState<InterviewLengthTier>('standard');
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const modalEpochRef = useRef<symbol | null>(null);
  const startingRef = useRef(false);

  useEffect(() => {
    modalEpochRef.current = isOpen ? Symbol() : null;
    startingRef.current = false;
    setIsStarting(false);
    setError(null);
    return () => {
      modalEpochRef.current = null;
      startingRef.current = false;
    };
  }, [isOpen, studyId, persona.id, persona.generation_run_id]);

  const handleClose = () => {
    modalEpochRef.current = null;
    startingRef.current = false;
    setIsStarting(false);
    onClose();
  };
  useDialogA11y(dialogRef, isOpen, handleClose, { returnFocusTo });

  // The grounding claim is only made when the persona actually carries one.
  const evidenceBacked = isEvidenceBacked(persona);

  if (!isOpen) return null;

  const handleStart = async () => {
    const modalEpoch = modalEpochRef.current;
    if (!modalEpoch || startingRef.current || (selectedObjective === 'custom' && !customObjectiveText.trim())) return;
    startingRef.current = true;
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
      if (modalEpochRef.current !== modalEpoch) return;
      onInterviewStarted(interview.id);
      handleClose();
    } catch (err: unknown) {
      if (modalEpochRef.current !== modalEpoch) return;
      setError(err instanceof Error ? err.message : 'Failed to start interview. Please try again.');
    } finally {
      if (modalEpochRef.current === modalEpoch) {
        startingRef.current = false;
        setIsStarting(false);
      }
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
        className="bg-[var(--bg-card)] border border-[var(--border-control)] rounded-xl w-full min-w-0 max-w-2xl overflow-hidden flex flex-col max-h-[90vh] bx-modal"
        style={{ fontFamily: 'var(--font-sans)', color: 'var(--text-primary)' }}
      >
        {/* Modal Header */}
        <div className="p-6 border-b border-[var(--border-medium)] flex items-start justify-between gap-3 bg-[var(--bg-secondary)]">
          <div className="flex min-w-0 items-start gap-3">
            <div className="w-10 h-10 shrink-0 rounded-lg bg-[var(--accent-subtle)] border border-[var(--accent-glow)] flex items-center justify-center text-[var(--accent-teal)] font-semibold text-lg">
              {persona.avatar_url ? (
                <img
                  src={persona.avatar_url}
                  alt={persona.name}
                  loading="lazy"
                  decoding="async"
                  className="w-full h-full rounded-lg object-cover"
                />
              ) : (
                persona.name.charAt(0)
              )}
            </div>
            <div className="min-w-0 flex-1 break-words">
              <div className="flex flex-wrap items-center gap-2">
                <h2 id="start-interview-title" className="text-lg font-semibold text-[var(--text-main)] tracking-normal">
                  Interview {persona.name}
                </h2>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
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
            onClick={handleClose}
            aria-label="Close interview setup dialog"
            className="min-h-11 min-w-11 shrink-0 flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-main)] p-2 rounded-md hover:bg-[var(--bg-card-hover)] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
          >
            <X className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 min-w-0 overflow-y-auto space-y-6 flex-1 text-sm text-[var(--text-secondary)]">
          {/* Grounding Context Alert */}
          <div className="bg-[var(--bg-card-hover)] border border-teal-500/20 rounded-lg p-4 flex items-start gap-3">
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
            <div role="alert" className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 flex items-center gap-3 text-[var(--status-error-text)] text-xs">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Objective Selection */}
          <fieldset disabled={isStarting} className="min-w-0 space-y-3 border-0 p-0">
            <legend className="block text-sm font-semibold text-[var(--text-main)]">
              1. Select Interview Objective
            </legend>
            <div className="grid grid-cols-1 gap-2.5">
              {OBJECTIVE_PRESETS.map((obj) => {
                const isSelected = selectedObjective === obj.id;
                return (
                  <label
                    key={obj.id}
                    className={`flex min-h-11 min-w-0 items-start gap-3 p-3.5 rounded-lg border cursor-pointer transition-colors focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--focus-ring)] ${
                      isSelected
                        ? 'bg-[var(--accent-subtle)] border-[var(--accent-teal)] text-[var(--text-main)]'
                        : 'bg-[var(--bg-card-hover)] border-[var(--border-control)] hover:border-[var(--border-hover)] text-[var(--text-label)]'
                    }`}
                  >
                    <input
                      type="radio"
                      name="interview-objective"
                      value={obj.id}
                      checked={isSelected}
                      aria-labelledby={`interview-objective-${obj.id}`}
                      aria-describedby={`interview-objective-${obj.id}-description`}
                      onChange={() => {
                        setSelectedObjective(obj.id);
                        setLengthTier(obj.recommendedTier);
                      }}
                      className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--accent-teal)]"
                    />
                    <span className="block min-w-0 flex-1 break-words">
                      <span className="flex items-start justify-between gap-2">
                        <span id={`interview-objective-${obj.id}`} className="font-semibold text-sm">{obj.title}</span>
                        {isSelected && <CheckCircle2 aria-hidden="true" className="w-4 h-4 shrink-0 text-[var(--accent-teal)]" />}
                      </span>
                      <span id={`interview-objective-${obj.id}-description`} className="block text-xs text-[var(--text-secondary)] mt-1">{obj.description}</span>
                    </span>
                  </label>
                );
              })}
            </div>

            {selectedObjective === 'custom' && (
              <div className="mt-3">
                <textarea
                  aria-label="Custom research objective"
                  value={customObjectiveText}
                  onChange={(e) => setCustomObjectiveText(e.target.value)}
                  placeholder="e.g. Ask about how they manage weekly budgeting and whether a ৳150 weekly fee works..."
                  rows={3}
                  className="w-full min-h-11 min-w-0 bg-[var(--bg-card-hover)] border border-[var(--border-control)] rounded-md p-3 text-[var(--text-main)] text-base placeholder-[var(--text-muted)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
                />
              </div>
            )}
          </fieldset>

          {/* Length & Turn Limit Selection */}
          <fieldset disabled={isStarting} className="min-w-0 space-y-3 border-0 p-0">
            <legend className="block text-sm font-semibold text-[var(--text-main)]">
              2. Interview Depth & Length
            </legend>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
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
                  <label
                    key={tier.id}
                    className={`flex min-h-11 min-w-0 items-start gap-2 p-3 rounded-lg border cursor-pointer transition-colors focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--focus-ring)] ${
                      isSelected
                        ? 'bg-[var(--accent-subtle)] border-[var(--accent-teal)] text-[var(--text-main)]'
                        : 'bg-[var(--bg-card-hover)] border-[var(--border-control)] hover:border-[var(--border-hover)] text-[var(--text-label)]'
                    }`}
                  >
                    <input
                      type="radio"
                      name="interview-depth"
                      value={tier.id}
                      checked={isSelected}
                      aria-labelledby={`interview-depth-${tier.id}`}
                      aria-describedby={`interview-depth-${tier.id}-description`}
                      onChange={() => setLengthTier(tier.id)}
                      className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--accent-teal)]"
                    />
                    <span className="block min-w-0 flex-1 break-words">
                      <span id={`interview-depth-${tier.id}`} className="block font-semibold text-xs text-[var(--text-main)]">{tier.label}</span>
                      <span id={`interview-depth-${tier.id}-description`} className="block">
                        <span className="block text-[var(--accent-teal)] font-semibold text-xs mt-0.5">{tier.turns}</span>
                        <span className="block text-[0.72rem] text-[var(--text-secondary)] mt-1">{tier.desc}</span>
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        </div>

        {/* Modal Footer */}
        <div className="p-5 min-w-0 border-t border-[var(--border-medium)] bg-[var(--bg-secondary)] flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            onClick={handleClose}
            className="min-h-11 px-4 py-2.5 rounded-md border border-[var(--border-control)] text-[var(--text-secondary)] hover:text-[var(--text-main)] hover:bg-[var(--bg-card-hover)] text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleStart}
            aria-busy={isStarting}
            disabled={
              isStarting || (selectedObjective === 'custom' && !customObjectiveText.trim())
            }
            className="min-h-11 min-w-0 max-w-full px-6 py-2.5 rounded-md bg-[var(--accent-teal)] disabled:opacity-50 disabled:cursor-not-allowed text-[var(--text-on-accent)] font-semibold text-sm flex items-center justify-center gap-2 transition-colors cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
          >
            {isStarting ? (
              <>
                <div className="w-4 h-4 shrink-0 border-2 border-[var(--text-on-accent)] border-t-transparent rounded-full animate-spin" />
                <span>Initializing Interview...</span>
              </>
            ) : (
              <>
                <MessageSquare className="w-4 h-4 shrink-0" />
                <span>Start Adaptive Interview</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
