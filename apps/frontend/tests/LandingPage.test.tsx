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
    .getByRole('heading', { level: 1, name: /BebshaX\. Synthetic persona research\./i })
    .closest('section') as HTMLElement;

const finalCtaSection = (): HTMLElement =>
  screen
    .getByRole('heading', { name: /Bring your next question\./i })
    .closest('section') as HTMLElement;

describe('BebshaX Premium Landing Page', () => {
  beforeEach(resetBrowserState);
  afterEach(resetBrowserState);

  it('renders core hero storytelling and headline', () => {
    render(<App />);

    expect(
      screen.getByRole('heading', { level: 1, name: /BebshaX\. Synthetic persona research\./i })
    ).toBeInTheDocument();

    expect(
      screen.getByText(/Develop hypotheses to test with real people\./i)
    ).toBeInTheDocument();

    expect(
      screen.getByRole('img', { name: /BebshaX research workspace/i })
    ).toBeInTheDocument();

    expect(
      screen.getByText(/Synthetic personas are not real participants or validated demand\./i)
    ).toBeInTheDocument();
  });

  it('renders the product story and research boundaries', () => {
    render(<App />);

    expect(screen.getByText('Synthetic', { selector: 'dt' })).toBeInTheDocument();
    expect(screen.getByText('Inferred', { selector: 'dt' })).toBeInTheDocument();
    expect(screen.getByText('Observed', { selector: 'dt' })).toBeInTheDocument();

    expect(
      screen.getByRole('heading', { name: /From a question to a research trail/i })
    ).toBeInTheDocument();

    expect(
      screen.getByRole('heading', { name: /A workspace for the questions/i })
    ).toBeInTheDocument();

    expect(
      screen.getByRole('heading', { name: /A few important answers/i })
    ).toBeInTheDocument();
  });

  it('allows navigating to dedicated auth page and returning', async () => {
    render(<App />);

    const signInButtons = screen.getAllByRole('button', { name: /Sign In/i });
    expect(signInButtons.length).toBeGreaterThan(0);
    fireEvent.click(signInButtons[0]);

    expect(
      await screen.findByRole('heading', { name: /Welcome back/i })
    ).toBeInTheDocument();

    const backBtn = screen.getByRole('button', { name: /Back to BebshaX/i });
    fireEvent.click(backBtn);

    expect(
      screen.queryByRole('heading', { name: /Welcome back/i })
    ).not.toBeInTheDocument();
  });

  it('sends a signed-out visitor from the hero CTA to the sign-in page', async () => {
    render(<App />);

    const cta = within(heroSection()).getByRole('button', {
      name: /Open workspace/i,
    });
    fireEvent.click(cta);

    expect(
      await screen.findByRole('heading', { name: /Welcome back/i })
    ).toBeInTheDocument();
  });

  it('opens the console from the hero CTA when the visitor is already signed in', async () => {
    signIn();
    render(<App />);

    const cta = await within(heroSection()).findByRole('button', {
      name: /Open workspace/i,
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
      name: /Open workspace/i,
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
