import React from 'react';
import { AlertTriangle, ArrowRight, Check, CheckCircle2, FlaskConical, Loader2, Minus, Plus, Sparkles } from 'lucide-react';
import { PersonaRoleSuggestion } from '../../../../types';
import { CopilotMessage, MAX_PERSONAS_PER_ROLE, READ_ONLY_TITLE } from './types';
import { EvidenceProbe } from './evidenceProbe';
import { RequestIdTag } from '../../../common/RequestIdTag';
import { PromptInputBox } from '../../../ui/PromptInputBox';

/** Why a template-produced goal card cannot be approved. */
export const TEMPLATE_APPROVAL_BLOCKED =
  'This goal card came from a keyword template, not the AI — retry when providers are back before approving it.';

/** Step 1 — conversational context gathering + role selection drawer. Pure
 * JSX extraction from StudyWorkflowView: copilot state, persistence, and the
 * chat auto-scroll effect (targeting `copilotChatRef`) stay in the parent. */
interface Step1ContextProps {
  copilotChatRef: React.MutableRefObject<HTMLDivElement | null>;
  copilotMessages: CopilotMessage[];
  isCopilotTyping: boolean;
  showRoleSelection: boolean;
  handleApproveGoal: (summary?: string) => Promise<void>;
  handleSendCopilotMessage: (text?: string) => void;
  handleRetryCopilotMessage: (errorMessageId: string) => void;
  step1InputRef: React.MutableRefObject<HTMLTextAreaElement | null>;
  step1Prompt: string;
  setStep1Prompt: React.Dispatch<React.SetStateAction<string>>;
  roleSelectionRef: React.MutableRefObject<HTMLDivElement | null>;
  suggestedRoles: PersonaRoleSuggestion[];
  isLoadingRoles: boolean;
  roleError: string | null;
  handleRetrySuggestedRoles: () => void;
  isGeneratingPersonas: boolean;
  handleGeneratePersonas: () => Promise<void>;
  handleToggleRole: (roleId: string) => void;
  handleIncrementRole: (roleId: string, e: React.MouseEvent) => void;
  handleDecrementRole: (roleId: string, e: React.MouseEvent) => void;
  evidenceProbe: EvidenceProbe;
  onNavigateToEvidence?: () => void;
  /** Starts the evidence research run from the `not_run` state. The parent
   * withholds it for read-only studies. */
  onRunEvidence?: () => void;
  /** Example (demo) studies are viewable but never mutable from here. */
  isReadOnly?: boolean;
}

