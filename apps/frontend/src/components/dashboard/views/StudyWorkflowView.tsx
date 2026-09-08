import React, { useState, useEffect, useRef } from 'react';
import { Check, Lock } from 'lucide-react';
import {
  Study,
  StudyType,
  Persona,
  ConversationTurn,
  PersonaRoleSuggestion,
  StudyReport,
} from '../../../types';
import { api } from '../../../services/api';
import type { FailedPersonaRole } from '../../../services/api';
import { useNavigation } from '../../../context/NavigationContext';
import { useViewMotion } from '../../../motion/useViewMotion';
import {
  CopilotMessage,
  DEFAULT_PERSONA_COUNT,
  MAX_PERSONAS_PER_ROLE,
  READ_ONLY_TITLE,
  isTemplateReply,
} from './workflow/types';
import { fromUnknownError, toUserMessage } from '../../../utils/apiError';
import { Step1Context } from './workflow/Step1Context';
import { Step2Personas } from './workflow/Step2Personas';
import { Step3Script } from './workflow/Step3Script';
import { Step4Interviews } from './workflow/Step4Interviews';
import { Step5Report } from './workflow/Step5Report';
import { PersonaDetailModal } from './workflow/PersonaDetailModal';
import { EvidenceProbe, nextEvidenceProbe } from './workflow/evidenceProbe';

interface StudyWorkflowViewProps {
  studyId?: string;
  initialStep?: number;
  initialType?: StudyType;
  initialPrompt?: string;
  onExit: () => void;
  onStepChange?: (step: number) => void;
}

