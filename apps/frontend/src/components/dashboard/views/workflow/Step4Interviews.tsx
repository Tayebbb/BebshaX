import React from 'react';
import { AlertTriangle, FileText, MessageSquare, Send, Sparkles } from 'lucide-react';
import { ConversationTurn, Persona } from '../../../../types';
import { READ_ONLY_TITLE } from './types';
import { MemoryDisclosure, RouteDisclosure } from '../../../common/MemoryDisclosure';
import { RequestIdTag } from '../../../common/RequestIdTag';

/** Step 4 — synthetic interviews & live simulation. Pure JSX extraction from
 * StudyWorkflowView: batch/polling/chat state and handlers stay in the parent;
 * the transcript container ref is owned by the parent's auto-scroll effect. */
interface Step4InterviewsProps {
  personas: Persona[];
  isBatchRunning: boolean;
  batchStartBlockedReason?: string | null;
  handleRunBatchInterviews: () => Promise<void>;
  onCancelBatch: () => void;
  isGeneratingReport: boolean;
  handleGenerateFinalReport: () => Promise<void>;
  handleStepChange: (newStep: number, opts?: { reportReady?: boolean }) => void;
  interviewStatusMap: Record<string, 'pending' | 'in_progress' | 'completed' | 'failed'>;
  /** Backend-reported reason per failed persona interview (shown on the pill). */
  interviewFailureReasons?: Record<string, string>;
  /** Whole-batch failure (job never started / lost) with its request id. */
  batchError?: { message: string; requestId: string | null } | null;
  activeInterviewPersonaId: string;
  setActiveInterviewPersonaId: React.Dispatch<React.SetStateAction<string>>;
  setChatMessages: React.Dispatch<React.SetStateAction<ConversationTurn[]>>;
  setConversationId: React.Dispatch<React.SetStateAction<string | null>>;
  interviewChatRef: React.MutableRefObject<HTMLDivElement | null>;
  chatMessages: ConversationTurn[];
  isSimulating: boolean;
  isRestoringInterview?: boolean;
  restoreError?: string | null;
  onRetryRestore?: () => void;
  handleSendInterviewMessage: (e: React.FormEvent) => Promise<void>;
  userInputMessage: string;
  setUserInputMessage: React.Dispatch<React.SetStateAction<string>>;
  /** Example (demo) studies are viewable but never mutable from here. */
  isReadOnly?: boolean;
}

