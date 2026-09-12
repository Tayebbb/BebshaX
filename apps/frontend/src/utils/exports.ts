import type { StudyReport } from '../types/study';

export function serializeCsv(rows: readonly (readonly unknown[])[]): string {
  return rows.map((row) => row.map((value) => {
    const text = value === null || value === undefined ? '' : String(value);
    const inert = typeof value === 'string' && (/^[\s\u0000-\u001f\u007f-\u009f\ufeff]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) ? `'${text}` : text;
    return `"${inert.replace(/"/g, '""')}"`;
  }).join(',')).join('\r\n');
}

export function downloadText(content: string, filename: string, type: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_');
  anchor.click();
  URL.revokeObjectURL(url);
}

const sectionNames: Partial<Record<keyof StudyReport, string>> = {
  executive_summary: 'Executive Summary', key_findings: 'Key Findings', recommendations: 'Recommendations',
  target_market_summary: 'Target Market', market_context_summary: 'Market Context', evidence_findings: 'Evidence Findings',
  dataset_findings: 'Dataset Findings', market_segments_summary: 'Market Segments', persona_overview: 'Persona Overview',
  interview_findings: 'Interview Findings', major_pain_points: 'Pain Points', customer_needs: 'Customer Needs',
  behavioral_results: 'Behavioral Results', pricing_signals: 'Pricing Signals', major_risks: 'Risks', opportunities: 'Opportunities',
  strongest_segments: 'Strongest Segments', validation_summary: 'Validation Summary', limitations: 'Limitations',
  quote_highlights: 'Quotes', metrics: 'Metrics And Provenance',
};

function jsonBlock(value: unknown): string {
  const json = JSON.stringify(value, null, 2);
  const longestFence = Math.max(2, ...Array.from(json.matchAll(/`+/g), (match) => match[0].length));
  const fence = '`'.repeat(longestFence + 1);
  return `${fence}json\n${json}\n${fence}`;
}

export function reportMarkdown(report: StudyReport): string {
  const sections = [
    `# ${report.title || 'Research Report'}`,
    'SYNTHETIC RESEARCH REHEARSAL. These results are not observed customers, representative demand, or purchase probabilities.',
    `Report: ${report.id ?? 'unavailable'}\nStudy: ${report.study_id ?? 'unavailable'}\nVersion: ${report.version ?? 'unknown'}\nCreated: ${report.created_at ?? 'unknown'}`,
  ];
  for (const [key, title] of Object.entries(sectionNames)) {
    const value = report[key as keyof StudyReport];
    if (value === undefined || value === null) continue;
    const content = typeof value === 'string' ? value
      : Array.isArray(value) && value.every((item) => typeof item === 'string') ? value.map((item) => `- ${item}`).join('\n')
      : jsonBlock(value);
    sections.push(`## ${title}\n${content}`);
  }
  if (!report.limitations) sections.push('## Limitations\nNo limitations were recorded for this version. This absence is not evidence of validity.');
  sections.push(`## Full Stored Report\n${jsonBlock(report)}`);
  return sections.join('\n\n') + '\n';
}