export const StudyWorkflowView: React.FC<StudyWorkflowViewProps> = ({
  studyId,
  initialStep = 1,
  initialType = 'interviews',
  initialPrompt = '',
  onExit,
  onStepChange,
}) => {
  const [currentStep, setCurrentStep] = useState<number>(initialStep);
  const { navigate } = useNavigation();
  const stepViewRef = useViewMotion<HTMLDivElement>([currentStep]);
  const [study, setStudy] = useState<Study | null>(null);
  // Example studies are readable by everyone but writable by no one — the UI
  // must never offer a CTA the backend's write gate will refuse.
  const isReadOnly = study?.is_demo === true;
  // A 403 from a write endpoint is the read-only gate, not a failure — its
  // message renders as a calm notice instead of an alarming error.
  const [readOnlyNotice, setReadOnlyNotice] = useState<string | null>(null);
  const readOnlyRefusal = (err: unknown): string | null =>
    (err as { status?: number })?.status === 403
      ? (err as Error)?.message || READ_ONLY_TITLE
      : null;
  const [promptInput, setPromptInput] = useState<string>(initialPrompt);
  // No seeded questionnaire: the script is either written by the model from
  // this study's context or typed by the researcher. An empty list is honest.
  const [questions, setQuestions] = useState<string[]>([]);
  const [scriptGenerated, setScriptGenerated] = useState<boolean>(() => {
    if (!studyId || typeof localStorage === 'undefined') return false;
    return localStorage.getItem(`bebshax_script_generated_${studyId}`) === '1';
  });
  // Where the current questions came from, once a generation has run this session.
  const [scriptSource, setScriptSource] = useState<'llm' | 'fallback_static' | null>(null);
  const [newQuestion, setNewQuestion] = useState<string>('');
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [selectedPersonaIds, setSelectedPersonaIds] = useState<string[]>([]);
  const [isGeneratingPersonas, setIsGeneratingPersonas] = useState<boolean>(false);
  const [personaGenError, setPersonaGenError] = useState<string | null>(null);
  const [personaGenRequestId, setPersonaGenRequestId] = useState<string | null>(null);
  const [personaFailedRoles, setPersonaFailedRoles] = useState<FailedPersonaRole[]>([]);
  const [personaServedBy, setPersonaServedBy] = useState<string[]>([]);
  const [viewingPersona, setViewingPersona] = useState<Persona | null>(null);

  // Copilot Multi-turn Conversational States (Step 1)
  const [copilotMessages, setCopilotMessages] = useState<CopilotMessage[]>([]);
  const [isCopilotTyping, setIsCopilotTyping] = useState<boolean>(false);
  const [step1Prompt, setStep1Prompt] = useState<string>('');
  const [showRoleSelection, setShowRoleSelection] = useState<boolean>(false);
  const [suggestedRoles, setSuggestedRoles] = useState<PersonaRoleSuggestion[]>([]);
  const [isLoadingRoles, setIsLoadingRoles] = useState<boolean>(false);
  const [roleError, setRoleError] = useState<string | null>(null);
  const [scriptError, setScriptError] = useState<string | null>(null);

  // Live Interview Simulation States (Step 4)
  const [activeInterviewPersonaId, setActiveInterviewPersonaId] = useState<string>('');
  const [chatMessages, setChatMessages] = useState<ConversationTurn[]>([]);
  const [isSimulating, setIsSimulating] = useState(false);
  const [isBatchRunning, setIsBatchRunning] = useState(false);
  const [userInputMessage, setUserInputMessage] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [interviewStatusMap, setInterviewStatusMap] = useState<Record<string, 'pending' | 'in_progress' | 'completed' | 'failed'>>({});
  // Per-persona failure reasons reported by the batch job, plus the whole-batch
  // error (with its request id) when the job itself could not start.
  const [interviewFailureReasons, setInterviewFailureReasons] = useState<Record<string, string>>({});
  const [batchError, setBatchError] = useState<{ message: string; requestId: string | null } | null>(null);

  // Step 5: Final Report
  const [report, setReport] = useState<StudyReport | null>(null);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [availableReports, setAvailableReports] = useState<StudyReport[]>([]);
  const [copiedToast, setCopiedToast] = useState(false);
  const [isGeneratingScript, setIsGeneratingScript] = useState(false);

  // Step 1: state of the supporting-evidence attempt for this study. Read from
  // the evidence summary the Evidence Laboratory already serves — no new
  // endpoint, and it never blocks the copilot path.
  const [evidenceProbe, setEvidenceProbe] = useState<EvidenceProbe>({ state: 'checking' });
  const evidenceProbeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const evidenceProbeAliveRef = useRef<boolean>(true);

  const copilotMessagesRef = useRef<CopilotMessage[]>([]);
  const isFetchingCopilotRef = useRef<boolean>(false);
  const initialPromptHandledRef = useRef<string | null>(null);
  const roleSelectionRef = useRef<HTMLDivElement | null>(null);
  const copilotChatRef = useRef<HTMLDivElement | null>(null);
  const interviewChatRef = useRef<HTMLDivElement | null>(null);
  const step1InputRef = useRef<HTMLTextAreaElement | null>(null);
  const personaModalTriggerRef = useRef<HTMLElement | null>(null);
  const personaModalRef = useRef<HTMLDivElement | null>(null);

  // Chats must stay pinned to the newest message — both containers scroll internally.
  useEffect(() => {
    const el = copilotChatRef.current;
    if (el) el.scrollTo?.({ top: el.scrollHeight, behavior: 'smooth' });
  }, [copilotMessages, isCopilotTyping]);
  useEffect(() => {
    const el = interviewChatRef.current;
    if (el) el.scrollTo?.({ top: el.scrollHeight, behavior: 'smooth' });
  }, [chatMessages, isSimulating]);

  useEffect(() => {
    copilotMessagesRef.current = copilotMessages;
  }, [copilotMessages]);

  // Restore the interview transcript for the selected persona on refresh:
  // the turns live in the backend; only the conversation id is kept locally.
  useEffect(() => {
    if (!studyId || !activeInterviewPersonaId) return;
    const storedConvId = localStorage.getItem(
      `bebshax_conv_${studyId}_${activeInterviewPersonaId}`
    );
    if (!storedConvId) {
      setConversationId(null);
      setChatMessages([]);
      return;
    }
    let cancelled = false;
    api
      .getConversation(storedConvId)
      .then((conv) => {
        if (cancelled || !conv) return;
        setConversationId(conv.id);
        setChatMessages(conv.turns || []);
      })
      .catch(() => {
        if (!cancelled) {
          localStorage.removeItem(`bebshax_conv_${studyId}_${activeInterviewPersonaId}`);
          setConversationId(null);
          setChatMessages([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [studyId, activeInterviewPersonaId]);

  const handleStepChange = (newStep: number, opts?: { reportReady?: boolean }) => {
    const clamped = Math.max(1, Math.min(newStep, 5));
    setCurrentStep(clamped);
    onStepChange?.(clamped);
    // Read-only example studies never PATCH — the write gate would refuse.
    if (studyId && !isReadOnly) {
      // 'completed' is earned by a generated report — never by visiting step 5.
      const reportExists = opts?.reportReady || report !== null || availableReports.length > 0;
      api
        .updateStudy(studyId, {
          step: clamped,
          status: reportExists ? 'completed' : 'in_progress',
          prompt: promptInput || study?.prompt,
          copilot_messages: copilotMessagesRef.current as any,
          suggested_roles: suggestedRoles,
          personas_data: personas as any,
          persona_count: personas.length,
          persona_ids: personas.map((p) => p.id),
          script_questions: questions,
        })
        .catch(() => {});
    }
  };

  // Restore full study state from DB on mount / refresh
  useEffect(() => {
    if (!studyId) return;
    api
      .getStudy(studyId)
      .then((s) => {
        if (!s) return;
        setStudy(s);
        if (s.prompt && !promptInput) setPromptInput(s.prompt);
        // Saved history wins whenever it is longer than what's in memory
        // (e.g. a stale initialPrompt seeded a single-message chat).
        const saved = (s.copilot_messages || []) as any[];
        if (saved.length > copilotMessagesRef.current.length) {
          const restored = saved.map((m: any, i: number) => ({
            ...m,
            id: m.id || `msg_restored_${i}_${Date.now()}`,
          }));
          setCopilotMessages(restored);
          copilotMessagesRef.current = restored;
        }
        if (s.suggested_roles && s.suggested_roles.length > 0) {
          // Studies saved before the per-role cap can carry counts the server now rejects.
          setSuggestedRoles(
            s.suggested_roles.map((r: any) => ({ ...r, count: Math.min(MAX_PERSONAS_PER_ROLE, Number(r.count) || 0) }))
          );
          // Reopen the role drawer when the goal was already approved pre-refresh.
          if ((s.copilot_messages || []).some((m: any) => m.isGoalCard)) {
            setShowRoleSelection(true);
          }
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
        // Honor the URL step when it was explicitly provided (> 1);
        // otherwise restore the persisted step from the DB.
        if (s.step && initialStep === 1) {
          setCurrentStep(s.step);
        }
      })
      .catch(() => {});

    // Load reports if step 5
    api.getStudyReports(studyId).then((reps) => {
      if (reps && reps.length > 0) {
        setAvailableReports(reps);
        setReport(reps[0]);
      }
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studyId]);

  // Report on the evidence attempt itself so step 2 never arrives unexplained.
  // A single GET; while a run is in flight it re-checks a bounded number of
  // times so "Looking for…" can actually resolve without a page reload.
  const probeEvidence = React.useCallback(
    async (attemptsLeft = 8) => {
      if (!studyId) {
        setEvidenceProbe({ state: 'not_run' });
        return;
      }
      try {
        const summary = await api.getEvidenceSummary(studyId);
        if (!evidenceProbeAliveRef.current) return;
        const next = nextEvidenceProbe(summary, attemptsLeft);
        setEvidenceProbe(next);
        if (next.state === 'searching') {
          evidenceProbeTimerRef.current = setTimeout(() => probeEvidence(attemptsLeft - 1), 6000);
        }
      } catch {
        if (evidenceProbeAliveRef.current) setEvidenceProbe({ state: 'unavailable' });
      }
    },
    [studyId],
  );

  useEffect(() => {
    evidenceProbeAliveRef.current = true;
    setEvidenceProbe({ state: 'checking' });
    probeEvidence();
    return () => {
      evidenceProbeAliveRef.current = false;
      if (evidenceProbeTimerRef.current) clearTimeout(evidenceProbeTimerRef.current);
    };
  }, [probeEvidence]);

  /** Step 1's `not_run` state can start the evidence run directly — same
   * trigger + probe plumbing handleApproveGoal already uses. */
  const handleRunEvidenceResearch = () => {
    // Guard the one-frame window before re-render unmounts the button.
    if (!studyId || evidenceProbe.state !== 'not_run') return;
    setEvidenceProbe({ state: 'searching' });
    api
      .triggerStudyResearch(studyId)
      .catch(() => {})
      .finally(() => probeEvidence());
  };

  const fetchCopilotTurn = async (history: { role: 'user' | 'assistant'; content: string }[]) => {
    if (isFetchingCopilotRef.current) return;
    isFetchingCopilotRef.current = true;
    setIsCopilotTyping(true);
    try {
      const res = await api.sendStudyCopilotMessage(history, initialType, studyId);
      const template = isTemplateReply(res);
      const assistantMsg: CopilotMessage = {
        id: `msg_a_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
        role: 'assistant',
        content: res.reply,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
        isGoalCard: res.is_ready_for_approval && !!res.research_goal_card,
        goalCardData: res.research_goal_card || undefined,
        servedBy: res.served_by,
        fallbackReason: res.fallback_reason ?? null,
        isTemplate: template,
      };

      const last = copilotMessagesRef.current[copilotMessagesRef.current.length - 1];
      const isDuplicate = last && last.role === 'assistant' && last.content.trim() === assistantMsg.content.trim();
      if (!isDuplicate) {
        const updated = [...copilotMessagesRef.current, assistantMsg];
        copilotMessagesRef.current = updated;
        setCopilotMessages(updated);
        if (studyId) {
          api.updateStudy(studyId, { copilot_messages: updated as any }).catch(() => {});
        }
      }

      if (res.suggested_roles && res.suggested_roles.length > 0) {
        setSuggestedRoles(res.suggested_roles);
      }
    } catch (err) {
      const refusal = readOnlyRefusal(err);
      if (refusal) {
        // Read-only refusal: relay the backend's message as a plain reply — no
        // retry prompt, no persistence (the write would be refused again).
        const noticeMsg: CopilotMessage = {
          id: `msg_a_${Date.now()}`,
          role: 'assistant',
          content: refusal,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
        };
        const updated = [...copilotMessagesRef.current, noticeMsg];
        copilotMessagesRef.current = updated;
        setCopilotMessages(updated);
      } else {
        // Never synthesise a goal card on error — that would present a fabrication as AI success.
        const lastUserMsg = history.filter((m) => m.role === 'user').pop();
        const detail = toUserMessage(err, { timeoutMs: 300000 });
        const errorMsg: CopilotMessage = {
          id: `msg_a_${Date.now()}`,
          role: 'assistant',
          content: `I couldn't process that — ${detail}`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
          isRetryPrompt: true,
          retryContent: lastUserMsg?.content,
          errorDetail: detail,
          requestId: fromUnknownError(err).requestId ?? null,
        };
        const updated = [...copilotMessagesRef.current, errorMsg];
        copilotMessagesRef.current = updated;
        setCopilotMessages(updated);
        if (studyId) {
          api.updateStudy(studyId, { copilot_messages: updated as any }).catch(() => {});
        }
      }
    } finally {
      setIsCopilotTyping(false);
      isFetchingCopilotRef.current = false;
    }
  };

  const handleSendCopilotMessage = (text?: string) => {
    // Guard first: a second fast click must add nothing at all (it used to
    // append a duplicate user bubble before the in-flight check ran).
    if (isFetchingCopilotRef.current) return;
    const inputValue = step1InputRef.current?.value || '';
    const messageToSend = (
      typeof text === 'string' && text.trim() ? text : step1Prompt || promptInput || inputValue
    ).trim();
    if (!messageToSend) return;

    setStep1Prompt('');
    setPromptInput('');

    const userMsg: CopilotMessage = {
      id: `msg_u_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      role: 'user',
      content: messageToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
    };

    const updated = [...copilotMessagesRef.current, userMsg];
    copilotMessagesRef.current = updated;
    setCopilotMessages(updated);

    if (studyId) {
      api.updateStudy(studyId, { prompt: messageToSend, copilot_messages: updated as any }).catch(() => {});
    }

    fetchCopilotTurn(updated.map((m) => ({ role: m.role, content: m.content })));
  };

  /** Retry a failed turn: drop the error bubble and re-send the existing
   * history. Appending a new user message would feed the model its own error
   * line and leave the error visible after a successful retry. */
  const handleRetryCopilotMessage = (errorMessageId: string) => {
    if (isFetchingCopilotRef.current) return;
    const trimmed = copilotMessagesRef.current.filter((m) => m.id !== errorMessageId);
    if (trimmed.length === 0) return;
    copilotMessagesRef.current = trimmed;
    setCopilotMessages(trimmed);
    if (studyId) {
      api.updateStudy(studyId, { copilot_messages: trimmed as any }).catch(() => {});
    }
    fetchCopilotTurn(trimmed.map((m) => ({ role: m.role, content: m.content })));
  };

  const lastRolePromptRef = useRef<string>('');

  /** Role discovery is a visible, retryable step — an empty drawer with a live
   * "Generate Personas" button used to be the only sign that it had failed. */
  const loadSuggestedRoles = async (activePrompt: string) => {
    lastRolePromptRef.current = activePrompt;
    setIsLoadingRoles(true);
    setRoleError(null);
    try {
      const roles = await api.getSuggestedPersonaRoles(activePrompt);
      if (roles && roles.length > 0) {
        setSuggestedRoles(roles);
      } else {
        setRoleError('No roles came back for this goal. Retry, or add your own detail in the chat above.');
      }
    } catch (err: any) {
      setRoleError(
        `We couldn't suggest persona roles: ${err?.message || 'the request did not complete.'}`
      );
    } finally {
      setIsLoadingRoles(false);
    }
  };

  const handleRetrySuggestedRoles = () => {
    const activePrompt =
      lastRolePromptRef.current ||
      [...copilotMessagesRef.current].reverse().find((m) => m.role === 'user')?.content ||
      promptInput ||
      study?.prompt ||
      '';
    if (!activePrompt.trim()) {
      // A made-up business here would send the model researching nobody's idea.
      setRoleError('Describe your business idea first — there is nothing to suggest roles for.');
      return;
    }
    void loadSuggestedRoles(activePrompt);
  };

  const handleApproveGoal = async (summary?: string) => {
    setShowRoleSelection(true);
    // The drawer mounts below the fold — scroll to it so the click has visible feedback.
    setTimeout(() => {
      roleSelectionRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    }, 80);
    const activePrompt =
      summary ||
      [...copilotMessages].reverse().find((m) => m.role === 'user')?.content ||
      promptInput ||
      study?.prompt ||
      '';
    if (!activePrompt.trim()) {
      setRoleError('Describe your business idea first — there is nothing to suggest roles for.');
      return;
    }

    // 1. Trigger background autonomous research and dataset discovery
    if (studyId) {
      setEvidenceProbe({ state: 'searching' });
      api
        .triggerStudyResearch(studyId)
        .catch(() => {})
        .finally(() => probeEvidence());
    }

    // 2. Fetch suggested roles only when the copilot didn't already supply them,
    //    so re-approving never clobbers the user's count/selection tweaks.
    if (suggestedRoles.length === 0) {
      await loadSuggestedRoles(activePrompt);
    }

    if (studyId) {
      api.updateStudy(studyId, {
        prompt: activePrompt,
        step: 2,
        copilot_messages: copilotMessagesRef.current as any,
      }).catch(() => {});
    }
  };

  const handleToggleRole = (roleId: string) => {
    setSuggestedRoles((prev) =>
      prev.map((r) => {
        if (r.id === roleId) {
          const nextSelected = !r.selected;
          return {
            ...r,
            selected: nextSelected,
            count: nextSelected ? (r.count > 0 ? r.count : MAX_PERSONAS_PER_ROLE) : 0,
          };
        }
        return r;
      })
    );
  };

  const handleIncrementRole = (roleId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSuggestedRoles((prev) =>
      prev.map((r) =>
        r.id === roleId
          ? { ...r, count: Math.min(MAX_PERSONAS_PER_ROLE, r.count + 1), selected: true }
          : r
      )
    );
  };

  const handleDecrementRole = (roleId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSuggestedRoles((prev) =>
      prev.map((r) => {
        if (r.id === roleId) {
          const nextCount = Math.max(0, r.count - 1);
          return { ...r, count: nextCount, selected: nextCount > 0 };
        }
        return r;
      })
    );
  };

  const handleGeneratePersonas = async () => {
    setPersonaGenError(null);

    const activeRoles = suggestedRoles.filter((r) => r.selected && r.count > 0);
    const totalCount = activeRoles.reduce((sum, r) => sum + r.count, 0) || DEFAULT_PERSONA_COUNT;

    const allUserTexts = copilotMessagesRef.current
      .filter((m) => m.role === 'user')
      .map((m) => m.content)
      .join(' ');

    // No literal fallback: a made-up idea would yield personas for a business
    // nobody described. Both guards run BEFORE the step change so the user is
    // not moved away from the idea and roles they need to fix. The message is
    // written to both alerts because Generate exists in step 1 (role drawer)
    // and step 2 (persona panel), and only the current step's alert renders.
    const refuse = (message: string) => {
      setRoleError(message);
      setPersonaGenError(message);
    };
    const userPrompt = [allUserTexts, promptInput, study?.prompt ?? ''].find((t) => t.trim()) ?? '';
    if (!userPrompt) {
      refuse('Describe your business idea first — there is nothing to generate personas from.');
      return;
    }
    if (activeRoles.length === 0) {
      refuse('Pick at least one role (with a count of 1–3) before generating personas.');
      return;
    }
    setRoleError(null);
    setIsGeneratingPersonas(true);
    handleStepChange(2);
    // Word-boundary cut — slice(0, 50) mid-word produced titles like "…Students at".
    const derivedTitle = (() => {
      if (userPrompt.length <= 50) return userPrompt;
      const cut = userPrompt.slice(0, 50);
      const atWord = cut.lastIndexOf(' ') > 25 ? cut.slice(0, cut.lastIndexOf(' ')) : cut;
      return atWord.replace(/\s+(?:a|an|the|and|or|but|for|nor|on|at|to|from|by|with|in|of)$/i, '');
    })();
    const studyTitle = study?.title && study.title !== 'Untitled Study' ? study.title : derivedTitle;

    try {
      // Only the roles the user asked for: a selected zero-count role (model-
      // suggested lists can carry one) is a 422 on the server, not ignored.
      const result = await api.generateStudyPersonasDetailed(
        study?.id || studyId,
        userPrompt,
        activeRoles,
        studyTitle
      );
      const generated = result.personas;
      setPersonaFailedRoles(result.failed_roles);
      setPersonaServedBy(result.served_by);

      setPersonas(generated);
      setSelectedPersonaIds(generated.map((p) => p.id));
      if (generated[0]) setActiveInterviewPersonaId(generated[0].id);

      if (studyId) {
        await api.updateStudy(studyId, {
          title: studyTitle,
          prompt: userPrompt,
          persona_count: generated.length || totalCount,
          persona_ids: generated.map((p) => p.id),
          personas_data: generated as any,
          step: 2,
        });
      }
    } catch (err: any) {
      const refusal = readOnlyRefusal(err);
      if (refusal) {
        setReadOnlyNotice(refusal);
      } else {
        setPersonaGenError(toUserMessage(err, { timeoutMs: 300000 }));
        setPersonaGenRequestId(fromUnknownError(err).requestId ?? null);
      }
    } finally {
      setIsGeneratingPersonas(false);
    }
  };

  const handleRemovePersona = (personaId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const nextPersonas = personas.filter((p) => p.id !== personaId);
    setPersonas(nextPersonas);
    setSelectedPersonaIds((prev) => prev.filter((id) => id !== personaId));
    if (studyId) {
      api.updateStudy(studyId, {
        personas_data: nextPersonas as any,
        persona_count: nextPersonas.length,
        persona_ids: nextPersonas.map((p) => p.id),
      }).catch(() => {});
    }
  };

  const handleGenerateScript = async () => {
    if (!studyId) return;
    setIsGeneratingScript(true);
    setScriptError(null);
    try {
      const res = await api.generateStudyScriptQuestions(studyId, study?.prompt || promptInput);
      if (res.questions && res.questions.length > 0) {
        setQuestions(res.questions);
        // Only a model-written script counts as "generated"; a canned starter
        // script must keep the template label (honesty over convenience).
        const fromLlm = res.source === 'llm';
        setScriptSource(fromLlm ? 'llm' : 'fallback_static');
        setScriptGenerated(fromLlm);
        try {
          if (fromLlm) localStorage.setItem(`bebshax_script_generated_${studyId}`, '1');
          else localStorage.removeItem(`bebshax_script_generated_${studyId}`);
        } catch {
          // storage unavailable — the label just resets on the next reload
        }
        api.updateStudy(studyId, { script_questions: res.questions }).catch(() => {});
      } else {
        setScriptError('The generator returned no questions. Your existing script is unchanged — try again.');
      }
    } catch (err: any) {
      const refusal = readOnlyRefusal(err);
      if (refusal) {
        setReadOnlyNotice(refusal);
      } else {
        // Silently swallowing this left the user staring at unchanged questions
        // after a 30-120s wait with no explanation.
        setScriptError(
          `${err?.message || 'The question generator did not respond.'} Your existing script is unchanged.`
        );
      }
    } finally {
      setIsGeneratingScript(false);
    }
  };

  // Step 4: Batch Interviews Execution (async job + polling)
  const batchPollCancelledRef = useRef<boolean>(false);
  useEffect(() => {
    return () => {
      batchPollCancelledRef.current = true;
    };
  }, []);

  const handleRunBatchInterviews = async () => {
    if (!studyId) return;
    setIsBatchRunning(true);
    batchPollCancelledRef.current = false;

    const initialMap: Record<string, 'in_progress'> = {};
    personas.forEach((p) => {
      initialMap[p.id] = 'in_progress';
    });
    setInterviewStatusMap(initialMap);
    setInterviewFailureReasons({});
    setBatchError(null);

    const applyJobStatuses = (job: any) => {
      const map: Record<string, 'pending' | 'in_progress' | 'completed' | 'failed'> = {};
      const reasons: Record<string, string> = {};
      personas.forEach((p) => {
        const entry = job?.personas?.[p.id];
        map[p.id] = entry ? entry.status : 'pending';
        if (entry?.status === 'failed' && typeof entry.error === 'string' && entry.error) {
          reasons[p.id] = entry.error;
        }
      });
      setInterviewStatusMap(map);
      setInterviewFailureReasons(reasons);
    };

    try {
      const start = await api.runBatchStudyInterviews(studyId, selectedPersonaIds, questions);
      const jobId = start?.job_id;
      if (!jobId) throw new Error('Batch job did not start');
      applyJobStatuses(start);

      // Poll until the job leaves "running" (real batches run for many minutes).
      let job: any = start;
      while (!batchPollCancelledRef.current && job?.status === 'running') {
        await new Promise((r) => setTimeout(r, 5000));
        try {
          job = await api.getBatchRunStatus(studyId, jobId);
          applyJobStatuses(job);
        } catch (pollErr: any) {
          if (pollErr?.status === 404) {
            // Job lost (e.g. backend restart) — everything unfinished is failed.
            const lostReason = toUserMessage(pollErr);
            setBatchError({ message: lostReason, requestId: fromUnknownError(pollErr).requestId ?? null });
            setInterviewStatusMap((prev) => {
              const map = { ...prev };
              const reasons: Record<string, string> = {};
              Object.keys(map).forEach((pid) => {
                if (map[pid] === 'in_progress' || map[pid] === 'pending') {
                  map[pid] = 'failed';
                  reasons[pid] = lostReason;
                }
              });
              setInterviewFailureReasons((prevReasons) => ({ ...prevReasons, ...reasons }));
              return map;
            });
            break;
          }
          // Transient poll error: keep polling.
        }
      }
      await api.listStudyInterviews(studyId).catch(() => []);
    } catch (err: any) {
      const refusal = readOnlyRefusal(err);
      if (refusal) {
        setReadOnlyNotice(refusal);
        setInterviewStatusMap({});
      } else {
        // Whole-batch failure: everything selected is failed. Nothing "completed".
        const reason = toUserMessage(err, { timeoutMs: 30000 });
        setBatchError({ message: reason, requestId: fromUnknownError(err).requestId ?? null });
        const failedMap: Record<string, 'pending' | 'failed'> = {};
        const reasons: Record<string, string> = {};
        personas.forEach((p) => {
          const selected = selectedPersonaIds.includes(p.id);
          failedMap[p.id] = selected ? 'failed' : 'pending';
          if (selected) reasons[p.id] = reason;
        });
        setInterviewStatusMap(failedMap);
        setInterviewFailureReasons(reasons);
      }
    } finally {
      setIsBatchRunning(false);
    }
  };

  const handleSendInterviewMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = userInputMessage.trim();
    if (!text || isSimulating || !activeInterviewPersonaId) return;

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
        if (studyId) {
          localStorage.setItem(`bebshax_conv_${studyId}_${activeInterviewPersonaId}`, conv.id);
        }
        const res = await api.sendMessage(conv.id, text);
        setChatMessages((prev) => [...prev, res.assistantTurn]);
      }
    } catch (err: any) {
      const refusal = readOnlyRefusal(err);
      if (refusal) {
        setReadOnlyNotice(refusal);
      } else {
        // Honest failure: show the error in the transcript instead of silently
        // dropping the turn (the user otherwise watches their question vanish).
        setChatMessages((prev) => [
          ...prev,
          {
            id: `turn_err_${Date.now()}`,
            role: 'assistant',
            content: `⚠ Interview turn failed: ${err?.message || 'request timed out'}. Your question was not answered — please retry.`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
          },
        ]);
      }
    } finally {
      setIsSimulating(false);
    }
  };

  // Step 5: Report Synthesis
  const [reportError, setReportError] = useState<string | null>(null);
  const handleGenerateFinalReport = async () => {
    if (!studyId) return;
    setIsGeneratingReport(true);
    setReportError(null);
    // Move to the report step first: synthesis can take minutes, and waiting
    // on a disabled button with no feedback looks like nothing happened.
    handleStepChange(5);
    try {
      const rep = await api.generateStudyReport(studyId);
      setReport(rep);
      setAvailableReports((prev) => [rep, ...prev.filter((r) => r.id !== rep.id)]);
      // The freshly-generated report is what earns 'completed' status.
      handleStepChange(5, { reportReady: true });
    } catch (err: any) {
      const refusal = readOnlyRefusal(err);
      if (refusal) {
        setReadOnlyNotice(refusal);
      } else {
        // Honest failure: the error is shown on the report step with a retry.
        setReportError(err?.message || 'Report generation failed. Please retry.');
      }
    } finally {
      setIsGeneratingReport(false);
    }
  };

  const copyReportMarkdown = () => {
    if (!report) return;
    const md = `# ${report.title || 'Research Report'}\n\n## Executive Summary\n${report.executive_summary}\n\n## Key Findings\n${(report.key_findings || []).map((f) => `- ${f}`).join('\n')}\n\n## Recommendations\n${(report.recommendations || []).map((r) => `- ${r}`).join('\n')}`;
    navigator.clipboard.writeText(md);
    setCopiedToast(true);
    setTimeout(() => setCopiedToast(false), 2500);
  };

  const exportReportMarkdown = () => {
    if (!report) return;
    const md = `# ${report.title || 'Research Report'}\n\n## Executive Summary\n${report.executive_summary}\n\n## Key Findings\n${(report.key_findings || []).map((f) => `- ${f}`).join('\n')}\n\n## Recommendations\n${(report.recommendations || []).map((r) => `- ${r}`).join('\n')}`;
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(report.title || 'Research_Report').replace(/\s+/g, '_')}_V${report.version || 1}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  useEffect(() => {
    if (initialPrompt && initialPrompt.trim() && initialPromptHandledRef.current !== initialPrompt.trim()) {
      // Never clobber an existing conversation (restored or in progress).
      if (copilotMessagesRef.current.length > 0) return;
      initialPromptHandledRef.current = initialPrompt.trim();
      const userMsg: CopilotMessage = {
        id: `msg_u_${Date.now()}`,
        role: 'user',
        content: initialPrompt.trim(),
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
      };
      copilotMessagesRef.current = [userMsg];
      setCopilotMessages([userMsg]);
      if (studyId) {
        api.updateStudy(studyId, { copilot_messages: [userMsg] as any }).catch(() => {});
      }
      fetchCopilotTurn([{ role: 'user', content: initialPrompt.trim() }]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPrompt]);

  const stepLabels = [
    { num: 1, label: 'Context', sub: 'Describe your idea' },
    { num: 2, label: 'Personas', sub: 'Meet your synthetic customers' },
    { num: 3, label: 'Script', sub: 'Plan the questions' },
    { num: 4, label: 'Interviews', sub: 'Run the interviews' },
    { num: 5, label: 'Report', sub: 'Get your report' },
  ];

  // Forward stepper navigation unlocks only when the prior step produced its
  // artifact; going backward (or staying) is always free.
  const goalApproved = showRoleSelection || personas.length > 0;
  const hasInterviewActivity =
    chatMessages.length > 0 ||
    conversationId !== null ||
    Object.values(interviewStatusMap).some((s) => s === 'completed' || s === 'in_progress');
  const hasReportArtifact = report !== null || availableReports.length > 0;
  const isStepUnlocked = (stepNum: number): boolean => {
    if (stepNum <= currentStep) return true;
    if (stepNum <= 3) return goalApproved;
    // Interviews need respondents AND questions: the backend refuses a batch
    // run without a script (script_required) rather than asking canned ones.
    if (stepNum === 4) return personas.length > 0 && questions.length > 0;
    return hasReportArtifact || hasInterviewActivity || personas.length > 0;
  };
  const stepLockReason = (stepNum: number): string =>
    stepNum <= 3
      ? 'Approve a research goal in Context first'
      : stepNum === 4
        ? personas.length > 0
          ? 'Generate or write interview questions first'
          : 'Generate personas first'
        : 'Generate personas or run an interview first';

  // Least-grounded claims across the persona panel — surfaced in the report as
  // "assumptions to verify with real customers". SYNTHETIC (no grounding at
  // all) ranks ahead of INFERRED. Purely presentational, from existing state.
  const verificationAssumptions: { value: string; provenance: string; personaName: string }[] = (() => {
    const out: { value: string; provenance: string; personaName: string }[] = [];
    for (const p of personas) {
      const prov = p.detailed_attributes?.claim_provenance as
        | Record<string, { value?: string; provenance?: string }[]>
        | undefined;
      if (!prov) continue;
      for (const group of Object.values(prov)) {
        if (!Array.isArray(group)) continue;
        for (const entry of group) {
          if (entry?.value && (entry.provenance === 'SYNTHETIC' || entry.provenance === 'INFERRED')) {
            out.push({ value: entry.value, provenance: entry.provenance, personaName: p.name });
          }
        }
      }
    }
    out.sort((a, b) => (a.provenance === b.provenance ? 0 : a.provenance === 'SYNTHETIC' ? -1 : 1));
    return out.slice(0, 3);
  })();

  // Close the persona detail modal and hand focus back to the card button
  // that opened it, so keyboard users are not dropped at the page top.
  const closePersonaModal = () => {
    setViewingPersona(null);
    personaModalTriggerRef.current?.focus();
    personaModalTriggerRef.current = null;
  };

  useEffect(() => {
    if (!viewingPersona) return;
    const focusables = () =>
      Array.from(
        personaModalRef.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        ) ?? []
      ).filter((el) => !el.hasAttribute('disabled'));
    // Move focus into the dialog on open (aria-modal without a trap strands AT users).
    focusables()[0]?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      // Topmost-surface-wins: consume the key so popover/drawer handlers skip it.
      if (e.defaultPrevented) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        closePersonaModal();
        return;
      }
      if (e.key === 'Tab') {
        // Minimal focus trap: Tab / Shift+Tab loop inside the dialog while open.
        const els = focusables();
        if (els.length === 0) return;
        const first = els[0];
        const last = els[els.length - 1];
        const active = document.activeElement as HTMLElement | null;
        const inside = !!active && !!personaModalRef.current?.contains(active);
        if (e.shiftKey && (!inside || active === first)) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && (!inside || active === last)) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    // Capture phase: the modal beats bubble-phase Escape listeners (popover/drawer).
    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewingPersona]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', background: 'transparent', color: 'var(--text-main)' }}>
      {/* Top Header with Stepper */}
      <header
        className="bx-appheader"
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 30,
          padding: '12px clamp(12px, 3vw, 24px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '10px 16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', minWidth: 0, flex: '1 1 auto' }}>
          <button
            type="button"
            onClick={onExit}
            style={{
              background: 'transparent',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              borderRadius: '8px',
              padding: '6px 12px',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            ← Exit Study
          </button>
          <div
            title={study?.title || 'Research Workflow'}
            style={{
              fontSize: '0.95rem',
              fontWeight: 600,
              color: 'var(--text-main)',
              minWidth: 0,
              maxWidth: '360px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {study?.title || 'Research Workflow'}
          </div>
        </div>

        {/* 5-Step Stepper */}
        <nav aria-label="Study steps" className="bx-stepper">
          <span className="bx-step-count" aria-hidden="true">
            Step {currentStep} of {stepLabels.length}
          </span>
          {stepLabels.map((s, idx) => {
            const isDone = s.num < currentStep;
            const isCurrent = s.num === currentStep;
            const unlocked = isStepUnlocked(s.num);
            return (
              <React.Fragment key={s.num}>
                {idx > 0 && <div className="bx-step-rule" style={{ width: '16px', height: '1px', background: isDone ? 'var(--accent-teal)' : 'var(--border-subtle)' }} />}
                <button
                  type="button"
                  onClick={() => {
                    if (unlocked) handleStepChange(s.num);
                  }}
                  aria-disabled={!unlocked}
                  aria-current={isCurrent ? 'step' : undefined}
                  aria-label={`Step ${s.num}: ${s.label}${isDone ? ' (done)' : ''}`}
                  tabIndex={unlocked ? 0 : -1}
                  title={unlocked ? s.sub : stepLockReason(s.num)}
                  className="bx-step"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '6px 12px',
                    borderRadius: '999px',
                    border: isCurrent ? '1px solid var(--accent-teal)' : '1px solid transparent',
                    background: isCurrent ? 'var(--accent-subtle)' : isDone ? 'var(--fill-soft)' : 'transparent',
                    color: isCurrent ? 'var(--accent-cyan)' : isDone ? 'var(--accent-teal)' : 'var(--text-secondary)',
                    fontSize: '0.8rem',
                    fontWeight: isCurrent || isDone ? 600 : 400,
                    cursor: unlocked ? 'pointer' : 'not-allowed',
                    opacity: unlocked ? 1 : 0.45,
                    flexShrink: 0,
                  }}
                >
                  <div
                    style={{
                      width: '18px',
                      height: '18px',
                      borderRadius: '50%',
                      background: isDone ? 'var(--accent-teal)' : isCurrent ? 'var(--accent-cyan)' : 'var(--border-subtle)',
                      color: isDone || isCurrent ? 'var(--bg-pure)' : 'var(--text-secondary)',
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    {isDone ? <Check size={11} strokeWidth={3} /> : s.num}
                  </div>
                  <span className={`bx-step-label${isCurrent ? ' bx-step-label--current' : ''}`} style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', lineHeight: 1.25 }}>
                    <span>{s.label}</span>
                    <span className="bx-step-sub">{s.sub}</span>
                  </span>
                </button>
              </React.Fragment>
            );
          })}
        </nav>

        {isReadOnly && (
          <div
            role="note"
            style={{
              flexBasis: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: 'var(--fill-soft)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              padding: '6px 12px',
              fontSize: '0.8rem',
              color: 'var(--text-secondary)',
            }}
          >
            <Lock size={13} color="var(--accent-cyan)" aria-hidden="true" />
            <span>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Example study — read-only.</span>{' '}
              Create your own study to run these steps.
            </span>
          </div>
        )}
      </header>

      {/* Main Workflow Container (the dashboard shell owns the <main> landmark) */}
      <div style={{ flex: 1, padding: '28px clamp(14px, 4vw, 40px)', maxWidth: '1280px', width: '100%', margin: '0 auto' }}>
        {readOnlyNotice && (
          <div
            role="status"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: 'var(--fill-soft)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '10px',
              padding: '10px 14px',
              marginBottom: '20px',
              fontSize: '0.84rem',
              color: 'var(--text-secondary)',
            }}
          >
            <Lock size={14} color="var(--accent-cyan)" aria-hidden="true" />
            <span>{readOnlyNotice}</span>
          </div>
        )}
        {/* ============================================================
            STEP 1: CONTEXT & ASSUMPTION GATHERING
           ============================================================ */}
        {currentStep === 1 && (
          <div ref={stepViewRef} style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <Step1Context
              copilotChatRef={copilotChatRef}
              copilotMessages={copilotMessages}
              isCopilotTyping={isCopilotTyping}
              showRoleSelection={showRoleSelection}
              handleApproveGoal={handleApproveGoal}
              handleSendCopilotMessage={handleSendCopilotMessage}
              handleRetryCopilotMessage={handleRetryCopilotMessage}
              step1InputRef={step1InputRef}
              step1Prompt={step1Prompt}
              setStep1Prompt={setStep1Prompt}
              roleSelectionRef={roleSelectionRef}
              suggestedRoles={suggestedRoles}
              isLoadingRoles={isLoadingRoles}
              roleError={roleError}
              handleRetrySuggestedRoles={handleRetrySuggestedRoles}
              isGeneratingPersonas={isGeneratingPersonas}
              handleGeneratePersonas={handleGeneratePersonas}
              handleToggleRole={handleToggleRole}
              handleIncrementRole={handleIncrementRole}
              handleDecrementRole={handleDecrementRole}
              evidenceProbe={evidenceProbe}
              onNavigateToEvidence={studyId ? () => navigate(`/research/${studyId}/evidence`) : undefined}
              onRunEvidence={studyId && !isReadOnly ? handleRunEvidenceResearch : undefined}
              isReadOnly={isReadOnly}
            />
          </div>
        )}

        {/* ============================================================
            STEP 2: SYNTHETIC PERSONAS
           ============================================================ */}
        {currentStep === 2 && (
          <div ref={stepViewRef} style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <Step2Personas
              personas={personas}
              personaGenError={personaGenError}
              personaGenRequestId={personaGenRequestId}
              failedRoles={personaFailedRoles}
              personaServedBy={personaServedBy}
              isGeneratingPersonas={isGeneratingPersonas}
              suggestedRoles={suggestedRoles}
              handleGeneratePersonas={handleGeneratePersonas}
              handleStepChange={handleStepChange}
              handleRemovePersona={handleRemovePersona}
              personaModalTriggerRef={personaModalTriggerRef}
              setViewingPersona={setViewingPersona}
              isStepUnlocked={isStepUnlocked}
              onNavigateToEvidence={studyId ? () => navigate(`/research/${studyId}/evidence`) : undefined}
              isReadOnly={isReadOnly}
            />
          </div>
        )}

        {/* ============================================================
            STEP 3: INTERVIEW SCRIPT & QUESTIONS
           ============================================================ */}
        {currentStep === 3 && (
          <div ref={stepViewRef} style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <Step3Script
              studyId={studyId}
              questions={questions}
              setQuestions={setQuestions}
              newQuestion={newQuestion}
              setNewQuestion={setNewQuestion}
              handleGenerateScript={handleGenerateScript}
              isGeneratingScript={isGeneratingScript}
              scriptError={scriptError}
              scriptGenerated={scriptGenerated}
              scriptSource={scriptSource}
              handleStepChange={handleStepChange}
              isReadOnly={isReadOnly}
            />
          </div>
        )}

        {/* ============================================================
            STEP 4: SYNTHETIC INTERVIEWS & SIMULATION
           ============================================================ */}
        {currentStep === 4 && (
          <div ref={stepViewRef} style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <Step4Interviews
              personas={personas}
              isBatchRunning={isBatchRunning}
              handleRunBatchInterviews={handleRunBatchInterviews}
              onCancelBatch={() => { batchPollCancelledRef.current = true; }}
              isGeneratingReport={isGeneratingReport}
              handleGenerateFinalReport={handleGenerateFinalReport}
              handleStepChange={handleStepChange}
              interviewStatusMap={interviewStatusMap}
              interviewFailureReasons={interviewFailureReasons}
              batchError={batchError}
              activeInterviewPersonaId={activeInterviewPersonaId}
              setActiveInterviewPersonaId={setActiveInterviewPersonaId}
              setChatMessages={setChatMessages}
              setConversationId={setConversationId}
              interviewChatRef={interviewChatRef}
              chatMessages={chatMessages}
              isSimulating={isSimulating}
              handleSendInterviewMessage={handleSendInterviewMessage}
              userInputMessage={userInputMessage}
              setUserInputMessage={setUserInputMessage}
              isReadOnly={isReadOnly}
            />
          </div>
        )}

        {/* ============================================================
            STEP 5: COMPREHENSIVE FINAL REPORT
           ============================================================ */}
        {currentStep === 5 && (
          <div ref={stepViewRef} style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
            <Step5Report
              study={study}
              personas={personas}
              report={report}
              availableReports={availableReports}
              reportError={reportError}
              isGeneratingReport={isGeneratingReport}
              copiedToast={copiedToast}
              copyReportMarkdown={copyReportMarkdown}
              exportReportMarkdown={exportReportMarkdown}
              handleGenerateFinalReport={handleGenerateFinalReport}
              verificationAssumptions={verificationAssumptions}
              isReadOnly={isReadOnly}
            />
          </div>
        )}
      </div>

      {/* Viewing Full Persona Modal */}
      {viewingPersona && (
        <PersonaDetailModal
          viewingPersona={viewingPersona}
          personaModalRef={personaModalRef}
          closePersonaModal={closePersonaModal}
        />
      )}
    </div>
  );
};
