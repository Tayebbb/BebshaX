import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { Step2Personas } from '../src/components/dashboard/views/workflow/Step2Personas';
import { Step4Interviews } from '../src/components/dashboard/views/workflow/Step4Interviews';
import { DashboardLayout } from '../src/components/dashboard/DashboardLayout';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';
import { Persona } from '../src/types';
import { api } from '../src/services/api';

const persona = (overrides: Partial<Persona>): Persona =>
  ({
    id: 'per_1',
    name: 'Nusrat Jahan',
    initials: 'NJ',
    archetype: 'The Frugal Striver',
    role_title: 'University Student',
    tagline: 'Every taka counts',
    description: 'Third-year student balancing tuition and tutoring income.',
    quote: '',
    country_code: 'BD',
    grounding_ratio: 0,
    critic_notes: '',
    generation_model: 'llm7/codestral-latest',
    ...overrides,
  } as unknown as Persona);

const renderStep2 = (personas: Persona[]) =>
  render(
    <Step2Personas
      personas={personas}
      personaGenError={null}
      isGeneratingPersonas={false}
      suggestedRoles={[]}
      handleGeneratePersonas={vi.fn()}
      handleStepChange={vi.fn()}
      handleRemovePersona={vi.fn()}
      personaModalTriggerRef={{ current: null }}
      setViewingPersona={vi.fn()}
      isStepUnlocked={() => true}
    />
  );

describe('Blocker 1 — the grounding badge never contradicts the data', () => {
  it('shows a plain-English "not evidence-backed" chip instead of a 0% success pill', () => {
    renderStep2([persona({ grounding_ratio: 0 })]);

    expect(screen.getByText(/Not evidence-backed — inferred from your description/i)).toBeInTheDocument();
    expect(screen.queryByText(/0% evidence-backed/i)).toBeNull();
    expect(screen.queryByText(/% Grounded/i)).toBeNull();
  });

  it('keeps the percentage when the persona really is evidence-backed', () => {
    renderStep2([persona({ grounding_ratio: 0.62 })]);

    expect(screen.getByText(/62% evidence-backed/i)).toBeInTheDocument();
    expect(screen.queryByText(/Not evidence-backed/i)).toBeNull();
  });

  it('honours the backend marker even when a ratio is present', () => {
    renderStep2([
      persona({ grounding_ratio: 0.4, ...( { grounding_basis: 'no_evidence_retrieved' } as object) }),
    ]);

    expect(screen.getByText(/Not evidence-backed — inferred from your description/i)).toBeInTheDocument();
  });

  it('does not claim evidence grounding in the section header', () => {
    renderStep2([persona({ grounding_ratio: 0 })]);

    expect(screen.queryByText(/Grounded in empirical evidence/i)).toBeNull();
    expect(screen.getByText(/0 of 1 backed by retrieved evidence/i)).toBeInTheDocument();
  });

  it('labels a skeleton/template persona and never renders an empty card body', () => {
    renderStep2([
      persona({
        generation_model: 'bebshax/skeleton-fallback',
        critic_notes: 'Model output unusable; template used.',
        description: '',
        tagline: '',
        quote: '',
      }),
    ]);

    expect(screen.getByText(/Template — regenerate for full detail/i)).toBeInTheDocument();
    expect(screen.getByText(/No summary yet/i)).toBeInTheDocument();
  });
});

describe('Blocker 6 — a failed interview is not shown as pending', () => {
  it('renders a Failed state with a retry affordance', () => {
    render(
      <Step4Interviews
        personas={[persona({ id: 'per_fail' })]}
        isBatchRunning={false}
        handleRunBatchInterviews={vi.fn()}
        onCancelBatch={vi.fn()}
        isGeneratingReport={false}
        handleGenerateFinalReport={vi.fn()}
        handleStepChange={vi.fn()}
        interviewStatusMap={{ per_fail: 'failed' }}
        activeInterviewPersonaId="per_fail"
        setActiveInterviewPersonaId={vi.fn()}
        setChatMessages={vi.fn()}
        setConversationId={vi.fn()}
        interviewChatRef={{ current: null }}
        chatMessages={[]}
        isSimulating={false}
        handleSendInterviewMessage={vi.fn()}
        userInputMessage=""
        setUserInputMessage={vi.fn()}
      />
    );

    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.queryByText('Pending')).toBeNull();
    // The action re-runs the whole batch, so it is no longer labelled "Retry".
    expect(screen.getByRole('button', { name: /Re-run all/i })).toBeInTheDocument();
  });
});

describe('Blockers 3 & 4 — failed study creation and study-less navigation', () => {
  beforeEach(() => {
    api.setMockMode(true);
    window.history.pushState({}, '', '/create-study');
    vi.restoreAllMocks();
  });

  const renderDashboard = () =>
    render(
      <NavigationProvider>
        <AuthProvider>
          <DashboardLayout />
        </AuthProvider>
      </NavigationProvider>
    );

  it('reports a failed study creation instead of inventing a study id', async () => {
    const createStudy = vi.spyOn(api, 'createStudy').mockRejectedValue(new Error('Server unavailable'));
    renderDashboard();

    fireEvent.change(screen.getByRole('textbox', { name: 'Business idea description' }), {
      target: { value: 'Test pricing sensitivity' },
    });
    const studyType = screen.getByRole('radio', { name: 'Pricing & WTP' });
    fireEvent.click(studyType);
    expect(studyType).toBeChecked();
    expect(createStudy).not.toHaveBeenCalled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Start research study' }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/couldn't create your study/i);
      expect(screen.getByRole('alert')).toHaveTextContent('Server unavailable');
    });
    expect(createStudy).toHaveBeenCalledExactlyOnceWith({
      type: 'ab_test',
      prompt: 'Test pricing sensitivity',
      status: 'in_progress',
      step: 1,
    });
    // Still on the New Study screen — no fabricated workflow was entered.
    expect(screen.getByText('What do you want to find out?')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/create-study');
  });

  it('sends a study-less user to an empty state, not a hardcoded study route', async () => {
    renderDashboard();

    fireEvent.click(screen.getByRole('button', { name: /^Interviews$/i }));

    await waitFor(() => {
      expect(screen.getByText(/No study selected for interviews/i)).toBeInTheDocument();
    });
    expect(window.location.pathname).toBe('/interviews');
    expect(window.location.pathname).not.toContain('tj6FY3cXDO8oxpuxeAMb');
  });
});
