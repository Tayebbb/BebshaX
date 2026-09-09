import { StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { DashboardLayout } from '../src/components/dashboard/DashboardLayout';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';
import { api } from '../src/services/api';
import type { Persona, Study, StudyReport } from '../src/types';

const deferred = <Value,>() => {
  let resolve!: (value: Value) => void;
  const promise = new Promise<Value>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
};

const emptyStudyFixture = (id: string, title: string): Study => ({
  id,
  title,
  type: 'interviews',
  prompt: '',
  status: 'draft',
  step: 1,
  is_demo: false,
  persona_count: 0,
  persona_ids: [],
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
  copilot_messages: [],
  suggested_roles: [],
  personas_data: [],
  script_questions: [],
});

const renderShell = (path: string, strict = false) => {
  window.history.pushState({}, '', path);
  const shell = (
    <NavigationProvider>
      <AuthProvider>
        <DashboardLayout />
      </AuthProvider>
    </NavigationProvider>
  );
  return render(strict ? <StrictMode>{shell}</StrictMode> : shell);
};

describe('Exhibition navigation through the real console shell', () => {
  let previousMockMode: boolean;

  beforeEach(() => {
    previousMockMode = api.isMockMode();
    api.setMockMode(true);
    localStorage.clear();
    localStorage.setItem('bebshax_tour_dismissed', '1');
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockRejectedValue(new Error('Unexpected network request')));
    vi.spyOn(api, 'getStudies').mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    api.setMockMode(previousMockMode);
    localStorage.clear();
    window.history.replaceState({}, '', '/');
  });

  it('clears populated study A state when the sidebar opens empty study B without changing tabs', async () => {
    const timestamp = '2026-09-09T10:00:00Z';
    const savedReply = 'Study A needs interviews about office refill subscriptions.';
    const persona: Persona = {
      id: 'persona_exhibition_a',
      business_id: 'business_exhibition_a',
      name: 'Synthetic Office Manager A',
      status: 'active',
      version: 1,
      archetype: 'Office Manager',
      tagline: 'A synthetic profile belonging only to study A.',
      demographics: {
        age: 35,
        gender: 'Unspecified',
        occupation: 'Office Manager',
        income_bracket: 'Not stated',
        location: 'Synthetic location',
        education: 'Not stated',
      },
      attributes: [],
      consistency_score: 0,
      grounding_ratio: 0,
      critic_notes: '',
      generation_model: 'test/synthetic-fixture',
      created_at: timestamp,
    };
    const populatedStudy: Study = {
      id: 'study_exhibition_a',
      title: 'Refill Study A',
      type: 'interviews',
      prompt: 'Study A investigates office refill subscriptions.',
      status: 'completed',
      step: 1,
      is_demo: false,
      persona_count: 1,
      persona_ids: [persona.id],
      created_at: timestamp,
      updated_at: timestamp,
      copilot_messages: [
        { id: 'message_a_user', role: 'user', content: 'Explore office refill subscriptions for study A.' },
        {
          id: 'message_a_assistant',
          role: 'assistant',
          content: savedReply,
          isGoalCard: true,
          goalCardData: {
            title: 'Study A research goal',
            summary: 'Understand refill purchasing in study A.',
            target_audience: 'Office managers',
            core_hypothesis: 'Refill delivery may reduce purchasing effort.',
          },
        },
      ],
      suggested_roles: [{
        id: 'role_exhibition_a',
        role: 'Study A office manager',
        description: 'Purchases refills for an office.',
        count: 1,
        selected: true,
      }],
      personas_data: [persona],
      script_questions: ['How does study A manage office refills?'],
    };
    const emptyStudy: Study = {
      ...populatedStudy,
      id: 'study_exhibition_b',
      title: 'Empty Study B',
      prompt: '',
      status: 'draft',
      persona_count: 0,
      persona_ids: [],
      copilot_messages: [],
      suggested_roles: [],
      personas_data: [],
      script_questions: [],
    };
    const report: StudyReport = {
      id: 'report_exhibition_a',
      study_id: populatedStudy.id,
      executive_summary: 'A report belonging only to study A.',
      key_findings: ['Study A purchasing needs further research.'],
      recommendations: ['Validate study A with real participants.'],
    };
    const studies = [populatedStudy, emptyStudy];
    vi.mocked(api.getStudies).mockResolvedValue(studies);
    const getStudy = vi.spyOn(api, 'getStudy').mockImplementation(async (studyId) => (
      studies.find((study) => study.id === studyId) ?? null
    ));
    vi.spyOn(api, 'getStudyById').mockImplementation(async (studyId) => (
      studies.find((study) => study.id === studyId) ?? null
    ));
    vi.spyOn(api, 'getStudyReports').mockImplementation(async (studyId) => (
      studyId === populatedStudy.id ? [report] : []
    ));
    vi.spyOn(api, 'getEvidenceSummary').mockRejectedValue(new Error('Evidence unavailable in this fixture'));
    const updateStudy = vi.spyOn(api, 'updateStudy').mockResolvedValue(emptyStudy);

    await act(async () => { renderShell(`/research/${populatedStudy.id}/step1`); });
    const main = screen.getByRole('main');
    const tabView = main.querySelector('.bx-view');
    expect(tabView).not.toBeNull();
    expect(await within(main).findByText(savedReply)).toBeInTheDocument();
    expect(within(main).getByText('Study A office manager')).toBeInTheDocument();
    expect(within(main).getByRole('button', { name: 'Step 4: Interviews' })).toHaveAttribute('aria-disabled', 'false');
    fireEvent.change(within(main).getByRole('textbox', { name: 'Describe your idea or answer the copilot' }), {
      target: { value: 'Unsent context belonging only to study A.' },
    });

    const sidebar = screen.getByRole('complementary');
    await act(async () => {
      fireEvent.click(within(sidebar).getByRole('button', { name: emptyStudy.title }));
    });

    expect(getStudy).toHaveBeenCalledWith(emptyStudy.id);
    expect(window.location.pathname).toBe(`/research/${emptyStudy.id}/step1`);
    expect(await within(main).findByTitle(emptyStudy.title)).toBeInTheDocument();
    expect(main.querySelector('.bx-view')).toBe(tabView);
    await waitFor(() => {
      expect(within(main).queryByText(savedReply)).not.toBeInTheDocument();
      expect(within(main).queryByRole('heading', { name: 'Suggested roles for your study' })).not.toBeInTheDocument();
      expect(within(main).getByText('What business idea or product concept would you like to validate?')).toBeInTheDocument();
      expect(within(main).getByRole('textbox', { name: 'Describe your idea or answer the copilot' })).toHaveValue('');
      for (const step of ['Step 2: Personas', 'Step 3: Script', 'Step 4: Interviews', 'Step 5: Report']) {
        expect(within(main).getByRole('button', { name: step })).toHaveAttribute('aria-disabled', 'true');
      }
    });
    expect(updateStudy).not.toHaveBeenCalled();
  });

  it('re-enables the same new-study form when the parent reports a creation failure', async () => {
    const createStudy = vi.spyOn(api, 'createStudy').mockRejectedValue(new Error('Exhibition service unavailable'));
    renderShell('/create-study');
    const prompt = 'Research a refill subscription for independent office managers.';
    const input = screen.getByRole('textbox', { name: 'Business idea description' });
    const submit = screen.getByRole('button', { name: 'Start research study' });
    fireEvent.change(input, { target: { value: prompt } });
    fireEvent.click(submit);

    expect(submit).toBeDisabled();
    expect(submit).toHaveAccessibleName('Creating study...');
    expect(await screen.findByRole('alert')).toHaveTextContent('Exhibition service unavailable');
    expect(window.location.pathname).toBe('/create-study');
    expect(screen.getByRole('textbox', { name: 'Business idea description' })).toBe(input);
    expect(input).toHaveValue(prompt);
    await waitFor(() => expect(submit).toBeEnabled());
    expect(submit).toHaveAccessibleName('Start research study');
    expect(screen.getByRole('button', { name: /User Interviews/i })).toBeEnabled();
    expect(createStudy).toHaveBeenCalledWith({ type: 'interviews', prompt, status: 'in_progress', step: 1 });

    fireEvent.click(submit);
    await waitFor(() => expect(createStudy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(submit).toBeEnabled());
  });

  it('does not navigate or save when an old report finishes after study A to B to A navigation', async () => {
    const studyA = emptyStudyFixture('study_report_a', 'Report Study A');
    const studyB = emptyStudyFixture('study_report_b', 'Report Study B');
    const studies = [studyA, studyB];
    const pendingReport = deferred<StudyReport>();
    vi.mocked(api.getStudies).mockResolvedValue(studies);
    vi.spyOn(api, 'getStudy').mockImplementation(async (studyId) => (
      studies.find((study) => study.id === studyId) ?? null
    ));
    vi.spyOn(api, 'getStudyById').mockImplementation(async (studyId) => (
      studies.find((study) => study.id === studyId) ?? null
    ));
    vi.spyOn(api, 'getStudyReports').mockResolvedValue([]);
    vi.spyOn(api, 'getEvidenceSummary').mockRejectedValue(new Error('Evidence unavailable in this fixture'));
    const updateStudy = vi.spyOn(api, 'updateStudy').mockResolvedValue(studyA);
    const generateReport = vi.spyOn(api, 'generateStudyReport').mockReturnValue(pendingReport.promise);

    await act(async () => { renderShell(`/research/${studyA.id}/step5`); });
    const main = screen.getByRole('main');
    expect(await within(main).findByTitle(studyA.title)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(within(main).getByRole('button', { name: /Generate Decision Report/i }));
    });
    expect(generateReport).toHaveBeenCalledWith(studyA.id);

    const sidebar = screen.getByRole('complementary');
    await act(async () => { fireEvent.click(within(sidebar).getByRole('button', { name: studyB.title })); });
    expect(await within(main).findByTitle(studyB.title)).toBeInTheDocument();
    await act(async () => { fireEvent.click(within(sidebar).getByRole('button', { name: studyA.title })); });
    expect(await within(main).findByTitle(studyA.title)).toBeInTheDocument();
    expect(window.location.pathname).toBe(`/research/${studyA.id}/step1`);
    const writesBeforeCompletion = updateStudy.mock.calls.length;

    await act(async () => {
      pendingReport.resolve({
        id: 'report_abandoned_visit',
        study_id: studyA.id,
        executive_summary: 'A report from the abandoned visit.',
        key_findings: [],
        recommendations: [],
      });
    });

    expect(window.location.pathname).toBe(`/research/${studyA.id}/step1`);
    expect(updateStudy).toHaveBeenCalledTimes(writesBeforeCompletion);
    expect(within(main).getByRole('button', { name: 'Step 5: Report' })).toHaveAttribute('aria-disabled', 'true');
    expect(within(main).queryByText('A report from the abandoned visit.')).not.toBeInTheDocument();
  });

  it('seeds the initial copilot turn once and finishes it under Strict Mode', async () => {
    const prompt = 'Research refill subscriptions for small offices.';
    const created = { ...emptyStudyFixture('study_strict_creation', 'Strict creation'), prompt };
    vi.spyOn(api, 'createStudy').mockResolvedValue(created);
    vi.spyOn(api, 'getStudy').mockResolvedValue(created);
    vi.spyOn(api, 'getStudyById').mockResolvedValue(created);
    vi.spyOn(api, 'getStudyReports').mockResolvedValue([]);
    vi.spyOn(api, 'getEvidenceSummary').mockRejectedValue(new Error('Evidence unavailable in this fixture'));
    vi.spyOn(api, 'updateStudy').mockResolvedValue(created);
    const sendCopilot = vi.spyOn(api, 'sendStudyCopilotMessage').mockResolvedValue({
      reply: 'The first copilot reply survived Strict Mode.',
      suggested_study_type: 'interviews',
      is_ready_for_approval: false,
      research_goal_card: null,
      suggested_roles: [],
      served_by: 'test/synthetic-fixture',
    });

    await act(async () => { renderShell('/create-study', true); });
    fireEvent.change(screen.getByRole('textbox', { name: 'Business idea description' }), {
      target: { value: prompt },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Start research study' }));
    });

    expect(await screen.findByText('The first copilot reply survived Strict Mode.')).toBeInTheDocument();
    expect(sendCopilot).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('textbox', { name: 'Describe your idea or answer the copilot' })).toBeEnabled();
  });

  it('ignores a creation result after the user leaves and returns to a fresh creation form', async () => {
    const pendingStudy = deferred<Study>();
    vi.spyOn(api, 'createStudy').mockReturnValue(pendingStudy.promise);
    await act(async () => { renderShell('/create-study'); });
    fireEvent.change(screen.getByRole('textbox', { name: 'Business idea description' }), {
      target: { value: 'An abandoned creation request.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Start research study' }));
    const sidebar = screen.getByRole('complementary');
    await act(async () => { fireEvent.click(within(sidebar).getByRole('button', { name: 'Dashboard' })); });
    await act(async () => { fireEvent.click(within(sidebar).getByRole('button', { name: 'New Study' })); });
    const currentInput = screen.getByRole('textbox', { name: 'Business idea description' });
    fireEvent.change(currentInput, { target: { value: 'The current creation draft.' } });

    await act(async () => {
      pendingStudy.resolve(emptyStudyFixture('study_abandoned_creation', 'Abandoned creation'));
    });

    expect(window.location.pathname).toBe('/create-study');
    expect(currentInput).toHaveValue('The current creation draft.');
    expect(screen.getByRole('button', { name: 'Start research study' })).toBeEnabled();
    expect(within(sidebar).queryByRole('button', { name: 'Abandoned creation' })).not.toBeInTheDocument();
  });
});