export const Step1Context: React.FC<Step1ContextProps> = ({
  copilotChatRef,
  copilotMessages,
  isCopilotTyping,
  showRoleSelection,
  handleApproveGoal,
  handleSendCopilotMessage,
  handleRetryCopilotMessage,
  step1InputRef,
  step1Prompt,
  setStep1Prompt,
  roleSelectionRef,
  suggestedRoles,
  isLoadingRoles,
  roleError,
  handleRetrySuggestedRoles,
  isGeneratingPersonas,
  handleGeneratePersonas,
  handleToggleRole,
  handleIncrementRole,
  handleDecrementRole,
  evidenceProbe,
  onNavigateToEvidence,
  onRunEvidence,
  isReadOnly = false,
}) => {
  const busy = evidenceProbe.state === 'checking' || evidenceProbe.state === 'searching';
  const evidenceLine =
    evidenceProbe.state === 'checking'
      ? 'Checking for supporting evidence…'
      : evidenceProbe.state === 'searching'
      ? 'Looking for supporting evidence…'
      : evidenceProbe.state === 'found'
      ? `Found ${evidenceProbe.claims} supporting claim${evidenceProbe.claims === 1 ? '' : 's'}` +
        (evidenceProbe.sources > 0
          ? ` from ${evidenceProbe.sources} source${evidenceProbe.sources === 1 ? '' : 's'}`
          : '') +
        ' — personas can cite them.'
      : evidenceProbe.state === 'failed'
      ? `The evidence research run failed${
          evidenceProbe.message ? ` (${evidenceProbe.message})` : ''
        }${evidenceProbe.errorCode ? ` [${evidenceProbe.errorCode}]` : ''} — nothing was collected and nothing was substituted. Retry it in the Evidence Laboratory.`
      : evidenceProbe.state === 'timeout'
      ? 'Still searching — this can take a few minutes. Check the Evidence Laboratory.'
      : evidenceProbe.state === 'empty'
      ? evidenceProbe.noLiveEvidence
        ? `The live search${evidenceProbe.provider ? ` (${evidenceProbe.provider})` : ''} returned no sources for this idea — no claims were written in their place; personas will be inferred from your description.`
        : 'No evidence claims were extracted — personas will be inferred from your description.'
      : evidenceProbe.state === 'not_run'
      ? 'No evidence run yet for this study — personas will be inferred from your description.'
      : 'Could not check for supporting evidence right now.';
  return (
    <>
            <div style={{ textAlign: 'center', marginBottom: '8px' }}>
              <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--text-main)', margin: '0 0 6px 0' }}>
                Design your user interviews
              </h1>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', margin: 0 }}>
                Enter your product idea. BebshaX will refine your research objective, look for supporting
                market evidence, and build personas — labelling which parts that evidence actually backs.
              </p>
            </div>

            {/* Evidence attempt status — says what was looked for and what came back,
                so step 2's per-persona labels are never a surprise. */}
            <div
              role="status"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexWrap: 'wrap',
                gap: '8px',
                background: 'var(--fill-soft)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '10px',
                padding: '8px 14px',
                fontSize: '0.82rem',
                color: 'var(--text-secondary)',
              }}
            >
              {busy ? (
                <Loader2 size={14} className="animate-spin" color="var(--accent-cyan)" />
              ) : (
                <FlaskConical size={14} color="var(--accent-cyan)" />
              )}
              <span>{evidenceLine}</span>
              {evidenceProbe.state === 'not_run' && onRunEvidence && (
                <button
                  type="button"
                  onClick={onRunEvidence}
                  className="bx-btn bx-btn--tinted bx-btn--sm"
                >
                  <FlaskConical size={13} aria-hidden="true" />
                  Run evidence research
                </button>
              )}
              {onNavigateToEvidence && !busy && (
                <button
                  type="button"
                  onClick={onNavigateToEvidence}
                  className="bx-btn bx-btn--ghost bx-btn--sm"
                >
                  Open Evidence Laboratory
                  <ArrowRight size={13} aria-hidden="true" />
                </button>
              )}
            </div>

            {/* Chat Transcript Area */}
            <div
              ref={copilotChatRef}
              style={{
                background: 'var(--glass-soft)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '22px',
                padding: 'clamp(14px, 3vw, 24px)',
                minHeight: copilotMessages.length === 0 ? '220px' : '300px',
                maxHeight: 'min(480px, 55dvh)',
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
                gap: '14px',
                boxShadow: 'inset 0 1px 0 var(--reflect)',
              }}
            >
              {copilotMessages.length === 0 && (
                <div style={{ textAlign: 'center', color: 'var(--text-secondary)', margin: 'auto', padding: '32px 0' }}>
                  <Sparkles size={28} className="text-teal-400 mx-auto mb-2" />
                  <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-main)' }}>
                    What business idea or product concept would you like to validate?
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    Type your idea below to start conversational context refinement.
                  </div>
                </div>
              )}

              {copilotMessages.map((msg) => (
                <div
                  key={msg.id}
                  className="bx-pop"
                  style={{
                    alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: 'min(85%, 640px)',
                    background: msg.role === 'user' ? 'var(--accent-gradient)' : 'var(--bg-card-hover)',
                    color: 'var(--text-main)',
                    padding: '12px 16px',
                    borderRadius: msg.role === 'user' ? '18px 18px 6px 18px' : '18px 18px 18px 6px',
                    border: msg.role === 'user' ? 'none' : '1px solid var(--border-subtle)',
                  }}
                >
                  <div style={{ fontSize: '0.9rem', lineHeight: 1.5 }}>{msg.content}</div>

                  {msg.role === 'assistant' && msg.isTemplate && (
                    <div
                      role="note"
                      title={msg.fallbackReason ? `Backend reason: ${msg.fallbackReason}` : undefined}
                      style={{
                        marginTop: '10px',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        background: 'rgba(245, 158, 11, 0.12)',
                        border: '1px solid rgba(245, 158, 11, 0.4)',
                        borderRadius: '6px',
                        padding: '3px 8px',
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        color: '#F59E0B',
                        letterSpacing: '0.03em',
                      }}
                    >
                      <AlertTriangle size={12} aria-hidden="true" />
                      Template reply — AI providers unavailable
                      {msg.fallbackReason && (
                        <span style={{ fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono, monospace)' }}>
                          ({msg.fallbackReason})
                        </span>
                      )}
                    </div>
                  )}

                  {msg.isRetryPrompt && msg.requestId && (
                    <div style={{ marginTop: '8px' }}>
                      <RequestIdTag requestId={msg.requestId} />
                    </div>
                  )}

                  {msg.isRetryPrompt && msg.retryContent && (
                    <button
                      type="button"
                      onClick={() => handleRetryCopilotMessage(msg.id)}
                      className="bx-btn bx-btn--tinted bx-btn--sm"
                      style={{ marginTop: '10px' }}
                    >
                      Retry
                    </button>
                  )}

                  {msg.isGoalCard && msg.goalCardData && (
                    <div
                      style={{
                        marginTop: '14px',
                        background: 'var(--bg-secondary)',
                        border: '1px solid var(--border-hover)',
                        borderRadius: '12px',
                        padding: '16px',
                      }}
                    >
                      <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--accent-cyan)', letterSpacing: '0.06em' }}>
                        {msg.goalCardData.title}
                      </div>
                      <div style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-main)', marginTop: '4px' }}>
                        {msg.goalCardData.summary}
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(180px, 100%), 1fr))', gap: '8px', marginTop: '12px', fontSize: '0.78rem' }}>
                        <div>
                          <span style={{ color: 'var(--text-secondary)' }}>Target Audience: </span>
                          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{msg.goalCardData.target_audience}</span>
                        </div>
                        <div>
                          <span style={{ color: 'var(--text-secondary)' }}>Hypothesis: </span>
                          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{msg.goalCardData.core_hypothesis}</span>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleApproveGoal(msg.goalCardData?.summary)}
                        disabled={isReadOnly || !!msg.isTemplate}
                        aria-disabled={isReadOnly || !!msg.isTemplate}
                        title={isReadOnly ? READ_ONLY_TITLE : msg.isTemplate ? TEMPLATE_APPROVAL_BLOCKED : undefined}
                        className={`bx-btn bx-btn--block ${showRoleSelection ? 'bx-btn--tinted' : 'bx-btn--primary'}`}
                        style={{ marginTop: '14px' }}
                      >
                        <CheckCircle2 size={16} aria-hidden="true" />
                        {showRoleSelection ? 'Goal Approved — View Suggested Roles ↓' : 'Approve Goal & Discover Personas'}
                      </button>
                      {msg.isTemplate && (
                        <p style={{ margin: '8px 0 0', fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                          {TEMPLATE_APPROVAL_BLOCKED}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {isCopilotTyping && (
                <div style={{ alignSelf: 'flex-start', color: 'var(--text-secondary)', fontSize: '0.82rem', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Sparkles size={14} className="text-teal-400 animate-spin" />
                    Synthesizing market context &amp; assumptions...
                  </div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', paddingLeft: '20px' }}>
                    Free providers may take up to 1–2 minutes
                  </span>
                </div>
              )}
            </div>

            {/* Input Bar */}
            <PromptInputBox
              textareaRef={step1InputRef}
              value={step1Prompt}
              onValueChange={setStep1Prompt}
              onSend={(text) => handleSendCopilotMessage(text)}
              isLoading={isCopilotTyping}
              disabled={isReadOnly}
              disabledReason={isReadOnly ? READ_ONLY_TITLE : undefined}
              maxHeight={160}
              placeholder={
                isReadOnly
                  ? 'Example study — read-only. Create your own study to chat with the copilot.'
                  : 'Type here to answer or give more context...'
              }
              aria-label="Describe your idea or answer the copilot"
              sendLabel="Send prompt"
              className="bx-prompt-wrap--full"
            />

            {/* Role Selection Drawer when ready */}
            {showRoleSelection && (
              <div ref={roleSelectionRef} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '16px', padding: '24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
                  <div>
                    <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--text-main)', margin: 0 }}>
                      Suggested roles for your study
                    </h2>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px', flexWrap: 'wrap' }}>
                      <span style={{ fontSize: '0.8rem', color: 'var(--accent-teal)', fontWeight: 600 }}>Panel not created yet</span>
                      <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>• Pick the roles you want, then generate the personas</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={handleGeneratePersonas}
                    disabled={isGeneratingPersonas || !suggestedRoles.some((r) => r.selected && r.count > 0) || isReadOnly}
                    title={
                      isReadOnly
                        ? READ_ONLY_TITLE
                        : !suggestedRoles.some((r) => r.selected && r.count > 0)
                        ? 'Pick at least one role first'
                        : undefined
                    }
                    style={{
                      background: 'var(--accent-gradient)',
                      border: 'none',
                      borderRadius: '8px',
                      padding: '10px 20px',
                      color: 'var(--text-on-accent)',
                      fontWeight: 700,
                      fontSize: '0.88rem',
                      cursor: isGeneratingPersonas || isReadOnly ? 'not-allowed' : 'pointer',
                      opacity: isReadOnly ? 0.55 : 1,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      boxShadow: '0 4px 14px var(--accent-glow)',
                    }}
                  >
                    <Sparkles size={16} />
                    {isGeneratingPersonas ? 'Generating Personas...' : 'Generate Personas'}
                  </button>
                </div>

                {/* Stacked Roles List */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {isLoadingRoles && suggestedRoles.length === 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)', fontSize: '0.85rem', padding: '14px 4px' }}>
                      <Sparkles size={14} className="text-teal-400 animate-spin" />
                      Discovering suggested roles for your study...
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                        Free providers may take up to 1–2 minutes
                      </span>
                    </div>
                  )}
                  {roleError && !isLoadingRoles && (
                    <div
                      role="alert"
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '12px',
                        background: 'rgba(239, 68, 68, 0.08)',
                        border: '1px solid rgba(239, 68, 68, 0.4)',
                        borderRadius: '10px',
                        padding: '12px 16px',
                        color: 'var(--status-error-text)',
                        fontSize: '0.85rem',
                      }}
                    >
                      <span>{roleError}</span>
                      <button
                        type="button"
                        onClick={handleRetrySuggestedRoles}
                        style={{
                          background: 'transparent',
                          border: '1px solid currentColor',
                          borderRadius: '6px',
                          padding: '4px 12px',
                          color: 'inherit',
                          cursor: 'pointer',
                          fontWeight: 600,
                          fontSize: '0.82rem',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        Retry
                      </button>
                    </div>
                  )}
                  {suggestedRoles.map((role, roleIdx) => {
                    const isSelected = !!role.selected && role.count > 0;
                    const atCap = role.count >= MAX_PERSONAS_PER_ROLE;
                    return (
                      <div
                        key={role.id}
                        onClick={() => handleToggleRole(role.id)}
                        className="bx-stagger"
                        style={{
                          ['--bx-i' as string]: Math.min(roleIdx, 12),
                          background: isSelected ? 'var(--accent-subtle)' : 'var(--bg-secondary)',
                          border: isSelected ? '1px solid var(--accent-teal)' : '1px solid var(--border-subtle)',
                          borderRadius: '12px',
                          padding: '14px 18px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '16px',
                          transition: 'all 0.2s ease',
                          boxShadow: isSelected ? '0 4px 16px -4px var(--accent-subtle)' : 'none',
                        }}
                      >
                        {/* Left Info: Checkbox + Role Name + Description */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flex: 1, minWidth: 0 }}>
                          <div
                            style={{
                              width: '22px',
                              height: '22px',
                              borderRadius: '6px',
                              border: isSelected ? '1px solid var(--accent-teal)' : '1px solid var(--border-medium)',
                              background: isSelected ? '#14B8A6' : 'var(--bg-card-hover)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              flexShrink: 0,
                              transition: 'all 0.2s ease',
                            }}
                          >
                            {isSelected && <Check size={14} color="var(--bg-pure)" strokeWidth={3} />}
                          </div>

                          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', minWidth: 0 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                              <span
                                style={{
                                  fontSize: '0.86rem',
                                  fontWeight: 700,
                                  letterSpacing: '0.04em',
                                  color: isSelected ? 'var(--accent-cyan)' : 'var(--text-main)',
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
                                    background: 'var(--accent-subtle)',
                                    color: 'var(--accent-teal-bright)',
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
                                color: 'var(--text-secondary)',
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
                            background: 'var(--bg-card-hover)',
                            border: '1px solid var(--border-medium)',
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
                              background: role.count > 0 ? 'var(--border-subtle)' : 'transparent',
                              border: 'none',
                              color: role.count > 0 ? 'var(--text-main)' : 'var(--text-faint)',
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
                              color: role.count > 0 ? 'var(--accent-cyan)' : 'var(--text-muted)',
                            }}
                          >
                            {role.count}
                          </span>

                          <button
                            type="button"
                            aria-label={`Increase ${role.role} count`}
                            onClick={(e) => handleIncrementRole(role.id, e)}
                            disabled={atCap}
                            aria-disabled={atCap ? true : undefined}
                            title={atCap ? `Up to ${MAX_PERSONAS_PER_ROLE} personas per role` : undefined}
                            style={{
                              background: atCap ? 'transparent' : 'var(--border-subtle)',
                              border: 'none',
                              color: atCap ? 'var(--text-faint)' : 'var(--text-main)',
                              borderRadius: '6px',
                              width: '26px',
                              height: '26px',
                              cursor: atCap ? 'not-allowed' : 'pointer',
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
    </>
  );
};
