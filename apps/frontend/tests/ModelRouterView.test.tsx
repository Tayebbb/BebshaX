import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ModelRouterView } from '../src/components/dashboard/views/ModelRouterView';
import { api } from '../src/services/api';
import { ProvenanceRecord, RoutesStatusResponse } from '../src/types';

vi.mock('../src/services/api', () => ({
  api: {
    getRoutesStatus: vi.fn(),
    getProvenance: vi.fn(),
    getEvaluationMetrics: vi.fn(),
    getDemoLabScenarios: vi.fn(),
    runDemoLabScenario: vi.fn(),
  },
  default: {
    getRoutesStatus: vi.fn(),
    getProvenance: vi.fn(),
    getEvaluationMetrics: vi.fn(),
    getDemoLabScenarios: vi.fn(),
    runDemoLabScenario: vi.fn(),
  },
}));

const mockRoutes: RoutesStatusResponse = {
  providers: [
    { name: 'groq', type: 'free_tier_key', status: 'healthy', available_models: 3, active_cooldowns: 0 },
  ],
  pools: [{ name: 'reasoning', max_concurrency: 2, active_requests: 0, candidates_count: 4 }],
};

/** A request that never reached a provider: every serving field is null. */
const failedTrace: ProvenanceRecord = {
  request_id: 'req_failed_001',
  task: 'PERSONA_GENERATION' as ProvenanceRecord['task'],
  pool: 'reasoning',
  persona_id: null,
  conversation_id: null,
  created_at: '2026-09-01T10:00:00Z',
  routing_path: [],
  attempts: [],
  served_by_provider: null,
  served_by_model: null,
  input_tokens: null,
  output_tokens: null,
  total_latency_ms: null,
  success: false,
};

describe('ModelRouterView honesty regressions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.getRoutesStatus as any).mockResolvedValue(mockRoutes);
    (api.getProvenance as any).mockResolvedValue({ items: [failedTrace] });
    (api.getEvaluationMetrics as any).mockRejectedValue(new Error('metrics offline'));
    (api.getDemoLabScenarios as any).mockResolvedValue(null);
  });

  it('renders "not served" and "—" for a failed trace, never a fabricated provider or latency', async () => {
    render(<ModelRouterView />);

    expect(await screen.findByText('not served')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    expect(screen.queryByText(/340ms/)).not.toBeInTheDocument();
    expect(screen.queryByText(/pollinations/i)).not.toBeInTheDocument();
  });

  it('labels the static routing/pool descriptions as architecture, not live status', async () => {
    render(<ModelRouterView />);

    await screen.findByText('Task Pool Design');
    expect(screen.queryByText('Active Task Pools')).not.toBeInTheDocument();
    expect(
      screen.getAllByText(/How routing works — architecture, not live status/i)
    ).toHaveLength(1);
  });
});
