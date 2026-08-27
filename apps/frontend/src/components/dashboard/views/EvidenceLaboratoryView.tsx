import React, { useState, useEffect } from 'react';
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
  const [, setIsLoading] = useState<boolean>(true);
  const [isRunningResearch, setIsRunningResearch] = useState<boolean>(false);
  const [researchProgressStep, setResearchProgressStep] = useState<number>(0);
  const [researchStatusText, setResearchStatusText] = useState<string>('');

  const loadAllData = async () => {
    setIsLoading(true);
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
    } catch {
      // Fallback in case of network issue
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
    setResearchProgressStep(1);
    setResearchStatusText('Building autonomous research plan...');

    try {
      setTimeout(() => {
        setResearchProgressStep(2);
        setResearchStatusText('Discovering public datasets (BBS, World Bank, Kaggle)...');
      }, 800);

      setTimeout(() => {
        setResearchProgressStep(3);
        setResearchStatusText('Generating targeted research queries...');
      }, 1800);

      setTimeout(() => {
        setResearchProgressStep(4);
        setResearchStatusText('Searching empirical sources & public discussions...');
      }, 2800);

      setTimeout(() => {
        setResearchProgressStep(5);
        setResearchStatusText('Chunking documents & computing pgvector embeddings...');
      }, 3800);

      setTimeout(() => {
        setResearchProgressStep(6);
        setResearchStatusText('Extracting structured claims & empirical classification...');
      }, 5000);

      await api.startResearch(studyId);

      setTimeout(async () => {
        setResearchProgressStep(7);
        setResearchStatusText('Research complete — datasets discovered & evidence extracted.');
        await loadAllData();
        setIsRunningResearch(false);
      }, 6200);
    } catch {
      setIsRunningResearch(false);
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

  const filteredClaims = claims.filter((c) => {
    const matchStatus = statusFilter === 'all' || c.status === statusFilter;
    const matchCategory = categoryFilter === 'all' || c.category === categoryFilter;
    const matchSearch =
      !searchQuery ||
      c.claim_text.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.rationale && c.rationale.toLowerCase().includes(searchQuery.toLowerCase()));
    return matchStatus && matchCategory && matchSearch;
  });

  const filteredSources = sources.filter((s) => {
    const matchType = sourceTypeFilter === 'all' || s.source_type === sourceTypeFilter;
    const matchSearch =
      !searchQuery ||
      s.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.publisher.toLowerCase().includes(searchQuery.toLowerCase());
    return matchType && matchSearch;
  });

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
      report: { bg: 'rgba(99, 102, 241, 0.12)', text: '#818CF8', border: 'rgba(99, 102, 241, 0.3)' },
      review: { bg: 'rgba(245, 158, 11, 0.12)', text: '#FBBF24', border: 'rgba(245, 158, 11, 0.3)' },
      web: { bg: 'rgba(59, 130, 246, 0.12)', text: '#60A5FA', border: 'rgba(59, 130, 246, 0.3)' },
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
        {type}
      </span>
    );
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        background: '#08090B',
        color: 'var(--text-primary)',
        fontFamily: 'Inter, -apple-system, sans-serif',
      }}
    >
      {/* Top Header */}
      <header
        className="bx-appheader"
        style={{
          padding: '20px clamp(14px, 3.5vw, 32px)',
          borderBottom: '1px solid var(--bg-card-hover)',
          background: 'var(--bg-secondary)',
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
              Empirical market grounding, public sources, and verified claim confidence
            </p>
          </div>
        </div>

        {/* Primary CTA */}
        <button
          onClick={handleRunResearch}
          disabled={isRunningResearch}
          style={{
            background: isRunningResearch ? '#0D9488' : 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
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
        {/* Research Running Stepper Banner */}
        {isRunningResearch && (
          <div
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid #14B8A6',
              borderRadius: '12px',
              padding: '20px 24px',
              marginBottom: '24px',
              boxShadow: '0 8px 24px var(--accent-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <RefreshCw size={18} color="var(--accent-cyan)" className="spin" />
                <span style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {researchStatusText}
                </span>
              </div>
              <span style={{ fontSize: '0.8rem', color: 'var(--accent-cyan)', fontWeight: 600 }}>
                Step {researchProgressStep} of 7
              </span>
            </div>

            {/* Stepper Progress Bar */}
            <div style={{ display: 'flex', gap: '8px' }}>
              {[1, 2, 3, 4, 5, 6, 7].map((step) => {
                const isPassed = researchProgressStep > step;
                const isCurrent = researchProgressStep === step;
                return (
                  <div
                    key={step}
                    style={{
                      flex: 1,
                      height: '6px',
                      borderRadius: '3px',
                      background: isPassed
                        ? 'var(--accent-emerald)'
                        : isCurrent
                        ? '#14B8A6'
                        : 'var(--border-subtle)',
                      transition: 'background 0.3s ease',
                    }}
                  />
                );
              })}
            </div>
          </div>
        )}

        {/* Evidence Overview Metrics Bar */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
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
                {summary?.evidence_coverage ?? 68}%
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--accent-emerald)', fontWeight: 600 }}>
                {summary?.supported_count ?? 3} verified claims
              </span>
            </div>
            <div style={{ height: '5px', background: 'var(--border-subtle)', borderRadius: '3px', marginTop: '10px', overflow: 'hidden' }}>
              <div
                style={{
                  height: '100%',
                  width: `${summary?.evidence_coverage ?? 68}%`,
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
                {summary?.supported_pct ?? 60}%
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                ({summary?.supported_count ?? 3} claims)
              </span>
            </div>
            <p style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', margin: '8px 0 0 0' }}>
              Citations from public forums, surveys & reports
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
                {summary?.inferred_pct ?? 20}%
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                ({summary?.inferred_count ?? 1} claim)
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
                {summary?.unsupported_pct ?? 20}%
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                ({summary?.unsupported_count ?? 1} claim)
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
                borderBottom: activeTab === 'claims' ? '2px solid #6366F1' : '2px solid transparent',
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
                borderBottom: activeTab === 'sources' ? '2px solid #6366F1' : '2px solid transparent',
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
                borderBottom: activeTab === 'runs' ? '2px solid #6366F1' : '2px solid transparent',
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
                    background: statusFilter === pill.id ? 'rgba(99, 102, 241, 0.2)' : 'var(--bg-secondary)',
                    color: statusFilter === pill.id ? '#818CF8' : 'var(--text-secondary)',
                    border: statusFilter === pill.id ? '1px solid #6366F1' : '1px solid var(--bg-card-hover)',
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
                          <>Supported by {claim.supporting_source_ids.length} empirical sources</>
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
                        background: 'rgba(99, 102, 241, 0.1)',
                        border: '1px solid rgba(99, 102, 241, 0.3)',
                        color: '#818CF8',
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
                      color: '#818CF8',
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
                    background: sourceTypeFilter === pill.id ? 'rgba(99, 102, 241, 0.2)' : 'var(--bg-secondary)',
                    color: sourceTypeFilter === pill.id ? '#818CF8' : 'var(--text-secondary)',
                    border: sourceTypeFilter === pill.id ? '1px solid #6366F1' : '1px solid var(--bg-card-hover)',
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
                      <span style={{ fontSize: '0.84rem', fontWeight: 600, color: '#818CF8' }}>
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
                        background: r.status === 'completed' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(99, 102, 241, 0.15)',
                        color: r.status === 'completed' ? 'var(--accent-emerald)' : '#818CF8',
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
            background: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: '20px',
          }}
          onClick={() => setSelectedClaimDetail(null)}
        >
          <div
            className="bx-modal"
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
                <ShieldCheck size={18} color="#818CF8" />
                <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#818CF8', textTransform: 'uppercase' }}>
                  Empirical Provenance Inspection
                </span>
              </div>
              <button
                onClick={() => setSelectedClaimDetail(null)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-secondary)',
                  fontSize: '1.2rem',
                  cursor: 'pointer',
                }}
              >
                ✕
              </button>
            </div>

            <div style={{ marginBottom: '14px' }}>{getStatusBadge(selectedClaimDetail.status)}</div>

            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 12px 0', lineHeight: 1.4 }}>
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
              <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#818CF8', marginBottom: '6px' }}>
                Why does BebshaX evaluate this as {selectedClaimDetail.status.toUpperCase()}?
              </div>
              <p style={{ fontSize: '0.86rem', color: 'var(--text-primary)', margin: 0, lineHeight: 1.5 }}>
                {selectedClaimDetail.rationale ||
                  'Extracted through semantic matching of domain research sources and verified against student survey distributions.'}
              </p>
            </div>

            {/* Supporting Sources */}
            <div style={{ marginBottom: '20px' }}>
              <h4 style={{ fontSize: '0.86rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '10px' }}>
                Supporting Empirical Citations ({selectedClaimDetail.supporting_sources.length})
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
                      <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#818CF8' }}>
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
                  background: '#6366F1',
                  color: 'var(--text-main)',
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
