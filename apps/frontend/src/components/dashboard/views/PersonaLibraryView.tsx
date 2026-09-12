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
import { SyntheticPersona, MarketSegment, Study } from '../../../types';
import { api } from '../../../services/api';
import { serializeCsv } from '../../../utils/exports';
import { datasetRefFields, datasetRefTitle, formatDatasetRefValue } from '../../../utils/datasetRefs';
import { useRequestScope } from '../../../utils/useRequestScope';
import { useRouteReady } from '../../../performance/routeTiming';
import { CountUp } from '../../../motion/CountUp';
import { EvidenceBadge, TemplateBadge, countEvidenceBacked } from '../../../utils/personaEvidence';
import { useDialogA11y } from '../../../utils/useDialogA11y';
import { PersonaMemoryPanel } from './persona/PersonaMemoryPanel';
import { EvidenceClaimPeek } from './persona/EvidenceClaimPeek';
import { Button } from '../../ui/Button';

interface PersonaLibraryViewProps {
  studyId?: string;
  onStartInterviewWithPersona?: (personaId: string, studyId?: string) => void;
  onTestBehaviorWithPersona?: (personaId: string, studyId?: string) => void;
  onNavigateToEvidence?: (studyId: string) => void;
  onNavigateToSegmentation?: () => void;
}

/** Per-claim provenance entry persisted by the generator in detailed_attributes.claim_provenance */
interface ClaimEntry {
  value: string;
  provenance?: string;
  evidence_ids?: string[];
}

