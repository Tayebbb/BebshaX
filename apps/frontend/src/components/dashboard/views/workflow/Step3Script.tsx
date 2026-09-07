import React from 'react';
import { AlertTriangle, ArrowRight, Trash2 } from 'lucide-react';
import { api } from '../../../../services/api';
import { READ_ONLY_TITLE } from './types';

/** Step 3 — interview script & questions. Pure JSX extraction from
 * StudyWorkflowView: all state stays in the parent; inline persistence
 * closures travel with the JSX they belong to. */
interface Step3ScriptProps {
  studyId?: string;
  questions: string[];
  setQuestions: React.Dispatch<React.SetStateAction<string[]>>;
  newQuestion: string;
  setNewQuestion: React.Dispatch<React.SetStateAction<string>>;
  handleGenerateScript: () => Promise<void>;
  isGeneratingScript: boolean;
  scriptError: string | null;
  /** False until the generator has actually returned questions for this study. */
  scriptGenerated?: boolean;
  /** Set after a generation attempt: 'fallback_static' means the backend served
   * canned starter questions because no LLM answered. */
  scriptSource?: 'llm' | 'fallback_static' | null;
  handleStepChange: (newStep: number, opts?: { reportReady?: boolean }) => void;
  /** Example (demo) studies are viewable but never mutable from here. */
  isReadOnly?: boolean;
}

