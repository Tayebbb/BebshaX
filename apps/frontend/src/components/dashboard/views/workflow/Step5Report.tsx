import React from 'react';
import { Copy, Download, FileText, RefreshCw } from 'lucide-react';
import { Persona, Study, StudyReport } from '../../../../types';
import { Button } from '../../../ui';
import { ProvenanceChip } from '../PersonaLibraryView';
import { countEvidenceBacked } from '../../../../utils/personaEvidence';
import { READ_ONLY_TITLE } from './types';
import { AiReviewCard } from './AiReviewCard';

export function formatScorePercent(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 100) {
    return '\u2014';
  }
  return `${Math.round(value <= 1 ? value * 100 : value)}%`;
}

const RECORD_SECTIONS: Array<[keyof StudyReport, string]> = [
  ['key_findings', 'Key findings'], ['evidence_findings', 'Evidence findings'], ['dataset_findings', 'Dataset findings'],
  ['market_segments_summary', 'Market segments'], ['persona_overview', 'Persona overview'], ['interview_findings', 'Interview findings'],
  ['major_pain_points', 'Pain points'], ['customer_needs', 'Customer needs'], ['behavioral_results', 'Behavioral results'],
  ['pricing_signals', 'Pricing signals'], ['major_risks', 'Risks'], ['opportunities', 'Opportunities'],
  ['strongest_segments', 'Strongest segments'], ['recommendations', 'Recommendations'],
];

/** Human-readable record of what the report contains and where it came from.
 * Replaces a raw JSON dump that exposed internal ids and read as noise. */
const ReportRecord: React.FC<{ report: StudyReport }> = ({ report }) => {
  const metrics = report.metrics ?? {};
  const grounding = (metrics.grounding ?? {}) as { sources_present?: string[]; removed_sections?: Record<string, unknown>; scores_nulled?: string[] };
  const manifest = (metrics.input_manifest ?? {}) as { interviews?: unknown[]; turns?: unknown[]; evidence_claims?: unknown[]; evidence_sources?: unknown[]; datasets?: unknown[]; segments?: unknown[]; behavioral_result_ids?: unknown[]; personas?: unknown[]; captured_at?: string };
  const count = (value: unknown) => (Array.isArray(value) ? value.length : 0);
  const removed = Object.keys(grounding.removed_sections ?? {});
  const rows: Array<[string, string]> = [
    ['Version', String(report.version ?? 1)],
    ['Written by', metrics.served_by ? String(metrics.served_by) : 'model route not recorded'],
    ['Inputs captured', manifest.captured_at ? new Date(manifest.captured_at).toLocaleString() : 'not recorded'],
    ['Panel size', String(count(manifest.personas) || metrics.total_personas || 0)],
    ['Interviews / turns', `${count(manifest.interviews) || metrics.total_interviews || 0} / ${count(manifest.turns)}`],
    ['Evidence sources / claims', `${count(manifest.evidence_sources)} / ${count(manifest.evidence_claims) || metrics.total_claims || 0}`],
    ['Datasets / segments', `${count(manifest.datasets)} / ${count(manifest.segments)}`],
    ['Behavioral results', String(count(manifest.behavioral_result_ids))],
  ];
  return (
    <div style={{ display: 'grid', gap: '14px', fontSize: '0.84rem', paddingTop: '10px' }}>
      <dl style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '6px 16px', margin: 0 }}>
        {rows.map(([label, value]) => (
          <React.Fragment key={label}>
            <dt style={{ color: 'var(--text-secondary)' }}>{label}</dt>
            <dd style={{ margin: 0, color: 'var(--text-main)', overflowWrap: 'anywhere' }}>{value}</dd>
          </React.Fragment>
        ))}
      </dl>
      <div>
        <div style={{ color: 'var(--text-secondary)', marginBottom: '6px' }}>Sections in this version</div>
        <ul style={{ margin: 0, paddingLeft: '18px', columns: 2, columnGap: '24px' }}>
          {RECORD_SECTIONS.map(([key, label]) => {
            const value = report[key];
            const n = Array.isArray(value) ? value.length : 0;
            return <li key={key} style={{ color: n ? 'var(--text-main)' : 'var(--text-muted)' }}>{label}: {n || 'none'}</li>;
          })}
        </ul>
      </div>
      {(removed.length > 0 || (grounding.scores_nulled?.length ?? 0) > 0) && (
        <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
          Grounding check: {removed.length > 0 && <>removed {removed.join(', ')} because the captured inputs had no matching records</>}
          {removed.length > 0 && (grounding.scores_nulled?.length ?? 0) > 0 && '; '}
          {(grounding.scores_nulled?.length ?? 0) > 0 && <>{grounding.scores_nulled!.join(' and ')} left unmeasured</>}.
        </p>
      )}
      {metrics.llm_request_id && <p style={{ margin: 0, color: 'var(--text-muted)' }}>Request {String(metrics.llm_request_id)}</p>}
    </div>
  );
};

/** Step 5 — final decision report. Pure JSX extraction from StudyWorkflowView;
 * `verificationAssumptions` is derived in the parent from persona provenance. */
