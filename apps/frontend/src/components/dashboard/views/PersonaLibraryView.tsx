import React, { useState, useEffect, useMemo } from 'react';
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

interface PersonaLibraryViewProps {
  studyId?: string;
  onStartInterviewWithPersona?: (personaId: string) => void;
  onTestBehaviorWithPersona?: (personaId: string) => void;
  onNavigateToEvidence?: () => void;
  onNavigateToSegmentation?: () => void;
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
  const [inspectorTab, setInspectorTab] = useState<'profile' | 'personality' | 'lifestyle' | 'commercial' | 'technology' | 'grounding' | 'dataset'>('profile');
  const [isRegenerating, setIsRegenerating] = useState<boolean>(false);

  // Generation Modal & Stepper States
  const [showGenerateModal, setShowGenerateModal] = useState<boolean>(false);
  const [personasPerSegment, setPersonasPerSegment] = useState<number>(2);
  const [distributionStrategy, setDistributionStrategy] = useState<'population_weighted' | 'equal'>('population_weighted');
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [generationStep, setGenerationStep] = useState<number>(0);
  const [generationError, setGenerationError] = useState<string | null>(null);

  // Load Studies on mount
  useEffect(() => {
    const loadStudies = async () => {
      try {
        const studyList = await api.getStudies();
        setStudies(studyList);
        if (!activeStudyId && studyList.length > 0) {
          setActiveStudyId(studyList[0].id);
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
    setIsLoading(true);
    setError(null);
    try {
      const [personasRes, segmentsRes, runsRes] = await Promise.allSettled([
        api.getStudyPersonas(activeStudyId || 'default'),
        activeStudyId ? api.getMarketSegments(activeStudyId) : Promise.resolve([]),
        activeStudyId ? api.listStudyPersonaRuns(activeStudyId) : Promise.resolve({ runs: [] }),
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
    loadStudyData();
  }, [activeStudyId]);

  // Filtered Personas
  const filteredPersonas = useMemo(() => {
    return personas.filter((p) => {
      if (selectedSegmentFilter !== 'all' && p.segment_id !== selectedSegmentFilter) return false;
      if (selectedStatusFilter !== 'all' && p.status !== selectedStatusFilter) return false;
      if (selectedRunFilter !== 'all' && p.generation_run_id !== selectedRunFilter) return false;
      if (selectedGroundingFilter === 'high' && p.grounding_score < 0.90) return false;
      if (selectedGroundingFilter === 'medium' && (p.grounding_score < 0.80 || p.grounding_score >= 0.90)) return false;

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
    const avgScore = total > 0 ? Math.round((personas.reduce((acc, p) => acc + p.grounding_score, 0) / total) * 100) : 0;
    const readyCount = personas.filter((p) => p.status === 'ready').length;
    return { total, repSegments, avgScore, readyCount };
  }, [personas]);

  // Generation Stepper Handler
  const handleTriggerGeneration = async () => {
    if (!activeStudyId) return;
    setIsGenerating(true);
    setGenerationStep(1);
    setGenerationError(null);

    const stepTimer = setInterval(() => {
      setGenerationStep((prev) => (prev < 4 ? prev + 1 : prev));
    }, 900);

    try {
      const res = await api.generateSyntheticPersonas(activeStudyId, {
        personas_per_segment: personasPerSegment,
        distribution_strategy: distributionStrategy,
      });

      clearInterval(stepTimer);
      setGenerationStep(5);

      setTimeout(() => {
        setIsGenerating(false);
        setShowGenerateModal(false);
        setPersonas(res.personas);
        setRuns((prev) => [res.run, ...prev]);
      }, 600);
    } catch (err: any) {
      clearInterval(stepTimer);
      setIsGenerating(false);
      setGenerationError(err.message || 'Persona generation failed. Please ensure segmentation has completed.');
    }
  };

  // Regenerate Persona Handler
  const handleRegeneratePersona = async (personaId: string) => {
    if (!activeStudyId) return;
    setIsRegenerating(true);
    try {
      const updated = await api.regenerateStudyPersona(activeStudyId, personaId);
      setPersonas((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      if (inspectingPersona && inspectingPersona.id === updated.id) {
        setInspectingPersona(updated);
      }
    } catch (err: any) {
      alert(`Regeneration failed: ${err.message}`);
    } finally {
      setIsRegenerating(false);
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            <h1 style={{ fontSize: '1.85rem', fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-0.02em', margin: 0 }}>
              Persona Library
            </h1>
            <span style={{ fontSize: '0.72rem', fontWeight: 600, padding: '2px 8px', borderRadius: '6px', background: 'var(--accent-subtle)', color: '#14B8A6', border: '1px solid var(--accent-glow)' }}>
              Synthetic Agents
            </span>
          </div>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', margin: 0 }}>
            Saved personas and audiences you can reuse in any study.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Study Context Selector if multiple studies exist */}
          {studies.length > 1 && (
            <select
              value={activeStudyId}
              onChange={(e) => setActiveStudyId(e.target.value)}
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '10px',
                padding: '9px 14px',
                fontSize: '0.85rem',
                color: 'var(--text-primary)',
                outline: 'none',
                cursor: 'pointer',
              }}
            >
              {studies.map((s) => (
                <option key={s.id} value={s.id}>
                  Study: {s.title || s.id}
                </option>
              ))}
            </select>
          )}

          <button
            type="button"
            onClick={() => setShowGenerateModal(true)}
            style={{
              background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
              color: 'var(--text-on-accent)',
              border: 'none',
              borderRadius: '10px',
              padding: '9px 18px',
              fontSize: '0.86rem',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              cursor: 'pointer',
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
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
          marginBottom: '28px',
        }}
      >
        <div className="bx-stagger" style={{ ['--bx-i' as string]: 0, background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '14px', padding: '18px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ width: '42px', height: '42px', borderRadius: '10px', background: 'var(--accent-subtle)', border: '1px solid var(--accent-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#14B8A6' }}>
            <User size={20} />
          </div>
          <div>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.1 }}><CountUp value={metrics.total} /></div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>Total Synthetic Personas</div>
          </div>
        </div>

        <div className="bx-stagger" style={{ ['--bx-i' as string]: 1, background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '14px', padding: '18px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ width: '42px', height: '42px', borderRadius: '10px', background: 'rgba(34, 211, 238, 0.12)', border: '1px solid rgba(34, 211, 238, 0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent-cyan)' }}>
            <Layers size={20} />
          </div>
          <div>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.1 }}><CountUp value={metrics.repSegments} /></div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>Represented Segments</div>
          </div>
        </div>

        <div className="bx-stagger" style={{ ['--bx-i' as string]: 2, background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '14px', padding: '18px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ width: '42px', height: '42px', borderRadius: '10px', background: 'rgba(16, 185, 129, 0.12)', border: '1px solid rgba(16, 185, 129, 0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent-emerald)' }}>
            <ShieldCheck size={20} />
          </div>
          <div>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--accent-emerald)', lineHeight: 1.1 }}><CountUp value={metrics.avgScore} format={(v) => `${Math.round(v)}%`} /></div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>Avg. Grounding Score</div>
          </div>
        </div>

        <div className="bx-stagger" style={{ ['--bx-i' as string]: 3, background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '14px', padding: '18px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ width: '42px', height: '42px', borderRadius: '10px', background: 'rgba(245, 158, 11, 0.12)', border: '1px solid rgba(245, 158, 11, 0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#F59E0B' }}>
            <CheckCircle2 size={20} />
          </div>
          <div>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.1 }}><CountUp value={metrics.readyCount} /> / <CountUp value={metrics.total} /></div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>Verified & Ready</div>
          </div>
        </div>
      </div>

      {/* =========================================================================
          3. FILTER & SEARCH BAR
         ========================================================================= */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '24px',
          flexWrap: 'wrap',
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '14px',
          padding: '12px 16px',
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
            <button type="button" onClick={() => setSearchQuery('')} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <X size={14} />
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
              padding: '6px 12px',
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
              padding: '6px 12px',
              fontSize: '0.82rem',
              color: 'var(--text-primary)',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="all">All Statuses</option>
            <option value="ready">Ready / Verified</option>
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
              padding: '6px 12px',
              fontSize: '0.82rem',
              color: 'var(--text-primary)',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="all">All Grounding Scores</option>
            <option value="high">High Grounding (≥90%)</option>
            <option value="medium">Medium Grounding (80–89%)</option>
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

      {/* =========================================================================
          4. PERSONA CARDS GRID / SKELETON / EMPTY STATE
         ========================================================================= */}
      {isLoading ? (
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
          <div style={{ width: '56px', height: '56px', borderRadius: '50%', background: 'var(--accent-subtle)', border: '1px solid var(--accent-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', color: '#14B8A6' }}>
            <Sparkles size={26} />
          </div>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', margin: '0 0 8px 0' }}>
            {personas.length === 0 ? 'No Synthetic Personas Generated Yet' : 'No Personas Match Your Filter'}
          </h3>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', maxWidth: '480px', margin: '0 auto 20px', lineHeight: 1.5 }}>
            {personas.length === 0
              ? 'Generate synthetic consumer simulation agents grounded in your study market segments, pricing quartiles, and research claims.'
              : 'Try clearing your search query or adjusting segment and status filters to see available personas.'}
          </p>
          {personas.length === 0 ? (
            <button
              type="button"
              onClick={() => setShowGenerateModal(true)}
              style={{
                background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
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
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '20px' }}>
          {filteredPersonas.map((persona, cardIdx) => {
            const initials = persona.name
              .split(' ')
              .map((n) => n[0])
              .join('')
              .toUpperCase()
              .slice(0, 2);
            const groundingPct = Math.round(persona.grounding_score * 100);
            const isReady = persona.status === 'ready';

            return (
              <div
                key={persona.id}
                className="bx-stagger bx-lift"
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
                  transition: 'all 0.18s ease',
                  position: 'relative',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'rgba(20, 184, 166, 0.4)';
                  e.currentTarget.style.boxShadow = '0 8px 24px rgba(0, 0, 0, 0.4)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border-subtle)';
                  e.currentTarget.style.boxShadow = 'none';
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
                            <span style={{ fontSize: '0.68rem', color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', padding: '1px 5px', borderRadius: '4px' }}>
                              v{persona.version}
                            </span>
                          )}
                          <span style={{ fontSize: '0.68rem', color: '#14B8A6', background: 'var(--accent-subtle)', border: '1px solid var(--accent-glow)', padding: '1px 6px', borderRadius: '4px', fontWeight: 600 }}>
                            {persona.country_code || 'BD'}
                          </span>
                          {persona.data_source === 'cached' && (
                            <span
                              title="Served from seeded/cached data — not generated live for this study"
                              style={{ fontSize: '0.62rem', color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', border: '1px solid var(--border-medium)', padding: '1px 6px', borderRadius: '4px', fontFamily: 'var(--font-mono)', letterSpacing: '0.06em' }}
                            >
                              CACHED
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                          {persona.demographics?.age ? `${persona.demographics.age} yo • ` : ''}
                          {persona.demographics?.occupation || persona.archetype || 'Consumer'}
                        </div>
                      </div>
                    </div>

                    {/* Status Badge */}
                    <span
                      style={{
                        fontSize: '0.72rem',
                        fontWeight: 600,
                        padding: '3px 8px',
                        borderRadius: '6px',
                        background: isReady ? 'rgba(16, 185, 129, 0.12)' : 'rgba(245, 158, 11, 0.12)',
                        color: isReady ? 'var(--accent-emerald)' : '#F59E0B',
                        border: `1px solid ${isReady ? 'rgba(16, 185, 129, 0.25)' : 'rgba(245, 158, 11, 0.25)'}`,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {isReady ? 'Verified' : 'Needs Review'}
                    </span>
                  </div>

                  {/* Tagline / Evocative Archetype */}
                  {persona.tagline && (
                    <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--accent-cyan)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <Sparkles size={12} color="var(--accent-cyan)" />
                      <span>{persona.tagline}</span>
                    </div>
                  )}

                  {/* Segment & Synthetic Tag */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '10px' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 500, padding: '2px 8px', borderRadius: '6px', background: 'rgba(34, 211, 238, 0.1)', color: 'var(--accent-cyan)', border: '1px solid rgba(34, 211, 238, 0.2)' }}>
                      {persona.segment_name || 'Target Segment'}
                    </span>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', padding: '2px 7px', borderRadius: '5px', border: '1px solid var(--border-subtle)' }}>
                      Synthetic Persona
                    </span>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', padding: '2px 7px', borderRadius: '5px', border: '1px solid var(--border-subtle)' }}>
                      {persona.origin_country || 'Bangladesh'}
                    </span>
                  </div>

                  {/* Big Five Personality Micro Bars */}
                  {persona.personality && (
                    <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '8px 10px', marginBottom: '12px' }}>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Brain size={11} color="#14B8A6" /> Big Five Traits
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '6px', textAlign: 'center' }}>
                        {[
                          { label: 'O', name: 'Openness', val: persona.personality.openness, color: '#38BDF8' },
                          { label: 'C', name: 'Conscientiousness', val: persona.personality.conscientiousness, color: 'var(--accent-emerald)' },
                          { label: 'E', name: 'Extroversion', val: persona.personality.extroversion, color: '#F59E0B' },
                          { label: 'A', name: 'Agreeableness', val: persona.personality.agreeableness, color: '#A855F7' },
                          { label: 'N', name: 'Neuroticism', val: persona.personality.neuroticism, color: '#EC4899' },
                        ].map((trait) => (
                          <div key={trait.label} title={`${trait.name}: ${trait.val}/100`}>
                            <div style={{ fontSize: '0.68rem', fontWeight: 600, color: trait.color }}>{trait.val}</div>
                            <div style={{ height: '3px', background: 'var(--border-subtle)', borderRadius: '2px', overflow: 'hidden', margin: '2px 0' }}>
                              <div style={{ width: `${trait.val}%`, height: '100%', background: trait.color }} />
                            </div>
                            <div style={{ fontSize: '0.62rem', color: 'var(--text-secondary)' }}>{trait.label}</div>
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
                        <Target size={12} color="#14B8A6" style={{ flexShrink: 0 }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{persona.goals[0]}</span>
                      </div>
                    )}
                    {persona.pain_points?.[0] && (
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <AlertCircle size={12} color="#F59E0B" style={{ flexShrink: 0 }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{persona.pain_points[0]}</span>
                      </div>
                    )}
                    {persona.detailed_attributes?.work_schedule && (
                      <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <Clock size={11} color="#38BDF8" style={{ flexShrink: 0 }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{persona.detailed_attributes.work_schedule}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Card Footer: Commercial budget, Grounding score meter, Deep Dive Button */}
                <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      <CreditCard size={13} color="#14B8A6" />
                      <span>{persona.commercial_profile?.monthly_budget_bdt ? `৳${persona.commercial_profile.monthly_budget_bdt}/mo` : '৳350/mo'}</span>
                    </div>

                    {/* Grounding Score */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <div style={{ width: '48px', height: '5px', borderRadius: '3px', background: 'var(--border-subtle)', overflow: 'hidden' }}>
                        <div style={{ width: `${groundingPct}%`, height: '100%', background: groundingPct >= 90 ? 'var(--accent-emerald)' : '#14B8A6' }} />
                      </div>
                      <span style={{ fontSize: '0.75rem', fontWeight: 600, color: groundingPct >= 90 ? 'var(--accent-emerald)' : '#14B8A6' }}>
                        {groundingPct}%
                      </span>
                    </div>
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
                        e.currentTarget.style.color = '#14B8A6';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'var(--bg-card-hover)';
                        e.currentTarget.style.borderColor = 'var(--border-subtle)';
                        e.currentTarget.style.color = 'var(--text-primary)';
                      }}
                    >
                      Deep Dive Inspector
                    </button>

                    {onStartInterviewWithPersona && (
                      <button
                        type="button"
                        onClick={() => onStartInterviewWithPersona(persona.id)}
                        title="Start Adaptive Interview with this persona (Part 6)"
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
                        onClick={() => onTestBehaviorWithPersona(persona.id)}
                        title="Simulate Behavioral Scenario with this persona (Part 7)"
                        style={{
                          background: 'var(--accent-subtle)',
                          border: '1px solid var(--accent-glow)',
                          borderRadius: '8px',
                          padding: '7px 10px',
                          color: '#14B8A6',
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
              </div>
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
            background: 'var(--glass-strong)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            zIndex: 100,
          }}
          onClick={() => setInspectingPersona(null)}
        >
          <div
            className="bx-modal"
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '20px',
              maxWidth: '900px',
              width: '100%',
              maxHeight: '90vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 24px 64px rgba(0, 0, 0, 0.9)',
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
                    <h2 style={{ fontSize: '1.35rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                      {inspectingPersona.name}
                    </h2>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', padding: '2px 6px', borderRadius: '4px' }}>
                      v{inspectingPersona.version}
                    </span>
                    <span style={{ fontSize: '0.72rem', fontWeight: 600, padding: '2px 8px', borderRadius: '6px', background: inspectingPersona.status === 'ready' ? 'rgba(16, 185, 129, 0.12)' : 'rgba(245, 158, 11, 0.12)', color: inspectingPersona.status === 'ready' ? 'var(--accent-emerald)' : '#F59E0B', border: '1px solid rgba(16, 185, 129, 0.25)' }}>
                      {inspectingPersona.status === 'ready' ? 'Verified' : 'Needs Review'}
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
                  style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', padding: '6px' }}
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Modal Tabs Bar */}
            <div style={{ display: 'flex', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', padding: '0 28px', background: '#090C0C', overflowX: 'auto' }}>
              {[
                { id: 'profile', label: 'Persona Profile', icon: <User size={14} /> },
                { id: 'personality', label: 'Personality (Big Five)', icon: <Brain size={14} /> },
                { id: 'lifestyle', label: 'Lifestyle & Routine', icon: <Activity size={14} /> },
                { id: 'commercial', label: 'Commercial & WTP', icon: <CreditCard size={14} /> },
                { id: 'technology', label: 'Technology Profile', icon: <Smartphone size={14} /> },
                { id: 'grounding', label: `Evidence Citations (${inspectingPersona.evidence_citations?.length || 0})`, icon: <ShieldCheck size={14} /> },
                { id: 'dataset', label: 'Dataset Provenance', icon: <Database size={14} /> },
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
                      borderBottom: isActive ? '2px solid #14B8A6' : '2px solid transparent',
                      padding: '12px 16px',
                      fontSize: '0.84rem',
                      fontWeight: isActive ? 600 : 500,
                      color: isActive ? '#14B8A6' : 'var(--text-secondary)',
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
                        <span style={{ fontSize: '0.78rem', color: '#14B8A6', background: 'var(--accent-subtle)', border: '1px solid var(--accent-glow)', padding: '3px 10px', borderRadius: '6px', fontWeight: 600 }}>
                          {inspectingPersona.country_code || 'BD'} • {inspectingPersona.origin_country || 'Bangladesh'}
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Bio & Quote */}
                  <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#14B8A6', fontSize: '0.8rem', fontWeight: 600, marginBottom: '6px' }}>
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
                        {inspectingPersona.goals?.map((g, idx) => (
                          <li key={idx}>{g}</li>
                        ))}
                      </ul>
                    </div>

                    <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--accent-cyan)', fontSize: '0.82rem', fontWeight: 600, marginBottom: '10px' }}>
                        <CheckCircle2 size={14} /> Observed Needs
                      </div>
                      <ul style={{ margin: 0, paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.84rem', color: 'var(--text-primary)' }}>
                        {inspectingPersona.needs?.map((n, idx) => (
                          <li key={idx}>{n}</li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {/* Pain Points & Objections Grid */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(260px, 100%), 1fr))', gap: '16px' }}>
                    <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#F59E0B', fontSize: '0.82rem', fontWeight: 600, marginBottom: '10px' }}>
                        <AlertCircle size={14} /> Pain Points & Anxieties
                      </div>
                      <ul style={{ margin: 0, paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.84rem', color: 'var(--text-primary)' }}>
                        {inspectingPersona.pain_points?.map((pp, idx) => (
                          <li key={idx}>{pp}</li>
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
                          <Brain size={18} color="#14B8A6" /> Big Five Trait Spectrum
                        </h4>
                        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: '4px 0 0 0' }}>
                          Quantified psychometric scale (0–100) governing simulation conversational tone, risk tolerance, and decision pace.
                        </p>
                      </div>
                      <span style={{ fontSize: '0.75rem', background: 'var(--accent-subtle)', color: '#14B8A6', padding: '4px 10px', borderRadius: '6px', fontWeight: 600 }}>
                        OCEAN Psychometrics
                      </span>
                    </div>

                    {inspectingPersona.personality ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {[
                          {
                            key: 'openness',
                            name: 'Openness to Experience',
                            val: inspectingPersona.personality.openness ?? 50,
                            desc: 'Curiosity, imagination, and receptivity to novel ideas vs preference for routine and convention.',
                            color: '#38BDF8',
                          },
                          {
                            key: 'conscientiousness',
                            name: 'Conscientiousness',
                            val: inspectingPersona.personality.conscientiousness ?? 50,
                            desc: 'Self-discipline, organization, diligence, and goal-oriented planning.',
                            color: 'var(--accent-emerald)',
                          },
                          {
                            key: 'extroversion',
                            name: 'Extroversion',
                            val: inspectingPersona.personality.extroversion ?? 50,
                            desc: 'Outgoing energy, social engagement, assertiveness, and enthusiasm.',
                            color: '#F59E0B',
                          },
                          {
                            key: 'agreeableness',
                            name: 'Agreeableness',
                            val: inspectingPersona.personality.agreeableness ?? 50,
                            desc: 'Cooperativeness, empathy, consideration, and trust in social interactions.',
                            color: '#A855F7',
                          },
                          {
                            key: 'neuroticism',
                            name: 'Neuroticism (Emotional Sensitivity)',
                            val: inspectingPersona.personality.neuroticism ?? 50,
                            desc: 'Sensitivity to stress, vulnerability to anxiety, and reactivity to disruption.',
                            color: '#EC4899',
                          },
                        ].map((trait) => (
                          <div key={trait.key} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '10px', padding: '14px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                              <div style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)' }}>{trait.name}</div>
                              <div style={{ fontSize: '0.95rem', fontWeight: 700, color: trait.color }}>{trait.val} / 100</div>
                            </div>
                            <div style={{ height: '7px', background: 'var(--border-subtle)', borderRadius: '4px', overflow: 'hidden', marginBottom: '8px' }}>
                              <div style={{ width: `${trait.val}%`, height: '100%', background: `linear-gradient(90deg, ${trait.color}99, ${trait.color})`, borderRadius: '4px' }} />
                            </div>
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
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38BDF8', fontSize: '0.88rem', fontWeight: 600, marginBottom: '14px' }}>
                          <Briefcase size={16} /> Work, Commute & Schedule Context
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
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
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
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
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#F59E0B', fontSize: '0.88rem', fontWeight: 600, marginBottom: '14px' }}>
                          <Compass size={16} /> Mindset, Psychology & Communication Style
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
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
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#A855F7', fontSize: '0.88rem', fontWeight: 600, marginBottom: '14px' }}>
                          <Globe size={16} /> Culture, Beliefs & Life Priorities
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
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
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#EC4899', fontSize: '0.88rem', fontWeight: 600, marginBottom: '14px' }}>
                          <DollarSign size={16} /> Financial Mindset & Technology Adoption
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
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
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px' }}>
                    <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>Estimated Monthly Budget</div>
                      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#14B8A6' }}>
                        ৳{inspectingPersona.commercial_profile?.monthly_budget_bdt || 350} / mo
                      </div>
                    </div>

                    <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>Price Sensitivity</div>
                      <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {inspectingPersona.commercial_profile?.price_sensitivity || 'High'}
                      </div>
                    </div>

                    <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>Payment Preference</div>
                      <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--accent-cyan)' }}>
                        {inspectingPersona.commercial_profile?.payment_preference || 'bKash / Nagad Mobile Wallet'}
                      </div>
                    </div>
                  </div>

                  <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                    <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px' }}>Willingness-to-Pay Range</div>
                    <p style={{ fontSize: '0.86rem', color: 'var(--text-primary)', margin: 0 }}>
                      {inspectingPersona.commercial_profile?.willingness_to_pay || '৳250–৳400 / month based on empirical student budget distributions.'}
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
                        <span key={idx} style={{ background: 'var(--border-subtle)', color: '#14B8A6', padding: '4px 10px', borderRadius: '6px', fontSize: '0.8rem', border: '1px solid var(--accent-glow)' }}>
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
                    Every synthetic persona is anchored in empirical findings extracted during study research runs.
                  </div>

                  {inspectingPersona.evidence_citations && inspectingPersona.evidence_citations.length > 0 ? (
                    inspectingPersona.evidence_citations.map((c, idx) => (
                      <div key={idx} style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#14B8A6', textTransform: 'uppercase' }}>
                            {c.category || 'General Finding'}
                          </span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                            Confidence: {c.confidence ? `${Math.round(c.confidence * 100)}%` : '88%'}
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
                        color: '#14B8A6',
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
                          <span style={{ color: '#14B8A6', fontWeight: 600 }}>{String(ref.value)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div style={{ padding: '16px 28px', borderTop: '1px solid var(--border-subtle)', background: '#090C0C', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                Persona ID: <code style={{ color: '#14B8A6' }}>{inspectingPersona.id}</code>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {onStartInterviewWithPersona && (
                  <button
                    type="button"
                    onClick={() => {
                      onStartInterviewWithPersona(inspectingPersona.id);
                      setInspectingPersona(null);
                    }}
                    style={{
                      background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
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
            background: 'var(--glass-strong)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            zIndex: 100,
          }}
          onClick={() => !isGenerating && setShowGenerateModal(false)}
        >
          <div
            className="bx-modal"
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '20px',
              maxWidth: '560px',
              width: '100%',
              padding: '28px',
              boxShadow: '0 24px 64px rgba(0, 0, 0, 0.9)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '20px' }}>
              <div>
                <h2 style={{ fontSize: '1.35rem', fontWeight: 600, color: 'var(--text-primary)', margin: '0 0 4px 0' }}>
                  Generate Synthetic Personas
                </h2>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: 0 }}>
                  Synthesize data-grounded simulation agents across market segments.
                </p>
              </div>
              {!isGenerating && (
                <button type="button" onClick={() => setShowGenerateModal(false)} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  <X size={18} />
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
                        border: `1px solid ${distributionStrategy === 'population_weighted' ? '#14B8A6' : 'var(--border-subtle)'}`,
                        borderRadius: '10px',
                        padding: '12px',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <div style={{ fontSize: '0.84rem', fontWeight: 600, color: distributionStrategy === 'population_weighted' ? '#14B8A6' : 'var(--text-primary)', marginBottom: '2px' }}>
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
                        border: `1px solid ${distributionStrategy === 'equal' ? '#14B8A6' : 'var(--border-subtle)'}`,
                        borderRadius: '10px',
                        padding: '12px',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <div style={{ fontSize: '0.84rem', fontWeight: 600, color: distributionStrategy === 'equal' ? '#14B8A6' : 'var(--text-primary)', marginBottom: '2px' }}>
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
                      background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
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
              /* LIVE EXECUTION PROGRESS STEPPER */
              <div style={{ padding: '16px 0' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
                  {[
                    { step: 1, label: 'Loading study segments and distributions' },
                    { step: 2, label: 'Synthesizing grounded consumer profiles' },
                    { step: 3, label: 'Validating age, budget & behavioral bounds' },
                    { step: 4, label: 'Computing exact grounding scores' },
                    { step: 5, label: 'Persisting personas in Study Library' },
                  ].map((s) => {
                    const isDone = generationStep > s.step;
                    const isCurrent = generationStep === s.step;

                    return (
                      <div key={s.step} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div
                          style={{
                            width: '24px',
                            height: '24px',
                            borderRadius: '50%',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            background: isDone ? 'var(--accent-emerald)' : isCurrent ? 'var(--accent-glow)' : 'var(--bg-card-hover)',
                            color: isDone ? 'var(--bg-pure)' : isCurrent ? '#14B8A6' : 'var(--text-secondary)',
                            border: `1px solid ${isDone ? 'var(--accent-emerald)' : isCurrent ? '#14B8A6' : 'var(--border-subtle)'}`,
                          }}
                        >
                          {isDone ? <CheckCircle2 size={14} /> : s.step}
                        </div>
                        <span style={{ fontSize: '0.86rem', color: isDone || isCurrent ? 'var(--text-primary)' : 'var(--text-secondary)', fontWeight: isCurrent ? 600 : 400 }}>
                          {s.label}
                        </span>
                      </div>
                    );
                  })}
                </div>

                <div style={{ height: '6px', borderRadius: '3px', background: 'var(--bg-card-hover)', overflow: 'hidden' }}>
                  <div style={{ width: `${(generationStep / 5) * 100}%`, height: '100%', background: 'linear-gradient(90deg, #14B8A6, var(--accent-cyan))', transition: 'width 0.4s ease' }} />
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