export const Step3Script: React.FC<Step3ScriptProps> = ({
  studyId,
  questions,
  setQuestions,
  newQuestion,
  setNewQuestion,
  handleGenerateScript,
  isGeneratingScript,
  scriptError,
  scriptGenerated = false,
  scriptSource = null,
  handleStepChange,
  isReadOnly = false,
}) => {
  return (
    <>
            {scriptSource === 'fallback_static' && (
              <div
                role="status"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  background: 'rgba(245, 158, 11, 0.1)',
                  border: '1px solid rgba(245, 158, 11, 0.4)',
                  borderRadius: '10px',
                  padding: '10px 14px',
                  color: '#F59E0B',
                  fontSize: '0.84rem',
                  fontWeight: 600,
                }}
              >
                <AlertTriangle size={15} aria-hidden="true" />
                <span>
                  Starter script (not AI-generated for this study) — the AI providers did not answer, so
                  these are generic questions. Edit them or regenerate later.
                </span>
              </div>
            )}
            {scriptError && (
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
                  fontSize: '0.86rem',
                }}
              >
                <span>Question generation failed: {scriptError}</span>
                <button
                  type="button"
                  onClick={handleGenerateScript}
                  disabled={isGeneratingScript || isReadOnly}
                  title={isReadOnly ? READ_ONLY_TITLE : undefined}
                  style={{
                    background: 'transparent',
                    border: '1px solid currentColor',
                    borderRadius: '6px',
                    padding: '4px 12px',
                    color: 'inherit',
                    cursor: isGeneratingScript || isReadOnly ? 'not-allowed' : 'pointer',
                    fontWeight: 600,
                    fontSize: '0.82rem',
                    whiteSpace: 'nowrap',
                  }}
                >
                  Retry
                </button>
              </div>
            )}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--text-main)', margin: '0 0 4px 0' }}>
                  Interview Script & Probing Rules
                </h1>
                <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', margin: 0 }}>
                  {scriptGenerated
                    ? 'Customize the core questions the AI interviewer will ask across your personas.'
                    : 'These are generic starter questions, not generated for your study — edit them, or generate a script from your study context.'}
                </p>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={handleGenerateScript}
                  disabled={isGeneratingScript || isReadOnly}
                  title={isReadOnly ? READ_ONLY_TITLE : undefined}
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--accent-cyan)',
                    borderRadius: '8px',
                    padding: '8px 16px',
                    fontSize: '0.84rem',
                    fontWeight: 600,
                    cursor: isGeneratingScript || isReadOnly ? 'not-allowed' : 'pointer',
                    opacity: isGeneratingScript || isReadOnly ? 0.6 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  {isGeneratingScript && (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ animation: 'authSpin 0.7s linear infinite' }} aria-hidden="true">
                      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                    </svg>
                  )}
                  {isGeneratingScript
                    ? 'Generating...'
                    : scriptGenerated
                    ? 'Regenerate Questions'
                    : 'Generate Questions'}
                </button>
                <button
                  type="button"
                  onClick={() => handleStepChange(4)}
                  style={{
                    background: 'var(--accent-gradient)',
                    border: 'none',
                    color: 'var(--text-on-accent)',
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

            {isGeneratingScript && (
              <div
                role="status"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  background: 'var(--accent-subtle)',
                  border: '1px solid var(--accent-glow)',
                  borderRadius: '12px',
                  padding: '12px 16px',
                  color: 'var(--accent-teal-bright)',
                  fontSize: '0.86rem',
                  fontWeight: 600,
                }}
              >
                Writing interview questions from your study context…
                <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: '0.78rem' }}>
                  Free providers may take up to 1–2 minutes
                </span>
              </div>
            )}

            {/* Question List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {!scriptGenerated && questions.length > 0 && (
                <div
                  style={{
                    fontSize: '0.8rem',
                    color: 'var(--text-secondary)',
                    background: 'var(--fill-soft)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '10px',
                    padding: '10px 14px',
                  }}
                >
                  Starting template — the same generic questions for every study. Edit them or press
                  &quot;Generate Questions&quot; to write a script from your study context.
                </div>
              )}
              {questions.map((q, idx) => (
                <div
                  key={idx}
                  className="bx-stagger"
                  style={{
                    ['--bx-i' as string]: Math.min(idx, 12),
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '12px',
                    padding: '16px 20px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '14px',
                  }}
                >
                  <span style={{ color: 'var(--accent-teal)', fontWeight: 700, fontSize: '0.88rem' }}>
                    Q{idx + 1}
                  </span>
                  <input
                    type="text"
                    value={q}
                    disabled={isReadOnly}
                    title={isReadOnly ? READ_ONLY_TITLE : undefined}
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
                      color: 'var(--text-main)',
                      fontSize: '0.9rem',
                      outline: 'none',
                      opacity: isReadOnly ? 0.75 : 1,
                    }}
                    onFocus={(e) => { (e.currentTarget as HTMLInputElement).style.boxShadow = '0 0 0 2px var(--accent-teal)'; }}
                    onBlur={(e) => { (e.currentTarget as HTMLInputElement).style.boxShadow = 'none'; }}
                  />
                  <button
                    type="button"
                    onClick={() => {
                      const nextQ = questions.filter((_, i) => i !== idx);
                      setQuestions(nextQ);
                      if (studyId) api.updateStudy(studyId, { script_questions: nextQ }).catch(() => {});
                    }}
                    disabled={isReadOnly}
                    title={isReadOnly ? READ_ONLY_TITLE : undefined}
                    style={{ background: 'transparent', border: 'none', color: 'var(--text-faint)', cursor: isReadOnly ? 'not-allowed' : 'pointer', opacity: isReadOnly ? 0.5 : 1 }}
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
                disabled={isReadOnly}
                title={isReadOnly ? READ_ONLY_TITLE : undefined}
                style={{
                  flex: 1,
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '10px',
                  padding: '12px 16px',
                  color: 'var(--text-main)',
                  fontSize: '0.88rem',
                  outline: 'none',
                  opacity: isReadOnly ? 0.6 : 1,
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
                disabled={isReadOnly}
                title={isReadOnly ? READ_ONLY_TITLE : undefined}
                style={{
                  background: 'var(--accent-subtle)',
                  border: '1px solid var(--border-hover)',
                  color: 'var(--accent-cyan)',
                  borderRadius: '10px',
                  padding: '0 20px',
                  fontWeight: 600,
                  fontSize: '0.88rem',
                  cursor: isReadOnly ? 'not-allowed' : 'pointer',
                  opacity: isReadOnly ? 0.55 : 1,
                }}
              >
                Add Question
              </button>
            </div>
    </>
  );
};
