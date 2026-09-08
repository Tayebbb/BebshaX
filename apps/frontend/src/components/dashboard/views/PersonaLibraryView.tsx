import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Search,
  Sparkles,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Download,
  RefreshCw,
  X,
  ExternalLink,
  MessageSquare,
  ShieldCheck,
  User,
  Smartphone,
  CreditCard,
  Database,
  Quote,
  Target,
  AlertCircle,
  Sliders,
  Brain,
  Compass,
  Activity,
  Briefcase,
  Clock,
  Coffee,
  Globe,
  DollarSign,
} from 'lucide-react';
import { SyntheticPersona, MarketSegment, Study, PersonaGenerationRun } from '../../../types';
import { api } from '../../../services/api';
import { CountUp } from '../../../motion/CountUp';
import { EvidenceBadge, TemplateBadge, countEvidenceBacked } from '../../../utils/personaEvidence';
import { useDialogA11y } from '../../../utils/useDialogA11y';
import { PersonaMemoryPanel } from './persona/PersonaMemoryPanel';
import { EvidenceClaimPeek } from './persona/EvidenceClaimPeek';

interface PersonaLibraryViewProps {
  studyId?: string;
  onStartInterviewWithPersona?: (personaId: string, studyId?: string) => void;
  onTestBehaviorWithPersona?: (personaId: string, studyId?: string) => void;
  onNavigateToEvidence?: () => void;
  onNavigateToSegmentation?: () => void;
}

/** Per-claim provenance entry persisted by the generator in detailed_attributes.claim_provenance */
interface ClaimEntry {
  value: string;
  provenance?: string;
  evidence_ids?: string[];
}

const PROV_STYLES: Record<string, { fg: string; bg: string }> = {
  OBSERVED: { fg: 'var(--accent-emerald)', bg: 'rgba(16, 185, 129, 0.12)' },
  INFERRED: { fg: 'var(--prov-inferred)', bg: 'var(--status-warn-bg)' },
  SYNTHETIC: { fg: 'var(--text-secondary)', bg: 'var(--fill-soft-2)' },
};

export const ProvenanceChip: React.FC<{
  label?: string;
  /** Evidence claim ids behind an OBSERVED claim; with `onOpenEvidence` the chip becomes a button. */
  evidenceIds?: string[];
  onOpenEvidence?: (ids: string[]) => void;
  expanded?: boolean;
}> = ({ label, evidenceIds, onOpenEvidence, expanded }) => {
  if (!label || !PROV_STYLES[label]) return null;
  const s = PROV_STYLES[label];
  const title =
    label === 'OBSERVED'
      ? 'Cited to a retrieved evidence claim shown during generation'
      : label === 'INFERRED'
      ? 'Reasoned from business context or evidence — no direct citation'
      : 'Plausible assumption — no evidence grounding';
  const chipStyle: React.CSSProperties = {
    fontSize: '0.72rem',
    fontWeight: 700,
    letterSpacing: '0.05em',
    color: s.fg,
    background: s.bg,
    padding: '1px 6px',
    borderRadius: '4px',
    marginLeft: '6px',
    verticalAlign: 'middle',
    whiteSpace: 'nowrap',
  };
  const clickable = label === 'OBSERVED' && !!onOpenEvidence && !!evidenceIds && evidenceIds.length > 0;
  if (clickable) {
    return (
      <button
        type="button"
        onClick={() => onOpenEvidence!(evidenceIds!)}
        aria-expanded={expanded}
        title={`${title} — click to see the cited claim and its source`}
        style={{ ...chipStyle, border: `1px solid ${s.fg}`, cursor: 'pointer', font: 'inherit', fontSize: '0.72rem', fontWeight: 700 }}
      >
        {label} ↗
      </button>
    );
  }
  return (
    <span title={title} style={chipStyle}>
      {label}
    </span>
  );
};

/** Claims with provenance when the generator recorded it; plain strings otherwise. */
function claimEntries(persona: SyntheticPersona, group: 'goals' | 'needs' | 'pain_points'): ClaimEntry[] {
  const prov = (persona.detailed_attributes as Record<string, unknown> | undefined)?.claim_provenance as
    | Record<string, ClaimEntry[]>
    | undefined;
  const classed = prov?.[group];
  if (Array.isArray(classed) && classed.length > 0) return classed;
  return ((persona[group] as string[] | undefined) || []).map((v) => ({ value: v }));
}

