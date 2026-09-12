import { describe, expect, it } from 'vitest';
import { reportMarkdown, serializeCsv } from '../src/utils/exports';

describe('Frontend faithful exports', () => {
  it('escapes quotes, commas and multiline values and preserves zero and negative numbers', () => {
    expect(serializeCsv([['A "quoted", name', 'line 1\nline 2', 0, -12, null]]))
      .toBe('"A ""quoted"", name","line 1\nline 2","0","-12",""');
  });
  it.each(['=SUM(1,2)', '+cmd', '-42', '@value', '\t=1', '\r=1', ' \u0000=1', '\ufeff=1'])(
    'neutralizes formula-like text %j without removing its content', (value) => {
      expect(serializeCsv([[value]])).toBe(`"'${value}"`);
    },
  );
  it('includes limitations, citations, route provenance and every stored report field', () => {
    const report = {
      id: 'report-fixture', version: 7, study_id: 'study-fixture', title: 'Full report', executive_summary: 'Line one\nLine two',
      key_findings: ['Synthetic finding'], recommendations: ['Interview real participants'], limitations: 'Synthetic only\nNo measured demand',
      evidence_findings: [{ title: 'Source', claim: 'Claim', confidence: 0.3, source: 'source-fixture' }],
      metrics: { served_by: 'freellmpool/fixture', llm_request_id: 'request-fixture', source_identity: 'source-persona-fixture' },
      future_metadata: { field: 'Never discard unknown canonical fields' },
    };
    const markdown = reportMarkdown(report);
    expect(markdown).toContain('SYNTHETIC RESEARCH REHEARSAL');
    expect(markdown).toContain('Version: 7');
    expect(markdown).toContain('## Limitations\nSynthetic only\nNo measured demand');
    expect(markdown).toContain('source-fixture');
    expect(markdown).toContain('request-fixture');
    expect(markdown).toContain('source-persona-fixture');
    expect(markdown).toContain(JSON.stringify(report, null, 2));
  });
});