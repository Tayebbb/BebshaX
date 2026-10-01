import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { DashboardLayout } from '../src/components/dashboard/DashboardLayout';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';
import { api } from '../src/services/api';
import { Button, Callout, ConfidenceBar, EmptyState, Metric, CommandMenu, type CommandItem } from '../src/components/ui';

const renderShell = (path = '/create-study', role: 'user' | 'developer' = 'user') => {
  api.setStoredUser({
    id: 'studio_shell_user',
    email: 'shell@example.test',
    full_name: 'Shell Reviewer',
    avatar_url: null,
    is_active: true,
    is_verified: true,
    auth_provider: 'email',
    created_at: '2026-09-12T00:00:00Z',
    role,
  });
  window.history.pushState({}, '', path);
  return render(
    <NavigationProvider>
      <AuthProvider>
        <DashboardLayout />
      </AuthProvider>
    </NavigationProvider>,
  );
};

describe('Console shell — navigation architecture', () => {
  beforeEach(() => {
    api.setMockMode(true);
    localStorage.setItem('bebshax_tour_dismissed', '1');
  });

  it('opens a first visit directly on the study controls without a tour banner', () => {
    localStorage.removeItem('bebshax_tour_dismissed');
    renderShell();
    const main = screen.getByRole('main');
    expect(within(main).queryByText(/New here\? The 3-minute tour/)).not.toBeInTheDocument();
    expect(within(main).getAllByRole('radio')).toHaveLength(4);
    expect(within(main).getByRole('textbox', { name: 'Business idea description' })).toBeEnabled();
    expect(within(main).getByRole('button', { name: 'Start research study' })).toBeInTheDocument();
  });

  it('keeps the desktop sidebar at 240px and preserves its collapsed rail', () => {
    renderShell();
    const sidebar = screen.getByRole('navigation', { name: /primary/i }).closest('aside');
    expect(sidebar).toHaveStyle({ width: '240px' });
    fireEvent.click(screen.getByRole('button', { name: 'Toggle sidebar' }));
    expect(sidebar).toHaveStyle({ width: '72px' });
  });

  it('groups regular-user navigation into Workspace and Study with one current page', () => {
    renderShell('/dashboard');
    const nav = screen.getByRole('navigation', { name: /primary/i });
    expect(within(nav).getByText('Workspace')).toBeInTheDocument();
    expect(within(nav).getByText('Study')).toBeInTheDocument();
    expect(within(nav).queryByText('System')).not.toBeInTheDocument();
    expect(within(nav).queryByRole('button', { name: 'Routing & Provenance' })).not.toBeInTheDocument();
    const current = within(nav).getAllByRole('button').filter((b) => b.getAttribute('aria-current') === 'page');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent('Dashboard');
  });

  it('includes System navigation for a developer account', () => {
    renderShell('/dashboard', 'developer');
    const nav = screen.getByRole('navigation', { name: /primary/i });
    expect(within(nav).getByText('System')).toBeInTheDocument();
    expect(within(nav).getByRole('button', { name: 'Routing & Provenance' })).toBeInTheDocument();
  });

  it('does not mount diagnostics for a regular user visiting the router URL', async () => {
    const routes = vi.spyOn(api, 'getRoutesStatus');
    try {
      renderShell('/router');
      expect(await screen.findByRole('heading', { name: 'Developer access required' })).toBeInTheDocument();
      expect(routes).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole('button', { name: 'Back to studies' }));
      await waitFor(() => expect(window.location.pathname).toBe('/dashboard'));
    } finally {
      routes.mockRestore();
    }
  });

  it('tells the user when study-scoped tabs have no study to work in', () => {
    renderShell('/dashboard');
    expect(screen.getByText('No study selected')).toBeInTheDocument();
  });

  it('shows the active study in the Study group when a study is open', async () => {
    renderShell('/research/tj6FY3cXDO8oxpuxeAMb/step1');
    await waitFor(() => {
      expect(screen.queryByText('No study selected')).toBeNull();
    });
    const chip = screen.getByRole('button', { name: /^Current study/i });
    expect(chip).toHaveAttribute('aria-current', 'page');
    expect(chip).toHaveTextContent(/Step 1/);
  });

  it('keeps the selected study when an unscoped Study tab is opened', async () => {
    renderShell('/research/tj6FY3cXDO8oxpuxeAMb/step1');
    await waitFor(() => expect(screen.queryByText('No study selected')).toBeNull());

    fireEvent.click(screen.getByRole('button', { name: 'Interviews' }));

    await waitFor(() => expect(screen.queryByText('No study selected for interviews')).toBeNull());
    expect(screen.getByRole('button', { name: 'Interviews' })).toHaveAttribute('aria-current', 'page');
  });

  it('opens evidence for the library-selected study and shares that scope with the shell', async () => {
    renderShell('/persona-library');
    const studyPicker = await screen.findByRole<HTMLSelectElement>('combobox', { name: 'Active study' });
    await waitFor(() => expect(studyPicker.value).not.toBe(''));
    const [selectedStudy] = within(studyPicker).getAllByRole<HTMLOptionElement>('option')
      .filter((option) => option.value && option.value !== studyPicker.value);
    expect(selectedStudy).toBeDefined();

    fireEvent.change(studyPicker, { target: { value: selectedStudy.value } });
    const openers = await screen.findAllByRole('button', { name: 'Open profile' });
    expect(studyPicker).toHaveValue(selectedStudy.value);
    // Live 2026-09-14: the library's picker was local state, so the Study group
    // still read "No study selected" while the library showed another study.
    await waitFor(() => expect(screen.queryByText('No study selected')).toBeNull());
    expect(screen.getByTitle(/^Open “.*” workflow$/)).toBeInTheDocument();
    fireEvent.click(openers[0]);
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/ }));
    fireEvent.click(screen.getByRole('button', { name: /View in Evidence Laboratory/ }));

    await waitFor(() => {
      expect(window.location.pathname).toBe(`/research/${selectedStudy.value}/evidence`);
    });
  });

  it('renders a breadcrumb that names the section and page', () => {
    renderShell('/router', 'developer');
    const crumbs = screen.getByRole('navigation', { name: /breadcrumb/i });
    expect(within(crumbs).getByText('System')).toBeInTheDocument();
    expect(within(crumbs).getByText('Routing & Provenance')).toHaveAttribute('aria-current', 'page');
  });

  it('exposes a skip link that targets the main landmark', () => {
    renderShell('/dashboard');
    const link = screen.getByRole('link', { name: /skip to main content/i });
    expect(link).toHaveAttribute('href', '#bx-main');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'bx-main');
  });

  it('reports backend state as text, not colour alone', () => {
    renderShell('/dashboard');
    expect(screen.getByRole('status', { name: /sample data/i })).toBeInTheDocument();
  });
});

