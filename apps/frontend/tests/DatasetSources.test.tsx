import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DatasetSourcesView } from '../src/components/dashboard/views/DatasetSourcesView';
import { OpenRouterDiagnosticModal } from '../src/components/dashboard/views/OpenRouterDiagnosticModal';
import { api } from '../src/services/api';

describe('DatasetSourcesView & OpenRouter Diagnostics', () => {
  beforeEach(() => {
    api.setMockMode(true);
    api.resetMockStore();
  });

  it('renders dataset sources header, summary metrics, and dataset cards', async () => {
    render(<DatasetSourcesView />);

    expect(screen.getByText(/Dataset Sources & Empirical Grounding/i)).toBeInTheDocument();
    expect(screen.getByText(/Connected Datasets/i)).toBeInTheDocument();
    expect(screen.getByText(/Profiled Evidence Rows/i)).toBeInTheDocument();
    expect(screen.getByText(/Discovered Segments/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/Bangladesh University Student Tech & Budget Survey 2026/i)).toBeInTheDocument();
      expect(screen.getAllByText(/1,250/i).length).toBeGreaterThan(0);
    });
  });

  it('opens and closes Add Dataset modal and supports switching modes', async () => {
    render(<DatasetSourcesView />);

    const addButtons = screen.getAllByRole('button', { name: /Add Dataset/i });
    fireEvent.click(addButtons[0]);

    expect(screen.getByText(/Add Dataset Source/i)).toBeInTheDocument();
    expect(screen.getByText(/Dataset URL \(HTTP\/HTTPS\)/i)).toBeInTheDocument();

    // Switch to upload mode
    const uploadTab = screen.getByRole('button', { name: /Upload File/i });
    fireEvent.click(uploadTab);

    expect(screen.getByText(/Dataset File \(CSV, JSON, TSV, XLSX\)/i)).toBeInTheDocument();
  });

  it('opens dataset detail modal and displays schema and descriptive statistics', async () => {
    render(<DatasetSourcesView />);

    await waitFor(() => {
      expect(screen.getByText(/Bangladesh University Student Tech & Budget Survey 2026/i)).toBeInTheDocument();
    });

    // Click dataset card to open detail modal
    fireEvent.click(screen.getByText(/Bangladesh University Student Tech & Budget Survey 2026/i));

    // Click Schema tab
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^schema$/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /^schema$/i }));

    await waitFor(() => {
      expect(screen.getByText(/Inferred Column Types & Quality Profiling/i)).toBeInTheDocument();
    });

    // Switch to Descriptive Statistics tab
    const statsTab = screen.getByRole('button', { name: /Descriptive Statistics/i });
    fireEvent.click(statsTab);

    await waitFor(() => {
      expect(screen.getByText(/Numeric Distributions/i)).toBeInTheDocument();
      expect(screen.getByText(/Categorical Frequencies/i)).toBeInTheDocument();
    });
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
