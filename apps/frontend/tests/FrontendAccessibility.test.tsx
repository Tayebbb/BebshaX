import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';
import { DashboardLayout } from '../src/components/dashboard/DashboardLayout';
import { InterviewsView } from '../src/components/dashboard/views/InterviewsView';
import { Pricing } from '../src/components/landing/Pricing';
import { CommandMenu } from '../src/components/ui/CommandMenu';
import { api } from '../src/services/api';

describe('Frontend keyboard access and commercial honesty', () => {
  afterEach(() => { vi.restoreAllMocks(); window.history.replaceState({}, '', '/'); });

  it('keeps command search focused on Shift+Tab and runs only the highlighted result on Enter', async () => {
    const onClose = vi.fn();
    const items = [
      { id: 'first-command', label: 'First destination', group: 'Workspace', onSelect: vi.fn() },
      { id: 'highlighted-command', label: 'Highlighted destination', group: 'Workspace', onSelect: vi.fn() },
      { id: 'last-command', label: 'Last destination', group: 'Workspace', onSelect: vi.fn() },
    ];
    render(<CommandMenu open onClose={onClose} items={items} />);
    const search = screen.getByRole('combobox', { name: 'Search commands and destinations' });
    const results = within(screen.getByRole('listbox', { name: 'Results' })).getAllByRole('option');

    await waitFor(() => expect(search).toHaveFocus());
    fireEvent.keyDown(search, { key: 'ArrowDown' });
    expect(results[1]).toHaveAttribute('aria-selected', 'true');
    expect(search).toHaveAttribute('aria-activedescendant', results[1].id);
    for (const result of results) expect(result).toHaveAttribute('tabindex', '-1');

    fireEvent.keyDown(search, { key: 'Tab', shiftKey: true });
    expect(search).toHaveFocus();
    for (const result of results) expect(result).not.toHaveFocus();
    fireEvent.keyDown(search, { key: 'Tab' });
    expect(search).toHaveFocus();
    fireEvent.keyDown(document.activeElement ?? search, { key: 'Enter' });

    expect(items[1].onSelect).toHaveBeenCalledOnce();
    expect(items[0].onSelect).not.toHaveBeenCalled();
    expect(items[2].onSelect).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('makes closed mobile navigation inert and traps focus while open', async () => {
    const original = window.matchMedia;
    vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({ ...original(query), matches: query.includes('900px') }));
    api.setMockMode(true);
    vi.spyOn(api, 'getStudies').mockResolvedValue([]);
    render(<NavigationProvider><AuthProvider><DashboardLayout /></AuthProvider></NavigationProvider>);
    const drawer = document.querySelector('aside') as HTMLElement;
    expect(drawer.inert).toBe(true);
    expect(drawer).toHaveAttribute('aria-hidden', 'true');
    const trigger = screen.getByRole('button', { name: /Open navigation/i });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Workspace navigation' });
    await waitFor(() => expect(dialog).toContainElement(document.activeElement as HTMLElement));
    expect(drawer.inert).toBe(false);
    const controls = within(dialog).getAllByRole('button');
    controls[controls.length - 1].focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(drawer.inert).toBe(true);
  });

  it('keeps the mobile drawer behind the command menu until a second Escape', async () => {
    const original = window.matchMedia;
    vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({ ...original(query), matches: query.includes('900px') }));
    api.setMockMode(true);
    vi.spyOn(api, 'getStudies').mockResolvedValue([]);
    render(<NavigationProvider><AuthProvider><DashboardLayout /></AuthProvider></NavigationProvider>);
    const trigger = screen.getByRole('button', { name: /Open navigation/i });
    trigger.focus();
    fireEvent.click(trigger);
    const drawer = screen.getByRole('dialog', { name: 'Workspace navigation' });
    await waitFor(() => expect(drawer).toContainElement(document.activeElement as HTMLElement));

    fireEvent.keyDown(document, { key: 'k', ctrlKey: true });
    const search = screen.getByRole('combobox', { name: 'Search commands and destinations' });
    await waitFor(() => expect(search).toHaveFocus());
    fireEvent.keyDown(search, { key: 'Tab' });
    expect(search).toHaveFocus();
    fireEvent.keyDown(search, { key: 'Tab', shiftKey: true });
    expect(search).toHaveFocus();
    fireEvent.keyDown(search, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Command menu' })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Workspace navigation' })).toBe(drawer);
    await waitFor(() => expect(drawer).toContainElement(document.activeElement as HTMLElement));
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(drawer.inert).toBe(true);
  });

  it('closes the mobile account menu before its containing drawer', async () => {
    const original = window.matchMedia;
    vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({ ...original(query), matches: query.includes('900px') }));
    api.setMockMode(true);
    vi.spyOn(api, 'getStudies').mockResolvedValue([]);
    render(<NavigationProvider><AuthProvider><DashboardLayout /></AuthProvider></NavigationProvider>);
    fireEvent.click(screen.getByRole('button', { name: /Open navigation/i }));
    const drawer = screen.getByRole('dialog', { name: 'Workspace navigation' });
    await waitFor(() => expect(drawer).toContainElement(document.activeElement as HTMLElement));
    const account = drawer.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]');
    if (!account) throw new Error('Missing account menu trigger');
    account.focus();
    fireEvent.click(account);
    expect(screen.getByRole('menu', { name: 'User menu' })).toBeInTheDocument();
    fireEvent.keyDown(account, { key: 'Escape' });
    expect(screen.queryByRole('menu', { name: 'User menu' })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Workspace navigation' })).toBe(drawer);
    expect(account).toHaveFocus();
  });

  it('opens interview cards with keyboard activation and labels the filters', async () => {
    vi.spyOn(api, 'listStudyInterviews').mockResolvedValue({ interviews: [{ id: 'keyboard-interview', persona_name: 'Keyboard fixture', status: 'active', topics_explored: {} }], total: 1 });
    vi.spyOn(api, 'getStudyInterviewMetrics').mockRejectedValue(new Error('Fixture metrics unavailable'));
    const open = vi.fn();
    render(<InterviewsView studyId="keyboard-study" onOpenInterview={open} onNavigateToPersonas={vi.fn()} />);
    const card = await screen.findByRole('button', { name: 'Open interview with Keyboard fixture' });
    card.focus();
    fireEvent.keyDown(card, { key: 'Enter' });
    expect(open).toHaveBeenCalledWith('keyboard-interview');
    expect(screen.getByRole('textbox', { name: 'Search interviews' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Interview status' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Interview objective' })).toBeInTheDocument();
  });

  it('keeps the mock-data notice in the content layout before mobile page actions', async () => {
    const original = window.matchMedia;
    vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({ ...original(query), matches: query.includes('900px') }));
    api.setMockMode(true);
    vi.spyOn(api, 'getStudies').mockResolvedValue([]);
    render(<NavigationProvider><AuthProvider><DashboardLayout /></AuthProvider></NavigationProvider>);

    const notice = await screen.findByTestId('mock-mode-banner');
    const heading = screen.getByRole('heading', { name: 'What do you want to find out?' });
    expect(screen.getByRole('main')).toContainElement(notice);
    expect(notice.parentElement).toHaveStyle({ position: 'relative' });
    expect(notice.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('keeps paid offers and checkout disabled in mock mode even with success query parameters', async () => {
    api.setMockMode(true);
    window.history.replaceState({}, '', '/?checkout=success&plan=enterprise');
    render(<NavigationProvider><AuthProvider><Pricing /></AuthProvider></NavigationProvider>);
    expect(screen.queryByText('Pro Researcher')).not.toBeInTheDocument();
    expect(screen.queryByText(/Unlimited active|Unlimited personas|priority.*routes/i)).not.toBeInTheDocument();
    await expect(api.createCheckoutSession('pro')).rejects.toThrow(/disabled/);
    expect((await api.getSubscription()).is_paid).toBe(false);
  });
});