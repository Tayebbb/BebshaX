import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PersonaLibraryView } from '../src/components/dashboard/views/PersonaLibraryView';
import { api } from '../src/services/api';
import { AuthPage } from '../src/components/auth/AuthPage';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';
import { clearRouteTimings, readRouteTimings, setRouteTimingEnabled, startRouteTiming } from '../src/performance/routeTiming';

describe('Primary content independence', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    setRouteTimingEnabled(false);
    clearRouteTimings();
    window.history.replaceState({}, '', '/');
  });
  it('renders the persona-list empty result while auxiliary segment metadata remains pending', async () => {
    vi.spyOn(api, 'getStudies').mockResolvedValue([]);
    vi.spyOn(api, 'getStudyPersonas').mockResolvedValue({ personas: [], total: 0, represented_segments: 0, average_grounding_score: 0 });
    vi.spyOn(api, 'getMarketSegments').mockReturnValue(new Promise(() => {}));
    render(<PersonaLibraryView studyId="primary-content-study" />);
    expect(await screen.findByText('No Synthetic Personas Generated Yet')).toBeInTheDocument();
  });

  it('does not count the sign-in boundary as successful private workflow content', async () => {
    api.setMockMode(true);
    api.clearSession();
    window.history.replaceState({}, '', '/research/private-fixture/step2');
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.push(callback); return frames.length; });
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    setRouteTimingEnabled(true);
    startRouteTiming('/research/private-fixture/step2');
    render(<NavigationProvider><AuthProvider><AuthPage initialMode="signin" /></AuthProvider></NavigationProvider>);
    await screen.findByLabelText(/Email/i);
    act(() => { frames.shift()?.(0); frames.shift()?.(0); });

    expect(readRouteTimings()).toEqual([expect.objectContaining({ route: 'workflow-2', stage: 'primary-content', outcome: 'error' })]);
  });
});