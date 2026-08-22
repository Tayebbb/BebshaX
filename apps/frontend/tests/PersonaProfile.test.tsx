import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { PersonaProfileView } from '../src/views/PersonaProfileView';

describe('PersonaProfileView', () => {
  it('renders persona demographics, attributes, and provenance badges', async () => {
    render(<PersonaProfileView initialBusinessId="biz_fintech_01" />);

    await waitFor(() => {
      expect(screen.getAllByText(/Sarah Chen/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/The Resilient Gig Maximizer/i).length).toBeGreaterThan(0);
    });

    // Check presence of provenance badges
    expect(screen.getAllByText(/OBSERVED/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/INFERRED/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/SYNTHETIC/i).length).toBeGreaterThan(0);

    // Check evidence grounding quote
    expect(screen.getByText(/PersonaHub \(Gig Economy Dataset\)/i)).toBeInTheDocument();
  });
});
