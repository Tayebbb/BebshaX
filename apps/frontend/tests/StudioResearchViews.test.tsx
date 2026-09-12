import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { EvidenceLaboratoryView } from '../src/components/dashboard/views/EvidenceLaboratoryView';
import { api } from '../src/services/api';
import type { ClaimDetail, EvidenceClaim, EvidenceSource, EvidenceSummary, ResearchRun } from '../src/types';

const evidenceSummary: EvidenceSummary = {
  study_id: 'study-evidence', research_status: 'completed', evidence_coverage: 50,
  supported_pct: 50, inferred_pct: 25, unsupported_pct: 25,
  supported_count: 2, inferred_count: 1, unsupported_count: 1,
  total_claims: 4, total_sources: 1,
};

const evidenceSource: EvidenceSource = {
  id: 'source-sample', study_id: 'study-evidence',
  source_type: 'curated_sample' as EvidenceSource['source_type'],
  title: 'Illustrative source', publisher: 'Sample corpus',
  content: 'Illustrative synthetic sample, not live customer evidence.',
  url: 'https://example.test/sample', relevance_score: 0.8, status: 'collected',
};

const makeEvidenceClaim = (id: string, status: EvidenceClaim['status']): EvidenceClaim => ({
  id, study_id: 'study-evidence', claim_text: `${id} research claim`, status,
  category: 'problem', confidence: 0.7,
  supporting_source_ids: status === 'supported' ? [evidenceSource.id] : [],
  supporting_chunk_ids: [], contradicting_source_ids: [],
  rationale: 'Synthetic sample citation; not validated demand.',
});

const evidenceClaims = [
  makeEvidenceClaim('supported-first', 'supported'),
  makeEvidenceClaim('supported-second', 'supported'),
  makeEvidenceClaim('inferred', 'inference'),
  makeEvidenceClaim('unsupported', 'unsupported'),
];

const evidenceDetail = (claim: EvidenceClaim): ClaimDetail => ({
  ...claim, supporting_sources: [evidenceSource], supporting_chunks: [], contradicting_sources: [],
});

const evidenceRun: ResearchRun = {
  id: 'research-sample', study_id: 'study-evidence', status: 'completed',
  query_count: 2, source_count: 1, claim_count: 4, queries: ['Sample research'],
  started_at: '2026-09-10T10:00:00Z', created_at: '2026-09-10T10:00:00Z',
  completed_at: '2026-09-10T10:01:00Z',
};

const evidenceRequest = <Value,>() => {
  let resolve!: (value: Value) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<Value>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
};

const expectEvidenceSizing = (root: HTMLElement) => {
  for (const element of root.querySelectorAll<HTMLElement>('[style]')) {
    const { fontSize, letterSpacing, borderRadius } = element.style;
    if (fontSize.endsWith('rem')) expect(Number.parseFloat(fontSize)).toBeGreaterThanOrEqual(0.75);
    expect(fontSize).not.toMatch(/vw/);
    if (letterSpacing) expect(Number.parseFloat(letterSpacing)).toBeGreaterThanOrEqual(0);
    if (borderRadius.endsWith('px')) {
      expect(Number.parseFloat(borderRadius)).toBeLessThanOrEqual(element.getAttribute('role') === 'dialog' ? 12 : 8);
    }
  }
};

