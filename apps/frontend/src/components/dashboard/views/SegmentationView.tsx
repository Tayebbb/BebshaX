import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  PieChart,
  Sparkles,
  ArrowRight,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Sliders,
  Download,
  Search,
  ChevronRight,
  X,
  FileSpreadsheet,
  CheckSquare,
  Square,
  FileText,
} from 'lucide-react';
import { api } from '../../../services/api';
import { useDialogA11y } from '../../../utils/useDialogA11y';
import {
  MarketSegment,
  ObservedDistribution,
  SegmentationReadiness,
  SegmentationRun,
  SegmentComparisonResult,
} from '../../../types/segmentation';

interface SegmentationViewProps {
  studyId: string;
  onNavigateToEvidence?: () => void;
  onProceedToPersonas?: (selectedSegmentId?: string) => void;
}

const fmt = (n: number | undefined | null): string =>
  typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';

/** What the dataset actually measured for a segment — the partition variable's
 * range/median and the dominant category per observed categorical variable.
 * Segments carry no assumed demographics, currency or tech level. */
const observedFacts = (segment: MarketSegment) => {
  const chars = segment.characteristics || {};
  const observed = (chars.observed || segment.variable_distributions || {}) as Record<string, ObservedDistribution>;
  const partitionVariable = chars.partition_variable as string | undefined;
  const primary = partitionVariable ? observed[partitionVariable] : undefined;
  const dominant = Object.entries(observed)
    .filter(([, d]) => d && Array.isArray(d.top_categories) && d.top_categories.length > 0)
    .map(([name, d]) => `${name}: ${d.top_categories![0].category}`)
    .slice(0, 3);
  const constraints = (chars.observed_constraints || {}) as Record<string, unknown>;
  const constraintBits = Object.entries(constraints)
    .filter(([k, v]) => k !== 'rule_description' && (typeof v === 'string' || typeof v === 'number'))
    .map(([k, v]) => `${k}: ${String(v)}`)
    .slice(0, 3);
  return {
    partitionLabel: partitionVariable ? `${partitionVariable.replace(/_/g, ' ')} range` : 'Grouping',
    headline: primary && typeof primary.min === 'number' && typeof primary.max === 'number'
      ? `${fmt(primary.min)}–${fmt(primary.max)}`
      : chars.partition_method === 'categorical_grouping'
      ? String(chars.name_hint || segment.cluster_label)
      : '—',
    median: primary && typeof primary.median === 'number' ? fmt(primary.median) : '—',
    dominant: (dominant.length ? dominant : constraintBits).join(' · ') || 'No categorical variables observed',
    observedVariables: Object.keys(observed),
  };
};

