import React, { useState, useEffect, useRef } from 'react';
import {
  Sliders,
  Plus,
  Search,
  ArrowRight,
  TrendingUp,
  Users,
  CheckCircle2,
  AlertTriangle,
  RotateCw,
  Layers,
  DollarSign,
  ShoppingCart,
  MessageSquare,
  Gift,
  RefreshCw,
  Lightbulb,
} from 'lucide-react';
import { BehavioralTest, BehavioralMetricsResponse, BehavioralTestType } from '../../../types';
import { api } from '../../../services/api';
import { useRequestScope } from '../../../utils/useRequestScope';
import { useRouteReady } from '../../../performance/routeTiming';
import { CountUp } from '../../../motion/CountUp';
import { CreateBehavioralTestModal } from '../modals/CreateBehavioralTestModal';

interface BehavioralTestingViewProps {
  studyId: string;
  onOpenTest: (testId: string, runId?: string) => void;
  onCompareRuns?: (runIds: string[]) => void;
  onNavigateToPersonas?: () => void;
}

export const BehavioralTestingView: React.FC<BehavioralTestingViewProps> = ({
  studyId,
  onOpenTest,
  onCompareRuns: _onCompareRuns,
  onNavigateToPersonas: _onNavigateToPersonas,
}) => {
  const [tests, setTests] = useState<BehavioralTest[]>([]);
  const [metrics, setMetrics] = useState<BehavioralMetricsResponse | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const scopeRef = useRequestScope([studyId]);
  const generationRef = useRef(0);
  useRouteReady(!isLoading, error ? 'error' : tests.length ? 'content' : 'empty');

  const fetchTestsAndMetrics = async () => {
    const scope = scopeRef.current;
    const generation = ++generationRef.current;
    const isCurrent = () => scope.active && generation === generationRef.current;
    setIsLoading(true);
    setError(null);
    setMetricsError(null);
    setMetrics(null);
    void api.getBehavioralMetrics(studyId).then((value) => { if (isCurrent()) setMetrics(value); })
      .catch(() => { if (isCurrent()) setMetricsError('Behavioral metrics unavailable'); });
    try {
      const testList = await api.getBehavioralTests(studyId, searchQuery, typeFilter, statusFilter);
      if (isCurrent()) setTests(testList || []);
    } catch (err: unknown) {
      if (isCurrent()) setError(err instanceof Error ? err.message : 'Failed to load behavioral tests.');
    } finally {
      if (isCurrent()) setIsLoading(false);
    }
  };

  useEffect(() => {
    setTests([]);
    setShowCreateModal(false);
    void fetchTestsAndMetrics();
    return () => { generationRef.current += 1; };
  }, [studyId, typeFilter, statusFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isLoading) void fetchTestsAndMetrics();
  };

  const getTypeIcon = (type: BehavioralTestType) => {
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

  const hasFilters = !!searchQuery.trim() || typeFilter !== 'all' || statusFilter !== 'all';

  return (
    <div style={{ padding: '32px clamp(16px, 4vw, 40px)', maxWidth: '1400px', minWidth: 0, margin: '0 auto', width: '100%', fontFamily: 'var(--font-sans)', color: 'var(--text-primary)' }}>
      {metricsError && <div role="alert">{metricsError}</div>}
      {error && (
        <div
          role="alert"
          style={{
            background: 'var(--bg-card)',
            border: '1px solid rgba(239,68,68,0.4)',
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
          <span>{error}</span>
          <button
            type="button"
            onClick={fetchTestsAndMetrics}
            disabled={isLoading}
            className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
            style={{ minHeight: '44px', background: 'transparent', border: '1px solid currentColor', borderRadius: '6px', padding: '8px 12px', fontFamily: 'var(--font-sans)', color: 'inherit', cursor: 'pointer', fontWeight: 600, fontSize: '0.82rem' }}
          >
            Retry
          </button>
        </div>
      )}
      {/* Top Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: '24px',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div style={{ minWidth: 0, flex: '1 1 320px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                flexShrink: 0,
                borderRadius: '8px',
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-secondary)',
              }}
            >
              <Sliders size={18} />
            </div>
            <h1 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 650, letterSpacing: 0, overflowWrap: 'anywhere', color: 'var(--text-main)' }}>
              Behavioral Testing & Simulation
            </h1>
          </div>
          <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            Synthetic responses to pricing, features, copy, and product offers.
          </p>
        </div>

        <button
          type="button"
          className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
          onClick={() => setShowCreateModal(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            minWidth: 0,
            minHeight: '44px',
            padding: '12px 22px',
            borderRadius: '6px',
            backgroundColor: 'var(--accent-teal)',
            border: 'none',
            color: 'var(--text-on-accent)',
            fontFamily: 'var(--font-sans)',
            fontSize: '0.9rem',
            fontWeight: 700,
            cursor: 'pointer',
            transition: 'background-color 0.2s ease',
          }}
        >
          <Plus size={18} />
          New Behavioral Test
        </button>
      </div>

      {/* Top Metrics Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))',
          gap: '16px',
          marginBottom: '28px',
        }}
      >
        <div
          style={{
            padding: '20px',
            borderRadius: '8px',
            backgroundColor: 'var(--glass-mid)',
            border: '1px solid var(--fill-soft-2)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Total Tests</span>
            <Sliders size={16} className="text-teal-400" />
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 650, color: 'var(--text-main)' }}>
            <CountUp value={metrics?.total_tests ?? tests.length} />
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>Active decision hypotheses</div>
        </div>

        <div
          style={{
            padding: '20px',
            borderRadius: '8px',
            backgroundColor: 'var(--glass-mid)',
            border: '1px solid var(--fill-soft-2)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Completed Runs</span>
            <CheckCircle2 size={16} className="text-emerald-400" />
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 650, color: 'var(--text-main)' }}>
            <CountUp value={metrics?.completed_runs ?? 0} />
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>Across scenarios</div>
        </div>

        <div
          style={{
            padding: '20px',
            borderRadius: '8px',
            backgroundColor: 'var(--glass-mid)',
            border: '1px solid var(--fill-soft-2)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Simulated Personas</span>
            <Users size={16} className="text-cyan-400" />
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 650, color: 'var(--text-main)' }}>
            <CountUp value={metrics?.total_personas_simulated ?? 0} />
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>Persona evaluations</div>
        </div>

        <div
          style={{
            padding: '20px',
            borderRadius: '8px',
            backgroundColor: 'var(--glass-mid)',
            border: '1px solid var(--fill-soft-2)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Avg Buy Likelihood</span>
            <TrendingUp size={16} className="text-teal-400" />
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 650, color: 'var(--accent-teal-bright)' }}>
            {(metrics?.completed_runs ?? 0) > 0 && typeof metrics?.average_buy_likelihood_percentage === 'number' ? (
              <CountUp value={metrics.average_buy_likelihood_percentage} format={(v) => `${Math.round(v)}%`} />
            ) : (
              <span style={{ color: 'var(--text-faint)' }}>—</span>
            )}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>Simulation aggregate signal</div>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '24px',
          gap: '14px',
          flexWrap: 'wrap',
        }}
      >
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', flex: '1 1 280px', minWidth: 0, maxWidth: '420px' }}>
          <div style={{ position: 'relative', width: '100%' }}>
            <Search
              size={16}
              style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}
            />
            <input
              type="text"
              aria-label="Search behavioral tests"
              className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search behavioral tests..."
              style={{
                width: '100%',
                minWidth: 0,
                minHeight: '44px',
                padding: '10px 14px 10px 38px',
                borderRadius: '6px',
                backgroundColor: 'var(--glass-mid)',
                border: '1px solid var(--border-control)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-sans)',
                fontSize: '0.88rem',
                boxSizing: 'border-box',
              }}
            />
          </div>
        </form>

        <div style={{ display: 'flex', flexWrap: 'wrap', minWidth: 0, gap: '10px', alignItems: 'center' }}>
          <select
            aria-label="Test type"
            className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            style={{
              padding: '10px 34px 10px 14px',
              minWidth: 0,
              maxWidth: '100%',
              minHeight: '44px',
              borderRadius: '6px',
              backgroundColor: 'var(--glass-mid)',
              border: '1px solid var(--border-control)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-sans)',
              fontSize: '0.85rem',
              cursor: 'pointer',
            }}
          >
            <option value="all">All Test Types</option>
            <option value="pricing_test">Pricing Tests</option>
            <option value="purchase_decision">Purchase Decisions</option>
            <option value="feature_test">Feature Tests</option>
            <option value="concept_test">Product Concepts</option>
            <option value="message_test">Marketing Copy</option>
            <option value="offer_test">Promotional Offers</option>
            <option value="switching_test">Competitor Switching</option>
            <option value="objection_test">Adoption Barriers</option>
          </select>

          <select
            aria-label="Test status"
            className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{
              padding: '10px 34px 10px 14px',
              minWidth: 0,
              maxWidth: '100%',
              minHeight: '44px',
              borderRadius: '6px',
              backgroundColor: 'var(--glass-mid)',
              border: '1px solid var(--border-control)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-sans)',
              fontSize: '0.85rem',
              cursor: 'pointer',
            }}
          >
            <option value="all">All Statuses</option>
            <option value="ready">Ready</option>
            <option value="completed">Completed</option>
            <option value="running">Running</option>
          </select>

          <button
            type="button"
            aria-label="Refresh"
            aria-busy={isLoading}
            disabled={isLoading}
            className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
            onClick={fetchTestsAndMetrics}
            style={{
              padding: '10px',
              minWidth: '44px',
              minHeight: '44px',
              borderRadius: '6px',
              backgroundColor: 'var(--glass-mid)',
              border: '1px solid var(--border-control)',
              color: 'var(--text-secondary)',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              opacity: isLoading ? 0.55 : 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Refresh"
          >
            <RotateCw size={16} />
          </button>
        </div>
      </div>

      {/* Tests Grid */}
      {isLoading ? (
        <div role="status" aria-label="Loading behavioral tests" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(360px, 100%), 1fr))', gap: '18px' }}>
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              style={{
                height: '180px',
                borderRadius: '8px',
                backgroundColor: 'var(--fill-soft-2)',
                border: '1px solid var(--fill-soft)',
                animation: 'pulse 1.5s infinite',
              }}
            />
          ))}
        </div>
      ) : error ? null : tests.length === 0 ? (
        <div
          style={{
            padding: '60px 24px',
            textAlign: 'center',
            backgroundColor: 'var(--fill-soft-2)',
            border: '1px dashed var(--border-soft)',
            borderRadius: '8px',
          }}
        >
          <div
            style={{
              width: '56px',
              height: '56px',
              borderRadius: '8px',
              backgroundColor: 'var(--accent-subtle)',
              border: '1px solid var(--accent-glow)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--accent-teal)',
              margin: '0 auto 16px auto',
            }}
          >
            <Sliders size={28} />
          </div>
          <h3 style={{ margin: '0 0 8px 0', fontSize: '1.2rem', color: 'var(--text-main)' }}>
            {hasFilters ? 'No Matching Behavioral Tests' : 'No Behavioral Tests Created Yet'}
          </h3>
          <p style={{ margin: '0 auto 24px auto', maxWidth: '440px', fontSize: '0.88rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            {hasFilters ? 'No simulations match the current search and filters.' : 'No behavioral simulations have been created for this study.'}
          </p>
          {!hasFilters && <button
            type="button"
            className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
            onClick={() => setShowCreateModal(true)}
            style={{
              minHeight: '44px',
              padding: '12px 24px',
              borderRadius: '6px',
              backgroundColor: 'var(--accent-teal)',
              border: 'none',
              color: 'var(--text-on-accent)',
              fontFamily: 'var(--font-sans)',
              fontSize: '0.9rem',
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            Create First Behavioral Test
          </button>}
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(min(380px, 100%), 1fr))',
            gap: '18px',
          }}
        >
          {tests.map((test) => {
            const hasRun = test.latest_run != null;
            return (
              <button
                key={test.id}
                type="button"
                aria-label={`View Results: ${test.name}`}
                className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
                onClick={() => onOpenTest(test.id, test.latest_run?.id)}
                style={{
                  padding: '22px',
                  minWidth: 0,
                  minHeight: '44px',
                  width: '100%',
                  textAlign: 'left',
                  fontFamily: 'var(--font-sans)',
                  color: 'var(--text-primary)',
                  overflowWrap: 'anywhere',
                  borderRadius: '8px',
                  backgroundColor: 'var(--glass-mid)',
                  border: '1px solid var(--border-control)',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  transition: 'border-color 0.2s ease',
                }}
              >
                <span style={{ display: 'block', minWidth: 0, width: '100%' }}>
                  <span style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                    <span style={{ display: 'flex', minWidth: 0, alignItems: 'center', gap: '8px' }}>
                      <span
                        style={{
                          padding: '6px',
                          borderRadius: '8px',
                          backgroundColor: 'var(--glass-mid)',
                        }}
                      >
                        {getTypeIcon(test.test_type)}
                      </span>
                      <span
                        style={{
                          fontSize: '0.72rem',
                          padding: '2px 8px',
                          borderRadius: '6px',
                          backgroundColor: 'var(--accent-subtle)',
                          color: 'var(--accent-teal-bright)',
                          border: '1px solid var(--accent-glow)',
                          textTransform: 'capitalize',
                        }}
                      >
                        {test.test_type.replace('_', ' ')}
                      </span>
                    </span>

                    <span
                      style={{
                        fontSize: '0.72rem',
                        color: test.status === 'completed' ? 'var(--status-success-text)' : 'var(--text-secondary)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      <span
                        style={{
                          width: '6px',
                          height: '6px',
                          borderRadius: '50%',
                          backgroundColor: test.status === 'completed' ? 'var(--accent-emerald)' : 'var(--text-muted)',
                        }}
                      />
                      {test.status}
                    </span>
                  </span>

                  <span style={{ display: 'block', margin: '0 0 6px 0', fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-main)' }}>
                    {test.name}
                  </span>
                  <span style={{ display: 'block', margin: '0 0 16px 0', fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.4, minHeight: '36px' }}>
                    {test.description || 'Behavioral evaluation scenario against this study\u2019s synthetic population.'}
                  </span>
                </span>

                <span style={{ display: 'block', minWidth: 0, width: '100%' }}>
                  {/* Latest Run Snapshot */}
                  {hasRun ? (
                    <span
                      style={{
                        padding: '12px 0',
                        borderTop: '1px solid var(--border-subtle)',
                        marginBottom: '14px',
                        display: 'flex',
                        flexWrap: 'wrap',
                        gap: '12px',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <span>
                        <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)' }}>Latest Simulation</span>
                        <span style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                          {test.latest_run?.persona_count} personas evaluated
                        </span>
                      </span>
                      <span style={{ textAlign: 'right' }}>
                        <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)' }}>Likelihood</span>
                        <span
                          style={{ display: 'block', fontSize: '0.95rem', fontWeight: 700, color: typeof test.latest_run?.average_likelihood === 'number' ? 'var(--accent-teal-bright)' : 'var(--text-muted)' }}
                          title={typeof test.latest_run?.average_likelihood === 'number' ? undefined : 'Not measured yet for this run'}
                        >
                          {typeof test.latest_run?.average_likelihood === 'number'
                            ? `${Math.round(test.latest_run.average_likelihood * 100)}%`
                            : '—'}
                        </span>
                      </span>
                    </span>
                  ) : (
                    <span
                      style={{
                        display: 'block',
                        padding: '10px 0',
                        borderTop: '1px solid var(--border-subtle)',
                        marginBottom: '14px',
                        fontSize: '0.78rem',
                        color: 'var(--text-secondary)',
                        fontStyle: 'italic',
                      }}
                    >
                      Ready to execute first simulation run.
                    </span>
                  )}

                  <span style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', minWidth: 0, alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {test.run_count} {test.run_count === 1 ? 'run' : 'runs'} recorded
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.82rem', color: 'var(--accent-teal)', fontWeight: 600 }}>
                      <span>View Results</span>
                      <ArrowRight size={14} />
                    </span>
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* Creation Modal */}
      {showCreateModal && (
        <CreateBehavioralTestModal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          studyId={studyId}
          onTestCreated={(testId, runId) => {
            void fetchTestsAndMetrics();
            onOpenTest(testId, runId);
          }}
        />
      )}
    </div>
  );
};
