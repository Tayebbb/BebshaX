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

    expect(screen.getByRole('heading', { level: 1, name: /Dataset Sources/i })).toBeInTheDocument();
    expect(screen.getByText(/Data Lab/i)).toBeInTheDocument();
    expect(screen.getByText(/Connected Datasets/i)).toBeInTheDocument();
    expect(screen.getByText(/Total Empirical Records/i)).toBeInTheDocument();
    expect(screen.getByText(/Discovered Segments/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/Bangladesh University Student Tech & Budget Survey 2026/i)).toBeInTheDocument();
      expect(screen.getAllByText(/1,250/i).length).toBeGreaterThan(0);
    });
  });

  it('opens and closes Add Dataset modal and supports switching between URL and File upload', async () => {
    render(<DatasetSourcesView />);

    const addButtons = screen.getAllByRole('button', { name: /Add Dataset/i });
    fireEvent.click(addButtons[0]);

    expect(screen.getByText(/Add Dataset Source/i)).toBeInTheDocument();
    expect(screen.getByText(/URL Ingestion/i)).toBeInTheDocument();

    // Switch to upload mode
    const uploadTab = screen.getByRole('button', { name: /File Upload/i });
    fireEvent.click(uploadTab);

    expect(screen.getByText(/Select File \(CSV, JSON, XLSX, TSV\)/i)).toBeInTheDocument();
  });

  it('opens dataset detail modal, tests Preview tab and Data Quality alerts', async () => {
    render(<DatasetSourcesView />);

    await waitFor(() => {
      expect(screen.getByText(/Bangladesh University Student Tech & Budget Survey 2026/i)).toBeInTheDocument();
    });

    // Click dataset card to open detail modal
    fireEvent.click(screen.getByTestId('dataset-card-ds_bd_student_survey_2026'));

    // Verify modal is open on Overview tab
    await waitFor(() => {
      expect(screen.getByText(/CONTENT HASH/i)).toBeInTheDocument();
    });

    // Click Schema tab
    fireEvent.click(screen.getByTestId('tab-schema'));
    await waitFor(() => {
      expect(screen.getByText(/Inferred Column Types & Missingness Profiling/i)).toBeInTheDocument();
    });

    // Click Stats tab
    fireEvent.click(screen.getByTestId('tab-stats'));
    await waitFor(() => {
      expect(screen.getByText(/Numeric Distributions/i)).toBeInTheDocument();
      expect(screen.getByText(/Categorical Frequencies/i)).toBeInTheDocument();
    });

    // Click Preview tab
    fireEvent.click(screen.getByTestId('tab-preview'));
    await waitFor(() => {
      expect(screen.getByText(/Showing records/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Next/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Previous/i })).toBeInTheDocument();
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
