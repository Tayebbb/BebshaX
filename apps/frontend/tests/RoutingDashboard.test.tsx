import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { RoutingDashboardView } from '../src/views/RoutingDashboardView';

describe('RoutingDashboardView', () => {
  it('renders summary KPIs and provider cards properly', async () => {
    render(<RoutingDashboardView />);

    await waitFor(() => {
      expect(screen.getByText(/Total Governed Calls/i)).toBeInTheDocument();
      expect(screen.getByText(/Routing Success Rate/i)).toBeInTheDocument();
      expect(screen.getByText(/Active Providers & Free Tier Status/i)).toBeInTheDocument();
      expect(screen.getByText(/LLM Request Provenance Log/i)).toBeInTheDocument();
    });

    // Check presence of providers using getAllByText
    expect(screen.getAllByText(/pollinations/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/ollama/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/groq/i).length).toBeGreaterThan(0);
  });
});
