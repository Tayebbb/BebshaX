import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LandingPage } from '../src/components/landing/LandingPage';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';
import { ThemeProvider } from '../src/context/ThemeContext';
import App from '../src/App';
import { api } from '../src/services/api';

const snapshotStorage = (storage: Storage): [string, string][] =>
  Object.keys(storage).map((key) => [key, storage.getItem(key) ?? '']);

const restoreStorage = (storage: Storage, entries: [string, string][]): void => {
  storage.clear();
  entries.forEach(([key, value]) => storage.setItem(key, value));
};

const snapshotAttributes = (element: HTMLElement): [string, string][] =>
  Array.from(element.attributes, (attribute) => [attribute.name, attribute.value]);

const restoreAttributes = (element: HTMLElement, attributes: [string, string][]): void => {
  Array.from(element.attributes).forEach((attribute) => element.removeAttribute(attribute.name));
  attributes.forEach(([name, value]) => element.setAttribute(name, value));
};

const snapshotBrowser = () => ({
  mockMode: api.isMockMode(),
  authToken: api.getAuthToken(),
  user: api.getStoredUser(),
  local: snapshotStorage(localStorage),
  session: snapshotStorage(sessionStorage),
  url: window.location.href,
  historyState: window.history.state as unknown,
  rootAttributes: snapshotAttributes(document.documentElement),
  bodyAttributes: snapshotAttributes(document.body),
});

let previousBrowser: ReturnType<typeof snapshotBrowser>;

beforeEach(() => {
  previousBrowser = snapshotBrowser();
  localStorage.clear();
  sessionStorage.clear();
  window.history.replaceState({}, '', '/');
  api.setMockMode(true);
  api.setAuthToken(null);
  api.setStoredUser(null);
  localStorage.setItem('bebshax_theme', 'dark');

  const originalMatchMedia = window.matchMedia;
  vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({
    ...originalMatchMedia(query),
    matches: query.includes('prefers-reduced-motion: reduce') ||
      (query.includes('max-width') && window.innerWidth === 390),
  }));
});

afterEach(() => {
  cleanup();
  if (vi.isFakeTimers()) {
    vi.clearAllTimers();
    vi.useRealTimers();
  }
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  api.setMockMode(previousBrowser.mockMode);
  api.setAuthToken(previousBrowser.authToken);
  api.setStoredUser(previousBrowser.user);
  restoreStorage(localStorage, previousBrowser.local);
  restoreStorage(sessionStorage, previousBrowser.session);
  window.history.replaceState(previousBrowser.historyState, '', previousBrowser.url);
  restoreAttributes(document.documentElement, previousBrowser.rootAttributes);
  restoreAttributes(document.body, previousBrowser.bodyAttributes);
});

const renderLanding = ({ signedIn = false, mobile = false } = {}) => {
  if (signedIn) api.setAuthToken('test-token');
  if (mobile) vi.stubGlobal('innerWidth', 390);
  const onOpenApp = vi.fn();
  const onOpenAuth = vi.fn();
  const result = render(
    <NavigationProvider>
      <AuthProvider>
        <ThemeProvider>
          <LandingPage onOpenApp={onOpenApp} onOpenAuth={onOpenAuth} />
        </ThemeProvider>
      </AuthProvider>
    </NavigationProvider>,
  );
  return { ...result, onOpenApp, onOpenAuth };
};

const accountAction = (name: RegExp): HTMLElement =>
  screen.queryByRole('menuitem', { name }) ??
  screen.queryByRole('link', { name }) ??
  screen.getByRole('button', { name });

const sampleScreenshot = (): HTMLElement =>
  screen.getByRole('img', { name: /sample.*synthetic|synthetic.*sample/i });

const billingUser = {
  id: 'studio-billing-user', email: 'studio@example.test', full_name: 'Studio Researcher',
  avatar_url: null, is_active: true, is_verified: true,
  auth_provider: 'email' as const, created_at: '2026-09-10T00:00:00Z',
};

