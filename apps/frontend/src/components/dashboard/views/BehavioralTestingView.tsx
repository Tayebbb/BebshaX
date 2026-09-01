import React, { useState, useEffect } from 'react';
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
  const [showCreateModal, setShowCreateModal] = useState(false);

  const fetchTestsAndMetrics = async () => {
    setIsLoading(true);
    try {
      const [testList, metricsData] = await Promise.all([
        api.getBehavioralTests(studyId, searchQuery, typeFilter, statusFilter),
        api.getBehavioralMetrics(studyId),
      ]);
      setTests(testList || []);
      setMetrics(metricsData || null);
    } catch {
      // Graceful fallback
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTestsAndMetrics();
  }, [studyId, typeFilter, statusFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchTestsAndMetrics();
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

  return (
    <div style={{ padding: '32px clamp(16px, 4vw, 40px)', maxWidth: '1400px', margin: '0 auto', width: '100%', color: 'var(--text-primary)' }}>
      {/* Top Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: '28px',
          flexWrap: 'wrap',
          gap: '16px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '10px',
                backgroundColor: 'var(--accent-subtle)',
                border: '1px solid var(--border-hover)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--accent-teal)',
              }}
            >
              <Sliders size={20} />
            </div>
            <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.02em', color: 'var(--text-main)' }}>
              Behavioral Testing & Simulation
            </h1>
          </div>
          <p style={{ margin: 0, fontSize: '0.92rem', color: 'var(--text-secondary)' }}>
            Test how your synthetic customer population responds to pricing, features, copy, and product offers.
          </p>
        </div>

        <button
          onClick={() => setShowCreateModal(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '12px 22px',
            borderRadius: '10px',
            backgroundColor: '#14B8A6',
            border: 'none',
            color: 'var(--text-on-accent)',
            fontSize: '0.9rem',
            fontWeight: 700,
            cursor: 'pointer',
            boxShadow: '0 0 20px var(--border-hover)',
            transition: 'all 0.2s ease',
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
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
          marginBottom: '28px',
        }}
      >
        <div
          style={{
            padding: '20px',
            borderRadius: '14px',
            backgroundColor: 'var(--glass-mid)',
            border: '1px solid var(--fill-soft-2)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Total Tests</span>
            <Sliders size={16} className="text-teal-400" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--text-main)' }}>
            <CountUp value={metrics?.total_tests ?? tests.length} />
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>Active decision hypotheses</div>
        </div>

        <div
          style={{
            padding: '20px',
            borderRadius: '14px',
            backgroundColor: 'var(--glass-mid)',
            border: '1px solid var(--fill-soft-2)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Completed Runs</span>
            <CheckCircle2 size={16} className="text-emerald-400" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--text-main)' }}>
            <CountUp value={metrics?.completed_runs ?? 0} />
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>Across scenarios</div>
        </div>

        <div
          style={{
            padding: '20px',
            borderRadius: '14px',
            backgroundColor: 'var(--glass-mid)',
            border: '1px solid var(--fill-soft-2)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Simulated Personas</span>
            <Users size={16} className="text-cyan-400" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--text-main)' }}>
            <CountUp value={metrics?.total_personas_simulated ?? 0} />
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>Persona evaluations</div>
        </div>

        <div
          style={{
            padding: '20px',
            borderRadius: '14px',
            backgroundColor: 'var(--glass-mid)',
            border: '1px solid var(--fill-soft-2)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Avg Buy Likelihood</span>
            <TrendingUp size={16} className="text-teal-400" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--accent-teal-bright)' }}>
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
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', flex: 1, minWidth: '280px', maxWidth: '420px' }}>
          <div style={{ position: 'relative', width: '100%' }}>
            <Search
              size={16}
              style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search behavioral tests..."
              style={{
                width: '100%',
                padding: '10px 14px 10px 38px',
                borderRadius: '10px',
                backgroundColor: 'var(--glass-mid)',
                border: '1px solid var(--border-soft)',
                color: 'var(--text-primary)',
                fontSize: '0.88rem',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>
        </form>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            style={{
              padding: '10px 34px 10px 14px',
              borderRadius: '10px',
              backgroundColor: 'var(--glass-mid)',
              border: '1px solid var(--border-soft)',
              color: 'var(--text-primary)',
              fontSize: '0.85rem',
              outline: 'none',
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
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{
              padding: '10px 34px 10px 14px',
              borderRadius: '10px',
              backgroundColor: 'var(--glass-mid)',
              border: '1px solid var(--border-soft)',
              color: 'var(--text-primary)',
              fontSize: '0.85rem',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="all">All Statuses</option>
            <option value="ready">Ready</option>
            <option value="completed">Completed</option>
            <option value="running">Running</option>
          </select>

          <button
            onClick={fetchTestsAndMetrics}
            style={{
              padding: '10px',
              borderRadius: '10px',
              backgroundColor: 'var(--glass-mid)',
              border: '1px solid var(--border-soft)',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
            }}
            title="Refresh"
          >
            <RotateCw size={16} />
          </button>
        </div>
      </div>

      {/* Tests Grid */}
      {isLoading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(360px, 100%), 1fr))', gap: '18px' }}>
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              style={{
                height: '180px',
                borderRadius: '14px',
                backgroundColor: 'var(--fill-soft-2)',
                border: '1px solid var(--fill-soft)',
                animation: 'pulse 1.5s infinite',
              }}
            />
          ))}
        </div>
      ) : tests.length === 0 ? (
        <div
          style={{
            padding: '60px 24px',
            textAlign: 'center',
            backgroundColor: 'var(--fill-soft-2)',
            border: '1px dashed var(--border-soft)',
            borderRadius: '16px',
          }}
        >
          <div
            style={{
              width: '56px',
              height: '56px',
              borderRadius: '14px',
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
            No Behavioral Tests Created Yet
          </h3>
          <p style={{ margin: '0 auto 24px auto', maxWidth: '440px', fontSize: '0.88rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            Simulate how your synthetic customer population responds to pricing, features, marketing messages, and competitor alternatives.
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            style={{
              padding: '12px 24px',
              borderRadius: '10px',
              backgroundColor: '#14B8A6',
              border: 'none',
              color: 'var(--text-on-accent)',
              fontSize: '0.9rem',
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: '0 0 20px var(--border-hover)',
            }}
          >
            Create First Behavioral Test
          </button>
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
              <div
                key={test.id}
                onClick={() => onOpenTest(test.id, test.latest_run?.id)}
                style={{
                  padding: '22px',
                  borderRadius: '14px',
                  backgroundColor: 'var(--glass-mid)',
                  border: '1px solid var(--fill-soft-2)',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  position: 'relative',
                  overflow: 'hidden',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div
                        style={{
                          padding: '6px',
                          borderRadius: '8px',
                          backgroundColor: 'var(--glass-mid)',
                        }}
                      >
                        {getTypeIcon(test.test_type)}
                      </div>
                      <span
                        style={{
                          fontSize: '0.72rem',
                          padding: '2px 8px',
                          borderRadius: '999px',
                          backgroundColor: 'var(--accent-subtle)',
                          color: 'var(--accent-teal-bright)',
                          border: '1px solid var(--accent-glow)',
                          textTransform: 'capitalize',
                        }}
                      >
                        {test.test_type.replace('_', ' ')}
                      </span>
                    </div>

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
                  </div>

                  <h3 style={{ margin: '0 0 6px 0', fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-main)' }}>
                    {test.name}
                  </h3>
                  <p style={{ margin: '0 0 16px 0', fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.4, minHeight: '36px' }}>
                    {test.description || 'Behavioral evaluation scenario against grounded population.'}
                  </p>
                </div>

                <div>
                  {/* Latest Run Snapshot */}
                  {hasRun ? (
                    <div
                      style={{
                        padding: '12px',
                        borderRadius: '10px',
                        backgroundColor: 'var(--glass-mid)',
                        marginBottom: '14px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Latest Simulation</div>
                        <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                          {test.latest_run?.persona_count} personas evaluated
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Likelihood</div>
                        <div style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--accent-teal-bright)' }}>
                          {Math.round((test.latest_run?.average_likelihood || 0.5) * 100)}%
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div
                      style={{
                        padding: '10px 12px',
                        borderRadius: '10px',
                        backgroundColor: 'rgba(15, 23, 42, 0.4)',
                        marginBottom: '14px',
                        fontSize: '0.78rem',
                        color: 'var(--text-secondary)',
                        fontStyle: 'italic',
                      }}
                    >
                      Ready to execute first simulation run.
                    </div>
                  )}

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {test.run_count} {test.run_count === 1 ? 'run' : 'runs'} recorded
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.82rem', color: 'var(--accent-teal)', fontWeight: 600 }}>
                      <span>View Results</span>
                      <ArrowRight size={14} />
                    </div>
                  </div>
                </div>
              </div>
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
            fetchTestsAndMetrics();
            onOpenTest(testId, runId);
          }}
        />
      )}
    </div>
  );
};
