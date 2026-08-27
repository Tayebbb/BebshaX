import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowRight,
  Sparkles,
  CheckCircle2,
  Check,
  Send,
  Zap,
  Download,
  Trash2,
  X,
  RefreshCw,
  FileText,
  Copy,
  MessageSquare,
  Plus,
  Minus,
} from 'lucide-react';
import {
  Study,
  StudyType,
  Persona,
  ConversationTurn,
  PersonaRoleSuggestion,
  StudyReport,
} from '../../../types';
import { api } from '../../../services/api';

interface StudyWorkflowViewProps {
  studyId?: string;
  initialStep?: number;
  initialType?: StudyType;
  initialPrompt?: string;
  onExit: () => void;
  onStepChange?: (step: number) => void;
}

interface CopilotMessage {
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
  const [study, setStudy] = useState<Study | null>(null);
  const [promptInput, setPromptInput] = useState<string>(initialPrompt);
  const [questions, setQuestions] = useState<string[]>([
    'How do you currently handle tasks and challenges in this area?',
    'What is your biggest frustration or friction point with existing alternatives?',
    'What specific features or capabilities would make this solution indispensable?',
    'What are your pricing expectations and willingness to pay for this tool?',
    'What hesitations or barriers would prevent you from adopting this workflow?',
  ]);
  const [newQuestion, setNewQuestion] = useState<string>('');
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [selectedPersonaIds, setSelectedPersonaIds] = useState<string[]>([]);
  const [isGeneratingPersonas, setIsGeneratingPersonas] = useState<boolean>(false);
  const [personaGenError, setPersonaGenError] = useState<string | null>(null);
  const [viewingPersona, setViewingPersona] = useState<Persona | null>(null);

  // Copilot Multi-turn Conversational States (Step 1)
  const [copilotMessages, setCopilotMessages] = useState<CopilotMessage[]>([]);
  const [isCopilotTyping, setIsCopilotTyping] = useState<boolean>(false);
  const [step1Prompt, setStep1Prompt] = useState<string>('');
  const [showRoleSelection, setShowRoleSelection] = useState<boolean>(false);
  const [suggestedRoles, setSuggestedRoles] = useState<PersonaRoleSuggestion[]>([]);
  const [isLoadingRoles, setIsLoadingRoles] = useState<boolean>(false);

  // Live Interview Simulation States (Step 4)
  const [activeInterviewPersonaId, setActiveInterviewPersonaId] = useState<string>('');
  const [chatMessages, setChatMessages] = useState<ConversationTurn[]>([]);
  const [isSimulating, setIsSimulating] = useState(false);
  const [isBatchRunning, setIsBatchRunning] = useState(false);
  const [userInputMessage, setUserInputMessage] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [interviewStatusMap, setInterviewStatusMap] = useState<Record<string, 'pending' | 'in_progress' | 'completed' | 'failed'>>({});

  // Step 5: Final Report
  const [report, setReport] = useState<StudyReport | null>(null);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [availableReports, setAvailableReports] = useState<StudyReport[]>([]);
  const [copiedToast, setCopiedToast] = useState(false);

  const copilotMessagesRef = useRef<CopilotMessage[]>([]);
  const isFetchingCopilotRef = useRef<boolean>(false);
  const initialPromptHandledRef = useRef<string | null>(null);
  const roleSelectionRef = useRef<HTMLDivElement | null>(null);
  const copilotChatRef = useRef<HTMLDivElement | null>(null);
  const interviewChatRef = useRef<HTMLDivElement | null>(null);

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

