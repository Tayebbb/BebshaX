import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import App from '../src/App';

const AUTH_TOKEN_KEY = 'bebshax_auth_token';

const resetBrowserState = (): void => {
  localStorage.clear();
  window.history.pushState({}, '', '/');
};

const signIn = (): void => {
  localStorage.setItem(AUTH_TOKEN_KEY, 'test-token');
};

const heroSection = (): HTMLElement =>
  screen
    .getByText(/Evidence in\./i)
    .closest('section') as HTMLElement;

const finalCtaSection = (): HTMLElement =>
  screen
    .getByRole('heading', { name: /Describe a business\. Meet its personas\./i })
    .closest('section') as HTMLElement;

describe('BebshaX Premium Landing Page', () => {
  beforeEach(resetBrowserState);
  afterEach(resetBrowserState);

  it('renders core hero storytelling and headline', () => {
    render(<App />);

    expect(
      screen.getByText(/Evidence in\./i)
    ).toBeInTheDocument();

    expect(
      screen.getByText(/Personas out\./i)
    ).toBeInTheDocument();

    expect(
      screen.getByText(/Then interview them\./i)
    ).toBeInTheDocument();

    expect(
      screen.getByText('Synthetic Persona Research')
    ).toBeInTheDocument();
  });

  it('renders all key landing sections and metrics', () => {
    render(<App />);

    // Capability metrics
    expect(screen.getByText('Routing pools')).toBeInTheDocument();
    expect(screen.getByText('Provenance classes')).toBeInTheDocument();
    expect(screen.getByText('Failure kinds')).toBeInTheDocument();

    // Problem section
    expect(
      screen.getByText(/Asking a model for a persona is easy\./i)
    ).toBeInTheDocument();

    // How it works
    expect(
      screen.getByText(/From a business description to/i)
    ).toBeInTheDocument();

    // Console showcase
    expect(
      screen.getByText(/Four tabs\./i)
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

  it('sends a signed-out visitor from the hero CTA to the sign-up page', () => {
    render(<App />);

    const cta = within(heroSection()).getByRole('button', {
      name: /Generate your first persona/i,
    });
    fireEvent.click(cta);

    expect(
      screen.getByRole('heading', { name: /Create your account/i })
    ).toBeInTheDocument();
  });

  it('opens the console from the hero CTA when the visitor is already signed in', async () => {
    signIn();
    render(<App />);

    const cta = await within(heroSection()).findByRole('button', {
      name: /Launch Console/i,
    });
    fireEvent.click(cta);

    expect(
      await screen.findByRole('heading', { name: /What do you want to find out/i })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: /Create your account/i })
    ).not.toBeInTheDocument();
  });

  it('opens the console from the final CTA when the visitor is already signed in', async () => {
    signIn();
    render(<App />);

    const cta = await within(finalCtaSection()).findByRole('button', {
      name: /Launch Console/i,
    });
    fireEvent.click(cta);

    expect(
      await screen.findByRole('heading', { name: /What do you want to find out/i })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: /Create your account/i })
    ).not.toBeInTheDocument();
  });
});