describe('Console shell — command menu', () => {
  beforeEach(() => {
    api.setMockMode(true);
    localStorage.setItem('bebshax_tour_dismissed', '1');
  });

  it('opens with Ctrl+K, filters as you type, and Enter navigates', async () => {
    renderShell('/dashboard', 'developer');
    expect(screen.queryByRole('dialog', { name: /command menu/i })).toBeNull();
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true });
    const dialog = await screen.findByRole('dialog', { name: /command menu/i });
    const input = within(dialog).getByRole('combobox');
    fireEvent.change(input, { target: { value: 'routing' } });
    const options = within(dialog).getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent('Routing & Provenance');
    fireEvent.keyDown(dialog, { key: 'Enter' });
    await waitFor(() => {
      expect(window.location.pathname).toBe('/router');
    });
    expect(screen.queryByRole('dialog', { name: /command menu/i })).toBeNull();
  });

  it('does not offer routing commands to a regular account', async () => {
    renderShell('/dashboard');
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true });
    const dialog = await screen.findByRole('dialog', { name: /command menu/i });
    fireEvent.change(within(dialog).getByRole('combobox'), { target: { value: 'routing' } });
    expect(within(dialog).queryByRole('option')).not.toBeInTheDocument();
    expect(within(dialog).getByText(/Nothing matches/i)).toBeInTheDocument();
  });

  it('opens from the toolbar button and closes on Escape', async () => {
    renderShell('/dashboard');
    fireEvent.click(screen.getByRole('button', { name: /open command menu/i }));
    const dialog = await screen.findByRole('dialog', { name: /command menu/i });
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
  });

  it('says so when nothing matches instead of showing an empty box', async () => {
    renderShell('/dashboard');
    fireEvent.keyDown(document, { key: 'K', ctrlKey: true });
    const dialog = await screen.findByRole('dialog', { name: /command menu/i });
    fireEvent.change(within(dialog).getByRole('combobox'), { target: { value: 'zzqx' } });
    expect(within(dialog).getByText(/Nothing matches/i)).toBeInTheDocument();
  });

  it('lists recent studies so a returning user can jump straight back in', async () => {
    renderShell('/dashboard');
    await screen.findAllByText('Price Tracker Demand');
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true });
    const dialog = await screen.findByRole('dialog', { name: /command menu/i });
    fireEvent.change(within(dialog).getByRole('combobox'), { target: { value: 'price tracker' } });
    expect(within(dialog).getByRole('option', { name: /Price Tracker Demand/i })).toBeInTheDocument();
  });
});