describe('Evidence laboratory presentation', () => {
  beforeEach(() => {
    vi.spyOn(api, 'getEvidenceSummary').mockResolvedValue(evidenceSummary);
    vi.spyOn(api, 'getEvidenceClaims').mockResolvedValue(evidenceClaims);
    vi.spyOn(api, 'getEvidenceSources').mockResolvedValue([evidenceSource]);
    vi.spyOn(api, 'getResearchRuns').mockResolvedValue([evidenceRun]);
    vi.spyOn(api, 'startResearch').mockResolvedValue(evidenceRun);
    vi.spyOn(api, 'getEvidenceClaimDetail').mockImplementation(async (_studyId, claimId): Promise<ClaimDetail> => {
      const claim = evidenceClaims.find((candidate) => candidate.id === claimId);
      if (!claim) throw new Error('Claim unavailable');
      return evidenceDetail(claim);
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('presents four named summary figures and keeps unavailable values unknown', async () => {
    vi.mocked(api.getEvidenceSummary).mockRejectedValue(new Error('Summary unavailable'));
    render(<EvidenceLaboratoryView studyId="study-evidence" />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Summary unavailable');
    const summary = screen.getByLabelText('Evidence summary');
    expect(summary.tagName).toBe('DL');
    expect(summary).toHaveClass('grid-cols-1', 'sm:grid-cols-2', 'xl:grid-cols-4');
    expect(within(summary).getAllByRole('term').map((term) => term.textContent)).toEqual([
      'Evidence Coverage',
      'Supported Evidence',
      'Model Inferences',
      'Unsupported',
    ]);
    const figures = within(summary).getAllByRole('definition');
    expect(figures).toHaveLength(4);
    for (const figure of figures) {
      expect(figure).toHaveTextContent('Unknown');
      expect(figure).not.toHaveTextContent('0%');
    }
  });

  it('retains reported summary percentages, counts, and claim-strength descriptions', async () => {
    render(<EvidenceLaboratoryView studyId="study-evidence" />);
    await screen.findByRole('tab', { name: 'Key Claims (4)' });

    const summary = screen.getByLabelText('Evidence summary');
    const figures = within(summary).getAllByRole('definition');
    expect(figures.map((figure) => figure.textContent)).toEqual([
      '50%2 supported claims', '50%(2 claims)', '25%(1 claims)', '25%(1 claims)',
    ]);
    expect(summary).toHaveTextContent('Claims citing retrieved chunks from collected sources');
    expect(summary).toHaveTextContent('Plausible extrapolation needing interview probe');
    expect(summary).toHaveTextContent('Ungrounded assumptions or contradicted points');
  });

  it('keeps a measured zero distinct from unavailable coverage', async () => {
    vi.mocked(api.getEvidenceSummary).mockResolvedValue({ ...evidenceSummary, evidence_coverage: 0 });
    render(<EvidenceLaboratoryView studyId="study-evidence" />);
    await screen.findByRole('tab', { name: 'Key Claims (4)' });

    const coverage = within(screen.getByLabelText('Evidence summary')).getAllByRole('definition')[0];
    expect(coverage).toHaveTextContent('0%');
    expect(coverage).not.toHaveTextContent('Unknown');
  });

  it('separates the kicker from a wrapping title and allows header actions to wrap', async () => {
    render(<EvidenceLaboratoryView studyId="study-evidence" />);
    await screen.findByRole('tab', { name: 'Key Claims (4)' });

    const header = screen.getByRole('banner');
    expect(header).toHaveStyle({ flexWrap: 'wrap' });
    expect(within(header).getByText('Evidence Laboratory').tagName).toBe('P');
    expect(within(header).getByRole('heading', { level: 1 })).toHaveStyle({ overflowWrap: 'anywhere' });
    expect(header).toHaveTextContent('sample sources are labeled');
  });

  it('uses compact shared actions and announces the guarded research request as busy', async () => {
    const research = evidenceRequest<ResearchRun>();
    vi.mocked(api.startResearch).mockReturnValue(research.promise);
    const onBack = vi.fn();
    render(<EvidenceLaboratoryView studyId="study-evidence" onBack={onBack} />);
    await screen.findByRole('tab', { name: 'Key Claims (4)' });

    const back = screen.getByRole('button', { name: 'Back' });
    expect(back).toHaveClass('bx-btn', 'bx-btn--sm');
    fireEvent.click(back);
    expect(onBack).toHaveBeenCalledOnce();

    const runResearch = screen.getByRole('button', { name: 'Run Research' });
    expect(runResearch).toHaveClass('bx-btn', 'bx-btn--sm', 'bx-btn--secondary');
    fireEvent.click(runResearch);
    fireEvent.click(runResearch);
    expect(runResearch).toBeDisabled();
    expect(runResearch).toHaveAttribute('aria-busy', 'true');
    expect(api.startResearch).toHaveBeenCalledTimes(1);
    expectEvidenceSizing(screen.getByRole('banner').parentElement!);

    await act(async () => research.resolve(evidenceRun));
    await waitFor(() => expect(runResearch).toBeEnabled());
  });

  it('preserves arrow, Home, and End navigation with linked panels and one tab stop', async () => {
    render(<EvidenceLaboratoryView studyId="study-evidence" />);
    const claimsTab = await screen.findByRole('tab', { name: 'Key Claims (4)' });
    claimsTab.focus();

    const keysAndTabs = [
      ['ArrowRight', 'Sources & Chunks (1)'], ['End', 'Research History (1)'],
      ['ArrowRight', 'Key Claims (4)'], ['ArrowLeft', 'Research History (1)'],
      ['Home', 'Key Claims (4)'],
    ];
    for (const [key, name] of keysAndTabs) {
      fireEvent.keyDown(document.activeElement!, { key });
      const selected = screen.getByRole('tab', { name });
      expect(selected).toHaveFocus();
      expect(selected).toHaveAttribute('aria-selected', 'true');
      expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', selected.id);
      expect(screen.getAllByRole('tab').filter((tab) => tab.tabIndex === 0)).toEqual([selected]);
    }
  });

  it('announces the selected status filter without changing evidence classifications', async () => {
    render(<EvidenceLaboratoryView studyId="study-evidence" />);
    await screen.findByRole('tab', { name: 'Key Claims (4)' });
    expect(screen.getByText('Model Inference')).toBeInTheDocument();
    expect(screen.getAllByText('Evidence-supported')).toHaveLength(2);
    expect(screen.getByText('Unsupported Assumption')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Unsupported (Red)' }));
    expect(screen.getByRole('button', { name: 'Unsupported (Red)' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText(evidenceClaims[3].claim_text)).toBeInTheDocument();
    expect(screen.queryByText(evidenceClaims[0].claim_text)).not.toBeInTheDocument();
    expect(screen.queryByText(evidenceClaims[2].claim_text)).not.toBeInTheDocument();
  });

  it('retains runtime sample labeling and reports the selected source filter', async () => {
    render(<EvidenceLaboratoryView studyId="study-evidence" />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Sources & Chunks (1)' }));

    expect(screen.getByText('SAMPLE')).toBeInTheDocument();
    expect(screen.getByText(evidenceSource.content)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open/ })).toHaveAttribute('href', evidenceSource.url);
    expect(screen.getByRole('button', { name: 'All Sources' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.change(screen.getByRole('textbox', { name: 'Search claims and evidence' }), { target: { value: 'not in corpus' } });
    expect(screen.queryByText(evidenceSource.title)).not.toBeInTheDocument();
  });

  it.each(['Key Claims (4)', 'Sources & Chunks (1)', 'Research History (1)'])(
    'keeps inline text and surfaces within the requested size limits in %s', async (tabName) => {
      const { container } = render(<EvidenceLaboratoryView studyId="study-evidence" />);
      fireEvent.click(await screen.findByRole('tab', { name: tabName }));
      expectEvidenceSizing(container);
    },
  );

  it('preserves provenance content and dialog keyboard dismissal with shared close actions', async () => {
    const { container } = render(<EvidenceLaboratoryView studyId="study-evidence" />);
    const inspect = (await screen.findAllByRole('button', { name: 'Inspect Provenance' }))[0];
    inspect.focus();
    fireEvent.click(inspect);

    const dialog = await screen.findByRole('dialog', { name: evidenceClaims[0].claim_text });
    expect(within(dialog).getByText(evidenceClaims[0].rationale!)).toBeInTheDocument();
    expect(dialog).toHaveTextContent(evidenceSource.content);
    expect(within(dialog).getByRole('button', { name: 'Close claim provenance' })).toHaveClass('bx-btn');
    expect(within(dialog).getByRole('button', { name: 'Close Inspection' })).toHaveClass('bx-btn');
    expectEvidenceSizing(container);

    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(inspect).toHaveFocus();
  });

  it('renders complete labeled supporting and contradicting evidence including private excerpts', async () => {
    const privateSource = {
      ...evidenceSource, id: 'private-source', title: 'Private study notes', url: '',
      content: `Private source opening.\n${'Complete private evidence. '.repeat(40)}Private source ending.`,
    };
    const contradiction = {
      ...evidenceSource, id: 'contradiction', title: 'Contradicting report',
      content: `Contradicting opening.\n${'Counter-evidence. '.repeat(40)}Contradicting ending.`,
    };
    const chunks = [
      { id: 'private-chunk', source_id: privateSource.id, chunk_index: 0, content: `Excerpt opening.\n${'Full excerpt. '.repeat(80)}Excerpt ending.` },
      { id: 'second-chunk', source_id: privateSource.id, chunk_index: 1, content: 'Another complete private excerpt.' },
    ];
    vi.mocked(api.getEvidenceClaimDetail).mockResolvedValueOnce({
      ...evidenceDetail(evidenceClaims[0]),
      supporting_sources: [evidenceSource, privateSource],
      contradicting_sources: [contradiction], supporting_chunks: chunks,
    });
    render(<EvidenceLaboratoryView studyId="study-evidence" />);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Inspect Provenance' }))[0]);
    const dialog = await screen.findByRole('dialog');
    const supporting = within(dialog).getByRole('list', { name: 'Supporting sources' });
    const contradicting = within(dialog).getByRole('list', { name: 'Contradicting sources' });
    const excerpts = within(dialog).getByRole('list', { name: 'Supporting excerpts' });

    expect(within(supporting).getAllByRole('listitem')).toHaveLength(2);
    expect(within(supporting).getAllByRole('link')).toHaveLength(1);
    expect(supporting.textContent).toContain(privateSource.title);
    expect(supporting.textContent).toContain(privateSource.content);
    expect(contradicting.textContent).toContain(contradiction.title);
    expect(contradicting.textContent).toContain(contradiction.content);
    expect(within(excerpts).getAllByRole('listitem')).toHaveLength(2);
    for (const chunk of chunks) {
      expect(excerpts.textContent).toContain(chunk.content);
      expect(excerpts.textContent).toContain(chunk.id);
      expect(excerpts.textContent).toContain(chunk.source_id);
    }
    for (const quote of dialog.querySelectorAll('blockquote')) expect(quote).toHaveStyle({ whiteSpace: 'pre-wrap' });
    expect(dialog).not.toHaveTextContent('unverified model assumption');
    expectEvidenceSizing(dialog);
  });

  it.each(['empty', 'chunks only', 'contradictions only'] as const)(
    'reports empty evidence collections truthfully when detail is %s', async (collection) => {
      vi.mocked(api.getEvidenceClaimDetail).mockResolvedValueOnce({
        ...evidenceDetail(evidenceClaims[0]), supporting_sources: [],
        supporting_chunks: collection === 'chunks only'
          ? [{ id: 'private-excerpt', source_id: 'private-source', chunk_index: 0, content: 'A private supporting excerpt.' }] : [],
        contradicting_sources: collection === 'contradictions only' ? [evidenceSource] : [],
      });
      render(<EvidenceLaboratoryView studyId="study-evidence" />);
      fireEvent.click((await screen.findAllByRole('button', { name: 'Inspect Provenance' }))[0]);
      const dialog = await screen.findByRole('dialog');

      expect(dialog).toHaveTextContent('No supporting sources attached to this claim.');
      expect(dialog).not.toHaveTextContent('unverified model assumption');
      if (collection === 'chunks only') expect(within(dialog).getByRole('list', { name: 'Supporting excerpts' })).toHaveTextContent('A private supporting excerpt.');
      else expect(dialog).toHaveTextContent('No supporting excerpts attached to this claim.');
      if (collection === 'contradictions only') expect(within(dialog).getByRole('list', { name: 'Contradicting sources' })).toHaveTextContent(evidenceSource.content);
      else expect(dialog).toHaveTextContent('No contradicting sources attached to this claim.');
      expect(within(dialog).getByText('Evidence-supported')).toBeInTheDocument();
    },
  );

  it.each(['javascript:alert(1)', 'data:text/html,private', '//external.example/path'])(
    'preserves evidence text without exposing an unsafe source link %s', async (url) => {
      const source = { ...evidenceSource, url, content: 'Evidence remains readable without a safe external link.' };
      vi.mocked(api.getEvidenceClaimDetail).mockResolvedValueOnce({
        ...evidenceDetail(evidenceClaims[0]), supporting_sources: [source], contradicting_sources: [source],
      });
      render(<EvidenceLaboratoryView studyId="study-evidence" />);
      fireEvent.click((await screen.findAllByRole('button', { name: 'Inspect Provenance' }))[0]);
      const dialog = await screen.findByRole('dialog');

      expect(within(dialog).queryByRole('link')).not.toBeInTheDocument();
      expect(within(dialog).getAllByText(source.content)).toHaveLength(2);
    },
  );

  it('does not reveal private evidence when the claim read is denied', async () => {
    vi.mocked(api.getEvidenceClaimDetail).mockRejectedValueOnce(new Error('403: Claim read permission denied'));
    render(<EvidenceLaboratoryView studyId="study-evidence" />);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Inspect Provenance' }))[0]);

    expect(await screen.findByRole('alert')).toHaveTextContent('Claim read permission denied');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByText(evidenceSource.content)).not.toBeInTheDocument();
    expect(api.getEvidenceClaimDetail).toHaveBeenCalledOnce();
    expect(api.getEvidenceClaimDetail).toHaveBeenCalledWith('study-evidence', evidenceClaims[0].id, expect.any(AbortSignal));
  });

  it('keeps source repository evidence readable when its URL is unsafe', async () => {
    vi.mocked(api.getEvidenceSources).mockResolvedValueOnce([{ ...evidenceSource, url: 'data:text/html,private' }]);
    render(<EvidenceLaboratoryView studyId="study-evidence" />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Sources & Chunks (1)' }));

    expect(screen.getByText(evidenceSource.content)).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('uses the black page canvas token while preserving neutral evidence surfaces', async () => {
    render(<EvidenceLaboratoryView studyId="study-evidence" />);
    await screen.findByRole('tab', { name: 'Key Claims (4)' });
    expect(screen.getByRole('banner').parentElement).toHaveStyle({ background: 'var(--bg-pure)' });
  });

  it.each([
    { failure: new Error('Detail lookup failed'), message: 'Detail lookup failed', kind: 'an Error' },
    { failure: null, message: 'The request did not complete.', kind: 'a non-Error rejection' },
  ])('announces $kind and retries provenance for the same claim', async ({ failure, message }) => {
    vi.mocked(api.getEvidenceClaimDetail).mockRejectedValueOnce(failure);
    const { container } = render(<EvidenceLaboratoryView studyId="study-evidence" />);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Inspect Provenance' }))[0]);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(`Claim provenance could not be loaded: ${message}`);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expectEvidenceSizing(container);
    fireEvent.click(within(alert).getByRole('button', { name: 'Retry inspection' }));
    expect(alert).not.toBeInTheDocument();

    expect(await screen.findByRole('dialog', { name: evidenceClaims[0].claim_text })).toBeInTheDocument();
    expect(api.getEvidenceClaimDetail).toHaveBeenCalledTimes(2);
    expect(vi.mocked(api.getEvidenceClaimDetail).mock.calls.map(([studyId, claimId]) => [studyId, claimId])).toEqual([
      ['study-evidence', evidenceClaims[0].id], ['study-evidence', evidenceClaims[0].id],
    ]);
  });

  it.each(['Escape', 'Close claim provenance', 'Close Inspection', 'backdrop'])(
    'returns focus to the original claim trigger after a deferred retry succeeds and %s closes', async (dismissal) => {
      const retry = evidenceRequest<ClaimDetail>();
      vi.mocked(api.getEvidenceClaimDetail)
        .mockRejectedValueOnce(new Error('Detail lookup failed'))
        .mockReturnValueOnce(retry.promise);
      render(<EvidenceLaboratoryView studyId="study-evidence" />);
      const inspect = (await screen.findAllByRole('button', { name: 'Inspect Provenance' }))[1];
      inspect.focus();
      fireEvent.click(inspect);

      const alert = await screen.findByRole('alert');
      expect(alert).toHaveTextContent('Claim provenance could not be loaded: Detail lookup failed');
      const retryButton = within(alert).getByRole('button', { name: 'Retry inspection' });
      retryButton.focus();
      expect(retryButton).toHaveFocus();
      fireEvent.click(retryButton);
      expect(retryButton).not.toBeInTheDocument();
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

      await act(async () => retry.resolve(evidenceDetail(evidenceClaims[1])));
      const dialog = await screen.findByRole('dialog', { name: evidenceClaims[1].claim_text });
      await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
      if (dismissal === 'Escape') fireEvent.keyDown(document, { key: 'Escape' });
      else if (dismissal === 'backdrop') fireEvent.click(dialog.parentElement!);
      else fireEvent.click(within(dialog).getByRole('button', { name: dismissal }));
      await waitFor(() => expect(dialog).not.toBeInTheDocument());
      expect(inspect).toHaveFocus();
      expect(vi.mocked(api.getEvidenceClaimDetail).mock.calls.map(([, claimId]) => claimId)).toEqual([
        evidenceClaims[1].id, evidenceClaims[1].id,
      ]);
    },
  );

  it('ignores an older inspection failure after a newer claim opens', async () => {
    const stale = evidenceRequest<ClaimDetail>();
    vi.mocked(api.getEvidenceClaimDetail).mockReturnValueOnce(stale.promise);
    render(<EvidenceLaboratoryView studyId="study-evidence" />);
    const inspectButtons = await screen.findAllByRole('button', { name: 'Inspect Provenance' });
    fireEvent.click(inspectButtons[0]);
    fireEvent.click(inspectButtons[1]);
    const currentDialog = await screen.findByRole('dialog', { name: evidenceClaims[1].claim_text });

    await act(async () => stale.reject(new Error('Old detail failure')));
    expect(currentDialog).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it.each(['success', 'failure'] as const)(
    'does not let an older inspection %s replace the latest failure', async (outcome) => {
      const stale = evidenceRequest<ClaimDetail>();
      vi.mocked(api.getEvidenceClaimDetail)
        .mockReturnValueOnce(stale.promise)
        .mockRejectedValueOnce(new Error('Current detail failure'));
      render(<EvidenceLaboratoryView studyId="study-evidence" />);
      const inspectButtons = await screen.findAllByRole('button', { name: 'Inspect Provenance' });
      fireEvent.click(inspectButtons[0]);
      fireEvent.click(inspectButtons[1]);
      expect(await screen.findByRole('alert')).toHaveTextContent('Current detail failure');

      await act(async () => {
        if (outcome === 'success') stale.resolve(evidenceDetail(evidenceClaims[0]));
        else stale.reject(new Error('Old detail failure'));
      });
      expect(screen.getByRole('alert')).toHaveTextContent('Current detail failure');
      expect(screen.queryByText(/Old detail failure/)).not.toBeInTheDocument();
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    },
  );

  it.each(['success', 'failure'] as const)(
    'ignores an inspection %s after its study scope is replaced', async (outcome) => {
      const stale = evidenceRequest<ClaimDetail>();
      vi.mocked(api.getEvidenceClaimDetail).mockReturnValueOnce(stale.promise);
      const { rerender } = render(<EvidenceLaboratoryView studyId="study-evidence" />);
      fireEvent.click((await screen.findAllByRole('button', { name: 'Inspect Provenance' }))[0]);
      const signal = vi.mocked(api.getEvidenceClaimDetail).mock.calls[0][2];

      rerender(<EvidenceLaboratoryView studyId="study-next" />);
      await screen.findByRole('tab', { name: 'Key Claims (4)' });
      expect(signal?.aborted).toBe(true);
      await act(async () => {
        if (outcome === 'success') stale.resolve(evidenceDetail(evidenceClaims[0]));
        else stale.reject(new Error('Previous study failure'));
      });
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    },
  );

  it('clears a visible inspection error when the study changes', async () => {
    vi.mocked(api.getEvidenceClaimDetail).mockRejectedValueOnce(new Error('Previous study failure'));
    const { rerender } = render(<EvidenceLaboratoryView studyId="study-evidence" />);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Inspect Provenance' }))[0]);
    expect(await screen.findByRole('alert')).toHaveTextContent('Previous study failure');

    rerender(<EvidenceLaboratoryView studyId="study-next" />);
    await screen.findByRole('tab', { name: 'Key Claims (4)' });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});