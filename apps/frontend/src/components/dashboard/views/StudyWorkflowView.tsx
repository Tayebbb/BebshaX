import React, { useState, useEffect } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Sparkles,
  Package,
  Clock,
  Lightbulb,
  UserCheck,
  Paperclip,
  ArrowUp,
  LogOut,
  CheckCircle2,
  Users,
  MessageSquare,
  FileText,
  Send,
  Zap,
  ShieldAlert,
  Download,
  Share2,
} from 'lucide-react';
import { Study, ResearchGoal, StudyType, Persona, ConversationTurn } from '../../../types';
import { api } from '../../../services/api';

interface StudyWorkflowViewProps {
  studyId?: string;
  initialType?: StudyType;
  initialPrompt?: string;
  onExit: () => void;
}

export const StudyWorkflowView: React.FC<StudyWorkflowViewProps> = ({
  studyId,
  initialType = 'interviews',
  initialPrompt = '',
  onExit,
}) => {
  const [currentStep, setCurrentStep] = useState<number>(1);
  const [study, setStudy] = useState<Study | null>(null);
  const [selectedGoal, setSelectedGoal] = useState<ResearchGoal>('demand_validation');
  const [promptInput, setPromptInput] = useState(initialPrompt);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [selectedPersonaIds, setSelectedPersonaIds] = useState<string[]>(['per_sarah_01']);
  const [questions, setQuestions] = useState<string[]>([
    'How do you currently handle unexpected expenses or irregular income?',
    'What is the biggest frustration with your existing financial management tools?',
    'If an automated reserve saved 15% from payouts with a 1-tap unlock, what would keep you from using it?',
  ]);
  const [newQuestion, setNewQuestion] = useState('');

  // Live Interview Simulation States
  const [activeInterviewPersonaId, setActiveInterviewPersonaId] = useState<string>('per_sarah_01');
  const [chatMessages, setChatMessages] = useState<ConversationTurn[]>([]);
  const [isSimulating, setIsSimulating] = useState(false);
  const [userInputMessage, setUserInputMessage] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);

  useEffect(() => {
    const initWorkflow = async () => {
      const allPersonas = await api.getPersonas();
      setPersonas(allPersonas);

      if (studyId) {
        const found = await api.getStudyById(studyId);
        if (found) {
          setStudy(found);
          if (found.goal) setSelectedGoal(found.goal);
          if (found.prompt) setPromptInput(found.prompt);
          if (found.persona_ids?.length) setSelectedPersonaIds(found.persona_ids);
          if (found.step) setCurrentStep(found.step);
          return;
        }
      }

      // Create new study draft
      const created = await api.createStudy({
        title: initialPrompt ? initialPrompt.slice(0, 40) + '...' : 'Untitled Study',
        type: initialType,
        goal: selectedGoal,
        prompt: initialPrompt,
        status: 'draft',
        step: 1,
        persona_count: 1,
        persona_ids: ['per_sarah_01'],
      });
      setStudy(created);
    };

    initWorkflow();
  }, [studyId, initialType, initialPrompt]);

  // Load chat messages when entering step 4 (Interviews)
  useEffect(() => {
    if (currentStep === 4) {
      const startInterview = async () => {
        setIsSimulating(true);
        try {
          const conv = await api.startConversation(
            activeInterviewPersonaId,
            study?.prompt || 'User Research Interview'
          );
          setConversationId(conv.id);
          setChatMessages(conv.turns);
        } catch {
          // fallback
        } finally {
          setIsSimulating(false);
        }
      };
      startInterview();
    }
  }, [currentStep, activeInterviewPersonaId]);

  const handleGoalSelect = (goal: ResearchGoal) => {
    setSelectedGoal(goal);
    if (study) {
      api.updateStudy(study.id, { goal });
    }
  };

  const handleSendInterviewMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!userInputMessage.trim() || !conversationId) return;

    const messageText = userInputMessage.trim();
    setUserInputMessage('');
    setIsSimulating(true);

    try {
      const turnResult = await api.sendMessage(conversationId, messageText);
      setChatMessages((prev) => [
        ...prev,
        turnResult.userTurn,
        turnResult.assistantTurn,
      ]);
    } catch {
      // ignore
    } finally {
      setIsSimulating(false);
    }
  };

  const stepsList = [
    { num: 1, label: 'Context' },
    { num: 2, label: 'Personas' },
    { num: 3, label: 'Script' },
    { num: 4, label: 'Interviews' },
    { num: 5, label: 'Report' },
  ];

  const goalsList: {
    id: ResearchGoal;
    icon: React.ReactNode;
    title: string;
    description: string;
  }[] = [
    {
      id: 'demand_validation',
      icon: <Package size={20} color="#F6C878" />,
      title: 'Demand Validation',
      description: 'Test if real buyers want what you\'re planning, before you commit to building.',
    },
    {
      id: 'messaging_positioning',
      icon: <Clock size={20} color="#A855F7" />,
      title: 'Messaging & Positioning',
      description: 'Find the words, claims, and framings that actually move your buyers.',
    },
    {
      id: 'feature_concept_exploration',
      icon: <Lightbulb size={20} color="#10B981" />,
      title: 'Feature & Concept Exploration',
      description: 'Surface user needs and reactions so you know what to build next.',
    },
    {
      id: 'discover_personas',
      icon: <UserCheck size={20} color="#3B82F6" />,
      title: 'Discover Personas',
      description: 'Understand who your users really are, what drives them, and how they decide.',
    },
  ];

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        background: '#080909',
        color: '#FFFFFF',
      }}
    >
      {/* Top Breadcrumb Stepper Header (Screenshot 4) */}
      <header
        style={{
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          padding: '14px 32px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'rgba(8, 9, 9, 0.95)',
          backdropFilter: 'blur(12px)',
          position: 'sticky',
          top: 0,
          zIndex: 30,
        }}
      >
        {/* Stepper Center */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '24px',
            margin: '0 auto',
          }}
        >
          {stepsList.map((st) => {
            const isActive = currentStep === st.num;
            const isPassed = currentStep > st.num;

            return (
              <div
                key={st.num}
                onClick={() => setCurrentStep(st.num)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  cursor: 'pointer',
                  opacity: isActive || isPassed ? 1 : 0.45,
                  transition: 'opacity 0.2s ease',
                }}
              >
                <div
                  style={{
                    width: '18px',
                    height: '18px',
                    borderRadius: '50%',
                    border: isActive
                      ? '2px solid #F6C878'
                      : isPassed
                      ? '2px solid #10B981'
                      : '2px solid #6B7280',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: isPassed ? '#10B981' : 'transparent',
                  }}
                >
                  {isPassed && <CheckCircle2 size={12} color="#080909" strokeWidth={3} />}
                </div>
                <span
                  style={{
                    fontSize: '0.86rem',
                    fontWeight: isActive ? 600 : 400,
                    color: isActive ? '#FFFFFF' : '#9CA3AF',
                  }}
                >
                  {st.label}
                </span>
              </div>
            );
          })}
        </div>

        {/* Exit Button */}
        <button
          type="button"
          onClick={onExit}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#9CA3AF',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '0.84rem',
            cursor: 'pointer',
          }}
        >
          <LogOut size={15} /> Exit
        </button>
      </header>

      {/* Main Content Area */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '36px 24px 120px 24px',
          maxWidth: '860px',
          margin: '0 auto',
          width: '100%',
        }}
      >
        {/* ============================================================
            STEP 1: CONTEXT & GOAL SELECTION (Matches Screenshot 4)
           ============================================================ */}
        {currentStep === 1 && (
          <div style={{ width: '100%' }}>
            {/* Title & Subtitle */}
            <div style={{ textAlign: 'center', marginBottom: '32px' }}>
              <h1
                style={{
                  fontSize: 'clamp(1.75rem, 3vw, 2.25rem)',
                  fontWeight: 500,
                  color: '#FFFFFF',
                  letterSpacing: '-0.02em',
                  margin: '0 0 8px 0',
                }}
              >
                Design your user interviews
              </h1>
              <p style={{ fontSize: '0.92rem', color: '#9CA3AF', margin: 0 }}>
                Pick a common starting point, or tell me what you want to figure out.
              </p>
            </div>

            {/* AI Assistant Message Bubble with Gold 'A' / 'B' avatar badge */}
            <div
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '12px',
                background: 'rgba(255, 255, 255, 0.02)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '16px',
                padding: '16px 20px',
                marginBottom: '28px',
              }}
            >
              <div
                style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '8px',
                  background: 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)',
                  color: '#080909',
                  fontWeight: 700,
                  fontSize: '0.85rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                B
              </div>
              <div style={{ fontSize: '0.9rem', color: '#E5E7EB', lineHeight: 1.5 }}>
                Hello! Excited to help you conduct user research faster. Can you tell us what's your research goal?
              </div>
            </div>

            {/* 4 Research Goal Option Cards (2x2 Grid) */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '14px',
                marginBottom: '36px',
              }}
            >
              {goalsList.map((g) => {
                const isSelected = selectedGoal === g.id;
                return (
                  <div
                    key={g.id}
                    onClick={() => handleGoalSelect(g.id)}
                    style={{
                      background: isSelected
                        ? 'rgba(246, 200, 120, 0.04)'
                        : 'rgba(255, 255, 255, 0.015)',
                      border: isSelected
                        ? '1px solid rgba(246, 200, 120, 0.4)'
                        : '1px solid rgba(255, 255, 255, 0.07)',
                      borderRadius: '14px',
                      padding: '18px 20px',
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = 'rgba(246, 200, 120, 0.35)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = isSelected
                        ? 'rgba(246, 200, 120, 0.4)'
                        : 'rgba(255, 255, 255, 0.07)';
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      {g.icon}
                      <span style={{ fontWeight: 600, fontSize: '0.92rem', color: '#FFFFFF' }}>
                        {g.title}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#8A909A', lineHeight: 1.4 }}>
                      {g.description}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ============================================================
            STEP 2: PERSONAS GROUNDING SELECTION
           ============================================================ */}
        {currentStep === 2 && (
          <div style={{ width: '100%' }}>
            <div style={{ textAlign: 'center', marginBottom: '28px' }}>
              <h2 style={{ fontSize: '1.75rem', fontWeight: 500, margin: '0 0 6px 0' }}>
                Select Synthetic Audience
              </h2>
              <p style={{ fontSize: '0.88rem', color: '#9CA3AF', margin: 0 }}>
                Choose which empirical personas will participate in this research study.
              </p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '32px' }}>
              {personas.map((p) => {
                const isChecked = selectedPersonaIds.includes(p.id);
                return (
                  <div
                    key={p.id}
                    onClick={() => {
                      setSelectedPersonaIds((prev) =>
                        prev.includes(p.id) ? prev.filter((id) => id !== p.id) : [...prev, p.id]
                      );
                    }}
                    style={{
                      background: isChecked ? 'rgba(246, 200, 120, 0.04)' : 'rgba(255, 255, 255, 0.02)',
                      border: isChecked
                        ? '1px solid rgba(246, 200, 120, 0.4)'
                        : '1px solid rgba(255, 255, 255, 0.07)',
                      borderRadius: '14px',
                      padding: '16px 20px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {}}
                        style={{ accentColor: '#F6C878', cursor: 'pointer' }}
                      />
                      <div>
                        <div style={{ fontWeight: 600, fontSize: '0.95rem', color: '#FFFFFF' }}>
                          {p.name}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: '#9CA3AF' }}>
                          {p.archetype} • {p.demographics.occupation}
                        </div>
                      </div>
                    </div>
                    <div
                      style={{
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        color: '#10B981',
                        background: 'rgba(16, 185, 129, 0.1)',
                        padding: '2px 8px',
                        borderRadius: '6px',
                      }}
                    >
                      {Math.round(p.grounding_ratio * 100)}% Grounded
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ============================================================
            STEP 3: INTERVIEW SCRIPT & QUESTIONS
           ============================================================ */}
        {currentStep === 3 && (
          <div style={{ width: '100%' }}>
            <div style={{ textAlign: 'center', marginBottom: '28px' }}>
              <h2 style={{ fontSize: '1.75rem', fontWeight: 500, margin: '0 0 6px 0' }}>
                Interview Script & Probing Rules
              </h2>
              <p style={{ fontSize: '0.88rem', color: '#9CA3AF', margin: 0 }}>
                Review and customize the core questions the AI interviewer will ask.
              </p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '24px' }}>
              {questions.map((q, idx) => (
                <div
                  key={idx}
                  style={{
                    background: 'rgba(255, 255, 255, 0.02)',
                    border: '1px solid rgba(255, 255, 255, 0.07)',
                    borderRadius: '12px',
                    padding: '14px 18px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                  }}
                >
                  <span style={{ color: '#F6C878', fontWeight: 700, fontSize: '0.85rem' }}>
                    Q{idx + 1}
                  </span>
                  <span style={{ flex: 1, fontSize: '0.88rem', color: '#FFFFFF' }}>{q}</span>
                </div>
              ))}
            </div>

            {/* Add Question input */}
            <div style={{ display: 'flex', gap: '10px' }}>
              <input
                type="text"
                value={newQuestion}
                onChange={(e) => setNewQuestion(e.target.value)}
                placeholder="Add another interview question..."
                style={{
                  flex: 1,
                  background: 'rgba(255, 255, 255, 0.03)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '10px',
                  padding: '10px 14px',
                  color: '#FFFFFF',
                  fontSize: '0.88rem',
                  outline: 'none',
                }}
              />
              <button
                type="button"
                onClick={() => {
                  if (newQuestion.trim()) {
                    setQuestions((prev) => [...prev, newQuestion.trim()]);
                    setNewQuestion('');
                  }
                }}
                style={{
                  background: 'rgba(246, 200, 120, 0.15)',
                  border: '1px solid rgba(246, 200, 120, 0.3)',
                  color: '#F6C878',
                  borderRadius: '10px',
                  padding: '0 16px',
                  fontWeight: 600,
                  fontSize: '0.84rem',
                  cursor: 'pointer',
                }}
              >
                Add
              </button>
            </div>
          </div>
        )}

        {/* ============================================================
            STEP 4: LIVE SYNTHETIC INTERVIEWS SIMULATION
           ============================================================ */}
        {currentStep === 4 && (
          <div style={{ width: '100%' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: '20px',
              }}
            >
              <div>
                <h2 style={{ fontSize: '1.4rem', fontWeight: 600, margin: '0 0 4px 0' }}>
                  Live Persona Interview Simulation
                </h2>
                <div style={{ fontSize: '0.82rem', color: '#9CA3AF' }}>
                  Multi-turn conversation grounded in memory stream & FreeLLMpool routes
                </div>
              </div>

              {/* Persona Selector Pill */}
              <div style={{ display: 'flex', gap: '8px' }}>
                {personas.slice(0, 3).map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setActiveInterviewPersonaId(p.id)}
                    style={{
                      background:
                        activeInterviewPersonaId === p.id
                          ? 'rgba(246, 200, 120, 0.15)'
                          : 'rgba(255, 255, 255, 0.03)',
                      border:
                        activeInterviewPersonaId === p.id
                          ? '1px solid rgba(246, 200, 120, 0.4)'
                          : '1px solid rgba(255, 255, 255, 0.08)',
                      color: activeInterviewPersonaId === p.id ? '#F6C878' : '#9CA3AF',
                      padding: '4px 10px',
                      borderRadius: '8px',
                      fontSize: '0.78rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    {p.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Chat Transcript Area */}
            <div
              style={{
                background: 'rgba(255, 255, 255, 0.015)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '16px',
                padding: '24px',
                minHeight: '380px',
                maxHeight: '480px',
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
                gap: '16px',
                marginBottom: '16px',
              }}
            >
              {chatMessages.map((msg, idx) => {
                const isUser = msg.role === 'user';
                return (
                  <div
                    key={msg.id || idx}
                    style={{
                      alignSelf: isUser ? 'flex-end' : 'flex-start',
                      maxWidth: '82%',
                      background: isUser
                        ? 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)'
                        : 'rgba(255, 255, 255, 0.04)',
                      color: isUser ? '#080909' : '#FFFFFF',
                      padding: '14px 18px',
                      borderRadius: isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                      border: isUser ? 'none' : '1px solid rgba(255, 255, 255, 0.08)',
                      boxShadow: '0 4px 12px rgba(0, 0, 0, 0.2)',
                    }}
                  >
                    <div style={{ fontSize: '0.9rem', lineHeight: 1.5 }}>{msg.content}</div>

                    {!isUser && msg.served_by && (
                      <div
                        style={{
                          marginTop: '8px',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          fontSize: '0.72rem',
                          color: '#F6C878',
                          opacity: 0.85,
                        }}
                      >
                        <Zap size={11} />
                        <span>Served by {msg.served_by}</span>
                        {msg.latency_ms && <span>• {Math.round(msg.latency_ms)}ms</span>}
                      </div>
                    )}
                  </div>
                );
              })}

              {isSimulating && (
                <div
                  style={{
                    alignSelf: 'flex-start',
                    background: 'rgba(255, 255, 255, 0.03)',
                    padding: '12px 16px',
                    borderRadius: '12px',
                    color: '#9CA3AF',
                    fontSize: '0.84rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <Sparkles size={14} color="#F6C878" />
                  Generating grounded synthetic response...
                </div>
              )}
            </div>

            {/* Prompt input for live interview turn */}
            <form
              onSubmit={handleSendInterviewMessage}
              style={{
                display: 'flex',
                gap: '10px',
              }}
            >
              <input
                type="text"
                value={userInputMessage}
                onChange={(e) => setUserInputMessage(e.target.value)}
                placeholder="Ask Sarah Chen a follow-up interview question..."
                style={{
                  flex: 1,
                  background: 'rgba(255, 255, 255, 0.04)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '12px',
                  padding: '12px 18px',
                  color: '#FFFFFF',
                  fontSize: '0.88rem',
                  outline: 'none',
                }}
              />
              <button
                type="submit"
                disabled={isSimulating || !userInputMessage.trim()}
                style={{
                  background: 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)',
                  border: 'none',
                  color: '#080909',
                  borderRadius: '12px',
                  padding: '0 20px',
                  fontWeight: 600,
                  cursor: isSimulating || !userInputMessage.trim() ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Send size={16} />
              </button>
            </form>
          </div>
        )}

        {/* ============================================================
            STEP 5: RESEARCH REPORT & SYNTHESIS
           ============================================================ */}
        {currentStep === 5 && (
          <div style={{ width: '100%' }}>
            {/* Header & Export Actions */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '16px',
                marginBottom: '28px',
              }}
            >
              <div>
                <span
                  style={{
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    padding: '3px 8px',
                    borderRadius: '6px',
                    background: 'rgba(16, 185, 129, 0.12)',
                    color: '#10B981',
                    border: '1px solid rgba(16, 185, 129, 0.25)',
                  }}
                >
                  Decision Report Ready
                </span>
                <h2 style={{ fontSize: '1.8rem', fontWeight: 600, margin: '8px 0 4px 0' }}>
                  {study?.title || 'Brand Messaging & Demand Report'}
                </h2>
                <div style={{ fontSize: '0.84rem', color: '#9CA3AF' }}>
                  Synthesized from 9 grounded synthetic interviews across 3 personas
                </div>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => alert('Report copied to clipboard in markdown format!')}
                  style={{
                    background: 'rgba(255, 255, 255, 0.05)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    color: '#FFFFFF',
                    borderRadius: '8px',
                    padding: '8px 14px',
                    fontSize: '0.82rem',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <Share2 size={14} /> Share
                </button>
                <button
                  type="button"
                  onClick={() => alert('Exporting PDF synthesis report...')}
                  style={{
                    background: 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)',
                    border: 'none',
                    color: '#080909',
                    borderRadius: '8px',
                    padding: '8px 16px',
                    fontSize: '0.82rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <Download size={14} /> Export Report
                </button>
              </div>
            </div>

            {/* Metrics cards */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                gap: '16px',
                marginBottom: '28px',
              }}
            >
              <div
                style={{
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '14px',
                  padding: '18px 20px',
                }}
              >
                <div style={{ fontSize: '0.78rem', color: '#9CA3AF' }}>Demand Signal</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#10B981', marginTop: '4px' }}>
                  High (88%)
                </div>
              </div>

              <div
                style={{
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '14px',
                  padding: '18px 20px',
                }}
              >
                <div style={{ fontSize: '0.78rem', color: '#9CA3AF' }}>Evidence Consistency</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#F6C878', marginTop: '4px' }}>
                  96.4%
                </div>
              </div>

              <div
                style={{
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '14px',
                  padding: '18px 20px',
                }}
              >
                <div style={{ fontSize: '0.78rem', color: '#9CA3AF' }}>API Cost</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#FFFFFF', marginTop: '4px' }}>
                  $0.00
                </div>
              </div>
            </div>

            {/* Executive Summary Card */}
            <div
              style={{
                background: 'rgba(255, 255, 255, 0.02)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '16px',
                padding: '24px',
                marginBottom: '24px',
              }}
            >
              <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: '#F6C878', margin: '0 0 12px 0' }}>
                Executive Summary
              </h3>
              <p style={{ fontSize: '0.9rem', color: '#E5E7EB', lineHeight: 1.6, margin: 0 }}>
                {study?.report?.executive_summary ||
                  'Across 9 evidence-grounded synthetic interviews, 88% of target personas expressed immediate buying intent when the value proposition centered on zero-risk speed and concrete decision evidence rather than generic AI simulation.'}
              </p>
            </div>

            {/* Key Findings List */}
            <div
              style={{
                background: 'rgba(255, 255, 255, 0.02)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '16px',
                padding: '24px',
                marginBottom: '24px',
              }}
            >
              <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: '#FFFFFF', margin: '0 0 14px 0' }}>
                Key Findings
              </h3>
              <ul style={{ margin: 0, paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {(
                  study?.report?.key_findings || [
                    'Lead message "Cut 3-Week User Research to 10 Minutes with Evidence Grounding" generated 3.2x higher intent score.',
                    'Technical personas demanded visible provenance records and retrieval source inspection before adopting.',
                    'Pricing transparency and 1-tap emergency unlocks were non-negotiable trust criteria across all demographics.',
                  ]
                ).map((kf, i) => (
                  <li key={i} style={{ fontSize: '0.88rem', color: '#D1D5DB', lineHeight: 1.5 }}>
                    {kf}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>

      {/* Fixed Bottom Action / Chat Bar (Matches Screenshot 4) */}
      {currentStep < 5 && (
        <div
          style={{
            position: 'fixed',
            bottom: 0,
            left: 0,
            right: 0,
            background: 'rgba(8, 9, 9, 0.96)',
            backdropFilter: 'blur(16px)',
            borderTop: '1px solid rgba(255, 255, 255, 0.08)',
            padding: '16px 24px',
            zIndex: 20,
            display: 'flex',
            justifyContent: 'center',
          }}
        >
          <div
            style={{
              width: '100%',
              maxWidth: '860px',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
            {/* Status Pill Badge */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  background: 'rgba(16, 185, 129, 0.1)',
                  border: '1px solid rgba(16, 185, 129, 0.25)',
                  borderRadius: '20px',
                  padding: '4px 12px',
                  fontSize: '0.76rem',
                  color: '#10B981',
                }}
              >
                <Users size={13} />
                <span style={{ fontWeight: 600 }}>User Interviews</span>
                <span style={{ opacity: 0.6 }}>•</span>
                <span>Ready - Modelled buyers • Same-day results</span>
              </div>

              {/* Navigation button */}
              <button
                type="button"
                onClick={() => setCurrentStep((prev) => Math.min(prev + 1, 5))}
                style={{
                  background: 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)',
                  border: 'none',
                  color: '#080909',
                  borderRadius: '10px',
                  padding: '7px 18px',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <span>Continue to {stepsList[currentStep]?.label || 'Report'}</span>
                <ArrowRight size={14} />
              </button>
            </div>

            {/* Prompt input field */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                background: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(255, 255, 255, 0.09)',
                borderRadius: '14px',
                padding: '10px 16px',
              }}
            >
              <button
                type="button"
                aria-label="Attach file or context"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#6B7280',
                  cursor: 'pointer',
                  padding: 0,
                  display: 'flex',
                  alignItems: 'center',
                }}
              >
                <Paperclip size={16} />
              </button>

              <input
                type="text"
                value={promptInput}
                onChange={(e) => setPromptInput(e.target.value)}
                placeholder="Type here..."
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    setCurrentStep((prev) => Math.min(prev + 1, 5));
                  }
                }}
                style={{
                  flex: 1,
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  color: '#FFFFFF',
                  fontSize: '0.88rem',
                }}
              />

              <button
                type="button"
                onClick={() => setCurrentStep((prev) => Math.min(prev + 1, 5))}
                aria-label="Send prompt"
                style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '50%',
                  background: promptInput.trim()
                    ? '#F6C878'
                    : 'rgba(255, 255, 255, 0.08)',
                  color: promptInput.trim() ? '#080909' : '#6B7280',
                  border: 'none',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                }}
              >
                <ArrowUp size={15} strokeWidth={2.5} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