const enableBillingFixture = (checkoutMessage: string): ReturnType<typeof vi.fn> => {
  api.setMockMode(false);
  api.setStoredUser(billingUser);
  const request = vi.fn(async (input: RequestInfo | URL) => {
    const path = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, window.location.origin).pathname;
    if (path.endsWith('/auth/me')) return new Response(JSON.stringify(billingUser));
    if (path.endsWith('/payments/subscription')) {
      return new Response(JSON.stringify({ plan: 'free', status: 'active', is_paid: false, has_billing_account: false, billing_enabled: true }));
    }
    if (path.endsWith('/payments/create-checkout-session')) {
      return new Response(JSON.stringify({ detail: checkoutMessage }), { status: 503 });
    }
    throw new Error(`Unexpected fixture request: ${path}`);
  });
  vi.stubGlobal('fetch', request);
  return request;
};

describe('Studio landing contracts', () => {
  it('uses one literal H1 naming BebshaX and synthetic persona research', () => {
    renderLanding();
    const headline = screen.getByRole('heading', { level: 1 });

    expect(headline.tagName).toBe('H1');
    expect(headline).toHaveTextContent(/^BebshaX\.\s*Synthetic\s+persona\s+research\.$/i);
  });

  it('gives the main content landmark an accessible name', () => {
    renderLanding();

    expect(screen.getByRole('main')).toHaveAccessibleName();
  });

  it('organizes the main story into five to seven headed sections', () => {
    renderLanding();
    const main = screen.getByRole('main');
    const sections = Array.from(main.querySelectorAll('section')).filter((section) => {
      const parentSection = section.parentElement?.closest('section');
      return !parentSection || !main.contains(parentSection);
    });

    expect(sections.length).toBeGreaterThanOrEqual(5);
    expect(sections.length).toBeLessThanOrEqual(7);
    sections.forEach((section) => {
      expect(within(section).getAllByRole('heading').length).toBeGreaterThan(0);
    });
  });

  it('provides a skip-to-content link targeting the actual main landmark', () => {
    renderLanding();
    const skipLink = screen.getByRole('link', { name: /skip.*(?:content|main)/i });
    const href = skipLink.getAttribute('href');

    expect(href).toMatch(/^#.+/);
    expect(document.getElementById(decodeURIComponent(href!.slice(1)))).toBe(screen.getByRole('main'));
  });

  it('resolves navigation and footer hash anchors without placeholder links', () => {
    const { container } = renderLanding();
    const landmarks = [
      ...screen.getAllByRole('navigation', { hidden: true }),
      screen.getByRole('contentinfo'),
    ];
    const destinations = landmarks.flatMap((landmark) =>
      Array.from(landmark.querySelectorAll('a[href]'), (link) =>
        new URL(link.getAttribute('href')!, window.location.href)),
    );
    const hashDestinations = destinations.filter((destination) =>
      destination.origin === window.location.origin &&
      destination.pathname === window.location.pathname && destination.hash,
    );

    expect(container.querySelector('a[href="#"]')).not.toBeInTheDocument();
    expect(hashDestinations.length).toBeGreaterThan(0);
    hashDestinations.forEach((destination) => {
      expect(document.getElementById(decodeURIComponent(destination.hash.slice(1)))).toBeInTheDocument();
    });
  });

  it('delegates the signed-out hero Open workspace action to the provided callback', () => {
    const { onOpenApp, onOpenAuth } = renderLanding();
    const hero = screen.getByRole('heading', { level: 1 }).closest('section');
    expect(hero).not.toBeNull();

    fireEvent.click(within(hero!).getByRole('button', { name: /^Open workspace$/i }));

    expect(onOpenApp).toHaveBeenCalledTimes(1);
    expect(onOpenAuth).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe('/');
  });

  it('changes the real document theme and updates the theme button accessible name', () => {
    vi.useFakeTimers();
    renderLanding();
    const toggle = screen.getByRole('button', { name: /light/i });
    expect(document.documentElement.dataset.theme).toBe('dark');

    fireEvent.click(toggle);
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(toggle).toHaveAccessibleName(/dark/i);

    fireEvent.click(toggle);
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(toggle).toHaveAccessibleName(/light/i);
  });

  it('opens a labelled mobile navigation disclosure and focuses its first link', async () => {
    renderLanding({ mobile: true });
    const trigger = screen.getByRole('button', { name: 'Open navigation' });
    const controlledId = trigger.getAttribute('aria-controls');
    expect(controlledId).toBeTruthy();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('navigation', { name: 'Mobile navigation' })).not.toBeInTheDocument();

    fireEvent.click(trigger);
    const navigation = screen.getByRole('navigation', { name: 'Mobile navigation' });
    expect(navigation).toHaveAttribute('id', controlledId!);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(trigger).toHaveAccessibleName('Close navigation');
    await waitFor(() => expect(within(navigation).getAllByRole('link')[0]).toHaveFocus());

    fireEvent.click(screen.getByRole('button', { name: 'Close navigation' }));
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveAccessibleName('Open navigation');
    expect(screen.queryByRole('navigation', { name: 'Mobile navigation' })).not.toBeInTheDocument();
  });

  it('closes mobile navigation with Escape and returns focus to its trigger', async () => {
    renderLanding({ mobile: true });
    const trigger = screen.getByRole('button', { name: 'Open navigation' });
    trigger.focus();
    fireEvent.click(trigger);
    const navigation = screen.getByRole('navigation', { name: 'Mobile navigation' });
    await waitFor(() => expect(within(navigation).getAllByRole('link')[0]).toHaveFocus());

    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });

    expect(screen.queryByRole('navigation', { name: 'Mobile navigation' })).not.toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it('closes mobile navigation after a section anchor is selected', async () => {
    renderLanding({ mobile: true });
    const trigger = screen.getByRole('button', { name: 'Open navigation' });
    fireEvent.click(trigger);
    const navigation = screen.getByRole('navigation', { name: 'Mobile navigation' });
    const anchor = within(navigation).getAllByRole('link').find((link) =>
      link.getAttribute('href')?.startsWith('#'),
    );
    expect(anchor).toBeDefined();

    fireEvent.click(anchor!);

    await waitFor(() => {
      expect(screen.queryByRole('navigation', { name: 'Mobile navigation' })).not.toBeInTheDocument();
    });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('closes a drawer opened at the exact mobile breakpoint when the viewport widens', () => {
    const defaultMedia = window.matchMedia('(max-width: 60rem)');
    const listeners = new Map<string, (event: MediaQueryListEvent) => void>();
    vi.mocked(window.matchMedia).mockImplementation((query) => ({
      ...defaultMedia,
      media: query,
      matches: true,
      addEventListener: (_type: string, listener: EventListenerOrEventListenerObject) => {
        listeners.set(query, listener as (event: MediaQueryListEvent) => void);
      },
      removeEventListener: () => { },
    }));
    renderLanding({ mobile: true });
    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }));
    expect(screen.getByRole('navigation', { name: 'Mobile navigation' })).toBeVisible();

    act(() => listeners.get('(max-width: 60rem)')?.({ matches: false } as MediaQueryListEvent));

    expect(screen.queryByRole('navigation', { name: 'Mobile navigation' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open navigation' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('closes the previous account menu when the active session changes', async () => {
    api.setStoredUser({ ...billingUser, id: 'studio-original', full_name: 'Original Researcher' });
    renderLanding({ signedIn: true });
    await act(async () => { });
    fireEvent.click(screen.getByRole('button', { name: 'Account menu' }));
    expect(screen.getByRole('menu', { name: 'Account' })).toBeVisible();

    await act(async () => {
      api.setAuthToken('replacement-session-token');
      api.setStoredUser({ ...billingUser, id: 'studio-replacement' });
    });

    expect(screen.queryByRole('menu', { name: 'Account' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Account menu' }));
    expect(screen.getByText(billingUser.full_name)).toBeVisible();
    expect(screen.queryByText('Original Researcher')).not.toBeInTheDocument();
  });

  it('preserves current-user information and account access in the authenticated menu', () => {
    renderLanding({ signedIn: true });
    const trigger = screen.getByRole('button', { name: 'Account menu' });
    expect(trigger).toHaveAttribute('aria-label', 'Account menu');

    fireEvent.click(trigger);

    expect(screen.getByText('Test User')).toBeVisible();
    expect(screen.getByText('user@example.com')).toBeVisible();
    expect(accountAction(/^Open workspace$/i)).toBeVisible();
    expect(accountAction(/^(?:log\s*out|sign\s*out)$/i)).toBeVisible();
  });

  it('signs the real mock-mode user out through the account menu', async () => {
    renderLanding({ signedIn: true });
    fireEvent.click(screen.getByRole('button', { name: 'Account menu' }));

    fireEvent.click(accountAction(/^(?:log\s*out|sign\s*out)$/i));

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Account menu' })).not.toBeInTheDocument();
      expect(api.getAuthToken()).toBeNull();
    });
    expect(screen.queryByText('user@example.com')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /sign\s*in/i }).length).toBeGreaterThan(0);
  });

  it('offers actionable free research access while billing is disabled', () => {
    renderLanding();
    const freePlan = screen.getByRole('heading', { name: /\bfree\b/i });
    const pricing = freePlan.closest('section');
    expect(freePlan).toBeVisible();
    expect(pricing).not.toBeNull();
    expect(within(pricing!).getByRole('button', { name: /\bfree\b|open workspace/i })).toBeEnabled();
  });

  it('does not advertise paid plans or checkout to a mock-mode account when billing is disabled', () => {
    renderLanding({ signedIn: true });
    const main = screen.getByRole('main');

    expect(within(main).queryByRole('heading', {
      name: /\bpro\b|\benterprise\b|team\s*(?:&|and)\s*scale/i,
    })).not.toBeInTheDocument();
    expect(within(main).queryByRole('button', {
      name: /\bupgrade\b|\bsubscribe\b|\bcheckout\b/i,
    })).not.toBeInTheDocument();
  });

  it('withdraws paid checkout when the server reports billing has been disabled', async () => {
    enableBillingFixture('Payments are disabled');
    renderLanding({ signedIn: true });
    fireEvent.click(await screen.findByRole('button', { name: 'Upgrade to Pro' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/Paid plans are not enabled/);
    expect(screen.queryByRole('button', { name: 'Upgrade to Pro' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Subscribe to Enterprise' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Free Starter' })).toBeVisible();
  });

  it('keeps paid checkout retryable for a temporary provider failure', async () => {
    enableBillingFixture('Checkout is temporarily unavailable');
    renderLanding({ signedIn: true });
    fireEvent.click(await screen.findByRole('button', { name: 'Upgrade to Pro' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't start checkout/);
    expect(screen.getByRole('button', { name: 'Upgrade to Pro' })).toBeEnabled();
    expect(screen.queryByText(/No payment was taken and no paid access/)).not.toBeInTheDocument();
  });

  it.each(['Terms of Service', 'Privacy Policy'])(
    'opens and dismisses the existing %s legal content from the footer',
    (title) => {
      renderLanding();
      const footer = screen.getByRole('contentinfo');
      fireEvent.click(within(footer).getByRole('button', { name: new RegExp(`^${title}$`, 'i') }));

      const heading = screen.getByRole('heading', { name: new RegExp(`BebshaX ${title}`, 'i') });
      expect(heading).toBeVisible();

      fireEvent.click(screen.getByRole('button', { name: /I Understand/i }));
      expect(heading).not.toBeInTheDocument();
    },
  );

  it('uses a local product screenshot with meaningful SAMPLE synthetic alt text and intrinsic dimensions', () => {
    renderLanding();
    const screenshot = sampleScreenshot();
    const source = screenshot.getAttribute('src');
    expect(screenshot.tagName).toBe('IMG');
    expect(screenshot).toHaveAccessibleName(/workspace|persona|study|research|interview|dashboard|product/i);
    expect(source).toBeTruthy();

    const resource = new URL(source!, window.location.href);
    expect(resource.protocol).toMatch(/^https?:$/);
    expect(resource.origin).toBe(window.location.origin);
    expect(resource.pathname).toMatch(/\.(?:avif|png|jpe?g|webp)$/i);
    expect(screenshot.getAttribute('width')).toMatch(/^[1-9]\d*$/);
    expect(screenshot.getAttribute('height')).toMatch(/^[1-9]\d*$/);
  });

  it('visibly captions the product screenshot as SAMPLE synthetic output rather than observed research', () => {
    renderLanding();
    const figure = sampleScreenshot().closest('figure');
    expect(figure).not.toBeNull();
    const caption = figure!.querySelector('figcaption');

    expect(caption).toBeVisible();
    expect(caption).toHaveTextContent(/\bSAMPLE\b/i);
    expect(caption).toHaveTextContent(/\bsynthetic\b/i);
    expect(caption).toHaveTextContent(/\bnot\s+(?:an?\s+)?(?:observed|real|customer)\b|\bnon[-\s]observed\b/i);
  });

  it('provides a phone-sized SAMPLE screenshot without shrinking the entire desktop workspace', () => {
    renderLanding();
    const screenshot = sampleScreenshot();
    const picture = screenshot.closest('picture');
    expect(picture).not.toBeNull();
    const mobileSource = picture!.querySelector('source[media="(max-width: 40rem)"]');
    expect(mobileSource).toHaveAttribute('srcset', expect.stringContaining('research-workspace-mobile.png'));
    expect(mobileSource).toHaveAttribute('width', '390');
    expect(mobileSource).toHaveAttribute('height', '844');
    expect(screenshot).toHaveAttribute('width', '1200');
    expect(screenshot).toHaveAttribute('height', '1000');
  });

  it('loads the above-fold screenshot eagerly without an unsupported React DOM prop', () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => { });
    renderLanding();

    expect(sampleScreenshot()).toHaveAttribute('loading', 'eager');
    expect(errors.mock.calls.some((entry) => entry.some((value) => String(value).includes('fetchPriority')))).toBe(false);
  });

  it('switches the product gallery between real screenshots with tabs and arrow keys', () => {
    renderLanding();
    const tablist = screen.getByRole('tablist', { name: 'Product views' });
    const tabs = within(tablist).getAllByRole('tab');
    expect(tabs.length).toBeGreaterThanOrEqual(3);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    const first = sampleScreenshot().getAttribute('src');

    fireEvent.click(tabs[1]);
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[0]).toHaveAttribute('aria-selected', 'false');
    const second = sampleScreenshot();
    expect(second.getAttribute('src')).not.toBe(first);
    expect(second.getAttribute('alt')).toMatch(/SAMPLE/);
    expect(second.closest('figure')!.querySelector('figcaption')).toHaveTextContent(/\bSAMPLE\b/);

    tabs[1].focus();
    fireEvent.keyDown(tabs[1], { key: 'ArrowRight' });
    expect(tabs[2]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[2]).toHaveFocus();
    fireEvent.keyDown(tabs[2], { key: 'Home' });
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[0]).toHaveFocus();
    expect(sampleScreenshot().getAttribute('src')).toBe(first);
  });
});

describe('Studio landing', () => {
  beforeEach(() => {
    localStorage.clear();
    window.history.pushState({}, '', '/');
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
    window.history.pushState({}, '', '/');
  });

  it('introduces BebshaX as the only primary heading', () => {
    render(<App />);

    expect(screen.getAllByRole('main')).toHaveLength(1);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1, name: /BebshaX\. Synthetic persona research\./i })).toBeVisible();
  });

  it('keeps the research story within seven unframed sections', () => {
    render(<App />);

    const sections = within(screen.getByRole('main')).getAllByRole('region');
    expect(sections.length).toBeGreaterThanOrEqual(5);
    expect(sections.length).toBeLessThanOrEqual(7);
    expect(screen.getByRole('region', { name: 'How it works' })).toBeVisible();
  });

  it('reserves the real workspace image dimensions without a fabricated preview', () => {
    const { container } = render(<App />);

    const image = screen.getByRole('img', { name: /BebshaX research workspace/i });
    const source = new URL(image.getAttribute('src')!, window.location.href);
    expect(source.origin).toBe(window.location.origin);
    expect(source.pathname).toMatch(/\.(?:avif|png|jpe?g|webp)$/i);
    expect(Number(image.getAttribute('width'))).toBeGreaterThan(0);
    expect(Number(image.getAttribute('height'))).toBeGreaterThan(0);
    expect(container.querySelector('canvas')).not.toBeInTheDocument();
  });

  it('frames synthetic research as hypotheses rather than validated customers', () => {
    render(<App />);

    expect(screen.getByText(/Develop hypotheses to test with real people\./i)).toBeVisible();
    expect(screen.getByText(/Synthetic personas are not real participants or validated demand\./i)).toBeVisible();
    expect(screen.queryByText(/realistic customers|free providers and a local model/i)).not.toBeInTheDocument();
  });
});