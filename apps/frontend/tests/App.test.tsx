import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import App from '../src/App';

describe('App Minimal Shell', () => {
  it('renders BebshaX app title and health info', async () => {
    render(<App />);

    expect(screen.getByRole('heading', { level: 1, name: /BebshaX/i })).toBeInTheDocument();
    expect(screen.getByText(/Synthetic Persona Research Platform/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/Backend Status:/i)).toBeInTheDocument();
    });
  });
});
