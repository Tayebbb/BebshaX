import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowRight,
  Sparkles,
  Package,
  Lightbulb,
  UserCheck,
  Paperclip,
  ArrowUp,
  LogOut,
  CheckCircle2,
  Check,
  Send,
  Zap,
  Download,
  Share2,
  Bookmark,
  Plus,
  Trash2,
  Info,
  Search,
  X,
  RefreshCw,
} from 'lucide-react';
import { Study, ResearchGoal, StudyType, Persona, ConversationTurn, PersonaRoleSuggestion } from '../../../types';
import { api } from '../../../services/api';

interface StudyWorkflowViewProps {
  studyId?: string;
  initialStep?: number;
  initialType?: StudyType;
  initialPrompt?: string;
  onExit: () => void;
  onStepChange?: (step: number) => void;
}

const DEFAULT_STUDENT_ROLES: PersonaRoleSuggestion[] = [
  {
    id: 'role_uni_student',
    role: 'UNIVERSITY STUDENT',
    description: 'Directly represents the primary target user for a study planner AI website in Bangladesh and can provide first-hand feedback on demand and pricing sensitivity.',
    count: 3,
    selected: true,
  },
  {
    id: 'role_college_applicant',
    role: 'COLLEGE APPLICANT',
    description: 'Actively preparing for university entrance exams, this group faces unique planning pressures and can reveal willingness to pay for tools that support their study goals.',
    count: 3,
    selected: true,
  },
  {
    id: 'role_high_schooler',
    role: 'BUSY HIGH SCHOOLER',
    description: 'Juggling heavy academic loads and extracurriculars, these students offer insight into daily pain points and real value perception for time management tools at a student-friendly price.',
    count: 3,
    selected: true,
  },
  {
    id: 'role_private_tutor_student',
    role: 'PRIVATE TUTOR STUDENT',
    description: 'Engaged in additional study support, this profile can comment on the need for supplementary planning aids and evaluate if 250 taka/month fits their budget for academic resources.',
    count: 0,
    selected: false,
  },
  {
    id: 'role_parental_planner',
    role: 'PARENTAL PLANNER',
    description: 'Represents parents who guide or organize their children\'s study schedules and may influence or directly pay for educational tools, providing insights on family budgeting and value.',
    count: 0,
    selected: false,
  },
  {
    id: 'role_test_prep',
    role: 'TEST PREP SEEKER',
    description: 'Focused on standardized or competitive exams, these students are motivated by performance improvement and may see more value in specialized AI planning, informing demand and price limits.',
    count: 0,
    selected: false,
  },
  {
    id: 'role_scholarship_aspirant',
    role: 'SCHOLARSHIP ASPIRANT',
    description: 'Highly goal-oriented, these students need detailed, efficient study plans and can indicate whether pricing aligns with their need for academic support.',
    count: 0,
    selected: false,
  },
  {
    id: 'role_budget_learner',
    role: 'BUDGET-CONSCIOUS LEARNER',
    description: 'Represents students highly sensitive to price, who will help test the floor of acceptable monthly costs and highlight trade-offs between features and affordability.',
    count: 0,
    selected: false,
  },
  {
    id: 'role_remote_student',
    role: 'REMOTE STUDENT',
    description: 'Studying from rural areas or at a distance, these users may have different access patterns and willingness to invest in digital tools, offering a contrast to urban peers.',
    count: 0,
    selected: false,
  },
  {
    id: 'role_group_organizer',
    role: 'STUDY GROUP ORGANIZER',
    description: 'Manages schedules for collective learning, providing perspective on group adoption, potential for shared subscriptions, and broader acceptance of proposed pricing.',
    count: 0,
    selected: false,
  },
];