const PROV_STYLES: Record<string, { fg: string; bg: string }> = {
  OBSERVED: { fg: 'var(--status-success-text)', bg: 'var(--status-success-bg)' },
  INFERRED: { fg: 'var(--status-warn-text)', bg: 'var(--status-warn-bg)' },
  SYNTHETIC: { fg: 'var(--text-muted)', bg: 'var(--bg-card)' },
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
    letterSpacing: 0,
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

function isMeasuredTraitScore(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100;
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
  const loadEpoch = useRef(0);
  const activeStudyRef = useRef(activeStudyId);
  activeStudyRef.current = activeStudyId;
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [studiesLoading, setStudiesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const scopeRef = useRequestScope([activeStudyId]);
  const mutationPendingRef = useRef(false);
  useRouteReady(!isLoading && !studiesLoading, error ? 'error' : personas.length ? 'content' : 'empty');

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
  const generateFocusRef = useRef<HTMLElement | null>(null);

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
  }, { initialFocus: generateFocusRef });
  useEffect(() => {
    if (!showGenerateModal) return;
    generateFocusRef.current = generateModalRef.current?.querySelector<HTMLElement>(
      '[role="alert"], [role="status"], input[type="range"]',
    ) ?? null;
    generateFocusRef.current?.focus();
  }, [showGenerateModal, isGenerating, generationError]);
  useEffect(() => {
    setOpenEvidenceKey(null);
  }, [inspectingPersona?.id, inspectorTab]);

  // Load Studies on mount
  useEffect(() => {
    let current = true;
    const loadStudies = async () => {
      try {
        const studyList = await api.getStudies();
        if (!current) return;
        setStudies(studyList);
        if (!activeStudyRef.current) {
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
        if (current) setError('Studies could not be loaded.');
      } finally {
        if (current) setStudiesLoading(false);
      }
    };
    void loadStudies();
    return () => { current = false; };
  }, []);

  // Update activeStudyId when prop changes
  useEffect(() => {
    mutationPendingRef.current = false;
    if (studyId) {
      setActiveStudyId(studyId);
    }
  }, [studyId]);

  // Load personas, segments, and runs when activeStudyId changes
  const loadStudyData = async () => {
    if (activeStudyRef.current !== activeStudyId) return;
    const epoch = ++loadEpoch.current;
    const isCurrent = () => isMountedRef.current && loadEpoch.current === epoch;
    setPersonas([]);
    setSegments([]);
    setInspectingPersona(null);
    setError(null);
    setActionError(null);
    if (!activeStudyId) {
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    try {
      const [personasRes, segmentsRes] = await Promise.allSettled([
        api.getStudyPersonas(activeStudyId).then((result) => {
          if (isCurrent()) { setPersonas(result.personas); setIsLoading(false); }
          return result;
        }).catch((failure: unknown) => {
          if (isCurrent()) { setError('Personas could not be loaded.'); setIsLoading(false); }
          throw failure;
        }),
        api.getMarketSegments(activeStudyId).then((result) => {
          if (isCurrent()) setSegments(result);
          return result;
        }),
      ]);
      if (!isCurrent()) return;
      setPersonas(personasRes.status === 'fulfilled' ? personasRes.value.personas : []);
      setSegments(segmentsRes.status === 'fulfilled' ? segmentsRes.value : []);
      if (personasRes.status === 'rejected') setError('Personas could not be loaded.');
      if (segmentsRes.status === 'rejected') setActionError('Segments could not be loaded.');
    } catch {
      if (isCurrent()) setError('Personas could not be loaded.');
    } finally {
      if (isCurrent()) setIsLoading(false);
    }
  };

  useEffect(() => {
    setIsGenerating(false);
    mutationPendingRef.current = false;
    setIsRegenerating(false);
    setShowGenerateModal(false);
    void loadStudyData();
    return () => { loadEpoch.current += 1; };
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
    const scope = scopeRef.current;
    if (!activeStudyId || isLoading || !scope.active || mutationPendingRef.current) return;
    mutationPendingRef.current = true;
    loadEpoch.current += 1;
    setIsGenerating(true);
    setGenerationError(null);

    try {
      const res = await api.generateSyntheticPersonas(activeStudyId, {
        personas_per_segment: personasPerSegment,
        distribution_strategy: distributionStrategy,
      });

      if (!scope.active) return;
      setIsGenerating(false);
      setShowGenerateModal(false);
      setPersonas(res.personas);
      setIsLoading(false);
      setError(null);
    } catch (err: any) {
      if (!scope.active) return;
      setIsGenerating(false);
      setGenerationError(err.message || 'Persona generation failed. Please ensure segmentation has completed.');
    } finally {
      if (scope.active) mutationPendingRef.current = false;
    }
  };

  // Regenerate Persona Handler
  const handleRegeneratePersona = async (personaId: string) => {
    const scope = scopeRef.current;
    if (!activeStudyId || !scope.active || mutationPendingRef.current) return;
    mutationPendingRef.current = true;
    loadEpoch.current += 1;
    setIsRegenerating(true);
    setActionError(null);
    try {
      const updated = await api.regenerateStudyPersona(activeStudyId, personaId);
      if (!scope.active) return;
      setPersonas((current) => {
        if (!scope.active || activeStudyRef.current !== activeStudyId) return current;
        return current.map((entry) => (entry.id === updated.id ? updated : entry));
      });
      setInspectingPersona((current) =>
        scope.active && activeStudyRef.current === activeStudyId && current?.id === updated.id
          ? updated
          : current,
      );
    } catch (err: any) {
      if (!scope.active) return;
      setActionError(`Regeneration failed: ${err.message || 'the request did not complete.'}`);
    } finally {
      if (scope.active) { mutationPendingRef.current = false; setIsRegenerating(false); }
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
      p.id,
      p.name,
      p.segment_name || p.segment_id || '',
      p.demographics?.age ?? '',
      p.demographics?.occupation ?? '',
      p.demographics?.location ?? '',
      p.commercial_profile?.monthly_budget_bdt ?? '',
      `${(p.grounding_score * 100).toFixed(0)}%`,
      p.status,
    ]);
    const csvContent = serializeCsv([headers, ...rows]);
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bebshax_personas_${activeStudyId}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ padding: '1.5rem clamp(1rem, 4vw, 2.5rem)', maxWidth: '1400px', margin: '0 auto', width: '100%', minWidth: 0, overflowWrap: 'anywhere', letterSpacing: 0 }}>
      {/* =========================================================================
          1. HEADER & ACTIONS
         ========================================================================= */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px', marginBottom: '24px' }}>
        <div style={{ minWidth: 0, flex: '1 1 20rem' }}>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--text-main)', letterSpacing: 0, margin: '0 0 0.5rem' }}>
            Persona Library
          </h1>
          <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-muted)', margin: '4px 0 0 0' }}>
            Synthetic participants: findings are research hypotheses to validate with real users.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', minWidth: 0, maxWidth: '100%' }}>
          {/* Study Context Selector — shown whenever there is something to pick */}
          {studies.length > 0 && (
            <select
              aria-label="Active study"
              value={activeStudyId}
              onChange={(e) => setActiveStudyId(e.target.value)}
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                padding: '9px 34px 9px 14px',
                fontSize: '0.85rem',
                color: 'var(--text-main)',
                outlineOffset: '2px',
                minWidth: 0,
                maxWidth: '100%',
                minHeight: '2.5rem',
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

          <Button
            type="button"
            variant="primary"
            onClick={() => setShowGenerateModal(true)}
            disabled={!activeStudyId || isLoading}
            title={activeStudyId ? undefined : 'Choose a study first — personas are generated inside one'}
            style={{ minHeight: '2.5rem', whiteSpace: 'normal' }}
          >
            <Sparkles size={16} aria-hidden="true" />
            Generate Personas
          </Button>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: '1 1 16rem', minWidth: 0 }}>
          <Search size={16} color="var(--text-secondary)" />
          <input
            type="search"
            aria-label="Search personas"
            placeholder="Search personas by name, occupation, goals, or pain points..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              background: 'transparent',
              border: 'none',
              outlineOffset: '2px',
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

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', minWidth: 0, maxWidth: '100%' }}>
          {/* Segment Filter */}
          <select
            aria-label="Filter by segment"
            value={selectedSegmentFilter}
            onChange={(e) => setSelectedSegmentFilter(e.target.value)}
            style={{
              background: 'var(--bg-card-hover)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              padding: '6px 30px 6px 12px',
              fontSize: '0.82rem',
              color: 'var(--text-primary)',
              outlineOffset: '2px',
              minWidth: 0,
              maxWidth: '100%',
              minHeight: '2.25rem',
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
            aria-label="Filter by status"
            value={selectedStatusFilter}
            onChange={(e) => setSelectedStatusFilter(e.target.value)}
            style={{
              background: 'var(--bg-card-hover)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              padding: '6px 30px 6px 12px',
              fontSize: '0.82rem',
              color: 'var(--text-primary)',
              outlineOffset: '2px',
              minWidth: 0,
              maxWidth: '100%',
              minHeight: '2.25rem',
              cursor: 'pointer',
            }}
          >
            <option value="all">All Statuses</option>
            <option value="ready">Complete</option>
            <option value="needs_review">Needs Review</option>
          </select>

          {/* Grounding Filter */}
          <select
            aria-label="Filter by evidence grounding"
            value={selectedGroundingFilter}
            onChange={(e) => setSelectedGroundingFilter(e.target.value)}
            style={{
              background: 'var(--bg-card-hover)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              padding: '6px 30px 6px 12px',
              fontSize: '0.82rem',
              color: 'var(--text-primary)',
              outlineOffset: '2px',
              minWidth: 0,
              maxWidth: '100%',
              minHeight: '2.25rem',
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
      {actionError && !inspectingPersona && (
        <div
          role="alert"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            background: 'var(--bg-pure)',
            border: '1px solid var(--status-error-border)',
            borderRadius: '8px',
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
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      )}

      {!activeStudyId ? (
        <div style={{ padding: '2rem 0', textAlign: 'center', minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem', color: 'var(--text-muted)' }}>
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
            <div key={idx} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '24px', height: '320px', animation: 'pulse 1.5s infinite', minWidth: 0 }}>
              <div style={{ height: '48px', width: '48px', borderRadius: '50%', background: 'var(--bg-card-hover)', marginBottom: '16px' }} />
              <div style={{ height: '20px', width: '60%', background: 'var(--bg-card-hover)', borderRadius: '6px', marginBottom: '10px' }} />
              <div style={{ height: '14px', width: '80%', background: 'var(--bg-card-hover)', borderRadius: '4px', marginBottom: '18px' }} />
              <div style={{ height: '60px', width: '100%', background: 'var(--bg-card-hover)', borderRadius: '8px' }} />
            </div>
          ))}
        </div>
      ) : error ? (
        <div role="alert" style={{ background: 'var(--bg-pure)', border: '1px solid var(--status-error-border)', borderRadius: '8px', padding: '1.5rem', textAlign: 'center', color: 'var(--status-error-text)' }}>
          <AlertTriangle size={24} aria-hidden="true" style={{ margin: '0 auto 0.75rem' }} />
          <h3 style={{ fontSize: '1rem', color: 'var(--status-error-text)', margin: '0 0 0.5rem' }}>Failed to Load Personas</h3>
          <p style={{ fontSize: '0.875rem', margin: '0 0 1rem' }}>{error}</p>
          <Button type="button" variant="secondary" onClick={loadStudyData}>
            <RefreshCw size={16} aria-hidden="true" /> Retry
          </Button>
        </div>
      ) : filteredPersonas.length === 0 ? (
        <div role="status" style={{ padding: '2rem 0', textAlign: 'center', minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem', color: 'var(--text-muted)' }}>
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
            <Button
              type="button"
              variant="primary"
              onClick={() => setShowGenerateModal(true)}
            >
              <Sparkles size={16} aria-hidden="true" />
              Generate Personas for Study
            </Button>
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
                className="bx-stagger"
                aria-label={`${persona.name} persona`}
                style={{
                  ['--bx-i' as string]: Math.min(cardIdx, 12),
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '8px',
                  padding: '1rem',
                  minWidth: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '16px',
                  position: 'relative',
                }}
              >
                {/* Card Header: Avatar, Name, Badges */}
                <div>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap', minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0, flex: '1 1 12rem' }}>
                      <div
                        style={{
                          width: '44px',
                          height: '44px',
                          borderRadius: '8px',
                          background: 'var(--bg-card-hover)',
                          border: '1px solid var(--border-subtle)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '0.95rem',
                          fontWeight: 700,
                          color: 'var(--text-main)',
                          letterSpacing: 0,
                          flexShrink: 0,
                        }}
                      >
                        {initials}
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', minWidth: 0 }}>
                          <h2 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', margin: 0, overflowWrap: 'anywhere' }}>
                            {persona.name}
                          </h2>
                          {persona.version > 1 && (
                            <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', padding: '1px 5px', borderRadius: '4px' }}>
                              v{persona.version}
                            </span>
                          )}
                          {persona.data_source === 'cached' && (
                            <span
                              title="Served from seeded/cached data — not generated live for this study"
                              style={{ fontSize: '0.72rem', color: 'var(--text-muted)', background: 'var(--bg-card-hover)', border: '1px solid var(--border-medium)', padding: '1px 6px', borderRadius: '4px', fontFamily: 'var(--font-mono)', letterSpacing: 0 }}
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
                      <span style={{ fontSize: '0.75rem', fontWeight: 500, padding: '2px 8px', borderRadius: '6px', background: 'var(--bg-card-hover)', color: 'var(--text-main)', border: '1px solid var(--border-subtle)' }}>
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
                        ].map((trait) => {
                          const measured = isMeasuredTraitScore(trait.val);
                          return (
                            <div key={trait.label} title={measured ? `${trait.name}: ${trait.val}/100` : `${trait.name}: Not measured`} role={measured ? 'img' : undefined} aria-label={measured ? `${trait.name} ${trait.val} out of 100` : undefined} style={{ minWidth: 0 }}>
                              <div style={{ fontSize: '0.72rem', fontWeight: 600, color: measured ? 'var(--text-main)' : 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>{measured ? trait.val : 'Not measured'}</div>
                              <div style={{ height: '3px', background: 'var(--border-subtle)', borderRadius: '2px', overflow: 'hidden', margin: '2px 0' }}>
                                {measured && <div style={{ width: `${trait.val}%`, height: '100%', background: trait.color }} />}
                              </div>
                              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{trait.label}</div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Bio or Quote preview */}
                  <p style={{ fontSize: '0.875rem', color: 'var(--text-primary)', lineHeight: 1.5, margin: '0 0 0.75rem', overflowWrap: 'anywhere' }}>
                    {persona.quote ? `"${persona.quote}"` : persona.bio}
                  </p>

                  {/* Goal and Pain Point Pills */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '14px' }}>
                    {persona.goals?.map((goal, index) => (
                      <div key={index} style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'flex-start', gap: '0.375rem', minWidth: 0 }}>
                        <Target size={14} aria-hidden="true" style={{ flexShrink: 0 }} />
                        <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>{goal}</span>
                      </div>
                    ))}
                    {persona.pain_points?.map((painPoint, index) => (
                      <div key={index} style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'flex-start', gap: '0.375rem', minWidth: 0 }}>
                        <AlertCircle size={14} aria-hidden="true" style={{ flexShrink: 0 }} />
                        <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>{painPoint}</span>
                      </div>
                    ))}
                    {persona.detailed_attributes?.work_schedule && (
                      <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'flex-start', gap: '0.375rem', minWidth: 0 }}>
                        <Clock size={14} aria-hidden="true" style={{ flexShrink: 0 }} />
                        <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>{persona.detailed_attributes.work_schedule}</span>
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
                        {typeof persona.commercial_profile?.monthly_budget_bdt === 'number'
                          ? `৳${persona.commercial_profile.monthly_budget_bdt}/mo`
                          : 'Budget not stated'}
                      </span>
                    </div>

                    <EvidenceBadge persona={persona} />
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => {
                        setInspectingPersona(persona);
                        setInspectorTab('profile');
                      }}
                      style={{ flex: 1, minWidth: 0, minHeight: '2.25rem', whiteSpace: 'normal' }}
                    >
                      <User size={14} aria-hidden="true" />
                      Open profile
                    </Button>

                    {onStartInterviewWithPersona && (
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => onStartInterviewWithPersona(persona.id, activeStudyId || undefined)}
                        aria-label={`Start an interview with ${persona.name}`}
                        title={`Start an adaptive interview with ${persona.name}`}
                        style={{ width: '2.25rem', height: '2.25rem', flexShrink: 0, padding: 0 }}
                      >
                        <MessageSquare size={14} aria-hidden="true" />
                      </Button>
                    )}

                    {onTestBehaviorWithPersona && (
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => onTestBehaviorWithPersona(persona.id, activeStudyId || undefined)}
                        aria-label={`Run a behavioral test with ${persona.name}`}
                        title={`Simulate a behavioral scenario with ${persona.name}`}
                        style={{ width: '2.25rem', height: '2.25rem', flexShrink: 0, padding: 0 }}
                      >
                        <Sliders size={14} aria-hidden="true" />
                      </Button>
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
            padding: '1rem',
            zIndex: 100,
          }}
          onClick={() => setInspectingPersona(null)}
        >
          <div
            ref={inspectorModalRef}
            className="bx-modal"
            role="dialog"
            tabIndex={-1}
            aria-modal="true"
            aria-labelledby="persona-inspector-title"
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '12px',
              maxWidth: '56.25rem',
              width: '100%',
              minWidth: 0,
              maxHeight: 'calc(100dvh - 2rem)',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: 'var(--shadow-lg)',
              overflowY: 'auto',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <header style={{ padding: '1rem', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', minWidth: 0, flexShrink: 0 }}>
              <div style={{ flex: '1 1 18rem', minWidth: 0 }}>
                <h2 id="persona-inspector-title" style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0, overflowWrap: 'anywhere', letterSpacing: 0 }}>
                  {inspectingPersona.name}
                </h2>
                <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginTop: '0.25rem', overflowWrap: 'anywhere' }}>
                  {inspectingPersona.demographics?.age} yo • {inspectingPersona.demographics?.occupation} • {inspectingPersona.demographics?.location}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  <span>Synthetic Persona</span>
                  <span>v{inspectingPersona.version}</span>
                  <span style={{ fontWeight: 600, padding: '2px 8px', borderRadius: '4px', background: inspectingPersona.status === 'ready' ? 'var(--status-success-bg)' : 'var(--status-warn-bg)', color: inspectingPersona.status === 'ready' ? 'var(--status-success-text)' : 'var(--status-warn-text)', border: `1px solid ${inspectingPersona.status === 'ready' ? 'var(--status-success-border)' : 'var(--status-warn-border)'}` }}>
                    {inspectingPersona.status === 'ready' ? 'Complete' : 'Needs Review'}
                  </span>
                  {inspectingPersona.data_source === 'cached' && (
                    <span title="Served from seeded/cached data - not generated live for this study" style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-medium)', padding: '2px 8px', borderRadius: '4px', fontFamily: 'var(--font-mono)', letterSpacing: 0 }}>
                      CACHED
                    </span>
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', minWidth: 0 }}>
                <Button
                  size="sm"
                  onClick={() => handleRegeneratePersona(inspectingPersona.id)}
                  loading={isRegenerating}
                  leadingIcon={<RefreshCw size={14} aria-hidden="true" />}
                >
                  {isRegenerating ? 'Regenerating...' : 'Regenerate'}
                </Button>
                <Button
                  variant="ghost"
                  icon
                  onClick={() => setInspectingPersona(null)}
                  aria-label="Close persona details"
                  title="Close persona details"
                >
                  <X size={18} aria-hidden="true" />
                  <span className="sr-only">Close</span>
                </Button>
              </div>
            </header>

            {actionError && (
              <div role="alert" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem', padding: '0.75rem 1rem', background: 'var(--bg-pure)', color: 'var(--status-error-text)', borderBottom: '1px solid var(--status-error-border)', fontSize: '0.875rem', overflowWrap: 'anywhere' }}>
                <span style={{ minWidth: 0, flex: '1 1 12rem' }}>{actionError}</span>
                <Button variant="ghost" icon onClick={() => setActionError(null)} aria-label="Dismiss error" title="Dismiss error">
                  <X size={16} aria-hidden="true" />
                </Button>
              </div>
            )}

            {/* Modal Tabs Bar */}
            <div
              role="tablist"
              aria-label="Persona details"
              onKeyDown={(event) => {
                const tabs = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
                const currentIndex = tabs.indexOf(event.target as HTMLButtonElement);
                if (currentIndex < 0) return;
                let nextIndex: number;
                switch (event.key) {
                  case 'ArrowRight':
                  case 'ArrowDown':
                    nextIndex = (currentIndex + 1) % tabs.length;
                    break;
                  case 'ArrowLeft':
                  case 'ArrowUp':
                    nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
                    break;
                  case 'Home':
                    nextIndex = 0;
                    break;
                  case 'End':
                    nextIndex = tabs.length - 1;
                    break;
                  default:
                    return;
                }
                event.preventDefault();
                tabs[nextIndex].focus();
                tabs[nextIndex].click();
              }}
              style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(9rem, 100%), 1fr))', gap: '0.25rem', borderBottom: '1px solid var(--border-subtle)', padding: '0.75rem 1rem', background: 'var(--bg-pure)', minWidth: 0, flexShrink: 0 }}
            >
              {([
                { id: 'profile', label: 'Persona Profile', icon: <User size={14} /> },
                { id: 'personality', label: 'Personality (Big Five)', icon: <Brain size={14} /> },
                { id: 'lifestyle', label: 'Lifestyle & Routine', icon: <Activity size={14} /> },
                { id: 'commercial', label: 'Commercial & WTP', icon: <CreditCard size={14} /> },
                { id: 'technology', label: 'Technology Profile', icon: <Smartphone size={14} /> },
                { id: 'grounding', label: `Evidence Citations (${inspectingPersona.evidence_citations?.length || 0})`, icon: <ShieldCheck size={14} /> },
                { id: 'dataset', label: 'Dataset Provenance', icon: <Database size={14} /> },
                { id: 'memory', label: 'Memory', icon: <Brain size={14} /> },
              ] as const).map((tab) => {
                const isActive = inspectorTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    id={`persona-tab-${tab.id}`}
                    aria-selected={isActive}
                    aria-controls="persona-inspector-panel"
                    tabIndex={isActive ? 0 : -1}
                    onClick={() => setInspectorTab(tab.id)}
                    style={{
                      background: isActive ? 'var(--bg-card-hover)' : 'transparent',
                      border: '1px solid transparent',
                      borderBottom: isActive ? '2px solid var(--text-primary)' : '2px solid transparent',
                      borderRadius: '4px',
                      padding: '0.625rem 0.5rem',
                      fontSize: '0.8125rem',
                      fontWeight: isActive ? 600 : 500,
                      color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.375rem',
                      minWidth: 0,
                      minHeight: '2.75rem',
                      whiteSpace: 'normal',
                      textAlign: 'left',
                      letterSpacing: 0,
                      outlineOffset: '2px',
                    }}
                  >
                    <span aria-hidden="true" style={{ display: 'flex', flexShrink: 0 }}>{tab.icon}</span>
                    <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>{tab.label}</span>
                  </button>
                );
              })}
            </div>

            {/* Modal Tab Body */}
            <div role="tabpanel" id="persona-inspector-panel" aria-labelledby={`persona-tab-${inspectorTab}`} tabIndex={0} style={{ padding: '1rem', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '1.25rem', minWidth: 0, minHeight: '8rem', overflowWrap: 'anywhere' }}>
              {/* TAB 1: PROFILE */}
              {inspectorTab === 'profile' && (
                <>
                  <section aria-labelledby="persona-identity-heading" style={{ minWidth: 0 }}>
                    <h3 id="persona-identity-heading" style={{ fontSize: '1rem', color: 'var(--text-primary)', margin: '0 0 0.75rem' }}>Identity</h3>
                    <dl style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(12rem, 100%), 1fr))', gap: '0.75rem', margin: 0 }}>
                      {[
                        { label: 'Age', value: inspectingPersona.demographics?.age },
                        { label: 'Gender', value: inspectingPersona.demographics?.gender },
                        { label: 'Occupation', value: inspectingPersona.demographics?.occupation },
                        { label: 'Location', value: inspectingPersona.demographics?.location },
                        { label: 'Education', value: inspectingPersona.demographics?.education },
                        { label: 'Income or budget', value: inspectingPersona.demographics?.income_or_budget },
                        { label: 'Archetype', value: inspectingPersona.archetype },
                        { label: 'Origin country', value: inspectingPersona.origin_country },
                        { label: 'Country code', value: inspectingPersona.country_code },
                      ].map((field) => (
                        <div key={field.label} style={{ minWidth: 0 }}>
                          <dt style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>{field.label}</dt>
                          <dd style={{ color: 'var(--text-primary)', fontSize: '0.875rem', margin: '0.25rem 0 0', overflowWrap: 'anywhere' }}>{field.value ?? 'Not stated'}</dd>
                        </div>
                      ))}
                    </dl>
                  </section>
                  {inspectingPersona.validation_warnings.length > 0 && (
                    <section aria-labelledby="persona-warnings-heading" style={{ minWidth: 0, borderLeft: '2px solid var(--status-warn-border)', paddingLeft: '0.75rem' }}>
                      <h3 id="persona-warnings-heading" style={{ fontSize: '1rem', color: 'var(--status-warn-text)', margin: '0 0 0.5rem' }}>Validation warnings</h3>
                      <ul style={{ margin: 0, paddingLeft: '1.25rem', color: 'var(--text-primary)', fontSize: '0.875rem' }}>
                        {inspectingPersona.validation_warnings.map((warning, index) => <li key={index}>{warning}</li>)}
                      </ul>
                    </section>
                  )}
                  {/* Tagline & Identity overview */}
                  {inspectingPersona.tagline && (
                    <section aria-labelledby="persona-tagline-heading" style={{ minWidth: 0, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
                      <div style={{ minWidth: 0 }}>
                        <h3 id="persona-tagline-heading" style={{ fontSize: '1rem', color: 'var(--text-main)', fontWeight: 600, margin: '0 0 0.5rem' }}>Archetype Tagline</h3>
                        <p style={{ fontSize: '0.875rem', color: 'var(--text-main)', margin: 0 }}>{inspectingPersona.tagline}</p>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
                        {(inspectingPersona.country_code || inspectingPersona.origin_country) && (
                          <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                            {[inspectingPersona.country_code, inspectingPersona.origin_country].filter(Boolean).join(' • ')}
                          </span>
                        )}
                      </div>
                    </section>
                  )}

                  {/* Bio & Quote */}
                  <section aria-labelledby="persona-bio-heading" style={{ minWidth: 0 }}>
                    <h3 id="persona-bio-heading" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-main)', fontSize: '1rem', fontWeight: 600, margin: '0 0 0.75rem' }}>
                      <Quote size={16} aria-hidden="true" style={{ flexShrink: 0 }} /> Consumer Bio & Direct Perspective
                    </h3>
                    <p style={{ fontSize: '0.9rem', color: 'var(--text-primary)', lineHeight: 1.55, margin: '0 0 10px 0' }}>
                      {inspectingPersona.bio}
                    </p>
                    {inspectingPersona.quote && (
                      <blockquote style={{ fontStyle: 'italic', color: 'var(--text-main)', fontSize: '0.875rem', borderLeft: '1px solid var(--border-subtle)', paddingLeft: '0.75rem', margin: 0, whiteSpace: 'pre-wrap' }}>
                        "{inspectingPersona.quote}"
                      </blockquote>
                    )}
                  </section>

                  {/* Goals & Needs Grid */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(260px, 100%), 1fr))', gap: '16px' }}>
                    <section aria-labelledby="persona-goals-heading" style={{ minWidth: 0 }}>
                      <h3 id="persona-goals-heading" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-main)', fontSize: '1rem', fontWeight: 600, margin: '0 0 0.75rem' }}>
                        <Target size={16} aria-hidden="true" style={{ flexShrink: 0 }} /> Core Goals
                      </h3>
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
                    </section>

                    <section aria-labelledby="persona-needs-heading" style={{ minWidth: 0 }}>
                      <h3 id="persona-needs-heading" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-main)', fontSize: '1rem', fontWeight: 600, margin: '0 0 0.75rem' }}>
                        <CheckCircle2 size={16} aria-hidden="true" style={{ flexShrink: 0 }} /> Needs
                      </h3>
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
                    </section>
                  </div>

                  {/* Pain Points & Objections Grid */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(260px, 100%), 1fr))', gap: '16px' }}>
                    <section aria-labelledby="persona-pain-points-heading" style={{ minWidth: 0 }}>
                      <h3 id="persona-pain-points-heading" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--status-warn-text)', fontSize: '1rem', fontWeight: 600, margin: '0 0 0.75rem' }}>
                        <AlertCircle size={16} aria-hidden="true" style={{ flexShrink: 0 }} /> Pain Points & Anxieties
                      </h3>
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
                    </section>

                    <section aria-labelledby="persona-objections-heading" style={{ minWidth: 0 }}>
                      <h3 id="persona-objections-heading" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--status-error-text)', fontSize: '1rem', fontWeight: 600, margin: '0 0 0.75rem' }}>
                        <AlertTriangle size={16} aria-hidden="true" style={{ flexShrink: 0 }} /> Buying Objections
                      </h3>
                      <ul style={{ margin: 0, paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.84rem', color: 'var(--text-primary)' }}>
                        {inspectingPersona.objections?.map((obj, idx) => (
                          <li key={idx}>{obj}</li>
                        ))}
                      </ul>
                    </section>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(12rem, 100%), 1fr))', gap: '1rem' }}>
                    {[
                      { label: 'Behaviors', values: inspectingPersona.behaviors },
                      { label: 'Preferences', values: inspectingPersona.preferences },
                      { label: 'Motivations', values: inspectingPersona.motivations },
                    ].map((group) => (
                      <section key={group.label} style={{ minWidth: 0 }}>
                        <h3 style={{ fontSize: '1rem', color: 'var(--text-primary)', margin: '0 0 0.5rem' }}>{group.label}</h3>
                        {group.values.length > 0 ? (
                          <ul style={{ margin: 0, paddingLeft: '1.25rem', color: 'var(--text-primary)', fontSize: '0.875rem' }}>
                            {group.values.map((value, index) => <li key={index}>{value}</li>)}
                          </ul>
                        ) : <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.875rem' }}>No {group.label.toLowerCase()} recorded.</p>}
                      </section>
                    ))}
                  </div>
                </>
              )}

              {/* TAB: PERSONALITY (BIG FIVE) */}
              {inspectorTab === 'personality' && (
                <section aria-labelledby="persona-personality-title" style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
                      <div style={{ minWidth: 0, flex: '1 1 16rem' }}>
                        <h3 id="persona-personality-title" style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <Brain size={18} aria-hidden="true" style={{ flexShrink: 0 }} /> Big Five Trait Spectrum
                        </h3>
                        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', margin: '0.5rem 0 0' }}>
                          Recorded source traits; not a validated psychometric assessment.
                        </p>
                      </div>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>
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
                            color: 'var(--trait-c)',
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
                        ].map((trait) => {
                          const measured = isMeasuredTraitScore(trait.val);
                          return (
                            <div key={trait.key} style={{ minWidth: 0, borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem' }}>
                              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.5rem' }}>
                                <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-main)' }}>{trait.name}</div>
                                {measured ? (
                                  <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-main)', fontVariantNumeric: 'tabular-nums' }}>{trait.val} / 100</div>
                                ) : (
                                  <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Not measured</div>
                                )}
                              </div>
                              {measured && (
                                <div role="meter" aria-label={trait.name} aria-valuemin={0} aria-valuemax={100} aria-valuenow={trait.val} aria-describedby={`persona-trait-description-${trait.key}`} style={{ height: '7px', background: 'var(--border-subtle)', borderRadius: '4px', overflow: 'hidden', marginBottom: '0.5rem' }}>
                                  <div style={{ width: `${trait.val}%`, height: '100%', background: trait.color, borderRadius: '4px' }} />
                                </div>
                              )}
                              <p id={`persona-trait-description-${trait.key}`} style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', margin: 0, lineHeight: 1.5 }}>{trait.desc}</p>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <p role="status" style={{ color: 'var(--text-muted)', margin: 0, padding: '1rem 0' }}>
                        No psychometric score data recorded for this persona.
                      </p>
                    )}
                </section>
              )}

              {/* TAB: LIFESTYLE & ROUTINE (45+ DETAILED ATTRIBUTES) */}
              {inspectorTab === 'lifestyle' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', minWidth: 0 }}>
                  {inspectingPersona.detailed_attributes ? (
                    <>
                      {/* Section 1: Work & Daily Schedule */}
                      <section aria-labelledby="persona-work-heading" style={{ minWidth: 0 }}>
                        <h3 id="persona-work-heading" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-main)', fontSize: '1rem', fontWeight: 600, margin: '0 0 0.75rem' }}>
                          <Briefcase size={16} aria-hidden="true" style={{ flexShrink: 0 }} /> Work, Commute & Schedule Context
                        </h3>
                        <dl style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: '0.75rem', margin: 0 }}>
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
                              <div key={key} style={{ minWidth: 0, borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem' }}>
                                <dt style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>{label}</dt>
                                <dd style={{ fontSize: '0.875rem', color: 'var(--text-main)', lineHeight: 1.5, margin: '0.25rem 0 0', whiteSpace: 'pre-wrap' }}>{inspectingPersona.detailed_attributes[key]}</dd>
                              </div>
                            ) : null
                          ))}
                        </dl>
                      </section>

                      {/* Section 2: Living & Sustenance */}
                      <section aria-labelledby="persona-household-heading" style={{ minWidth: 0 }}>
                        <h3 id="persona-household-heading" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-main)', fontSize: '1rem', fontWeight: 600, margin: '0 0 0.75rem' }}>
                          <Coffee size={16} aria-hidden="true" style={{ flexShrink: 0 }} /> Living, Meals & Household Structure
                        </h3>
                        <dl style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: '0.75rem', margin: 0 }}>
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
                              <div key={key} style={{ minWidth: 0, borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem' }}>
                                <dt style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>{label}</dt>
                                <dd style={{ fontSize: '0.875rem', color: 'var(--text-main)', lineHeight: 1.5, margin: '0.25rem 0 0', whiteSpace: 'pre-wrap' }}>{inspectingPersona.detailed_attributes[key]}</dd>
                              </div>
                            ) : null
                          ))}
                        </dl>
                      </section>

                      {/* Section 3: Mindset, Psychology & Communication */}
                      <section aria-labelledby="persona-mindset-heading" style={{ minWidth: 0 }}>
                        <h3 id="persona-mindset-heading" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-main)', fontSize: '1rem', fontWeight: 600, margin: '0 0 0.75rem' }}>
                          <Compass size={16} aria-hidden="true" style={{ flexShrink: 0 }} /> Mindset, Psychology & Communication Style
                        </h3>
                        <dl style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: '0.75rem', margin: 0 }}>
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
                              <div key={key} style={{ minWidth: 0, borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem' }}>
                                <dt style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>{label}</dt>
                                <dd style={{ fontSize: '0.875rem', color: 'var(--text-main)', lineHeight: 1.5, margin: '0.25rem 0 0', whiteSpace: 'pre-wrap' }}>{inspectingPersona.detailed_attributes[key]}</dd>
                              </div>
                            ) : null
                          ))}
                        </dl>
                      </section>

                      {/* Section 4: Culture, Beliefs & Social Values */}
                      <section aria-labelledby="persona-culture-heading" style={{ minWidth: 0 }}>
                        <h3 id="persona-culture-heading" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-main)', fontSize: '1rem', fontWeight: 600, margin: '0 0 0.75rem' }}>
                          <Globe size={16} aria-hidden="true" style={{ flexShrink: 0 }} /> Culture, Beliefs & Life Priorities
                        </h3>
                        <dl style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: '0.75rem', margin: 0 }}>
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
                              <div key={key} style={{ minWidth: 0, borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem' }}>
                                <dt style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>{label}</dt>
                                <dd style={{ fontSize: '0.875rem', color: 'var(--text-main)', lineHeight: 1.5, margin: '0.25rem 0 0', whiteSpace: 'pre-wrap' }}>{inspectingPersona.detailed_attributes[key]}</dd>
                              </div>
                            ) : null
                          ))}
                        </dl>
                      </section>

                      {/* Section 5: Finance & Technology */}
                      <section aria-labelledby="persona-financial-mindset-heading" style={{ minWidth: 0 }}>
                        <h3 id="persona-financial-mindset-heading" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-main)', fontSize: '1rem', fontWeight: 600, margin: '0 0 0.75rem' }}>
                          <DollarSign size={16} aria-hidden="true" style={{ flexShrink: 0 }} /> Financial Mindset & Technology Adoption
                        </h3>
                        <dl style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: '0.75rem', margin: 0 }}>
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
                              <div key={key} style={{ minWidth: 0, borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem' }}>
                                <dt style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>{label}</dt>
                                <dd style={{ fontSize: '0.875rem', color: 'var(--text-main)', lineHeight: 1.5, margin: '0.25rem 0 0', whiteSpace: 'pre-wrap' }}>{inspectingPersona.detailed_attributes[key]}</dd>
                              </div>
                            ) : null
                          ))}
                        </dl>
                      </section>
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
                <section aria-label="Commercial profile" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', minWidth: 0 }}>
                  <dl style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 200px), 1fr))', gap: '1rem', margin: 0 }}>
                    <div style={{ minWidth: 0 }}>
                      <dt style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Estimated Monthly Budget</dt>
                      <dd style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-main)', margin: 0, fontVariantNumeric: 'tabular-nums' }}>
                        {typeof inspectingPersona.commercial_profile?.monthly_budget_bdt === 'number'
                          ? `৳${inspectingPersona.commercial_profile.monthly_budget_bdt} / mo`
                          : 'Not stated'}
                      </dd>
                    </div>

                    <div style={{ minWidth: 0 }}>
                      <dt style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Price Sensitivity</dt>
                      <dd style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', margin: 0 }}>
                        {inspectingPersona.commercial_profile?.price_sensitivity || 'Not stated'}
                      </dd>
                    </div>

                    <div style={{ minWidth: 0 }}>
                      <dt style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Payment Preference</dt>
                      <dd style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', margin: 0 }}>
                        {inspectingPersona.commercial_profile?.payment_preference || 'Not stated'}
                      </dd>
                    </div>
                  </dl>

                  <div style={{ minWidth: 0 }}>
                    <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', margin: '0 0 0.5rem' }}>Willingness-to-Pay Range</h3>
                    <p style={{ fontSize: '0.86rem', color: 'var(--text-primary)', margin: 0 }}>
                      {inspectingPersona.commercial_profile?.willingness_to_pay || 'Not stated'}
                    </p>
                  </div>
                </section>
              )}

              {/* TAB 3: TECHNOLOGY PROFILE */}
              {inspectorTab === 'technology' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <section aria-labelledby="persona-devices-heading" style={{ minWidth: 0 }}>
                    <h3 id="persona-devices-heading" style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', margin: '0 0 0.75rem' }}>Primary Devices</h3>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      {inspectingPersona.technology_profile?.primary_devices?.map((d, idx) => (
                        <span key={idx} style={{ background: 'var(--bg-card)', color: 'var(--text-main)', padding: '4px 10px', borderRadius: '6px', fontSize: '0.8125rem', border: '1px solid var(--border-subtle)', minWidth: 0 }}>
                          {d}
                        </span>
                      ))}
                      {!inspectingPersona.technology_profile?.primary_devices?.length && <p role="status" style={{ margin: 0, color: 'var(--text-secondary)' }}>No devices recorded.</p>}
                    </div>
                  </section>

                  <section aria-labelledby="persona-platforms-heading" style={{ minWidth: 0 }}>
                    <h3 id="persona-platforms-heading" style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', margin: '0 0 0.75rem' }}>Frequently Used Platforms</h3>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      {inspectingPersona.technology_profile?.platforms?.map((p, idx) => (
                        <span key={idx} style={{ background: 'var(--bg-card)', color: 'var(--text-main)', padding: '4px 10px', borderRadius: '6px', fontSize: '0.8125rem', border: '1px solid var(--border-subtle)', minWidth: 0 }}>
                          {p}
                        </span>
                      ))}
                      {!inspectingPersona.technology_profile?.platforms?.length && <p role="status" style={{ margin: 0, color: 'var(--text-secondary)' }}>No platforms recorded.</p>}
                    </div>
                  </section>
                  <section style={{ minWidth: 0 }}>
                    <h3 style={{ fontSize: '1rem', color: 'var(--text-primary)', margin: '0 0 0.5rem' }}>Technology familiarity</h3>
                    <p style={{ margin: 0, color: 'var(--text-primary)', fontSize: '0.875rem' }}>{inspectingPersona.technology_profile?.familiarity || 'Not stated'}</p>
                  </section>
                </div>
              )}

              {/* TAB 4: EVIDENCE CITATIONS */}
              {inspectorTab === 'grounding' && (
                <section aria-labelledby="persona-citations-heading" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', minWidth: 0 }}>
                  <h3 id="persona-citations-heading" style={{ fontSize: '1rem', color: 'var(--text-main)', margin: 0 }}>Evidence citations</h3>

                  {inspectingPersona.evidence_citations && inspectingPersona.evidence_citations.length > 0 ? (
                    inspectingPersona.evidence_citations.map((c, idx) => (
                      <div key={idx} style={{ minWidth: 0, borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.5rem' }}>
                          <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-main)' }}>
                            {c.category || 'General Finding'}
                          </span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                            Confidence: {typeof c.confidence === 'number' ? `${Math.round(c.confidence * 100)}%` : 'n/a'}
                          </span>
                        </div>
                        <p style={{ fontSize: '0.875rem', color: 'var(--text-main)', margin: 0, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
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
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => onNavigateToEvidence?.(activeStudyId)}
                      style={{ alignSelf: 'flex-start', minHeight: '2.25rem', whiteSpace: 'normal', textAlign: 'left' }}
                    >
                      View in Evidence Laboratory <ExternalLink size={14} aria-hidden="true" />
                    </Button>
                  )}
                </section>
              )}

              {/* TAB 5: DATASET PROVENANCE */}
              {inspectorTab === 'dataset' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <section style={{ minWidth: 0 }}>
                    <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', margin: '0 0 0.75rem' }}>Variable Constraints</h3>
                    {!inspectingPersona.dataset_refs?.length && (
                      <p role="status" style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.875rem' }}>No dataset provenance recorded for this persona.</p>
                    )}
                    <dl style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', margin: 0 }}>
                      {inspectingPersona.dataset_refs?.map((ref, idx) => (
                        <div key={idx} style={{ padding: '0.75rem 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '0.875rem', minWidth: 0, overflowWrap: 'anywhere' }}>
                          <dt style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{datasetRefTitle(ref)}</dt>
                          <dd style={{ margin: '0.5rem 0 0', minWidth: 0 }}>
                            {ref.variable !== undefined && (
                              <pre style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', margin: 0 }}>{formatDatasetRefValue(ref.value)}</pre>
                            )}
                            {ref.variable === undefined && (
                              <dl style={{ margin: 0, display: 'grid', gridTemplateColumns: 'minmax(0, 11rem) minmax(0, 1fr)', gap: '0.25rem 0.75rem' }}>
                                {datasetRefFields(ref).map(([key, value]) => (
                                  <React.Fragment key={key}>
                                    <dt style={{ color: 'var(--text-secondary)' }}>{key.replace(/_/g, ' ')}</dt>
                                    <dd style={{ margin: 0, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', whiteSpace: 'pre-wrap' }}>{value}</dd>
                                  </React.Fragment>
                                ))}
                              </dl>
                            )}
                            {ref.source && <div style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>Source: {ref.source}</div>}
                            {ref.dataset_id && <div style={{ color: 'var(--text-secondary)' }}>Dataset ID: <code>{ref.dataset_id}</code></div>}
                            {ref.content_hash && <div style={{ color: 'var(--text-secondary)' }}>Content hash: <code>{ref.content_hash}</code></div>}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </section>
                </div>
              )}

              {/* TAB: MEMORY (what the persona has remembered across interviews) */}
              {inspectorTab === 'memory' && <PersonaMemoryPanel personaId={inspectingPersona.id} />}
            </div>

            {/* Modal Footer */}
            <footer style={{ padding: '1rem', borderTop: '1px solid var(--border-subtle)', background: 'var(--bg-pure)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem', minWidth: 0, flexShrink: 0 }}>
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', minWidth: 0, overflowWrap: 'anywhere' }}>
                Persona ID: <code>{inspectingPersona.id}</code>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', minWidth: 0 }}>
                {onStartInterviewWithPersona && (
                  <Button
                    variant="primary"
                    size="sm"
                    leadingIcon={<MessageSquare size={14} aria-hidden="true" />}
                    onClick={() => {
                      onStartInterviewWithPersona(inspectingPersona.id, activeStudyId || undefined);
                      setInspectingPersona(null);
                    }}
                  >
                    Start Adaptive Interview
                  </Button>
                )}
              </div>
            </footer>
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
            padding: '1rem',
            zIndex: 100,
          }}
          onClick={() => !isGenerating && setShowGenerateModal(false)}
        >
          <div
            ref={generateModalRef}
            className="bx-modal"
            role="dialog"
            tabIndex={-1}
            aria-modal="true"
            aria-labelledby="generate-personas-title"
            aria-busy={isGenerating}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '12px',
              maxWidth: '560px',
              width: '100%',
              minWidth: 0,
              maxHeight: 'calc(100dvh - 2rem)',
              overflowY: 'auto',
              overflowWrap: 'anywhere',
              padding: '1rem',
              boxShadow: 'var(--shadow-lg)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '1.25rem', minWidth: 0 }}>
              <div style={{ minWidth: 0 }}>
                <h2 id="generate-personas-title" style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-main)', margin: '0 0 0.25rem', overflowWrap: 'anywhere' }}>
                  Generate Synthetic Personas
                </h2>
              </div>
              {!isGenerating && (
                <Button type="button" variant="ghost" onClick={() => setShowGenerateModal(false)} aria-label="Close generate personas dialog" title="Close generate personas dialog" style={{ width: '2.25rem', height: '2.25rem', flexShrink: 0, padding: 0 }}>
                  <X size={18} aria-hidden="true" />
                </Button>
              )}
            </div>

            {generationError && (
              <div id="persona-generation-error" role="alert" tabIndex={-1} style={{ background: 'var(--bg-pure)', border: '1px solid var(--status-error-border)', borderRadius: '6px', padding: '0.75rem', color: 'var(--status-error-text)', fontSize: '0.875rem', marginBottom: '1rem', overflowWrap: 'anywhere' }}>
                {generationError}
              </div>
            )}

            {!isGenerating ? (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void handleTriggerGeneration();
                }}
                aria-describedby={generationError ? 'persona-generation-error' : undefined}
                style={{ display: 'flex', flexDirection: 'column', gap: '1rem', minWidth: 0 }}
              >
                {/* Personas per segment */}
                <div>
                  <label htmlFor="persona-segment-count" style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
                    Personas per Market Segment: {personasPerSegment}
                  </label>
                  <input
                    id="persona-segment-count"
                    type="range"
                    min="1"
                    max="6"
                    value={personasPerSegment}
                    onChange={(e) => setPersonasPerSegment(Number(e.target.value))}
                    style={{ width: '100%', accentColor: 'var(--text-primary)', cursor: 'pointer' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    <span>1 Persona</span>
                    <span>3 Personas</span>
                    <span>6 Personas</span>
                  </div>
                </div>

                {/* Distribution Strategy */}
                <fieldset style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
                  <legend style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
                    Quota Allocation Strategy
                  </legend>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(12rem, 100%), 1fr))', gap: '0.5rem' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem', border: '1px solid var(--border-medium)', borderRadius: '6px', color: 'var(--text-primary)', fontSize: '0.875rem', cursor: 'pointer', minWidth: 0 }}>
                      <input type="radio" name="persona-distribution" value="population_weighted" checked={distributionStrategy === 'population_weighted'} onChange={() => setDistributionStrategy('population_weighted')} style={{ accentColor: 'var(--text-primary)', flexShrink: 0 }} />
                      Population-Weighted
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem', border: '1px solid var(--border-medium)', borderRadius: '6px', color: 'var(--text-primary)', fontSize: '0.875rem', cursor: 'pointer', minWidth: 0 }}>
                      <input type="radio" name="persona-distribution" value="equal" checked={distributionStrategy === 'equal'} onChange={() => setDistributionStrategy('equal')} style={{ accentColor: 'var(--text-primary)', flexShrink: 0 }} />
                      Equal Distribution
                    </label>
                  </div>
                </fieldset>

                {/* Submit button */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.5rem' }}>
                  <Button
                    onClick={() => setShowGenerateModal(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    variant="primary"
                    leadingIcon={<Sparkles size={15} aria-hidden="true" />}
                  >
                    Synthesize Personas
                  </Button>
                </div>
              </form>
            ) : (
              /* HONEST INDETERMINATE LOADING — no fake step timers */
              <div role="status" tabIndex={0} aria-live="polite" aria-atomic="true" style={{ padding: '1.5rem 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
                <div
                  style={{
                    width: '36px',
                    height: '36px',
                    border: '3px solid var(--border-medium)',
                    borderTopColor: 'var(--text-primary)',
                    borderRadius: '50%',
                    animation: 'authSpin 0.7s linear infinite',
                  }}
                />
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '4px' }}>
                    Generating personas…
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Selecting synthetic source profiles.
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