export const SegmentationView: React.FC<SegmentationViewProps> = ({
  studyId,
  onNavigateToEvidence,
  onProceedToPersonas,
}) => {
  const [readiness, setReadiness] = useState<SegmentationReadiness | null>(null);
  const [segments, setSegments] = useState<MarketSegment[]>([]);
  const [, setRuns] = useState<SegmentationRun[]>([]);
  const [activeRun, setActiveRun] = useState<SegmentationRun | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [executionStep, setExecutionStep] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const segmentIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Clear any in-flight interval on unmount
  useEffect(() => () => { if (segmentIntervalRef.current) clearInterval(segmentIntervalRef.current); }, []);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [desiredClusters, setDesiredClusters] = useState<number>(3);

  // Selection & Deep Dive
  const [selectedSegment, setSelectedSegment] = useState<MarketSegment | null>(null);
  const [modalTab, setModalTab] = useState<'overview' | 'observed' | 'evidence' | 'provenance'>('overview');
  const [comparedSegmentIds, setComparedSegmentIds] = useState<string[]>([]);
  const [comparisonResult, setComparisonResult] = useState<SegmentComparisonResult | null>(null);
  const [isComparing, setIsComparing] = useState<boolean>(false);
  const detailDialogRef = useRef<HTMLDivElement | null>(null);
  const compareDialogRef = useRef<HTMLDivElement | null>(null);
  useDialogA11y(detailDialogRef, !!selectedSegment, () => setSelectedSegment(null));
  useDialogA11y(compareDialogRef, isComparing && !!comparisonResult, () => setIsComparing(false));

  const executionSteps = [
    'Analysing study datasets and profiles',
    'Selecting high-signal variables',
    'Grouping your market into distinct customer segments…',
    'Building qualitative profiles and evidence links',
    'Segmentation complete',
  ];

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [readinessData, segmentsData, runsData] = await Promise.all([
        api.getSegmentationReadiness(studyId),
        api.listStudySegments(studyId),
        api.listSegmentationRuns(studyId),
      ]);
      setReadiness(readinessData);
      setSegments(segmentsData);
      setRuns(runsData);
      if (runsData.length > 0) {
        setActiveRun(runsData[0]);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load segmentation data.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [studyId]);

  const handleRunSegmentation = async () => {
    setIsExecuting(true);
    setError(null);
    setExecutionStep(0);

    const stepInterval = setInterval(() => {
      setExecutionStep((prev) => (prev < 3 ? prev + 1 : prev));
    }, 600);
    segmentIntervalRef.current = stepInterval;

    try {
      const result = await api.runSegmentation(studyId, { desired_clusters: desiredClusters });
      clearInterval(stepInterval);
      setExecutionStep(4);
      setActiveRun(result.run);
      setSegments(result.segments);
      const updatedRuns = await api.listSegmentationRuns(studyId);
      setRuns(updatedRuns);
    } catch (err: any) {
      clearInterval(stepInterval);
      setError(err.message || 'Segmentation failed.');
    } finally {
      setIsExecuting(false);
    }
  };

  const handleToggleCompare = (segId: string) => {
    setComparedSegmentIds((prev) => {
      if (prev.includes(segId)) {
        return prev.filter((id) => id !== segId);
      }
      if (prev.length >= 4) {
        return prev;
      }
      return [...prev, segId];
    });
  };

  const handleOpenComparisonModal = async () => {
    if (comparedSegmentIds.length < 2) return;
    try {
      const comp = await api.compareSegments(studyId, comparedSegmentIds);
      setComparisonResult(comp);
      setIsComparing(true);
    } catch (err: any) {
      setError(err.message || 'Failed to compare segments.');
    }
  };

  const handleExportJSON = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(segments, null, 2));
    const dlAnchorElem = document.createElement('a');
    dlAnchorElem.setAttribute('href', dataStr);
    dlAnchorElem.setAttribute('download', `study_${studyId}_market_segments.json`);
    dlAnchorElem.click();
  };

  const handleExportCSV = () => {
    if (segments.length === 0) return;
    const headers = ['id', 'name', 'cluster_label', 'population_percentage', 'population_count', 'confidence_score', 'status', 'description'];
    const rows = segments.map((s) => [
      s.id,
      `"${s.name.replace(/"/g, '""')}"`,
      s.cluster_label,
      s.population_percentage,
      s.population_count,
      s.confidence_score,
      s.status,
      `"${s.description.replace(/"/g, '""')}"`,
    ]);
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((e) => e.join(','))].join('\n');
    const dlAnchorElem = document.createElement('a');
    dlAnchorElem.setAttribute('href', encodeURI(csvContent));
    dlAnchorElem.setAttribute('download', `study_${studyId}_market_segments.csv`);
    dlAnchorElem.click();
  };

  const filteredSegments = useMemo(() => {
    return segments.filter((s) => {
      const matchesSearch =
        s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (s.differentiation_summary && s.differentiation_summary.toLowerCase().includes(searchQuery.toLowerCase()));
      const matchesStatus = statusFilter === 'all' || s.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [segments, searchQuery, statusFilter]);

  const totalSurveyed = readiness?.total_records || segments.reduce((acc, s) => acc + s.population_count, 0);

  return (
    <div className="space-y-6 animate-fadeIn pb-16" data-testid="segmentation-view">
      {isLoading && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '48px 24px', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Loading segmentation data…
        </div>
      )}
      {error && !isLoading && (
        <div
          role="alert"
          style={{
            background: 'rgba(239,68,68,0.08)',
            border: '1px solid rgba(239,68,68,0.4)',
            borderRadius: '10px',
            padding: '14px 18px',
            marginBottom: '16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            color: 'var(--status-error-text)',
            fontSize: '0.88rem',
          }}
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={loadData}
            style={{ background: 'transparent', border: '1px solid currentColor', borderRadius: '6px', padding: '4px 12px', color: 'inherit', cursor: 'pointer', fontWeight: 600, fontSize: '0.82rem', whiteSpace: 'nowrap' }}
          >
            Retry
          </button>
        </div>
      )}
      {/* Top Banner / Metrics Header */}
      <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-teal-500/5 rounded-full blur-3xl pointer-events-none" />
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 relative z-10">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="p-2.5 bg-teal-500/10 border border-teal-500/30 rounded-lg text-teal-400">
                <PieChart className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-[var(--text-primary)] tracking-tight">Market Segmentation</h1>
                <p className="text-sm text-[var(--text-secondary)]">
                  Evidence + Dataset Profiles + Business Context → Market Segments
                </p>
              </div>
            </div>
          </div>

          {/* Quick Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-[var(--bg-card)] border border-[var(--border-subtle)] px-4 py-2.5 rounded-lg">
              <span className="text-xs text-[var(--text-secondary)] block font-medium">Dataset Cohort</span>
              <span className="text-lg font-bold text-teal-400 font-mono">
                {totalSurveyed.toLocaleString()} <span className="text-xs text-[var(--text-secondary)] font-normal">records</span>
              </span>
            </div>
            <div className="bg-[var(--bg-card)] border border-[var(--border-subtle)] px-4 py-2.5 rounded-lg">
              <span className="text-xs text-[var(--text-secondary)] block font-medium">Segments Built</span>
              <span className="text-lg font-bold text-[var(--accent-cyan)] font-mono">{segments.length}</span>
            </div>
            <div className="bg-[var(--bg-card)] border border-[var(--border-subtle)] px-4 py-2.5 rounded-lg">
              <span className="text-xs text-[var(--text-secondary)] block font-medium">Data Readiness</span>
              <span
                className={`text-sm font-semibold capitalize mt-0.5 block ${
                  readiness?.status === 'ready'
                    ? 'text-emerald-400'
                    : readiness?.status === 'insufficient_records'
                    ? 'text-amber-400'
                    : 'text-rose-400'
                }`}
              >
                {readiness?.status?.replace(/_/g, ' ') || 'Checking...'}
              </span>
            </div>
            <div className="bg-[var(--bg-card)] border border-[var(--border-subtle)] px-4 py-2.5 rounded-lg">
              <span className="text-xs text-[var(--text-secondary)] block font-medium">Algorithm</span>
              <span className="text-xs font-semibold text-[var(--text-primary)] mt-1 block leading-snug">
                Quantile Clustering
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="bg-rose-500/10 border border-rose-500/30 p-4 rounded-xl flex items-center justify-between text-rose-300 text-sm">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 flex-shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
          <button type="button" onClick={() => setError(null)} aria-label="Dismiss error" className="text-rose-400 hover:text-rose-200">
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      )}

      {/* Pre-Segmentation Readiness Card */}
      {readiness && (
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-xl p-5 shadow-lg">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div
                className={`p-2 rounded-lg mt-0.5 ${
                  readiness.status === 'ready'
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                    : readiness.status === 'insufficient_records'
                    ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                    : 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                }`}
              >
                {readiness.status === 'ready' ? (
                  <CheckCircle2 className="w-5 h-5" />
                ) : readiness.status === 'insufficient_records' ? (
                  <HelpCircle className="w-5 h-5" />
                ) : (
                  <AlertCircle className="w-5 h-5" />
                )}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-semibold text-[var(--text-primary)]">Pre-Segmentation Assessment</h2>
                  <span
                    className={`text-xs px-2.5 py-0.5 rounded-full font-medium uppercase tracking-wider ${
                      readiness.status === 'ready'
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                        : readiness.status === 'insufficient_records'
                        ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                        : 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                    }`}
                  >
                    {readiness.status.replace(/_/g, ' ')}
                  </span>
                </div>
                <p className="text-xs text-[var(--text-secondary)] mt-1 max-w-3xl leading-relaxed">
                  {readiness.guidance_message}
                </p>

                {/* Usable Variables Badges */}
                {readiness.usable_variables.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 mt-3">
                    <span className="text-xs text-[var(--text-secondary)] font-medium mr-1">Candidate Variables:</span>
                    {readiness.usable_variables.map((v) => (
                      <span
                        key={v.name}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[var(--bg-card)] border border-[var(--border-subtle)] text-xs text-[var(--text-primary)]"
                        title={`${v.source_dataset_name} • ${v.coverage_percentage}% coverage`}
                      >
                        <span className="text-teal-400 font-mono font-medium">{v.name}</span>
                        <span className="text-[0.72rem] text-[var(--text-secondary)] bg-[var(--bg-pure)] px-1 rounded">
                          {v.coverage_percentage}%
                        </span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Run Controls */}
            <div className="flex items-center gap-3 self-end md:self-center flex-shrink-0">
              <div className="flex items-center gap-2 bg-[var(--bg-card)] border border-[var(--border-subtle)] px-3 py-1.5 rounded-lg">
                <span className="text-xs text-[var(--text-secondary)] font-medium">Clusters:</span>
                <select
                  value={desiredClusters}
                  onChange={(e) => setDesiredClusters(Number(e.target.value))}
                  disabled={isExecuting}
                  className="bg-[var(--bg-pure)] border border-[var(--border-subtle)] rounded text-xs text-[var(--text-primary)] pl-2 pr-7 py-1 focus:outline-none focus:border-teal-500 font-mono"
                  data-testid="cluster-count-select"
                >
                  <option value={2}>2 Segments</option>
                  <option value={3}>3 Segments</option>
                  <option value={4}>4 Segments</option>
                </select>
              </div>

              <button
                onClick={handleRunSegmentation}
                disabled={isExecuting || !readiness.can_run}
                data-testid="run-segmentation-btn"
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-xs tracking-wide transition-all shadow-md ${
                  isExecuting || !readiness.can_run
                    ? 'bg-teal-500/30 text-teal-300/50 cursor-not-allowed border border-teal-500/20'
                    : 'bg-teal-500 text-[var(--bg-pure)] hover:bg-teal-400 active:scale-95 shadow-teal-500/20'
                }`}
              >
                {isExecuting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Running Clustering...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Run Segmentation</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Execution Stepper */}
      {isExecuting && (
        <div className="bg-[var(--bg-secondary)] border border-teal-500/40 rounded-xl p-5 shadow-xl animate-pulse">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-teal-400 flex items-center gap-2">
              <RefreshCw className="w-4 h-4 animate-spin text-teal-400" />
              Segmentation Engine in Progress
            </h3>
            <span className="text-xs font-mono text-[var(--text-secondary)]">
              Step {executionStep + 1} of {executionSteps.length}
            </span>
          </div>
          <div className="space-y-2">
            {executionSteps.map((step, idx) => (
              <div key={step} className="flex items-center gap-3">
                <div
                  className={`w-5 h-5 rounded-full flex items-center justify-center text-[0.72rem] font-bold ${
                    idx < executionStep
                      ? 'bg-emerald-500 text-[var(--bg-pure)]'
                      : idx === executionStep
                      ? 'bg-teal-500 text-[var(--bg-pure)] ring-2 ring-teal-500/30'
                      : 'bg-[var(--bg-card)] text-[var(--text-secondary)] border border-[var(--border-subtle)]'
                  }`}
                >
                  {idx < executionStep ? '✓' : idx + 1}
                </div>
                <span
                  className={`text-xs ${
                    idx === executionStep
                      ? 'text-[var(--text-primary)] font-semibold'
                      : idx < executionStep
                      ? 'text-emerald-400/80'
                      : 'text-[var(--text-secondary)]'
                  }`}
                >
                  {step}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filter and Action Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-3.5 rounded-xl">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          {/* Search Box */}
          <div className="relative flex-1 sm:w-64">
            <Search className="w-4 h-4 text-[var(--text-secondary)] absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search segments, needs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-lg pl-9 pr-3 py-1.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-secondary)] focus:outline-none focus:border-teal-500"
              data-testid="search-segments-input"
            />
          </div>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-lg text-xs text-[var(--text-primary)] pl-3 pr-8 py-1.5 focus:outline-none focus:border-teal-500"
            data-testid="status-filter-select"
          >
            <option value="all">All Statuses</option>
            <option value="data_backed">Data Backed</option>
            <option value="inference_assisted">Inference Assisted</option>
          </select>
        </div>

        {/* Actions (Export & Compare) */}
        <div className="flex items-center gap-2 self-end sm:self-center">
          {comparedSegmentIds.length >= 2 && (
            <button
              onClick={handleOpenComparisonModal}
              data-testid="compare-selected-btn"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-teal-500/20 text-teal-300 border border-teal-500/40 text-xs font-semibold hover:bg-teal-500/30 transition-colors"
            >
              <Sliders className="w-3.5 h-3.5" />
              <span>Compare Selected ({comparedSegmentIds.length})</span>
            </button>
          )}

          <button
            onClick={handleExportJSON}
            disabled={segments.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--bg-card)] border border-[var(--border-subtle)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-teal-500/40 transition-colors"
            title="Export as JSON"
            data-testid="export-json-btn"
          >
            <Download className="w-3.5 h-3.5" />
            <span>JSON</span>
          </button>

          <button
            onClick={handleExportCSV}
            disabled={segments.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--bg-card)] border border-[var(--border-subtle)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-teal-500/40 transition-colors"
            title="Export as CSV"
            data-testid="export-csv-btn"
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            <span>CSV</span>
          </button>
        </div>
      </div>

      {/* Segments Grid */}
      {filteredSegments.length === 0 ? (
        <div
          className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-xl p-12 text-center text-[var(--text-secondary)]"
          data-testid="no-segments-placeholder"
        >
          <PieChart className="w-12 h-12 text-[var(--text-secondary)]/40 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-[var(--text-primary)]">No Market Segments Available</h3>
          <p className="text-xs text-[var(--text-secondary)] max-w-md mx-auto mt-1 mb-5">
            Run segmentation above or upload your own study data to discover meaningful customer clusters.
          </p>
          <div className="flex items-center justify-center gap-3">
            {onNavigateToEvidence && (
              <button
                onClick={onNavigateToEvidence}
                className="px-4 py-2 rounded-lg bg-[var(--bg-card)] border border-[var(--border-subtle)] text-xs text-[var(--accent-cyan)] hover:border-cyan-500 transition-colors"
              >
                Inspect Evidence Lab
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="segments-grid">
          {filteredSegments.map((segment) => {
            const isCompared = comparedSegmentIds.includes(segment.id);
            const facts = observedFacts(segment);

            return (
              <div
                key={segment.id}
                data-testid={`segment-card-${segment.id}`}
                className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] hover:border-teal-500/40 rounded-xl p-5 transition-all shadow-lg flex flex-col justify-between group relative overflow-hidden"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-teal-500/5 rounded-full blur-2xl pointer-events-none group-hover:bg-teal-500/10 transition-colors" />

                <div>
                  {/* Card Header & Checkbox */}
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleToggleCompare(segment.id)}
                        className="text-[var(--text-secondary)] hover:text-teal-400 transition-colors"
                        title="Select for comparison"
                        data-testid={`compare-checkbox-${segment.id}`}
                      >
                        {isCompared ? (
                          <CheckSquare className="w-4 h-4 text-teal-400" />
                        ) : (
                          <Square className="w-4 h-4" />
                        )}
                      </button>
                      <span className="text-[0.72rem] font-mono uppercase tracking-wider bg-[var(--bg-card)] border border-[var(--border-subtle)] text-teal-400 px-2 py-0.5 rounded">
                        {segment.cluster_label}
                      </span>
                    </div>

                    <span
                      className={`text-[0.72rem] font-semibold px-2 py-0.5 rounded-full border ${
                        segment.status === 'data_backed'
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                      }`}
                    >
                      {segment.status === 'data_backed' ? 'Data Backed' : 'Inference Assisted'}
                    </span>
                  </div>

                  {/* Title & Population Share */}
                  <h3 className="text-base font-bold text-[var(--text-primary)] group-hover:text-teal-300 transition-colors line-clamp-1">
                    {segment.name}
                  </h3>

                  {/* Population Progress Bar */}
                  <div className="mt-2.5 mb-3.5">
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-[var(--text-secondary)]">Population Share</span>
                      <span className="text-[var(--text-primary)] font-mono font-semibold">
                        {segment.population_percentage}%{' '}
                        <span className="text-[var(--text-secondary)] font-normal">
                          ({segment.population_count.toLocaleString()} rows)
                        </span>
                      </span>
                    </div>
                    <div className="h-1.5 w-full bg-[var(--bg-card)] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-teal-500 to-cyan-400 rounded-full"
                        style={{ width: `${Math.min(100, segment.population_percentage)}%` }}
                      />
                    </div>
                  </div>

                  {/* Short Description */}
                  <p className="text-xs text-[var(--text-secondary)] line-clamp-2 leading-relaxed mb-4">
                    {segment.description}
                  </p>

                  {/* Observed facts — only what the dataset measured for this cluster */}
                  <div className="grid grid-cols-2 gap-2 bg-[var(--bg-card)] border border-[var(--border-subtle)] p-2.5 rounded-lg mb-4 text-xs">
                    <div>
                      <span className="text-[0.72rem] text-[var(--text-secondary)] block">
                        {facts.partitionLabel}
                      </span>
                      <span className="font-semibold text-teal-400 font-mono">{facts.headline}</span>
                    </div>
                    <div>
                      <span className="text-[0.72rem] text-[var(--text-secondary)] block">Median</span>
                      <span className="font-semibold text-[var(--text-primary)] font-mono">{facts.median}</span>
                    </div>
                    <div>
                      <span className="text-[0.72rem] text-[var(--text-secondary)] block">Dominant traits</span>
                      <span className="font-semibold text-[var(--text-primary)] line-clamp-2">{facts.dominant}</span>
                    </div>
                    <div>
                      <span className="text-[0.72rem] text-[var(--text-secondary)] block">Confidence</span>
                      <span className="font-semibold text-cyan-400 font-mono">
                        {Math.round(segment.confidence_score * 100)}%
                      </span>
                    </div>
                  </div>
                </div>

                {/* Card Footer Actions */}
                <div className="flex items-center justify-between pt-3 border-t border-[var(--border-subtle)] gap-2">
                  <div className="flex items-center gap-1.5 text-xs text-[var(--text-secondary)]">
                    <FileText className="w-3.5 h-3.5 text-teal-400" />
                    <span>{segment.evidence_citations?.length || 0} citations</span>
                  </div>

                  <button
                    onClick={() => {
                      setSelectedSegment(segment);
                      setModalTab('overview');
                    }}
                    data-testid={`deep-dive-btn-${segment.id}`}
                    className="flex items-center gap-1 text-xs text-teal-400 hover:text-teal-300 font-medium transition-colors"
                  >
                    <span>Deep Dive</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Floating Comparison Sticky Bar */}
      {comparedSegmentIds.length >= 2 && (
        <div
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 bg-[var(--bg-secondary)] border border-teal-500/50 rounded-xl px-5 py-3 shadow-2xl flex items-center gap-4 animate-slideUp backdrop-blur-md"
          data-testid="floating-compare-bar"
        >
          <span className="text-xs font-semibold text-[var(--text-primary)]">
            {comparedSegmentIds.length} segments selected for side-by-side comparison
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setComparedSegmentIds([])}
              className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] px-2 py-1"
            >
              Clear
            </button>
            <button
              onClick={handleOpenComparisonModal}
              className="px-3.5 py-1.5 bg-teal-500 text-[var(--bg-pure)] font-bold text-xs rounded-lg hover:bg-teal-400 transition-colors shadow-lg"
            >
              Compare Now
            </button>
          </div>
        </div>
      )}

      {/* Side-by-Side Comparison Modal */}
      {isComparing && comparisonResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="fixed inset-0 bg-[var(--scrim)] bx-backdrop"
            onClick={() => setIsComparing(false)}
            data-testid="compare-modal-backdrop"
          />
          <div
            ref={compareDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="segment-compare-title"
            className="relative z-10 w-full max-w-5xl bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] bx-modal"
            data-testid="comparison-modal"
          >
            <div className="p-5 border-b border-[var(--border-subtle)] flex items-center justify-between bg-[var(--bg-card)]">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-teal-500/10 text-teal-400 rounded-lg">
                  <Sliders className="w-5 h-5" />
                </div>
                <div>
                  <h3 id="segment-compare-title" className="text-lg font-bold text-[var(--text-primary)]">Side-by-Side Segment Comparison</h3>
                  <p className="text-xs text-[var(--text-secondary)]">
                    Comparing {comparisonResult.compared_count} segments on shared dimensions
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsComparing(false)}
                aria-label="Close segment comparison"
                className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] p-1.5 rounded-lg hover:bg-[var(--border-subtle)]"
              >
                <X className="w-5 h-5" aria-hidden="true" />
              </button>
            </div>

            <div className="p-6 overflow-x-auto overflow-y-auto space-y-6">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border-subtle)]">
                    <th className="p-3 text-[var(--text-secondary)] font-medium w-44">Dimension</th>
                    {comparisonResult.comparison_matrix.map((c) => (
                      <th key={c.segment_id} className="p-3 text-teal-400 font-bold min-w-[200px]">
                        {c.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-subtle)]/60">
                  <tr>
                    <td className="p-3 text-[var(--text-secondary)] font-medium">Cluster Label</td>
                    {comparisonResult.comparison_matrix.map((c) => (
                      <td key={c.segment_id} className="p-3 font-mono text-[var(--text-primary)]">
                        {c.cluster_label}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="p-3 text-[var(--text-secondary)] font-medium">Population Share</td>
                    {comparisonResult.comparison_matrix.map((c) => (
                      <td key={c.segment_id} className="p-3 font-semibold text-teal-400 font-mono">
                        {c.population_percentage}% ({c.population_count.toLocaleString()} rows)
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="p-3 text-[var(--text-secondary)] font-medium">Partition variable</td>
                    {comparisonResult.comparison_matrix.map((c) => (
                      <td key={c.segment_id} className="p-3 font-mono text-[var(--accent-cyan)] font-bold">
                        {c.partition_variable ? c.partition_variable.replace(/_/g, ' ') : 'categorical grouping'}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="p-3 text-[var(--text-secondary)] font-medium">Observed range</td>
                    {comparisonResult.comparison_matrix.map((c) => (
                      <td key={c.segment_id} className="p-3 text-[var(--text-primary)] font-mono">
                        {c.headline_range ?? '— not measured'}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="p-3 text-[var(--text-secondary)] font-medium">Observed median</td>
                    {comparisonResult.comparison_matrix.map((c) => (
                      <td key={c.segment_id} className="p-3 text-[var(--text-primary)] font-mono">
                        {c.headline_median != null ? fmt(c.headline_median) : '— not measured'}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="p-3 text-[var(--text-secondary)] font-medium">Dominant categories</td>
                    {comparisonResult.comparison_matrix.map((c) => (
                      <td key={c.segment_id} className="p-3 text-[var(--text-primary)]">
                        {Object.entries(c.top_categories || {}).length
                          ? Object.entries(c.top_categories).map(([k, v]) => `${k}: ${v}`).join(' · ')
                          : '— none observed'}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="p-3 text-[var(--text-secondary)] font-medium">Variables measured</td>
                    {comparisonResult.comparison_matrix.map((c) => (
                      <td key={c.segment_id} className="p-3 text-[var(--text-secondary)] font-mono text-xs">
                        {(c.observed_variables || []).join(', ') || '—'}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="p-3 text-[var(--text-secondary)] font-medium">Evidence Citations</td>
                    {comparisonResult.comparison_matrix.map((c) => (
                      <td key={c.segment_id} className="p-3 text-emerald-400 font-semibold">
                        {c.evidence_citations_count} claims cited
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="p-3 text-[var(--text-secondary)] font-medium">Differentiation Rationale</td>
                    {comparisonResult.comparison_matrix.map((c) => (
                      <td key={c.segment_id} className="p-3 text-[var(--text-secondary)] leading-relaxed">
                        {c.differentiation}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="p-4 border-t border-[var(--border-subtle)] bg-[var(--bg-card)] flex justify-end">
              <button
                onClick={() => setIsComparing(false)}
                className="px-4 py-2 rounded-lg bg-[var(--border-subtle)] text-[var(--text-primary)] text-xs font-semibold hover:bg-[var(--border-subtle)]/80"
              >
                Close Comparison
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Deep Dive Inspection Modal / Drawer */}
      {selectedSegment && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="fixed inset-0 bg-[var(--scrim)] bx-backdrop"
            onClick={() => setSelectedSegment(null)}
            data-testid="detail-modal-backdrop"
          />
          <div
            ref={detailDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="segment-detail-title"
            className="relative z-10 w-full max-w-3xl bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] bx-modal"
            data-testid="segment-detail-modal"
          >
            {/* Modal Header */}
            <div className="p-6 border-b border-[var(--border-subtle)] bg-[var(--bg-card)] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-teal-500/10 text-teal-400 border border-teal-500/30 rounded-xl">
                  <PieChart className="w-6 h-6" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 id="segment-detail-title" className="text-lg font-bold text-[var(--text-primary)]">{selectedSegment.name}</h3>
                    <span className="text-xs px-2 py-0.5 rounded bg-[var(--bg-pure)] border border-[var(--border-subtle)] text-teal-400 font-mono">
                      {selectedSegment.cluster_label}
                    </span>
                  </div>
                  <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                    {selectedSegment.population_percentage}% population • {selectedSegment.population_count.toLocaleString()} dataset records
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedSegment(null)}
                aria-label="Close segment details"
                className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] p-1.5 rounded-lg hover:bg-[var(--border-subtle)]"
                data-testid="close-detail-modal-btn"
              >
                <X className="w-5 h-5" aria-hidden="true" />
              </button>
            </div>

            {/* Modal Navigation Tabs */}
            <div className="flex items-center gap-2 px-6 pt-3 border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)] overflow-x-auto">
              {[
                { id: 'overview', label: 'Overview' },
                { id: 'observed', label: 'Observed variables' },
                { id: 'evidence', label: `Evidence (${selectedSegment.evidence_citations?.length || 0})` },
                { id: 'provenance', label: 'Dataset Provenance' },
              ].map((t) => (
                <button
                  key={t.id}
                  onClick={() => setModalTab(t.id as any)}
                  data-testid={`modal-tab-${t.id}`}
                  className={`px-3.5 py-2 text-xs font-semibold border-b-2 whitespace-nowrap transition-colors ${
                    modalTab === t.id
                      ? 'border-teal-400 text-teal-400'
                      : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Modal Tab Content */}
            <div className="p-6 overflow-y-auto space-y-6 text-xs text-[var(--text-primary)]">
              {modalTab === 'overview' && (
                <div className="space-y-5" data-testid="tab-content-overview">
                  <div>
                    <h4 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-2">
                      Segment Description
                    </h4>
                    <p className="bg-[var(--bg-card)] border border-[var(--border-subtle)] p-3.5 rounded-lg leading-relaxed text-[var(--text-primary)]">
                      {selectedSegment.description}
                    </p>
                  </div>

                  {selectedSegment.differentiation_summary && (
                    <div>
                      <h4 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-2">
                        Key Differentiation Rationale
                      </h4>
                      <p className="bg-[var(--bg-card)] border border-[var(--border-subtle)] p-3.5 rounded-lg leading-relaxed text-teal-300">
                        {selectedSegment.differentiation_summary}
                      </p>
                    </div>
                  )}

                  <div>
                    <h4 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-2">
                      Interpretation provenance
                    </h4>
                    <p className="bg-[var(--bg-card)] border border-[var(--border-subtle)] p-2.5 rounded-lg text-[var(--text-secondary)]">
                      {selectedSegment.characteristics?.served_by
                        ? `Name and description written by ${selectedSegment.characteristics.served_by} from this cluster's observed statistics.`
                        : 'Name and description written by the model from this cluster\u2019s observed statistics.'}
                    </p>
                  </div>
                </div>
              )}

              {modalTab === 'observed' && (
                <div className="space-y-4" data-testid="tab-content-observed">
                  <div className="bg-[var(--bg-card)] border border-[var(--border-subtle)] p-3.5 rounded-lg">
                    <span className="text-[0.72rem] text-[var(--text-secondary)] block uppercase font-bold">How this cluster was formed</span>
                    <span className="text-sm font-semibold text-[var(--text-primary)] mt-1 block">
                      {selectedSegment.characteristics?.partition_method === 'quantile_bands'
                        ? `Quantile band of ${String(selectedSegment.characteristics.partition_variable).replace(/_/g, ' ')}` +
                          (selectedSegment.characteristics.band
                            ? ` (${fmt(selectedSegment.characteristics.band.lower)} – ${fmt(selectedSegment.characteristics.band.upper)})`
                            : '')
                        : selectedSegment.characteristics?.partition_method === 'categorical_grouping'
                        ? `Rows sharing a value of the grouping column`
                        : 'Partition method not recorded'}
                    </span>
                    {selectedSegment.characteristics?.rule_description && (
                      <p className="text-[0.72rem] text-[var(--text-secondary)] font-mono mt-1">
                        {selectedSegment.characteristics.rule_description}
                      </p>
                    )}
                  </div>

                  {Object.entries(
                    (selectedSegment.characteristics?.observed || selectedSegment.variable_distributions || {}) as Record<string, ObservedDistribution>
                  ).filter(([, d]) => d && typeof d === 'object').length === 0 ? (
                    <p className="bg-[var(--bg-card)] border border-[var(--border-subtle)] p-3.5 rounded-lg text-[var(--text-secondary)] text-center">
                      The dataset carried no further variables for this cluster — nothing is assumed in their place.
                    </p>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {Object.entries(
                        (selectedSegment.characteristics?.observed || selectedSegment.variable_distributions || {}) as Record<string, ObservedDistribution>
                      )
                        .filter(([, d]) => d && typeof d === 'object')
                        .map(([name, d]) => (
                          <div key={name} className="bg-[var(--bg-card)] border border-[var(--border-subtle)] p-3.5 rounded-lg">
                            <span className="text-[0.72rem] text-teal-400 font-semibold block font-mono">{name}</span>
                            {typeof d.median === 'number' ? (
                              <div className="mt-1 grid grid-cols-3 gap-2 text-[var(--text-primary)] font-mono">
                                <span><span className="text-[var(--text-secondary)] text-[0.7rem] block">min</span>{fmt(d.min)}</span>
                                <span><span className="text-[var(--text-secondary)] text-[0.7rem] block">median</span>{fmt(d.median)}</span>
                                <span><span className="text-[var(--text-secondary)] text-[0.7rem] block">max</span>{fmt(d.max)}</span>
                              </div>
                            ) : Array.isArray(d.top_categories) && d.top_categories.length > 0 ? (
                              <ul className="mt-1 space-y-0.5">
                                {d.top_categories.slice(0, 4).map((cat) => (
                                  <li key={cat.category} className="flex justify-between text-[var(--text-primary)]">
                                    <span className="truncate">{cat.category}</span>
                                    <span className="font-mono text-[var(--text-secondary)]">{cat.percentage}%</span>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <span className="text-[var(--text-secondary)]">—</span>
                            )}
                            {typeof d.count === 'number' && (
                              <span className="text-[0.7rem] text-[var(--text-secondary)] block mt-1">{d.count.toLocaleString()} observations</span>
                            )}
                          </div>
                        ))}
                    </div>
                  )}
                </div>
              )}

              {modalTab === 'evidence' && (
                <div className="space-y-3" data-testid="tab-content-evidence">
                  {(selectedSegment.evidence_citations || []).length === 0 ? (
                    <p className="text-[var(--text-secondary)] text-center py-6">No specific evidence claims attached to this segment.</p>
                  ) : (
                    selectedSegment.evidence_citations.map((cite, idx) => (
                      <div
                        key={idx}
                        className="bg-[var(--bg-card)] border border-[var(--border-subtle)] p-3.5 rounded-lg space-y-1.5"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-[0.72rem] font-mono uppercase text-teal-400 font-semibold">
                            {cite.category}
                          </span>
                          <span className="text-[0.72rem] text-emerald-400 font-mono">
                            {cite.confidence != null ? `${Math.round(cite.confidence * 100)}% confidence` : 'confidence n/a'}
                          </span>
                        </div>
                        <p className="text-xs text-[var(--text-primary)] font-medium leading-relaxed">
                          "{cite.claim_text}"
                        </p>
                        {cite.rationale && (
                          <p className="text-[0.72rem] text-[var(--text-secondary)] italic">{cite.rationale}</p>
                        )}
                      </div>
                    ))
                  )}
                </div>
              )}

              {modalTab === 'provenance' && (
                <div className="space-y-4" data-testid="tab-content-provenance">
                  <div className="bg-[var(--bg-card)] border border-[var(--border-subtle)] p-3.5 rounded-lg space-y-2">
                    <div className="flex items-center justify-between text-[0.72rem]">
                      <span className="text-[var(--text-secondary)]">Segmentation Run ID</span>
                      <span className="font-mono text-teal-400">{selectedSegment.segmentation_run_id}</span>
                    </div>
                    <div className="flex items-center justify-between text-[0.72rem]">
                      <span className="text-[var(--text-secondary)]">Created Timestamp</span>
                      <span className="font-mono text-[var(--text-primary)]">{new Date(selectedSegment.created_at).toLocaleString()}</span>
                    </div>
                    <div className="flex items-center justify-between text-[0.72rem]">
                      <span className="text-[var(--text-secondary)]">Status</span>
                      <span className="font-semibold text-emerald-400">{selectedSegment.status}</span>
                    </div>
                  </div>

                  {activeRun?.dataset_versions && activeRun.dataset_versions.length > 0 && (
                    <div>
                      <h5 className="text-[0.72rem] uppercase font-bold text-[var(--text-secondary)] mb-2">Connected Dataset Versions</h5>
                      <div className="space-y-2">
                        {activeRun.dataset_versions.map((ds) => (
                          <div
                            key={ds.dataset_id}
                            className="bg-[var(--bg-card)] border border-[var(--border-subtle)] p-3 rounded-lg flex items-center justify-between text-[0.72rem]"
                          >
                            <div>
                              <span className="font-semibold text-[var(--text-primary)] flex items-center gap-2">
                                {ds.name}
                                {ds.is_sample && (
                                  <span
                                    title="Illustrative sample catalog — modeled on public sources, not fetched live."
                                    style={{ fontSize: '0.72rem', fontWeight: 400, color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', border: '1px solid var(--border-medium)', padding: '2px 6px', borderRadius: '4px', fontFamily: 'var(--font-mono)', letterSpacing: '0.06em' }}
                                  >
                                    SAMPLE
                                  </span>
                                )}
                              </span>
                              <span className="text-[var(--text-secondary)] font-mono text-[0.72rem]">
                                Hash: {ds.content_hash}
                              </span>
                            </div>
                            <span className="text-teal-400 font-mono font-semibold">
                              {ds.row_count.toLocaleString()} rows
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-[var(--border-subtle)] bg-[var(--bg-card)] flex items-center justify-between">
              <button
                onClick={() => setSelectedSegment(null)}
                className="px-4 py-2 rounded-lg bg-[var(--border-subtle)] text-[var(--text-primary)] text-xs font-semibold hover:bg-[var(--border-subtle)]/80"
              >
                Close
              </button>

              {onProceedToPersonas && (
                <button
                  onClick={() => {
                    onProceedToPersonas(selectedSegment.id);
                    setSelectedSegment(null);
                  }}
                  className="px-4 py-2 rounded-lg bg-teal-500 text-[var(--bg-pure)] font-bold text-xs hover:bg-teal-400 transition-colors flex items-center gap-1.5 shadow-lg"
                >
                  <span>Build Personas for this Segment</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SegmentationView;