describe('CommandMenu primitive — keyboard model', () => {
  const items: CommandItem[] = [
    { id: 'a', label: 'Alpha', group: 'G', onSelect: () => {} },
    { id: 'b', label: 'Beta', group: 'G', onSelect: () => {} },
  ];

  it('moves the selection with arrow keys and wraps', () => {
    render(<CommandMenu open onClose={() => {}} items={items} />);
    const dialog = screen.getByRole('dialog');
    const [a, b] = screen.getAllByRole('option');
    expect(a).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(dialog, { key: 'ArrowDown' });
    expect(b).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(dialog, { key: 'ArrowDown' });
    expect(a).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(dialog, { key: 'ArrowUp' });
    expect(b).toHaveAttribute('aria-selected', 'true');
  });

  it('renders nothing while closed', () => {
    const { container } = render(<CommandMenu open={false} onClose={() => {}} items={items} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('UI primitives — honest states', () => {
  it('Metric renders an em dash for a missing value, never a fabricated zero', () => {
    render(<Metric label="Latency" value={null} note="not yet measured" />);
    expect(screen.getByText('—')).toHaveAttribute('aria-label', 'not measured');
    expect(screen.getByText('not yet measured')).toBeInTheDocument();
  });

  it('ConfidenceBar exposes a meter with the percentage and says "not measured" for null', () => {
    const { rerender } = render(<ConfidenceBar value={0.62} label="Evidence coverage" />);
    const meter = screen.getByRole('meter', { name: /evidence coverage/i });
    expect(meter).toHaveAttribute('aria-valuenow', '62');
    expect(screen.getByText('62%')).toBeInTheDocument();
    rerender(<ConfidenceBar value={null} label="Evidence coverage" />);
    expect(screen.getByText('not measured')).toBeInTheDocument();
    expect(screen.getByRole('meter')).not.toHaveAttribute('aria-valuenow');
  });

  it('ConfidenceBar clamps out-of-range ratios', () => {
    render(<ConfidenceBar value={1.7} label="Coverage" />);
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '100');
  });

  it('Callout announces errors and keeps informational notes polite', () => {
    render(
      <>
        <Callout tone="error" title="Generation failed">Nothing was saved.</Callout>
        <Callout tone="info">Evidence found.</Callout>
      </>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Generation failed');
    expect(screen.getByRole('status')).toHaveTextContent('Evidence found.');
  });

  it('EmptyState always pairs the message with a next action when given one', () => {
    render(
      <EmptyState title="No personas yet" description="Generate them from your research goal." actions={<Button variant="primary">Generate personas</Button>} />,
    );
    expect(screen.getByRole('heading', { name: 'No personas yet' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Generate personas' })).toBeInTheDocument();
  });

  it('Button in loading state is disabled and marked busy', () => {
    render(<Button loading>Saving</Button>);
    const btn = screen.getByRole('button', { name: /saving/i });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('aria-busy', 'true');
  });
});