export const PersonaLibraryView: React.FC<PersonaLibraryViewProps> = ({
  studyId,
  onStartInterviewWithPersona,
  onTestBehaviorWithPersona,
  onNavigateToEvidence,
  onNavigateToSegmentation: _onNavigateToSegmentation,
}) => {
  // Studies and active context
  const [studies, setStudies] = useState<Study[]>([]);
  const [activeStudyId, setActiveStudyId] = useState<string>(studyId || '');
  const [personas, setPersonas] = useState<SyntheticPersona[]>([]);
  const [segments, setSegments] = useState<MarketSegment[]>([]);
  const [, setRuns] = useState<PersonaGenerationRun[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Search and Filters
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedSegmentFilter, setSelectedSegmentFilter] = useState<string>('all');
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<string>('all');
  const [selectedGroundingFilter, setSelectedGroundingFilter] = useState<string>('all');
  const [selectedRunFilter] = useState<string>('all');

  // Deep Dive Inspector Modal
  const [inspectingPersona, setInspectingPersona] = useState<SyntheticPersona | null>(null);
  const [inspectorTab, setInspectorTab] = useState<'profile' | 'personality' | 'lifestyle' | 'commercial' | 'technology' | 'grounding' | 'dataset' | 'memory'>('profile');
  const [isRegenerating, setIsRegenerating] = useState<boolean>(false);
  // Which OBSERVED claim (group:index) has its evidence trace expanded.
  const [openEvidenceKey, setOpenEvidenceKey] = useState<string | null>(null);
  const inspectorModalRef = useRef<HTMLDivElement | null>(null);
  const generateModalRef = useRef<HTMLDivElement | null>(null);

  // Generation Modal & Stepper States
  const [showGenerateModal, setShowGenerateModal] = useState<boolean>(false);
  const [personasPerSegment, setPersonasPerSegment] = useState<number>(2);
  const [distributionStrategy, setDistributionStrategy] = useState<'population_weighted' | 'equal'>('population_weighted');
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Real unmount guard for post-await state writes (a `let mounted` inside a
  // click handler is never reset by React and guards nothing).
  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Dialog semantics: Escape closes (topmost surface wins), focus enters the dialog.
  useDialogA11y(inspectorModalRef, !!inspectingPersona, () => setInspectingPersona(null));
  useDialogA11y(generateModalRef, showGenerateModal, () => {
    if (!isGenerating) setShowGenerateModal(false);
  });
  useEffect(() => {
    setOpenEvidenceKey(null);
  }, [inspectingPersona?.id, inspectorTab]);

  // Load Studies on mount
  useEffect(() => {
    const loadStudies = async () => {
      try {
        const studyList = await api.getStudies();
        setStudies(studyList);
        if (!activeStudyId) {
          // Never auto-open the seeded demo: showing someone else's personas as
          // "your library" is worse than showing an explicit picker.
          const own = studyList.filter((s) => !s.is_demo);
          const mostRecent = [...own].sort(
            (a, b) =>
              new Date(b.updated_at || b.created_at || 0).getTime() -
              new Date(a.updated_at || a.created_at || 0).getTime(),
          )[0];
          if (mostRecent) setActiveStudyId(mostRecent.id);
        }
      } catch {
        // fallback
      }
    };
    loadStudies();
  }, []);

  // Update activeStudyId when prop changes
  useEffect(() => {
    if (studyId) {
      setActiveStudyId(studyId);
    }
  }, [studyId]);

  // Load personas, segments, and runs when activeStudyId changes
  const loadStudyData = async () => {
    if (!activeStudyId) {
      setPersonas([]);
      setSegments([]);
      setRuns([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const [personasRes, segmentsRes, runsRes] = await Promise.allSettled([
        api.getStudyPersonas(activeStudyId),
        api.getMarketSegments(activeStudyId),
        api.listStudyPersonaRuns(activeStudyId),
      ]);

      if (personasRes.status === 'fulfilled') {
        setPersonas(personasRes.value.personas);
      }
      if (segmentsRes.status === 'fulfilled') {
        setSegments((segmentsRes.value as MarketSegment[]) || []);
      }
      if (runsRes.status === 'fulfilled') {
        setRuns((runsRes.value as any)?.runs || []);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load synthetic personas.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (!activeStudyId) {
        setPersonas([]);
        setSegments([]);
        setRuns([]);
        setIsLoading(false);
        return;
      }
      setIsLoading(true);
      setError(null);
      try {
        const [personasRes, segmentsRes, runsRes] = await Promise.allSettled([
          api.getStudyPersonas(activeStudyId),
          api.getMarketSegments(activeStudyId),
          api.listStudyPersonaRuns(activeStudyId),
        ]);
        if (cancelled) return;
        if (personasRes.status === 'fulfilled') setPersonas(personasRes.value.personas);
        if (segmentsRes.status === 'fulfilled') setSegments((segmentsRes.value as MarketSegment[]) || []);
        if (runsRes.status === 'fulfilled') setRuns((runsRes.value as any)?.runs || []);
      } catch (err: any) {
        if (!cancelled) setError(err.message || 'Failed to load synthetic personas.');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    run();
    return () => { cancelled = true; };
  }, [activeStudyId]);

  // Filtered Personas
  const filteredPersonas = useMemo(() => {
    return personas.filter((p) => {
      if (selectedSegmentFilter !== 'all' && p.segment_id !== selectedSegmentFilter) return false;
      if (selectedStatusFilter !== 'all' && p.status !== selectedStatusFilter) return false;
      if (selectedRunFilter !== 'all' && p.generation_run_id !== selectedRunFilter) return false;
      if (selectedGroundingFilter === 'high' && p.grounding_score < 0.5) return false;
      if (selectedGroundingFilter === 'medium' && (p.grounding_score <= 0 || p.grounding_score >= 0.5)) return false;

      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesName = p.name.toLowerCase().includes(query);
        const matchesArchetype = p.archetype?.toLowerCase().includes(query) || false;
        const matchesOccupation = p.demographics?.occupation?.toLowerCase().includes(query) || false;
        const matchesBio = p.bio?.toLowerCase().includes(query) || false;
        const matchesGoals = p.goals?.some((g) => g.toLowerCase().includes(query)) || false;
        const matchesPain = p.pain_points?.some((pp) => pp.toLowerCase().includes(query)) || false;

        if (!matchesName && !matchesArchetype && !matchesOccupation && !matchesBio && !matchesGoals && !matchesPain) {
          return false;
        }
      }
      return true;
    });
  }, [personas, selectedSegmentFilter, selectedStatusFilter, selectedGroundingFilter, selectedRunFilter, searchQuery]);

  // Metrics
  const metrics = useMemo(() => {
    const total = personas.length;
    const repSegments = new Set(personas.map((p) => p.segment_id).filter(Boolean)).size;
    const evidenceBacked = countEvidenceBacked(personas);
    const readyCount = personas.filter((p) => p.status === 'ready').length;
    return { total, repSegments, evidenceBacked, readyCount };
  }, [personas]);

  // Generation Stepper Handler
  const handleTriggerGeneration = async () => {
    if (!activeStudyId) return;
    setIsGenerating(true);
    setGenerationError(null);

    try {
      const res = await api.generateSyntheticPersonas(activeStudyId, {
        personas_per_segment: personasPerSegment,
        distribution_strategy: distributionStrategy,
      });

      if (!isMountedRef.current) return;
      setIsGenerating(false);
      setShowGenerateModal(false);
      setPersonas(res.personas);
      setRuns((prev) => [res.run, ...prev]);
    } catch (err: any) {
      if (!isMountedRef.current) return;
      setIsGenerating(false);
      setGenerationError(err.message || 'Persona generation failed. Please ensure segmentation has completed.');
    }
  };

  // Regenerate Persona Handler
  const handleRegeneratePersona = async (personaId: string) => {
    if (!activeStudyId) return;
    setIsRegenerating(true);
    setActionError(null);
    try {
      const updated = await api.regenerateStudyPersona(activeStudyId, personaId);
      if (!isMountedRef.current) return;
      setPersonas((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      if (inspectingPersona && inspectingPersona.id === updated.id) {
        setInspectingPersona(updated);
      }
    } catch (err: any) {
      if (!isMountedRef.current) return;
      setActionError(`Regeneration failed: ${err.message || 'the request did not complete.'}`);
    } finally {
      if (isMountedRef.current) setIsRegenerating(false);
    }
  };

  // Export handlers
  const handleExportJSON = () => {
    const blob = new Blob([JSON.stringify(filteredPersonas, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bebshax_personas_${activeStudyId}_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportCSV = () => {
    const headers = ['ID', 'Name', 'Segment', 'Age', 'Occupation', 'Location', 'Monthly Budget', 'Grounding Score', 'Status'];
    const rows = filteredPersonas.map((p) => [
      `"${p.id}"`,
      `"${p.name}"`,
      `"${p.segment_name || p.segment_id || ''}"`,
      `"${p.demographics?.age || ''}"`,
      `"${p.demographics?.occupation || ''}"`,
      `"${p.demographics?.location || ''}"`,
      `"${p.commercial_profile?.monthly_budget_bdt || ''}"`,
      `"${(p.grounding_score * 100).toFixed(0)}%"`,
      `"${p.status}"`,
    ]);
    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bebshax_personas_${activeStudyId}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ padding: '32px clamp(16px, 4vw, 40px)', maxWidth: '1400px', margin: '0 auto', width: '100%' }}>
      {/* =========================================================================
          1. HEADER & ACTIONS
         ========================================================================= */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: 'var(--fs-2xl)', fontWeight: 700, color: 'var(--text-main)', letterSpacing: '-0.03em', margin: '0 0 6px 0' }}>
            Persona Library
          </h1>
          <p style={{ fontSize: 'var(--fs-md)', color: 'var(--text-secondary)', margin: 0 }}>
            Saved personas and audiences you can reuse in any study.
          </p>
          <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-muted)', margin: '4px 0 0 0' }}>
            Synthetic participants: findings are research hypotheses to validate with real users.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Study Context Selector — shown whenever there is something to pick */}
          {studies.length > 0 && (
            <select
              aria-label="Active study"
              value={activeStudyId}
              onChange={(e) => setActiveStudyId(e.target.value)}
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '10px',
                padding: '9px 34px 9px 14px',
                fontSize: '0.85rem',
                color: 'var(--text-primary)',
                outline: 'none',
                cursor: 'pointer',
              }}
            >
              {!activeStudyId && <option value="">Choose a study…</option>}
              {studies.map((s) => (
                <option key={s.id} value={s.id}>
                  Study: {s.title || s.id}
                  {s.is_demo ? ' — demo' : ''}
                </option>
              ))}
            </select>
          )}

          <button
            type="button"
            onClick={() => setShowGenerateModal(true)}
            disabled={!activeStudyId}
            title={activeStudyId ? undefined : 'Choose a study first — personas are generated inside one'}
            style={{
              background: 'var(--accent-gradient)',
              color: 'var(--text-on-accent)',
              border: 'none',
              borderRadius: '10px',
              padding: '9px 18px',
              fontSize: '0.86rem',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              cursor: activeStudyId ? 'pointer' : 'not-allowed',
              opacity: activeStudyId ? 1 : 0.55,
              boxShadow: '0 4px 14px var(--accent-glow)',
              transition: 'all 0.16s ease',
            }}
          >
            <Sparkles size={16} strokeWidth={2.5} />
            Generate Personas
          </button>
        </div>
      </div>

      {/* =========================================================================
          2. METRICS BANNER
         ========================================================================= */}
      {activeStudyId && (
      <dl
        className="bx-figures"
        aria-label="Library summary"
      >
        <div className="bx-figure bx-stagger" style={{ ['--bx-i' as string]: 0 }}>
          <dd><CountUp value={metrics.total} /></dd>
          <dt>Total Synthetic Personas</dt>
        </div>
        <div className="bx-figure bx-stagger" style={{ ['--bx-i' as string]: 1 }}>
          <dd><CountUp value={metrics.repSegments} /></dd>
          <dt>Represented Segments</dt>
        </div>
        <div className="bx-figure bx-stagger" style={{ ['--bx-i' as string]: 2 }}>
          <dd style={{ color: metrics.evidenceBacked > 0 ? 'var(--status-success-text)' : undefined }}>
            <CountUp value={metrics.evidenceBacked} /> <span className="bx-figure__of">of</span> <CountUp value={metrics.total} />
          </dd>
          <dt>Evidence-backed personas</dt>
        </div>
        <div className="bx-figure bx-stagger" style={{ ['--bx-i' as string]: 3 }}>
          <dd>
            <CountUp value={metrics.readyCount} /> <span className="bx-figure__of">of</span> <CountUp value={metrics.total} />
          </dd>
          <dt title="Passed the generator's structural completeness checks (all required fields present). This says nothing about evidence support.">
            Complete profiles
          </dt>
        </div>
      </dl>
      )}

      {/* =========================================================================
          3. FILTER & SEARCH BAR
         ========================================================================= */}
      {activeStudyId && (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '24px',
          flexWrap: 'wrap',
          paddingBottom: '16px',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: '220px' }}>
          <Search size={16} color="var(--text-secondary)" />
          <input
            type="text"
            placeholder="Search personas by name, occupation, goals, or pain points..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: 'var(--text-primary)',
              fontSize: '0.88rem',
              width: '100%',
            }}
          />
          {searchQuery && (
            <button type="button" onClick={() => setSearchQuery('')} aria-label="Clear search" style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <X size={14} aria-hidden="true" />
            </button>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          {/* Segment Filter */}
          <select
            value={selectedSegmentFilter}
            onChange={(e) => setSelectedSegmentFilter(e.target.value)}
            style={{
              background: 'var(--bg-card-hover)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              padding: '6px 30px 6px 12px',
              fontSize: '0.82rem',
              color: 'var(--text-primary)',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="all">All Segments ({segments.length})</option>
            {segments.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>

          {/* Status Filter */}
          <select
            value={selectedStatusFilter}
            onChange={(e) => setSelectedStatusFilter(e.target.value)}
            style={{
              background: 'var(--bg-card-hover)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              padding: '6px 30px 6px 12px',
              fontSize: '0.82rem',
              color: 'var(--text-primary)',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="all">All Statuses</option>
            <option value="ready">Complete</option>
            <option value="needs_review">Needs Review</option>
          </select>

          {/* Grounding Filter */}
          <select
            value={selectedGroundingFilter}
            onChange={(e) => setSelectedGroundingFilter(e.target.value)}
            style={{
              background: 'var(--bg-card-hover)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              padding: '6px 30px 6px 12px',
              fontSize: '0.82rem',
              color: 'var(--text-primary)',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="all">All Grounding Levels</option>
            <option value="high">Majority Observed (≥50%)</option>
            <option value="medium">Some Observed Evidence (&gt;0%)</option>
          </select>

          {/* Export Actions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', borderLeft: '1px solid var(--border-subtle)', paddingLeft: '10px' }}>
            <button
              type="button"
              onClick={handleExportJSON}
              disabled={filteredPersonas.length === 0}
              title="Export filtered personas as JSON"
              style={{
                background: 'var(--bg-card-hover)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                padding: '6px 10px',
                fontSize: '0.78rem',
                color: 'var(--text-secondary)',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                cursor: filteredPersonas.length > 0 ? 'pointer' : 'not-allowed',
              }}
            >
              <Download size={13} /> JSON
            </button>
            <button
              type="button"
              onClick={handleExportCSV}
              disabled={filteredPersonas.length === 0}
              title="Export filtered personas as CSV"
              style={{
                background: 'var(--bg-card-hover)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                padding: '6px 10px',
                fontSize: '0.78rem',
                color: 'var(--text-secondary)',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                cursor: filteredPersonas.length > 0 ? 'pointer' : 'not-allowed',
              }}
            >
              <Download size={13} /> CSV
            </button>
          </div>
        </div>
      </div>
      )}

      {/* =========================================================================
          4. PERSONA CARDS GRID / SKELETON / EMPTY STATE
         ========================================================================= */}
      {actionError && (
        <div
          role="alert"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.4)',
            borderRadius: '12px',
            padding: '12px 16px',
            marginBottom: '16px',
            color: 'var(--status-error-text)',
            fontSize: '0.85rem',
          }}
        >
          <span>{actionError}</span>
          <button
            type="button"
            onClick={() => setActionError(null)}
            aria-label="Dismiss error"
            style={{ background: 'none', border: 'none', color: 'var(--status-error-text)', cursor: 'pointer', fontWeight: 700 }}
          >
            ×
          </button>
        </div>
      )}

      {!activeStudyId ? (
        <div style={{ background: 'var(--bg-secondary)', border: '1px dashed var(--border-subtle)', borderRadius: '18px', padding: '48px 24px', textAlign: 'center' }}>
          <div style={{ width: '56px', height: '56px', borderRadius: '50%', background: 'var(--accent-subtle)', border: '1px solid var(--accent-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', color: 'var(--accent-teal)' }}>
            <Layers size={26} />
          </div>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', margin: '0 0 8px 0' }}>
            Pick a study
          </h3>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', maxWidth: '480px', margin: '0 auto', lineHeight: 1.5 }}>
            {studies.length > 0
              ? 'Personas belong to a study. Choose one above to see its library.'
              : 'You have no studies yet. Start a study first — personas are generated inside one.'}
          </p>
        </div>
      ) : isLoading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(340px, 100%), 1fr))', gap: '20px' }}>
          {[1, 2, 3, 4, 5, 6].map((idx) => (
            <div key={idx} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '16px', padding: '24px', height: '320px', animation: 'pulse 1.5s infinite' }}>
              <div style={{ height: '48px', width: '48px', borderRadius: '50%', background: 'var(--bg-card-hover)', marginBottom: '16px' }} />
              <div style={{ height: '20px', width: '60%', background: 'var(--bg-card-hover)', borderRadius: '6px', marginBottom: '10px' }} />
              <div style={{ height: '14px', width: '80%', background: 'var(--bg-card-hover)', borderRadius: '4px', marginBottom: '18px' }} />
              <div style={{ height: '60px', width: '100%', background: 'var(--bg-card-hover)', borderRadius: '8px' }} />
            </div>
          ))}
        </div>
      ) : error ? (
        <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.25)', borderRadius: '16px', padding: '32px', textAlign: 'center' }}>
          <AlertTriangle size={32} color="#EF4444" style={{ margin: '0 auto 12px' }} />
          <h3 style={{ fontSize: '1.1rem', color: 'var(--text-primary)', margin: '0 0 6px 0' }}>Failed to Load Personas</h3>
          <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', margin: '0 0 16px 0' }}>{error}</p>
          <button type="button" onClick={loadStudyData} style={{ background: '#14B8A6', color: 'var(--text-on-accent)', border: 'none', borderRadius: '8px', padding: '8px 16px', fontWeight: 600, cursor: 'pointer' }}>
            Retry
          </button>
        </div>
      ) : filteredPersonas.length === 0 ? (
        <div style={{ background: 'var(--bg-secondary)', border: '1px dashed var(--border-subtle)', borderRadius: '18px', padding: '48px 24px', textAlign: 'center' }}>
          <div style={{ width: '56px', height: '56px', borderRadius: '50%', background: 'var(--accent-subtle)', border: '1px solid var(--accent-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', color: 'var(--accent-teal)' }}>
            <Sparkles size={26} />
          </div>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', margin: '0 0 8px 0' }}>
            {personas.length === 0 ? 'No Synthetic Personas Generated Yet' : 'No Personas Match Your Filter'}
          </h3>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', maxWidth: '480px', margin: '0 auto 20px', lineHeight: 1.5 }}>
            {personas.length === 0
              ? 'Generate synthetic consumer simulation agents from your study market segments, pricing quartiles, and any research claims you have collected.'
              : 'Try clearing your search query or adjusting segment and status filters to see available personas.'}
          </p>
          {personas.length === 0 ? (
            <button
              type="button"
              onClick={() => setShowGenerateModal(true)}
              style={{
                background: 'var(--accent-gradient)',
                color: 'var(--text-on-accent)',
                border: 'none',
                borderRadius: '10px',
                padding: '10px 22px',
                fontSize: '0.9rem',
                fontWeight: 600,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                cursor: 'pointer',
              }}
            >
              <Sparkles size={16} />
              Generate Personas for Study
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                setSearchQuery('');
                setSelectedSegmentFilter('all');
                setSelectedStatusFilter('all');
                setSelectedGroundingFilter('all');
              }}
              style={{
                background: 'var(--bg-card-hover)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-primary)',
                borderRadius: '8px',
                padding: '8px 16px',
                fontSize: '0.85rem',
                cursor: 'pointer',
              }}
            >
              Clear All Filters
            </button>
          )}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(320px, 100%), 1fr))', gap: '20px' }}>
          {filteredPersonas.map((persona, cardIdx) => {
            const initials = persona.name
              .split(' ')
              .map((n) => n[0])
              .join('')
              .toUpperCase()
              .slice(0, 2);
            const isReady = persona.status === 'ready';

            return (
              <article
                key={persona.id}
                className="bx-stagger bx-lift"
                aria-label={`${persona.name} persona`}
                style={{
                  ['--bx-i' as string]: Math.min(cardIdx, 12),
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '16px',
                  padding: '22px',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '16px',
                  position: 'relative',
                }}
              >
                {/* Card Header: Avatar, Name, Badges */}
                <div>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '10px', marginBottom: '14px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      {/* Geometric Gradient Avatar */}
                      <div
                        style={{
                          width: '44px',
                          height: '44px',
                          borderRadius: '12px',
                          background: 'linear-gradient(135deg, var(--border-hover) 0%, rgba(34, 211, 238, 0.15) 100%)',
                          border: '1px solid var(--border-hover)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '0.95rem',
                          fontWeight: 700,
                          color: 'var(--accent-cyan)',
                          letterSpacing: '0.04em',
                          flexShrink: 0,
                        }}
                      >
                        {initials}
                      </div>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                            {persona.name}
                          </h3>
                          {persona.version > 1 && (
                            <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', padding: '1px 5px', borderRadius: '4px' }}>
                              v{persona.version}
                            </span>
                          )}
                          {persona.data_source === 'cached' && (
                            <span
                              title="Served from seeded/cached data — not generated live for this study"
                              style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', border: '1px solid var(--border-medium)', padding: '1px 6px', borderRadius: '4px', fontFamily: 'var(--font-mono)', letterSpacing: '0.06em' }}
                            >
                              CACHED
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                          {persona.demographics?.age ? `${persona.demographics.age} yo • ` : ''}
                          {persona.demographics?.occupation || persona.archetype || 'Occupation not stated'}
                        </div>
                        <TemplateBadge persona={persona} />
                      </div>
                    </div>

                    {/* Status Badge */}
                    <span
                      title={
                        isReady
                          ? "Passed the generator's structural completeness checks — every required field is present. Evidence support is shown separately."
                          : 'The generator flagged missing or inconsistent fields on this profile.'
                      }
                      style={{
                        fontSize: '0.72rem',
                        fontWeight: 600,
                        padding: '3px 8px',
                        borderRadius: '6px',
                        background: isReady ? 'var(--status-success-bg)' : 'var(--status-warn-bg)',
                        color: isReady ? 'var(--status-success-text)' : 'var(--status-warn-text)',
                        border: `1px solid ${isReady ? 'var(--status-success-border)' : 'var(--status-warn-border)'}`,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {isReady ? 'Complete' : 'Needs Review'}
                    </span>
                  </div>

                  {/* Tagline / Evocative Archetype */}
                  {persona.tagline && (
                    <p style={{ fontSize: '0.92rem', fontWeight: 500, fontStyle: 'italic', color: 'var(--text-primary)', margin: '0 0 10px 0', lineHeight: 1.4 }}>
                      {persona.tagline}
                    </p>
                  )}

                  {/* Segment & Synthetic Tag */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '10px' }}>
                    {persona.segment_name && (
                      <span style={{ fontSize: '0.75rem', fontWeight: 500, padding: '2px 8px', borderRadius: '6px', background: 'rgba(34, 211, 238, 0.1)', color: 'var(--accent-cyan)', border: '1px solid rgba(34, 211, 238, 0.2)' }}>
                        {persona.segment_name}
                      </span>
                    )}
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', padding: '2px 7px', borderRadius: '5px', border: '1px solid var(--border-subtle)' }}>
                      Synthetic Persona
                    </span>
                    {persona.origin_country && (
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', padding: '2px 7px', borderRadius: '5px', border: '1px solid var(--border-subtle)' }}>
                        {persona.origin_country}
                      </span>
                    )}
                  </div>

                  {/* Big Five Personality Micro Bars */}
                  {persona.personality && (
                    <div style={{ padding: '10px 0 12px', marginBottom: '4px', borderTop: '1px solid var(--border-subtle)' }}>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 500, marginBottom: '8px' }}>
                        Personality (Big Five)
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '6px', textAlign: 'center' }}>
                        {[
                          { label: 'O', name: 'Openness', val: persona.personality.openness, color: 'var(--trait-o)' },
                          { label: 'C', name: 'Conscientiousness', val: persona.personality.conscientiousness, color: 'var(--trait-c)' },
                          { label: 'E', name: 'Extroversion', val: persona.personality.extroversion, color: 'var(--trait-e)' },
                          { label: 'A', name: 'Agreeableness', val: persona.personality.agreeableness, color: 'var(--trait-a)' },
                          { label: 'N', name: 'Neuroticism', val: persona.personality.neuroticism, color: 'var(--trait-n)' },
                        ].map((trait) => (
                          <div key={trait.label} title={`${trait.name}: ${trait.val}/100`} role="img" aria-label={`${trait.name} ${trait.val} out of 100`}>
                            <div style={{ fontSize: '0.72rem', fontWeight: 600, color: trait.color }}>{trait.val}</div>
                            <div style={{ height: '3px', background: 'var(--border-subtle)', borderRadius: '2px', overflow: 'hidden', margin: '2px 0' }}>
                              <div style={{ width: `${trait.val}%`, height: '100%', background: trait.color }} />
                            </div>
                            <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>{trait.label}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Bio or Quote preview */}
                  <p style={{ fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.45, margin: '0 0 12px 0', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {persona.quote ? `"${persona.quote}"` : persona.bio}
                  </p>

                  {/* Goal and Pain Point Pills */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '14px' }}>
                    {persona.goals?.[0] && (
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <Target size={12} color="var(--accent-teal)" style={{ flexShrink: 0 }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{persona.goals[0]}</span>
                      </div>
                    )}
                    {persona.pain_points?.[0] && (
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <AlertCircle size={12} color="var(--accent-amber)" style={{ flexShrink: 0 }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{persona.pain_points[0]}</span>
                      </div>
                    )}
                    {persona.detailed_attributes?.work_schedule && (
                      <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <Clock size={11} color="var(--accent-cyan)" style={{ flexShrink: 0 }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{persona.detailed_attributes.work_schedule}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Card Footer: Commercial budget, Grounding score meter, Deep Dive Button */}
                <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', flexWrap: 'wrap', marginBottom: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      <CreditCard size={13} color="var(--accent-teal)" />
                      <span>
                        {persona.commercial_profile?.monthly_budget_bdt
                          ? `৳${persona.commercial_profile.monthly_budget_bdt}/mo`
                          : 'Budget not stated'}
                      </span>
                    </div>

                    <EvidenceBadge persona={persona} />
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <button
                      type="button"
                      onClick={() => {
                        setInspectingPersona(persona);
                        setInspectorTab('profile');
                      }}
                      style={{
                        flex: 1,
                        background: 'var(--bg-card-hover)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: '8px',
                        padding: '7px 12px',
                        fontSize: '0.82rem',
                        fontWeight: 600,
                        color: 'var(--text-primary)',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                        transition: 'all 0.16s ease',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = 'var(--accent-subtle)';
                        e.currentTarget.style.borderColor = 'var(--border-hover)';
                        e.currentTarget.style.color = 'var(--accent-teal)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'var(--bg-card-hover)';
                        e.currentTarget.style.borderColor = 'var(--border-subtle)';
                        e.currentTarget.style.color = 'var(--text-primary)';
                      }}
                    >
                      Open profile
                    </button>

                    {onStartInterviewWithPersona && (
                      <button
                        type="button"
                        onClick={() => onStartInterviewWithPersona(persona.id, activeStudyId || undefined)}
                        aria-label={`Start an interview with ${persona.name}`}
                        title={`Start an adaptive interview with ${persona.name}`}
                        style={{
                          background: 'rgba(34, 211, 238, 0.1)',
                          border: '1px solid rgba(34, 211, 238, 0.25)',
                          borderRadius: '8px',
                          padding: '7px 10px',
                          color: 'var(--accent-cyan)',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        <MessageSquare size={14} />
                      </button>
                    )}

                    {onTestBehaviorWithPersona && (
                      <button
                        type="button"
                        onClick={() => onTestBehaviorWithPersona(persona.id, activeStudyId || undefined)}
                        aria-label={`Run a behavioral test with ${persona.name}`}
                        title={`Simulate a behavioral scenario with ${persona.name}`}
                        style={{
                          background: 'var(--accent-subtle)',
                          border: '1px solid var(--accent-glow)',
                          borderRadius: '8px',
                          padding: '7px 10px',
                          color: 'var(--accent-teal)',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        <Sliders size={14} />
                      </button>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* =========================================================================
          5. DEEP DIVE PERSONA INSPECTOR MODAL (5 TABS)
         ========================================================================= */}
      {inspectingPersona && (
        <div
          className="bx-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'var(--scrim)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            zIndex: 100,
          }}
          onClick={() => setInspectingPersona(null)}
        >
          <div
            ref={inspectorModalRef}
            className="bx-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="persona-inspector-title"
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '20px',
              maxWidth: '900px',
              width: '100%',
              maxHeight: '90vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: 'var(--shadow-lg)',
              overflow: 'hidden',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div style={{ padding: '24px 28px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <div
                  style={{
                    width: '54px',
                    height: '54px',
                    borderRadius: '16px',
                    background: 'linear-gradient(135deg, var(--border-hover) 0%, rgba(34, 211, 238, 0.15) 100%)',
                    border: '1px solid var(--border-hover)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '1.2rem',
                    fontWeight: 700,
                    color: 'var(--accent-cyan)',
                  }}
                >
                  {inspectingPersona.name.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <h2 id="persona-inspector-title" style={{ fontSize: '1.35rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                      {inspectingPersona.name}
                    </h2>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', padding: '2px 6px', borderRadius: '4px' }}>
                      v{inspectingPersona.version}
                    </span>
                    <span style={{ fontSize: '0.72rem', fontWeight: 600, padding: '2px 8px', borderRadius: '6px', background: inspectingPersona.status === 'ready' ? 'var(--status-success-bg)' : 'var(--status-warn-bg)', color: inspectingPersona.status === 'ready' ? 'var(--status-success-text)' : 'var(--status-warn-text)', border: `1px solid ${inspectingPersona.status === 'ready' ? 'var(--status-success-border)' : 'var(--status-warn-border)'}` }}>
                      {inspectingPersona.status === 'ready' ? 'Complete' : 'Needs Review'}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '3px' }}>
                    {inspectingPersona.demographics?.age} yo • {inspectingPersona.demographics?.occupation} • {inspectingPersona.demographics?.location}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => handleRegeneratePersona(inspectingPersona.id)}
                  disabled={isRegenerating}
                  style={{
                    background: 'var(--bg-card-hover)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '8px',
                    padding: '6px 12px',
                    fontSize: '0.8rem',
                    color: 'var(--text-secondary)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <RefreshCw size={13} className={isRegenerating ? 'animate-spin' : ''} />
                  {isRegenerating ? 'Regenerating...' : 'Regenerate'}
                </button>
                <button
                  type="button"
                  onClick={() => setInspectingPersona(null)}
                  aria-label="Close persona details"
                  style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', padding: '6px' }}
                >
                  <X size={18} aria-hidden="true" />
                </button>
              </div>
            </div>

            {/* Modal Tabs Bar */}
            <div style={{ display: 'flex', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', padding: '0 28px', background: 'var(--bg-pure)', overflowX: 'auto' }}>
              {[
                { id: 'profile', label: 'Persona Profile', icon: <User size={14} /> },
                { id: 'personality', label: 'Personality (Big Five)', icon: <Brain size={14} /> },
                { id: 'lifestyle', label: 'Lifestyle & Routine', icon: <Activity size={14} /> },
                { id: 'commercial', label: 'Commercial & WTP', icon: <CreditCard size={14} /> },
                { id: 'technology', label: 'Technology Profile', icon: <Smartphone size={14} /> },
                { id: 'grounding', label: `Evidence Citations (${inspectingPersona.evidence_citations?.length || 0})`, icon: <ShieldCheck size={14} /> },
                { id: 'dataset', label: 'Dataset Provenance', icon: <Database size={14} /> },
                { id: 'memory', label: 'Memory', icon: <Brain size={14} /> },
              ].map((t) => {
                const isActive = inspectorTab === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setInspectorTab(t.id as any)}
                    style={{
                      background: 'none',
                      border: 'none',
                      borderBottom: isActive ? '2px solid var(--accent-teal)' : '2px solid transparent',
                      padding: '12px 16px',
                      fontSize: '0.84rem',
                      fontWeight: isActive ? 600 : 500,
                      color: isActive ? 'var(--accent-teal)' : 'var(--text-secondary)',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '7px',
                      whiteSpace: 'nowrap',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {t.icon}
                    {t.label}
                  </button>
                );
              })}
            </div>

            {/* Modal Tab Body */}
            <div style={{ padding: '24px 28px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* TAB 1: PROFILE */}
              {inspectorTab === 'profile' && (
                <>
                  {/* Tagline & Identity overview */}
                  {inspectingPersona.tagline && (
                    <div style={{ background: 'rgba(34, 211, 238, 0.08)', border: '1px solid rgba(34, 211, 238, 0.25)', borderRadius: '12px', padding: '14px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div>
                        <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--accent-cyan)', fontWeight: 700, letterSpacing: '0.05em' }}>Archetype Tagline</div>
                        <div style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', marginTop: '2px' }}>{inspectingPersona.tagline}</div>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {inspectingPersona.data_source === 'cached' && (
                          <span
                            title="Served from seeded/cached data — not generated live for this study"
                            style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', border: '1px solid var(--border-medium)', padding: '3px 8px', borderRadius: '6px', fontFamily: 'var(--font-mono)', letterSpacing: '0.06em' }}
                          >
                            CACHED
                          </span>
                        )}
                        {(inspectingPersona.country_code || inspectingPersona.origin_country) && (
                          <span style={{ fontSize: '0.78rem', color: 'var(--accent-teal)', background: 'var(--accent-subtle)', border: '1px solid var(--accent-glow)', padding: '3px 10px', borderRadius: '6px', fontWeight: 600 }}>
                            {[inspectingPersona.country_code, inspectingPersona.origin_country].filter(Boolean).join(' • ')}
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Bio & Quote */}
                  <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--accent-teal)', fontSize: '0.8rem', fontWeight: 600, marginBottom: '6px' }}>
                      <Quote size={14} /> Consumer Bio & Direct Perspective
                    </div>
                    <p style={{ fontSize: '0.9rem', color: 'var(--text-primary)', lineHeight: 1.55, margin: '0 0 10px 0' }}>
                      {inspectingPersona.bio}
                    </p>
                    {inspectingPersona.quote && (
                      <div style={{ fontStyle: 'italic', color: 'var(--accent-cyan)', fontSize: '0.86rem', borderLeft: '2px solid var(--accent-cyan)', paddingLeft: '10px' }}>
                        "{inspectingPersona.quote}"
                      </div>
                    )}
                  </div>

                  {/* Goals & Needs Grid */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(260px, 100%), 1fr))', gap: '16px' }}>
                    <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--accent-emerald)', fontSize: '0.82rem', fontWeight: 600, marginBottom: '10px' }}>
                        <Target size={14} /> Core Goals
                      </div>
                      <ul style={{ margin: 0, paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.84rem', color: 'var(--text-primary)' }}>
                        {claimEntries(inspectingPersona, 'goals').map((e, idx) => (
                          <li key={idx}>
                            {e.value}
                            <ProvenanceChip
                              label={e.provenance}
                              evidenceIds={e.evidence_ids}
                              expanded={openEvidenceKey === `goals:${idx}`}
                              onOpenEvidence={activeStudyId ? () => setOpenEvidenceKey((k) => (k === `goals:${idx}` ? null : `goals:${idx}`)) : undefined}
                            />
                            {openEvidenceKey === `goals:${idx}` && activeStudyId && e.evidence_ids && (
                              <EvidenceClaimPeek studyId={activeStudyId} evidenceIds={e.evidence_ids} onClose={() => setOpenEvidenceKey(null)} />
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--accent-cyan)', fontSize: '0.82rem', fontWeight: 600, marginBottom: '10px' }}>
                        <CheckCircle2 size={14} /> Needs
                      </div>
                      <ul style={{ margin: 0, paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.84rem', color: 'var(--text-primary)' }}>
                        {claimEntries(inspectingPersona, 'needs').map((e, idx) => (
                          <li key={idx}>
                            {e.value}
                            <ProvenanceChip
                              label={e.provenance}
                              evidenceIds={e.evidence_ids}
                              expanded={openEvidenceKey === `needs:${idx}`}
                              onOpenEvidence={activeStudyId ? () => setOpenEvidenceKey((k) => (k === `needs:${idx}` ? null : `needs:${idx}`)) : undefined}
                            />
                            {openEvidenceKey === `needs:${idx}` && activeStudyId && e.evidence_ids && (
                              <EvidenceClaimPeek studyId={activeStudyId} evidenceIds={e.evidence_ids} onClose={() => setOpenEvidenceKey(null)} />
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {/* Pain Points & Objections Grid */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(260px, 100%), 1fr))', gap: '16px' }}>
                    <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--status-warn-text)', fontSize: '0.82rem', fontWeight: 600, marginBottom: '10px' }}>
                        <AlertCircle size={14} /> Pain Points & Anxieties
                      </div>
                      <ul style={{ margin: 0, paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.84rem', color: 'var(--text-primary)' }}>
                        {claimEntries(inspectingPersona, 'pain_points').map((e, idx) => (
                          <li key={idx}>
                            {e.value}
                            <ProvenanceChip
                              label={e.provenance}
                              evidenceIds={e.evidence_ids}
                              expanded={openEvidenceKey === `pain_points:${idx}`}
                              onOpenEvidence={activeStudyId ? () => setOpenEvidenceKey((k) => (k === `pain_points:${idx}` ? null : `pain_points:${idx}`)) : undefined}
                            />
                            {openEvidenceKey === `pain_points:${idx}` && activeStudyId && e.evidence_ids && (
                              <EvidenceClaimPeek studyId={activeStudyId} evidenceIds={e.evidence_ids} onClose={() => setOpenEvidenceKey(null)} />
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#EF4444', fontSize: '0.82rem', fontWeight: 600, marginBottom: '10px' }}>
                        <AlertTriangle size={14} /> Buying Objections
                      </div>
                      <ul style={{ margin: 0, paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.84rem', color: 'var(--text-primary)' }}>
                        {inspectingPersona.objections?.map((obj, idx) => (
                          <li key={idx}>{obj}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </>
              )}

              {/* TAB: PERSONALITY (BIG FIVE) */}
              {inspectorTab === 'personality' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                  <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '14px', padding: '20px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                      <div>
                        <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Brain size={18} color="var(--accent-teal)" /> Big Five Trait Spectrum
                        </h4>
                        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: '4px 0 0 0' }}>
                          Quantified psychometric scale (0–100) governing simulation conversational tone, risk tolerance, and decision pace.
                        </p>
                      </div>
                      <span style={{ fontSize: '0.75rem', background: 'var(--accent-subtle)', color: 'var(--accent-teal)', padding: '4px 10px', borderRadius: '6px', fontWeight: 600 }}>
                        OCEAN Psychometrics
                      </span>
                    </div>

                    {inspectingPersona.personality ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {[
                          {
                            key: 'openness',
                            name: 'Openness to Experience',
                            val: inspectingPersona.personality.openness ?? null,
                            desc: 'Curiosity, imagination, and receptivity to novel ideas vs preference for routine and convention.',
                            color: 'var(--trait-o)',
                          },
                          {
                            key: 'conscientiousness',
                            name: 'Conscientiousness',
                            val: inspectingPersona.personality.conscientiousness ?? null,
                            desc: 'Self-discipline, organization, diligence, and goal-oriented planning.',
                            color: 'var(--accent-emerald)',
                          },
                          {
                            key: 'extroversion',
                            name: 'Extroversion',
                            val: inspectingPersona.personality.extroversion ?? null,
                            desc: 'Outgoing energy, social engagement, assertiveness, and enthusiasm.',
                            color: 'var(--trait-e)',
                          },
                          {
                            key: 'agreeableness',
                            name: 'Agreeableness',
                            val: inspectingPersona.personality.agreeableness ?? null,
                            desc: 'Cooperativeness, empathy, consideration, and trust in social interactions.',
                            color: 'var(--trait-a)',
                          },
                          {
                            key: 'neuroticism',
                            name: 'Neuroticism (Emotional Sensitivity)',
                            val: inspectingPersona.personality.neuroticism ?? null,
                            desc: 'Sensitivity to stress, vulnerability to anxiety, and reactivity to disruption.',
                            color: 'var(--trait-n)',
                          },
                        ].map((trait) => (
                          <div key={trait.key} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '10px', padding: '14px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                              <div style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)' }}>{trait.name}</div>
                              {typeof trait.val === 'number' ? (
                                <div style={{ fontSize: '0.95rem', fontWeight: 700, color: trait.color }}>{trait.val} / 100</div>
                              ) : (
                                <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', fontStyle: 'italic' }}>Not measured</div>
                              )}
                            </div>
                            {typeof trait.val === 'number' && (
                              <div style={{ height: '7px', background: 'var(--border-subtle)', borderRadius: '4px', overflow: 'hidden', marginBottom: '8px' }}>
                                <div style={{ width: `${Math.max(0, Math.min(100, trait.val))}%`, height: '100%', background: `linear-gradient(90deg, ${trait.color}99, ${trait.color})`, borderRadius: '4px' }} />
                              </div>
                            )}
                            <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.4 }}>{trait.desc}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '24px' }}>
                        No psychometric score data recorded for this persona.
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* TAB: LIFESTYLE & ROUTINE (45+ DETAILED ATTRIBUTES) */}
              {inspectorTab === 'lifestyle' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    Granular behavioral context comprising daily habits, coping strategies, cultural affiliations, and operational realities.
                  </div>

                  {inspectingPersona.detailed_attributes ? (
                    <>
                      {/* Section 1: Work & Daily Schedule */}
                      <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '18px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--trait-o)', fontSize: '0.88rem', fontWeight: 600, marginBottom: '14px' }}>
                          <Briefcase size={16} /> Work, Commute & Schedule Context
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: '12px' }}>
                          {[
                            { key: 'work_schedule', label: 'Work Schedule' },
                            { key: 'workplace_setting', label: 'Workplace Setting' },
                            { key: 'commute_mode', label: 'Commute Mode' },
                            { key: 'work_ethic', label: 'Work Ethic' },
                            { key: 'schedule_flexibility', label: 'Schedule Flexibility' },
                            { key: 'time_management', label: 'Time Management' },
                            { key: 'daily_activities', label: 'Daily Activities' },
                          ].map(({ key, label }) => (
                            inspectingPersona.detailed_attributes?.[key] ? (
                              <div key={key} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '10px 12px' }}>
                                <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '3px' }}>{label}</div>
                                <div style={{ fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.4 }}>{inspectingPersona.detailed_attributes[key]}</div>
                              </div>
                            ) : null
                          ))}
                        </div>
                      </div>

                      {/* Section 2: Living & Sustenance */}
                      <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '18px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-emerald)', fontSize: '0.88rem', fontWeight: 600, marginBottom: '14px' }}>
                          <Coffee size={16} /> Living, Meals & Household Structure
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: '12px' }}>
                          {[
                            { key: 'food_source', label: 'Food Source' },
                            { key: 'meal_timing', label: 'Meal Timing' },
                            { key: 'sleep_schedule', label: 'Sleep Schedule' },
                            { key: 'urban_living', label: 'Urban Living Realities' },
                            { key: 'household_structure', label: 'Household Structure' },
                            { key: 'family_dynamics', label: 'Family Dynamics' },
                            { key: 'hobbies', label: 'Hobbies & Interests' },
                          ].map(({ key, label }) => (
                            inspectingPersona.detailed_attributes?.[key] ? (
                              <div key={key} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '10px 12px' }}>
                                <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '3px' }}>{label}</div>
                                <div style={{ fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.4 }}>{inspectingPersona.detailed_attributes[key]}</div>
                              </div>
                            ) : null
                          ))}
                        </div>
                      </div>

                      {/* Section 3: Mindset, Psychology & Communication */}
                      <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '18px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--trait-e)', fontSize: '0.88rem', fontWeight: 600, marginBottom: '14px' }}>
                          <Compass size={16} /> Mindset, Psychology & Communication Style
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: '12px' }}>
                          {[
                            { key: 'communication_style', label: 'Communication Style' },
                            { key: 'activity_level', label: 'Activity Level' },
                            { key: 'adaptability_level', label: 'Adaptability Level' },
                            { key: 'anxiety_level', label: 'Anxiety & Pressure Response' },
                            { key: 'attention_focus', label: 'Attention Focus' },
                            { key: 'coping_strategies', label: 'Coping Strategies' },
                            { key: 'decision_style', label: 'Decision Style' },
                            { key: 'introversion_level', label: 'Introversion Level' },
                            { key: 'growth_mindset', label: 'Growth Mindset' },
                            { key: 'self_discipline', label: 'Self Discipline' },
                            { key: 'learning_style', label: 'Learning Style' },
                          ].map(({ key, label }) => (
                            inspectingPersona.detailed_attributes?.[key] ? (
                              <div key={key} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '10px 12px' }}>
                                <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '3px' }}>{label}</div>
                                <div style={{ fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.4 }}>{inspectingPersona.detailed_attributes[key]}</div>
                              </div>
                            ) : null
                          ))}
                        </div>
                      </div>

                      {/* Section 4: Culture, Beliefs & Social Values */}
                      <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '18px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--trait-a)', fontSize: '0.88rem', fontWeight: 600, marginBottom: '14px' }}>
                          <Globe size={16} /> Culture, Beliefs & Life Priorities
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: '12px' }}>
                          {[
                            { key: 'language_preferences', label: 'Language Preferences' },
                            { key: 'cultural_affiliations', label: 'Cultural Affiliations' },
                            { key: 'cultural_traditions', label: 'Cultural Traditions' },
                            { key: 'belief_system', label: 'Belief System' },
                            { key: 'religious_practices', label: 'Religious Practices' },
                            { key: 'spiritual_outlook', label: 'Spiritual Outlook' },
                            { key: 'social_identity', label: 'Social Identity' },
                            { key: 'social_values', label: 'Social Values' },
                            { key: 'personal_values', label: 'Personal Values' },
                            { key: 'life_priorities', label: 'Life Priorities' },
                            { key: 'core_motivators', label: 'Core Motivators' },
                            { key: 'motivation_goals', label: 'Motivation Goals' },
                            { key: 'personal_independence', label: 'Personal Independence' },
                            { key: 'community_engagement', label: 'Community Engagement' },
                          ].map(({ key, label }) => (
                            inspectingPersona.detailed_attributes?.[key] ? (
                              <div key={key} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '10px 12px' }}>
                                <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '3px' }}>{label}</div>
                                <div style={{ fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.4 }}>{inspectingPersona.detailed_attributes[key]}</div>
                              </div>
                            ) : null
                          ))}
                        </div>
                      </div>

                      {/* Section 5: Finance & Technology */}
                      <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '18px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--trait-n)', fontSize: '0.88rem', fontWeight: 600, marginBottom: '14px' }}>
                          <DollarSign size={16} /> Financial Mindset & Technology Adoption
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: '12px' }}>
                          {[
                            { key: 'payment_method', label: 'Preferred Payment Method' },
                            { key: 'financial_attitude', label: 'Financial Attitude' },
                            { key: 'financial_profile', label: 'Financial Profile' },
                            { key: 'planning_horizon', label: 'Planning Horizon' },
                            { key: 'general_risk', label: 'General Risk Tolerance' },
                            { key: 'value_risk', label: 'Value & Experimentation Risk' },
                            { key: 'tech_interest', label: 'Tech Interest' },
                            { key: 'technology_usage', label: 'Technology Usage' },
                          ].map(({ key, label }) => (
                            inspectingPersona.detailed_attributes?.[key] ? (
                              <div key={key} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '10px 12px' }}>
                                <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '3px' }}>{label}</div>
                                <div style={{ fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.4 }}>{inspectingPersona.detailed_attributes[key]}</div>
                              </div>
                            ) : null
                          ))}
                        </div>
                      </div>
                    </>
                  ) : (
                    <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '24px' }}>
                      No detailed lifestyle attributes recorded for this persona.
                    </div>
                  )}
                </div>
              )}

              {/* TAB 2: COMMERCIAL & WTP */}
              {inspectorTab === 'commercial' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 200px), 1fr))', gap: '14px' }}>
                    <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>Estimated Monthly Budget</div>
                      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--accent-teal)' }}>
                        {inspectingPersona.commercial_profile?.monthly_budget_bdt
                          ? `৳${inspectingPersona.commercial_profile.monthly_budget_bdt} / mo`
                          : 'Not stated'}
                      </div>
                    </div>

                    <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>Price Sensitivity</div>
                      <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {inspectingPersona.commercial_profile?.price_sensitivity || 'Not stated'}
                      </div>
                    </div>

                    <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>Payment Preference</div>
                      <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--accent-cyan)' }}>
                        {inspectingPersona.commercial_profile?.payment_preference || 'Not stated'}
                      </div>
                    </div>
                  </div>

                  <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                    <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px' }}>Willingness-to-Pay Range</div>
                    <p style={{ fontSize: '0.86rem', color: 'var(--text-primary)', margin: 0 }}>
                      {inspectingPersona.commercial_profile?.willingness_to_pay || 'Not stated'}
                    </p>
                  </div>
                </div>
              )}

              {/* TAB 3: TECHNOLOGY PROFILE */}
              {inspectorTab === 'technology' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                    <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '10px' }}>Primary Devices</div>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      {inspectingPersona.technology_profile?.primary_devices?.map((d, idx) => (
                        <span key={idx} style={{ background: 'var(--border-subtle)', color: 'var(--accent-cyan)', padding: '4px 10px', borderRadius: '6px', fontSize: '0.8rem', border: '1px solid rgba(34, 211, 238, 0.2)' }}>
                          {d}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                    <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '10px' }}>Frequently Used Platforms</div>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      {inspectingPersona.technology_profile?.platforms?.map((p, idx) => (
                        <span key={idx} style={{ background: 'var(--border-subtle)', color: 'var(--accent-teal)', padding: '4px 10px', borderRadius: '6px', fontSize: '0.8rem', border: '1px solid var(--accent-glow)' }}>
                          {p}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 4: EVIDENCE CITATIONS */}
              {inspectorTab === 'grounding' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
                    Claims this persona cites from the study's evidence runs. Personas without citations are labeled
                    INFERRED/SYNTHETIC in the profile tab — absence of evidence is shown, never papered over.
                  </div>

                  {inspectingPersona.evidence_citations && inspectingPersona.evidence_citations.length > 0 ? (
                    inspectingPersona.evidence_citations.map((c, idx) => (
                      <div key={idx} style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--accent-teal)', textTransform: 'uppercase' }}>
                            {c.category || 'General Finding'}
                          </span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                            Confidence: {c.confidence ? `${Math.round(c.confidence * 100)}%` : 'n/a'}
                          </span>
                        </div>
                        <p style={{ fontSize: '0.88rem', color: 'var(--text-primary)', margin: 0, lineHeight: 1.45 }}>
                          "{c.claim_text}"
                        </p>
                      </div>
                    ))
                  ) : (
                    <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      No direct claim citations recorded for this persona.
                    </div>
                  )}

                  {onNavigateToEvidence && (
                    <button
                      type="button"
                      onClick={onNavigateToEvidence}
                      style={{
                        alignSelf: 'flex-start',
                        background: 'none',
                        border: 'none',
                        color: 'var(--accent-teal)',
                        fontSize: '0.82rem',
                        fontWeight: 600,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        cursor: 'pointer',
                        padding: 0,
                        marginTop: '6px',
                      }}
                    >
                      View in Evidence Laboratory <ExternalLink size={12} />
                    </button>
                  )}
                </div>
              )}

              {/* TAB 5: DATASET PROVENANCE */}
              {inspectorTab === 'dataset' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
                    Dataset distributions that constrained demographic and commercial boundaries.
                  </div>

                  <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                    <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '10px' }}>Variable Constraints</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {inspectingPersona.dataset_refs?.map((ref, idx) => (
                        <div key={idx} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '0.82rem' }}>
                          <span style={{ color: 'var(--text-secondary)' }}>{ref.variable}</span>
                          <span style={{ color: 'var(--accent-teal)', fontWeight: 600 }}>{String(ref.value)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB: MEMORY (what the persona has remembered across interviews) */}
              {inspectorTab === 'memory' && <PersonaMemoryPanel personaId={inspectingPersona.id} />}
            </div>

            {/* Modal Footer */}
            <div style={{ padding: '16px 28px', borderTop: '1px solid var(--border-subtle)', background: 'var(--bg-pure)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                Persona ID: <code style={{ color: 'var(--accent-teal)' }}>{inspectingPersona.id}</code>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {onStartInterviewWithPersona && (
                  <button
                    type="button"
                    onClick={() => {
                      onStartInterviewWithPersona(inspectingPersona.id, activeStudyId || undefined);
                      setInspectingPersona(null);
                    }}
                    style={{
                      background: 'var(--accent-gradient)',
                      color: 'var(--text-on-accent)',
                      border: 'none',
                      borderRadius: '8px',
                      padding: '8px 16px',
                      fontSize: '0.84rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <MessageSquare size={14} /> Start Adaptive Interview
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setInspectingPersona(null)}
                  style={{
                    background: 'var(--bg-card-hover)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-primary)',
                    borderRadius: '8px',
                    padding: '8px 16px',
                    fontSize: '0.84rem',
                    cursor: 'pointer',
                  }}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          6. GENERATE PERSONAS MODAL WITH REAL-TIME STEPPER
         ========================================================================= */}
      {showGenerateModal && (
        <div
          className="bx-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'var(--scrim)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            zIndex: 100,
          }}
          onClick={() => !isGenerating && setShowGenerateModal(false)}
        >
          <div
            ref={generateModalRef}
            className="bx-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="generate-personas-title"
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '20px',
              maxWidth: '560px',
              width: '100%',
              padding: '28px',
              boxShadow: 'var(--shadow-lg)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '20px' }}>
              <div>
                <h2 id="generate-personas-title" style={{ fontSize: '1.35rem', fontWeight: 600, color: 'var(--text-primary)', margin: '0 0 4px 0' }}>
                  Generate Synthetic Personas
                </h2>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: 0 }}>
                  Synthesize simulation agents across market segments.
                </p>
              </div>
              {!isGenerating && (
                <button type="button" onClick={() => setShowGenerateModal(false)} aria-label="Close generate personas dialog" style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  <X size={18} aria-hidden="true" />
                </button>
              )}
            </div>

            {generationError && (
              <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.25)', borderRadius: '10px', padding: '12px 14px', color: '#EF4444', fontSize: '0.84rem', marginBottom: '18px' }}>
                {generationError}
              </div>
            )}

            {!isGenerating ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                {/* Personas per segment */}
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px' }}>
                    Personas per Market Segment: {personasPerSegment}
                  </label>
                  <input
                    type="range"
                    min="1"
                    max="6"
                    value={personasPerSegment}
                    onChange={(e) => setPersonasPerSegment(Number(e.target.value))}
                    style={{ width: '100%', accentColor: '#14B8A6', cursor: 'pointer' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    <span>1 Persona</span>
                    <span>3 Personas</span>
                    <span>6 Personas</span>
                  </div>
                </div>

                {/* Distribution Strategy */}
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px' }}>
                    Quota Allocation Strategy
                  </label>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(220px, 100%), 1fr))', gap: '10px' }}>
                    <div
                      onClick={() => setDistributionStrategy('population_weighted')}
                      style={{
                        background: distributionStrategy === 'population_weighted' ? 'var(--accent-subtle)' : 'var(--bg-card-hover)',
                        border: `1px solid ${distributionStrategy === 'population_weighted' ? 'var(--accent-teal)' : 'var(--border-subtle)'}`,
                        borderRadius: '10px',
                        padding: '12px',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <div style={{ fontSize: '0.84rem', fontWeight: 600, color: distributionStrategy === 'population_weighted' ? 'var(--accent-teal)' : 'var(--text-primary)', marginBottom: '2px' }}>
                        Population-Weighted
                      </div>
                      <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                        Allocates personas proportionally by segment market share.
                      </div>
                    </div>

                    <div
                      onClick={() => setDistributionStrategy('equal')}
                      style={{
                        background: distributionStrategy === 'equal' ? 'var(--accent-subtle)' : 'var(--bg-card-hover)',
                        border: `1px solid ${distributionStrategy === 'equal' ? 'var(--accent-teal)' : 'var(--border-subtle)'}`,
                        borderRadius: '10px',
                        padding: '12px',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <div style={{ fontSize: '0.84rem', fontWeight: 600, color: distributionStrategy === 'equal' ? 'var(--accent-teal)' : 'var(--text-primary)', marginBottom: '2px' }}>
                        Equal Distribution
                      </div>
                      <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                        Generates equal number of personas for each segment.
                      </div>
                    </div>
                  </div>
                </div>

                {/* Submit button */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '12px' }}>
                  <button
                    type="button"
                    onClick={() => setShowGenerateModal(false)}
                    style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)', borderRadius: '8px', padding: '9px 16px', fontSize: '0.84rem', cursor: 'pointer' }}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleTriggerGeneration}
                    style={{
                      background: 'var(--accent-gradient)',
                      color: 'var(--text-on-accent)',
                      border: 'none',
                      borderRadius: '8px',
                      padding: '9px 18px',
                      fontSize: '0.86rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <Sparkles size={15} />
                    Synthesize Personas
                  </button>
                </div>
              </div>
            ) : (
              /* HONEST INDETERMINATE LOADING — no fake step timers */
              <div style={{ padding: '24px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px' }}>
                <div
                  style={{
                    width: '36px',
                    height: '36px',
                    border: '3px solid var(--accent-glow)',
                    borderTopColor: 'var(--accent-teal)',
                    borderRadius: '50%',
                    animation: 'authSpin 0.7s linear infinite',
                  }}
                />
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '4px' }}>
                    Generating personas…
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    This may take up to a minute on free providers
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
