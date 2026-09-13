import React, { useState, useEffect, useLayoutEffect, useRef } from 'react';
import {
  ArrowLeft,
  Sliders,
  Play,
  RotateCw,
  AlertTriangle,
  Sparkles,
  ShieldCheck,
  Layers,
  DollarSign,
  ShoppingCart,
  MessageSquare,
  Gift,
  RefreshCw,
  Lightbulb,
  X,
} from 'lucide-react';
import {
  BehavioralTest,
  BehavioralTestRun,
  BehavioralTestResult,
  BehavioralTestType,
  RunBehavioralTestPayload,
} from '../../../types';
import { api } from '../../../services/api';
import { useDialogA11y } from '../../../utils/useDialogA11y';
import { useRequestScope } from '../../../utils/useRequestScope';
import { pollSerial } from '../../../services/polling';
import { toUserMessage } from '../../../utils/apiError';
import { useRouteReady } from '../../../performance/routeTiming';

interface BehavioralTestDetailViewProps {
  studyId: string;
  testId: string;
  initialRunId?: string;
  onBack: () => void;
  onCompareRuns?: (runIds: string[]) => void;
  onNavigateToPersona?: (personaId: string) => void;
}

export const BehavioralTestDetailView: React.FC<BehavioralTestDetailViewProps> = ({
  studyId,
  testId,
  initialRunId,
  onBack,
  onCompareRuns,
  onNavigateToPersona: _onNavigateToPersona,
}) => {
  const [test, setTest] = useState<BehavioralTest | null>(null);
  const [runs, setRuns] = useState<BehavioralTestRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>(initialRunId || '');
  const [activeRun, setActiveRun] = useState<BehavioralTestRun | null>(null);
  const [pollAttempt, setPollAttempt] = useState(0);
  const [selectedPersonaResult, setSelectedPersonaResult] = useState<BehavioralTestResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingRun, setIsLoadingRun] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [isTriggeringRun, setIsTriggeringRun] = useState(false);

  const scopeRef = useRequestScope([studyId, testId]);
  const selectionRef = useRef(initialRunId || '');
  const requestRef = useRef(0);
  const actionRef = useRef(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  useRouteReady(!isLoading, loadError ? 'error' : test ? 'content' : 'empty');
  const resultDialogRef = useRef<HTMLDivElement | null>(null);
  useDialogA11y(resultDialogRef, !!selectedPersonaResult, () => setSelectedPersonaResult(null));

  useLayoutEffect(() => {
    selectionRef.current = initialRunId || '';
    requestRef.current += 1;
    actionRef.current = false;
    setSelectedRunId(initialRunId || '');
    setTest(null);
    setRuns([]);
    setActiveRun(null);
    setSelectedPersonaResult(null);
    setLoadError(null);
    setActionError(null);
    setIsLoadingRun(false);
    setIsRetrying(false);
    setIsTriggeringRun(false);
  }, [studyId, testId]);

  const fetchDetailAndRuns = async (keepLoading = true, restartPolling = false) => {
    const scope = scopeRef.current;
    const request = ++requestRef.current;
    const isCurrent = () => scope.active && request === requestRef.current;
    if (keepLoading) setIsLoading(true);
    setLoadError(null);
    try {
      const [testData, runList] = await Promise.all([
        api.getBehavioralTestDetail(studyId, testId, scope.controller.signal),
        api.getBehavioralTestRuns(studyId, testId, scope.controller.signal),
      ]);
      if (!isCurrent()) return;
      setTest(testData);
      setRuns(runList);

      const targetRunId = selectionRef.current || initialRunId || (runList.length > 0 ? runList[0].id : '');
      if (targetRunId) {
        selectionRef.current = targetRunId;
        setSelectedRunId(targetRunId);
        const runDetail = await api.getBehavioralRunResults(studyId, targetRunId, scope.controller.signal);
        if (isCurrent()) {
          setActiveRun(runDetail);
          if (restartPolling) setPollAttempt((attempt) => attempt + 1);
        }
      } else {
        setActiveRun(null);
      }
    } catch (error) {
      if (isCurrent()) setLoadError(toUserMessage(error));
    } finally {
      if (isCurrent()) setIsLoading(false);
    }
  };

  useEffect(() => {
    void fetchDetailAndRuns();
  }, [studyId, testId]);

  // Polling for active / running simulation runs
  useEffect(() => {
    if (!activeRun || !['pending', 'running'].includes(activeRun.status)) return;
    const scope = scopeRef.current;
    const controller = new AbortController();
    const runId = activeRun.id;
    const isCurrent = () => scope.active && !controller.signal.aborted && selectionRef.current === runId;
    void pollSerial<BehavioralTestRun>((signal) => api.getBehavioralRunResults(studyId, runId, signal), {
      signal: controller.signal, intervalMs: 2500, timeoutMs: 1800000, idleTimeoutMs: 300000, pauseWhenHidden: true,
      complete: (run) => !['pending', 'running'].includes(run.status),
      progress: (run) => `${run.status}:${run.completed_count}:${run.failed_count}`,
      onUpdate: (run) => {
        if (!isCurrent()) return;
        setActiveRun(run);
        setRuns((previous) => previous.map((candidate) => candidate.id === run.id ? run : candidate));
      },
    }).catch((error: unknown) => { if (isCurrent()) setLoadError(toUserMessage(error)); });
    return () => controller.abort();
  }, [activeRun?.status, activeRun?.id, studyId, testId, pollAttempt]);

  const handleSelectRun = async (runId: string) => {
    if (actionRef.current) return;
    const scope = scopeRef.current;
    const request = ++requestRef.current;
    selectionRef.current = runId;
    setSelectedRunId(runId);
    setSelectedPersonaResult(null);
    setActiveRun(null);
    setLoadError(null);
    setActionError(null);
    setIsLoadingRun(true);
    try {
      const runDetail = await api.getBehavioralRunResults(studyId, runId, scope.controller.signal);
      if (scope.active && request === requestRef.current) setActiveRun(runDetail);
    } catch (error) {
      if (scope.active && request === requestRef.current) setLoadError(toUserMessage(error));
    } finally {
      if (scope.active && request === requestRef.current) setIsLoadingRun(false);
    }
  };

  const handleTriggerNewRun = async () => {
    const scope = scopeRef.current;
    if (!test || !activeRun || !scope.active || actionRef.current || isLoadingRun || ['pending', 'running'].includes(activeRun.status)) return;
    const snapshot = activeRun.scenario_snapshot;
    const targetType = activeRun.target_population_type;
    const validScenario = typeof snapshot?.scenario_text === 'string' && snapshot.scenario_text.trim()
      && snapshot.structured_parameters != null && typeof snapshot.structured_parameters === 'object'
      && !Array.isArray(snapshot.structured_parameters);
    const validTarget = targetType === 'all'
      || (targetType === 'segment' && typeof activeRun.target_segment_id === 'string' && activeRun.target_segment_id.trim())
      || (targetType === 'selected_personas' && Array.isArray(activeRun.target_persona_ids)
        && activeRun.target_persona_ids.length > 0
        && activeRun.target_persona_ids.every((personaId) => typeof personaId === 'string' && personaId.trim()));
    if (!validScenario || !validTarget) {
      setActionError('The saved run configuration is incomplete. Return to Behavioral Tests to configure a new simulation with an explicit scenario and population.');
      return;
    }
    const payload: RunBehavioralTestPayload = {
      scenario_title: snapshot.title,
      scenario_text: snapshot.scenario_text,
      parameters: snapshot.structured_parameters,
      target_population_type: targetType,
      ...(targetType === 'segment' ? { target_segment_id: activeRun.target_segment_id! } : {}),
      ...(targetType === 'selected_personas' ? { target_persona_ids: [...activeRun.target_persona_ids] } : {}),
    };
    actionRef.current = true;
    setIsTriggeringRun(true);
    setActionError(null);
    setLoadError(null);
    try {
      const newRun = await api.triggerBehavioralTestRun(studyId, test.id, payload, scope.controller.signal);
      if (!scope.active) return;
      selectionRef.current = newRun.id;
      setSelectedRunId(newRun.id);
      setActiveRun(newRun);
      await fetchDetailAndRuns(false);
    } catch (error) {
      if (scope.active) setActionError(toUserMessage(error));
    } finally {
      if (scope.active) { actionRef.current = false; setIsTriggeringRun(false); }
    }
  };

  const handleRetryFailed = async () => {
    const scope = scopeRef.current;
    if (!activeRun || !scope.active || actionRef.current || isLoadingRun || ['pending', 'running'].includes(activeRun.status)) return;
    actionRef.current = true;
    setIsRetrying(true);
    setActionError(null);
    setLoadError(null);
    try {
      const retried = await api.retryFailedBehavioralRun(studyId, activeRun.id, scope.controller.signal);
      if (!scope.active) return;
      setActiveRun(retried);
      await fetchDetailAndRuns(false);
    } catch (error) {
      if (scope.active) setActionError(toUserMessage(error));
    } finally {
      if (scope.active) { actionRef.current = false; setIsRetrying(false); }
    }
  };

  const getTypeIcon = (type?: BehavioralTestType) => {
    switch (type) {
      case 'pricing_test':
        return <DollarSign size={18} className="text-teal-400" />;
      case 'purchase_decision':
        return <ShoppingCart size={18} className="text-cyan-400" />;
      case 'feature_test':
        return <Layers size={18} className="text-emerald-400" />;
      case 'concept_test':
        return <Lightbulb size={18} className="text-amber-400" />;
      case 'message_test':
        return <MessageSquare size={18} className="text-sky-400" />;
      case 'offer_test':
        return <Gift size={18} className="text-violet-400" />;
      case 'switching_test':
        return <RefreshCw size={18} className="text-rose-400" />;
      case 'objection_test':
        return <AlertTriangle size={18} className="text-orange-400" />;
      default:
        return <Sliders size={18} className="text-teal-400" />;
    }
  };

  if (isLoading) {
    return (
      <div role="status" aria-label="Loading behavioral test" style={{ padding: '40px', maxWidth: '1400px', margin: '0 auto', color: 'var(--text-secondary)' }}>
        <div style={{ height: '30px', width: '200px', backgroundColor: 'var(--fill-soft)', borderRadius: '8px', marginBottom: '20px' }} />
        <div style={{ height: '140px', backgroundColor: 'var(--fill-soft)', borderRadius: '12px' }} />
      </div>
    );
  }

  if (!test) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
        <h3>{loadError ? 'Test unavailable' : 'Test not found'}</h3>
        {loadError && <p role="alert">{loadError}</p>}
        {loadError && <button type="button" className="bx-btn bx-btn-secondary" onClick={() => void fetchDetailAndRuns(true, true)}>Retry</button>}
        <button onClick={onBack} style={{ marginTop: '12px', padding: '8px 16px', borderRadius: '8px', backgroundColor: '#14B8A6', color: 'var(--text-on-accent)', border: 'none', cursor: 'pointer' }}>
          Back to Tests
        </button>
      </div>
    );
  }

  const metrics = activeRun?.aggregate_metrics;
  const isRunning = activeRun?.status === 'running' || activeRun?.status === 'pending';
  const actionPending = isTriggeringRun || isRetrying;
  const rerunDisabled = actionPending || isRunning || isLoadingRun || !activeRun;

  return (
    <div style={{ padding: '32px clamp(16px, 4vw, 40px)', maxWidth: '1400px', minWidth: 0, margin: '0 auto', width: '100%', color: 'var(--text-primary)', overflowWrap: 'anywhere' }}>
      {loadError && <div role="alert" className="bx-alert bx-alert--error">
        <span>{loadError}</span>
        <button type="button" className="bx-btn bx-btn-secondary" disabled={actionPending || isLoadingRun} onClick={() => void fetchDetailAndRuns(true, true)}>Retry</button>
      </div>}
      {actionError && <div role="alert" className="bx-alert bx-alert--error">{actionError}</div>}
      {/* Top Breadcrumb & Actions */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '24px',
          flexWrap: 'wrap',
          gap: '16px',
        }}
      >
        <button
          type="button"
          onClick={onBack}
          className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: 'transparent',
            border: 'none',
            color: 'var(--text-secondary)',
            fontSize: '0.88rem',
            cursor: 'pointer',
            padding: 0,
            minHeight: '44px',
          }}
        >
          <ArrowLeft size={16} />
          Back to Behavioral Tests
        </button>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          {runs.length > 1 && onCompareRuns && (
            <button
              type="button"
              onClick={() => onCompareRuns(runs.map((r) => r.id))}
              disabled={actionPending}
              className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '9px 16px',
                borderRadius: '8px',
                backgroundColor: 'var(--glass-mid)',
                border: '1px solid var(--border-soft)',
                color: 'var(--text-primary)',
                fontSize: '0.85rem',
                cursor: actionPending ? 'not-allowed' : 'pointer',
                minHeight: '44px',
                opacity: actionPending ? 0.55 : 1,
              }}
            >
              Compare Runs ({runs.length})
            </button>
          )}

          <button
            type="button"
            onClick={handleTriggerNewRun}
            disabled={rerunDisabled}
            aria-busy={isTriggeringRun}
            className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '9px 18px',
              borderRadius: '8px',
              backgroundColor: '#14B8A6',
              border: 'none',
              color: 'var(--text-on-accent)',
              fontSize: '0.85rem',
              fontWeight: 700,
              minHeight: '44px',
              cursor: rerunDisabled ? 'not-allowed' : 'pointer',
              opacity: rerunDisabled ? 0.55 : 1,
            }}
          >
            <Play size={15} />
            {isTriggeringRun ? 'Starting...' : 'Re-Run Simulation'}
          </button>
        </div>
      </div>

      {/* Test Title Header */}
      <div
        style={{
          paddingBottom: '24px',
          borderBottom: '1px solid var(--border-soft)',
          marginBottom: '24px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '8px' }}>
          <div
            style={{
              padding: '8px',
              borderRadius: '8px',
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-soft)',
            }}
          >
            {getTypeIcon(test.test_type)}
          </div>
          <span
            style={{
              fontSize: '0.75rem',
              padding: '3px 10px',
              borderRadius: '999px',
              backgroundColor: 'var(--accent-subtle)',
              color: 'var(--accent-teal-bright)',
              border: '1px solid var(--border-hover)',
              textTransform: 'capitalize',
            }}
          >
            {test.test_type.replace('_', ' ')}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
            <ShieldCheck size={14} className="text-teal-400" />
            <span>Synthetic simulation over this study&apos;s personas and collected evidence</span>
          </div>
        </div>

        <h1 style={{ margin: '0 0 8px 0', fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-main)' }}>
          {test.name}
        </h1>
        <p style={{ margin: '0 0 16px 0', fontSize: '0.9rem', color: 'var(--text-secondary)', maxWidth: '900px' }}>
          {test.description || 'Behavioral evaluation scenario against this study\u2019s synthetic population.'}
        </p>

        {/* Parameters Snapshot Row */}
        {test.configuration && Object.keys(test.configuration).length > 0 && (
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '12px',
              padding: '12px 16px',
              backgroundColor: 'var(--glass-mid)',
              borderRadius: '10px',
              fontSize: '0.82rem',
            }}
          >
            {Object.entries(test.configuration).map(([k, v]) => (
              <div key={k} style={{ display: 'flex', gap: '6px' }}>
                <span style={{ color: 'var(--text-muted)', textTransform: 'capitalize' }}>{k.replace('_', ' ')}:</span>
                <strong style={{ color: 'var(--text-primary)' }}>{String(v)}</strong>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Historical Runs Selector Tabs */}
      {runs.length > 1 && (
        <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', overflowX: 'auto', paddingBottom: '4px' }}>
          {runs.map((r, idx) => {
            const isSelected = r.id === selectedRunId;
            return (
              <button
                key={r.id}
                type="button"
                onClick={() => handleSelectRun(r.id)}
                disabled={actionPending}
                aria-pressed={isSelected}
                className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
                style={{
                  padding: '8px 16px',
                  borderRadius: '8px',
                  backgroundColor: isSelected ? 'var(--accent-subtle)' : 'var(--fill-soft-2)',
                  border: isSelected ? '1px solid var(--accent-teal)' : '1px solid var(--fill-soft-2)',
                  color: isSelected ? 'var(--accent-teal-bright)' : 'var(--text-secondary)',
                  fontSize: '0.82rem',
                  fontWeight: isSelected ? 600 : 400,
                  minHeight: '44px',
                  cursor: actionPending ? 'not-allowed' : 'pointer',
                  opacity: actionPending ? 0.55 : 1,
                  whiteSpace: 'nowrap',
                }}
              >
                Run #{runs.length - idx} ({r.persona_count} personas) • {r.status}
              </button>
            );
          })}
        </div>
      )}

      {isLoadingRun && <p role="status">Loading run...</p>}
      {!activeRun && !isLoadingRun && !loadError && <p>No saved runs. Return to Behavioral Tests to configure a new simulation.</p>}

      {/* Live Simulation Progress Banner */}
      {isRunning && (
        <div
          role="status"
          style={{
            padding: '20px 24px',
            borderRadius: '8px',
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-soft)',
            marginBottom: '24px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px', marginBottom: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <RotateCw size={18} className="text-teal-400 animate-spin" />
              <span style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--text-main)' }}>
                Simulation in Progress...
              </span>
            </div>
            <span style={{ fontSize: '0.85rem', color: 'var(--accent-teal-bright)' }}>
              {activeRun?.completed_count} / {activeRun?.persona_count} personas evaluated
            </span>
          </div>

          <div role="progressbar" aria-label="Personas evaluated" aria-valuemin={0} aria-valuemax={activeRun?.persona_count || 1} aria-valuenow={activeRun?.completed_count || 0} style={{ width: '100%', height: '8px', backgroundColor: 'var(--bg-card-hover)', borderRadius: '999px', overflow: 'hidden' }}>
            <div
              style={{
                height: '100%',
                backgroundColor: '#14B8A6',
                width: `${activeRun ? (activeRun.completed_count / (activeRun.persona_count || 1)) * 100 : 0}%`,
              }}
            />
          </div>
        </div>
      )}

      {activeRun && !isRunning && activeRun.failed_count > 0 && (
        <div style={{ padding: '20px', borderRadius: '8px', backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-soft)', marginBottom: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--status-error-text)', fontWeight: 600, marginBottom: '6px' }}>
            <AlertTriangle size={18} />
            <span>{activeRun.failed_count} Persona Evaluations Failed</span>
          </div>
          <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Some persona evaluations failed. Retry only those evaluations.</p>
          <button type="button" onClick={handleRetryFailed} disabled={actionPending || isLoadingRun} aria-busy={isRetrying}
            className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
            style={{ marginTop: '12px', minHeight: '44px', padding: '8px 16px', borderRadius: '8px', backgroundColor: 'var(--bg-card-hover)', color: 'var(--status-error-text)', border: '1px solid var(--border-control)', fontSize: '0.85rem', fontWeight: 600, cursor: actionPending ? 'not-allowed' : 'pointer', opacity: actionPending ? 0.55 : 1 }}>
            {isRetrying ? 'Retrying...' : 'Retry Failed Simulations'}
          </button>
        </div>
      )}

      {/* Results Overview Metrics */}
      {activeRun && !isRunning && metrics && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))',
              gap: '16px',
              marginBottom: '24px',
            }}
          >
            {/* Purchase / Adoption Likelihood */}
            <div
              style={{
                padding: '22px',
                borderRadius: '14px',
                backgroundColor: 'var(--glass-mid)',
                border: '1px solid var(--fill-soft-2)',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '8px' }}>Average Acceptance Likelihood</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
                <span style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--accent-teal-bright)' }}>
                  {metrics.average_likelihood_percentage}%
                </span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  ({metrics.positive_count} of {metrics.total_personas} positive)
                </span>
              </div>

              {/* Stacked Sentiment Bar */}
              <div style={{ marginTop: '14px' }}>
                <div style={{ display: 'flex', height: '10px', borderRadius: '999px', overflow: 'hidden', backgroundColor: 'var(--bg-card-hover)' }}>
                  <div style={{ width: `${metrics.positive_percentage}%`, backgroundColor: 'var(--accent-emerald)' }} title={`Positive: ${metrics.positive_percentage}%`} />
                  <div style={{ width: `${metrics.neutral_percentage}%`, backgroundColor: '#F59E0B' }} title={`Neutral: ${metrics.neutral_percentage}%`} />
                  <div style={{ width: `${metrics.negative_percentage}%`, backgroundColor: '#EF4444' }} title={`Negative: ${metrics.negative_percentage}%`} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '6px' }}>
                  <span style={{ color: 'var(--status-success-text)' }}>● {metrics.positive_percentage}% Positive</span>
                  <span style={{ color: '#FBBF24' }}>● {metrics.neutral_percentage}% Neutral</span>
                  <span style={{ color: 'var(--status-error-text)' }}>● {metrics.negative_percentage}% Negative</span>
                </div>
              </div>
            </div>

            {/* Confidence Breakdown */}
            <div
              style={{
                padding: '22px',
                borderRadius: '14px',
                backgroundColor: 'var(--glass-mid)',
                border: '1px solid var(--fill-soft-2)',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '8px' }}>Simulation Confidence Distribution</div>
              <div style={{ display: 'flex', gap: '12px', marginTop: '12px' }}>
                <div style={{ flex: 1, padding: '10px', backgroundColor: 'var(--glass-mid)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--status-success-text)' }}>{metrics.confidence_breakdown?.high || 0}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>High Grounding</div>
                </div>
                <div style={{ flex: 1, padding: '10px', backgroundColor: 'var(--glass-mid)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#FBBF24' }}>{metrics.confidence_breakdown?.medium || 0}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Medium Grounding</div>
                </div>
                <div style={{ flex: 1, padding: '10px', backgroundColor: 'var(--glass-mid)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-secondary)' }}>{metrics.confidence_breakdown?.low || 0}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Low Grounding</div>
                </div>
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '10px' }}>
                Grounding considers Part 6 interview transcripts and Part 2 market claims.
              </div>
            </div>

          </div>

          {/* Risks & Opportunities Callouts */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(min(340px, 100%), 1fr))',
              gap: '16px',
              marginBottom: '28px',
            }}
          >
            {/* Risks / Barriers */}
            <div
              style={{
                padding: '20px',
                borderRadius: '8px',
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-soft)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px', color: 'var(--status-error-text)' }}>
                <AlertTriangle size={18} />
                <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Identified Risks & Friction</h3>
              </div>
              {activeRun.risks && activeRun.risks.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {activeRun.risks.map((risk, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '12px 0',
                        borderTop: '1px solid var(--border-soft)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', marginBottom: '4px' }}>
                        <strong style={{ fontSize: '0.85rem', color: 'var(--text-primary)' }}>{risk.title}</strong>
                        <span style={{ fontSize: 'var(--fs-xs)', color: risk.severity === 'high' ? 'var(--status-error-text)' : 'var(--status-warn-text)', textTransform: 'uppercase' }}>
                          {risk.severity}
                        </span>
                      </div>
                      <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                        {risk.description}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                  No significant adoption risks surfaced in this run.
                </div>
              )}
            </div>

            {/* Opportunities */}
            <div
              style={{
                padding: '20px',
                borderRadius: '8px',
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-soft)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px', color: 'var(--accent-teal-bright)' }}>
                <Sparkles size={18} />
                <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Opportunities & Drivers</h3>
              </div>
              {activeRun.opportunities && activeRun.opportunities.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {activeRun.opportunities.map((opp, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '12px 0',
                        borderTop: '1px solid var(--border-soft)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', marginBottom: '4px' }}>
                        <strong style={{ fontSize: '0.85rem', color: 'var(--text-primary)' }}>{opp.title}</strong>
                        <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--accent-teal-bright)', textTransform: 'uppercase' }}>
                          {opp.appeal}
                        </span>
                      </div>
                      <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                        {opp.description}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                  No high-appeal opportunities surfaced in this run.
                </div>
              )}
            </div>
          </div>

          {/* Segment Analysis Table */}
          {activeRun.segment_analysis && activeRun.segment_analysis.length > 0 && (
            <div
              style={{
                padding: '22px',
                borderRadius: '14px',
                backgroundColor: 'var(--glass-mid)',
                border: '1px solid var(--fill-soft-2)',
                marginBottom: '28px',
              }}
            >
              <h3 style={{ margin: '0 0 14px 0', fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-main)' }}>
                Segment-Level Response Breakdown
              </h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-soft)', color: 'var(--text-secondary)' }}>
                      <th style={{ padding: '10px 14px' }}>Segment</th>
                      <th style={{ padding: '10px 14px' }}>Personas</th>
                      <th style={{ padding: '10px 14px' }}>Acceptance Likelihood</th>
                      <th style={{ padding: '10px 14px' }}>Positive / Negative</th>
                      <th style={{ padding: '10px 14px' }}>Top Objection</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeRun.segment_analysis.map((seg) => (
                      <tr key={seg.segment_id} style={{ borderBottom: '1px solid var(--fill-soft)' }}>
                        <td style={{ padding: '12px 14px', fontWeight: 600, color: 'var(--text-main)' }}>
                          {seg.segment_name}
                        </td>
                        <td style={{ padding: '12px 14px', color: 'var(--text-secondary)' }}>{seg.persona_count}</td>
                        <td style={{ padding: '12px 14px' }}>
                          <span style={{ fontWeight: 700, color: 'var(--accent-teal-bright)' }}>
                            {Math.round(seg.average_likelihood * 100)}%
                          </span>
                        </td>
                        <td style={{ padding: '12px 14px' }}>
                          <span style={{ color: 'var(--status-success-text)' }}>{seg.positive_percentage}% pos</span> / <span style={{ color: 'var(--status-error-text)' }}>{seg.negative_percentage}% neg</span>
                        </td>
                        <td style={{ padding: '12px 14px', color: 'var(--text-primary)', fontStyle: 'italic' }}>
                          {seg.top_objection}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Persona Decision Grid / Table */}
          <div
            style={{
              padding: '22px',
              borderRadius: '14px',
              backgroundColor: 'var(--glass-mid)',
              border: '1px solid var(--fill-soft-2)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div>
                <h3 style={{ margin: '0 0 4px 0', fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-main)' }}>
                  Individual Persona Simulations ({activeRun.results?.length || 0})
                </h3>
                <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  Click any persona to inspect full reasoning chains, decision factors, and the context signals used.
                </p>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(320px, 100%), 1fr))', gap: '14px' }}>
              {activeRun.results?.map((res) => {
                const isPositive = res.decision.includes('positive') || res.decision.includes('buy');
                const isNegative = res.decision.includes('negative') || res.decision.includes('not') || res.decision.includes('unlikely');
                return (
                  <button
                    key={res.id}
                    type="button"
                    data-testid="persona-result-card"
                    aria-label={`Open reasoning for ${res.persona_name}`}
                    aria-haspopup="dialog"
                    className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
                    onClick={(event) => {
                      event.currentTarget.focus();
                      setSelectedPersonaResult(res);
                    }}
                    style={{
                      padding: '16px',
                      minWidth: 0,
                      width: '100%',
                      textAlign: 'left',
                      fontFamily: 'var(--font-sans)',
                      color: 'var(--text-primary)',
                      overflowWrap: 'anywhere',
                      borderRadius: '8px',
                      backgroundColor: 'var(--bg-card)',
                      border: '1px solid var(--border-control)',
                      cursor: 'pointer',
                      transition: 'border-color 0.2s ease',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                    }}
                  >
                    <span style={{ display: 'block', width: '100%', minWidth: 0 }}>
                      <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
                        <span style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-main)' }}>
                          {res.persona_name}
                        </span>
                        <span
                          style={{
                            fontSize: '0.7rem',
                            padding: '2px 8px',
                            borderRadius: '999px',
                            backgroundColor: isPositive ? 'rgba(16, 185, 129, 0.15)' : isNegative ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                            color: isPositive ? 'var(--status-success-text)' : isNegative ? 'var(--status-error-text)' : '#FBBF24',
                            border: `1px solid ${isPositive ? 'rgba(16, 185, 129, 0.3)' : isNegative ? 'rgba(239, 68, 68, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
                          }}
                        >
                          {res.decision_label || res.decision.replace('_', ' ')}
                        </span>
                      </span>

                      {res.segment_name && (
                        <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '8px' }}>
                          Segment: {res.segment_name}
                        </span>
                      )}

                      <span style={{ display: 'block', margin: '0 0 10px 0', fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                        {res.reasoning_summary}
                      </span>
                    </span>

                    <span style={{ display: 'block', width: '100%', minWidth: 0 }}>
                      {/* Likelihood Bar */}
                      <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: '4px' }}>
                        <span style={{ color: 'var(--text-muted)' }}>Likelihood</span>
                        <strong style={{ color: 'var(--accent-teal-bright)' }}>{Math.round(res.probability * 100)}%</strong>
                      </span>
                      <span style={{ display: 'block', width: '100%', height: '4px', backgroundColor: 'var(--bg-card-hover)', borderRadius: '999px', overflow: 'hidden' }}>
                        <span
                          style={{
                            display: 'block',
                            height: '100%',
                            backgroundColor: '#14B8A6',
                            width: `${Math.round(res.probability * 100)}%`,
                          }}
                        />
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* Persona Simulation Result Modal Drawer */}
      {selectedPersonaResult && (
        <div
          data-testid="persona-modal"
          className="bx-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'var(--scrim)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '16px',
          }}
          onClick={() => setSelectedPersonaResult(null)}
        >
          <div
            ref={resultDialogRef}
            className="bx-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="persona-result-title"
            style={{
              width: '100%',
              maxWidth: '680px',
              maxHeight: '85vh',
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-hover)',
              borderRadius: '8px',
              minWidth: 0,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              color: 'var(--text-primary)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div
              style={{
                padding: '20px 24px',
                borderBottom: '1px solid var(--fill-soft-2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                backgroundColor: 'var(--bg-card)',
                gap: '12px',
              }}
            >
              <div>
                <h2 id="persona-result-title" style={{ margin: '0 0 4px 0', fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-main)' }}>
                  {selectedPersonaResult.persona_name} — Behavioral Evaluation
                </h2>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  Decision: <strong style={{ color: 'var(--accent-teal-bright)' }}>{selectedPersonaResult.decision_label}</strong> ({Math.round(selectedPersonaResult.probability * 100)}% likelihood)
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedPersonaResult(null)}
                aria-label="Close behavioral evaluation"
                className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
                style={{ minWidth: '44px', minHeight: '44px', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <X size={20} aria-hidden="true" />
              </button>
            </div>

            {/* Modal Body */}
            <div style={{ padding: '24px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '18px' }}>
              {/* Reasoning Summary */}
              <div>
                <h4 style={{ margin: '0 0 6px 0', fontSize: '0.85rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Simulated Persona Reasoning
                </h4>
                <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-primary)', lineHeight: 1.5, padding: '14px', backgroundColor: 'var(--bg-card-hover)', borderRadius: '10px' }}>
                  {selectedPersonaResult.reasoning_summary}
                </p>
              </div>

              {/* Key Decision Factors */}
              {selectedPersonaResult.key_factors && selectedPersonaResult.key_factors.length > 0 && (
                <div>
                  <h4 style={{ margin: '0 0 8px 0', fontSize: '0.85rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Decision Factors
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {selectedPersonaResult.key_factors.map((f, i) => (
                      <div
                        key={i}
                        style={{
                          padding: '10px 14px',
                          backgroundColor: 'var(--bg-card-hover)',
                          borderRadius: '8px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          fontSize: '0.85rem',
                        }}
                      >
                        <div>
                          <strong style={{ color: 'var(--text-main)' }}>{f.name}</strong>
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{f.description}</div>
                        </div>
                        <span
                          style={{
                            fontSize: '0.72rem',
                            padding: '2px 8px',
                            borderRadius: '6px',
                            backgroundColor: f.direction === 'positive' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                            color: f.direction === 'positive' ? 'var(--status-success-text)' : 'var(--status-error-text)',
                          }}
                        >
                          {f.direction} ({f.impact})
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Motivators vs Objections */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(220px, 100%), 1fr))', gap: '12px' }}>
                <div style={{ padding: '12px', backgroundColor: 'var(--bg-card-hover)', borderRadius: '8px', border: '1px solid var(--border-soft)' }}>
                  <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--status-success-text)', marginBottom: '6px' }}>Motivators</div>
                  <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '0.8rem', color: 'var(--text-primary)' }}>
                    {selectedPersonaResult.motivators?.map((m, i) => (
                      <li key={i}>{m}</li>
                    )) || <li>None noted</li>}
                  </ul>
                </div>

                <div style={{ padding: '12px', backgroundColor: 'var(--bg-card-hover)', borderRadius: '8px', border: '1px solid var(--border-soft)' }}>
                  <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--status-error-text)', marginBottom: '6px' }}>Objections</div>
                  <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '0.8rem', color: 'var(--text-primary)' }}>
                    {selectedPersonaResult.objections?.map((o, i) => (
                      <li key={i}>{o}</li>
                    )) || <li>None noted</li>}
                  </ul>
                </div>
              </div>

              {/* Interview Signals Used */}
              {selectedPersonaResult.interview_signals_used && selectedPersonaResult.interview_signals_used.length > 0 && (
                <div>
                  <h4 style={{ margin: '0 0 6px 0', fontSize: '0.85rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Part 6 Interview Signals Used
                  </h4>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {selectedPersonaResult.interview_signals_used.map((sig, i) => (
                      <span
                        key={i}
                        style={{
                          fontSize: '0.75rem',
                          padding: '4px 10px',
                          borderRadius: '6px',
                          backgroundColor: 'var(--accent-subtle)',
                          color: 'var(--accent-teal-bright)',
                          border: '1px solid var(--accent-glow)',
                        }}
                      >
                        {sig}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
