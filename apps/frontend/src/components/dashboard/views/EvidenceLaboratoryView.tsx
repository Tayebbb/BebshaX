import React, { useState, useEffect, useLayoutEffect, useMemo, useRef, useId } from 'react';
import {
  Search,
  Sparkles,
  Database,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ExternalLink,
  RefreshCw,
  ArrowLeft,
  ChevronRight,
  ShieldCheck,
  Clock,
  X,
} from 'lucide-react';
import {
  ClaimDetail,
  EvidenceClaim,
  EvidenceSource,
  EvidenceStatus,
  EvidenceSummary,
  ResearchRun,
  Study,
} from '../../../types';
import { api } from '../../../services/api';
import { pollSerial } from '../../../services/polling';
import { isResearchRunSettled, researchFailureText, researchProgressText } from '../../../utils/researchRun';
import { Button } from '../../ui';
import { useDialogA11y } from '../../../utils/useDialogA11y';
import { useRequestScope } from '../../../utils/useRequestScope';
import { useRouteReady } from '../../../performance/routeTiming';

interface EvidenceLaboratoryViewProps {
  studyId: string;
  study?: Study | null;
  onBack?: () => void;
}

type EvidenceTab = 'claims' | 'sources' | 'runs';
type EvidenceResource = EvidenceTab | 'summary';

const externalSourceUrl = (value?: string | null): string | undefined => {
  if (!value || /[\u0000-\u001f\u007f-\u009f]/.test(value)) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : undefined;
  } catch {
    return undefined;
  }
};