export const StudyWorkflowView: React.FC<StudyWorkflowViewProps> = ({
  studyId,
  initialStep = 1,
  initialType = 'interviews',
  initialPrompt = '',
  onExit,
  onStepChange,
}) => {
  const [currentStep, setCurrentStep] = useState<number>(initialStep);
  const [study, setStudy] = useState<Study | null>(null);
  const [selectedGoal, setSelectedGoal] = useState<string>('demand');
  const [promptInput, setPromptInput] = useState<string>(initialPrompt);
  const [questions, setQuestions] = useState<string[]>([
    'How do you currently structure your weekly schedule and daily priorities?',
    'What is your biggest frustration or source of anxiety with existing academic tools?',
    'Would you pay 250 BDT/month for an intelligent study planner that adapts to your exam timetable?',
    'What features would make this an indispensable daily habit rather than just another app?',
  ]);
  const [newQuestion, setNewQuestion] = useState<string>('');
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [selectedPersonaIds, setSelectedPersonaIds] = useState<string[]>([]);
  const [selectedRoleFilter, setSelectedRoleFilter] = useState<string>('all');
  const [isGeneratingPersonas, setIsGeneratingPersonas] = useState<boolean>(false);
  const [generationProgress, setGenerationProgress] = useState<number>(0);
  const [viewingPersona, setViewingPersona] = useState<Persona | null>(null);
  const [showDidYouKnow, setShowDidYouKnow] = useState<boolean>(true);
  const [savedAudiences, setSavedAudiences] = useState<string[]>([]);

  // Copilot Multi-turn Conversational States (Step 1)
  const [copilotMessages, setCopilotMessages] = useState<
    {
      id: string;
      role: 'user' | 'assistant';
      content: string;
      timestamp?: string;
      isGoalCard?: boolean;
      goalCardData?: {
        title: string;
        summary: string;
        target_audience: string;
        core_hypothesis: string;
      };
    }[]
  >([]);
  const [isCopilotTyping, setIsCopilotTyping] = useState<boolean>(false);
  const [step1Prompt, setStep1Prompt] = useState<string>('');
  const [showRoleSelection, setShowRoleSelection] = useState<boolean>(false);
  const [suggestedRoles, setSuggestedRoles] = useState<PersonaRoleSuggestion[]>(DEFAULT_STUDENT_ROLES);

  // Live Interview Simulation States (Step 4)
  const [activeInterviewPersonaId, setActiveInterviewPersonaId] = useState<string>('per_sarah_01');
  const [chatMessages, setChatMessages] = useState<ConversationTurn[]>([]);
  const [isSimulating, setIsSimulating] = useState(false);
  const [userInputMessage, setUserInputMessage] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);

  const handleStepChange = (newStep: number) => {
    const clamped = Math.max(1, Math.min(newStep, 5));
    setCurrentStep(clamped);
    onStepChange?.(clamped);
    if (studyId) {
      api.updateStudy(studyId, {
        step: clamped,
        status: clamped === 5 ? 'completed' : 'in_progress',
        prompt: promptInput || study?.prompt,
        copilot_messages: copilotMessagesRef.current as any,
        suggested_roles: suggestedRoles,
        personas_data: personas as any,
        persona_count: personas.length,
        persona_ids: personas.map((p) => p.id),
        script_questions: questions,
      }).catch(() => {});
    }
  };

  // Synchronization refs to eliminate any duplicate assistant turns
  const isFetchingCopilotRef = useRef<boolean>(false);
  const pendingHistoryRef = useRef<{ role: 'user' | 'assistant'; content: string }[] | null>(null);
  const initialPromptHandledRef = useRef<string | null>(null);
  const copilotMessagesRef = useRef<CopilotMessage[]>([]);

  useEffect(() => {
    copilotMessagesRef.current = copilotMessages;
  }, [copilotMessages]);

  // Restore full study state from DB when loading an existing study
  useEffect(() => {
    if (!studyId) return;
    api.getStudy(studyId).then((s) => {
      if (!s) return;
      setStudy(s);
      if (s.prompt && !promptInput) setPromptInput(s.prompt);
      if (!initialPrompt && s.copilot_messages && s.copilot_messages.length > 0 && copilotMessages.length === 0) {
        // Ensure each message has a unique id
        const restored = s.copilot_messages.map((m: any, i: number) => ({
          ...m,
          id: m.id || `msg_restored_${i}_${Date.now()}`,
        }));
        setCopilotMessages(restored);
        copilotMessagesRef.current = restored;
      }
      if (s.suggested_roles && s.suggested_roles.length > 0) {
        setSuggestedRoles(s.suggested_roles);
      }
      if (s.script_questions && s.script_questions.length > 0) {
        setQuestions(s.script_questions);
      }
      if (s.personas_data && s.personas_data.length > 0) {
        setPersonas(s.personas_data as any);
        const firstId = (s.personas_data[0] as any)?.id;
        if (firstId) setActiveInterviewPersonaId(firstId);
        setSelectedPersonaIds((s.personas_data as any[]).map((p: any) => p.id));
      }
    }).catch(() => { /* best-effort: start fresh if load fails */ });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studyId]);

  const fetchCopilotTurn = async (history: { role: 'user' | 'assistant'; content: string }[]) => {
    if (isFetchingCopilotRef.current) {
      pendingHistoryRef.current = history;
      return;
    }
    isFetchingCopilotRef.current = true;
    setIsCopilotTyping(true);
    try {
      const res = await api.sendStudyCopilotMessage(history, initialType, studyId);
      const assistantMsg = {
        id: `msg_a_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
        role: 'assistant' as const,
        content: res.reply,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
        isGoalCard: res.is_ready_for_approval && !!res.research_goal_card,
        goalCardData: res.research_goal_card || undefined,
      };

      setCopilotMessages((prev) => {
        const lastMsg = prev[prev.length - 1];
        if (lastMsg && lastMsg.role === 'assistant' && lastMsg.content.trim() === assistantMsg.content.trim()) {
          return prev;
        }
        const updated = [...prev, assistantMsg];
        copilotMessagesRef.current = updated;
        return updated;
      });

      if (res.suggested_roles && res.suggested_roles.length > 0) {
        setSuggestedRoles(res.suggested_roles);
      }
    } catch {
      // Guaranteed fallback: create helpful assistant turn with approval card so the user is never stuck
      const userTurns = history.filter((m) => m.role === 'user');
      const latestUserPrompt = userTurns[userTurns.length - 1]?.content || 'Product Study';
      const fallbackMsg = {
        id: `msg_a_${Date.now()}`,
        role: 'assistant' as const,
        content: `Understood! I've synthesized your research objective for "${latestUserPrompt}". User Interviews will validate customer interest, price sensitivity, and willingness to pay.`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
        isGoalCard: true,
        goalCardData: {
          title: 'RESEARCH GOAL',
          summary: `Validate demand, pricing sensitivity, and willingness to pay for "${latestUserPrompt}". Does this capture what you're looking for?`,
          target_audience: 'Target customers and price-sensitive shoppers',
          core_hypothesis: 'Strong product-market fit and willingness to pay',
        },
      };
      setCopilotMessages((prev) => {
        const updated = [...prev, fallbackMsg];
        copilotMessagesRef.current = updated;
        return updated;
      });
    } finally {
      setIsCopilotTyping(false);
      isFetchingCopilotRef.current = false;
      if (pendingHistoryRef.current) {
        const queued = pendingHistoryRef.current;
        pendingHistoryRef.current = null;
        fetchCopilotTurn(queued);
      }
    }
  };

  const handleSendCopilotMessage = (text?: string) => {
    const inputEl = document.querySelector('input[placeholder*="Type here"]') as HTMLInputElement | null;
    const domValue = inputEl?.value || '';
    const messageToSend = (
      typeof text === 'string' && text.trim() ? text : step1Prompt || promptInput || domValue
    ).trim();
    if (!messageToSend) return;

    setStep1Prompt('');
    setPromptInput('');
    if (inputEl) inputEl.value = '';

    if (studyId) {
      api.updateStudy(studyId, { prompt: messageToSend }).catch(() => {});
    }

    const userMsg: CopilotMessage = {
      id: `msg_u_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      role: 'user' as const,
      content: messageToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
    };

    const currentList = copilotMessagesRef.current;
    const updatedMessages = [...currentList, userMsg];
    copilotMessagesRef.current = updatedMessages;
    setCopilotMessages(updatedMessages);

    const newHistory = updatedMessages.map((m) => ({ role: m.role, content: m.content }));
    fetchCopilotTurn(newHistory);
  };

  const handleSendInterviewMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = userInputMessage.trim();
    if (!text || isSimulating) return;

    setUserInputMessage('');
    const userTurn: ConversationTurn = {
      id: `turn_u_${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
    };
    setChatMessages((prev) => [...prev, userTurn]);
    setIsSimulating(true);

    try {
      if (conversationId) {
        const res = await api.sendMessage(conversationId, text);
        setChatMessages((prev) => [...prev, res.assistantTurn]);
      } else {
        const conv = await api.startConversation(activeInterviewPersonaId, study?.prompt || 'User Research Interview');
        setConversationId(conv.id);
        const res = await api.sendMessage(conv.id, text);
        setChatMessages((prev) => [...prev, res.assistantTurn]);
      }
    } catch {
      // fallback
    } finally {
      setIsSimulating(false);
    }
  };

  const handleApproveGoal = async (summary?: string) => {
    setShowRoleSelection(true);
    const activePrompt =
      summary ||
      [...copilotMessages].reverse().find((m) => m.role === 'user')?.content ||
      promptInput ||
      study?.prompt ||
      'Product Research Study';

    try {
      const roles = await api.getSuggestedPersonaRoles(activePrompt);
      if (roles && roles.length > 0) {
        setSuggestedRoles(roles);
      }
    } catch {
      // ignore
    }

    if (study) {
      try {
        api.updateStudy(study.id, {
          prompt: activePrompt,
        });
      } catch {
        // ignore
      }
    }
  };

  const handleToggleRole = (roleId: string) => {
    setSuggestedRoles((prev) =>
      prev.map((r) => {
        if (r.id === roleId) {
          const willBeSelected = !r.selected;
          return {
            ...r,
            selected: willBeSelected,
            count: willBeSelected ? (r.count > 0 ? r.count : 3) : 0,
          };
        }
        return r;
      })
    );
  };

  const handleIncrementRole = (roleId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSuggestedRoles((prev) =>
      prev.map((r) => {
        if (r.id === roleId) {
          const nextCount = r.count + 1;
          return {
            ...r,
            count: nextCount,
            selected: true,
          };
        }
        return r;
      })
    );
  };

  const handleDecrementRole = (roleId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSuggestedRoles((prev) =>
      prev.map((r) => {
        if (r.id === roleId) {
          const nextCount = Math.max(0, r.count - 1);
          return {
            ...r,
            count: nextCount,
            selected: nextCount > 0,
          };
        }
        return r;
      })
    );
  };

  const handleGeneratePersonas = async () => {
    setIsGeneratingPersonas(true);
    setGenerationProgress(15);
    handleStepChange(2);

    const activeRoles = suggestedRoles.filter((r) => r.selected && r.count > 0);
    const totalCount = activeRoles.reduce((sum, r) => sum + r.count, 0) || 10;

    const allUserTexts = copilotMessagesRef.current
      .filter((m) => m.role === 'user')
      .map((m) => m.content)
      .join(' ');

    const userPrompt =
      allUserTexts ||
      promptInput ||
      study?.prompt ||
      'Product Research Study';

    const studyTitle =
      study?.title && study.title !== 'Untitled Study'
        ? study.title
        : userPrompt.length > 50
        ? userPrompt.slice(0, 50) + '...'
        : userPrompt;

    // Fast animated generation sequence
    const progressInterval = setInterval(() => {
      setGenerationProgress((prev) => {
        if (prev >= 85) {
          clearInterval(progressInterval);
          return 85;
        }
        return prev + 25;
      });
    }, 180);

    try {
      const generated = await api.generateStudyPersonas(
        study?.id || studyId,
        userPrompt,
        suggestedRoles,
        studyTitle
      );

      setTimeout(() => {
        clearInterval(progressInterval);
        setGenerationProgress(100);
        setPersonas(generated);
        setSelectedPersonaIds(generated.map((p) => p.id));
        if (generated[0]) setActiveInterviewPersonaId(generated[0].id);
        setIsGeneratingPersonas(false);

        if (study) {
          api.updateStudy(study.id, {
            title: studyTitle,
            prompt: userPrompt,
            persona_count: generated.length || totalCount,
            persona_ids: generated.map((p) => p.id),
            personas_data: generated as any,
            step: 2,
          });
        }
      }, 650);
    } catch {
      clearInterval(progressInterval);
      setIsGeneratingPersonas(false);
    }
  };

  const handleRoleCountChangeInStep2 = (roleId: string, delta: number) => {
    setSuggestedRoles((prev) =>
      prev.map((r) => {
        if (r.id === roleId) {
          const nextCount = Math.max(0, r.count + delta);
          return {
            ...r,
            count: nextCount,
            selected: nextCount > 0,
          };
        }
        return r;
      })
    );
  };

  const handleRemovePersona = (personaId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setPersonas((prev) => prev.filter((p) => p.id !== personaId));
    setSelectedPersonaIds((prev) => prev.filter((id) => id !== personaId));
  };

  const handleClonePersona = (persona: Persona, e: React.MouseEvent) => {
    e.stopPropagation();
    const cloned: Persona = {
      ...persona,
      id: `${persona.id}_clone_${Date.now()}`,
      name: `${persona.name} (Copy)`,
    };
    setPersonas((prev) => [...prev, cloned]);
    setSelectedPersonaIds((prev) => [...prev, cloned.id]);
  };

  useEffect(() => {
    if (initialStep && initialStep !== currentStep) {
      setCurrentStep(initialStep);
    }
  }, [initialStep]);

  useEffect(() => {
    if (initialPrompt && initialPrompt.trim() && initialPromptHandledRef.current !== initialPrompt.trim()) {
      initialPromptHandledRef.current = initialPrompt.trim();
      const userMsg = {
        id: `msg_u_${Date.now()}`,
        role: 'user' as const,
        content: initialPrompt.trim(),
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
      };
      setCopilotMessages([userMsg]);
      fetchCopilotTurn([{ role: 'user', content: initialPrompt.trim() }]);
    }
  }, [initialPrompt]);

  useEffect(() => {
    if (studyId) {
      api.getStudy(studyId).then((data) => {
        if (data) {
          setStudy(data);
          if (data.prompt) setPromptInput(data.prompt);
          if (data.goal) setSelectedGoal(data.goal);
          if (data.step && !initialStep) setCurrentStep(data.step);
          if (data.copilot_messages && data.copilot_messages.length > 0 && copilotMessagesRef.current.length === 0) {
            setCopilotMessages(
              data.copilot_messages.map((m: any, idx: number) => ({
                id: m.id || `msg_loaded_${idx}`,
                role: m.role,
                content: m.text || m.content || '',
                timestamp: m.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
                isGoalCard: !!m.isGoalCard,
                goalCardData: m.goalCardData,
              }))
            );
          }
          if (data.suggested_roles && data.suggested_roles.length > 0) {
            setSuggestedRoles(data.suggested_roles);
          }
          if (data.personas_data && data.personas_data.length > 0) {
            setPersonas(data.personas_data);
            setSelectedPersonaIds(data.personas_data.map((p: any) => p.id));
          }
          if (data.script_questions && data.script_questions.length > 0) {
            setQuestions(data.script_questions);
          }
        }
      });
    }
  }, [studyId]);

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

  const goalsList: { id: ResearchGoal; title: string; description: string; icon: React.ReactNode }[] = [
    {
      id: 'demand_validation',
      title: 'Demand & WTP Validation',
      description: 'Test willingness to pay, budget ceilings, and core value perception.',
      icon: <Zap size={18} color="#F6C878" />,
    },
    {
      id: 'messaging_positioning',
      title: 'Messaging & Pitch Testing',
      description: 'Determine which headline, hook, or value proposition converts highest.',
      icon: <Sparkles size={18} color="#60A5FA" />,
    },
    {
      id: 'feature_concept_exploration',
      title: 'Feature & UX Concept Testing',
      description: 'Probe usability friction, objections, and dealbreakers before code.',
      icon: <Package size={18} color="#A78BFA" />,
    },
    {
      id: 'discover_personas',
      title: 'Audience Discovery',
      description: 'Uncover unexpected buyer archetypes, motivations, and hidden objections.',
      icon: <UserCheck size={18} color="#34D399" />,
    },
  ];

  const handleGoalSelect = (goalId: ResearchGoal) => {
    setSelectedGoal(goalId);
    if (study) {
      api.updateStudy(study.id, { goal: goalId });
    }
  };

  const stepsList = [
    { num: 1, label: 'Context' },
    { num: 2, label: 'Personas' },
    { num: 3, label: 'Script' },
    { num: 4, label: 'Interviews' },
    { num: 5, label: 'Report' },
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
      {/* Header Stepper Navigation (Matches Reference Design) */}
      <header
        style={{
          border: 'none',
          outline: 'none',
          padding: '14px 32px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'rgba(8, 9, 9, 0.95)',
          position: 'sticky',
          top: 0,
          zIndex: 30,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '24px', margin: '0 auto' }}>
          {stepsList.map((st) => {
            const isActive = currentStep === st.num;
            const isPassed = currentStep > st.num;
            return (
              <div
                key={st.num}
                onClick={() => handleStepChange(st.num)}
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
          padding: currentStep === 2 ? '28px 32px 140px 32px' : '36px 24px 120px 24px',
          maxWidth: currentStep === 2 ? '1440px' : '980px',
          margin: '0 auto',
          width: '100%',
        }}
      >
        {/* ============================================================
            STEP 1: CONTEXT & COPILOT CHAT STREAM OR ROLE SELECTION
           ============================================================ */}
        {currentStep === 1 && (
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {showRoleSelection ? (
              /* ============================================================
                 SUGGESTED ROLES FOR YOUR STUDY (Matches Reference Screenshots)
                 ============================================================ */
              <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <UserCheck size={17} color="#9CA3AF" />
                  <span
                    style={{
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      letterSpacing: '0.08em',
                      color: '#9CA3AF',
                      textTransform: 'uppercase',
                    }}
                  >
                    SUGGESTED ROLES FOR YOUR STUDY
                  </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', width: '100%' }}>
                  {suggestedRoles.map((roleItem) => {
                    const isSelected = roleItem.selected || roleItem.count > 0;
                    return (
                      <div
                        key={roleItem.id}
                        onClick={() => handleToggleRole(roleItem.id)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '20px',
                          background: isSelected ? 'rgba(246, 200, 120, 0.025)' : 'rgba(255, 255, 255, 0.01)',
                          border: isSelected ? '1px solid rgba(246, 200, 120, 0.5)' : '1px solid rgba(255, 255, 255, 0.07)',
                          borderRadius: '12px',
                          padding: '16px 20px',
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        {/* Left: Checkbox + Title */}
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '14px',
                            minWidth: '220px',
                            maxWidth: '240px',
                            flexShrink: 0,
                          }}
                        >
                          <div
                            style={{
                              width: '18px',
                              height: '18px',
                              borderRadius: '4px',
                              background: isSelected ? '#F6C878' : 'transparent',
                              border: isSelected ? '1px solid #F6C878' : '1px solid rgba(255, 255, 255, 0.25)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              flexShrink: 0,
                              transition: 'all 0.15s ease',
                            }}
                          >
                            {isSelected && <Check size={12} color="#080909" strokeWidth={3} />}
                          </div>
                          <span
                            style={{
                              fontSize: '0.86rem',
                              fontWeight: 700,
                              color: isSelected ? '#F6C878' : '#FFFFFF',
                              letterSpacing: '0.04em',
                              textTransform: 'uppercase',
                              lineHeight: 1.3,
                            }}
                          >
                            {roleItem.role}
                          </span>
                        </div>

                        {/* Middle: Description */}
                        <div
                          style={{
                            flex: 1,
                            fontSize: '0.82rem',
                            color: '#9CA3AF',
                            lineHeight: 1.45,
                          }}
                        >
                          {roleItem.description}
                        </div>

                        {/* Right: Quantity Stepper */}
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '12px',
                            flexShrink: 0,
                            paddingLeft: '18px',
                            borderLeft: '1px solid rgba(255, 255, 255, 0.08)',
                          }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            type="button"
                            onClick={(e) => handleDecrementRole(roleItem.id, e)}
                            aria-label={`Decrease ${roleItem.role} count`}
                            style={{
                              background: 'transparent',
                              border: 'none',
                              color: isSelected ? '#FFFFFF' : '#6B7280',
                              fontSize: '1.1rem',
                              fontWeight: 600,
                              cursor: 'pointer',
                              width: '24px',
                              height: '24px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              padding: 0,
                            }}
                          >
                            −
                          </button>
                          <span
                            style={{
                              fontSize: '0.95rem',
                              fontWeight: 700,
                              color: isSelected ? '#FFFFFF' : '#6B7280',
                              minWidth: '16px',
                              textAlign: 'center',
                            }}
                          >
                            {roleItem.count}
                          </span>
                          <button
                            type="button"
                            onClick={(e) => handleIncrementRole(roleItem.id, e)}
                            aria-label={`Increase ${roleItem.role} count`}
                            style={{
                              background: 'transparent',
                              border: 'none',
                              color: '#F6C878',
                              fontSize: '1.1rem',
                              fontWeight: 600,
                              cursor: 'pointer',
                              width: '24px',
                              height: '24px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              padding: 0,
                            }}
                          >
                            +
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Floating Bottom Action Banner */}
                <div
                  style={{
                    position: 'sticky',
                    bottom: '24px',
                    margin: '18px auto 0 auto',
                    width: '100%',
                    maxWidth: '680px',
                    background: '#141719',
                    border: '1px solid rgba(246, 200, 120, 0.4)',
                    borderRadius: '16px',
                    padding: '12px 20px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '16px',
                    boxShadow: '0 12px 36px rgba(0, 0, 0, 0.65)',
                    zIndex: 20,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '0.88rem', fontWeight: 600, color: '#FFFFFF' }}>
                      Persona Panel Configured
                    </span>
                    <span style={{ fontSize: '0.78rem', color: '#9CA3AF' }}>
                      · Ready for synthetic generation
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={handleGeneratePersonas}
                    style={{
                      background: 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)',
                      color: '#080909',
                      border: 'none',
                      borderRadius: '10px',
                      padding: '8px 18px',
                      fontSize: '0.86rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      boxShadow: '0 4px 14px rgba(246, 200, 120, 0.25)',
                    }}
                  >
                    <span>Generate Personas</span>
                    <ArrowRight size={15} strokeWidth={2.5} />
                  </button>
                </div>
              </div>
            ) : (
              <>
                {/* Title & Subtitle */}
                <div style={{ textAlign: 'center', marginBottom: '20px' }}>
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

                {/* If no copilot messages yet, show default welcome intro bubble */}
                {copilotMessages.length === 0 && (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '14px',
                      background: 'rgba(255, 255, 255, 0.02)',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      borderRadius: '16px',
                      padding: '18px 22px',
                      marginBottom: '16px',
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
                        marginTop: '2px',
                      }}
                    >
                      A
                    </div>
                    <div style={{ fontSize: '0.92rem', color: '#E5E7EB', lineHeight: 1.55 }}>
                      Hello! Tell me what product idea, feature, or pricing model you want to research with synthetic personas.
                    </div>
                  </div>
                )}

                {/* Render Conversational Dialogue Stream */}
                {copilotMessages.map((msg) => {
                  if (msg.role === 'user') {
                    return (
                      <div
                        key={msg.id}
                        style={{
                          alignSelf: 'flex-end',
                          maxWidth: '80%',
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'flex-end',
                        }}
                      >
                        <div
                          style={{
                            background: '#1F2428',
                            border: '1px solid rgba(255, 255, 255, 0.09)',
                            borderRadius: '16px',
                            padding: '14px 20px',
                            color: '#F4F4F5',
                            fontSize: '0.92rem',
                            lineHeight: 1.5,
                            boxShadow: '0 4px 16px rgba(0, 0, 0, 0.25)',
                          }}
                        >
                          {msg.content}
                        </div>
                        <div
                          style={{
                            fontSize: '0.72rem',
                            color: '#71717A',
                            marginTop: '5px',
                            paddingRight: '6px',
                          }}
                        >
                          {msg.timestamp || 'Just now'}
                        </div>
                      </div>
                    );
                  }

                  // Assistant message
                  return (
                    <div
                      key={msg.id}
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: '14px',
                        maxWidth: '90%',
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
                          marginTop: '3px',
                        }}
                      >
                        A
                      </div>
                      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '14px' }}>
                        <div
                          style={{
                            background: 'rgba(255, 255, 255, 0.02)',
                            border: '1px solid rgba(255, 255, 255, 0.07)',
                            borderRadius: '16px',
                            padding: '16px 20px',
                            color: '#E5E7EB',
                            fontSize: '0.92rem',
                            lineHeight: 1.6,
                            whiteSpace: 'pre-wrap',
                          }}
                        >
                          {msg.content}
                        </div>

                        {/* Synthesized Research Goal Card */}
                        {msg.isGoalCard && msg.goalCardData && (
                          <div
                            style={{
                              background: '#121415',
                              border: '1px solid rgba(246, 200, 120, 0.35)',
                              borderRadius: '18px',
                              padding: '22px 24px',
                              boxShadow: '0 12px 36px rgba(0, 0, 0, 0.5)',
                            }}
                          >
                            <div
                              style={{
                                fontSize: '0.72rem',
                                fontWeight: 700,
                                color: '#F6C878',
                                letterSpacing: '0.08em',
                                marginBottom: '10px',
                              }}
                            >
                              {msg.goalCardData.title || 'RESEARCH GOAL'}
                            </div>
                            <div
                              style={{
                                fontSize: '0.92rem',
                                color: '#FFFFFF',
                                lineHeight: 1.55,
                                marginBottom: '20px',
                              }}
                            >
                              {msg.goalCardData.summary}
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                              <button
                                type="button"
                                onClick={() => handleApproveGoal(msg.goalCardData?.summary)}
                                style={{
                                  background: '#F6C878',
                                  color: '#080909',
                                  border: 'none',
                                  borderRadius: '8px',
                                  padding: '8px 20px',
                                  fontSize: '0.85rem',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '6px',
                                  transition: 'transform 0.15s ease',
                                }}
                                onMouseEnter={(e) => (e.currentTarget.style.transform = 'scale(1.03)')}
                                onMouseLeave={(e) => (e.currentTarget.style.transform = 'scale(1)')}
                              >
                                <CheckCircle2 size={15} strokeWidth={2.5} />
                                <span>Approve</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  handleSendCopilotMessage('I would like to refine the goal a bit further.');
                                }}
                                style={{
                                  background: 'rgba(255, 255, 255, 0.06)',
                                  color: '#9CA3AF',
                                  border: '1px solid rgba(255, 255, 255, 0.1)',
                                  borderRadius: '8px',
                                  padding: '8px 18px',
                                  fontSize: '0.85rem',
                                  cursor: 'pointer',
                                }}
                              >
                                Decline
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}

                {/* Typing Indicator */}
                {isCopilotTyping && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
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
                      A
                    </div>
                    <div
                      style={{
                        background: 'rgba(255, 255, 255, 0.02)',
                        border: '1px solid rgba(255, 255, 255, 0.06)',
                        borderRadius: '16px',
                        padding: '12px 18px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                      }}
                    >
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#F6C878' }} />
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#F6C878', opacity: 0.6 }} />
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#F6C878', opacity: 0.3 }} />
                    </div>
                  </div>
                )}

                {/* Quick 4 Research Goal Cards (shown when beginning or empty) */}
                {copilotMessages.length === 0 && (
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(4, 1fr)',
                      gap: '12px',
                      marginTop: '16px',
                      width: '100%',
                    }}
                  >
                    {goalsList.map((g) => {
                      const isSelected = selectedGoal === g.id;
                      return (
                        <div
                          key={g.id}
                          onClick={() => {
                            handleGoalSelect(g.id);
                            handleSendCopilotMessage(`Let's run a ${g.title} study to ${g.description.toLowerCase()}`);
                          }}
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
                )}
              </>
            )}
          </div>
        )}

        {/* ============================================================
            STEP 2: PERSONAS GROUNDING & AUDIENCE GENERATION (Matches Screenshots 1, 2, 3)
           ============================================================ */}
        {currentStep === 2 && (
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '20px', paddingBottom: '140px' }}>
            {/* Header: Title + Subtitle */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <h1
                style={{
                  fontSize: 'clamp(1.8rem, 3.2vw, 2.3rem)',
                  fontWeight: 500,
                  color: '#FFFFFF',
                  letterSpacing: '-0.02em',
                  margin: 0,
                }}
              >
                {study?.title && study.title !== 'Untitled Study'
                  ? study.title
                  : [...copilotMessages].reverse().find((m) => m.role === 'user')?.content ||
                    promptInput ||
                    'Product Research Study'}
              </h1>

              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginTop: '2px' }}>
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px',
                    fontSize: '0.86rem',
                    color: '#9CA3AF',
                  }}
                >
                  <Search size={14} color="#6B7280" />
                  <span>Search audience</span>
                </div>
                <span style={{ color: '#4B5563' }}>•</span>
                <span style={{ fontSize: '0.84rem', color: '#9CA3AF' }}>
                  {isGeneratingPersonas
                    ? 'Generating personas...'
                    : `${personas.length} personas, shaped from your research`}
                </span>
              </div>
            </div>

            {/* Horizontal Filter Tabs Pill Row */}
            {!isGeneratingPersonas && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  overflowX: 'auto',
                  paddingBottom: '4px',
                  scrollbarWidth: 'none',
                }}
              >
                <button
                  type="button"
                  onClick={() => setSelectedRoleFilter('all')}
                  style={{
                    background: selectedRoleFilter === 'all' ? 'rgba(246, 200, 120, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                    border: selectedRoleFilter === 'all' ? '1px solid #F6C878' : '1px solid rgba(255, 255, 255, 0.08)',
                    color: selectedRoleFilter === 'all' ? '#F6C878' : '#9CA3AF',
                    borderRadius: '20px',
                    padding: '6px 14px',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    transition: 'all 0.15s ease',
                  }}
                >
                  All {personas.length}
                </button>

                {suggestedRoles
                  .filter((r) => r.selected || r.count > 0)
                  .map((role) => {
                    const rolePersonasCount = personas.filter(
                      (p) => p.role_id === role.id || p.archetype.toLowerCase().includes(role.role.toLowerCase())
                    ).length || role.count;
                    const isSelected = selectedRoleFilter === role.id;

                    return (
                      <button
                        key={role.id}
                        type="button"
                        onClick={() => setSelectedRoleFilter(role.id)}
                        style={{
                          background: isSelected ? 'rgba(246, 200, 120, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                          border: isSelected ? '1px solid #F6C878' : '1px solid rgba(255, 255, 255, 0.08)',
                          color: isSelected ? '#F6C878' : '#9CA3AF',
                          borderRadius: '20px',
                          padding: '6px 14px',
                          fontSize: '0.78rem',
                          fontWeight: 500,
                          cursor: 'pointer',
                          whiteSpace: 'nowrap',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        {role.role} {rolePersonasCount}
                      </button>
                    );
                  })}
              </div>
            )}

            {/* Split 2-Column Section: Sidebar + Cards Grid */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '260px 1fr',
                gap: '24px',
                width: '100%',
                alignItems: 'start',
              }}
            >
              {/* Left Sidebar: Total Personas & Role Steppers */}
              <div
                style={{
                  background: 'rgba(255, 255, 255, 0.015)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '16px',
                  padding: '20px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '16px',
                  position: 'sticky',
                  top: '80px',
                }}
              >
                {/* Total Personas header */}
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.82rem', color: '#9CA3AF' }}>
                    <span>Total Personas</span>
                    <Info size={13} color="#6B7280" />
                  </div>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: '#FFFFFF', marginTop: '2px', lineHeight: 1.1 }}>
                    {personas.length} <span style={{ fontSize: '0.9rem', fontWeight: 400, color: '#9CA3AF' }}>personas</span>
                  </div>
                  <div style={{ fontSize: '0.76rem', color: '#6B7280', marginTop: '2px' }}>
                    across {suggestedRoles.filter((r) => r.selected || r.count > 0).length || 10} roles
                  </div>
                </div>

                {/* PER ROLE Section */}
                <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.06)', paddingTop: '14px' }}>
                  <div
                    style={{
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      letterSpacing: '0.08em',
                      color: '#6B7280',
                      textTransform: 'uppercase',
                      marginBottom: '12px',
                    }}
                  >
                    PER ROLE
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {suggestedRoles.map((role) => (
                      <div
                        key={role.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '8px',
                          fontSize: '0.82rem',
                        }}
                      >
                        <span style={{ color: '#D1D5DB', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {role.role}
                        </span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ color: '#FFFFFF', fontWeight: 600, minWidth: '14px', textAlign: 'center' }}>
                            {role.count}
                          </span>
                          <button
                            type="button"
                            onClick={() => handleRoleCountChangeInStep2(role.id, 1)}
                            style={{
                              background: 'transparent',
                              border: 'none',
                              color: '#F6C878',
                              cursor: 'pointer',
                              padding: '2px 4px',
                              fontSize: '0.95rem',
                              fontWeight: 700,
                            }}
                          >
                            +
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Action Buttons in Sidebar */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '10px' }}>
                  <button
                    type="button"
                    onClick={() => {
                      setSavedAudiences((prev) => [...prev, study?.id || 'audience_1']);
                      alert('Audience saved to Persona Library!');
                    }}
                    style={{
                      background: '#1F2428',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      color: savedAudiences.length > 0 ? '#10B981' : '#FFFFFF',
                      borderRadius: '10px',
                      padding: '10px',
                      fontSize: '0.82rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '8px',
                    }}
                  >
                    <Bookmark size={14} color={savedAudiences ? '#10B981' : '#F6C878'} />
                    <span>{savedAudiences ? 'Audience Saved' : 'Save audience'}</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => handleStepChange(1)}
                    style={{
                      background: 'transparent',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      color: '#9CA3AF',
                      borderRadius: '10px',
                      padding: '8px',
                      fontSize: '0.78rem',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '6px',
                    }}
                  >
                    <Plus size={13} />
                    <span>Refine all Personas</span>
                  </button>
                </div>
              </div>

              {/* Main Content Area: Shimmering Skeletons OR 3-Column Persona Cards Grid */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                {isGeneratingPersonas ? (
                  /* Shimmering Skeletons matching Screenshot 1 */
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
                      gap: '16px',
                    }}
                  >
                    {[1, 2, 3, 4, 5, 6].map((idx) => (
                      <div
                        key={idx}
                        style={{
                          background: 'rgba(255, 255, 255, 0.015)',
                          border: '1px solid rgba(255, 255, 255, 0.06)',
                          borderRadius: '14px',
                          padding: '20px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '14px',
                          opacity: 0.7,
                          animation: 'pulse 1.5s infinite ease-in-out',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <div style={{ width: '40px', height: '40px', borderRadius: '10px', background: 'rgba(246, 200, 120, 0.1)' }} />
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
                            <div style={{ width: '60%', height: '14px', borderRadius: '4px', background: 'rgba(255, 255, 255, 0.08)' }} />
                            <div style={{ width: '40%', height: '10px', borderRadius: '4px', background: 'rgba(255, 255, 255, 0.04)' }} />
                          </div>
                        </div>
                        <div style={{ width: '100%', height: '10px', borderRadius: '4px', background: 'rgba(255, 255, 255, 0.05)' }} />
                        <div style={{ width: '85%', height: '10px', borderRadius: '4px', background: 'rgba(255, 255, 255, 0.05)' }} />
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginTop: '6px' }}>
                          <div style={{ height: '32px', borderRadius: '6px', background: 'rgba(255, 255, 255, 0.03)' }} />
                          <div style={{ height: '32px', borderRadius: '6px', background: 'rgba(255, 255, 255, 0.03)' }} />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  /* Loaded 3-Column Persona Cards Grid matching Screenshots 2 & 3 */
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                      gap: '16px',
                      width: '100%',
                    }}
                  >
                    {personas
                      .filter((p) => {
                        if (selectedRoleFilter === 'all') return true;
                        return p.role_id === selectedRoleFilter || p.archetype.toLowerCase().includes(selectedRoleFilter.replace('role_', '').replace('_', ' '));
                      })
                      .map((p) => {
                        const initials = p.initials || p.name.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase();
                        const isSelected = selectedPersonaIds.includes(p.id);

                        return (
                          <div
                            key={p.id}
                            style={{
                              background: '#121417',
                              border: isSelected ? '1px solid rgba(246, 200, 120, 0.4)' : '1px solid rgba(255, 255, 255, 0.08)',
                              borderRadius: '14px',
                              padding: '20px',
                              display: 'flex',
                              flexDirection: 'column',
                              gap: '14px',
                              boxShadow: '0 4px 20px rgba(0, 0, 0, 0.4)',
                              transition: 'all 0.15s ease',
                              position: 'relative',
                              minWidth: 0,
                              overflow: 'hidden',
                              boxSizing: 'border-box',
                            }}
                          >
                            {/* Card Top Row: Initials Avatar + Name & Subline + Action Icons */}
                            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '10px', minWidth: 0 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0, flex: 1 }}>
                                <div
                                  style={{
                                    width: '42px',
                                    height: '42px',
                                    borderRadius: '10px',
                                    background: 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)',
                                    color: '#080909',
                                    fontWeight: 700,
                                    fontSize: '0.92rem',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    flexShrink: 0,
                                  }}
                                >
                                  {initials}
                                </div>
                                <div style={{ minWidth: 0, flex: 1 }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
                                    <span style={{ fontWeight: 600, fontSize: '0.95rem', color: '#FFFFFF', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                      {p.name}
                                    </span>
                                    <span
                                      style={{
                                        fontSize: '0.68rem',
                                        background: 'rgba(255, 255, 255, 0.08)',
                                        borderRadius: '4px',
                                        padding: '1px 5px',
                                        color: '#9CA3AF',
                                        fontWeight: 600,
                                        flexShrink: 0,
                                      }}
                                    >
                                      {p.country_code || 'GLOBAL'}
                                    </span>
                                  </div>
                                  <div style={{ fontSize: '0.76rem', color: '#9CA3AF', marginTop: '2px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                    {p.demographics?.age ? `${p.demographics.age} years old • ` : ''}{p.demographics?.location || 'Target Market'}
                                  </div>
                                  <div style={{ fontSize: '0.78rem', color: '#F6C878', fontWeight: 600, marginTop: '2px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                    {p.tagline || p.archetype}
                                  </div>
                                </div>
                              </div>

                              {/* Card Action Icons */}
                              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    alert(`Saved ${p.name} to favorites!`);
                                  }}
                                  title="Save persona"
                                  style={{
                                    background: 'transparent',
                                    border: 'none',
                                    color: '#6B7280',
                                    cursor: 'pointer',
                                    padding: '4px',
                                    display: 'flex',
                                    alignItems: 'center',
                                  }}
                                >
                                  <Bookmark size={14} />
                                </button>
                                <button
                                  type="button"
                                  onClick={(e) => handleClonePersona(p, e)}
                                  title="Clone persona"
                                  style={{
                                    background: 'transparent',
                                    border: 'none',
                                    color: '#6B7280',
                                    cursor: 'pointer',
                                    padding: '4px',
                                    display: 'flex',
                                    alignItems: 'center',
                                  }}
                                >
                                  <Plus size={14} />
                                </button>
                                <button
                                  type="button"
                                  onClick={(e) => handleRemovePersona(p.id, e)}
                                  title="Delete persona"
                                  style={{
                                    background: 'transparent',
                                    border: 'none',
                                    color: '#6B7280',
                                    cursor: 'pointer',
                                    padding: '4px',
                                    display: 'flex',
                                    alignItems: 'center',
                                  }}
                                >
                                  <Trash2 size={14} />
                                </button>
                              </div>
                            </div>

                            {/* Narrative Description */}
                            <div
                              style={{
                                fontSize: '0.82rem',
                                color: '#D1D5DB',
                                lineHeight: 1.45,
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                display: '-webkit-box',
                                WebkitLineClamp: 3,
                                WebkitBoxOrient: 'vertical',
                                wordBreak: 'break-word',
                              }}
                            >
                              {p.description ||
                                `${p.name} is a representative archetype synthesized to validate customer adoption, pain points, and willingness to pay.`}
                            </div>

                            {/* Metadata Badges (Protected Grid with Truncation) */}
                            <div
                              style={{
                                display: 'grid',
                                gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                                gap: '10px 14px',
                                background: 'rgba(255, 255, 255, 0.02)',
                                border: '1px solid rgba(255, 255, 255, 0.05)',
                                borderRadius: '10px',
                                padding: '12px 14px',
                                minWidth: 0,
                                overflow: 'hidden',
                                boxSizing: 'border-box',
                              }}
                            >
                              {(p.badges && p.badges.length > 0 ? p.badges : [
                                { label: 'USAGE PATTERN', value: 'Active Daily Adopter' },
                                { label: 'PRICE COMFORT', value: 'Values Transparent Tiers' },
                                { label: 'PRIMARY GOAL', value: 'Efficiency & Convenience' },
                                { label: 'CHURN RISK', value: 'High if onboarding is slow' },
                              ]).slice(0, 4).map((b, bIdx) => (
                                <div key={bIdx} style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0, overflow: 'hidden' }}>
                                  <span
                                    style={{
                                      fontSize: '0.66rem',
                                      fontWeight: 700,
                                      color: '#F6C878',
                                      letterSpacing: '0.04em',
                                      textTransform: 'uppercase',
                                      whiteSpace: 'nowrap',
                                      overflow: 'hidden',
                                      textOverflow: 'ellipsis',
                                    }}
                                    title={b.label}
                                  >
                                    {b.label}
                                  </span>
                                  <span
                                    style={{
                                      fontSize: '0.76rem',
                                      color: '#9CA3AF',
                                      lineHeight: 1.3,
                                      whiteSpace: 'nowrap',
                                      overflow: 'hidden',
                                      textOverflow: 'ellipsis',
                                      display: 'block',
                                      minWidth: 0,
                                    }}
                                    title={b.value}
                                  >
                                    {b.value}
                                  </span>
                                </div>
                              ))}
                            </div>

                            {/* View Full Profile link */}
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto', paddingTop: '4px' }}>
                              <button
                                type="button"
                                onClick={() => setViewingPersona(p)}
                                style={{
                                  background: 'transparent',
                                  border: 'none',
                                  color: '#F6C878',
                                  fontSize: '0.8rem',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                  padding: 0,
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '4px',
                                }}
                              >
                                <span>View full profile</span>
                                <ArrowRight size={13} />
                              </button>

                              <span
                                style={{
                                  fontSize: '0.7rem',
                                  fontWeight: 700,
                                  color: '#10B981',
                                  background: 'rgba(16, 185, 129, 0.1)',
                                  padding: '2px 8px',
                                  borderRadius: '6px',
                                  flexShrink: 0,
                                }}
                              >
                                {Math.round((p.grounding_ratio || 0.96) * 100)}% Grounded
                              </span>
                            </div>
                          </div>
                        );
                      })}
                  </div>
                )}
              </div>
            </div>

            {/* Modal: Full Persona Demographic & Evidence Profile */}
            {viewingPersona && (
              <div
                style={{
                  position: 'fixed',
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  background: 'rgba(0, 0, 0, 0.8)',
                  backdropFilter: 'blur(10px)',
                  zIndex: 50,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '24px',
                }}
                onClick={() => setViewingPersona(null)}
              >
                <div
                  style={{
                    background: '#121416',
                    border: '1px solid rgba(246, 200, 120, 0.35)',
                    borderRadius: '20px',
                    maxWidth: '680px',
                    width: '100%',
                    maxHeight: '85vh',
                    overflowY: 'auto',
                    padding: '28px 32px',
                    boxShadow: '0 24px 60px rgba(0, 0, 0, 0.8)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '20px',
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {/* Modal Header */}
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                      <div
                        style={{
                          width: '52px',
                          height: '52px',
                          borderRadius: '12px',
                          background: 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)',
                          color: '#080909',
                          fontWeight: 700,
                          fontSize: '1.2rem',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        {viewingPersona.initials || viewingPersona.name.slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <h2 style={{ fontSize: '1.35rem', fontWeight: 600, color: '#FFFFFF', margin: 0 }}>
                            {viewingPersona.name}
                          </h2>
                          <span style={{ fontSize: '0.72rem', background: 'rgba(255, 255, 255, 0.08)', padding: '2px 6px', borderRadius: '4px', color: '#9CA3AF', fontWeight: 600 }}>
                            {viewingPersona.country_code || 'GLOBAL'}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.84rem', color: '#9CA3AF', marginTop: '2px' }}>
                          {viewingPersona.demographics?.age} years old • {viewingPersona.demographics?.occupation} • {viewingPersona.demographics?.location}
                        </div>
                        <div style={{ fontSize: '0.86rem', color: '#F6C878', fontWeight: 600, marginTop: '2px' }}>
                          {viewingPersona.tagline}
                        </div>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => setViewingPersona(null)}
                      style={{
                        background: 'rgba(255, 255, 255, 0.06)',
                        border: 'none',
                        color: '#9CA3AF',
                        borderRadius: '50%',
                        width: '32px',
                        height: '32px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        cursor: 'pointer',
                      }}
                    >
                      <X size={16} />
                    </button>
                  </div>

                  {/* Narrative Bio */}
                  <div
                    style={{
                      background: 'rgba(255, 255, 255, 0.02)',
                      border: '1px solid rgba(255, 255, 255, 0.06)',
                      borderRadius: '12px',
                      padding: '16px 20px',
                      fontSize: '0.88rem',
                      color: '#E5E7EB',
                      lineHeight: 1.55,
                    }}
                  >
                    {viewingPersona.description}
                  </div>

                  {/* Badges breakdown */}
                  {viewingPersona.badges && (
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        gap: '12px',
                        background: 'rgba(255, 255, 255, 0.015)',
                        border: '1px solid rgba(255, 255, 255, 0.05)',
                        borderRadius: '12px',
                        padding: '16px',
                      }}
                    >
                      {viewingPersona.badges.map((b, i) => (
                        <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                          <span style={{ fontSize: '0.7rem', fontWeight: 700, color: '#F6C878' }}>
                            {b.label}
                          </span>
                          <span style={{ fontSize: '0.82rem', color: '#D1D5DB' }}>
                            {b.value}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Grounded Claims Breakdown */}
                  {viewingPersona.attributes && viewingPersona.attributes.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#9CA3AF', letterSpacing: '0.06em' }}>
                        GROUNDED BEHAVIORAL CLAIMS & PROVENANCE
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {viewingPersona.attributes.map((attr, idx) => (
                          <div
                            key={idx}
                            style={{
                              background: 'rgba(255, 255, 255, 0.02)',
                              border: '1px solid rgba(255, 255, 255, 0.06)',
                              borderRadius: '10px',
                              padding: '12px 16px',
                              display: 'flex',
                              flexDirection: 'column',
                              gap: '4px',
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                              <span style={{ fontSize: '0.84rem', fontWeight: 600, color: '#FFFFFF' }}>
                                {attr.category}: {attr.title}
                              </span>
                              <span
                                style={{
                                  fontSize: '0.68rem',
                                  fontWeight: 700,
                                  color: attr.provenance_class === 'OBSERVED' ? '#10B981' : '#F6C878',
                                  background: attr.provenance_class === 'OBSERVED' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(246, 200, 120, 0.1)',
                                  padding: '2px 6px',
                                  borderRadius: '4px',
                                }}
                              >
                                {attr.provenance_class || 'OBSERVED'}
                              </span>
                            </div>
                            <div style={{ fontSize: '0.8rem', color: '#9CA3AF', lineHeight: 1.4 }}>
                              {attr.description}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
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

      {/* Floating Action Banner when on Step 2 (Personas) */}
      {currentStep === 2 && (
        <div
          style={{
            position: 'fixed',
            bottom: '24px',
            left: '50%',
            transform: 'translateX(-50%)',
            background: 'rgba(18, 20, 22, 0.96)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            borderRadius: '16px',
            padding: isGeneratingPersonas ? '14px 28px' : '12px 24px',
            display: 'flex',
            alignItems: 'center',
            gap: '28px',
            boxShadow: '0 16px 40px rgba(0, 0, 0, 0.75), 0 0 0 1px rgba(255, 255, 255, 0.05)',
            backdropFilter: 'blur(20px)',
            zIndex: 40,
            maxWidth: isGeneratingPersonas ? '580px' : '480px',
            width: 'calc(100% - 48px)',
            justifyContent: 'space-between',
          }}
        >
          {isGeneratingPersonas ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <RefreshCw size={14} color="#F6C878" />
                  <span style={{ fontSize: '0.86rem', fontWeight: 600, color: '#FFFFFF' }}>
                    Generating personas...
                  </span>
                </div>
                <div style={{ fontSize: '0.76rem', color: '#9CA3AF' }}>
                  Estimated time: ~2 min
                </div>
              </div>

              {/* Progress bar */}
              <div style={{ width: '100%', height: '4px', background: 'rgba(255, 255, 255, 0.08)', borderRadius: '2px', overflow: 'hidden' }}>
                <div
                  style={{
                    width: `${generationProgress}%`,
                    height: '100%',
                    background: 'linear-gradient(90deg, #F6C878 0%, #D4AF37 100%)',
                    transition: 'width 0.2s ease',
                  }}
                />
              </div>

              {showDidYouKnow && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '10px',
                    fontSize: '0.74rem',
                    color: '#9CA3AF',
                    background: 'rgba(255, 255, 255, 0.03)',
                    padding: '6px 10px',
                    borderRadius: '8px',
                    marginTop: '2px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Lightbulb size={13} color="#F6C878" />
                    <span>
                      <strong style={{ color: '#FFFFFF' }}>Did you know?</strong> Personas aren't one-time — once they're ready, save the whole audience and reuse it in your next study without regenerating.
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowDidYouKnow(false)}
                    style={{ background: 'transparent', border: 'none', color: '#6B7280', cursor: 'pointer', padding: 0 }}
                  >
                    <X size={12} />
                  </button>
                </div>
              )}
            </div>
          ) : (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <div style={{ fontSize: '0.88rem', fontWeight: 600, color: '#FFFFFF', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>Personas ready</span>
                  <span>🥳</span>
                </div>
                <div style={{ fontSize: '0.78rem', color: '#9CA3AF' }}>
                  Your report is just 1 step away
                </div>
              </div>

              <button
                type="button"
                onClick={() => handleStepChange(3)}
                style={{
                  background: '#F6C878',
                  color: '#080909',
                  border: 'none',
                  borderRadius: '10px',
                  padding: '10px 22px',
                  fontSize: '0.86rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  transition: 'transform 0.15s ease, background 0.15s ease',
                  flexShrink: 0,
                }}
                onMouseEnter={(e) => (e.currentTarget.style.transform = 'scale(1.03)')}
                onMouseLeave={(e) => (e.currentTarget.style.transform = 'scale(1)')}
              >
                <span>Generate Script</span>
                <ArrowRight size={15} strokeWidth={2.5} />
              </button>
            </>
          )}
        </div>
      )}

      {/* Fixed Bottom Action / Chat Bar (Matches Screenshot 4) */}
      {currentStep < 5 && !(currentStep === 1 && showRoleSelection) && currentStep !== 2 && (
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
              maxWidth: '980px',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
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
                value={currentStep === 1 ? step1Prompt : promptInput}
                onChange={(e) => {
                  if (currentStep === 1) {
                    setStep1Prompt(e.target.value);
                  } else {
                    setPromptInput(e.target.value);
                  }
                }}
                placeholder={
                  currentStep === 1
                    ? "Type here to answer or give more context..."
                    : "Type here..."
                }
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    const val = (e.target as HTMLInputElement).value || step1Prompt;
                    if (currentStep === 1) {
                      handleSendCopilotMessage(val);
                    } else {
                      handleStepChange(currentStep + 1);
                    }
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
                onClick={() => {
                  if (currentStep === 1) {
                    handleSendCopilotMessage();
                  } else {
                    handleStepChange(currentStep + 1);
                  }
                }}
                aria-label="Send prompt"
                style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '50%',
                  background: (currentStep === 1 ? step1Prompt : promptInput).trim()
                    ? '#F6C878'
                    : 'rgba(255, 255, 255, 0.08)',
                  color: (currentStep === 1 ? step1Prompt : promptInput).trim() ? '#080909' : '#6B7280',
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
