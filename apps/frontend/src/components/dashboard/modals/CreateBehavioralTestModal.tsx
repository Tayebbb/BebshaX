import React, { useState, useEffect, useRef } from 'react';
import {
  X,
  Sparkles,
  ArrowRight,
  ArrowLeft,
  DollarSign,
  ShoppingCart,
  Layers,
  Lightbulb,
  MessageSquare,
  Gift,
  RefreshCw,
  AlertTriangle,
  Users,
  Sliders,
  ShieldCheck,
} from 'lucide-react';
import { BehavioralTest, BehavioralTestType, SyntheticPersona, MarketSegment } from '../../../types';
import { api } from '../../../services/api';
import { useDialogA11y } from '../../../utils/useDialogA11y';

interface CreateBehavioralTestModalProps {
  isOpen: boolean;
  onClose: () => void;
  studyId: string;
  onTestCreated: (testId: string, runId?: string) => void;
  initialPersonaId?: string;
}

interface TestTypeOption {
  type: BehavioralTestType;
  title: string;
  description: string;
  icon: React.ReactNode;
  tag: string;
  example: string;
}

interface SavedSimulation {
  test: BehavioralTest;
  payload: {
    scenario_title: string;
    scenario_text: string;
    parameters: Record<string, unknown>;
    target_population_type: 'all' | 'segment' | 'selected_personas';
    target_segment_id?: string;
    target_persona_ids?: string[];
  };
}

const TEST_TYPE_OPTIONS: TestTypeOption[] = [
  {
    type: 'pricing_test',
    title: 'Pricing Sensitivity',
    description: 'Test willingness to pay across specific price tiers in BDT vs disposable budget.',
    icon: <DollarSign size={20} className="text-teal-400" />,
    tag: 'Willingness to Pay',
    example: 'e.g. à§³299/month for the full plan',
  },
  {
    type: 'purchase_decision',
    title: 'Purchase Decision',
    description: 'Simulate immediate buying intent and evaluate urgency vs hesitation.',
    icon: <ShoppingCart size={20} className="text-cyan-400" />,
    tag: 'Buying Intent',
    example: 'e.g. Would personas buy now, or wait and keep their current workaround?',
  },
  {
    type: 'feature_test',
    title: 'Feature Utility',
    description: 'Evaluate if a proposed feature solves pain points or feels unnecessary.',
    icon: <Layers size={20} className="text-emerald-400" />,
    tag: 'Feature Appeal',
    example: 'e.g. One-tap reorder with saved payment details',
  },
  {
    type: 'concept_test',
    title: 'Product Concept',
    description: 'Test overall value proposition resonance, clarity, and perceived novelty.',
    icon: <Lightbulb size={20} className="text-amber-400" />,
    tag: 'Concept Resonance',
    example: 'e.g. A subscription that replaces a weekly errand',
  },
  {
    type: 'message_test',
    title: 'Marketing Copy',
    description: 'Test headlines, value proposition clarity, emotional appeal, and CTA friction.',
    icon: <MessageSquare size={20} className="text-sky-400" />,
    tag: 'Copy Resonance',
    example: 'e.g. "Done in 30 seconds, every week"',
  },
  {
    type: 'offer_test',
    title: 'Promotional Offer',
    description: 'Evaluate discounts, trial terms, and whether incentives drive conversion.',
    icon: <Gift size={20} className="text-violet-400" />,
    tag: 'Promotions & Trials',
    example: 'e.g. First month 50% off or 14-day free pass',
  },
  {
    type: 'switching_test',
    title: 'Competitor Switching',
    description: 'Measure the friction of abandoning free manual tools or rival apps.',
    icon: <RefreshCw size={20} className="text-rose-400" />,
    tag: 'Migration Friction',
    example: 'e.g. Switching from the free manual routine they use today',
  },
  {
    type: 'objection_test',
    title: 'Adoption Barriers',
    description: 'Surface the strongest friction points, trust hurdles, and hidden blockers.',
    icon: <AlertTriangle size={20} className="text-orange-400" />,
    tag: 'Friction & Risk',
    example: 'e.g. Data privacy worries or doubts the service shows up on time',
  },
];

