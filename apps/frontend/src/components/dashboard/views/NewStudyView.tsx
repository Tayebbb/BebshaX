import React, { useState, useRef } from 'react';
import {
  Users,
  Compass,
  MessageSquare,
  BadgePercent,
  ArrowUp,
  ArrowUpRight,
  Loader2,
  AlertCircle,
  Check,
} from 'lucide-react';
import { StudyType } from '../../../types';
import './newstudy.css';

interface NewStudyViewProps {
  onStartStudy: (type: StudyType, initialPrompt?: string) => Promise<void> | void;
  /** Provided only when a finished demo study exists to open. */
  onOpenExampleStudy?: () => void;
}

const EXAMPLE_PROMPTS = [
  'An AI study planner for students with a 250 BDT/month tier',
  'Subscription meal-prep delivery for busy professionals in Dhaka',
  'A price-drop alert service for online gadget shoppers',
];

export const NewStudyView: React.FC<NewStudyViewProps> = ({ onStartStudy, onOpenExampleStudy }) => {
  const [prompt, setPrompt] = useState('');
  const [selectedType, setSelectedType] = useState<StudyType>('interviews');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const cleanPrompt = prompt.trim();

    if (!cleanPrompt) {
      setValidationError('Describe your product idea before starting the study.');
      return;
    }

    setValidationError(null);
    setIsSubmitting(true);
    try {
      await onStartStudy(selectedType, cleanPrompt);
    } catch {
      setIsSubmitting(false);
    }
  };

  const handleCardClick = async (type: StudyType) => {
    setSelectedType(type);
    setValidationError(null);
    const cleanPrompt = prompt.trim();
    if (cleanPrompt) {
      setIsSubmitting(true);
      try {
        await onStartStudy(type, cleanPrompt);
      } catch {
        setIsSubmitting(false);
      }
    }
  };

  const studyTypes: {
    type: StudyType;
    icon: React.ReactNode;
    iconBg: string;
    iconColor: string;
    title: string;
    description: string;
  }[] = [
    {
      type: 'interviews',
      icon: <Users size={19} />,
      iconBg: 'var(--accent-subtle)',
      iconColor: 'var(--accent-teal)',
      title: 'User Interviews',
      description: 'Simulate in-depth discovery interviews with synthetic personas to reveal daily workflows and unarticulated pain points.',
    },
    {
      type: 'landing_page_test',
      icon: <Compass size={19} />,
      iconBg: 'rgba(34, 211, 238, 0.15)',
      iconColor: 'var(--accent-cyan)',
      title: 'Concept & Demand',
      description: 'Validate product-market fit, value proposition desirability, and core feature hypotheses before writing code.',
    },
    {
      type: 'message_testing',
      icon: <MessageSquare size={19} />,
      iconBg: 'var(--accent-subtle)',
      iconColor: 'var(--accent-teal-bright)',
      title: 'Message Testing',
      description: 'Test pitch clarity, value proposition framing, and objection handling across customer demographic segments.',
    },
    {
      type: 'ab_test',
      icon: <BadgePercent size={19} />,
      iconBg: 'rgba(34, 211, 238, 0.15)',
      iconColor: 'var(--accent-cyan)',
      title: 'Pricing & WTP',
      description: 'Validate price elasticity, subscription ceilings, and tier packaging against each persona\u2019s stated budget constraints.',
    },
  ];

  return (
    <div className="ns-root">
      <div className="ns-ambient" aria-hidden="true" />
      <div className="ns-inner">
        <div className="ns-kicker">New research study</div>
        <h1 className="ns-title">What do you want to find out?</h1>
        <p className="ns-sub">Ask anything about your business idea, or pick any study type below.</p>

        {validationError && (
          <div role="alert" className="ns-error">
            <AlertCircle size={17} style={{ flexShrink: 0 }} aria-hidden="true" />
            <span>{validationError}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="ns-composer">
          <textarea
            ref={textareaRef}
            className="ns-textarea"
            style={{ outline: 'none', border: 'none', boxShadow: 'none' }}
            value={prompt}
            onChange={(e) => {
              setPrompt(e.target.value);
              if (validationError) setValidationError(null);
            }}
            onKeyDown={handleKeyDown}
            placeholder="Describe your business idea, target audience, or pricing hypothesis (e.g., An AI study planner for students with a 250 BDT/month tier)..."
            rows={3}
            aria-label="Business idea description"
          />
          <div className="ns-composer-bar">
            <span className="ns-hint">
              <span className="ns-kbd">Ctrl</span>+<span className="ns-kbd">Enter</span> to start
            </span>
            <button
              type="submit"
              className="ns-send"
              disabled={isSubmitting || !prompt.trim()}
              aria-label={isSubmitting ? 'Creating study...' : 'Start research study'}
            >
              {isSubmitting ? (
                <Loader2 size={19} className="animate-spin" aria-hidden="true" />
              ) : (
                <ArrowUp size={19} strokeWidth={2.5} aria-hidden="true" />
              )}
            </button>
          </div>
        </form>

        <div className="ns-examples" aria-label="Example ideas">
          {EXAMPLE_PROMPTS.map((ex) => (
            <button
              key={ex}
              type="button"
              className="ns-example"
              disabled={isSubmitting}
              onClick={() => {
                setPrompt(ex);
                setValidationError(null);
                textareaRef.current?.focus();
              }}
              title={ex}
            >
              {ex}
            </button>
          ))}
        </div>

        {onOpenExampleStudy && (
          <button type="button" className="ns-demo-link" onClick={onOpenExampleStudy}>
            See a finished example study
            <ArrowUpRight size={14} aria-hidden="true" />
          </button>
        )}

        <div className="ns-section-label">Study type</div>
        <div className="ns-grid" role="group" aria-label="Study type selection">
          {studyTypes.map((item) => {
            const isSelected = selectedType === item.type;
            return (
              <button
                key={item.type}
                type="button"
                className={`ns-card${isSelected ? ' ns-selected' : ''}`}
                aria-pressed={isSelected}
                disabled={isSubmitting}
                onClick={() => handleCardClick(item.type)}
              >
                <span className="ns-check" aria-hidden="true">
                  <Check size={12} strokeWidth={3} />
                </span>
                <span
                  className="ns-card-icon"
                  style={{ background: item.iconBg, color: item.iconColor }}
                  aria-hidden="true"
                >
                  {item.icon}
                </span>
                <span>
                  <h2 className="ns-card-title">{item.title}</h2>
                  <p className="ns-card-desc">{item.description}</p>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
