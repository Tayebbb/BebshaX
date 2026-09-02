import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { EvidenceLaboratoryView } from '../src/components/dashboard/views/EvidenceLaboratoryView';
import { api } from '../src/services/api';

describe('EvidenceLaboratoryView Component', () => {
  beforeEach(() => {
    api.resetMockStore();
    api.setMockMode(true);
  });

  it('renders coverage metrics and claims tab by default', async () => {
    render(<EvidenceLaboratoryView studyId="study_test_1" />);

    expect(screen.getByText('Evidence Laboratory')).toBeInTheDocument();
    expect(screen.getByText('Evidence Coverage')).toBeInTheDocument();
    expect(screen.getByText('Run Research')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Key Claims (5)')).toBeInTheDocument();
      expect(screen.getByText('Sources & Chunks (4)')).toBeInTheDocument();
    });
  });

  it('filters claims when clicking status filter pills', async () => {
    render(<EvidenceLaboratoryView studyId="study_test_1" />);

    await waitFor(() => {
      expect(screen.getByText(/Students experience significant fragmentation/i)).toBeInTheDocument();
    });

    // Click "Unsupported (Red)" filter pill
    const unsupportedPill = screen.getByRole('button', { name: /Unsupported \(Red\)/i });
    fireEvent.click(unsupportedPill);

    await waitFor(() => {
      expect(screen.getByText(/Students will pay ৳1,000\+\/month/i)).toBeInTheDocument();
      expect(screen.queryByText(/Students experience significant fragmentation/i)).not.toBeInTheDocument();
    });
  });

  it('filters claims using the live search input', async () => {
    render(<EvidenceLaboratoryView studyId="study_test_1" />);

    await waitFor(() => {
      expect(screen.getByText(/Students experience significant fragmentation/i)).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Search claims & evidence.../i);
    fireEvent.change(searchInput, { target: { value: 'mobile payment' } });

    await waitFor(() => {
      expect(screen.getByText(/Target users show strong willingness to pay/i)).toBeInTheDocument();
      expect(screen.queryByText(/Students experience significant fragmentation/i)).not.toBeInTheDocument();
    });
  });

  it('opens and closes the claim provenance inspection modal', async () => {
    render(<EvidenceLaboratoryView studyId="study_test_1" />);

    await waitFor(() => {
      expect(screen.getAllByText(/Inspect Provenance/i).length).toBeGreaterThan(0);
    });

    const inspectButtons = screen.getAllByText(/Inspect Provenance/i);
    fireEvent.click(inspectButtons[0]);

    await waitFor(() => {
      expect(screen.getByText(/Claim Provenance Inspection/i)).toBeInTheDocument();
      expect(screen.getByText(/Why does BebshaX evaluate this as/i)).toBeInTheDocument();
    });

    const closeBtn = screen.getByRole('button', { name: /Close Inspection/i });
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByText(/Claim Provenance Inspection/i)).not.toBeInTheDocument();
    });
  });

  it('switches to Sources tab and renders source repository', async () => {
    render(<EvidenceLaboratoryView studyId="study_test_1" />);

    await waitFor(() => {
      expect(screen.getByText(/Sources & Chunks/i)).toBeInTheDocument();
    });

    const sourcesTabBtn = screen.getByText(/Sources & Chunks/i);
    fireEvent.click(sourcesTabBtn);

    await waitFor(() => {
      expect(screen.getByText(/Reddit r\/bangladesh/i)).toBeInTheDocument();
      expect(screen.getByText(/The Daily Star Tech/i)).toBeInTheDocument();
      expect(screen.getByText(/Survey Report: Tech spending/i)).toBeInTheDocument();
    });
  });
});
