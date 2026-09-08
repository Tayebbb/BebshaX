import React, { useState, useEffect, useMemo, useRef } from 'react';
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
import { useDialogA11y } from '../../../utils/useDialogA11y';

interface EvidenceLaboratoryViewProps {
  studyId: string;
  study?: Study | null;
  onBack?: () => void;
}

export const EvidenceLaboratoryView: React.FC<EvidenceLaboratoryViewProps> = ({
  studyId,
  study,
  onBack,
}) => {
  const [activeTab, setActiveTab] = useState<'claims' | 'sources' | 'runs'>('claims');
  const [summary, setSummary] = useState<EvidenceSummary | null>(null);
  const [claims, setClaims] = useState<EvidenceClaim[]>([]);
  const [sources, setSources] = useState<EvidenceSource[]>([]);
  const [runs, setRuns] = useState<ResearchRun[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [categoryFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sourceTypeFilter, setSourceTypeFilter] = useState<string>('all');
  const [selectedClaimDetail, setSelectedClaimDetail] = useState<ClaimDetail | null>(null);
  const claimDialogRef = useRef<HTMLDivElement | null>(null);
  useDialogA11y(claimDialogRef, !!selectedClaimDetail, () => setSelectedClaimDetail(null));
  const [, setIsLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isRunningResearch, setIsRunningResearch] = useState<boolean>(false);
  const [researchStatusText, setResearchStatusText] = useState<string>('');

  // Real unmount guard for post-await state writes.
  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const loadAllData = async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const [sumRes, claimsRes, sourcesRes, runsRes] = await Promise.all([
        api.getEvidenceSummary(studyId),
        api.getEvidenceClaims(studyId),
        api.getEvidenceSources(studyId),
        api.getResearchRuns(studyId),
      ]);
      setSummary(sumRes);
      setClaims(claimsRes);
      setSources(sourcesRes);
      setRuns(runsRes);
    } catch (err: any) {
      setLoadError(err?.message || 'Failed to load evidence data.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAllData();
  }, [studyId]);

  const handleRunResearch = async () => {
    if (isRunningResearch) return;
    setIsRunningResearch(true);
    setLoadError(null);
    setResearchStatusText('Researching — this usually takes 30–90 seconds on free providers…');

    try {
      await api.startResearch(studyId);
      if (!isMountedRef.current) return;
      setResearchStatusText('Research complete — evidence extracted.');
      await loadAllData();
    } catch (err: any) {
      if (!isMountedRef.current) return;
      setResearchStatusText('');
      setLoadError(
        `Research run failed: ${err?.message || 'the request did not complete.'} Nothing was added — you can retry.`
      );
    } finally {
      if (isMountedRef.current) setIsRunningResearch(false);
    }
  };

  const handleInspectClaim = async (claimId: string) => {
    try {
      const detail = await api.getEvidenceClaimDetail(studyId, claimId);
      setSelectedClaimDetail(detail);
    } catch {
      // fallback
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
            background: 'rgba(16, 185, 129, 0.12)',
            color: 'var(--accent-emerald)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
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
            background: 'rgba(245, 158, 11, 0.12)',
            color: '#F59E0B',
            border: '1px solid rgba(245, 158, 11, 0.3)',
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
          background: 'rgba(239, 68, 68, 0.12)',
          color: '#EF4444',
          border: '1px solid rgba(239, 68, 68, 0.3)',
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
    const colors: Record<string, { bg: string; text: string; border: string }> = {
      reddit: { bg: 'rgba(255, 69, 0, 0.12)', text: '#FF5722', border: 'rgba(255, 69, 0, 0.3)' },
      report: { bg: 'var(--accent-subtle)', text: 'var(--accent-cyan)', border: 'var(--accent-glow)' },
      review: { bg: 'rgba(245, 158, 11, 0.12)', text: '#FBBF24', border: 'rgba(245, 158, 11, 0.3)' },
      web: { bg: 'rgba(59, 130, 246, 0.12)', text: '#60A5FA', border: 'rgba(59, 130, 246, 0.3)' },
      curated_sample: { bg: 'rgba(156, 163, 175, 0.15)', text: 'var(--text-secondary)', border: 'rgba(156, 163, 175, 0.35)' },
    };
    const c = colors[type] || { bg: 'rgba(156, 163, 175, 0.12)', text: 'var(--text-muted)', border: 'rgba(156, 163, 175, 0.3)' };
    return (
      <span
        style={{
          background: c.bg,
          color: c.text,
          border: `1px solid ${c.border}`,
          padding: '2px 8px',
          borderRadius: '4px',
          fontSize: '0.74rem',
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
        background: 'transparent',
        color: 'var(--text-primary)',
      }}
    >
      {/* Top Header */}
      <header
        className="bx-appheader"
        style={{
          padding: '20px clamp(14px, 3.5vw, 32px)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          position: 'sticky',
          top: 0,
          zIndex: 20,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          {onBack && (
            <button
              onClick={onBack}
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--bg-card-hover)',
                color: 'var(--text-secondary)',
                borderRadius: '8px',
                padding: '8px 12px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                cursor: 'pointer',
                fontSize: '0.84rem',
              }}
            >
              <ArrowLeft size={15} /> Back
            </button>
          )}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span
                style={{
                  background: 'var(--accent-subtle)',
                  color: 'var(--accent-cyan)',
                  border: '1px solid var(--border-hover)',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
              >
                Evidence Laboratory
              </span>
              <h1 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
                {study?.title || study?.prompt || 'Study Research & Evidence'}
              </h1>
            </div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: '4px 0 0 0' }}>
              Collected sources, extracted claims, and per-claim support status — sample sources are labeled
            </p>
          </div>
        </div>

        {/* Primary CTA */}
        <button
          onClick={handleRunResearch}
          disabled={isRunningResearch}
          style={{
            background: isRunningResearch ? '#0D9488' : 'var(--accent-gradient)',
            color: 'var(--text-on-accent)',
            border: 'none',
            borderRadius: '8px',
            padding: '10px 20px',
            fontSize: '0.88rem',
            fontWeight: 600,
            cursor: isRunningResearch ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            boxShadow: '0 4px 14px var(--border-hover)',
            transition: 'all 0.2s ease',
          }}
        >
          {isRunningResearch ? (
            <>
              <RefreshCw size={16} className="spin" />
              <span>Researching...</span>
            </>
          ) : (
            <>
              <Sparkles size={16} />
              <span>Run Research</span>
            </>
          )}
        </button>
      </header>

      {/* Main Content Body */}
      <div style={{ maxWidth: '1400px', width: '100%', margin: '0 auto', padding: '28px clamp(14px, 3.5vw, 32px)' }}>
        {/* Load error banner */}
        {loadError && !isRunningResearch && (
          <div
            role="alert"
            style={{
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.4)',
              borderRadius: '10px',
              padding: '14px 18px',
              marginBottom: '20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
              color: 'var(--status-error-text)',
              fontSize: '0.88rem',
            }}
          >
            <span>{loadError}</span>
            <button
              type="button"
              onClick={loadAllData}
              style={{ background: 'transparent', border: '1px solid currentColor', borderRadius: '6px', padding: '4px 12px', color: 'inherit', cursor: 'pointer', fontWeight: 600, fontSize: '0.82rem', whiteSpace: 'nowrap' }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Research Running Banner */}
        {isRunningResearch && (
          <div
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--accent-teal)',
              borderRadius: '12px',
              padding: '20px 24px',
              marginBottom: '24px',
              boxShadow: '0 8px 24px var(--accent-subtle)',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <RefreshCw size={18} color="var(--accent-cyan)" className="spin" />
            <span style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              {researchStatusText}
            </span>
          </div>
        )}

        {/* Evidence Overview Metrics Bar */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))',
            gap: '16px',
            marginBottom: '28px',
          }}
        >
          {/* Coverage Card */}
          <div
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '10px',
              padding: '18px 20px',
            }}
          >
            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600, marginBottom: '6px' }}>
              Evidence Coverage
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
              <span style={{ fontSize: '1.9rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                {summary?.evidence_coverage ?? 0}%
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--accent-emerald)', fontWeight: 600 }}>
                {summary?.supported_count ?? 0} supported claims
              </span>
            </div>
            <div style={{ height: '5px', background: 'var(--border-subtle)', borderRadius: '3px', marginTop: '10px', overflow: 'hidden' }}>
              <div
                style={{
                  height: '100%',
                  width: `${summary?.evidence_coverage ?? 0}%`,
                  background: 'linear-gradient(90deg, #14B8A6 0%, var(--accent-emerald) 100%)',
                }}
              />
            </div>
          </div>

          {/* Supported Card */}
          <div
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid rgba(16, 185, 129, 0.25)',
              borderRadius: '10px',
              padding: '18px 20px',
            }}
          >
            <div style={{ fontSize: '0.78rem', color: 'var(--accent-emerald)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600, marginBottom: '6px' }}>
              Supported Evidence (Green)
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
              <span style={{ fontSize: '1.9rem', fontWeight: 800, color: 'var(--accent-emerald)' }}>
                {summary?.supported_pct ?? 0}%
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                ({summary?.supported_count ?? 0} claims)
              </span>
            </div>
            <p style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', margin: '8px 0 0 0' }}>
              Claims citing retrieved chunks from collected sources
            </p>
          </div>

          {/* Inferred Card */}
          <div
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid rgba(245, 158, 11, 0.25)',
              borderRadius: '10px',
              padding: '18px 20px',
            }}
          >
            <div style={{ fontSize: '0.78rem', color: '#F59E0B', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600, marginBottom: '6px' }}>
              Model Inferences (Amber)
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
              <span style={{ fontSize: '1.9rem', fontWeight: 800, color: '#F59E0B' }}>
                {summary?.inferred_pct ?? 0}%
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                ({summary?.inferred_count ?? 0} claims)
              </span>
            </div>
            <p style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', margin: '8px 0 0 0' }}>
              Plausible extrapolation needing interview probe
            </p>
          </div>

          {/* Unsupported Card */}
          <div
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              borderRadius: '10px',
              padding: '18px 20px',
            }}
          >
            <div style={{ fontSize: '0.78rem', color: '#EF4444', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600, marginBottom: '6px' }}>
              Unsupported (Red)
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
              <span style={{ fontSize: '1.9rem', fontWeight: 800, color: '#EF4444' }}>
                {summary?.unsupported_pct ?? 0}%
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                ({summary?.unsupported_count ?? 0} claims)
              </span>
            </div>
            <p style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', margin: '8px 0 0 0' }}>
              Ungrounded assumptions or contradicted points
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid var(--bg-card-hover)',
            marginBottom: '20px',
          }}
        >
          <div style={{ display: 'flex', gap: '24px' }}>
            <button
              onClick={() => setActiveTab('claims')}
              style={{
                background: 'transparent',
                border: 'none',
                borderBottom: activeTab === 'claims' ? '2px solid var(--accent-teal)' : '2px solid transparent',
                color: activeTab === 'claims' ? 'var(--text-primary)' : 'var(--text-secondary)',
                padding: '12px 4px',
                fontSize: '0.9rem',
                fontWeight: activeTab === 'claims' ? 600 : 400,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <ShieldCheck size={16} />
              Key Claims ({claims.length})
            </button>

            <button
              onClick={() => setActiveTab('sources')}
              style={{
                background: 'transparent',
                border: 'none',
                borderBottom: activeTab === 'sources' ? '2px solid var(--accent-teal)' : '2px solid transparent',
                color: activeTab === 'sources' ? 'var(--text-primary)' : 'var(--text-secondary)',
                padding: '12px 4px',
                fontSize: '0.9rem',
                fontWeight: activeTab === 'sources' ? 600 : 400,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <Database size={16} />
              Sources & Chunks ({sources.length})
            </button>

            <button
              onClick={() => setActiveTab('runs')}
              style={{
                background: 'transparent',
                border: 'none',
                borderBottom: activeTab === 'runs' ? '2px solid var(--accent-teal)' : '2px solid transparent',
                color: activeTab === 'runs' ? 'var(--text-primary)' : 'var(--text-secondary)',
                padding: '12px 4px',
                fontSize: '0.9rem',
                fontWeight: activeTab === 'runs' ? 600 : 400,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <Clock size={16} />
              Research History ({runs.length})
            </button>
          </div>

          {/* Search Bar */}
          <div style={{ position: 'relative', width: '280px' }}>
            <Search size={14} color="var(--text-secondary)" style={{ position: 'absolute', left: '12px', top: '10px' }} />
            <input
              type="text"
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
                outline: 'none',
              }}
            />
          </div>
        </div>

        {/* Tab 1: Key Claims List */}
        {activeTab === 'claims' && (
          <div>
            {/* Filter Pills */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '18px', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginRight: '4px' }}>Filter Status:</span>
              {[
                { id: 'all', label: 'All' },
                { id: 'supported', label: 'Evidence-Supported (Green)' },
                { id: 'inference', label: 'Inferences (Amber)' },
                { id: 'unsupported', label: 'Unsupported (Red)' },
              ].map((pill) => (
                <button
                  key={pill.id}
                  onClick={() => setStatusFilter(pill.id)}
                  style={{
                    background: statusFilter === pill.id ? 'var(--accent-subtle)' : 'var(--bg-secondary)',
                    color: statusFilter === pill.id ? 'var(--accent-teal)' : 'var(--text-secondary)',
                    border: statusFilter === pill.id ? '1px solid var(--accent-teal)' : '1px solid var(--bg-card-hover)',
                    borderRadius: '20px',
                    padding: '5px 12px',
                    fontSize: '0.78rem',
                    fontWeight: 500,
                    cursor: 'pointer',
                  }}
                >
                  {pill.label}
                </button>
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
                    borderRadius: '10px',
                    padding: '20px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                    transition: 'border-color 0.2s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      {getStatusBadge(claim.status)}
                      <span
                        style={{
                          background: 'var(--bg-card)',
                          color: 'var(--text-secondary)',
                          border: '1px solid var(--bg-card-hover)',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontSize: '0.74rem',
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
                                ? 'var(--accent-emerald)'
                                : claim.status === 'inference'
                                ? '#F59E0B'
                                : '#EF4444',
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

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '10px', borderTop: '1px solid var(--bg-card-hover)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                        {claim.supporting_source_ids.length > 0 ? (
                          <>Cites {claim.supporting_source_ids.length} collected source{claim.supporting_source_ids.length === 1 ? '' : 's'}</>
                        ) : claim.contradicting_source_ids.length > 0 ? (
                          <span style={{ color: '#EF4444' }}>Contradicted by {claim.contradicting_source_ids.length} sources</span>
                        ) : (
                          <>No direct citations (Inference)</>
                        )}
                      </span>
                    </div>

                    <button
                      onClick={() => handleInspectClaim(claim.id)}
                      style={{
                        background: 'var(--accent-subtle)',
                        border: '1px solid var(--accent-glow)',
                        color: 'var(--accent-teal)',
                        borderRadius: '6px',
                        padding: '6px 14px',
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                      }}
                    >
                      Inspect Provenance <ChevronRight size={14} />
                    </button>
                  </div>
                </div>
              ))}

              {filteredClaims.length === 0 && (
                <div
                  style={{
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--bg-card-hover)',
                    borderRadius: '10px',
                    padding: '40px 20px',
                    textAlign: 'center',
                    color: 'var(--text-secondary)',
                  }}
                >
                  <p style={{ fontSize: '0.92rem', margin: '0 0 12px 0' }}>No claims match your filters.</p>
                  <button
                    onClick={() => {
                      setStatusFilter('all');
                      setSearchQuery('');
                    }}
                    style={{
                      background: 'var(--bg-card)',
                      border: '1px solid var(--bg-card-hover)',
                      color: 'var(--accent-teal)',
                      borderRadius: '6px',
                      padding: '6px 14px',
                      fontSize: '0.82rem',
                      cursor: 'pointer',
                    }}
                  >
                    Reset Filters
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 2: Sources Repository */}
        {activeTab === 'sources' && (
          <div>
            <div style={{ display: 'flex', gap: '8px', marginBottom: '18px', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginRight: '4px' }}>Source Type:</span>
              {[
                { id: 'all', label: 'All Sources' },
                { id: 'web', label: 'Web' },
                { id: 'reddit', label: 'Reddit / Forums' },
                { id: 'report', label: 'Survey Reports' },
                { id: 'review', label: 'Competitor Reviews' },
              ].map((pill) => (
                <button
                  key={pill.id}
                  onClick={() => setSourceTypeFilter(pill.id)}
                  style={{
                    background: sourceTypeFilter === pill.id ? 'var(--accent-subtle)' : 'var(--bg-secondary)',
                    color: sourceTypeFilter === pill.id ? 'var(--accent-teal)' : 'var(--text-secondary)',
                    border: sourceTypeFilter === pill.id ? '1px solid var(--accent-teal)' : '1px solid var(--bg-card-hover)',
                    borderRadius: '20px',
                    padding: '5px 12px',
                    fontSize: '0.78rem',
                    fontWeight: 500,
                    cursor: 'pointer',
                  }}
                >
                  {pill.label}
                </button>
              ))}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {filteredSources.map((src) => (
                <div
                  key={src.id}
                  style={{
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--bg-card-hover)',
                    borderRadius: '10px',
                    padding: '20px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '10px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      {getSourceTypeBadge(src.source_type)}
                      <span style={{ fontSize: '0.84rem', fontWeight: 600, color: 'var(--accent-cyan)' }}>
                        {src.publisher}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ fontSize: '0.78rem', color: 'var(--accent-emerald)', fontWeight: 600 }}>
                        {Math.round(src.relevance_score * 100)}% Relevance
                      </span>
                      {src.url && (
                        <a
                          href={src.url}
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
              ))}
            </div>
          </div>
        )}

        {/* Tab 3: Research History */}
        {activeTab === 'runs' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {runs.map((r) => (
              <div
                key={r.id}
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--bg-card-hover)',
                  borderRadius: '10px',
                  padding: '18px 20px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
                    <span
                      style={{
                        background: r.status === 'completed' ? 'rgba(16, 185, 129, 0.15)' : 'var(--accent-subtle)',
                        color: r.status === 'completed' ? 'var(--accent-emerald)' : 'var(--accent-cyan)',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        fontSize: '0.74rem',
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
                </div>

                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {r.completed_at ? new Date(r.completed_at).toLocaleString() : new Date(r.created_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
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
          onClick={() => setSelectedClaimDetail(null)}
        >
          <div
            ref={claimDialogRef}
            className="bx-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="claim-provenance-title"
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid #2A3042',
              borderRadius: '12px',
              maxWidth: '750px',
              width: '100%',
              maxHeight: '85vh',
              overflowY: 'auto',
              padding: '28px',
              boxShadow: '0 20px 40px rgba(0, 0, 0, 0.5)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ShieldCheck size={18} color="var(--accent-cyan)" />
                <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--accent-cyan)', textTransform: 'uppercase' }}>
                  Claim Provenance Inspection
                </span>
              </div>
              <button
                type="button"
                onClick={() => setSelectedClaimDetail(null)}
                aria-label="Close claim provenance"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-secondary)',
                  fontSize: '1.2rem',
                  cursor: 'pointer',
                }}
              >
                <span aria-hidden="true">✕</span>
              </button>
            </div>

            <div style={{ marginBottom: '14px' }}>{getStatusBadge(selectedClaimDetail.status)}</div>

            <h2 id="claim-provenance-title" style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 12px 0', lineHeight: 1.4 }}>
              {selectedClaimDetail.claim_text}
            </h2>

            {/* Why does BebshaX believe this? */}
            <div
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--bg-card-hover)',
                borderRadius: '8px',
                padding: '16px',
                marginBottom: '20px',
              }}
            >
              <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--accent-cyan)', marginBottom: '6px' }}>
                Why does BebshaX evaluate this as {selectedClaimDetail.status.toUpperCase()}?
              </div>
              <p style={{ fontSize: '0.86rem', color: 'var(--text-primary)', margin: 0, lineHeight: 1.5 }}>
                {selectedClaimDetail.rationale ||
                  'No rationale was recorded for this claim.'}
              </p>
            </div>

            {/* Supporting Sources */}
            <div style={{ marginBottom: '20px' }}>
              <h4 style={{ fontSize: '0.86rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '10px' }}>
                Supporting Citations ({selectedClaimDetail.supporting_sources.length})
              </h4>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {selectedClaimDetail.supporting_sources.map((src) => (
                  <div
                    key={src.id}
                    style={{
                      background: 'var(--bg-card)',
                      border: '1px solid var(--bg-card-hover)',
                      borderRadius: '8px',
                      padding: '14px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                      <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--accent-cyan)' }}>
                        {src.publisher}
                      </span>
                      {src.url && (
                        <a
                          href={src.url}
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: 'var(--text-secondary)', fontSize: '0.76rem', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px' }}
                        >
                          Link <ExternalLink size={11} />
                        </a>
                      )}
                    </div>
                    <p style={{ fontSize: '0.84rem', color: 'var(--text-primary)', margin: 0, lineHeight: 1.4 }}>
                      "{src.content}"
                    </p>
                  </div>
                ))}

                {selectedClaimDetail.supporting_sources.length === 0 && (
                  <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                    No direct supporting citations found in the corpus. This claim is flagged as an unverified model assumption.
                  </p>
                )}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
              <button
                onClick={() => setSelectedClaimDetail(null)}
                style={{
                  background: 'var(--accent-teal)',
                  color: 'var(--text-on-accent)',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '8px 18px',
                  fontSize: '0.86rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Close Inspection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
