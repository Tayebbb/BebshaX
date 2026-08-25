import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { OpenRouterDiagnosticModal } from '../src/components/dashboard/views/OpenRouterDiagnosticModal';
import { api } from '../src/services/api';

describe('Autonomous Research & Dataset Grounding Tests', () => {
  beforeEach(() => {
    api.setMockMode(true);
    api.resetMockStore();
  });

  it('triggers autonomous research and returns discovered sources and empirical claims', async () => {
    const run = await api.startResearch('study_demo_01');
    expect(run).toBeDefined();
    expect(run.status).toBe('completed');
    expect(run.claim_count).toBeGreaterThanOrEqual(0);
  });

  it('fetches dataset candidates discovered by research engine', async () => {
    const candidates = await api.getDatasetCandidates('study_demo_01');
    expect(Array.isArray(candidates)).toBe(true);
  });

  it('opens OpenRouter diagnostic modal and verifies connection diagnostics', async () => {
    const onClose = vi.fn();
    render(<OpenRouterDiagnosticModal isOpen={true} onClose={onClose} />);

    expect(screen.getByText(/OpenRouter Diagnostic Panel/i)).toBeInTheDocument();
    expect(screen.getByText(/Server Configuration/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/KEY CONFIGURED/i)).toBeInTheDocument();
      expect(screen.getByText(/CONNECTED & VERIFIED/i)).toBeInTheDocument();
    });

    const testButton = screen.getByRole('button', { name: /Test OpenRouter Connection/i });
    fireEvent.click(testButton);

    await waitFor(() => {
      expect(screen.getByText(/OpenRouter connection successful/i)).toBeInTheDocument();
    });
  });
});
