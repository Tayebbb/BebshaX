import React, { useState, useEffect, useLayoutEffect, useRef } from 'react';
import { Check, ChevronLeft, Lock } from 'lucide-react';
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
  ResearchGoalCardData,
  isTemplateReply,
} from './workflow/types';
import { fromUnknownError, toUserMessage } from '../../../utils/apiError';
import { Step1Context } from './workflow/Step1Context';
import { Step2Personas } from './workflow/Step2Personas';
import { Step3Script } from './workflow/Step3Script';
import { Step4Interviews } from './workflow/Step4Interviews';
import { Step5Report } from './workflow/Step5Report';
import { PersonaDetailModal } from './workflow/PersonaDetailModal';
import { ConfirmDialog } from '../../common/ConfirmDialog';
import { EvidenceProbe, nextEvidenceProbe } from './workflow/evidenceProbe';

const EVIDENCE_PROBE_ATTEMPTS = 40;
const EVIDENCE_PROBE_INTERVAL_MS = 9000;
/** Probe states from which Step 1 may start or retry the evidence run. */
const EVIDENCE_RUNNABLE_STATES: EvidenceProbe['state'][] = ['not_run', 'failed', 'timeout'];
import { getStudyDraftRetry, STUDY_SAVE_CHANGED, type StudySaveState } from '../../../services/studyPersistence';
import { getSessionEpoch } from '../../../services/session';
import { pollSerial } from '../../../services/polling';
import { reportMarkdown } from '../../../utils/exports';
import { copyText } from '../../../utils/clipboard';
import { useRouteReady } from '../../../performance/routeTiming';

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
  initialStep,
  initialType = 'interviews',
  initialPrompt = '',
  onExit,
  onStepChange,
}) => {
  const [currentStep, setCurrentStep] = useState<number>(initialStep ?? 1);
  const [saveState, setSaveState] = useState<StudySaveState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const { navigate, currentPath, currentSearch } = useNavigation();
  const studyEpochRef = useRef({ active: false });
  const previousStudyIdRef = useRef(studyId);
  useLayoutEffect(() => {
    if (initialStep !== undefined) setCurrentStep(Math.max(1, Math.min(5, initialStep)));
  }, [initialStep]);
  useLayoutEffect(() => {
    const epoch = { active: true };
    studyEpochRef.current = epoch;
    if (previousStudyIdRef.current !== studyId) {
    previousStudyIdRef.current = studyId;
    setStudy(null);
    setLoadError(null);
    setSaveState(null);
    setReport(null);
    setAvailableReports([]);
    setPersonas([]);
    setSelectedPersonaIds([]);
    setQuestions([]);
    setSuggestedRoles([]);
    setCopilotMessages([]);
    copilotMessagesRef.current = [];
    setIsCopilotTyping(false);
    isFetchingCopilotRef.current = false;
    initialPromptHandledRef.current = null;
    pendingInitialPromptRef.current = null;
    setPromptInput(initialPrompt);
    setReportError(null);
    setShowRoleSelection(false);
    setScriptGenerated(false);
    setScriptSource(null);
    setCurrentStep(initialStep ?? 1);
    }
    return () => { epoch.active = false; };
  }, [studyId]);
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
  const [personaErrorKind, setPersonaErrorKind] = useState<'generation' | 'save'>('generation');
  const [personaSaveRetry, setPersonaSaveRetry] = useState<(() => Promise<Study>) | null>(null);
  const [isRetryingPersonaSave, setIsRetryingPersonaSave] = useState(false);
  const hasUnresolvedDraftFailure = (personaErrorKind === 'save' && Boolean(personaGenError))
    || saveState?.state === 'unsaved' || saveState?.state === 'conflict';
  const personaSaveControllerRef = useRef<AbortController | null>(null);
  const personaSavePendingRef = useRef(false);
  const sessionEpoch = getSessionEpoch();
  const [personaGenRequestId, setPersonaGenRequestId] = useState<string | null>(null);
  const [personaFailedRoles, setPersonaFailedRoles] = useState<FailedPersonaRole[]>([]);
  const [personaServedBy, setPersonaServedBy] = useState<string[]>([]);
  const [viewingPersona, setViewingPersona] = useState<Persona | null>(null);

  useLayoutEffect(() => {
    const controller = new AbortController();
    personaSaveControllerRef.current = controller;
    personaSavePendingRef.current = false;
    setPersonaSaveRetry(null);
    setIsRetryingPersonaSave(false);
    return () => { controller.abort(); };
  }, [studyId, currentStep, currentPath, currentSearch, sessionEpoch]);

  useEffect(() => {
    const controller = personaSaveControllerRef.current;
    if (!studyId || currentStep !== 2 || isReadOnly || personaErrorKind !== 'save' || !personaGenError
      || !controller || controller.signal.aborted || personaSavePendingRef.current) return;
    const retry = getStudyDraftRetry(api.getStoredUser()?.id ?? 'anonymous', studyId, controller.signal);
    setPersonaSaveRetry(() => retry ?? null);
  }, [studyId, currentStep, currentPath, currentSearch, sessionEpoch, isReadOnly, personaErrorKind, personaGenError]);

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
  const [isRestoringInterview, setIsRestoringInterview] = useState(false);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const [isBatchRunning, setIsBatchRunning] = useState(false);
  const [userInputMessage, setUserInputMessage] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [interviewStatusMap, setInterviewStatusMap] = useState<Record<string, 'pending' | 'in_progress' | 'completed' | 'failed'>>({});
  // Per-persona failure reasons reported by the batch job, plus the whole-batch
  // error (with its request id) when the job itself could not start.
  const [interviewFailureReasons, setInterviewFailureReasons] = useState<Record<string, string>>({});
  const [batchError, setBatchError] = useState<{ message: string; requestId: string | null } | null>(null);
  // Saved interview ids per persona (from the server), so a reload can reopen
  // transcripts without depending on this tab's localStorage.
  const [interviewIdByPersona, setInterviewIdByPersona] = useState<Record<string, string>>({});
  // Destructive panel actions ask first when interviews or a report already
  // exist: they stay attributable to the old panel, not the new one.
  const [pendingPanelAction, setPendingPanelAction] = useState<
    | { kind: 'remove'; personaId: string; personaName: string }
    | { kind: 'regenerate' }
    | null
  >(null);
  const [panelActionBusy, setPanelActionBusy] = useState(false);
  const [panelActionError, setPanelActionError] = useState<string | null>(null);

  // Step 5: Final Report
  const [report, setReport] = useState<StudyReport | null>(null);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [availableReports, setAvailableReports] = useState<StudyReport[]>([]);
  const [reportsLoading, setReportsLoading] = useState(true);
  const [copiedToast, setCopiedToast] = useState(false);
  const [isGeneratingScript, setIsGeneratingScript] = useState(false);
  useRouteReady(Boolean(loadError) || Boolean(study && study.id === studyId &&
    (currentStep !== 2 || !isGeneratingPersonas) &&
    (currentStep !== 3 || !isGeneratingScript) &&
    (currentStep !== 4 || !isRestoringInterview) &&
    (currentStep !== 5 || (!reportsLoading && (report || !isGeneratingReport)))),
    loadError || (currentStep === 2 && personaGenError) || (currentStep === 3 && scriptError) || (currentStep === 4 && restoreError) ? 'error' : 'content');

  // Step 1: state of the supporting-evidence attempt for this study. Read from
  // the evidence summary the Evidence Laboratory already serves — no new
  // endpoint, and it never blocks the copilot path.
  const [evidenceProbe, setEvidenceProbe] = useState<EvidenceProbe>({ state: 'checking' });
  const evidenceProbeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scriptGenerationPendingRef = useRef(false);
  /** Summary of the goal card the user approved; drives which card reads as approved. */
  const [approvedGoalSummary, setApprovedGoalSummary] = useState<string | null>(null);

  const copilotMessagesRef = useRef<CopilotMessage[]>([]);
  const isFetchingCopilotRef = useRef<boolean>(false);
  const initialPromptHandledRef = useRef<string | null>(null);
  const pendingInitialPromptRef = useRef<CopilotMessage | null>(null);
  const roleSelectionRef = useRef<HTMLDivElement | null>(null);
  const copilotChatRef = useRef<HTMLDivElement | null>(null);
  const interviewChatRef = useRef<HTMLDivElement | null>(null);
  const step1InputRef = useRef<HTMLTextAreaElement | null>(null);
  const personaModalTriggerRef = useRef<HTMLElement | null>(null);
  const personaModalRef = useRef<HTMLDivElement | null>(null);
  const interviewEpochRef = useRef({ active: false, pending: false, restoring: false, restoreFailed: false, revision: 0 });

  useLayoutEffect(() => {
    const epoch = {
      active: true, pending: false, restoreFailed: false, revision: 0,
      restoring: Boolean(studyId && activeInterviewPersonaId && localStorage.getItem(
        `bebshax_conv_${studyId}_${activeInterviewPersonaId}`,
      )),
    };
    interviewEpochRef.current = epoch;
    setIsSimulating(false);
    setRestoreError(null);
    setIsRestoringInterview(epoch.restoring);
    setUserInputMessage('');
    setConversationId(null);
    setChatMessages([]);
    return () => { epoch.active = false; };
  }, [studyId, activeInterviewPersonaId]);

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
    const epoch = interviewEpochRef.current;
    const revision = epoch.revision;
    const storedConvId = localStorage.getItem(
      `bebshax_conv_${studyId}_${activeInterviewPersonaId}`
    );
    if (!storedConvId) {
      epoch.restoring = false;
      setIsRestoringInterview(false);
      setConversationId(null);
      setChatMessages([]);
      return;
    }
    epoch.restoring = true;
    epoch.restoreFailed = false;
    setRestoreError(null);
    setIsRestoringInterview(true);
    setConversationId(storedConvId);
    let cancelled = false;
    api
      .getConversation(storedConvId)
      .then((conv) => {
        if (cancelled || !epoch.active || epoch.revision !== revision) return;
        if (!conv) throw new Error('Saved conversation is unavailable.');
        setConversationId(conv.id);
        setChatMessages(conv.turns || []);
      })
      .catch((error: unknown) => {
        if (!cancelled && epoch.active && epoch.revision === revision) {
          epoch.restoreFailed = true;
          setRestoreError(toUserMessage(error));
        }
      })
      .finally(() => {
        if (!cancelled && epoch.active && epoch.revision === revision) {
          epoch.restoring = false;
          setIsRestoringInterview(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [studyId, activeInterviewPersonaId, restoreAttempt]);

  const handleStepChange = (newStep: number) => {
    const epoch = studyEpochRef.current;
    if (!epoch.active) return;
    const clamped = Math.max(1, Math.min(newStep, 5));
    setCurrentStep(clamped);
    onStepChange?.(clamped);
    // Read-only example studies never PATCH — the write gate would refuse.
    if (studyId && !isReadOnly && epoch.active) {
      // 'completed' is earned by a generated report — never by visiting step 5.
      // The prompt is not resent here: after approval it holds the approved goal,
      // and the copy in local state can be older (live 2026-09-14: a step change
      // reverted the goal to the first chat message, which every interview then
      // received as its objective).
      api
        .updateStudy(studyId, {
          step: clamped,
          copilot_messages: copilotMessagesRef.current as any,
          suggested_roles: suggestedRoles,
          script_questions: questions,
        })
        .catch(() => {});
    }
  };

  // Restore full study state from DB on mount / refresh
  useEffect(() => {
    const onSave = (event: Event) => {
      const state = (event as CustomEvent<StudySaveState>).detail;
      if (state.studyId === studyId && state.epoch === getSessionEpoch()) setSaveState(state);
    };
    window.addEventListener(STUDY_SAVE_CHANGED, onSave);
    return () => window.removeEventListener(STUDY_SAVE_CHANGED, onSave);
  }, [studyId]);

  useEffect(() => {
    if (!studyId) return;
    const epoch = studyEpochRef.current;
    api
      .getStudy(studyId)
      .then((loaded) => {
        if (!epoch.active) return;
        if (!loaded) {
          setLoadError('This study is unavailable or could not be found.');
          return;
        }
        const draft = studyId ? api.getPendingStudyDraft(studyId) : undefined;
        const s = loaded ? { ...loaded, ...draft } : loaded;
        if (!epoch.active || !s) return;
        if (draft) setSaveState({ studyId, epoch: getSessionEpoch(), state: 'unsaved', message: 'Recovered unsaved changes. The server version has not been overwritten.' });
        setStudy(s);
        if (s.prompt) setPromptInput((current) => current || s.prompt || '');
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
            // Approval stores the card summary as the prompt.
            if (s.prompt) setApprovedGoalSummary(s.prompt);
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
        if (s.step && initialStep === undefined) {
          setCurrentStep(s.step);
        }
      })
      .catch((error: unknown) => { if (epoch.active) setLoadError(`The saved study could not be loaded: ${toUserMessage(error)}`); });

    void reloadReports();
    const controller = new AbortController();
    if (api.getPendingJobHandle(studyId, 'report')) {
      setIsGeneratingReport(true);
      void api.resumeStudyReport(studyId, controller.signal).then((saved) => {
        if (!epoch.active) return;
        setReport(saved);
        setAvailableReports((previous) => [saved, ...previous.filter((candidate) => candidate.id !== saved.id)]);
      }).catch((error: unknown) => {
        if (epoch.active && !controller.signal.aborted) {
          setReportErrorKind('generation');
          setReportError(toUserMessage(error));
        }
      }).finally(() => { if (epoch.active) setIsGeneratingReport(false); });
    }
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studyId]);

  // Report on the evidence attempt itself so step 2 never arrives unexplained.
  // A single GET; while a run is in flight it re-checks a bounded number of
  // times so "Looking for…" can actually resolve without a page reload. Runs
  // take minutes on free providers: 40 polls at 9 s follows one to its end
  // (live 2026-09-14 the probe gave up after ~30 s and reported "still
  // searching" for a run that had already failed).
  const probeEvidence = React.useCallback(
    async (attemptsLeft = EVIDENCE_PROBE_ATTEMPTS, epoch = studyEpochRef.current) => {
      if (!epoch.active) return;
      if (!studyId) {
        setEvidenceProbe({ state: 'not_run' });
        return;
      }
      try {
        const summary = await api.getEvidenceSummary(studyId);
        if (!epoch.active) return;
        const next = nextEvidenceProbe(summary, attemptsLeft);
        setEvidenceProbe(next);
        if (next.state === 'searching') {
          evidenceProbeTimerRef.current = setTimeout(() => {
            void probeEvidence(attemptsLeft - 1, epoch);
          }, EVIDENCE_PROBE_INTERVAL_MS);
        }
      } catch {
        if (epoch.active) setEvidenceProbe({ state: 'unavailable' });
      }
    },
    [studyId],
  );

  useEffect(() => {
    setEvidenceProbe({ state: 'checking' });
    probeEvidence();
    return () => {
      if (evidenceProbeTimerRef.current) clearTimeout(evidenceProbeTimerRef.current);
    };
  }, [probeEvidence]);

  /** Step 1's `not_run`, `failed` and `timeout` states can start (or retry) the
   * evidence run directly — same trigger + probe plumbing handleApproveGoal
   * already uses, so a failed run never forces a detour through the lab. */
  const handleRunEvidenceResearch = () => {
    const epoch = studyEpochRef.current;
    // Guard the one-frame window before re-render unmounts the button.
    if (!epoch.active || !studyId || !EVIDENCE_RUNNABLE_STATES.includes(evidenceProbe.state)) return;
    if (evidenceProbeTimerRef.current) clearTimeout(evidenceProbeTimerRef.current);
    setEvidenceProbe({ state: 'searching' });
    api
      .triggerStudyResearch(studyId)
      .catch(() => {})
      .finally(() => {
        if (epoch.active) return probeEvidence(EVIDENCE_PROBE_ATTEMPTS, epoch);
      });
  };

  const fetchCopilotTurn = async (history: { role: 'user' | 'assistant'; content: string }[]) => {
    const epoch = studyEpochRef.current;
    if (!epoch.active || isFetchingCopilotRef.current) return;
    isFetchingCopilotRef.current = true;
    setIsCopilotTyping(true);
    try {
      const res = await api.sendStudyCopilotMessage(history, initialType, studyId);
      if (!epoch.active) return;
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
      if (!epoch.active) return;
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
      if (epoch.active) {
        setIsCopilotTyping(false);
        isFetchingCopilotRef.current = false;
      }
    }
  };

  const handleSendCopilotMessage = (text?: string) => {
    // Guard first: a second fast click must add nothing at all (it used to
    // append a duplicate user bubble before the in-flight check ran).
    if (!studyEpochRef.current.active || isFetchingCopilotRef.current) return;
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
      // Before approval the latest idea text is the working prompt; once a goal
      // is approved the prompt IS that goal and only re-approval changes it.
      const goalApproved = approvedGoalSummary !== null || showRoleSelection;
      api.updateStudy(studyId, {
        ...(goalApproved ? {} : { prompt: messageToSend }),
        copilot_messages: updated as any,
      }).catch(() => {});
    }

    fetchCopilotTurn(updated.map((m) => ({ role: m.role, content: m.content })));
  };

  /** Retry a failed turn: drop the error bubble and re-send the existing
   * history. Appending a new user message would feed the model its own error
   * line and leave the error visible after a successful retry. */
  const handleRetryCopilotMessage = (errorMessageId: string) => {
    if (!studyEpochRef.current.active || isFetchingCopilotRef.current) return;
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
    const epoch = studyEpochRef.current;
    if (!epoch.active) return;
    lastRolePromptRef.current = activePrompt;
    setIsLoadingRoles(true);
    setRoleError(null);
    try {
      const roles = await api.getSuggestedPersonaRoles(activePrompt);
      if (!epoch.active) return;
      if (roles && roles.length > 0) {
        setSuggestedRoles(roles);
      } else {
        setRoleError('No roles came back for this goal. Retry, or add your own detail in the chat above.');
      }
    } catch (err: any) {
      if (!epoch.active) return;
      setRoleError(
        `We couldn't suggest persona roles: ${err?.message || 'the request did not complete.'}`
      );
    } finally {
      if (epoch.active) setIsLoadingRoles(false);
    }
  };

  const handleRetrySuggestedRoles = () => {
    if (!studyEpochRef.current.active) return;
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

  const handleApproveGoal = async (summary?: string, card?: ResearchGoalCardData) => {
    const epoch = studyEpochRef.current;
    if (!epoch.active) return;
    setShowRoleSelection(true);
    // The drawer mounts below the fold — scroll to it so the click has visible feedback.
    setTimeout(() => {
      if (epoch.active) roleSelectionRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
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

    // Role discovery is the visible response to the click — start it at once.
    // Re-approving the same goal never clobbers the user's count/selection
    // tweaks; approving a different proposal asks for roles that fit it.
    const switchingGoal = approvedGoalSummary !== null && approvedGoalSummary !== activePrompt;
    setApprovedGoalSummary(activePrompt);
    const rolesLoading = suggestedRoles.length === 0 || switchingGoal ? loadSuggestedRoles(activePrompt) : Promise.resolve();

    // Persist the approved goal BEFORE starting research. Research admission
    // snapshots the study (prompt, revision) and refuses with 409
    // research_input_changed when a PATCH lands in between — which is exactly
    // what firing both at once did (live 2026-09-14). The save is a pure DB write.
    if (studyId) {
      const audience = card?.target_audience?.trim();
      setStudy((current) => (current ? { ...current, prompt: activePrompt, ...(audience ? { target_audience: audience } : {}) } : current));
      try {
        await api.updateStudy(studyId, {
          prompt: activePrompt,
          step: 2,
          copilot_messages: copilotMessagesRef.current as any,
          // The card's audience feeds research, role suggestion and persona
          // prompts; it used to stay NULL after approval (live 2026-09-14).
          ...(audience ? { target_audience: audience } : {}),
        });
      } catch {
        // The save banner reports this; research still runs on the stored prompt.
      }
      if (!epoch.active) return;
      if (evidenceProbeTimerRef.current) clearTimeout(evidenceProbeTimerRef.current);
      setEvidenceProbe({ state: 'searching' });
      api
        .triggerStudyResearch(studyId)
        .catch(() => {})
        .finally(() => {
          if (epoch.active) return probeEvidence(EVIDENCE_PROBE_ATTEMPTS, epoch);
        });
    }

    await rolesLoading;
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
    const epoch = studyEpochRef.current;
    if (!epoch.active || isGeneratingPersonas || personaSavePendingRef.current || hasUnresolvedDraftFailure) return;
    setPersonaGenError(null);
    setPersonaErrorKind('generation');
    setPersonaSaveRetry(null);

    const activeRoles = suggestedRoles.filter((r) => r.selected && r.count > 0);
    const totalCount = activeRoles.reduce((sum, r) => sum + r.count, 0) || DEFAULT_PERSONA_COUNT;

    const userMessages = copilotMessagesRef.current.filter((m) => m.role === 'user').map((m) => m.content);

    // No literal fallback: a made-up idea would yield personas for a business
    // nobody described. Both guards run BEFORE the step change so the user is
    // not moved away from the idea and roles they need to fix. The message is
    // written to both alerts because Generate exists in step 1 (role drawer)
    // and step 2 (persona panel), and only the current step's alert renders.
    const refuse = (message: string) => {
      setRoleError(message);
      setPersonaGenError(message);
    };
    // The saved study prompt stays the canonical idea. Joining every chat turn
    // into it ("...That is everything, please finalize") corrupted downstream
    // script/persona prompts and outgrew the 8k limit after a long conversation;
    // the server already reads the full copilot history from the study.
    const userPrompt = [study?.prompt ?? '', promptInput, userMessages[0] ?? ''].find((t) => t.trim()) ?? '';
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
      if (!epoch.active) return;
      const generated = result.personas;
      setPersonaFailedRoles(result.failed_roles);
      setPersonaServedBy(result.served_by);

      setPersonas(generated);
      setSelectedPersonaIds(generated.map((p) => p.id));
      if (generated[0]) setActiveInterviewPersonaId(generated[0].id);

      if (studyId) {
        try {
          await api.updateStudy(studyId, {
            title: studyTitle,
            prompt: userPrompt,
            persona_count: generated.length || totalCount,
            persona_ids: generated.map((p) => p.id),
            personas_data: generated as any,
            step: 2,
          });
        } catch (saveErr: unknown) {
          if (!epoch.active) return;
          // The cohort exists on the server; only this tab's study snapshot save
          // failed. Saying "generation failed" here made users regenerate.
          const refusal = readOnlyRefusal(saveErr);
          if (refusal) {
            setReadOnlyNotice(refusal);
          } else {
            setPersonaErrorKind('save');
            setPersonaGenError(toUserMessage(saveErr, { timeoutMs: 30000 }));
            setPersonaGenRequestId(fromUnknownError(saveErr).requestId ?? null);
          }
        }
      }
    } catch (err: any) {
      if (!epoch.active) return;
      const refusal = readOnlyRefusal(err);
      if (refusal) {
        setReadOnlyNotice(refusal);
      } else {
        setPersonaGenError(toUserMessage(err, { timeoutMs: 300000 }));
        setPersonaGenRequestId(fromUnknownError(err).requestId ?? null);
      }
    } finally {
      if (epoch.active) setIsGeneratingPersonas(false);
    }
  };

  const handleRetryPersonaSave = async () => {
    const controller = personaSaveControllerRef.current;
    const epoch = studyEpochRef.current;
    if (!studyId || !epoch.active || !personaSaveRetry || isReadOnly || personaSavePendingRef.current
      || !controller || controller.signal.aborted) return;
    const owner = api.getStoredUser()?.id ?? 'anonymous';
    const isCurrent = () => epoch.active && !controller.signal.aborted
      && personaSaveControllerRef.current === controller;
    personaSavePendingRef.current = true;
    setIsRetryingPersonaSave(true);
    try {
      await personaSaveRetry();
      if (!isCurrent()) return;
      setPersonaGenError(null);
      setPersonaGenRequestId(null);
      setPersonaSaveRetry(null);
    } catch (error: unknown) {
      if (!isCurrent()) return;
      const refusal = readOnlyRefusal(error);
      if (refusal) setReadOnlyNotice(refusal);
      else {
        setPersonaGenError(toUserMessage(error, { timeoutMs: 30000 }));
        setPersonaGenRequestId(fromUnknownError(error).requestId ?? null);
      }
      const retry = refusal ? undefined : getStudyDraftRetry(owner, studyId, controller.signal);
      setPersonaSaveRetry(() => retry ?? null);
    } finally {
      if (isCurrent()) {
        personaSavePendingRef.current = false;
        setIsRetryingPersonaSave(false);
      }
    }
  };

  const handleRemovePersona = (personaId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!studyEpochRef.current.active || isReadOnly) return;
    const persona = personas.find((p) => p.id === personaId);
    const status = interviewStatusMap[personaId];
    const hasHistory = status === 'completed' || status === 'in_progress' || Boolean(interviewIdByPersona[personaId]);
    if (hasHistory || hasReportArtifact) {
      setPanelActionError(null);
      setPendingPanelAction({ kind: 'remove', personaId, personaName: persona?.name || 'this persona' });
      return;
    }
    void removePersonaNow(personaId);
  };

  const removePersonaNow = async (personaId: string) => {
    const epoch = studyEpochRef.current;
    if (!epoch.active || !studyId) return;
    setPanelActionBusy(true);
    setPanelActionError(null);
    try {
      const result = await api.archiveStudyPersona(studyId, personaId);
      if (!epoch.active) return;
      const nextPersonas = personas.filter((p) => p.id !== personaId);
      setPersonas(nextPersonas);
      setSelectedPersonaIds((prev) => prev.filter((id) => id !== personaId));
      setStudy((prev) => prev ? { ...prev, persona_count: result.persona_count, persona_ids: result.persona_ids, revision: result.study_revision } : prev);
      if (activeInterviewPersonaId === personaId) setActiveInterviewPersonaId(nextPersonas[0]?.id ?? '');
      setPendingPanelAction(null);
    } catch (err: unknown) {
      if (!epoch.active) return;
      const refusal = readOnlyRefusal(err);
      if (refusal) {
        setReadOnlyNotice(refusal);
        setPendingPanelAction(null);
      } else {
        // Never drop the card locally while the server still has it.
        const message = `${toUserMessage(err)} The persona is still part of the study.`;
        if (pendingPanelAction) setPanelActionError(message);
        else setPersonaGenError(message);
      }
    } finally {
      if (epoch.active) setPanelActionBusy(false);
    }
  };

  const requestRegeneratePersonas = async () => {
    if (hasInterviewActivity || hasReportArtifact) {
      setPanelActionError(null);
      setPendingPanelAction({ kind: 'regenerate' });
      return;
    }
    await handleGeneratePersonas();
  };

  const handleGenerateScript = async () => {
    const epoch = studyEpochRef.current;
    // State updates land after this tick; the ref refuses the second click of a double-click.
    if (!epoch.active || !studyId || isGeneratingScript || scriptGenerationPendingRef.current) return;
    scriptGenerationPendingRef.current = true;
    setIsGeneratingScript(true);
    setScriptError(null);
    try {
      const res = await api.generateStudyScriptQuestions(studyId, study?.prompt || promptInput);
      if (!epoch.active) return;
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
        // The server already persisted the script (and reported the new
        // revision); re-sending it against the old revision produced a 412.
        if (res.study_revision == null) api.updateStudy(studyId, { script_questions: res.questions }).catch(() => {});
      } else {
        setScriptError('The generator returned no questions. Your existing script is unchanged — try again.');
      }
    } catch (err: any) {
      if (!epoch.active) return;
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
      scriptGenerationPendingRef.current = false;
      if (epoch.active) setIsGeneratingScript(false);
    }
  };

  // Step 4: Batch Interviews Execution (async job + polling)
  const batchPrerequisiteError = personas.length === 0 || selectedPersonaIds.length === 0
    ? 'Select at least one persona before running interviews.'
    : questions.length === 0
    ? 'Add at least one question in Script before running interviews.'
    : questions.some((question) => !question.trim())
    ? 'Fill in or remove empty script questions before running interviews.'
    : null;
  const batchStartBlockedReason = studyId && api.getPendingJobHandle(studyId, 'batch')
    ? null
    : batchPrerequisiteError;
  const batchPollCancelledRef = useRef(false);
  const batchControllerRef = useRef<AbortController | null>(null);
  useEffect(() => () => { batchControllerRef.current?.abort(); }, [studyId]);

  // Interview statuses live on the server. Hydrate them on load (and when the
  // panel changes) so a reload never shows a finished batch as "Pending";
  // also pick up a batch that was accepted before the reload.
  const hydrateInterviews = React.useCallback(async (epoch = studyEpochRef.current) => {
    if (!studyId || personas.length === 0) return;
    try {
      const { interviews } = await api.listStudyInterviews(studyId, { limit: 200 });
      if (!epoch.active) return;
      const map: Record<string, 'pending' | 'in_progress' | 'completed' | 'failed'> = {};
      const ids: Record<string, string> = {};
      let activeKeyWritten = false;
      for (const p of personas) {
        const mine = (interviews as Array<{ id: string; persona_id: string; status: string; turn_count?: number; created_at?: string }>)
          .filter((iv) => iv.persona_id === p.id)
          .sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? '')));
        const latest = mine[0];
        if (!latest) continue;
        ids[p.id] = latest.id;
        map[p.id] = mine.some((iv) => iv.status === 'completed')
          ? 'completed'
          : (latest.turn_count ?? 0) > 0 ? 'in_progress' : 'pending';
        // The transcript panel restores from this key; batch runs never wrote it.
        const key = `bebshax_conv_${studyId}_${p.id}`;
        try {
          if (!localStorage.getItem(key)) {
            localStorage.setItem(key, latest.id);
            if (p.id === activeInterviewPersonaId) activeKeyWritten = true;
          }
        } catch { /* storage unavailable: the Interview Lab still lists the transcript */ }
      }
      setInterviewIdByPersona(ids);
      // A live batch owns the map while it runs; otherwise the server is the truth.
      if (!batchControllerRef.current) setInterviewStatusMap((prev) => ({ ...prev, ...map }));
      if (activeKeyWritten) setRestoreAttempt((attempt) => attempt + 1);
    } catch {
      // The step still renders from whatever is known; the batch/list views report load errors.
    }
  }, [studyId, personas, activeInterviewPersonaId]);

  useEffect(() => {
    const epoch = studyEpochRef.current;
    void hydrateInterviews(epoch);
  }, [hydrateInterviews]);

  useEffect(() => {
    if (!studyId || isReadOnly || personas.length === 0) return;
    const jobId = api.getPendingJobHandle(studyId, 'batch');
    if (!jobId || batchControllerRef.current) return;
    void handleRunBatchInterviews();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studyId, personas.length]);

  const handleRunBatchInterviews = async () => {
    const epoch = studyEpochRef.current;
    if (!epoch.active || !studyId || isReadOnly || isBatchRunning || batchControllerRef.current) return;
    if (!api.getPendingJobHandle(studyId, 'batch') && batchPrerequisiteError) {
      setBatchError({ message: batchPrerequisiteError, requestId: null });
      return;
    }
    const controller = new AbortController();
    batchControllerRef.current = controller;
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
      if (!epoch.active) return;
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
      const start = await api.runBatchStudyInterviews(studyId, selectedPersonaIds, questions, controller.signal);
      if (!epoch.active || batchPollCancelledRef.current) return;
      const jobId = start?.job_id;
      if (!jobId) throw new Error('Batch job did not start');
      applyJobStatuses(start);

      if (['pending', 'queued', 'running'].includes(start.status)) {
        await pollSerial((signal) => api.getBatchRunStatus(studyId, jobId, signal), {
          signal: controller.signal, intervalMs: 5000, timeoutMs: 1800000, idleTimeoutMs: 300000, pauseWhenHidden: true,
          complete: (job) => !['pending', 'queued', 'running'].includes(job.status),
          progress: (job) => JSON.stringify([job.status, job.completed_count, job.failed_count, job.personas]),
          onUpdate: (job) => { if (epoch.active && !controller.signal.aborted) applyJobStatuses(job); },
        });
      }
      if (!epoch.active || batchPollCancelledRef.current) return;
      api.forgetJobHandle(studyId, 'batch');
      await hydrateInterviews(epoch);
    } catch (err: any) {
      if (!epoch.active) return;
      if (controller.signal.aborted || api.getPendingJobHandle(studyId, 'batch')) {
        setBatchError({ message: 'Live updates paused. The accepted batch may still be running; resume to check its saved progress.', requestId: null });
        return;
      }
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
      if (batchControllerRef.current === controller) batchControllerRef.current = null;
      if (epoch.active) setIsBatchRunning(false);
    }
  };

  const handleSendInterviewMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    const epoch = interviewEpochRef.current;
    const text = userInputMessage.trim();
    if (!epoch.active || epoch.pending || epoch.restoring || epoch.restoreFailed || !text || isSimulating || isBatchRunning || isGeneratingReport || !activeInterviewPersonaId) return;

    epoch.pending = true;
    epoch.revision += 1;
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
        if (!epoch.active) return;
        setChatMessages((prev) => [...prev, res.assistantTurn]);
      } else {
        const conv = await api.startConversation(activeInterviewPersonaId, study?.prompt || 'User Research Interview');
        if (!epoch.active) return;
        setConversationId(conv.id);
        if (studyId) {
          localStorage.setItem(`bebshax_conv_${studyId}_${activeInterviewPersonaId}`, conv.id);
        }
        const res = await api.sendMessage(conv.id, text);
        if (!epoch.active) return;
        setChatMessages((prev) => [...prev, res.assistantTurn]);
      }
    } catch (err: any) {
      if (!epoch.active) return;
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
      epoch.pending = false;
      if (epoch.active) setIsSimulating(false);
    }
  };

  // Step 5: Report Synthesis
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportErrorKind, setReportErrorKind] = useState<'loading' | 'generation' | 'copy'>('generation');
  const reloadReports = async () => {
    const epoch = studyEpochRef.current;
    if (!epoch.active || !studyId) return;
    setReportsLoading(true);
    setReportError(null);
    try {
      const savedReports = await api.getStudyReports(studyId);
      if (!epoch.active) return;
      setAvailableReports(savedReports);
      if (savedReports.length > 0) setReport(savedReports[0]);
    } catch {
      if (!epoch.active) return;
      setReportErrorKind('loading');
      setReportError('Saved reports could not be loaded. This does not mean the study has no reports.');
    } finally {
      if (epoch.active) setReportsLoading(false);
    }
  };
  const handleGenerateFinalReport = async () => {
    const epoch = studyEpochRef.current;
    if (!epoch.active || !studyId || isGeneratingReport) return;
    if (completedInterviewCount === 0 && !hasReportArtifact) {
      // The server refuses a report without findings; say so here instead of
      // moving to an empty report step.
      setBatchError({ message: 'Complete at least one interview before generating the decision report.', requestId: null });
      return;
    }
    setIsGeneratingReport(true);
    setReportError(null);
    // Move to the report step first: synthesis can take minutes, and waiting
    // on a disabled button with no feedback looks like nothing happened.
    handleStepChange(5);
    try {
      const rep = await api.generateStudyReport(studyId);
      if (!epoch.active) return;
      setReport(rep);
      setAvailableReports((prev) => [rep, ...prev.filter((r) => r.id !== rep.id)]);
      // The freshly-generated report is what earns 'completed' status.
      handleStepChange(5);
    } catch (err: any) {
      if (!epoch.active) return;
      const refusal = readOnlyRefusal(err);
      if (refusal) {
        setReadOnlyNotice(refusal);
      } else {
        // Honest failure: the error is shown on the report step with a retry.
        setReportErrorKind('generation');
        setReportError(err?.message || 'Report generation failed. Please retry.');
      }
    } finally {
      if (epoch.active) setIsGeneratingReport(false);
    }
  };

  const copyReportMarkdown = async () => {
    const epoch = studyEpochRef.current;
    if (!epoch.active || !report) return;
    const md = reportMarkdown(report);
    const copied = await copyText(md);
    if (!epoch.active) return;
    if (copied) {
      setCopiedToast(true);
      setTimeout(() => {
        if (epoch.active) setCopiedToast(false);
      }, 2500);
    } else {
      setReportErrorKind('copy');
      setReportError('Could not copy the report. Use Export Markdown to download it instead.');
    }
  };

  const exportReportMarkdown = () => {
    if (!studyEpochRef.current.active || !report) return;
    const md = reportMarkdown(report);
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(report.title || 'Research_Report').replace(/\s+/g, '_')}_V${report.version || 1}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  useEffect(() => {
    const epoch = studyEpochRef.current;
    let cancelled = false;
    if (studyId && (!study || study.id !== studyId)) return;
    const trimmedPrompt = initialPrompt.trim();
    if (!trimmedPrompt || initialPromptHandledRef.current === trimmedPrompt) return;
    let userMsg = pendingInitialPromptRef.current;
    if (!userMsg) {
      if (copilotMessagesRef.current.length > 0) return;
      userMsg = {
        id: `msg_u_${Date.now()}`,
        role: 'user',
        content: trimmedPrompt,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
      };
      pendingInitialPromptRef.current = userMsg;
    }
    if (copilotMessagesRef.current.length === 0) {
      copilotMessagesRef.current = [userMsg];
      setCopilotMessages([userMsg]);
    }
    const initialMessage = userMsg;
    queueMicrotask(() => {
      if (cancelled || !epoch.active) return;
      if (copilotMessagesRef.current.length !== 1 || copilotMessagesRef.current[0].id !== initialMessage.id) return;
      initialPromptHandledRef.current = trimmedPrompt;
      pendingInitialPromptRef.current = null;
      if (studyId) {
        api.updateStudy(studyId, { copilot_messages: [initialMessage] }).catch(() => {});
      }
      void fetchCopilotTurn([{ role: 'user', content: trimmedPrompt }]);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPrompt, studyId, study]);

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
  const completedInterviewCount = Object.values(interviewStatusMap).filter((s) => s === 'completed').length;
  const hasInterviewActivity =
    chatMessages.length > 0 ||
    conversationId !== null ||
    Object.keys(interviewIdByPersona).length > 0 ||
    Object.values(interviewStatusMap).some((s) => s === 'completed' || s === 'in_progress');
  const hasReportArtifact = report !== null || availableReports.length > 0;
  // "Done" is earned by the step's artifact, never by the URL or the step number.
  const stepCompleted = (stepNum: number): boolean => {
    switch (stepNum) {
      case 1: return goalApproved;
      case 2: return personas.length > 0;
      case 3: return questions.length > 0 && questions.every((q) => q.trim());
      case 4: return completedInterviewCount > 0;
      case 5: return hasReportArtifact;
      default: return false;
    }
  };
  // The furthest step a deep link may open: one past the last completed step.
  const highestReachableStep = (() => {
    let reach = 1;
    while (reach < 5 && stepCompleted(reach)) reach += 1;
    return hasReportArtifact ? 5 : reach;
  })();
  // A URL past the study's progress (stale bookmark, typed step) still opens,
  // but nothing is marked done or written for it; the step count says where the
  // study really is.
  const stepAheadOfProgress = Boolean(study && study.id === studyId && currentStep > highestReachableStep);
  const isStepUnlocked = (stepNum: number): boolean => {
    if (stepNum <= currentStep) return true;
    if (stepNum <= 3) return goalApproved;
    // Interviews need respondents AND questions: the backend refuses a batch
    // run without a script (script_required) rather than asking canned ones.
    if (stepNum === 4) return personas.length > 0 && questions.length > 0;
    // The report step is viewable once a panel exists (it explains what is
    // still missing); generating is gated separately on completed interviews.
    return hasReportArtifact || completedInterviewCount > 0 || personas.length > 0;
  };
  const stepLockReason = (stepNum: number): string =>
    stepNum <= 3
      ? 'Approve a research goal in Context first'
      : stepNum === 4
        ? personas.length > 0
          ? 'Generate or write interview questions first'
          : 'Generate personas first'
        : 'Generate personas first';

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

  if (studyId && (!study || study.id !== studyId)) {
    return (
      <div className="bx-empty-state">
        <p role={loadError ? 'alert' : 'status'}>{loadError || 'Loading saved study...'}</p>
        <button type="button" className="bx-btn bx-btn--secondary" onClick={onExit}>
          <ChevronLeft size={15} aria-hidden="true" /> Back to studies
        </button>
      </div>
    );
  }

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
            className="bx-btn bx-btn--secondary bx-btn--sm"
          >
            <ChevronLeft size={15} aria-hidden="true" />
            Exit Study
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
          {stepAheadOfProgress && (
            <span className="bx-step-ahead" role="status" style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
              Progress is at step {highestReachableStep}
            </span>
          )}
          {stepLabels.map((s, idx) => {
            const isDone = stepCompleted(s.num) && s.num !== currentStep;
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
                      width: '20px',
                      height: '20px',
                      borderRadius: '50%',
                      background: isDone
                        ? 'var(--accent-teal)'
                        : isCurrent
                        ? 'linear-gradient(180deg, var(--accent-teal-bright), var(--accent-teal))'
                        : 'var(--fill-soft-2)',
                      color: isDone || isCurrent ? 'var(--text-on-accent)' : 'var(--text-secondary)',
                      boxShadow: isCurrent ? '0 0 0 3px var(--accent-subtle), inset 0 1px 0 rgba(255,255,255,0.3)' : 'none',
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
        {loadError && <div role="alert" className="bx-alert bx-alert--error">{loadError}</div>}
        {saveState && saveState.state !== 'saved' && (
          <div role={saveState.state === 'saving' ? 'status' : 'alert'} className="bx-alert">
            <span>{saveState.state === 'saving' ? 'Saving changes...' : saveState.message}</span>
            {saveState.state !== 'saving' && <button type="button" className="bx-btn bx-btn--secondary" onClick={() => {
              if (studyId && window.confirm('Discard the unsaved draft and reload the saved server version?')) {
                api.discardStudyDraft(studyId);
                window.location.reload();
              }
            }}>Reload saved version</button>}
          </div>
        )}
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
              approvedGoalSummary={approvedGoalSummary}
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
              personaErrorKind={personaErrorKind}
              hasUnresolvedDraftFailure={hasUnresolvedDraftFailure}
              canRetryPersonaSave={Boolean(personaSaveRetry)}
              isRetryingPersonaSave={isRetryingPersonaSave}
              handleRetryPersonaSave={handleRetryPersonaSave}
              personaGenRequestId={personaGenRequestId}
              failedRoles={personaFailedRoles}
              personaServedBy={personaServedBy}
              isGeneratingPersonas={isGeneratingPersonas}
              suggestedRoles={suggestedRoles}
              handleGeneratePersonas={personas.length > 0 ? requestRegeneratePersonas : handleGeneratePersonas}
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
              batchStartBlockedReason={batchStartBlockedReason}
              handleRunBatchInterviews={handleRunBatchInterviews}
              onCancelBatch={() => { batchPollCancelledRef.current = true; batchControllerRef.current?.abort(); }}
              isGeneratingReport={isGeneratingReport}
              handleGenerateFinalReport={handleGenerateFinalReport}
              handleStepChange={handleStepChange}
              interviewStatusMap={interviewStatusMap}
              interviewFailureReasons={interviewFailureReasons}
              interviewIdByPersona={interviewIdByPersona}
              completedInterviewCount={completedInterviewCount}
              batchError={batchError}
              activeInterviewPersonaId={activeInterviewPersonaId}
              setActiveInterviewPersonaId={setActiveInterviewPersonaId}
              setChatMessages={setChatMessages}
              setConversationId={setConversationId}
              interviewChatRef={interviewChatRef}
              chatMessages={chatMessages}
              isSimulating={isSimulating}
              isRestoringInterview={isRestoringInterview}
              restoreError={restoreError}
              onRetryRestore={() => setRestoreAttempt((attempt) => attempt + 1)}
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
              reportErrorKind={reportErrorKind}
              onReloadReports={reloadReports}
              reportsLoading={reportsLoading}
              isGeneratingReport={isGeneratingReport}
              copiedToast={copiedToast}
              copyReportMarkdown={copyReportMarkdown}
              exportReportMarkdown={exportReportMarkdown}
              onSelectReport={setReport}
              handleGenerateFinalReport={handleGenerateFinalReport}
              completedInterviewCount={completedInterviewCount}
              verificationAssumptions={verificationAssumptions}
              isReadOnly={isReadOnly}
            />
          </div>
        )}
      </div>

      <ConfirmDialog
        open={pendingPanelAction !== null}
        title={pendingPanelAction?.kind === 'remove' ? 'Remove this persona?' : 'Regenerate the persona panel?'}
        description={
          pendingPanelAction?.kind === 'remove' ? (
            <>
              <strong>{pendingPanelAction.personaName}</strong> leaves the panel. Its saved interview and any report that cites it stay in
              the Interview Lab as history, but new interviews and reports will not include it.
            </>
          ) : (
            <>
              A new panel replaces the current personas.{' '}
              {completedInterviewCount > 0 && <>The {completedInterviewCount} completed interview{completedInterviewCount === 1 ? '' : 's'} stay attached to the old personas in the Interview Lab. </>}
              {hasReportArtifact && <>The existing report describes the old panel and will read as out of date until you generate a new version.</>}
            </>
          )
        }
        confirmLabel={pendingPanelAction?.kind === 'remove' ? 'Remove persona' : 'Regenerate panel'}
        destructive
        busy={panelActionBusy || isGeneratingPersonas}
        error={panelActionError}
        onCancel={() => { if (!panelActionBusy) { setPendingPanelAction(null); setPanelActionError(null); } }}
        onConfirm={() => {
          if (!pendingPanelAction) return;
          if (pendingPanelAction.kind === 'remove') { void removePersonaNow(pendingPanelAction.personaId); return; }
          setPendingPanelAction(null);
          void handleGeneratePersonas();
        }}
      />

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
