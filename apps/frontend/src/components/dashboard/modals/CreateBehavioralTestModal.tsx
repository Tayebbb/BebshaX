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
import { BehavioralTestType, SyntheticPersona, MarketSegment } from '../../../types';
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

const TEST_TYPE_OPTIONS: TestTypeOption[] = [
  {
    type: 'pricing_test',
    title: 'Pricing Sensitivity',
    description: 'Test willingness to pay across specific price tiers in BDT vs disposable budget.',
    icon: <DollarSign size={20} className="text-teal-400" />,
    tag: 'Willingness to Pay',
    example: 'e.g. ৳299/month for unlimited meal prep automation',
  },
  {
    type: 'purchase_decision',
    title: 'Purchase Decision',
    description: 'Simulate immediate buying intent and evaluate urgency vs hesitation.',
    icon: <ShoppingCart size={20} className="text-cyan-400" />,
    tag: 'Buying Intent',
    example: 'e.g. Would personas buy now to solve exam meal chaos?',
  },
  {
    type: 'feature_test',
    title: 'Feature Utility',
    description: 'Evaluate if a proposed feature solves pain points or feels unnecessary.',
    icon: <Layers size={20} className="text-emerald-400" />,
    tag: 'Feature Appeal',
    example: 'e.g. Automated bKash-integrated grocery list generator',
  },
  {
    type: 'concept_test',
    title: 'Product Concept',
    description: 'Test overall value proposition resonance, clarity, and perceived novelty.',
    icon: <Lightbulb size={20} className="text-amber-400" />,
    tag: 'Concept Resonance',
    example: 'e.g. AI-powered student hostel meal & diet planner',
  },
  {
    type: 'message_test',
    title: 'Marketing Copy',
    description: 'Test headlines, value proposition clarity, emotional appeal, and CTA friction.',
    icon: <MessageSquare size={20} className="text-sky-400" />,
    tag: 'Copy Resonance',
    example: 'e.g. "Plan your entire week of meals in 30 seconds"',
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
    example: 'e.g. Switching from handwritten lists and YouTube recipes',
  },
  {
    type: 'objection_test',
    title: 'Adoption Barriers',
    description: 'Surface the strongest friction points, trust hurdles, and hidden blockers.',
    icon: <AlertTriangle size={20} className="text-orange-400" />,
    tag: 'Friction & Risk',
    example: 'e.g. Data privacy concerns or food taste mismatch fears',
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

  // Dynamic configuration form fields
  const [price, setPrice] = useState('৳299');
  const [billingPeriod, setBillingPeriod] = useState('monthly');
  const [alternative, setAlternative] = useState('Free YouTube recipes & manual mess arrangements');
  const offer = 'Standard pricing';
  const [featureName, setFeatureName] = useState('AI Automated Weekly Meal Plan');
  const [benefit, setBenefit] = useState('Saves 45 minutes of decision fatigue every day');
  const [headline, setHeadline] = useState('Plan your entire week of nutritious meals in 30 seconds');
  const [cta, setCta] = useState('Start Free Trial');
  const [customScenarioText, setCustomScenarioText] = useState('');

  // Population selection
  const [populationType, setPopulationType] = useState<'all' | 'segment' | 'selected_personas'>('all');
  const [selectedSegmentId, setSelectedSegmentId] = useState<string>('');
  const [selectedPersonaIds, setSelectedPersonaIds] = useState<string[]>([]);
  const [personas, setPersonas] = useState<SyntheticPersona[]>([]);
  const [segments, setSegments] = useState<MarketSegment[]>([]);
  const [_isLoadingContext, setIsLoadingContext] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  useDialogA11y(dialogRef, isOpen, onClose);

  useEffect(() => {
    if (!isOpen) return;
    const loadContext = async () => {
      setIsLoadingContext(true);
      try {
        const [pList, sList] = await Promise.all([
          api.getStudyPersonas(studyId).catch(() => ({ personas: [] })),
          api.listStudySegments(studyId).catch(() => []),
        ]);
        const validPersonas = pList.personas || [];
        setPersonas(validPersonas);
        setSegments(sList || []);

        if (initialPersonaId && validPersonas.some((p: SyntheticPersona) => p.id === initialPersonaId)) {
          setSelectedPersonaIds([initialPersonaId]);
          setPopulationType('selected_personas');
        } else if (validPersonas.length > 0) {
          setSelectedPersonaIds(validPersonas.map((p: SyntheticPersona) => p.id));
        }

        if (sList && sList.length > 0) {
          setSelectedSegmentId(sList[0].id);
        }
      } catch {
        // Soft fallback
      } finally {
        setIsLoadingContext(false);
      }
    };
    loadContext();
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
      return personas.filter((p) => p.segment_id === selectedSegmentId).length || personas.length;
    }
    return selectedPersonaIds.length;
  };

  const buildStructuredConfig = (): Record<string, any> => {
    const config: Record<string, any> = { test_type: selectedType };
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
    setIsSubmitting(true);
    setError(null);
    try {
      const config = buildStructuredConfig();
      const scenarioText =
        customScenarioText ||
        `${name}: ${description}. Parameters: ${JSON.stringify(config)}`;

      // 1. Create Test
      const test = await api.createBehavioralTest(studyId, {
        name: name || `${selectedType} Test`,
        description: description,
        test_type: selectedType,
        configuration: config,
        scenario_title: name,
        scenario_text: scenarioText,
      });

      // 2. Trigger Run
      const run = await api.triggerBehavioralTestRun(studyId, test.id, {
        scenario_title: name,
        scenario_text: scenarioText,
        parameters: config,
        target_population_type: populationType,
        target_segment_id: populationType === 'segment' ? selectedSegmentId : undefined,
        target_persona_ids: populationType === 'selected_personas' ? selectedPersonaIds : undefined,
      });

      onTestCreated(test.id, run.id);
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Failed to start behavioral simulation');
    } finally {
      setIsSubmitting(false);
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
      onClick={onClose}
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
          border: '1px solid var(--accent-glow)',
          borderRadius: '16px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7), 0 0 30px var(--accent-subtle)',
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
            background: 'linear-gradient(to right, var(--glass-strong), rgba(13, 148, 136, 0.15))',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '10px',
                backgroundColor: 'var(--accent-subtle)',
                border: '1px solid var(--border-hover)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--accent-teal)',
              }}
            >
              <Sliders size={20} />
            </div>
            <div>
              <h2 id="create-behavioral-test-title" style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-main)' }}>
                New Behavioral Simulation
              </h2>
              <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                Step {step} of 4 — {step === 1 ? 'Choose Test Type' : step === 2 ? 'Configure Scenario' : step === 3 ? 'Select Population' : 'Preview & Confirm'}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close new behavioral simulation dialog"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: '8px',
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
                backgroundColor: step >= s ? '#14B8A6' : 'transparent',
                transition: 'background-color 0.3s ease',
              }}
            />
          ))}
        </div>

        {/* Body Content */}
        <div style={{ padding: '24px', overflowY: 'auto', flex: 1 }}>
          {error && (
            <div
              style={{
                padding: '12px 16px',
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
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
                      onClick={() => handleTypeSelect(opt.type)}
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
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Student Meal App Monthly Pricing"
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    backgroundColor: 'var(--bg-card-hover)',
                    border: '1px solid var(--border-soft)',
                    color: 'var(--text-primary)',
                    fontSize: '0.9rem',
                    outline: 'none',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              {/* Dynamic Type-specific form fields */}
              {selectedType === 'pricing_test' && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(240px, 100%), 1fr))', gap: '14px' }}>
                  <div>
                    <label htmlFor="bt-price" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                      Proposed Price (BDT ৳)
                    </label>
                    <input
                      id="bt-price"
                      type="text"
                      value={price}
                      onChange={(e) => setPrice(e.target.value)}
                      placeholder="e.g. ৳299"
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
                      <option value="per_use">Pay per meal / per use</option>
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
                  Detailed Scenario Context (Optional)
                </label>
                <textarea
                  id="bt-scenario"
                  rows={3}
                  value={customScenarioText}
                  onChange={(e) => setCustomScenarioText(e.target.value)}
                  placeholder="Describe specific conditions (e.g. During semester final exams, student receives a bKash prompt offering ৳299/mo for automated grocery ordering...)"
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              <div>
                <h3 style={{ margin: '0 0 6px 0', fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Select Target Population
                </h3>
                <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                  Run this behavioral scenario against your synthetic customer population.
                </p>
              </div>

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
                    style={{ accentColor: '#14B8A6' }}
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
                    style={{ accentColor: '#14B8A6' }}
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
                          style={{ accentColor: '#14B8A6' }}
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
                    style={{ accentColor: '#14B8A6' }}
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
                          style={{ accentColor: '#14B8A6' }}
                        />
                        <span style={{ color: isChecked ? 'var(--text-main)' : 'var(--text-secondary)' }}>{p.name}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
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
                  backgroundColor: 'var(--accent-subtle)',
                  borderRadius: '10px',
                  border: '1px solid var(--accent-glow)',
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
            backgroundColor: 'var(--glass-strong)',
          }}
        >
          {step > 1 ? (
            <button
              onClick={() => setStep((s) => (s - 1) as any)}
              disabled={isSubmitting}
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
                cursor: 'pointer',
              }}
            >
              <ArrowLeft size={16} />
              Back
            </button>
          ) : (
            <div />
          )}

          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              onClick={onClose}
              disabled={isSubmitting}
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
                onClick={() => setStep((s) => (s + 1) as any)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 20px',
                  borderRadius: '8px',
                  backgroundColor: '#0D9488',
                  border: 'none',
                  color: 'var(--text-main)',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  boxShadow: '0 0 15px rgba(13, 148, 136, 0.3)',
                }}
              >
                Continue
                <ArrowRight size={16} />
              </button>
            ) : (
              <button
                onClick={handleRunSimulation}
                disabled={isSubmitting || (populationType === 'selected_personas' && selectedPersonaIds.length === 0)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 22px',
                  borderRadius: '8px',
                  backgroundColor: '#14B8A6',
                  border: 'none',
                  color: 'var(--text-on-accent)',
                  fontSize: '0.88rem',
                  fontWeight: 700,
                  cursor: isSubmitting ? 'not-allowed' : 'pointer',
                  boxShadow: '0 0 20px rgba(20, 184, 166, 0.4)',
                }}
              >
                <Sparkles size={16} />
                {isSubmitting ? 'Starting Simulation...' : 'Run Simulation'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
