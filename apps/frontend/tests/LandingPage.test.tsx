import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import App from '../src/App';

describe('BebshaX Premium Landing Page', () => {
  it('renders core hero storytelling and headline', () => {
    render(<App />);

    expect(
      screen.getByText(/Turn business data into/i)
    ).toBeInTheDocument();

    expect(
      screen.getByText(/better decisions\./i)
    ).toBeInTheDocument();

    expect(
      screen.getByText(/The Smarter Way to Run Your Business/i)
    ).toBeInTheDocument();
  });

  it('renders all key landing sections and metrics', () => {
    render(<App />);

    // Trust metrics
    expect(screen.getByText(/Businesses Analyzed/i)).toBeInTheDocument();
    expect(screen.getByText(/Data Visibility/i)).toBeInTheDocument();
    expect(screen.getByText(/Faster Decision Making/i)).toBeInTheDocument();

    // Problem section
    expect(
      screen.getByText(/Your business already has the data\./i)
    ).toBeInTheDocument();

    // How it works
    expect(
      screen.getByText(/From scattered data to/i)
    ).toBeInTheDocument();

    // Product showcase
    expect(
      screen.getByText(/Everything important\./i)
    ).toBeInTheDocument();

    // FAQ section
    expect(
      screen.getByText(/Everything you need to know\./i)
    ).toBeInTheDocument();
  });

  it('allows navigating to dedicated auth page and returning', () => {
    render(<App />);

    const signInButtons = screen.getAllByRole('button', { name: /Sign In/i });
    expect(signInButtons.length).toBeGreaterThan(0);
    fireEvent.click(signInButtons[0]);

    expect(
      screen.getByRole('heading', { name: /Welcome back/i })
    ).toBeInTheDocument();

    const backBtn = screen.getByRole('button', { name: /Back to BebshaX/i });
    fireEvent.click(backBtn);

    expect(
      screen.queryByRole('heading', { name: /Welcome back/i })
    ).not.toBeInTheDocument();
  });
});
