import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { StudyWorkflowView } from '../src/components/dashboard/views/StudyWorkflowView';
import { api } from '../src/services/api';
import { EvidenceSummary } from '../src/types';

/** Proves the workflow actually wires the probe decision into step 1 — the pure
 * mapping is covered in JudgeRound4.test.tsx. */
describe('Step 1 evidence probe wiring', () => {
  beforeEach(async () => {
    api.setMockMode(true);
    await api.resetMockStore();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderWorkflow = () =>
    render(
      <StudyWorkflowView
        studyId="tj6FY3cXDO8oxpuxeAMb"
        initialStep={1}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />,
    );

  const evidenceSummary = (overrides: Partial<EvidenceSummary>): EvidenceSummary =>
    ({
      study_id: 'tj6FY3cXDO8oxpuxeAMb',
      research_status: 'idle',
      evidence_coverage: 0,
      supported_pct: 0,
      inferred_pct: 0,
      unsupported_pct: 0,
      supported_count: 0,
      inferred_count: 0,
      unsupported_count: 0,
      total_claims: 0,
      total_sources: 0,
      latest_run: null,
      ...overrides,
    } as EvidenceSummary);

  it('surfaces a failed research run as a failure, not as "no evidence found"', async () => {
    vi.spyOn(api, 'getEvidenceSummary').mockResolvedValue(
      evidenceSummary({
        research_status: 'failed',
        latest_run: { status: 'failed', error_message: 'provider quota exhausted' } as any,
      }),
    );

    renderWorkflow();

    await waitFor(() =>
      expect(screen.getByText(/evidence research run failed/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/No evidence found/i)).toBeNull();
  });

  it('says it is looking while a real in-flight backend status is reported', async () => {
    vi.spyOn(api, 'getEvidenceSummary').mockResolvedValue(
      evidenceSummary({
        research_status: 'searching_evidence',
        latest_run: { status: 'searching_evidence' } as any,
      }),
    );

    renderWorkflow();

    await waitFor(() =>
      expect(screen.getByText(/Looking for supporting evidence/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/No evidence found/i)).toBeNull();
  });
});