export const CreateBehavioralTestModal: React.FC<CreateBehavioralTestModalProps> = ({
  isOpen,
  onClose,
  studyId,
  onTestCreated,
  initialPersonaId,
}) => {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [selectedType, setSelectedType] = useState<BehavioralTestType>('pricing_test');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  // Dynamic configuration form fields. Deliberately blank: a prefilled meal-prep
  // scenario used to run unnoticed against studies about anything else.
  const [price, setPrice] = useState('');
  const [billingPeriod, setBillingPeriod] = useState('monthly');
  const [alternative, setAlternative] = useState('');
  const offer = 'Standard pricing';
  const [featureName, setFeatureName] = useState('');
  const [benefit, setBenefit] = useState('');
  const [headline, setHeadline] = useState('');
  const [cta, setCta] = useState('');
  const [customScenarioText, setCustomScenarioText] = useState('');

  // Population selection
  const [populationType, setPopulationType] = useState<'all' | 'segment' | 'selected_personas'>('all');
  const [selectedSegmentId, setSelectedSegmentId] = useState<string>('');
  const [selectedPersonaIds, setSelectedPersonaIds] = useState<string[]>([]);
  const [personas, setPersonas] = useState<SyntheticPersona[]>([]);
  const [segments, setSegments] = useState<MarketSegment[]>([]);
  const [isLoadingContext, setIsLoadingContext] = useState(false);
  const [contextError, setContextError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [savedSimulation, setSavedSimulation] = useState<SavedSimulation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const modalEpochRef = useRef<symbol | null>(null);
  const contextRequestRef = useRef(0);
  const submittingRef = useRef(false);

  const handleClose = () => {
    modalEpochRef.current = null;
    contextRequestRef.current += 1;
    submittingRef.current = false;
    setIsSubmitting(false);
    onClose();
  };
  useDialogA11y(dialogRef, isOpen, handleClose);

  const loadContext = async (modalEpoch: symbol) => {
    const request = ++contextRequestRef.current;
    const isCurrent = () => modalEpochRef.current === modalEpoch && contextRequestRef.current === request;
    setIsLoadingContext(true);
    setContextError(null);
    try {
      const [personaList, segmentList] = await Promise.all([
        api.getStudyPersonas(studyId),
        api.listStudySegments(studyId),
      ]);
      if (!isCurrent()) return;
      const validPersonas = personaList.personas || [];
      setPersonas(validPersonas);
      setSegments(segmentList);
      setSelectedPersonaIds(initialPersonaId
        ? validPersonas.filter((persona) => persona.id === initialPersonaId).map((persona) => persona.id)
        : validPersonas.map((persona) => persona.id));
      setSelectedSegmentId(segmentList[0]?.id || '');
    } catch (failure: unknown) {
      if (isCurrent()) setContextError(failure instanceof Error ? failure.message : 'Population could not be loaded.');
    } finally {
      if (isCurrent()) setIsLoadingContext(false);
    }
  };

  useEffect(() => {
    const modalEpoch = isOpen ? Symbol() : null;
    modalEpochRef.current = modalEpoch;
    submittingRef.current = false;
    setIsSubmitting(false);
    setSavedSimulation(null);
    setError(null);
    setContextError(null);
    setStep(1);
    setSelectedType('pricing_test');
    setName(`${TEST_TYPE_OPTIONS[0].title} Simulation`);
    setDescription(TEST_TYPE_OPTIONS[0].description);
    setPrice('');
    setBillingPeriod('monthly');
    setAlternative('');
    setFeatureName('');
    setBenefit('');
    setHeadline('');
    setCta('');
    setCustomScenarioText('');
    setPopulationType(initialPersonaId ? 'selected_personas' : 'all');
    setSelectedPersonaIds([]);
    setSelectedSegmentId('');
    setPersonas([]);
    setSegments([]);
    setIsLoadingContext(false);
    if (modalEpoch) void loadContext(modalEpoch);
    return () => {
      modalEpochRef.current = null;
      contextRequestRef.current += 1;
      submittingRef.current = false;
    };
  }, [isOpen, studyId, initialPersonaId]);

  // Set default names based on test type
  useEffect(() => {
    const opt = TEST_TYPE_OPTIONS.find((o) => o.type === selectedType);
    if (opt && !name) {
      setName(`${opt.title} Simulation`);
      setDescription(opt.description);
    }
  }, [selectedType, name]);

  if (!isOpen) return null;

  const handleTypeSelect = (type: BehavioralTestType) => {
    setSelectedType(type);
    const opt = TEST_TYPE_OPTIONS.find((o) => o.type === type);
    if (opt) {
      setName(`${opt.title} Simulation`);
      setDescription(opt.description);
    }
    setStep(2);
  };

  const getActivePersonaCount = () => {
    if (populationType === 'all') return personas.length;
    if (populationType === 'segment') {
      return personas.filter((persona) => persona.segment_id === selectedSegmentId).length;
    }
    return personas.filter((persona) => selectedPersonaIds.includes(persona.id)).length;
  };

  /** What step 2 still needs before the scenario can be simulated; null when complete. */
  const scenarioMissing: string | null = (() => {
    if (!name.trim()) return 'a test name';
    if (selectedType === 'pricing_test' && !price.trim()) return 'a proposed price';
    // "à§³299" and "299/month" are fine; "abc" and "-50" were accepted end to end (live 2026-09-14).
    if (price.trim() && !/\d/.test(price)) return 'a price that includes an amount (e.g. 299)';
    if (price.trim() && /-\s*\d/.test(price)) return 'a price of zero or more';
    if (selectedType === 'feature_test' && !featureName.trim()) return 'a feature name';
    if (selectedType === 'message_test' && !headline.trim()) return 'a headline';
    if (!['pricing_test', 'feature_test', 'message_test'].includes(selectedType) && !customScenarioText.trim()) {
      return 'a scenario description';
    }
    return null;
  })();
  const scenarioContextRequired = !['pricing_test', 'feature_test', 'message_test'].includes(selectedType);
  const populationReady = !isLoadingContext && !contextError && getActivePersonaCount() > 0
    && (populationType !== 'segment' || segments.some((segment) => segment.id === selectedSegmentId));
  const continueBlocked = (step === 2 && scenarioMissing !== null) || (step === 3 && !populationReady);

  const buildStructuredConfig = (): Record<string, unknown> => {
    const config: Record<string, unknown> = { test_type: selectedType };
    if (selectedType === 'pricing_test') {
      config.price = price;
      config.billing_period = billingPeriod;
      config.alternative = alternative;
      config.offer = offer;
    } else if (selectedType === 'feature_test') {
      config.feature = featureName;
      config.benefit = benefit;
    } else if (selectedType === 'message_test') {
      config.headline = headline;
      config.cta = cta;
    } else if (selectedType === 'offer_test') {
      config.offer = offer;
      config.price = price;
    } else if (selectedType === 'switching_test') {
      config.current_solution = alternative;
      config.advantage = benefit;
    } else {
      config.price = price;
      config.feature = featureName;
    }
    return config;
  };

  const handleRunSimulation = async () => {
    const modalEpoch = modalEpochRef.current;
    if (!modalEpoch || submittingRef.current) return;
    if (!savedSimulation && scenarioMissing) {
      setStep(2);
      setError(`Add ${scenarioMissing} before running the simulation.`);
      return;
    }
    if (!savedSimulation && !populationReady) {
      setStep(3);
      setError('Select an available population before running the simulation.');
      return;
    }
    submittingRef.current = true;
    setIsSubmitting(true);
    setError(null);
    let submission = savedSimulation;
    try {
      if (!submission) {
        const config = buildStructuredConfig();
        const scenarioText = customScenarioText || `${name}: ${description}. Parameters: ${JSON.stringify(config)}`;
        const payload: SavedSimulation['payload'] = {
          scenario_title: name,
          scenario_text: scenarioText,
          parameters: config,
          target_population_type: populationType,
          target_segment_id: populationType === 'segment' ? selectedSegmentId : undefined,
          target_persona_ids: populationType === 'selected_personas' ? [...selectedPersonaIds] : undefined,
        };
        const test: BehavioralTest = await api.createBehavioralTest(studyId, {
          name,
          description,
          test_type: selectedType,
          configuration: config,
          scenario_title: name,
          scenario_text: scenarioText,
        });
        if (modalEpochRef.current !== modalEpoch) return;
        submission = { test, payload };
        setSavedSimulation(submission);
      }

      const run = await api.triggerBehavioralTestRun(studyId, submission.test.id, submission.payload);
      if (modalEpochRef.current !== modalEpoch) return;
      onTestCreated(submission.test.id, run.id);
      handleClose();
    } catch (failure: unknown) {
      if (modalEpochRef.current !== modalEpoch) return;
      const message = failure instanceof Error ? failure.message : 'The request could not be completed.';
      setError(submission
        ? `Test saved, but the simulation run failed to start. ${message} Retry the run with the saved configuration or open the saved test.`
        : `Test was not confirmed saved. ${message} Check Behavioral Tests if the response was lost before retrying.`);
    } finally {
      if (modalEpochRef.current === modalEpoch) {
        submittingRef.current = false;
        setIsSubmitting(false);
      }
    }
  };

  const togglePersonaSelection = (pId: string) => {
    setSelectedPersonaIds((prev) =>
      prev.includes(pId) ? prev.filter((id) => id !== pId) : [...prev, pId]
    );
  };

  return (
    <div
      className="bx-backdrop"
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'var(--scrim)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
      onClick={handleClose}
    >
      <div
        ref={dialogRef}
        className="bx-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-behavioral-test-title"
        style={{
          width: '100%',
          maxWidth: '780px',
          maxHeight: '90vh',
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-control)',
          borderRadius: '8px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          color: 'var(--text-primary)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid var(--fill-soft-2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: 'var(--bg-card)',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
            <div
              style={{
                width: '38px',
                height: '38px',
                flexShrink: 0,
                borderRadius: '8px',
                backgroundColor: 'var(--bg-card-hover)',
                border: '1px solid var(--border-control)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--accent-teal)',
              }}
            >
              <Sliders size={20} />
            </div>
            <div>
              <h2 id="create-behavioral-test-title" style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700, letterSpacing: 0, color: 'var(--text-main)', overflowWrap: 'anywhere' }}>
                New Behavioral Simulation
              </h2>
              <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                Step {step} of 4 â€” {step === 1 ? 'Choose Test Type' : step === 2 ? 'Configure Scenario' : step === 3 ? 'Select Population' : 'Preview & Confirm'}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            aria-label="Close new behavioral simulation dialog"
            className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: '8px',
              minWidth: '44px',
              minHeight: '44px',
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>

        {/* Stepper Progress Bar */}
        <div style={{ display: 'flex', height: '3px', backgroundColor: 'var(--fill-soft)' }}>
          {[1, 2, 3, 4].map((s) => (
            <div
              key={s}
              style={{
                flex: 1,
                backgroundColor: step >= s ? 'var(--accent-primary)' : 'transparent',
                transition: 'background-color 0.3s ease',
              }}
            />
          ))}
        </div>

        {/* Body Content */}
        <div style={{ padding: '24px', overflowY: 'auto', flex: 1 }}>
          {isLoadingContext && <p role="status">Loading population...</p>}
          {contextError && (
            <div role="alert" className="bx-alert bx-alert--error">
              <p>{contextError}</p>
              <button type="button" disabled={isLoadingContext || isSubmitting || !!savedSimulation} onClick={() => {
                const modalEpoch = modalEpochRef.current;
                if (modalEpoch) void loadContext(modalEpoch);
              }} className="bx-btn bx-btn-secondary">Retry Population</button>
            </div>
          )}
          {error && (
            <div
              role="alert"
              style={{
                padding: '12px 16px',
                backgroundColor: 'var(--bg-card-hover)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                borderRadius: '8px',
                color: 'var(--status-error-text)',
                fontSize: '0.85rem',
                marginBottom: '20px',
              }}
            >
              {error}
            </div>
          )}

          {/* STEP 1: Test Type Selection */}
          {step === 1 && (
            <div>
              <div style={{ marginBottom: '18px' }}>
                <h3 style={{ margin: '0 0 6px 0', fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  What product decision do you want to test?
                </h3>
                <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                  Simulations test persona economic constraints, cognitive friction, and switching resistance.
                </p>
              </div>

              <div
                role="radiogroup"
                aria-label="Test type"
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(min(320px, 100%), 1fr))',
                  gap: '12px',
                }}
              >
                {TEST_TYPE_OPTIONS.map((opt) => {
                  const isSelected = selectedType === opt.type;
                  return (
                    <div
                      key={opt.type}
                      role="radio"
                      aria-checked={isSelected}
                      aria-label={opt.title}
                      tabIndex={0}
                      onClick={() => handleTypeSelect(opt.type)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          handleTypeSelect(opt.type);
                        }
                      }}
                      style={{
                        padding: '16px',
                        borderRadius: '12px',
                        backgroundColor: isSelected ? 'var(--accent-subtle)' : 'var(--glass-mid)',
                        border: isSelected ? '1px solid var(--accent-teal)' : '1px solid var(--fill-soft-2)',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <div
                            style={{
                              padding: '8px',
                              borderRadius: '8px',
                              backgroundColor: 'var(--glass-strong)',
                            }}
                          >
                            {opt.icon}
                          </div>
                          <span style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--text-main)' }}>{opt.title}</span>
                        </div>
                        <span
                          style={{
                            fontSize: '0.7rem',
                            padding: '3px 8px',
                            borderRadius: '999px',
                            backgroundColor: 'var(--accent-subtle)',
                            color: 'var(--accent-teal-bright)',
                            border: '1px solid var(--border-hover)',
                          }}
                        >
                          {opt.tag}
                        </span>
                      </div>
                      <p style={{ margin: '0 0 8px 0', fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                        {opt.description}
                      </p>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                        {opt.example}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* STEP 2: Scenario Configuration */}
          {step === 2 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              <div>
                <label htmlFor="bt-name" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                  Test Name
                </label>
                <input
                  id="bt-name"
                  type="text"
                  className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Monthly plan pricing"
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    backgroundColor: 'var(--bg-card-hover)',
                    border: '1px solid var(--border-soft)',
                    color: 'var(--text-primary)',
                    fontSize: '0.9rem',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              {/* Dynamic Type-specific form fields */}
              {selectedType === 'pricing_test' && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(240px, 100%), 1fr))', gap: '14px' }}>
                  <div>
                    <label htmlFor="bt-price" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                      Proposed Price (BDT à§³)
                    </label>
                    <input
                      id="bt-price"
                      type="text"
                      value={price}
                      onChange={(e) => setPrice(e.target.value)}
                      placeholder="e.g. à§³299"
                      style={{
                        width: '100%',
                        padding: '10px 14px',
                        borderRadius: '8px',
                        backgroundColor: 'var(--bg-card-hover)',
                        border: '1px solid var(--border-soft)',
                        color: 'var(--text-primary)',
                        fontSize: '0.9rem',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>
                  <div>
                    <label htmlFor="bt-billing" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                      Billing Period
                    </label>
                    <select
                      id="bt-billing"
                      value={billingPeriod}
                      onChange={(e) => setBillingPeriod(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '10px 34px 10px 14px',
                        borderRadius: '8px',
                        backgroundColor: 'var(--bg-card-hover)',
                        border: '1px solid var(--border-soft)',
                        color: 'var(--text-primary)',
                        fontSize: '0.9rem',
                        boxSizing: 'border-box',
                      }}
                    >
                      <option value="monthly">Monthly Subscription</option>
                      <option value="yearly">Yearly (Annual)</option>
                      <option value="one_time">One-time Purchase</option>
                      <option value="per_use">Pay per use</option>
                    </select>
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label htmlFor="bt-alternative" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                      Current Alternative Personas Use
                    </label>
                    <input
                      id="bt-alternative"
                      type="text"
                      value={alternative}
                      onChange={(e) => setAlternative(e.target.value)}
                      placeholder="e.g. Free YouTube recipes, messy handwritten lists, or local mess catering"
                      style={{
                        width: '100%',
                        padding: '10px 14px',
                        borderRadius: '8px',
                        backgroundColor: 'var(--bg-card-hover)',
                        border: '1px solid var(--border-soft)',
                        color: 'var(--text-primary)',
                        fontSize: '0.9rem',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>
                </div>
              )}

              {selectedType === 'feature_test' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div>
                    <label htmlFor="bt-feature" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                      Feature Name
                    </label>
                    <input
                      id="bt-feature"
                      type="text"
                      value={featureName}
                      onChange={(e) => setFeatureName(e.target.value)}
                      placeholder="e.g. Automated Weekly Meal Plan Generator"
                      style={{
                        width: '100%',
                        padding: '10px 14px',
                        borderRadius: '8px',
                        backgroundColor: 'var(--bg-card-hover)',
                        border: '1px solid var(--border-soft)',
                        color: 'var(--text-primary)',
                        fontSize: '0.9rem',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>
                  <div>
                    <label htmlFor="bt-benefit" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                      Key Claimed Benefit
                    </label>
                    <input
                      id="bt-benefit"
                      type="text"
                      value={benefit}
                      onChange={(e) => setBenefit(e.target.value)}
                      placeholder="e.g. Saves 45 minutes daily and eliminates decision fatigue"
                      style={{
                        width: '100%',
                        padding: '10px 14px',
                        borderRadius: '8px',
                        backgroundColor: 'var(--bg-card-hover)',
                        border: '1px solid var(--border-soft)',
                        color: 'var(--text-primary)',
                        fontSize: '0.9rem',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>
                </div>
              )}

              {selectedType === 'message_test' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div>
                    <label htmlFor="bt-headline" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                      Marketing Headline / Value Prop
                    </label>
                    <input
                      id="bt-headline"
                      type="text"
                      value={headline}
                      onChange={(e) => setHeadline(e.target.value)}
                      placeholder='e.g. "Plan your entire week of meals in 30 seconds."'
                      style={{
                        width: '100%',
                        padding: '10px 14px',
                        borderRadius: '8px',
                        backgroundColor: 'var(--bg-card-hover)',
                        border: '1px solid var(--border-soft)',
                        color: 'var(--text-primary)',
                        fontSize: '0.9rem',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>
                  <div>
                    <label htmlFor="bt-cta" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                      Call to Action (CTA)
                    </label>
                    <input
                      id="bt-cta"
                      type="text"
                      value={cta}
                      onChange={(e) => setCta(e.target.value)}
                      placeholder="e.g. Get Started Free"
                      style={{
                        width: '100%',
                        padding: '10px 14px',
                        borderRadius: '8px',
                        backgroundColor: 'var(--bg-card-hover)',
                        border: '1px solid var(--border-soft)',
                        color: 'var(--text-primary)',
                        fontSize: '0.9rem',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>
                </div>
              )}

              <div>
                <label htmlFor="bt-scenario" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                  Detailed Scenario Context {scenarioContextRequired ? '(Required for this test type)' : '(Optional)'}
                </label>
                <textarea
                  id="bt-scenario"
                  rows={3}
                  value={customScenarioText}
                  onChange={(e) => setCustomScenarioText(e.target.value)}
                  aria-required={scenarioContextRequired}
                  placeholder="Describe specific conditions (e.g. At the end of the month, the persona sees a mobile-payment prompt offering the plan at à§³299/mo...)"
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    backgroundColor: 'var(--bg-card-hover)',
                    border: '1px solid var(--border-soft)',
                    color: 'var(--text-primary)',
                    fontSize: '0.85rem',
                    resize: 'vertical',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
            </div>
          )}

          {/* STEP 3: Target Population */}
          {step === 3 && (
            <fieldset disabled={isLoadingContext || !!contextError} aria-label="Target population" style={{ border: 0, margin: 0, padding: 0, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '18px' }}>
              <div>
                <h3 style={{ margin: '0 0 6px 0', fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Select Target Population
                </h3>
                <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                  Run this behavioral scenario against your synthetic customer population.
                </p>
              </div>

              {!isLoadingContext && !contextError && getActivePersonaCount() === 0 && (
                <p role="status">
                  {personas.length === 0 ? 'No personas are available in this study. Return to the study to add personas.'
                    : populationType === 'segment' ? 'No personas belong to the selected segment. Choose another population.'
                      : 'Select at least one available persona to continue.'}
                </p>
              )}

              {/* Radio Group */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '14px 16px',
                    borderRadius: '10px',
                    backgroundColor: populationType === 'all' ? 'var(--accent-subtle)' : 'var(--glass-mid)',
                    border: populationType === 'all' ? '1px solid var(--accent-teal)' : '1px solid var(--fill-soft-2)',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="radio"
                    name="populationType"
                    checked={populationType === 'all'}
                    onChange={() => setPopulationType('all')}
                    style={{ accentColor: 'var(--accent-primary)' }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-main)' }}>All Personas in Study</div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                      Simulate across all {personas.length} synthetic personas in this study.
                    </div>
                  </div>
                </label>

                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '14px 16px',
                    borderRadius: '10px',
                    backgroundColor: populationType === 'segment' ? 'var(--accent-subtle)' : 'var(--glass-mid)',
                    border: populationType === 'segment' ? '1px solid var(--accent-teal)' : '1px solid var(--fill-soft-2)',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="radio"
                    name="populationType"
                    checked={populationType === 'segment'}
                    onChange={() => setPopulationType('segment')}
                    style={{ accentColor: 'var(--accent-primary)' }}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-main)' }}>Specific Market Segment</div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                      Target only personas within a specific customer segment.
                    </div>
                  </div>
                </label>

                {populationType === 'segment' && segments.length > 0 && (
                  <div style={{ paddingLeft: '32px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {segments.map((seg) => (
                      <label
                        key={seg.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          fontSize: '0.85rem',
                          color: 'var(--text-primary)',
                          cursor: 'pointer',
                        }}
                      >
                        <input
                          type="radio"
                          name="selectedSegment"
                          checked={selectedSegmentId === seg.id}
                          onChange={() => setSelectedSegmentId(seg.id)}
                          style={{ accentColor: 'var(--accent-primary)' }}
                        />
                        <span>{seg.name} ({seg.population_percentage.toFixed(0)}% of market)</span>
                      </label>
                    ))}
                  </div>
                )}

                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '14px 16px',
                    borderRadius: '10px',
                    backgroundColor: populationType === 'selected_personas' ? 'var(--accent-subtle)' : 'var(--glass-mid)',
                    border: populationType === 'selected_personas' ? '1px solid var(--accent-teal)' : '1px solid var(--fill-soft-2)',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="radio"
                    name="populationType"
                    checked={populationType === 'selected_personas'}
                    onChange={() => setPopulationType('selected_personas')}
                    style={{ accentColor: 'var(--accent-primary)' }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-main)' }}>Selected Personas</div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                      Manually pick individual personas to evaluate.
                    </div>
                  </div>
                </label>
              </div>

              {/* Persona Checkbox Grid */}
              {populationType === 'selected_personas' && (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 200px), 1fr))',
                    gap: '8px',
                    maxHeight: '180px',
                    overflowY: 'auto',
                    padding: '8px',
                    backgroundColor: 'var(--bg-card-hover)',
                    borderRadius: '8px',
                  }}
                >
                  {personas.map((p) => {
                    const isChecked = selectedPersonaIds.includes(p.id);
                    return (
                      <div
                        key={p.id}
                        onClick={() => togglePersonaSelection(p.id)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          padding: '6px 10px',
                          borderRadius: '6px',
                          backgroundColor: isChecked ? 'var(--accent-glow)' : 'transparent',
                          cursor: 'pointer',
                          fontSize: '0.82rem',
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => togglePersonaSelection(p.id)}
                          onClick={(e) => e.stopPropagation()}
                          aria-label={`Include ${p.name}`}
                          style={{ accentColor: 'var(--accent-primary)' }}
                        />
                        <span style={{ color: isChecked ? 'var(--text-main)' : 'var(--text-secondary)' }}>{p.name}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </fieldset>
          )}

          {/* STEP 4: Preview & Verification */}
          {step === 4 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div
                style={{
                  padding: '16px',
                  backgroundColor: 'var(--glass-mid)',
                  borderRadius: '12px',
                  border: '1px solid var(--fill-soft-2)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)' }}>
                    Scenario Summary
                  </span>
                  <span
                    style={{
                      fontSize: '0.72rem',
                      padding: '3px 10px',
                      borderRadius: '999px',
                      backgroundColor: 'var(--accent-subtle)',
                      color: 'var(--accent-teal-bright)',
                      border: '1px solid var(--border-hover)',
                    }}
                  >
                    {TEST_TYPE_OPTIONS.find((t) => t.type === selectedType)?.title}
                  </span>
                </div>
                <h4 style={{ margin: '0 0 6px 0', fontSize: '1.1rem', color: 'var(--text-main)' }}>{name}</h4>
                <p style={{ margin: '0 0 12px 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{description}</p>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(min(200px, 100%), 1fr))',
                    gap: '8px',
                    padding: '12px',
                    backgroundColor: 'var(--bg-card)',
                    borderRadius: '8px',
                    fontSize: '0.82rem',
                  }}
                >
                  {selectedType === 'pricing_test' && (
                    <>
                      <div><span style={{ color: 'var(--text-muted)' }}>Price:</span> <strong style={{ color: 'var(--text-primary)' }}>{price}</strong></div>
                      <div><span style={{ color: 'var(--text-muted)' }}>Billing:</span> <strong style={{ color: 'var(--text-primary)' }}>{billingPeriod}</strong></div>
                      <div style={{ gridColumn: '1 / -1' }}><span style={{ color: 'var(--text-muted)' }}>Alternative:</span> <strong style={{ color: 'var(--text-primary)' }}>{alternative}</strong></div>
                    </>
                  )}
                  {selectedType === 'feature_test' && (
                    <>
                      <div style={{ gridColumn: '1 / -1' }}><span style={{ color: 'var(--text-muted)' }}>Feature:</span> <strong style={{ color: 'var(--text-primary)' }}>{featureName}</strong></div>
                      <div style={{ gridColumn: '1 / -1' }}><span style={{ color: 'var(--text-muted)' }}>Benefit:</span> <strong style={{ color: 'var(--text-primary)' }}>{benefit}</strong></div>
                    </>
                  )}
                  {selectedType === 'message_test' && (
                    <>
                      <div style={{ gridColumn: '1 / -1' }}><span style={{ color: 'var(--text-muted)' }}>Headline:</span> <strong style={{ color: 'var(--text-primary)' }}>{headline}</strong></div>
                      <div style={{ gridColumn: '1 / -1' }}><span style={{ color: 'var(--text-muted)' }}>CTA:</span> <strong style={{ color: 'var(--text-primary)' }}>{cta}</strong></div>
                    </>
                  )}
                </div>
              </div>

              {/* Target Count & Synthetic Disclaimer */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px 16px',
                  backgroundColor: 'var(--bg-card-hover)',
                  borderRadius: '8px',
                  border: '1px solid var(--border-soft)',
                  flexWrap: 'wrap',
                  gap: '12px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <Users size={18} className="text-teal-400" />
                  <span style={{ fontSize: '0.88rem', color: 'var(--text-primary)' }}>
                    <strong>{getActivePersonaCount()}</strong> personas will be simulated
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', color: 'var(--accent-teal-bright)' }}>
                  <ShieldCheck size={14} />
                  <span>Synthetic Simulation</span>
                </div>
              </div>

              <div
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--text-muted)',
                  lineHeight: 1.4,
                  padding: '4px 8px',
                }}
              >
                * Notice: Results are simulated behavioral responses based on persona income, habits, past interview signals, and market evidence. They serve as exploratory decision signals, not statistical guarantees.
              </div>
            </div>
          )}
        </div>

        {/* Footer Controls */}
        <div
          style={{
            padding: '16px 24px',
            borderTop: '1px solid var(--fill-soft-2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: 'var(--bg-card)',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          {step > 1 ? (
            <button
              type="button"
              onClick={() => setStep((previous) => (previous - 1) as 1 | 2 | 3 | 4)}
              disabled={isSubmitting || !!savedSimulation}
              className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 18px',
                borderRadius: '8px',
                backgroundColor: 'var(--fill-soft)',
                border: '1px solid var(--border-soft)',
                color: 'var(--text-primary)',
                fontSize: '0.85rem',
                fontWeight: 500,
                cursor: isSubmitting || savedSimulation ? 'not-allowed' : 'pointer',
                opacity: isSubmitting || savedSimulation ? 0.55 : 1,
              }}
            >
              <ArrowLeft size={16} />
              Back
            </button>
          ) : (
            <div />
          )}

          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            {savedSimulation && (
              <button type="button" disabled={isSubmitting} className="bx-btn bx-btn-secondary" onClick={() => {
                if (!modalEpochRef.current) return;
                onTestCreated(savedSimulation.test.id);
                handleClose();
              }}>Open Saved Test</button>
            )}
            <button
              type="button"
              onClick={handleClose}
              className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
              style={{
                padding: '10px 18px',
                borderRadius: '8px',
                backgroundColor: 'transparent',
                border: '1px solid var(--border-soft)',
                color: 'var(--text-secondary)',
                fontSize: '0.85rem',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>

            {step < 4 ? (
              <button
                type="button"
                onClick={() => setStep((previous) => (previous + 1) as 1 | 2 | 3 | 4)}
                disabled={continueBlocked}
                aria-disabled={continueBlocked}
                title={continueBlocked ? step === 2 ? `Add ${scenarioMissing} to continue` : 'Choose an available population to continue' : undefined}
                className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 20px',
                  borderRadius: '8px',
                  backgroundColor: 'var(--accent-primary)',
                  border: 'none',
                  color: 'var(--text-on-accent)',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: continueBlocked ? 'not-allowed' : 'pointer',
                  opacity: continueBlocked ? 0.55 : 1,
                }}
              >
                Continue
                <ArrowRight size={16} />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleRunSimulation}
                disabled={isSubmitting || (!savedSimulation && (!populationReady || scenarioMissing !== null))}
                aria-busy={isSubmitting}
                className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 22px',
                  borderRadius: '8px',
                  backgroundColor: 'var(--accent-primary)',
                  border: 'none',
                  color: 'var(--text-on-accent)',
                  fontSize: '0.88rem',
                  fontWeight: 700,
                  cursor: isSubmitting ? 'not-allowed' : 'pointer',
                  opacity: isSubmitting ? 0.55 : 1,
                }}
              >
                <Sparkles size={16} />
                {isSubmitting ? 'Starting Simulation...' : savedSimulation ? 'Retry Run' : 'Run Simulation'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
