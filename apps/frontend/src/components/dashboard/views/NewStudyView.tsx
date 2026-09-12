import React, { useState, useRef, useLayoutEffect, useId } from 'react';
import {
  Users,
  Compass,
  MessageSquare,
  BadgePercent,
  ArrowUpRight,
  AlertCircle,
} from 'lucide-react';
import { StudyType } from '../../../types';
import { useRouteReady } from '../../../performance/routeTiming';
import { Button } from '../../ui/Button';
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
  useRouteReady(true);
  const [prompt, setPrompt] = useState('');
  const [selectedType, setSelectedType] = useState<StudyType>('interviews');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const formId = useId();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const submissionRef = useRef({ active: false, pending: false });

  useLayoutEffect(() => {
    const epoch = { active: true, pending: false };
    submissionRef.current = epoch;
    return () => { epoch.active = false; };
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const epoch = submissionRef.current;
    if (!epoch.active || epoch.pending) return;
    const cleanPrompt = prompt.trim();

    if (!cleanPrompt) {
      setValidationError('Describe your product idea before starting the study.');
      textareaRef.current?.focus();
      return;
    }

    setValidationError(null);
    epoch.pending = true;
    setIsSubmitting(true);
    try {
      await onStartStudy(selectedType, cleanPrompt);
    } catch (error) {
      if (epoch.active) {
        setValidationError(error instanceof Error ? error.message : "We couldn't create your study. Please try again.");
      }
    } finally {
      epoch.pending = false;
      if (epoch.active) setIsSubmitting(false);
    }
  };

  const handleTypeChange = (type: StudyType) => {
    const epoch = submissionRef.current;
    if (!epoch.active || epoch.pending) return;
    setSelectedType(type);
    setValidationError(null);
  };

  const studyTypes: {
    type: StudyType;
    icon: React.ReactNode;
    title: string;
    description: string;
  }[] = [
    {
      type: 'interviews',
      icon: <Users size={17} aria-hidden="true" />,
      title: 'User Interviews',
      description: 'Explore hypothetical routines, needs, and pain points through synthetic interviews.',
    },
    {
      type: 'landing_page_test',
      icon: <Compass size={17} aria-hidden="true" />,
      title: 'Concept & Demand',
      description: 'Explore possible reactions to a concept, not measured demand or product-market fit.',
    },
    {
      type: 'message_testing',
      icon: <MessageSquare size={17} aria-hidden="true" />,
      title: 'Message Testing',
      description: 'Explore how synthetic personas might interpret a message and question its claims.',
    },
    {
      type: 'ab_test',
      icon: <BadgePercent size={17} aria-hidden="true" />,
      title: 'Pricing & WTP',
      description: 'Explore hypothetical pricing trade-offs, not measured willingness to pay or price elasticity.',
    },
  ];

  return (
    <div className="ns-root">
      <div className="ns-inner">
        <header className="ns-header">
          <h1 className="ns-title">What do you want to find out?</h1>
          <p className="ns-sub">Explore questions and assumptions with synthetic personas.</p>
        </header>

        <form onSubmit={handleSubmit} className="ns-form">
          <fieldset className="ns-types" disabled={isSubmitting}>
            <legend className="ns-label">Study type</legend>
            <div className="ns-modes" role="radiogroup" aria-label="Study type selection">
              {studyTypes.map((item) => (
                <label key={item.type} className="ns-mode">
                  <input
                    type="radio"
                    name={`${formId}-type`}
                    value={item.type}
                    checked={selectedType === item.type}
                    onChange={() => handleTypeChange(item.type)}
                    aria-label={item.title}
                    aria-describedby={`${formId}-mode-description`}
                  />
                  <span className="ns-mode-label">{item.icon}<span>{item.title}</span></span>
                </label>
              ))}
            </div>
            <p className="ns-mode-description" id={`${formId}-mode-description`}>
              {studyTypes.find((item) => item.type === selectedType)?.description}
            </p>
          </fieldset>

          <div className="ns-composer">
            <label className="ns-label" htmlFor={`${formId}-question`}>Research question</label>
            <p className="ns-question-hint" id={`${formId}-question-hint`}>
              Your idea, intended audience, and the uncertainty behind it.
            </p>
            <textarea
              ref={textareaRef}
              id={`${formId}-question`}
              className="ns-textarea"
              value={prompt}
              readOnly={isSubmitting}
              onChange={(event) => {
                setPrompt(event.target.value);
                if (validationError) setValidationError(null);
              }}
              onKeyDown={handleKeyDown}
              placeholder="Describe your business idea or research question..."
              rows={4}
              aria-label="Business idea description"
              aria-invalid={!!validationError}
              aria-describedby={`${formId}-question-hint${validationError ? ` ${formId}-error` : ''}`}
            />
            {validationError && (
              <div role="alert" className="ns-error" id={`${formId}-error`}>
                <AlertCircle size={17} aria-hidden="true" />
                <span>{validationError}</span>
              </div>
            )}
            <div className="ns-composer-bar">
              <p className="ns-disclosure">Synthetic research, not observed customers or validated demand.</p>
              <Button
                type="submit"
                variant="primary"
                className="ns-submit"
                loading={isSubmitting}
                disabled={!prompt.trim()}
                aria-label={isSubmitting ? 'Creating study...' : 'Start research study'}
                trailingIcon={<ArrowUpRight size={17} aria-hidden="true" />}
              >
                {isSubmitting ? 'Creating study...' : 'Start research study'}
              </Button>
            </div>
          </div>
        </form>

        <section className="ns-examples" aria-label="Example ideas">
          <h2 className="ns-section-title">Example questions</h2>
          <ul className="ns-example-list">
            {EXAMPLE_PROMPTS.map((example) => (
              <li key={example}>
                <button
                  type="button"
                  className="ns-example"
                  disabled={isSubmitting}
                  onClick={() => {
                    setPrompt(example);
                    setValidationError(null);
                    textareaRef.current?.focus();
                  }}
                >
                  <span>{example}</span>
                  <ArrowUpRight size={15} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </section>

        {onOpenExampleStudy && (
          <button type="button" className="ns-demo-link" disabled={isSubmitting} onClick={onOpenExampleStudy}>
            See a finished example study
            <ArrowUpRight size={14} aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
};
