import React from 'react';
import { FileText, MessageSquare, Send, Sparkles, Zap } from 'lucide-react';
import { ConversationTurn, Persona } from '../../../../types';

/** Step 4 — synthetic interviews & live simulation. Pure JSX extraction from
 * StudyWorkflowView: batch/polling/chat state and handlers stay in the parent;
 * the transcript container ref is owned by the parent's auto-scroll effect. */
interface Step4InterviewsProps {
  personas: Persona[];
  isBatchRunning: boolean;
  handleRunBatchInterviews: () => Promise<void>;
  onCancelBatch: () => void;
  isGeneratingReport: boolean;
  handleGenerateFinalReport: () => Promise<void>;
  handleStepChange: (newStep: number, opts?: { reportReady?: boolean }) => void;
  interviewStatusMap: Record<string, 'pending' | 'in_progress' | 'completed' | 'failed'>;
  activeInterviewPersonaId: string;
  setActiveInterviewPersonaId: React.Dispatch<React.SetStateAction<string>>;
  setChatMessages: React.Dispatch<React.SetStateAction<ConversationTurn[]>>;
  setConversationId: React.Dispatch<React.SetStateAction<string | null>>;
  interviewChatRef: React.MutableRefObject<HTMLDivElement | null>;
  chatMessages: ConversationTurn[];
  isSimulating: boolean;
  handleSendInterviewMessage: (e: React.FormEvent) => Promise<void>;
  userInputMessage: string;
  setUserInputMessage: React.Dispatch<React.SetStateAction<string>>;
}

export const Step4Interviews: React.FC<Step4InterviewsProps> = ({
  personas,
  isBatchRunning,
  handleRunBatchInterviews,
  onCancelBatch,
  isGeneratingReport,
  handleGenerateFinalReport,
  handleStepChange,
  interviewStatusMap,
  activeInterviewPersonaId,
  setActiveInterviewPersonaId,
  setChatMessages,
  setConversationId,
  interviewChatRef,
  chatMessages,
  isSimulating,
  handleSendInterviewMessage,
  userInputMessage,
  setUserInputMessage,
}) => {
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

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'flex-end' }}>
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
                      color: 'var(--text-on-accent)',
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
                      Cancel
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handleGenerateFinalReport}
                    disabled={isGeneratingReport}
                    style={{
                      background: 'var(--bg-card)',
                      border: '1px solid var(--accent-teal)',
                      color: 'var(--accent-cyan)',
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
                {isBatchRunning && (
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'right' }}>
                    This can take 1–2 minutes on free providers. Cancelling stops polling but the backend job continues.
                  </div>
                )}
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
                  border: '1px dashed var(--border-subtle)',
                  borderRadius: '16px',
                  color: 'var(--text-secondary)',
                }}
              >
                <MessageSquare size={26} className="text-teal-400" />
                <div style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)' }}>No personas to interview yet</div>
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
                            ? 'rgba(16, 185, 129, 0.15)'
                            : status === 'in_progress'
                            ? 'rgba(34, 211, 238, 0.15)'
                            : 'var(--fill-soft)',
                        color:
                          status === 'completed'
                            ? 'var(--accent-emerald)'
                            : status === 'in_progress'
                            ? 'var(--accent-cyan)'
                            : 'var(--text-secondary)',
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
                background: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
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
                <div
                  key={msg.id || idx}
                  className="bx-pop"
                  role={isErrorTurn ? 'alert' : undefined}
                  style={{
                    alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: '82%',
                    background: isErrorTurn
                      ? 'rgba(239, 68, 68, 0.08)'
                      : msg.role === 'user'
                      ? 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)'
                      : 'var(--bg-card-hover)',
                    color: isErrorTurn ? 'var(--status-error-text)' : 'var(--text-main)',
                    padding: '14px 18px',
                    borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                    border: isErrorTurn
                      ? '1px solid rgba(239, 68, 68, 0.4)'
                      : msg.role === 'user'
                      ? 'none'
                      : '1px solid var(--border-subtle)',
                  }}
                >
                  <div style={{ fontSize: '0.9rem', lineHeight: 1.5 }}>{msg.content}</div>
                  {msg.role !== 'user' && msg.served_by && (
                    <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.72rem', color: 'var(--accent-cyan)' }}>
                      <Zap size={11} />
                      <span>Served by {msg.served_by}</span>
                      {msg.latency_ms && <span>• {Math.round(msg.latency_ms)}ms</span>}
                    </div>
                  )}
                </div>
                );
              })}

              {isSimulating && (
                <div style={{ alignSelf: 'flex-start', color: 'var(--text-secondary)', fontSize: '0.84rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
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
                aria-label="Follow-up interview question"
                style={{
                  flex: 1,
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '12px',
                  padding: '12px 18px',
                  color: 'var(--text-main)',
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
                  color: 'var(--text-on-accent)',
                  borderRadius: '12px',
                  padding: '0 20px',
                  fontWeight: 700,
                  cursor: isSimulating || !userInputMessage.trim() ? 'not-allowed' : 'pointer',
                }}
              >
                <Send size={16} />
              </button>
            </form>
    </>
  );
};
