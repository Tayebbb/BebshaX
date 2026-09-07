import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import App from '../src/App';

describe('App Minimal Shell', () => {
  it('renders BebshaX app identity and health info without a duplicate h1', async () => {
    render(<App />);

    // Auth initialisation may show a loading spinner first; wait for it to clear.
    await waitFor(() => {
      expect(screen.getAllByText(/BebshaX/i).length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/Synthetic Persona Research Platform/i)).toBeInTheDocument();
    // The visually-hidden identity block is plain text — the landing hero owns
    // the page's single h1 (two h1s confused the document outline).
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);

    await waitFor(() => {
      expect(screen.getByText(/Backend Status:/i)).toBeInTheDocument();
    });
  });
});
