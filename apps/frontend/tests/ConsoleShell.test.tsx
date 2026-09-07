import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { DashboardLayout } from '../src/components/dashboard/DashboardLayout';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';
import { api } from '../src/services/api';
import { Button, Callout, ConfidenceBar, EmptyState, Metric, CommandMenu, type CommandItem } from '../src/components/ui';

const renderShell = (path = '/create-study') => {
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

  it('groups primary navigation into Workspace / Study / System with one current page', () => {
    renderShell('/dashboard');
    const nav = screen.getByRole('navigation', { name: /primary/i });
    expect(within(nav).getByText('Workspace')).toBeInTheDocument();
    expect(within(nav).getByText('Study')).toBeInTheDocument();
    expect(within(nav).getByText('System')).toBeInTheDocument();
    const current = within(nav).getAllByRole('button').filter((b) => b.getAttribute('aria-current') === 'page');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent('Dashboard');
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

  it('renders a breadcrumb that names the section and page', () => {
    renderShell('/router');
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
    renderShell('/dashboard');
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