export const EvidenceLaboratoryView: React.FC<EvidenceLaboratoryViewProps> = ({
  studyId,
  study,
  onBack,
}) => {
  const [activeTab, setActiveTab] = useState<EvidenceTab>('claims');
  const tabsId = useId();
  const [summary, setSummary] = useState<EvidenceSummary | null>(null);
  const [claims, setClaims] = useState<EvidenceClaim[]>([]);
  const [sources, setSources] = useState<EvidenceSource[]>([]);
  const [runs, setRuns] = useState<ResearchRun[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [categoryFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sourceTypeFilter, setSourceTypeFilter] = useState<string>('all');
  const [selectedClaimDetail, setSelectedClaimDetail] = useState<ClaimDetail | null>(null);
  const [claimInspectionError, setClaimInspectionError] = useState<{ claimId: string; message: string } | null>(null);
  const claimDialogRef = useRef<HTMLDivElement | null>(null);
  const claimInspectionTriggerRef = useRef<HTMLButtonElement | null>(null);
  const closeClaimInspection = () => {
    setSelectedClaimDetail(null);
    if (claimInspectionTriggerRef.current?.isConnected) claimInspectionTriggerRef.current.focus();
  };
  useDialogA11y(claimDialogRef, !!selectedClaimDetail, closeClaimInspection, { returnFocus: false });
  const [pendingReads, setPendingReads] = useState<Record<EvidenceResource, boolean>>({ claims: true, sources: true, runs: true, summary: true });
  const [readErrors, setReadErrors] = useState<Partial<Record<EvidenceResource, string>>>({});
  const isLoading = pendingReads[activeTab];
  const [loadError, setLoadError] = useState<string | null>(null);
  const visibleError = loadError || readErrors[activeTab] || readErrors.summary;
  const activeRows = activeTab === 'claims' ? claims : activeTab === 'sources' ? sources : runs;
  useRouteReady(!isLoading, readErrors[activeTab] ? 'error' : activeRows.length ? 'content' : 'empty');
  const [isRunningResearch, setIsRunningResearch] = useState<boolean>(false);
  const [researchStatusText, setResearchStatusText] = useState<string>('');

  const scopeRef = useRequestScope([studyId]);
  const loadGenerationRef = useRef(0);
  const claimGenerationRef = useRef(0);
  const researchPendingRef = useRef(false);
  useLayoutEffect(() => {
    setSummary(null);
    setClaims([]);
    setSources([]);
    setRuns([]);
    setSelectedClaimDetail(null);
    claimInspectionTriggerRef.current = null;
    setClaimInspectionError(null);
    setLoadError(null);
    setReadErrors({});
    setPendingReads({ claims: true, sources: true, runs: true, summary: true });
    setResearchStatusText('');
    setIsRunningResearch(false);
    researchPendingRef.current = false;
  }, [studyId]);

  const loadAllData = async () => {
    const scope = scopeRef.current;
    const generation = ++loadGenerationRef.current;
    const isCurrent = () => scope.active && generation === loadGenerationRef.current;
    setPendingReads({ claims: true, sources: true, runs: true, summary: true });
    setReadErrors({});
    setLoadError(null);
    setSummary(null);
    const settle = async <Value,>(resource: EvidenceResource, read: Promise<Value>, commit: (value: Value) => void) => {
      try {
        const value = await read;
        if (isCurrent()) commit(value);
      } catch (error: unknown) {
        if (isCurrent()) setReadErrors((previous) => ({ ...previous, [resource]: error instanceof Error ? error.message : `${resource} unavailable` }));
      } finally {
        if (isCurrent()) setPendingReads((previous) => ({ ...previous, [resource]: false }));
      }
    };
    await Promise.all([
      settle('summary', api.getEvidenceSummary(studyId, scope.controller.signal), setSummary),
      settle('claims', api.getEvidenceClaims(studyId, undefined, scope.controller.signal), setClaims),
      settle('sources', api.getEvidenceSources(studyId, undefined, scope.controller.signal), setSources),
      settle('runs', api.getResearchRuns(studyId, scope.controller.signal), setRuns),
    ]);
  };

  const tabKeyboard = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const tabs: EvidenceTab[] = ['claims', 'sources', 'runs'];
    const current = tabs.indexOf(activeTab);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
      : event.key === 'ArrowRight' ? (current + 1) % tabs.length
      : event.key === 'ArrowLeft' ? (current + tabs.length - 1) % tabs.length : -1;
    if (next < 0) return;
    event.preventDefault();
    setActiveTab(tabs[next]);
    document.getElementById(`${tabsId}-${tabs[next]}`)?.focus();
  };

  useEffect(() => {
    loadAllData();
  }, [studyId]);

  // A run that was in flight when the page (re)loaded is followed exactly like
  // one started here (live 2026-09-14: after a reload the button re-enabled and
  // nothing showed the run executing, so users started more runs). A latest
  // run that failed is said on the page, not only in Research History.
  useEffect(() => {
    const latest = summary?.latest_run;
    if (!latest || researchPendingRef.current) return;
    if (!isResearchRunSettled(latest)) {
      void followRun(latest);
    } else if (latest.status === 'failed' && !researchStatusText && !loadError) {
      setLoadError(researchFailureText(latest));
    }
    // Only the summary's identity matters: following the same run twice is prevented by the ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summary?.latest_run?.id, summary?.latest_run?.status]);

  type FollowableRun = Pick<ResearchRun, 'id' | 'status' | 'current_step' | 'query_count' | 'source_count' | 'claim_count' | 'error_message'>;

  /** Poll `accepted` to a terminal state, then reload and report the outcome. */
  const followRun = async (accepted: FollowableRun) => {
    const scope = scopeRef.current;
    if (!scope.active || researchPendingRef.current) return;
    researchPendingRef.current = true;
    setIsRunningResearch(true);
    setLoadError(null);
    try {
      let run: FollowableRun = accepted;
      if (!isResearchRunSettled(run)) {
        setResearchStatusText(researchProgressText(run));
        run = await pollSerial(
          (signal) => api.getResearchRun(studyId, accepted.id, signal),
          {
            signal: scope.controller.signal,
            intervalMs: 2500,
            pauseWhenHidden: true,
            complete: (value) => isResearchRunSettled(value),
            progress: (value) => `${value.current_step}|${value.query_count}|${value.source_count}|${value.claim_count}`,
            onUpdate: (value) => { if (scope.active) setResearchStatusText(researchProgressText(value)); },
          },
        );
        if (!scope.active) return;
      }
      // Reload first: loadAllData resets the error banner, and the outcome must survive it.
      await loadAllData();
      if (!scope.active) return;
      if (run.status !== 'completed') {
        setResearchStatusText('');
        setLoadError(researchFailureText(run));
      } else {
        setResearchStatusText(
          run.claim_count
            ? `Research complete — ${run.claim_count} claims extracted from ${run.source_count} sources.`
            : 'Research complete — no live evidence was found for this idea, so no claims were added.',
        );
      }
    } catch (err: any) {
      if (!scope.active) return;
      setResearchStatusText('');
      const stillRunning = err?.jobContinues === true;
      if (stillRunning) await loadAllData();
      if (!scope.active) return;
      setLoadError(
        stillRunning
          ? `Stopped waiting for research updates: ${err?.message || 'the run may still be in progress.'} Check Research History for its final state.`
          : `Research run failed: ${err?.message || 'the request did not complete.'} Nothing was added — you can retry.`
      );
    } finally {
      if (scope.active) { researchPendingRef.current = false; setIsRunningResearch(false); }
    }
  };

  const handleRunResearch = async () => {
    const scope = scopeRef.current;
    if (!scope.active || researchPendingRef.current) return;
    setLoadError(null);
    setResearchStatusText('Researching — this usually takes 30–90 seconds on free providers…');
    setIsRunningResearch(true);
    let accepted: ResearchRun;
    try {
      accepted = await api.startResearch(studyId, scope.controller.signal);
    } catch (err: any) {
      if (!scope.active) return;
      setIsRunningResearch(false);
      setResearchStatusText('');
      // The server refuses a second concurrent run (409): show the one running.
      if (err?.status === 409) {
        await loadAllData();
        if (!scope.active) return;
        setLoadError(err?.message || 'An evidence research run is already in progress for this study.');
        return;
      }
      setLoadError(`Research run failed: ${err?.message || 'the request did not complete.'} Nothing was added — you can retry.`);
      return;
    }
    if (!scope.active) return;
    setIsRunningResearch(false);
    await followRun(accepted);
  };

  const handleInspectClaim = async (claimId: string) => {
    const scope = scopeRef.current;
    if (!scope.active) return;
    const generation = ++claimGenerationRef.current;
    setClaimInspectionError(null);
    try {
      const detail = await api.getEvidenceClaimDetail(studyId, claimId, scope.controller.signal);
      if (scope.active && generation === claimGenerationRef.current) setSelectedClaimDetail(detail);
    } catch (error: unknown) {
      if (!scope.active || generation !== claimGenerationRef.current) return;
      setClaimInspectionError({
        claimId,
        message: `Claim provenance could not be loaded: ${error instanceof Error ? error.message : 'The request did not complete.'}`,
      });
    }
  };

  // Re-filtering (and re-lowercasing) every claim and source on unrelated
  // re-renders is the single hottest thing in this view once a study has real
  // evidence in it.
  const normalizedQuery = searchQuery.toLowerCase();

  const filteredClaims = useMemo(
    () =>
      claims.filter((c) => {
        const matchStatus = statusFilter === 'all' || c.status === statusFilter;
        const matchCategory = categoryFilter === 'all' || c.category === categoryFilter;
        const matchSearch =
          !normalizedQuery ||
          c.claim_text.toLowerCase().includes(normalizedQuery) ||
          (c.rationale && c.rationale.toLowerCase().includes(normalizedQuery));
        return matchStatus && matchCategory && matchSearch;
      }),
    [claims, statusFilter, categoryFilter, normalizedQuery]
  );

  const filteredSources = useMemo(
    () =>
      sources.filter((s) => {
        const matchType = sourceTypeFilter === 'all' || s.source_type === sourceTypeFilter;
        const matchSearch =
          !normalizedQuery ||
          s.title.toLowerCase().includes(normalizedQuery) ||
          s.content.toLowerCase().includes(normalizedQuery) ||
          s.publisher.toLowerCase().includes(normalizedQuery);
        return matchType && matchSearch;
      }),
    [sources, sourceTypeFilter, normalizedQuery]
  );

  const getStatusBadge = (status: EvidenceStatus) => {
    if (status === 'supported') {
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '5px',
            background: 'var(--status-success-bg)',
            color: 'var(--status-success-text)',
            border: '1px solid var(--status-success-border)',
            padding: '3px 10px',
            borderRadius: '6px',
            fontSize: '0.78rem',
            fontWeight: 600,
          }}
        >
          <CheckCircle2 size={13} /> Evidence-supported
        </span>
      );
    }
    if (status === 'inference') {
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '5px',
            background: 'var(--status-warn-bg)',
            color: 'var(--status-warn-text)',
            border: '1px solid var(--status-warn-border)',
            padding: '3px 10px',
            borderRadius: '6px',
            fontSize: '0.78rem',
            fontWeight: 600,
          }}
        >
          <AlertTriangle size={13} /> Model Inference
        </span>
      );
    }
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '5px',
          background: 'var(--status-error-bg)',
          color: 'var(--status-error-text)',
          border: '1px solid var(--status-error-border)',
          padding: '3px 10px',
          borderRadius: '6px',
          fontSize: '0.78rem',
          fontWeight: 600,
        }}
      >
        <XCircle size={13} /> Unsupported Assumption
      </span>
    );
  };

  const getSourceTypeBadge = (type: string) => {
    return (
      <span
        style={{
          background: 'var(--bg-card)',
          color: 'var(--text-secondary)',
          border: '1px solid var(--border-subtle)',
          padding: '2px 8px',
          borderRadius: '4px',
          fontSize: '0.75rem',
          fontWeight: 600,
          textTransform: 'uppercase',
        }}
      >
        {type === 'curated_sample' ? 'SAMPLE' : type}
      </span>
    );
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        background: 'var(--bg-pure)',
        color: 'var(--text-primary)',
        minWidth: 0,
        letterSpacing: 0,
        overflowWrap: 'anywhere',
      }}
    >
      {/* Top Header */}
      <header
        className="bx-appheader"
        style={{
          padding: '20px clamp(14px, 3.5vw, 32px)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '16px',
          position: 'sticky',
          top: 0,
          zIndex: 20,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', flex: '1 1 320px', minWidth: 0 }}>
          {onBack && (
            <Button
              onClick={onBack}
              variant="ghost"
              size="sm"
              icon
              aria-label="Back"
              title="Back"
              leadingIcon={<ArrowLeft size={16} />}
              style={{ flexShrink: 0, color: 'var(--text-secondary)' }}
            />
          )}
          <div style={{ minWidth: 0 }}>
            <p style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', margin: '0 0 6px' }}>
              Evidence Laboratory
            </p>
            <h1 style={{ fontSize: '1.25rem', fontWeight: 700, lineHeight: 1.35, margin: 0, color: 'var(--text-primary)', overflowWrap: 'anywhere' }}>
              {study?.title || study?.prompt || 'Study Research & Evidence'}
            </h1>
            <p style={{ fontSize: '0.82rem', lineHeight: 1.5, color: 'var(--text-secondary)', margin: '8px 0 0', maxWidth: '70ch' }}>
              Collected sources, extracted claims, and per-claim support status
            </p>
          </div>
        </div>

        {/* Primary CTA */}
        <Button
          onClick={handleRunResearch}
          variant="secondary"
          size="sm"
          loading={isRunningResearch}
          leadingIcon={<Sparkles size={16} />}
          style={{ minWidth: '148px', flexShrink: 0 }}
        >
          {isRunningResearch ? 'Researching...' : 'Run Research'}
        </Button>
      </header>

      {/* Main Content Body */}
      <div style={{ maxWidth: '1400px', width: '100%', minWidth: 0, boxSizing: 'border-box', margin: '0 auto', padding: '24px clamp(14px, 3.5vw, 32px)' }}>
        {/* Load error banner */}
        {visibleError && !isRunningResearch && (
          <div
            role="alert"
            style={{
              background: 'var(--status-error-bg)',
              border: '1px solid var(--status-error-border)',
              borderRadius: '8px',
              padding: '14px 18px',
              marginBottom: '20px',
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
              color: 'var(--status-error-text)',
              fontSize: '0.88rem',
            }}
          >
            <span>{visibleError}</span>
            <Button
              size="sm"
              onClick={loadAllData}
              leadingIcon={<RefreshCw size={14} />}
            >
              Retry
            </Button>
          </div>
        )}

        {/* Research progress / outcome banner (spinner only while a run is in flight) */}
        {researchStatusText && (
          <div
            role="status"
            style={{
              borderBottom: '1px solid var(--border-subtle)',
              padding: '12px 0',
              marginBottom: '20px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            {isRunningResearch ? (
              <RefreshCw size={18} color="var(--text-secondary)" className="spin" style={{ flexShrink: 0 }} />
            ) : (
              <CheckCircle2 size={18} color="var(--status-success-text)" style={{ flexShrink: 0 }} aria-hidden="true" />
            )}
            <span style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-primary)', flex: 1 }}>
              {researchStatusText}
            </span>
            {!isRunningResearch && (
              <Button size="sm" variant="ghost" icon aria-label="Dismiss research status" leadingIcon={<X size={14} />} onClick={() => setResearchStatusText('')} />
            )}
          </div>
        )}

        {/* Evidence Overview Metrics Bar */}
        <dl
          aria-label="Evidence summary"
          className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4"
          style={{
            margin: '0 0 24px',
            paddingBottom: '24px',
            borderBottom: '1px solid var(--border-subtle)',
          }}
        >
          <div style={{ minWidth: 0 }}>
            <dt style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
              Evidence Coverage
            </dt>
            <dd style={{ margin: '6px 0 0', display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: '8px' }}>
              <span style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                {summary?.evidence_coverage == null ? (pendingReads.summary ? 'Loading' : 'Unknown') : `${summary.evidence_coverage}%`}
              </span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                {summary?.supported_count ?? 'Unknown'} supported claims
              </span>
            </dd>
          </div>
          {[
            { label: 'Supported Evidence', percentage: summary?.supported_pct, count: summary?.supported_count, description: 'Claims citing retrieved chunks from collected sources' },
            { label: 'Model Inferences', percentage: summary?.inferred_pct, count: summary?.inferred_count, description: 'Plausible extrapolation needing interview probe' },
            { label: 'Unsupported', percentage: summary?.unsupported_pct, count: summary?.unsupported_count, description: 'Ungrounded assumptions or contradicted points' },
          ].map((figure) => (
            <div key={figure.label} style={{ minWidth: 0 }}>
              <dt style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
                {figure.label}
              </dt>
              <dd style={{ margin: '6px 0 0', display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: '8px' }}>
                <span style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {figure.percentage == null ? 'Unknown' : `${figure.percentage}%`}
                </span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  ({figure.count ?? 'Unknown'} claims)
                </span>
              </dd>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', margin: '8px 0 0' }}>
                {figure.description}
              </p>
            </div>
          ))}
        </dl>

        {/* Navigation Tabs */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '12px 20px',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid var(--border-subtle)',
            marginBottom: '20px',
            paddingBottom: '12px',
          }}
        >
          <div role="tablist" aria-label="Evidence views" onKeyDown={tabKeyboard} style={{ display: 'flex', flex: '1 1 440px', minWidth: 0, gap: '16px', overflowX: 'auto' }}>
            <button
              type="button" role="tab" id={`${tabsId}-claims`} aria-controls={`${tabsId}-panel`} aria-selected={activeTab === 'claims'} tabIndex={activeTab === 'claims' ? 0 : -1}
              onClick={() => setActiveTab('claims')}
              style={{
                background: 'transparent',
                border: 'none',
                borderBottom: activeTab === 'claims' ? '2px solid var(--text-primary)' : '2px solid transparent',
                color: activeTab === 'claims' ? 'var(--text-primary)' : 'var(--text-secondary)',
                padding: '10px 2px',
                fontSize: '0.8125rem',
                flexShrink: 0,
                whiteSpace: 'nowrap',
                fontWeight: activeTab === 'claims' ? 600 : 400,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <ShieldCheck size={16} />
              Key Claims ({pendingReads.claims || readErrors.claims ? '?' : claims.length})
            </button>

            <button
              type="button" role="tab" id={`${tabsId}-sources`} aria-controls={`${tabsId}-panel`} aria-selected={activeTab === 'sources'} tabIndex={activeTab === 'sources' ? 0 : -1}
              onClick={() => setActiveTab('sources')}
              style={{
                background: 'transparent',
                border: 'none',
                borderBottom: activeTab === 'sources' ? '2px solid var(--text-primary)' : '2px solid transparent',
                color: activeTab === 'sources' ? 'var(--text-primary)' : 'var(--text-secondary)',
                padding: '10px 2px',
                fontSize: '0.8125rem',
                flexShrink: 0,
                whiteSpace: 'nowrap',
                fontWeight: activeTab === 'sources' ? 600 : 400,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <Database size={16} />
              Sources & Chunks ({pendingReads.sources || readErrors.sources ? '?' : sources.length})
            </button>

            <button
              type="button" role="tab" id={`${tabsId}-runs`} aria-controls={`${tabsId}-panel`} aria-selected={activeTab === 'runs'} tabIndex={activeTab === 'runs' ? 0 : -1}
              onClick={() => setActiveTab('runs')}
              style={{
                background: 'transparent',
                border: 'none',
                borderBottom: activeTab === 'runs' ? '2px solid var(--text-primary)' : '2px solid transparent',
                color: activeTab === 'runs' ? 'var(--text-primary)' : 'var(--text-secondary)',
                padding: '10px 2px',
                fontSize: '0.8125rem',
                flexShrink: 0,
                whiteSpace: 'nowrap',
                fontWeight: activeTab === 'runs' ? 600 : 400,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <Clock size={16} />
              Research History ({pendingReads.runs || readErrors.runs ? '?' : runs.length})
            </button>
          </div>

          {/* Search Bar */}
          <div style={{ position: 'relative', flex: '1 1 220px', minWidth: 0, maxWidth: '320px' }}>
            <Search size={14} color="var(--text-secondary)" style={{ position: 'absolute', left: '12px', top: '10px' }} />
            <input
              type="text"
              aria-label="Search claims and evidence"
              placeholder="Search claims & evidence..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%',
                background: 'var(--bg-secondary)',
                border: '1px solid var(--bg-card-hover)',
                borderRadius: '6px',
                padding: '7px 12px 7px 34px',
                color: 'var(--text-primary)',
                fontSize: '0.84rem',
              }}
            />
          </div>
        </div>

        {/* Tab 1: Key Claims List */}
        <div role="tabpanel" id={`${tabsId}-panel`} aria-labelledby={`${tabsId}-${activeTab}`} aria-busy={isLoading} tabIndex={0}>
        {isLoading && <div role="status">Loading {activeTab}...</div>}
        {activeTab === 'claims' && !isLoading && !readErrors.claims && (
          <div>
            {/* Filter Pills */}
            <div role="group" aria-label="Claim status" style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '18px', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginRight: '4px' }}>Filter Status:</span>
              {[
                { id: 'all', label: 'All' },
                { id: 'supported', label: 'Evidence-Supported (Green)' },
                { id: 'inference', label: 'Inferences (Amber)' },
                { id: 'unsupported', label: 'Unsupported (Red)' },
              ].map((pill) => (
                <Button
                  key={pill.id}
                  size="sm"
                  onClick={() => setStatusFilter(pill.id)}
                  aria-pressed={statusFilter === pill.id}
                  style={{
                    background: statusFilter === pill.id ? 'var(--text-primary)' : 'transparent',
                    color: statusFilter === pill.id ? 'var(--bg-primary)' : 'var(--text-secondary)',
                    borderColor: statusFilter === pill.id ? 'var(--text-primary)' : 'var(--border-subtle)',
                    borderRadius: '6px',
                  }}
                >
                  {pill.label}
                </Button>
              ))}
            </div>

            {/* Claims Cards Grid */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {filteredClaims.map((claim) => (
                <div
                  key={claim.id}
                  style={{
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--bg-card-hover)',
                    borderRadius: '8px',
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                    transition: 'border-color 0.2s ease',
                  }}
                >
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}>
                      {getStatusBadge(claim.status)}
                      <span
                        style={{
                          background: 'var(--bg-card)',
                          color: 'var(--text-secondary)',
                          border: '1px solid var(--bg-card-hover)',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          textTransform: 'uppercase',
                          fontWeight: 600,
                        }}
                      >
                        {claim.category}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Confidence:</span>
                      <div style={{ width: '60px', height: '6px', background: 'var(--bg-card-hover)', borderRadius: '3px', overflow: 'hidden' }}>
                        <div
                          style={{
                            height: '100%',
                            width: `${Math.round(claim.confidence * 100)}%`,
                            background:
                              claim.status === 'supported'
                                ? 'var(--status-success-text)'
                                : claim.status === 'inference'
                                ? 'var(--status-warn-text)'
                                : 'var(--status-error-text)',
                          }}
                        />
                      </div>
                      <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {Math.round(claim.confidence * 100)}%
                      </span>
                    </div>
                  </div>

                  <p style={{ fontSize: '0.96rem', fontWeight: 600, color: 'var(--text-primary)', margin: '4px 0 0 0', lineHeight: 1.5 }}>
                    {claim.claim_text}
                  </p>

                  {claim.rationale && (
                    <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.4 }}>
                      {claim.rationale}
                    </p>
                  )}

                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center', justifyContent: 'space-between', paddingTop: '10px', borderTop: '1px solid var(--bg-card-hover)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                        {claim.supporting_source_ids.length > 0 ? (
                          <>Cites {claim.supporting_source_ids.length} collected source{claim.supporting_source_ids.length === 1 ? '' : 's'}</>
                        ) : claim.contradicting_source_ids.length > 0 ? (
                          <span style={{ color: 'var(--status-error-text)' }}>Contradicted by {claim.contradicting_source_ids.length} sources</span>
                        ) : (
                          <>No direct citations (Inference)</>
                        )}
                      </span>
                    </div>

                    <Button
                      size="sm"
                      onClick={(event) => {
                        claimInspectionTriggerRef.current = event.currentTarget;
                        void handleInspectClaim(claim.id);
                      }}
                      trailingIcon={<ChevronRight size={14} />}
                    >
                      Inspect Provenance
                    </Button>
                  </div>
                  {claimInspectionError?.claimId === claim.id && (
                    <div role="alert" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px', color: 'var(--status-error-text)', fontSize: '0.8125rem' }}>
                      <span>{claimInspectionError.message}</span>
                      <Button
                        size="sm"
                        leadingIcon={<RefreshCw size={14} />}
                        onClick={() => handleInspectClaim(claim.id)}
                      >
                        Retry inspection
                      </Button>
                    </div>
                  )}
                </div>
              ))}

              {filteredClaims.length === 0 && (
                <div
                  style={{
                    padding: '32px 0',
                    textAlign: 'center',
                    color: 'var(--text-secondary)',
                  }}
                >
                  <p style={{ fontSize: '0.92rem', margin: '0 0 12px 0' }}>No claims match your filters.</p>
                  <Button
                    size="sm"
                    leadingIcon={<RefreshCw size={14} />}
                    onClick={() => {
                      setStatusFilter('all');
                      setSearchQuery('');
                    }}
                  >
                    Reset Filters
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 2: Sources Repository */}
        {activeTab === 'sources' && !isLoading && !readErrors.sources && (
          <div>
            <div role="group" aria-label="Source type" style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '18px', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginRight: '4px' }}>Source Type:</span>
              {[
                { id: 'all', label: 'All Sources' },
                { id: 'web', label: 'Web' },
                { id: 'reddit', label: 'Reddit / Forums' },
                { id: 'report', label: 'Survey Reports' },
                { id: 'review', label: 'Competitor Reviews' },
              ].map((pill) => (
                <Button
                  key={pill.id}
                  size="sm"
                  onClick={() => setSourceTypeFilter(pill.id)}
                  aria-pressed={sourceTypeFilter === pill.id}
                  style={{
                    background: sourceTypeFilter === pill.id ? 'var(--text-primary)' : 'transparent',
                    color: sourceTypeFilter === pill.id ? 'var(--bg-primary)' : 'var(--text-secondary)',
                    borderColor: sourceTypeFilter === pill.id ? 'var(--text-primary)' : 'var(--border-subtle)',
                    borderRadius: '6px',
                  }}
                >
                  {pill.label}
                </Button>
              ))}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {filteredSources.map((src) => {
                const sourceUrl = externalSourceUrl(src.url);
                return (
                <div
                  key={src.id}
                  style={{
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--bg-card-hover)',
                    borderRadius: '8px',
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '10px',
                  }}
                >
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}>
                      {getSourceTypeBadge(src.source_type)}
                      <span style={{ fontSize: '0.84rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {src.publisher}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
                        {Math.round(src.relevance_score * 100)}% Relevance
                      </span>
                      {sourceUrl && (
                        <a
                          href={sourceUrl}
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.78rem', textDecoration: 'none' }}
                        >
                          Open <ExternalLink size={12} />
                        </a>
                      )}
                    </div>
                  </div>

                  <h3 style={{ fontSize: '0.98rem', fontWeight: 600, color: 'var(--text-primary)', margin: '4px 0 0 0' }}>
                    {src.title}
                  </h3>

                  <p style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.5 }}>
                    {src.content}
                  </p>
                </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Tab 3: Research History */}
        {activeTab === 'runs' && !isLoading && !readErrors.runs && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {runs.map((r) => (
              <div
                key={r.id}
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--bg-card-hover)',
                  borderRadius: '8px',
                  padding: '16px',
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '12px',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
                    <span
                      style={{
                        background: r.status === 'completed' ? 'var(--status-success-bg)' : 'var(--bg-card)',
                        color: r.status === 'completed' ? 'var(--status-success-text)' : 'var(--text-secondary)',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        textTransform: 'uppercase',
                      }}
                    >
                      {r.status}
                    </span>
                    <span style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                      Research Run {r.id.slice(0, 10)}
                    </span>
                  </div>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: 0 }}>
                    {r.query_count} queries generated • {r.source_count} sources collected • {r.claim_count} claims synthesized
                  </p>
                  {r.status === 'completed' ? null : isResearchRunSettled(r) ? (
                    <p style={{ fontSize: '0.78rem', color: 'var(--status-error-text)', margin: '6px 0 0' }}>
                      {r.error_message?.trim() || 'Stopped before any evidence was saved; the reason was not recorded.'}
                    </p>
                  ) : (
                    <p style={{ fontSize: '0.78rem', color: 'var(--status-warn-text)', margin: '6px 0 0' }}>
                      {researchProgressText(r)}
                    </p>
                  )}
                </div>

                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {r.completed_at ? new Date(r.completed_at).toLocaleString() : new Date(r.created_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
        </div>
      </div>

      {/* Claim Provenance Modal */}
      {selectedClaimDetail && (
        <div
          className="bx-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'var(--scrim)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: '20px',
          }}
          onClick={closeClaimInspection}
        >
          <div
            ref={claimDialogRef}
            className="bx-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="claim-provenance-title"
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '12px',
              maxWidth: '750px',
              width: '100%',
              maxHeight: '85vh',
              overflowY: 'auto',
              padding: '20px',
              boxShadow: '0 20px 40px rgba(0, 0, 0, 0.5)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div style={{ display: 'flex', minWidth: 0, alignItems: 'center', gap: '8px' }}>
                <ShieldCheck size={18} color="var(--text-secondary)" style={{ flexShrink: 0 }} />
                <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Claim Provenance Inspection
                </span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                icon
                onClick={closeClaimInspection}
                aria-label="Close claim provenance"
                title="Close claim provenance"
                leadingIcon={<X size={18} />}
                style={{ color: 'var(--text-secondary)', flexShrink: 0 }}
              />
            </div>

            <div style={{ marginBottom: '14px' }}>{getStatusBadge(selectedClaimDetail.status)}</div>

            <h2 id="claim-provenance-title" style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 12px 0', lineHeight: 1.4 }}>
              {selectedClaimDetail.claim_text}
            </h2>

            {/* Why does BebshaX believe this? */}
            <div
              style={{
                borderTop: '1px solid var(--border-subtle)',
                padding: '16px 0',
                marginBottom: '20px',
              }}
            >
              <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>
                Why does BebshaX evaluate this as {selectedClaimDetail.status.toUpperCase()}?
              </div>
              <p style={{ fontSize: '0.86rem', color: 'var(--text-primary)', margin: 0, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                {selectedClaimDetail.rationale ||
                  'No rationale was recorded for this claim.'}
              </p>
            </div>

            {[
              { label: 'Supporting sources', sources: selectedClaimDetail.supporting_sources ?? [], empty: 'No supporting sources attached to this claim.' },
              { label: 'Contradicting sources', sources: selectedClaimDetail.contradicting_sources ?? [], empty: 'No contradicting sources attached to this claim.' },
            ].map((group) => (
              <div key={group.label} style={{ marginBottom: '20px' }}>
                <h3 style={{ fontSize: '0.86rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '10px' }}>
                  {group.label} ({group.sources.length})
                </h3>
                {group.sources.length > 0 ? (
                  <ul aria-label={group.label} role="list" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                    {group.sources.map((source) => {
                      const sourceUrl = externalSourceUrl(source.url);
                      return (
                        <li key={source.id} style={{ minWidth: 0, borderTop: '1px solid var(--border-subtle)', padding: '14px 0' }}>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                            <span style={{ fontSize: '0.86rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                              {source.title || source.publisher || source.id}
                            </span>
                            {sourceUrl && (
                              <a href={sourceUrl} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem', textDecoration: 'underline', textUnderlineOffset: '0.2em', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                Open source <ExternalLink size={12} aria-hidden="true" />
                              </a>
                            )}
                          </div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px', marginBottom: '8px', color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>
                            {getSourceTypeBadge(source.source_type)}
                            {source.publisher && <span>{source.publisher}</span>}
                            <span>Source <code>{source.id}</code></span>
                          </div>
                          <blockquote style={{ fontSize: '0.875rem', color: 'var(--text-primary)', margin: 0, lineHeight: 1.5, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                            {source.content}
                          </blockquote>
                        </li>
                      );
                    })}
                  </ul>
                ) : <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>{group.empty}</p>}
              </div>
            ))}

            <div style={{ marginBottom: '20px' }}>
              <h3 style={{ fontSize: '0.86rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '10px' }}>
                Supporting excerpts ({selectedClaimDetail.supporting_chunks?.length ?? 0})
              </h3>
              {selectedClaimDetail.supporting_chunks?.length ? (
                <ul aria-label="Supporting excerpts" role="list" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                  {selectedClaimDetail.supporting_chunks.map((chunk) => (
                    <li key={chunk.id} style={{ minWidth: 0, borderTop: '1px solid var(--border-subtle)', padding: '14px 0' }}>
                      <blockquote style={{ fontSize: '0.875rem', color: 'var(--text-primary)', margin: 0, lineHeight: 1.5, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                        {chunk.content}
                      </blockquote>
                      <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', margin: '8px 0 0' }}>
                        Source <code>{chunk.source_id}</code> / Excerpt <code>{chunk.id}</code>
                      </p>
                    </li>
                  ))}
                </ul>
              ) : <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>No supporting excerpts attached to this claim.</p>}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
              <Button
                size="sm"
                leadingIcon={<X size={14} />}
                onClick={closeClaimInspection}
              >
                Close Inspection
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
