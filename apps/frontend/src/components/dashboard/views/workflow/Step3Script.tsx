import React from 'react';
import { AlertTriangle, ArrowRight, Trash2 } from 'lucide-react';
import { api } from '../../../../services/api';
import { Button } from '../../../ui/Button';
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
                  minWidth: 0,
                  maxWidth: '100%',
                  boxSizing: 'border-box',
                  background: 'var(--status-warn-bg)',
                  border: '1px solid var(--status-warn-border)',
                  borderRadius: '10px',
                  padding: '10px 14px',
                  color: 'var(--status-warn-text)',
                  fontSize: '0.84rem',
                  fontWeight: 600,
                }}
              >
                <AlertTriangle size={15} aria-hidden="true" style={{ flexShrink: 0 }} />
                <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
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
                  flexWrap: 'wrap',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '12px',
                  minWidth: 0,
                  maxWidth: '100%',
                  boxSizing: 'border-box',
                  background: 'var(--status-error-bg)',
                  border: '1px solid var(--status-error-border)',
                  borderRadius: '10px',
                  padding: '12px 16px',
                  color: 'var(--status-error-text)',
                  fontSize: '0.86rem',
                }}
              >
                <span style={{ flex: '1 1 240px', minWidth: 0, overflowWrap: 'anywhere' }}>
                  Question generation failed: {scriptError}
                </span>
                <Button
                  type="button"
                  variant="ghost"
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
                    minHeight: 44,
                    maxWidth: '100%',
                    flexShrink: 0,
                  }}
                >
                  Retry
                </Button>
              </div>
            )}
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '16px', minWidth: 0, maxWidth: '100%' }}>
              <div style={{ flex: '1 1 320px', minWidth: 0, maxWidth: '100%' }}>
                <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--text-main)', margin: '0 0 4px 0' }}>
                  Interview Script & Probing Rules
                </h1>
                <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', margin: 0 }}>
                  {scriptGenerated
                    ? 'Customize the core questions the AI interviewer will ask across your personas.'
                    : questions.length > 0
                    ? 'Your own questions — edit them, or generate a script from your study context.'
                    : 'No script yet. Generate one from your study context, or add your own questions below.'}
                </p>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', minWidth: 0, maxWidth: '100%' }}>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleGenerateScript}
                  disabled={isGeneratingScript || isReadOnly}
                  loading={isGeneratingScript}
                  title={isReadOnly ? READ_ONLY_TITLE : undefined}
                  style={{
                    padding: '8px 16px',
                    fontSize: '0.84rem',
                    gap: '6px',
                    minHeight: 44,
                    maxWidth: '100%',
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}
                >
                  {isGeneratingScript
                    ? 'Generating...'
                    : scriptGenerated
                    ? 'Regenerate Questions'
                    : 'Generate Questions'}
                </Button>
                <Button
                  type="button"
                  variant="primary"
                  aria-label="Approve Script & Start Interviews"
                  onClick={() => handleStepChange(4)}
                  trailingIcon={<ArrowRight size={15} aria-hidden="true" />}
                  style={{
                    padding: '8px 20px',
                    fontSize: '0.84rem',
                    fontWeight: 700,
                    gap: '6px',
                    minHeight: 44,
                    maxWidth: '100%',
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}
                >
                  Start interviews
                </Button>
              </div>
            </div>

            {isGeneratingScript && (
              <div
                role="status"
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  alignItems: 'center',
                  gap: '10px',
                  minWidth: 0,
                  maxWidth: '100%',
                  boxSizing: 'border-box',
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
              {questions.length === 0 && !isGeneratingScript && (
                <div
                  data-testid="script-empty-state"
                  style={{
                    fontSize: '0.84rem',
                    color: 'var(--text-secondary)',
                    background: 'var(--fill-soft)',
                    border: '1px dashed var(--border-subtle)',
                    borderRadius: '10px',
                    padding: '16px 18px',
                    textAlign: 'center',
                  }}
                >
                  No interview questions yet. BebshaX does not ship a generic questionnaire — press
                  &quot;Generate Questions&quot; to write a script from your study context, or add your own below.
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
                    minWidth: 0,
                    maxWidth: '100%',
                    boxSizing: 'border-box',
                  }}
                >
                  <span style={{ color: 'var(--accent-teal)', fontWeight: 700, fontSize: '0.88rem', flexShrink: 0 }}>
                    Q{idx + 1}
                  </span>
                  <input
                    type="text"
                    aria-label={`Question ${idx + 1}`}
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
                      minWidth: 0,
                      maxWidth: '100%',
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
                  <Button
                    type="button"
                    variant="ghost"
                    icon
                    aria-label={`Delete question ${idx + 1}`}
                    onClick={() => {
                      const nextQ = questions.filter((_, i) => i !== idx);
                      setQuestions(nextQ);
                      if (studyId) api.updateStudy(studyId, { script_questions: nextQ }).catch(() => {});
                    }}
                    disabled={isReadOnly}
                    title={isReadOnly ? READ_ONLY_TITLE : `Delete question ${idx + 1}`}
                    style={{ color: 'var(--text-faint)', minWidth: 44, minHeight: 44, flexShrink: 0 }}
                  >
                    <Trash2 size={15} aria-hidden="true" />
                  </Button>
                </div>
              ))}
            </div>

            {/* Add Question input */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', minWidth: 0, maxWidth: '100%' }}>
              <input
                type="text"
                aria-label="New interview question"
                value={newQuestion}
                onChange={(e) => setNewQuestion(e.target.value)}
                placeholder="Add another interview question..."
                disabled={isReadOnly}
                title={isReadOnly ? READ_ONLY_TITLE : undefined}
                style={{
                  flex: '1 1 240px',
                  minWidth: 0,
                  maxWidth: '100%',
                  minHeight: 44,
                  boxSizing: 'border-box',
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
              <Button
                type="button"
                variant="secondary"
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
                  minHeight: 44,
                  maxWidth: '100%',
                  flexShrink: 0,
                  padding: '0 20px',
                  fontWeight: 600,
                  fontSize: '0.88rem',
                  cursor: isReadOnly ? 'not-allowed' : 'pointer',
                  opacity: isReadOnly ? 0.55 : 1,
                }}
              >
                Add Question
              </Button>
            </div>
    </>
  );
};
