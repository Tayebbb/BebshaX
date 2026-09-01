import React, { useState, useEffect } from 'react';
import {
  ArrowLeft,
  AlertTriangle,
  Sparkles,
  ShieldCheck,
} from 'lucide-react';
import { BehavioralTestRun } from '../../../types';
import { api } from '../../../services/api';

interface BehavioralComparisonViewProps {
  studyId: string;
  runIds: string[];
  onBack: () => void;
}

export const BehavioralComparisonView: React.FC<BehavioralComparisonViewProps> = ({
  studyId,
  runIds,
  onBack,
}) => {
  const [runs, setRuns] = useState<BehavioralTestRun[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchComparison = async () => {
      setIsLoading(true);
      try {
        const res = await api.compareBehavioralRuns(studyId, runIds);
        setRuns(res.runs || []);
      } catch {
        // Soft error
      } finally {
        setIsLoading(false);
      }
    };
    fetchComparison();
  }, [studyId, runIds]);

  return (
    <div style={{ padding: '32px clamp(16px, 4vw, 40px)', maxWidth: '1400px', margin: '0 auto', width: '100%', color: 'var(--text-primary)' }}>
      {/* Top Header */}
      <div style={{ marginBottom: '24px' }}>
        <button
          onClick={onBack}
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
            marginBottom: '16px',
          }}
        >
          <ArrowLeft size={16} />
          Back to Tests
        </button>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h1 style={{ margin: '0 0 6px 0', fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-main)' }}>
              Simulation Run Comparison
            </h1>
            <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
              Comparing {runs.length} simulation runs side-by-side across customer acceptance signals and friction points.
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', color: 'var(--accent-teal-bright)' }}>
            <ShieldCheck size={16} />
            <span>Synthetic Grounded Runs</span>
          </div>
        </div>
      </div>

      {isLoading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(320px, 100%), 1fr))', gap: '16px' }}>
          {[1, 2].map((i) => (
            <div
              key={i}
              style={{
                height: '350px',
                borderRadius: '14px',
                backgroundColor: 'var(--fill-soft-2)',
                animation: 'pulse 1.5s infinite',
              }}
            />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
          No runs found for comparison.
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${Math.min(runs.length, 3)}, 1fr)`,
            gap: '20px',
            overflowX: 'auto',
          }}
        >
          {runs.map((run, idx) => {
            const metrics = run.aggregate_metrics;
            return (
              <div
                key={run.id}
                style={{
                  padding: '24px',
                  borderRadius: '16px',
                  backgroundColor: 'var(--glass-mid)',
                  border: '1px solid var(--fill-soft-2)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '20px',
                }}
              >
                {/* Header */}
                <div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                    Run #{runs.length - idx} • {run.status}
                  </div>
                  <h3 style={{ margin: '0 0 6px 0', fontSize: '1.15rem', color: 'var(--text-main)', fontWeight: 700 }}>
                    {run.scenario_snapshot?.title || 'Scenario Run'}
                  </h3>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    {run.persona_count} personas evaluated
                  </div>
                </div>

                {/* Score */}
                <div style={{ padding: '16px', backgroundColor: 'var(--glass-mid)', borderRadius: '12px', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>Acceptance Likelihood</div>
                  <div style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--accent-teal-bright)' }}>
                    {metrics?.average_likelihood_percentage ?? Math.round((metrics?.average_likelihood || 0.5) * 100)}%
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                    {metrics?.positive_count} pos / {metrics?.neutral_count} neu / {metrics?.negative_count} neg
                  </div>
                </div>

                {/* Top Risks */}
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--status-error-text)', fontSize: '0.82rem', fontWeight: 600, marginBottom: '8px' }}>
                    <AlertTriangle size={15} />
                    <span>Top Risks</span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {run.risks?.slice(0, 2).map((r, i) => (
                      <div key={i} style={{ padding: '8px 10px', backgroundColor: 'var(--bg-card-hover)', borderRadius: '6px', fontSize: '0.78rem', color: 'var(--text-primary)' }}>
                        {r.title}
                      </div>
                    )) || <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>None</div>}
                  </div>
                </div>

                {/* Top Opportunities */}
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--accent-teal-bright)', fontSize: '0.82rem', fontWeight: 600, marginBottom: '8px' }}>
                    <Sparkles size={15} />
                    <span>Top Drivers</span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {run.opportunities?.slice(0, 2).map((o, i) => (
                      <div key={i} style={{ padding: '8px 10px', backgroundColor: 'var(--bg-card-hover)', borderRadius: '6px', fontSize: '0.78rem', color: 'var(--text-primary)' }}>
                        {o.title}
                      </div>
                    )) || <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>None</div>}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