export const Step4Interviews: React.FC<Step4InterviewsProps> = ({
  personas,
  isBatchRunning,
  batchStartBlockedReason = null,
  handleRunBatchInterviews,
  onCancelBatch,
  isGeneratingReport,
  handleGenerateFinalReport,
  handleStepChange,
  interviewStatusMap,
  interviewFailureReasons = {},
  batchError = null,
  activeInterviewPersonaId,
  setActiveInterviewPersonaId,
  interviewChatRef,
  chatMessages,
  isSimulating,
  isRestoringInterview = false,
  restoreError = null,
  onRetryRestore,
  handleSendInterviewMessage,
  userInputMessage,
  setUserInputMessage,
  isReadOnly = false,
}) => {
  const batchRunDisabled = isBatchRunning || isReadOnly || Boolean(batchStartBlockedReason);
  return (
    <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
              <div>
                <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--text-main)', margin: '0 0 4px 0' }}>
                  Synthetic Persona Interviews
                </h1>
                <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', margin: 0 }}>
                  Multi-turn qualitative interviews simulated across {personas.length} personas.
                </p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'flex-end', minWidth: 0, maxWidth: '100%' }}>
                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    onClick={handleRunBatchInterviews}
                    disabled={batchRunDisabled}
                    aria-describedby={batchStartBlockedReason ? 'batch-start-requirements' : undefined}
                    title={isReadOnly ? READ_ONLY_TITLE : batchStartBlockedReason ?? undefined}
                    style={{
                      background: 'var(--accent-gradient)',
                      border: 'none',
                      borderRadius: '8px',
                      padding: '10px 20px',
                      color: 'var(--text-on-accent)',
                      fontWeight: 700,
                      fontSize: '0.88rem',
                      cursor: batchRunDisabled ? 'not-allowed' : 'pointer',
                      opacity: batchRunDisabled ? 0.6 : 1,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                    }}
                  >
                    <Sparkles size={16} className={isBatchRunning ? 'animate-spin' : ''} />
                    {isBatchRunning ? 'Running Interviews...' : 'Run All Synthetic Interviews'}
                  </button>
                  {isBatchRunning && (
                    <button
                      type="button"
                      onClick={onCancelBatch}
                      style={{
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--text-secondary)',
                        borderRadius: '8px',
                        padding: '10px 16px',
                        fontSize: '0.84rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      Pause updates
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handleGenerateFinalReport}
                    disabled={isGeneratingReport || isReadOnly}
                    title={isReadOnly ? READ_ONLY_TITLE : undefined}
                    style={{
                      background: 'var(--bg-card)',
                      border: '1px solid var(--accent-teal)',
                      color: 'var(--accent-cyan)',
                      borderRadius: '8px',
                      padding: '10px 20px',
                      fontSize: '0.88rem',
                      fontWeight: 700,
                      cursor: isGeneratingReport || isReadOnly ? 'not-allowed' : 'pointer',
                      opacity: isGeneratingReport || isReadOnly ? 0.6 : 1,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <FileText size={16} />
                    {isGeneratingReport ? 'Synthesizing Report...' : 'Generate Decision Report'}
                  </button>
                </div>
                {batchStartBlockedReason && (
                  <div
                    id="batch-start-requirements"
                    role="status"
                    style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', textAlign: 'right', maxWidth: '100%', overflowWrap: 'anywhere' }}
                  >
                    {batchStartBlockedReason}
                  </div>
                )}
                {isBatchRunning && (
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'right' }}>
                    This can take 1–2 minutes on free providers. Cancelling stops polling but the backend job continues.
                  </div>
                )}
              </div>
            </div>

            {/* Persona Selector Tabs */}
            {batchError && (
              <div
                role="alert"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  background: 'rgba(239, 68, 68, 0.08)',
                  border: '1px solid rgba(239, 68, 68, 0.4)',
                  borderRadius: '10px',
                  padding: '12px 16px',
                  color: 'var(--status-error-text)',
                  fontSize: '0.86rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <AlertTriangle size={15} aria-hidden="true" />
                  <span>Batch interview status: {batchError.message}</span>
                </div>
                <RequestIdTag requestId={batchError.requestId} />
              </div>
            )}
            {personas.length === 0 ? (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '12px',
                  textAlign: 'center',
                  padding: '48px 24px',
                  border: '1px dashed var(--border-subtle)',
                  borderRadius: '16px',
                  color: 'var(--text-secondary)',
                }}
              >
                <MessageSquare size={26} className="text-teal-400" />
                <div style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)' }}>No personas to interview yet</div>
                <div style={{ fontSize: '0.85rem', maxWidth: '420px' }}>
                  Generate personas in the Personas step first — then run interviews here.
                </div>
                <button
                  type="button"
                  onClick={() => handleStepChange(2)}
                  style={{
                    marginTop: '6px',
                    background: 'var(--accent-gradient)',
                    border: 'none',
                    borderRadius: '8px',
                    padding: '10px 20px',
                    color: 'var(--text-on-accent)',
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
                const failureReason = status === 'failed' ? interviewFailureReasons[p.id] : undefined;
                return (
                  <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
                  <button
                    type="button"
                    title={failureReason ? `Failed: ${failureReason}` : undefined}
                    onClick={() => setActiveInterviewPersonaId(p.id)}
                    style={{
                      background: isActive ? 'var(--accent-subtle)' : 'var(--bg-card)',
                      border: isActive ? '1px solid var(--accent-teal)' : '1px solid var(--border-subtle)',
                      color: isActive ? 'var(--accent-cyan)' : 'var(--text-secondary)',
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
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background:
                          status === 'completed'
                            ? 'var(--status-success-bg)'
                            : status === 'in_progress'
                            ? 'var(--status-info-bg)'
                            : status === 'failed'
                            ? 'var(--status-error-bg)'
                            : 'var(--fill-soft)',
                        color:
                          status === 'completed'
                            ? 'var(--status-success-text)'
                            : status === 'in_progress'
                            ? 'var(--accent-cyan)'
                            : status === 'failed'
                            ? 'var(--status-error-text)'
                            : 'var(--text-secondary)',
                      }}
                    >
                      {status === 'completed'
                        ? 'Completed'
                        : status === 'in_progress'
                        ? 'Running'
                        : status === 'failed'
                        ? 'Failed'
                        : 'Pending'}
                    </span>
                    {failureReason && (
                      <span
                        style={{
                          fontSize: '0.72rem',
                          fontWeight: 500,
                          color: 'var(--status-error-text)',
                          maxWidth: '220px',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {failureReason}
                      </span>
                    )}
                  </button>
                  {status === 'failed' && (
                    <button
                      type="button"
                      onClick={handleRunBatchInterviews}
                      disabled={batchRunDisabled}
                      aria-describedby={batchStartBlockedReason ? 'batch-start-requirements' : undefined}
                      title={isReadOnly ? READ_ONLY_TITLE : batchStartBlockedReason ?? `Re-runs the interviews for every persona — ${p.name}'s did not finish`}
                      style={{
                        background: 'transparent',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--accent-cyan)',
                        borderRadius: '6px',
                        padding: '5px 10px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        cursor: batchRunDisabled ? 'not-allowed' : 'pointer',
                        opacity: batchRunDisabled ? 0.5 : 1,
                      }}
                    >
                      Re-run all
                    </button>
                  )}
                  </div>
                );
              })}
            </div>
            )}

            {/* Chat Transcript Area */}
            <div
              ref={interviewChatRef}
              role="log"
              aria-label="Interview transcript"
              aria-live="polite"
              aria-relevant="additions text"
              aria-busy={isRestoringInterview || isSimulating}
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                padding: 'clamp(14px, 3vw, 24px)',
                minHeight: '240px',
                maxHeight: 'min(480px, 55dvh)',
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
                gap: '16px',
              }}
            >
              {isRestoringInterview && (
                <div role="status" style={{ color: 'var(--text-secondary)', fontSize: '0.84rem' }}>
                  Loading saved transcript...
                </div>
              )}
              {restoreError && (
                <div role="alert" className="bx-alert bx-alert--error">
                  <span>{restoreError}</span>
                  <button type="button" className="bx-btn bx-btn--secondary" onClick={onRetryRestore}>Retry transcript</button>
                </div>
              )}
              {chatMessages.length === 0 && !isRestoringInterview && !restoreError && (
                <div style={{ textAlign: 'center', color: 'var(--text-secondary)', margin: 'auto', padding: '32px 0' }}>
                  <MessageSquare size={28} className="text-teal-400 mx-auto mb-2" />
                  <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-main)' }}>
                    Interactive Interview Transcript
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    Click &quot;Run All Synthetic Interviews&quot; or ask a specific follow-up question below.
                  </div>
                </div>
              )}

              {chatMessages.map((msg, idx) => {
                const isErrorTurn = typeof msg.id === 'string' && msg.id.startsWith('turn_err_');
                return (
                <article
                  key={msg.id || idx}
                  className="bx-pop"
                  role={isErrorTurn ? 'alert' : undefined}
                  aria-label={isErrorTurn ? undefined : msg.role === 'user' ? 'Your question' : 'Synthetic persona response'}
                  style={{
                    alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: 'min(92%, 640px)',
                    background: isErrorTurn
                      ? 'rgba(239, 68, 68, 0.08)'
                      : msg.role === 'user'
                      ? 'var(--accent-gradient)'
                      : 'var(--bg-card-hover)',
                    color: isErrorTurn ? 'var(--status-error-text)' : msg.role === 'user' ? 'var(--text-on-accent)' : 'var(--text-main)',
                    padding: '14px 18px',
                    borderRadius: msg.role === 'user' ? '8px 8px 2px 8px' : '8px 8px 8px 2px',
                    overflowWrap: 'anywhere',
                    border: isErrorTurn
                      ? '1px solid rgba(239, 68, 68, 0.4)'
                      : msg.role === 'user'
                      ? 'none'
                      : '1px solid var(--border-subtle)',
                  }}
                >
                  <div style={{ fontSize: '0.9rem', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{msg.content}</div>
                  {msg.role !== 'user' && !isErrorTurn && (
                    <>
                      <MemoryDisclosure memories={msg.retrieved_memories} compact />
                      <RouteDisclosure servedBy={msg.served_by} latencyMs={msg.latency_ms} compact />
                    </>
                  )}
                </article>
                );
              })}

              {isSimulating && (
                <div style={{ alignSelf: 'flex-start', color: 'var(--text-secondary)', fontSize: '0.84rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Sparkles size={14} className="text-teal-400 animate-spin" />
                  Generating synthetic response...
                </div>
              )}
            </div>

            {/* Prompt input for live interview turn */}
            <form onSubmit={handleSendInterviewMessage} style={{ display: 'flex', gap: '10px', minWidth: 0 }}>
              <input
                type="text"
                value={userInputMessage}
                onChange={(e) => setUserInputMessage(e.target.value)}
                placeholder={
                  isReadOnly
                    ? 'Example study — read-only. Create your own study to run interviews.'
                    : 'Ask a follow-up interview question...'
                }
                aria-label="Follow-up interview question"
                disabled={isReadOnly || isRestoringInterview || Boolean(restoreError) || isSimulating || isBatchRunning || isGeneratingReport}
                title={isReadOnly ? READ_ONLY_TITLE : undefined}
                style={{
                  flex: 1,
                  minWidth: 0,
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  padding: '12px 14px',
                  color: 'var(--text-main)',
                  fontSize: '0.88rem',
                  opacity: isReadOnly ? 0.6 : 1,
                }}
              />
              <button
                type="submit"
                className="bx-btn bx-btn--primary bx-btn--icon"
                aria-label="Send question"
                disabled={isSimulating || isRestoringInterview || Boolean(restoreError) || isBatchRunning || isGeneratingReport || !userInputMessage.trim() || isReadOnly}
                title={isReadOnly ? READ_ONLY_TITLE : 'Send question'}
                style={{
                  width: '44px',
                  minHeight: '44px',
                  flexShrink: 0,
                }}
              >
                <Send size={16} aria-hidden="true" />
              </button>
            </form>
    </>
  );
};