interface Step5ReportProps {
  study: Study | null;
  personas: Persona[];
  report: StudyReport | null;
  availableReports: StudyReport[];
  reportError: string | null;
  reportErrorKind?: 'loading' | 'generation' | 'copy';
  onReloadReports?: () => Promise<void>;
  reportsLoading?: boolean;
  isGeneratingReport: boolean;
  copiedToast: boolean;
  copyReportMarkdown: () => void;
  exportReportMarkdown: () => void;
  onSelectReport?: (report: StudyReport) => void;
  handleGenerateFinalReport: () => Promise<void>;
  /** Interviews completed so far; more than the report used means it is out of date. */
  completedInterviewCount?: number;
  verificationAssumptions: { value: string; provenance: string; personaName: string }[];
  /** Example (demo) studies are viewable but never mutable from here. */
  isReadOnly?: boolean;
}

export const Step5Report: React.FC<Step5ReportProps> = ({
  study,
  personas,
  report,
  availableReports,
  reportError,
  reportErrorKind = 'generation',
  onReloadReports,
  reportsLoading = false,
  isGeneratingReport,
  copiedToast,
  copyReportMarkdown,
  exportReportMarkdown,
  onSelectReport,
  handleGenerateFinalReport,
  completedInterviewCount = 0,
  verificationAssumptions,
  isReadOnly = false,
}) => {
  const evidenceBackedCount = countEvidenceBacked(personas);
  const claimCount = report?.metrics?.total_claims ?? report?.evidence_findings?.length ?? 0;
  const reportInterviews = typeof report?.metrics?.total_interviews === 'number' ? report.metrics.total_interviews : null;
  const interviewsSinceReport = report && reportInterviews !== null ? Math.max(0, completedInterviewCount - reportInterviews) : 0;
  const canRegenerate = Boolean(report) && !isGeneratingReport && !isReadOnly && completedInterviewCount > 0;
  const reportRecovery = {
    loading: { title: 'Saved reports unavailable', label: 'Reload saved reports', action: onReloadReports },
    generation: { title: 'Report generation failed', label: 'Retry report generation', action: handleGenerateFinalReport },
    copy: { title: 'Report copy failed', label: 'Try copying again', action: copyReportMarkdown },
  }[reportErrorKind];
  return (
    <>
            {reportError && (
              <div
                role="alert"
                style={{
                  background: 'var(--status-error-bg)',
                  border: '1px solid var(--status-error-border)',
                  color: 'var(--status-error-text)',
                  borderRadius: '8px',
                  padding: '12px 16px',
                  fontSize: '0.88rem',
                }}
              >
                <p>{reportRecovery.title}: {reportError}</p>
                <p style={{ marginTop: '6px', color: 'var(--text-secondary)' }}>
                  {report ? 'Your saved report is unchanged.' : 'Your study data is unchanged.'}
                </p>
                {reportRecovery.action && (
                  <Button
                    variant="secondary"
                    onClick={reportRecovery.action}
                    disabled={isGeneratingReport || reportsLoading || (isReadOnly && reportErrorKind === 'generation')}
                    title={isReadOnly && reportErrorKind === 'generation' ? READ_ONLY_TITLE : undefined}
                    style={{ marginTop: '12px' }}
                  >
                    <RefreshCw size={15} aria-hidden="true" />
                    {reportRecovery.label}
                  </Button>
                )}
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
                    : reportsLoading ? 'Loading saved reports' : reportError ? 'Saved report status unavailable' : 'No report generated yet'}
                </span>
                <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--text-main)', margin: '8px 0 4px 0' }}>
                  {report?.title || study?.title || 'Market Research & Validation Report'}
                </h1>
                <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', margin: 0 }}>
                  {report
                    ? `Synthesized from ${personas.length} synthetic persona${personas.length === 1 ? '' : 's'}${
                        claimCount > 0
                          ? ` and ${claimCount} retrieved research claim${claimCount === 1 ? '' : 's'}`
                          : ''
                      }.`
                    : `Will be synthesized from your study data — ${personas.length} synthetic persona${personas.length === 1 ? '' : 's'} and any research claims you have collected.`}
                </p>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', minWidth: 0 }}>
                {availableReports.length > 1 && onSelectReport && (
                  <select aria-label="Saved report version" value={report?.id ?? ''} onChange={(event) => {
                    const selected = availableReports.find((candidate) => candidate.id === event.target.value);
                    if (selected) onSelectReport(selected);
                  }}>
                    {availableReports.map((saved, index) => <option key={saved.id ?? index} value={saved.id}>Version {saved.version ?? 'unknown'}</option>)}
                  </select>
                )}
                {report && (
                  <button
                    type="button"
                    onClick={handleGenerateFinalReport}
                    disabled={!canRegenerate}
                    title={isReadOnly ? READ_ONLY_TITLE : completedInterviewCount === 0 ? 'Complete at least one interview first' : `Write version ${(report.version || 1) + 1} from the current study data`}
                    style={{
                      background: 'var(--bg-card)',
                      border: '1px solid var(--accent-teal)',
                      color: 'var(--accent-cyan)',
                      borderRadius: '8px',
                      padding: '8px 14px',
                      fontSize: '0.82rem',
                      fontWeight: 600,
                      cursor: canRegenerate ? 'pointer' : 'not-allowed',
                      opacity: canRegenerate ? 1 : 0.55,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <RefreshCw size={14} className={isGeneratingReport ? 'animate-spin' : ''} aria-hidden="true" />
                    {isGeneratingReport ? 'Synthesizing…' : 'Regenerate report'}
                  </button>
                )}
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
                    background: 'var(--accent-gradient)',
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
            {report && isGeneratingReport && (
              <div role="status" style={{ display: 'flex', alignItems: 'center', gap: '10px', background: 'var(--status-info-bg)', border: '1px solid var(--border-subtle)', borderRadius: '10px', padding: '12px 16px', fontSize: '0.86rem', color: 'var(--text-main)' }}>
                <FileText size={16} aria-hidden="true" />
                <span>Synthesizing version {(report.version || 1) + 1}… Version {report.version || 1} below stays available until the new one is saved.</span>
              </div>
            )}
            {report && !isGeneratingReport && interviewsSinceReport > 0 && (
              <div role="status" style={{ display: 'flex', alignItems: 'center', gap: '10px', background: 'var(--fill-soft)', border: '1px solid var(--border-subtle)', borderRadius: '10px', padding: '12px 16px', fontSize: '0.86rem', color: 'var(--text-main)' }}>
                <RefreshCw size={15} aria-hidden="true" />
                <span>
                  {interviewsSinceReport} interview{interviewsSinceReport === 1 ? '' : 's'} completed since version {report.version || 1} was written — regenerate to include {interviewsSinceReport === 1 ? 'it' : 'them'}.
                </span>
              </div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))', gap: '16px' }}>
              <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '14px', padding: '18px 20px' }}>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Demand Signal</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--accent-emerald)', marginTop: '4px' }}>
                  {formatScorePercent(report?.metrics?.demand_score)}
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
                  {formatScorePercent(report?.metrics?.confidence_score)}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                  The model&apos;s own confidence in this synthesis — not a measurement
                </div>
              </div>
            </div>

            {(isGeneratingReport || reportsLoading) && !report ? (
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
                <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '10px', color: 'var(--accent-teal-bright)', fontWeight: 600, fontSize: '0.92rem' }}>
                  <FileText size={16} />
                  {reportsLoading ? 'Loading saved report versions...' : 'Synthesizing your decision report…'}
                  {!reportsLoading && (
                    <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: '0.78rem' }}>
                      You can leave this view and return while generation continues.
                    </span>
                  )}
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
                  <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)', margin: '0 0 14px 0' }}>
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
                <section aria-label="Report limitations">
                  <h2>Limitations</h2>
                  <p style={{ whiteSpace: 'pre-wrap' }}>{report.limitations || 'No limitations were recorded for this report version. Synthetic results are not observed customer evidence.'}</p>
                </section>
                <details>
                  <summary>Report record: sections, sources and provenance</summary>
                  <ReportRecord report={report} />
                </details>
              </>
            ) : reportError ? null : (
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
                  {completedInterviewCount > 0
                    ? 'Generate it from your study data — your personas, interviews, and collected research claims feed the synthesis.'
                    : 'The report is synthesized from what your personas said. Complete at least one interview in the Interviews step first.'}
                </div>
                <button
                  type="button"
                  onClick={handleGenerateFinalReport}
                  disabled={isGeneratingReport || isReadOnly || completedInterviewCount === 0}
                  title={isReadOnly ? READ_ONLY_TITLE : completedInterviewCount === 0 ? 'Complete at least one interview first' : undefined}
                  style={{
                    marginTop: '6px',
                    background: 'var(--accent-gradient)',
                    border: 'none',
                    borderRadius: '8px',
                    padding: '10px 20px',
                    color: 'var(--text-on-accent)',
                    fontWeight: 700,
                    fontSize: '0.85rem',
                    cursor: isGeneratingReport || isReadOnly || completedInterviewCount === 0 ? 'not-allowed' : 'pointer',
                    opacity: isGeneratingReport || isReadOnly || completedInterviewCount === 0 ? 0.6 : 1,
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

            {/* Independent AI review of the whole study */}
            <AiReviewCard studyId={study?.id} isReadOnly={isReadOnly} />

            {/* Methodology & Limitations Disclaimer */}
            <div style={{ background: 'var(--accent-subtle)', border: '1px solid var(--accent-glow)', borderRadius: '12px', padding: '16px 20px', fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              <strong style={{ color: 'var(--accent-cyan)' }}>Research Methodology Note:</strong> Every section above was written by a model from this study’s own inputs — live evidence (each source linked), imported datasets, and exploratory synthetic-persona interviews and simulations
              {report?.metrics?.served_by ? ` (report synthesised by ${String(report.metrics.served_by)})` : ''}. Synthetic findings are research signals and hypotheses — validate consequential decisions with real users.
            </div>
    </>
  );
};
