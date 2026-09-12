import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NavigationProvider, useNavigation } from '../src/context/NavigationContext';
import { parseDashboardPath } from '../src/components/dashboard/DashboardLayout';

function NavigationProbe() {
  const { currentPath, currentSearch, navigate } = useNavigation();
  return <>
    <output data-testid="path">{currentPath}</output>
    <output data-testid="search">{currentSearch}</output>
    <button onClick={() => navigate('/research/study-a/behavioral-tests/compare?run_ids=run-c,run-d')}>Compare</button>
  </>;
}

describe('FE03 URL-owned navigation', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState({}, '', '/');
  });

  it('retains query parameters on initial load and query-only history navigation', () => {
    window.history.replaceState({}, '', '/research/study-a/behavioral-tests/compare?run_ids=run-a,run-b');
    render(<NavigationProvider><NavigationProbe /></NavigationProvider>);
    expect(screen.getByTestId('search')).toHaveTextContent('?run_ids=run-a,run-b');

    fireEvent.click(screen.getByRole('button', { name: 'Compare' }));
    expect(screen.getByTestId('path')).toHaveTextContent('/research/study-a/behavioral-tests/compare');
    expect(screen.getByTestId('search')).toHaveTextContent('?run_ids=run-c,run-d');

    act(() => {
      window.history.replaceState({}, '', '/research/study-a/behavioral-tests/compare?run_ids=run-a,run-b');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(screen.getByTestId('search')).toHaveTextContent('?run_ids=run-a,run-b');
  });

  it('does not push a duplicate history entry for the current pathname and query', () => {
    window.history.replaceState({}, '', '/research/study-a/behavioral-tests/compare?run_ids=run-c,run-d');
    render(<NavigationProvider><NavigationProbe /></NavigationProvider>);
    const push = vi.spyOn(window.history, 'pushState');
    fireEvent.click(screen.getByRole('button', { name: 'Compare' }));
    expect(push).not.toHaveBeenCalled();
  });

  it('distinguishes an omitted workflow step from explicit step one', () => {
    expect(parseDashboardPath('/research/study-a').step).toBeUndefined();
    expect(parseDashboardPath('/research/study-a/step1').step).toBe(1);
    expect(parseDashboardPath('/study/study-a/step3?tab=script').step).toBe(3);
  });

  it('matches route aliases exactly and keeps comparison IDs separate from path IDs', () => {
    expect(parseDashboardPath('/models').tab).toBe('router');
    expect(parseDashboardPath('/models-unrelated').tab).toBe('new-study');
    expect(parseDashboardPath('/research/study-a/behavioral-tests/compare?run_ids=run-a,run-b')).toEqual({
      tab: 'behavioral-compare', studyId: 'study-a', compareRunIds: ['run-a', 'run-b'],
    });
    expect(parseDashboardPath('/evidence').studyId).toBeUndefined();
  });
});