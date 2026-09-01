import React from 'react';
import { Copy, Download, FileText } from 'lucide-react';
import { Persona, Study, StudyReport } from '../../../../types';
import { ProvenanceChip } from '../PersonaLibraryView';
import { countEvidenceBacked } from '../../../../utils/personaEvidence';

/** Step 5 — final decision report. Pure JSX extraction from StudyWorkflowView;
 * `verificationAssumptions` is derived in the parent from persona provenance. */
interface Step5ReportProps {
  study: Study | null;
  personas: Persona[];
  report: StudyReport | null;
  availableReports: StudyReport[];
  reportError: string | null;
  isGeneratingReport: boolean;
  copiedToast: boolean;
  copyReportMarkdown: () => void;
  exportReportMarkdown: () => void;
  handleGenerateFinalReport: () => Promise<void>;
  verificationAssumptions: { value: string; provenance: string; personaName: string }[];
}

export const Step5Report: React.FC<Step5ReportProps> = ({
  study,
  personas,
  report,
  availableReports,
  reportError,
  isGeneratingReport,
  copiedToast,
  copyReportMarkdown,
  exportReportMarkdown,
  handleGenerateFinalReport,
  verificationAssumptions,
}) => {
  const evidenceBackedCount = countEvidenceBacked(personas);
  const claimCount = report?.metrics?.total_claims ?? report?.evidence_findings?.length ?? 0;
  return (
    <>
            {reportError && (
              <div
                role="alert"
                style={{
                  background: 'rgba(239, 68, 68, 0.08)',
                  border: '1px solid rgba(239, 68, 68, 0.4)',
                  color: 'var(--status-error-text)',
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
                    color: report ? 'var(--accent-emerald)' : 'var(--status-error-text)',
                    border: report ? '1px solid rgba(16, 185, 129, 0.25)' : '1px solid rgba(239, 68, 68, 0.25)',
                  }}
                >
                  {report
                    ? `Decision Report Ready • Version ${report.version || 1} ${availableReports.length > 1 ? `(${availableReports.length} versions)` : ''}`
                    : 'No report generated yet'}
                </span>
                <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--text-main)', margin: '8px 0 4px 0' }}>
                  {report?.title || study?.title || 'Market Research & Validation Report'}
                </h1>
                <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', margin: 0 }}>
                  {report
                    ? `Synthesized from ${personas.length} synthetic personas${claimCount > 0 ? ' and empirical research claims' : ''}.`
                    : `Will be synthesized from your study data — ${personas.length} synthetic personas and any research claims you have collected.`}
                </p>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={copyReportMarkdown}
                  disabled={!report}
                  title={report ? undefined : 'No report to copy yet — generate the report first'}
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-main)',
                    borderRadius: '8px',
                    padding: '8px 14px',
                    fontSize: '0.82rem',
                    fontWeight: 600,
                    cursor: report ? 'pointer' : 'not-allowed',
                    opacity: report ? 1 : 0.55,
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
                  disabled={!report}
                  title={report ? undefined : 'No report to export yet — generate the report first'}
                  style={{
                    background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                    border: 'none',
                    color: 'var(--text-on-accent)',
                    borderRadius: '8px',
                    padding: '8px 16px',
                    fontSize: '0.82rem',
                    fontWeight: 700,
                    cursor: report ? 'pointer' : 'not-allowed',
                    opacity: report ? 1 : 0.55,
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
              <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '14px', padding: '18px 20px' }}>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Demand Signal</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--accent-emerald)', marginTop: '4px' }}>
                  {report?.metrics?.demand_score != null ? `${report.metrics.demand_score}%` : '—'}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                  Model-estimated from the synthetic transcripts — not a measurement
                </div>
              </div>
              <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '14px', padding: '18px 20px' }}>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Personas</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--accent-cyan)', marginTop: '4px' }}>
                  {personas.length}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                  {evidenceBackedCount} of {personas.length} evidence-backed
                </div>
              </div>
              <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '14px', padding: '18px 20px' }}>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Confidence Score</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--accent-teal)', marginTop: '4px' }}>
                  {report?.metrics?.confidence_score != null
                    ? `${Math.round(report.metrics.confidence_score * 100)}%`
                    : '—'}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                  The model&apos;s own confidence in this synthesis — not a measurement
                </div>
              </div>
            </div>

            {isGeneratingReport && !report ? (
              /* Synthesis can take minutes on free routes — show the wait here
                 instead of on a disabled button back in step 4. */
              <div
                role="status"
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '16px',
                  padding: '24px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '14px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--accent-teal-bright)', fontWeight: 600, fontSize: '0.92rem' }}>
                  <FileText size={16} />
                  Synthesizing your decision report…
                  <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: '0.78rem' }}>
                    Free providers may take up to 1–2 minutes
                  </span>
                </div>
                <div className="bx-skeleton" style={{ height: '14px', width: '90%' }} />
                <div className="bx-skeleton" style={{ height: '14px', width: '78%' }} />
                <div className="bx-skeleton" style={{ height: '14px', width: '84%' }} />
                <div className="bx-skeleton" style={{ height: '14px', width: '60%' }} />
              </div>
            ) : report ? (
              <>
                {/* Executive Summary */}
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '16px', padding: '24px' }}>
                  <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--accent-cyan)', margin: '0 0 12px 0' }}>
                    Executive Summary
                  </h2>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-primary)', lineHeight: 1.6, margin: 0, whiteSpace: 'pre-line' }}>
                    {report.executive_summary}
                  </p>
                </div>

                {/* Key Findings */}
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '16px', padding: '24px' }}>
                  <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)', margin: '0 0 14px 0' }}>
                    Key Findings
                  </h2>
                  <ul style={{ margin: 0, paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {(report.key_findings || []).map((kf, i) => (
                      <li key={i} style={{ fontSize: '0.88rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                        {kf}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Recommendations */}
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '16px', padding: '24px' }}>
                  <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--accent-emerald)', margin: '0 0 14px 0' }}>
                    Strategic Recommendations
                  </h2>
                  <ul style={{ margin: 0, paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {(report.recommendations || []).map((rec, i) => (
                      <li key={i} style={{ fontSize: '0.88rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                        {rec}
                      </li>
                    ))}
                  </ul>
                </div>
              </>
            ) : (
              /* Honest empty state — placeholder findings must never render. */
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '12px',
                  textAlign: 'center',
                  padding: '64px 24px',
                  border: '1px dashed var(--border-subtle)',
                  borderRadius: '16px',
                  color: 'var(--text-secondary)',
                }}
              >
                <FileText size={28} className="text-teal-400" />
                <div style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)' }}>No report yet</div>
                <div style={{ fontSize: '0.85rem', maxWidth: '440px' }}>
                  Generate it from your study data — your personas, interviews, and collected research claims feed the synthesis.
                </div>
                <button
                  type="button"
                  onClick={handleGenerateFinalReport}
                  disabled={isGeneratingReport}
                  style={{
                    marginTop: '6px',
                    background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                    border: 'none',
                    borderRadius: '8px',
                    padding: '10px 20px',
                    color: 'var(--text-on-accent)',
                    fontWeight: 700,
                    fontSize: '0.85rem',
                    cursor: isGeneratingReport ? 'not-allowed' : 'pointer',
                    opacity: isGeneratingReport ? 0.6 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <FileText size={15} />
                  {isGeneratingReport ? 'Synthesizing Report...' : 'Generate Decision Report'}
                </button>
              </div>
            )}

            {/* Active honesty safeguard — synthetic findings hand off to real customers */}
            <div
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--accent-glow)',
                borderRadius: '16px',
                padding: '24px',
                boxShadow: 'var(--shadow-glow)',
              }}
            >
              <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--accent-teal-bright)', margin: '0 0 8px 0' }}>
                Validate with real customers next
              </h2>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-primary)', lineHeight: 1.6, margin: 0 }}>
                Synthetic research de-risks your questions — it never replaces real customers.
              </p>
              {verificationAssumptions.length > 0 && (
                <div style={{ marginTop: '16px' }}>
                  <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                    Assumptions to verify in real interviews
                  </div>
                  <ul style={{ margin: 0, paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {verificationAssumptions.map((a, i) => (
                      <li key={i} style={{ fontSize: '0.85rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                        {a.value}
                        <ProvenanceChip label={a.provenance} />
                        <span style={{ color: 'var(--text-secondary)', fontSize: '0.78rem' }}> — {a.personaName}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Methodology & Limitations Disclaimer */}
            <div style={{ background: 'var(--accent-subtle)', border: '1px solid var(--accent-glow)', borderRadius: '12px', padding: '16px 20px', fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              <strong style={{ color: 'var(--accent-cyan)' }}>Research Methodology Note:</strong> This report combines collected research material (clearly labeled by source, including curated samples) with exploratory synthetic persona simulations. Synthetic findings are research signals and hypotheses — validate consequential decisions with real users.
            </div>
    </>
  );
};