  const handleStepChange = (newStep: number) => {
    const clamped = Math.max(1, Math.min(newStep, 5));
    setCurrentStep(clamped);
    onStepChange?.(clamped);
    if (studyId) {
      api
        .updateStudy(studyId, {
          step: clamped,
          status: clamped === 5 ? 'completed' : 'in_progress',
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
          setSuggestedRoles(s.suggested_roles);
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
        if (s.step && !initialStep) {
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

  const fetchCopilotTurn = async (history: { role: 'user' | 'assistant'; content: string }[]) => {
    if (isFetchingCopilotRef.current) return;
    isFetchingCopilotRef.current = true;
    setIsCopilotTyping(true);
    try {
      const res = await api.sendStudyCopilotMessage(history, initialType, studyId);
      const assistantMsg: CopilotMessage = {
        id: `msg_a_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
        role: 'assistant',
        content: res.reply,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
        isGoalCard: res.is_ready_for_approval && !!res.research_goal_card,
        goalCardData: res.research_goal_card || undefined,
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
    } catch {
      const userTurns = history.filter((m) => m.role === 'user');
      const latestUserPrompt = userTurns[userTurns.length - 1]?.content || 'Product Study';
      const fallbackMsg: CopilotMessage = {
        id: `msg_a_${Date.now()}`,
        role: 'assistant',
        content: `Understood! I've structured your customer discovery objective for "${latestUserPrompt}". Let's validate target market demand, price sensitivity, and adoption barriers.`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase(),
        isGoalCard: true,
        goalCardData: {
          title: 'RESEARCH GOAL',
          summary: `Validate demand, pricing sensitivity, and willingness to pay for "${latestUserPrompt}".`,
          target_audience: 'Primary target users and decision makers',
          core_hypothesis: 'Strong product-market fit and willingness to pay',
        },
      };
      const updated = [...copilotMessagesRef.current, fallbackMsg];
      copilotMessagesRef.current = updated;
      setCopilotMessages(updated);
      if (studyId) {
        api.updateStudy(studyId, { copilot_messages: updated as any }).catch(() => {});
      }
    } finally {
      setIsCopilotTyping(false);
      isFetchingCopilotRef.current = false;
    }
  };

  const handleSendCopilotMessage = (text?: string) => {
    const inputEl = document.querySelector('input[placeholder*="Type here"]') as HTMLInputElement | null;
    const messageToSend = (
      typeof text === 'string' && text.trim() ? text : step1Prompt || promptInput || inputEl?.value || ''
    ).trim();
    if (!messageToSend) return;

    setStep1Prompt('');
    setPromptInput('');
    if (inputEl) inputEl.value = '';

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
      'Product Research Study';

    // 1. Trigger background autonomous research and dataset discovery
    if (studyId) {
      api.triggerStudyResearch(studyId).catch(() => {});
    }

    // 2. Fetch suggested roles only when the copilot didn't already supply them,
    //    so re-approving never clobbers the user's count/selection tweaks.
    if (suggestedRoles.length === 0) {
      setIsLoadingRoles(true);
      try {
        const roles = await api.getSuggestedPersonaRoles(activePrompt);
        if (roles && roles.length > 0) {
          setSuggestedRoles(roles);
        }
      } catch {
        // ignore
      } finally {
        setIsLoadingRoles(false);
      }
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
            count: nextSelected ? (r.count > 0 ? r.count : 3) : 0,
          };
        }
        return r;
      })
    );
  };

  const handleIncrementRole = (roleId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSuggestedRoles((prev) =>
      prev.map((r) => (r.id === roleId ? { ...r, count: r.count + 1, selected: true } : r))
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
    setIsGeneratingPersonas(true);
    setPersonaGenError(null);
    handleStepChange(2);

    const activeRoles = suggestedRoles.filter((r) => r.selected && r.count > 0);
    const totalCount = activeRoles.reduce((sum, r) => sum + r.count, 0) || 6;

    const allUserTexts = copilotMessagesRef.current
      .filter((m) => m.role === 'user')
      .map((m) => m.content)
      .join(' ');

    const userPrompt = allUserTexts || promptInput || study?.prompt || 'Product Research Study';
    // Word-boundary cut — slice(0, 50) mid-word produced titles like "…Students at".
    const derivedTitle = (() => {
      if (userPrompt.length <= 50) return userPrompt;
      const cut = userPrompt.slice(0, 50);
      const atWord = cut.lastIndexOf(' ') > 25 ? cut.slice(0, cut.lastIndexOf(' ')) : cut;
      return atWord.replace(/\s+(?:a|an|the|and|or|but|for|nor|on|at|to|from|by|with|in|of)$/i, '');
    })();
    const studyTitle = study?.title && study.title !== 'Untitled Study' ? study.title : derivedTitle;

    try {
      const generated = await api.generateStudyPersonas(
        study?.id || studyId,
        userPrompt,
        suggestedRoles,
        studyTitle
      );

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
      setPersonaGenError(
        err?.message || 'Persona generation failed. Please try again.'
      );
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
    try {
      const res = await api.generateStudyScriptQuestions(studyId, study?.prompt || promptInput);
      if (res.questions && res.questions.length > 0) {
        setQuestions(res.questions);
        api.updateStudy(studyId, { script_questions: res.questions }).catch(() => {});
      }
    } catch {
      // ignore
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

    const applyJobStatuses = (job: any) => {
      const map: Record<string, 'pending' | 'in_progress' | 'completed' | 'failed'> = {};
      personas.forEach((p) => {
        const entry = job?.personas?.[p.id];
        map[p.id] = entry ? entry.status : 'pending';
      });
      setInterviewStatusMap(map);
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
            setInterviewStatusMap((prev) => {
              const map = { ...prev };
              Object.keys(map).forEach((pid) => {
                if (map[pid] === 'in_progress' || map[pid] === 'pending') map[pid] = 'failed';
              });
              return map;
            });
            break;
          }
          // Transient poll error: keep polling.
        }
      }
      await api.listStudyInterviews(studyId).catch(() => []);
    } catch (err: any) {
      // Whole-batch failure: everything selected is failed. Nothing "completed".
      const failedMap: Record<string, 'pending' | 'failed'> = {};
      personas.forEach((p) => {
        failedMap[p.id] = selectedPersonaIds.includes(p.id) ? 'failed' : 'pending';
      });
      setInterviewStatusMap(failedMap);
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
    try {
      const rep = await api.generateStudyReport(studyId);
      setReport(rep);
      setAvailableReports((prev) => [rep, ...prev.filter((r) => r.id !== rep.id)]);
      handleStepChange(5);
    } catch (err: any) {
      // Honest failure: navigate to the report step and show the error there
      // instead of leaving the user staring at an unchanged page.
      setReportError(err?.message || 'Report generation failed. Please retry.');
      handleStepChange(5);
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
    { num: 1, label: 'Context' },
    { num: 2, label: 'Personas' },
    { num: 3, label: 'Script' },
    { num: 4, label: 'Interviews' },
    { num: 5, label: 'Report' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', background: '#080909', color: '#FFFFFF' }}>
      {/* Top Header with Stepper */}
      <header
        style={{
          borderBottom: '1px solid #202727',
          background: 'rgba(8, 9, 9, 0.95)',
          backdropFilter: 'blur(12px)',
          position: 'sticky',
          top: 0,
          zIndex: 30,
          padding: '12px 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button
            type="button"
            onClick={onExit}
            style={{
              background: 'transparent',
              border: '1px solid #202727',
              color: '#8D9999',
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
              color: '#FFFFFF',
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {stepLabels.map((s, idx) => {
            const isDone = s.num < currentStep;
            const isCurrent = s.num === currentStep;
            return (
              <React.Fragment key={s.num}>
                {idx > 0 && <div style={{ width: '16px', height: '1px', background: isDone ? '#14B8A6' : '#202727' }} />}
                <button
                  type="button"
                  onClick={() => handleStepChange(s.num)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '6px 12px',
                    borderRadius: '8px',
                    border: isCurrent ? '1px solid #14B8A6' : '1px solid transparent',
                    background: isCurrent ? 'rgba(20, 184, 166, 0.12)' : isDone ? 'rgba(255, 255, 255, 0.03)' : 'transparent',
                    color: isCurrent ? '#22D3EE' : isDone ? '#14B8A6' : '#8D9999',
                    fontSize: '0.8rem',
                    fontWeight: isCurrent || isDone ? 600 : 400,
                    cursor: 'pointer',
                  }}
                >
                  <div
                    style={{
                      width: '18px',
                      height: '18px',
                      borderRadius: '50%',
                      background: isDone ? '#14B8A6' : isCurrent ? '#22D3EE' : '#202727',
                      color: isDone || isCurrent ? '#080909' : '#8D9999',
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {isDone ? <Check size={11} strokeWidth={3} /> : s.num}
                  </div>
                  <span>{s.label}</span>
                </button>
              </React.Fragment>
            );
          })}
        </div>
      </header>

      {/* Main Workflow Container */}
      <main style={{ flex: 1, padding: '28px 40px', maxWidth: '1280px', width: '100%', margin: '0 auto' }}>
        {/* ============================================================
            STEP 1: CONTEXT & ASSUMPTION GATHERING
           ============================================================ */}
        {currentStep === 1 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ textAlign: 'center', marginBottom: '8px' }}>
              <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: '#FFFFFF', margin: '0 0 6px 0' }}>
                Design your user interviews
              </h1>
              <p style={{ fontSize: '0.9rem', color: '#8D9999', margin: 0 }}>
                Enter your product idea. BebshaX will refine your research objective, discover market evidence, and build grounded personas.
              </p>
            </div>

            {/* Chat Transcript Area */}
            <div
              ref={copilotChatRef}
              style={{
                background: '#111616',
                border: '1px solid #202727',
                borderRadius: '16px',
                padding: '24px',
                minHeight: '340px',
                maxHeight: '480px',
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
                gap: '16px',
              }}
            >
              {copilotMessages.length === 0 && (
                <div style={{ textAlign: 'center', color: '#8D9999', margin: 'auto', padding: '32px 0' }}>
                  <Sparkles size={28} className="text-teal-400 mx-auto mb-2" />
                  <div style={{ fontSize: '0.95rem', fontWeight: 600, color: '#FFFFFF' }}>
                    What business idea or product concept would you like to validate?
                  </div>
                  <div style={{ fontSize: '0.82rem', color: '#8D9999', marginTop: '4px' }}>
                    Type your idea below to start conversational context refinement.
                  </div>
                </div>
              )}

              {copilotMessages.map((msg) => (
                <div
                  key={msg.id}
                  style={{
                    alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: '80%',
                    background: msg.role === 'user' ? 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)' : '#161C1C',
                    color: '#FFFFFF',
                    padding: '14px 18px',
                    borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                    border: msg.role === 'user' ? 'none' : '1px solid #202727',
                  }}
                >
                  <div style={{ fontSize: '0.9rem', lineHeight: 1.5 }}>{msg.content}</div>

                  {msg.isGoalCard && msg.goalCardData && (
                    <div
                      style={{
                        marginTop: '14px',
                        background: '#0D1111',
                        border: '1px solid rgba(20, 184, 166, 0.35)',
                        borderRadius: '12px',
                        padding: '16px',
                      }}
                    >
                      <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#22D3EE', letterSpacing: '0.06em' }}>
                        {msg.goalCardData.title}
                      </div>
                      <div style={{ fontSize: '0.92rem', fontWeight: 600, color: '#FFFFFF', marginTop: '4px' }}>
                        {msg.goalCardData.summary}
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '12px', fontSize: '0.78rem' }}>
                        <div>
                          <span style={{ color: '#8D9999' }}>Target Audience: </span>
                          <span style={{ color: '#F4F7F7', fontWeight: 600 }}>{msg.goalCardData.target_audience}</span>
                        </div>
                        <div>
                          <span style={{ color: '#8D9999' }}>Hypothesis: </span>
                          <span style={{ color: '#F4F7F7', fontWeight: 600 }}>{msg.goalCardData.core_hypothesis}</span>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleApproveGoal(msg.goalCardData?.summary)}
                        style={{
                          marginTop: '14px',
                          width: '100%',
                          background: showRoleSelection
                            ? 'rgba(20, 184, 166, 0.16)'
                            : 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                          border: showRoleSelection ? '1px solid #14B8A6' : 'none',
                          borderRadius: '8px',
                          padding: '10px 16px',
                          color: showRoleSelection ? '#2DD4BF' : '#080909',
                          fontWeight: 700,
                          fontSize: '0.85rem',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '6px',
                        }}
                      >
                        <CheckCircle2 size={16} />
                        {showRoleSelection ? 'Goal Approved — View Suggested Roles ↓' : 'Approve Goal & Discover Personas'}
                      </button>
                    </div>
                  )}
                </div>
              ))}

              {isCopilotTyping && (
                <div style={{ alignSelf: 'flex-start', color: '#8D9999', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Sparkles size={14} className="text-teal-400 animate-spin" />
                  Synthesizing market context & assumptions...
                </div>
              )}
            </div>

            {/* Input Bar */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendCopilotMessage();
              }}
              style={{ display: 'flex', gap: '10px' }}
            >
              <input
                type="text"
                value={step1Prompt}
                onChange={(e) => setStep1Prompt(e.target.value)}
                placeholder="Type here to answer or give more context..."
                style={{
                  flex: 1,
                  background: '#111616',
                  border: '1px solid #202727',
                  borderRadius: '12px',
                  padding: '12px 18px',
                  color: '#FFFFFF',
                  fontSize: '0.9rem',
                  outline: 'none',
                }}
              />
              <button
                type="submit"
                aria-label="Send prompt"
                disabled={isCopilotTyping || !step1Prompt.trim()}
                style={{
                  background: '#14B8A6',
                  border: 'none',
                  borderRadius: '12px',
                  padding: '0 24px',
                  color: '#080909',
                  fontWeight: 700,
                  fontSize: '0.9rem',
                  cursor: isCopilotTyping || !step1Prompt.trim() ? 'not-allowed' : 'pointer',
                }}
              >
                <Send size={16} />
              </button>
            </form>

            {/* Role Selection Drawer when ready */}
            {showRoleSelection && (
              <div ref={roleSelectionRef} style={{ background: '#111616', border: '1px solid #202727', borderRadius: '16px', padding: '24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
                  <div>
                    <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#FFFFFF', margin: 0 }}>
                      SUGGESTED ROLES FOR YOUR STUDY
                    </h2>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px', flexWrap: 'wrap' }}>
                      <span style={{ fontSize: '0.8rem', color: '#14B8A6', fontWeight: 600 }}>Persona Panel Configured</span>
                      <span style={{ fontSize: '0.82rem', color: '#8D9999' }}>• Grounded in empirical evidence and dataset distributions</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={handleGeneratePersonas}
                    disabled={isGeneratingPersonas}
                    style={{
                      background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                      border: 'none',
                      borderRadius: '8px',
                      padding: '10px 20px',
                      color: '#080909',
                      fontWeight: 700,
                      fontSize: '0.88rem',
                      cursor: isGeneratingPersonas ? 'not-allowed' : 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      boxShadow: '0 4px 14px rgba(20, 184, 166, 0.25)',
                    }}
                  >
                    <Sparkles size={16} />
                    {isGeneratingPersonas ? 'Generating Personas...' : 'Generate Personas'}
                  </button>
                </div>

                {/* Stacked Roles List */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {isLoadingRoles && suggestedRoles.length === 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#8D9999', fontSize: '0.85rem', padding: '14px 4px' }}>
                      <Sparkles size={14} className="text-teal-400 animate-spin" />
                      Discovering suggested roles for your study...
                    </div>
                  )}
                  {suggestedRoles.map((role) => {
                    const isSelected = !!role.selected && role.count > 0;
                    return (
                      <div
                        key={role.id}
                        onClick={() => handleToggleRole(role.id)}
                        style={{
                          background: isSelected ? 'rgba(20, 184, 166, 0.08)' : '#0D1111',
                          border: isSelected ? '1px solid #14B8A6' : '1px solid #202727',
                          borderRadius: '12px',
                          padding: '14px 18px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '16px',
                          transition: 'all 0.2s ease',
                          boxShadow: isSelected ? '0 4px 16px -4px rgba(20, 184, 166, 0.15)' : 'none',
                        }}
                      >
                        {/* Left Info: Checkbox + Role Name + Description */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flex: 1, minWidth: 0 }}>
                          <div
                            style={{
                              width: '22px',
                              height: '22px',
                              borderRadius: '6px',
                              border: isSelected ? '1px solid #14B8A6' : '1px solid #334155',
                              background: isSelected ? '#14B8A6' : '#161B1B',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              flexShrink: 0,
                              transition: 'all 0.2s ease',
                            }}
                          >
                            {isSelected && <Check size={14} color="#080909" strokeWidth={3} />}
                          </div>

                          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', minWidth: 0 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                              <span
                                style={{
                                  fontSize: '0.86rem',
                                  fontWeight: 700,
                                  letterSpacing: '0.04em',
                                  color: isSelected ? '#22D3EE' : '#FFFFFF',
                                }}
                              >
                                {role.role}
                              </span>
                              {isSelected && (
                                <span
                                  style={{
                                    fontSize: '0.7rem',
                                    padding: '2px 8px',
                                    borderRadius: '9999px',
                                    background: 'rgba(20, 184, 166, 0.16)',
                                    color: '#2DD4BF',
                                    fontWeight: 600,
                                  }}
                                >
                                  Active ({role.count})
                                </span>
                              )}
                            </div>
                            <p
                              style={{
                                fontSize: '0.8rem',
                                color: '#8D9999',
                                margin: 0,
                                lineHeight: 1.4,
                              }}
                            >
                              {role.description}
                            </p>
                          </div>
                        </div>

                        {/* Right: Stepper Counter */}
                        <div
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            background: '#161B1B',
                            border: '1px solid #283333',
                            borderRadius: '8px',
                            padding: '4px 6px',
                            flexShrink: 0,
                          }}
                        >
                          <button
                            type="button"
                            aria-label={`Decrease ${role.role} count`}
                            onClick={(e) => handleDecrementRole(role.id, e)}
                            disabled={role.count <= 0}
                            style={{
                              background: role.count > 0 ? '#202727' : 'transparent',
                              border: 'none',
                              color: role.count > 0 ? '#FFFFFF' : '#4B5563',
                              borderRadius: '6px',
                              width: '26px',
                              height: '26px',
                              cursor: role.count > 0 ? 'pointer' : 'not-allowed',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              transition: 'background 0.15s ease',
                            }}
                          >
                            <Minus size={13} />
                          </button>

                          <span
                            style={{
                              fontSize: '0.88rem',
                              fontWeight: 700,
                              minWidth: '20px',
                              textAlign: 'center',
                              color: role.count > 0 ? '#22D3EE' : '#64748B',
                            }}
                          >
                            {role.count}
                          </span>

                          <button
                            type="button"
                            aria-label={`Increase ${role.role} count`}
                            onClick={(e) => handleIncrementRole(role.id, e)}
                            style={{
                              background: '#202727',
                              border: 'none',
                              color: '#FFFFFF',
                              borderRadius: '6px',
                              width: '26px',
                              height: '26px',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              transition: 'background 0.15s ease',
                            }}
                          >
                            <Plus size={13} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ============================================================
            STEP 2: GROUNDED SYNTHETIC PERSONAS
           ============================================================ */}
        {currentStep === 2 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            {personaGenError && (
              <div
                role="alert"
                style={{
                  background: 'rgba(239, 68, 68, 0.08)',
                  border: '1px solid rgba(239, 68, 68, 0.4)',
                  color: '#FCA5A5',
                  borderRadius: '8px',
                  padding: '12px 16px',
                  fontSize: '0.88rem',
                }}
              >
                Persona generation failed: {personaGenError} — no personas were fabricated. Retry when ready.
              </div>
            )}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
              <div>
                <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: '#FFFFFF', margin: '0 0 4px 0' }}>
                  Grounded Persona Library
                </h1>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.88rem', color: '#8D9999' }}>
                  <span>Total Personas</span>
                  <span>({personas.length})</span>
                  <span>• Grounded in empirical evidence & distributions</span>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={handleGeneratePersonas}
                  disabled={isGeneratingPersonas}
                  style={{
                    background: '#111616',
                    border: '1px solid #202727',
                    color: '#22D3EE',
                    borderRadius: '8px',
                    padding: '8px 16px',
                    fontSize: '0.84rem',
                    fontWeight: 600,
                    cursor: isGeneratingPersonas ? 'not-allowed' : 'pointer',
                    opacity: isGeneratingPersonas ? 0.6 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <RefreshCw size={14} className={isGeneratingPersonas ? 'animate-spin' : ''} />
                  Regenerate Personas
                </button>
                <button
                  type="button"
                  onClick={() => handleStepChange(3)}
                  style={{
                    background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                    border: 'none',
                    color: '#080909',
                    borderRadius: '8px',
                    padding: '8px 20px',
                    fontSize: '0.84rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  Generate Script
                  <ArrowRight size={15} />
                </button>
              </div>
            </div>

            {/* Generation progress banner */}
            {isGeneratingPersonas && (
              <div
                role="status"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  background: 'rgba(20, 184, 166, 0.06)',
                  border: '1px solid rgba(20, 184, 166, 0.25)',
                  borderRadius: '12px',
                  padding: '14px 18px',
                  color: '#2DD4BF',
                  fontSize: '0.88rem',
                  fontWeight: 600,
                }}
              >
                <Sparkles size={16} className="animate-spin" />
                Generating grounded personas from evidence datasets — this can take a minute on free-tier routes...
              </div>
            )}

            {/* Persona Cards Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '20px' }}>
              {isGeneratingPersonas &&
                personas.length === 0 &&
                Array.from({
                  length:
                    suggestedRoles.filter((r) => r.selected && r.count > 0).reduce((sum, r) => sum + r.count, 0) || 6,
                }).map((_, i) => (
                  <div
                    key={`persona_skeleton_${i}`}
                    className="bx-stagger"
                    style={{
                      ['--bx-i' as string]: Math.min(i, 12),
                      background: '#111616',
                      border: '1px solid #202727',
                      borderRadius: '16px',
                      padding: '20px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '14px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div className="bx-skeleton" style={{ width: '42px', height: '42px', borderRadius: '10px', flexShrink: 0 }} />
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
                        <div className="bx-skeleton" style={{ height: '14px', width: '55%' }} />
                        <div className="bx-skeleton" style={{ height: '11px', width: '40%' }} />
                      </div>
                    </div>
                    <div className="bx-skeleton" style={{ height: '30px', borderRadius: '6px' }} />
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <div className="bx-skeleton" style={{ height: '11px', width: '100%' }} />
                      <div className="bx-skeleton" style={{ height: '11px', width: '90%' }} />
                      <div className="bx-skeleton" style={{ height: '11px', width: '70%' }} />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 'auto', paddingTop: '8px' }}>
                      <div className="bx-skeleton" style={{ height: '13px', width: '38%' }} />
                      <div className="bx-skeleton" style={{ height: '18px', width: '25%', borderRadius: '6px' }} />
                    </div>
                  </div>
                ))}
              {personas.map((p, cardIdx) => (
                <div
                  key={p.id}
                  className="bx-stagger bx-lift"
                  style={{
                    ['--bx-i' as string]: Math.min(cardIdx, 12),
                    background: '#111616',
                    border: '1px solid #202727',
                    borderRadius: '16px',
                    padding: '20px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '14px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div
                        style={{
                          width: '42px',
                          height: '42px',
                          borderRadius: '10px',
                          background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                          color: '#080909',
                          fontWeight: 700,
                          fontSize: '1rem',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        {p.initials || p.name.slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <div style={{ fontSize: '1rem', fontWeight: 600, color: '#FFFFFF' }}>{p.name}</div>
                          <span style={{ fontSize: '0.65rem', color: '#14B8A6', background: 'rgba(20, 184, 166, 0.12)', border: '1px solid rgba(20, 184, 166, 0.25)', padding: '1px 5px', borderRadius: '4px', fontWeight: 600 }}>
                            {p.country_code || 'BD'}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.78rem', color: '#22D3EE' }}>{p.archetype || p.role_title}</div>
                        {p.tagline && <div style={{ fontSize: '0.74rem', color: '#8D9999' }}>{p.tagline}</div>}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => handleRemovePersona(p.id, e)}
                      style={{ background: 'transparent', border: 'none', color: '#535D5D', cursor: 'pointer' }}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>

                  {p.personality && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '4px', background: '#0D1111', padding: '6px 8px', borderRadius: '6px', border: '1px solid #1E2626', textAlign: 'center' }}>
                      {[
                        { l: 'O', v: p.personality.openness, c: '#38BDF8' },
                        { l: 'C', v: p.personality.conscientiousness, c: '#10B981' },
                        { l: 'E', v: p.personality.extroversion, c: '#F59E0B' },
                        { l: 'A', v: p.personality.agreeableness, c: '#A855F7' },
                        { l: 'N', v: p.personality.neuroticism, c: '#EC4899' },
                      ].map((t) => (
                        <div key={t.l} style={{ fontSize: '0.65rem' }}>
                          <span style={{ color: t.c, fontWeight: 700 }}>{t.v}</span>
                          <span style={{ color: '#8D9999', marginLeft: '2px' }}>{t.l}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <p style={{ fontSize: '0.84rem', color: '#D1D5DB', lineHeight: 1.45, margin: 0 }}>
                    {p.description || p.tagline || (p.quote ? `"${p.quote}"` : '')}
                  </p>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto', paddingTop: '8px' }}>
                    <button
                      type="button"
                      onClick={() => setViewingPersona(p)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#14B8A6',
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                        padding: 0,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      View full profile <ArrowRight size={13} />
                    </button>
                    <span style={{ fontSize: '0.72rem', fontWeight: 700, color: '#10B981', background: 'rgba(16, 185, 129, 0.1)', padding: '2px 8px', borderRadius: '6px' }}>
                      {Math.round((p.grounding_ratio || 0.95) * 100)}% Grounded
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Empty state: nothing generated yet and not currently generating */}
            {!isGeneratingPersonas && personas.length === 0 && (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '12px',
                  textAlign: 'center',
                  padding: '64px 24px',
                  border: '1px dashed #202727',
                  borderRadius: '16px',
                  color: '#8D9999',
                }}
              >
                <Sparkles size={28} className="text-teal-400" />
                <div style={{ fontSize: '1rem', fontWeight: 600, color: '#FFFFFF' }}>No personas yet</div>
                <div style={{ fontSize: '0.85rem', maxWidth: '420px' }}>
                  Generate grounded personas from your approved research goal and selected roles.
                </div>
                <button
                  type="button"
                  onClick={handleGeneratePersonas}
                  style={{
                    marginTop: '6px',
                    background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                    border: 'none',
                    borderRadius: '8px',
                    padding: '10px 20px',
                    color: '#080909',
                    fontWeight: 700,
                    fontSize: '0.85rem',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <Sparkles size={15} />
                  Generate Personas
                </button>
              </div>
            )}
          </div>
        )}

        {/* ============================================================
            STEP 3: INTERVIEW SCRIPT & QUESTIONS
           ============================================================ */}
        {currentStep === 3 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: '#FFFFFF', margin: '0 0 4px 0' }}>
                  Interview Script & Probing Rules
                </h1>
                <p style={{ fontSize: '0.88rem', color: '#8D9999', margin: 0 }}>
                  Customize the core questions the AI interviewer will ask across your personas.
                </p>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={handleGenerateScript}
                  style={{
                    background: '#111616',
                    border: '1px solid #202727',
                    color: '#22D3EE',
                    borderRadius: '8px',
                    padding: '8px 16px',
                    fontSize: '0.84rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Regenerate Questions
                </button>
                <button
                  type="button"
                  onClick={() => handleStepChange(4)}
                  style={{
                    background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                    border: 'none',
                    color: '#080909',
                    borderRadius: '8px',
                    padding: '8px 20px',
                    fontSize: '0.84rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  Approve Script & Start Interviews
                  <ArrowRight size={15} />
                </button>
              </div>
            </div>

            {/* Question List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {questions.map((q, idx) => (
                <div
                  key={idx}
                  style={{
                    background: '#111616',
                    border: '1px solid #202727',
                    borderRadius: '12px',
                    padding: '16px 20px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '14px',
                  }}
                >
                  <span style={{ color: '#14B8A6', fontWeight: 700, fontSize: '0.88rem' }}>
                    Q{idx + 1}
                  </span>
                  <input
                    type="text"
                    value={q}
                    onChange={(e) => {
                      const updated = [...questions];
                      updated[idx] = e.target.value;
                      setQuestions(updated);
                      if (studyId) api.updateStudy(studyId, { script_questions: updated }).catch(() => {});
                    }}
                    style={{
                      flex: 1,
                      background: 'transparent',
                      border: 'none',
                      color: '#FFFFFF',
                      fontSize: '0.9rem',
                      outline: 'none',
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => {
                      const nextQ = questions.filter((_, i) => i !== idx);
                      setQuestions(nextQ);
                      if (studyId) api.updateStudy(studyId, { script_questions: nextQ }).catch(() => {});
                    }}
                    style={{ background: 'transparent', border: 'none', color: '#535D5D', cursor: 'pointer' }}
                  >
                    <Trash2 size={15} />
                  </button>
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
                  background: '#111616',
                  border: '1px solid #202727',
                  borderRadius: '10px',
                  padding: '12px 16px',
                  color: '#FFFFFF',
                  fontSize: '0.88rem',
                  outline: 'none',
                }}
              />
              <button
                type="button"
                onClick={() => {
                  if (newQuestion.trim()) {
                    const nextQ = [...questions, newQuestion.trim()];
                    setQuestions(nextQ);
                    setNewQuestion('');
                    if (studyId) api.updateStudy(studyId, { script_questions: nextQ }).catch(() => {});
                  }
                }}
                style={{
                  background: 'rgba(20, 184, 166, 0.15)',
                  border: '1px solid rgba(20, 184, 166, 0.3)',
                  color: '#22D3EE',
                  borderRadius: '10px',
                  padding: '0 20px',
                  fontWeight: 600,
                  fontSize: '0.88rem',
                  cursor: 'pointer',
                }}
              >
                Add Question
              </button>
            </div>
          </div>
        )}

        {/* ============================================================
            STEP 4: SYNTHETIC INTERVIEWS & SIMULATION
           ============================================================ */}
        {currentStep === 4 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
              <div>
                <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: '#FFFFFF', margin: '0 0 4px 0' }}>
                  Synthetic Persona Interviews
                </h1>
                <p style={{ fontSize: '0.88rem', color: '#8D9999', margin: 0 }}>
                  Multi-turn qualitative interviews simulated across {personas.length} personas.
                </p>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={handleRunBatchInterviews}
                  disabled={isBatchRunning}
                  style={{
                    background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                    border: 'none',
                    borderRadius: '8px',
                    padding: '10px 20px',
                    color: '#080909',
                    fontWeight: 700,
                    fontSize: '0.88rem',
                    cursor: isBatchRunning ? 'not-allowed' : 'pointer',
                    opacity: isBatchRunning ? 0.6 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <Sparkles size={16} className={isBatchRunning ? 'animate-spin' : ''} />
                  {isBatchRunning ? 'Running Interviews...' : 'Run All Synthetic Interviews'}
                </button>
                <button
                  type="button"
                  onClick={handleGenerateFinalReport}
                  disabled={isGeneratingReport}
                  style={{
                    background: '#111616',
                    border: '1px solid #14B8A6',
                    color: '#22D3EE',
                    borderRadius: '8px',
                    padding: '10px 20px',
                    fontSize: '0.88rem',
                    fontWeight: 700,
                    cursor: isGeneratingReport ? 'not-allowed' : 'pointer',
                    opacity: isGeneratingReport ? 0.6 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <FileText size={16} />
                  {isGeneratingReport ? 'Synthesizing Report...' : 'Generate Decision Report'}
                </button>
              </div>
            </div>

            {/* Persona Selector Tabs */}
            {personas.length === 0 ? (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '12px',
                  textAlign: 'center',
                  padding: '48px 24px',
                  border: '1px dashed #202727',
                  borderRadius: '16px',
                  color: '#8D9999',
                }}
              >
                <MessageSquare size={26} className="text-teal-400" />
                <div style={{ fontSize: '1rem', fontWeight: 600, color: '#FFFFFF' }}>No personas to interview yet</div>
                <div style={{ fontSize: '0.85rem', maxWidth: '420px' }}>
                  Generate grounded personas in the Personas step first — then run interviews here.
                </div>
                <button
                  type="button"
                  onClick={() => handleStepChange(2)}
                  style={{
                    marginTop: '6px',
                    background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                    border: 'none',
                    borderRadius: '8px',
                    padding: '10px 20px',
                    color: '#080909',
                    fontWeight: 700,
                    fontSize: '0.85rem',
                    cursor: 'pointer',
                  }}
                >
                  Go to Personas
                </button>
              </div>
            ) : (
            <div style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '4px' }}>
              {personas.map((p) => {
                const status = interviewStatusMap[p.id] || 'pending';
                const isActive = activeInterviewPersonaId === p.id;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => {
                      setActiveInterviewPersonaId(p.id);
                      setChatMessages([]);
                      setConversationId(null);
                    }}
                    style={{
                      background: isActive ? 'rgba(20, 184, 166, 0.15)' : '#111616',
                      border: isActive ? '1px solid #14B8A6' : '1px solid #202727',
                      color: isActive ? '#22D3EE' : '#8D9999',
                      padding: '8px 14px',
                      borderRadius: '8px',
                      fontSize: '0.84rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                    }}
                  >
                    <span>{p.name}</span>
                    <span
                      style={{
                        fontSize: '0.68rem',
                        fontWeight: 700,
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background:
                          status === 'completed'
                            ? 'rgba(16, 185, 129, 0.15)'
                            : status === 'in_progress'
                            ? 'rgba(34, 211, 238, 0.15)'
                            : 'rgba(255, 255, 255, 0.05)',
                        color:
                          status === 'completed'
                            ? '#10B981'
                            : status === 'in_progress'
                            ? '#22D3EE'
                            : '#8D9999',
                      }}
                    >
                      {status === 'completed' ? 'Completed' : status === 'in_progress' ? 'Running' : 'Pending'}
                    </span>
                  </button>
                );
              })}
            </div>
            )}

            {/* Chat Transcript Area */}
            <div
              ref={interviewChatRef}
              style={{
                background: '#111616',
                border: '1px solid #202727',
                borderRadius: '16px',
                padding: '24px',
                minHeight: '380px',
                maxHeight: '480px',
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
                gap: '16px',
              }}
            >
              {chatMessages.length === 0 && (
                <div style={{ textAlign: 'center', color: '#8D9999', margin: 'auto', padding: '32px 0' }}>
                  <MessageSquare size={28} className="text-teal-400 mx-auto mb-2" />
                  <div style={{ fontSize: '0.95rem', fontWeight: 600, color: '#FFFFFF' }}>
                    Interactive Interview Transcript
                  </div>
                  <div style={{ fontSize: '0.82rem', color: '#8D9999', marginTop: '4px' }}>
                    Click &quot;Run All Synthetic Interviews&quot; or ask a specific follow-up question below.
                  </div>
                </div>
              )}

              {chatMessages.map((msg, idx) => {
                const isErrorTurn = typeof msg.id === 'string' && msg.id.startsWith('turn_err_');
                return (
                <div
                  key={msg.id || idx}
                  role={isErrorTurn ? 'alert' : undefined}
                  style={{
                    alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: '82%',
                    background: isErrorTurn
                      ? 'rgba(239, 68, 68, 0.08)'
                      : msg.role === 'user'
                      ? 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)'
                      : '#161C1C',
                    color: isErrorTurn ? '#FCA5A5' : '#FFFFFF',
                    padding: '14px 18px',
                    borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                    border: isErrorTurn
                      ? '1px solid rgba(239, 68, 68, 0.4)'
                      : msg.role === 'user'
                      ? 'none'
                      : '1px solid #202727',
                  }}
                >
                  <div style={{ fontSize: '0.9rem', lineHeight: 1.5 }}>{msg.content}</div>
                  {msg.role !== 'user' && msg.served_by && (
                    <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.72rem', color: '#22D3EE' }}>
                      <Zap size={11} />
                      <span>Served by {msg.served_by}</span>
                      {msg.latency_ms && <span>• {Math.round(msg.latency_ms)}ms</span>}
                    </div>
                  )}
                </div>
                );
              })}

              {isSimulating && (
                <div style={{ alignSelf: 'flex-start', color: '#8D9999', fontSize: '0.84rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Sparkles size={14} className="text-teal-400 animate-spin" />
                  Generating grounded synthetic response...
                </div>
              )}
            </div>

            {/* Prompt input for live interview turn */}
            <form onSubmit={handleSendInterviewMessage} style={{ display: 'flex', gap: '10px' }}>
              <input
                type="text"
                value={userInputMessage}
                onChange={(e) => setUserInputMessage(e.target.value)}
                placeholder="Ask a follow-up interview question..."
                style={{
                  flex: 1,
                  background: '#111616',
                  border: '1px solid #202727',
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
                  background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                  border: 'none',
                  color: '#080909',
                  borderRadius: '12px',
                  padding: '0 20px',
                  fontWeight: 700,
                  cursor: isSimulating || !userInputMessage.trim() ? 'not-allowed' : 'pointer',
                }}
              >
                <Send size={16} />
              </button>
            </form>
          </div>
        )}

        {/* ============================================================
            STEP 5: COMPREHENSIVE FINAL REPORT
           ============================================================ */}
        {currentStep === 5 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
            {reportError && (
              <div
                role="alert"
                style={{
                  background: 'rgba(239, 68, 68, 0.08)',
                  border: '1px solid rgba(239, 68, 68, 0.4)',
                  color: '#FCA5A5',
                  borderRadius: '8px',
                  padding: '12px 16px',
                  fontSize: '0.88rem',
                }}
              >
                Report generation failed: {reportError}
              </div>
            )}
            {/* Header & Export Actions */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
              <div>
                <span
                  style={{
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    padding: '3px 8px',
                    borderRadius: '6px',
                    background: report ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)',
                    color: report ? '#10B981' : '#FCA5A5',
                    border: report ? '1px solid rgba(16, 185, 129, 0.25)' : '1px solid rgba(239, 68, 68, 0.25)',
                  }}
                >
                  {report
                    ? `Decision Report Ready • Version ${report.version || 1} ${availableReports.length > 1 ? `(${availableReports.length} versions)` : ''}`
                    : 'No report generated yet'}
                </span>
                <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: '#FFFFFF', margin: '8px 0 4px 0' }}>
                  {report?.title || study?.title || 'Market Research & Validation Report'}
                </h1>
                <p style={{ fontSize: '0.84rem', color: '#8D9999', margin: 0 }}>
                  Synthesized from {personas.length} grounded synthetic personas and empirical research claims.
                </p>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={copyReportMarkdown}
                  style={{
                    background: '#111616',
                    border: '1px solid #202727',
                    color: '#FFFFFF',
                    borderRadius: '8px',
                    padding: '8px 14px',
                    fontSize: '0.82rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <Copy size={14} /> {copiedToast ? 'Copied!' : 'Copy'}
                </button>
                <button
                  type="button"
                  onClick={exportReportMarkdown}
                  style={{
                    background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                    border: 'none',
                    color: '#080909',
                    borderRadius: '8px',
                    padding: '8px 16px',
                    fontSize: '0.82rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <Download size={14} /> Export Markdown
                </button>
              </div>
            </div>

            {/* Metrics Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
              <div style={{ background: '#111616', border: '1px solid #202727', borderRadius: '14px', padding: '18px 20px' }}>
                <div style={{ fontSize: '0.78rem', color: '#8D9999' }}>Demand Signal</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#10B981', marginTop: '4px' }}>
                  {report?.metrics?.demand_score != null ? `${report.metrics.demand_score}%` : '—'}
                </div>
              </div>
              <div style={{ background: '#111616', border: '1px solid #202727', borderRadius: '14px', padding: '18px 20px' }}>
                <div style={{ fontSize: '0.78rem', color: '#8D9999' }}>Grounded Personas</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#22D3EE', marginTop: '4px' }}>
                  {personas.length}
                </div>
              </div>
              <div style={{ background: '#111616', border: '1px solid #202727', borderRadius: '14px', padding: '18px 20px' }}>
                <div style={{ fontSize: '0.78rem', color: '#8D9999' }}>Confidence Score</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#14B8A6', marginTop: '4px' }}>
                  {report?.metrics?.confidence_score != null
                    ? `${Math.round(report.metrics.confidence_score * 100)}%`
                    : '—'}
                </div>
              </div>
            </div>

            {/* Executive Summary */}
            <div style={{ background: '#111616', border: '1px solid #202727', borderRadius: '16px', padding: '24px' }}>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#22D3EE', margin: '0 0 12px 0' }}>
                Executive Summary
              </h2>
              <p style={{ fontSize: '0.9rem', color: '#E5E7EB', lineHeight: 1.6, margin: 0, whiteSpace: 'pre-line' }}>
                {report?.executive_summary ||
                  `Research validation report for "${study?.prompt || 'business concept'}". Personas indicate high adoption willingness driven by convenience, speed, and transparent pricing.`}
              </p>
            </div>

            {/* Key Findings */}
            <div style={{ background: '#111616', border: '1px solid #202727', borderRadius: '16px', padding: '24px' }}>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#FFFFFF', margin: '0 0 14px 0' }}>
                Key Findings
              </h2>
              <ul style={{ margin: 0, paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {(
                  report?.key_findings || [
                    'Strong baseline demand exists across target users when framed on immediate workflow time savings.',
                    'Transparent, predictable pricing tiers are a non-negotiable trust prerequisite.',
                    'Clear onboarding and visible evidence of quality prevent early drop-off.',
                  ]
                ).map((kf, i) => (
                  <li key={i} style={{ fontSize: '0.88rem', color: '#D1D5DB', lineHeight: 1.5 }}>
                    {kf}
                  </li>
                ))}
              </ul>
            </div>

            {/* Recommendations */}
            <div style={{ background: '#111616', border: '1px solid #202727', borderRadius: '16px', padding: '24px' }}>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#10B981', margin: '0 0 14px 0' }}>
                Strategic Recommendations
              </h2>
              <ul style={{ margin: 0, paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {(
                  report?.recommendations || [
                    'Launch MVP with focused core features directly resolving primary friction.',
                    'Emphasize speed and reliability in all messaging and product tutorials.',
                  ]
                ).map((rec, i) => (
                  <li key={i} style={{ fontSize: '0.88rem', color: '#D1D5DB', lineHeight: 1.5 }}>
                    {rec}
                  </li>
                ))}
              </ul>
            </div>

            {/* Methodology & Limitations Disclaimer */}
            <div style={{ background: 'rgba(20, 184, 166, 0.05)', border: '1px solid rgba(20, 184, 166, 0.2)', borderRadius: '12px', padding: '16px 20px', fontSize: '0.8rem', color: '#8D9999', lineHeight: 1.5 }}>
              <strong style={{ color: '#22D3EE' }}>Research Methodology Note:</strong> This report synthesizes real empirical research evidence and public dataset parameters with exploratory synthetic persona simulations. Simulations model expected behavioral dynamics based on grounded empirical distributions.
            </div>
          </div>
        )}
      </main>

      {/* Viewing Full Persona Modal */}
      {viewingPersona && (
        <div
          className="bx-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.8)',
            backdropFilter: 'blur(8px)',
            zIndex: 50,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
          }}
          onClick={() => setViewingPersona(null)}
        >
          <div
            className="bx-modal"
            style={{
              background: '#111616',
              border: '1px solid #202727',
              borderRadius: '20px',
              maxWidth: '640px',
              width: '100%',
              maxHeight: '85vh',
              overflowY: 'auto',
              padding: '28px 32px',
              display: 'flex',
              flexDirection: 'column',
              gap: '20px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                <div
                  style={{
                    width: '48px',
                    height: '48px',
                    borderRadius: '12px',
                    background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
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
                  <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#FFFFFF', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {viewingPersona.name}
                    {viewingPersona.data_source === 'cached' && (
                      <span
                        title="Served from seeded/cached data — not generated live for this study"
                        style={{ fontSize: '0.62rem', fontWeight: 400, color: '#8D9999', background: '#141818', border: '1px solid #2A3130', padding: '2px 6px', borderRadius: '4px', fontFamily: 'var(--font-mono)', letterSpacing: '0.06em' }}
                      >
                        CACHED
                      </span>
                    )}
                  </h3>
                  <div style={{ fontSize: '0.84rem', color: '#22D3EE' }}>{viewingPersona.archetype}</div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setViewingPersona(null)}
                style={{ background: 'transparent', border: 'none', color: '#8D9999', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            <p style={{ fontSize: '0.88rem', color: '#D1D5DB', lineHeight: 1.5, margin: 0 }}>
              {viewingPersona.description || viewingPersona.tagline}
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', background: '#0D1111', padding: '14px', borderRadius: '10px', border: '1px solid #202727' }}>
              <div>
                <span style={{ fontSize: '0.72rem', color: '#8D9999' }}>Age: </span>
                <span style={{ fontSize: '0.82rem', color: '#FFF' }}>{viewingPersona.demographics?.age || '28'}</span>
              </div>
              <div>
                <span style={{ fontSize: '0.72rem', color: '#8D9999' }}>Occupation: </span>
                <span style={{ fontSize: '0.82rem', color: '#FFF' }}>{viewingPersona.demographics?.occupation || viewingPersona.archetype || 'Professional'}</span>
              </div>
              <div>
                <span style={{ fontSize: '0.72rem', color: '#8D9999' }}>Location: </span>
                <span style={{ fontSize: '0.82rem', color: '#FFF' }}>{viewingPersona.demographics?.location || 'Dhaka, Bangladesh'}</span>
              </div>
              <div>
                <span style={{ fontSize: '0.72rem', color: '#8D9999' }}>Country: </span>
                <span style={{ fontSize: '0.82rem', color: '#14B8A6', fontWeight: 600 }}>{viewingPersona.origin_country || viewingPersona.country_code || 'BD'}</span>
              </div>
            </div>

            {/* Big Five Personality */}
            {viewingPersona.personality && (
              <div style={{ background: '#0D1111', padding: '14px', borderRadius: '10px', border: '1px solid #202727' }}>
                <div style={{ fontSize: '0.74rem', fontWeight: 700, color: '#14B8A6', letterSpacing: '0.06em', marginBottom: '8px' }}>
                  BIG FIVE PERSONALITY PROFILE
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '8px', textAlign: 'center' }}>
                  {[
                    { label: 'Openness', val: viewingPersona.personality.openness, color: '#38BDF8' },
                    { label: 'Conscientious', val: viewingPersona.personality.conscientiousness, color: '#10B981' },
                    { label: 'Extroversion', val: viewingPersona.personality.extroversion, color: '#F59E0B' },
                    { label: 'Agreeable', val: viewingPersona.personality.agreeableness, color: '#A855F7' },
                    { label: 'Neuroticism', val: viewingPersona.personality.neuroticism, color: '#EC4899' },
                  ].map((t) => (
                    <div key={t.label}>
                      <div style={{ fontSize: '0.75rem', fontWeight: 700, color: t.color }}>{t.val}</div>
                      <div style={{ height: '3px', background: '#202727', borderRadius: '2px', overflow: 'hidden', margin: '3px 0' }}>
                        <div style={{ width: `${t.val}%`, height: '100%', background: t.color }} />
                      </div>
                      <div style={{ fontSize: '0.65rem', color: '#8D9999' }}>{t.label}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Key Lifestyle Attributes */}
            {viewingPersona.detailed_attributes && Object.keys(viewingPersona.detailed_attributes).length > 0 && (
              <div style={{ background: '#0D1111', padding: '14px', borderRadius: '10px', border: '1px solid #202727' }}>
                <div style={{ fontSize: '0.74rem', fontWeight: 700, color: '#22D3EE', letterSpacing: '0.06em', marginBottom: '8px' }}>
                  LIFESTYLE & ROUTINE SNAPSHOT
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '0.78rem' }}>
                  {viewingPersona.detailed_attributes.commute_mode && (
                    <div><span style={{ color: '#8D9999' }}>Commute: </span><span style={{ color: '#FFF' }}>{viewingPersona.detailed_attributes.commute_mode}</span></div>
                  )}
                  {viewingPersona.detailed_attributes.work_schedule && (
                    <div><span style={{ color: '#8D9999' }}>Schedule: </span><span style={{ color: '#FFF' }}>{viewingPersona.detailed_attributes.work_schedule}</span></div>
                  )}
                  {viewingPersona.detailed_attributes.food_source && (
                    <div><span style={{ color: '#8D9999' }}>Food: </span><span style={{ color: '#FFF' }}>{viewingPersona.detailed_attributes.food_source}</span></div>
                  )}
                  {viewingPersona.detailed_attributes.payment_method && (
                    <div><span style={{ color: '#8D9999' }}>Payment: </span><span style={{ color: '#FFF' }}>{viewingPersona.detailed_attributes.payment_method}</span></div>
                  )}
                  {viewingPersona.detailed_attributes.communication_style && (
                    <div><span style={{ color: '#8D9999' }}>Communication: </span><span style={{ color: '#FFF' }}>{viewingPersona.detailed_attributes.communication_style}</span></div>
                  )}
                  {viewingPersona.detailed_attributes.hobbies && (
                    <div style={{ gridColumn: '1 / -1' }}><span style={{ color: '#8D9999' }}>Hobbies: </span><span style={{ color: '#FFF' }}>{viewingPersona.detailed_attributes.hobbies}</span></div>
                  )}
                </div>
              </div>
            )}

            {/* Grounded Claims & Provenance */}
            <div>
              <div style={{ fontSize: '0.74rem', fontWeight: 700, color: '#22D3EE', letterSpacing: '0.06em', marginBottom: '8px' }}>
                GROUNDED BEHAVIORAL CLAIMS & PROVENANCE
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {(viewingPersona.attributes || [
                  { category: 'Goals', title: 'Streamline daily tasks', description: 'Wants to minimize overhead' },
                  { category: 'Pain Points', title: 'High recurring cost', description: 'Sensitivity to expensive software' },
                ]).map((attr: any, idx: number) => (
                  <div key={idx} style={{ background: '#0D1111', padding: '10px 12px', borderRadius: '8px', border: '1px solid #202727' }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#FFF' }}>{attr.title}</div>
                    <div style={{ fontSize: '0.75rem', color: '#8D9999', marginTop: '2px' }}>{attr.description}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
