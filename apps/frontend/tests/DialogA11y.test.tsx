import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom';
import { StartInterviewModal } from '../src/components/dashboard/modals/StartInterviewModal';
import { CreateBehavioralTestModal } from '../src/components/dashboard/modals/CreateBehavioralTestModal';
import { api } from '../src/services/api';
import type { SyntheticPersona } from '../src/types';

vi.mock('../src/services/api', () => ({
  api: {
    startPersonaInterview: vi.fn(),
    getStudyPersonas: vi.fn(),
    listStudySegments: vi.fn(),
    createBehavioralTest: vi.fn(),
    triggerBehavioralTestRun: vi.fn(),
  },
  default: {
    startPersonaInterview: vi.fn(),
    getStudyPersonas: vi.fn(),
    listStudySegments: vi.fn(),
    createBehavioralTest: vi.fn(),
    triggerBehavioralTestRun: vi.fn(),
  },
}));

const persona = {
  id: 'per_01',
  study_id: 'study_1',
  name: 'Nadia Rahman',
  archetype: 'Budget-Conscious Student',
  demographics: { occupation: 'Undergrad Student', location: 'Dhaka' },
  grounding_score: 0,
} as unknown as SyntheticPersona;

/** Escape protocol shared by every modal: capture-phase listener, one surface per press. */
const pressEscape = () => fireEvent.keyDown(document, { key: 'Escape' });

describe('StartInterviewModal dialog semantics', () => {
  it('exposes role=dialog with a labelled title and close button, focuses inside, and closes on Escape', async () => {
    const onClose = vi.fn();
    render(
      <StartInterviewModal isOpen onClose={onClose} persona={persona} studyId="study_1" onInterviewStarted={vi.fn()} />
    );

    const dialog = screen.getByRole('dialog', { name: /Interview Nadia Rahman/ });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByRole('button', { name: /Close interview setup dialog/ })).toBeInTheDocument();

    // Focus moves to the first control inside the dialog (deferred one frame).
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));

    pressEscape();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not close on an Escape another surface already consumed', () => {
    const onClose = vi.fn();
    render(
      <StartInterviewModal isOpen onClose={onClose} persona={persona} studyId="study_1" onInterviewStarted={vi.fn()} />
    );
    const consumed = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true, bubbles: true });
    consumed.preventDefault();
    document.dispatchEvent(consumed);
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('CreateBehavioralTestModal dialog semantics and labelled fields', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.getStudyPersonas as any).mockResolvedValue({ personas: [persona] });
    (api.listStudySegments as any).mockResolvedValue([]);
  });

  it('is a labelled modal dialog whose close button has a name and which closes on Escape', async () => {
    const onClose = vi.fn();
    render(<CreateBehavioralTestModal isOpen onClose={onClose} studyId="study_1" onTestCreated={vi.fn()} />);

    const dialog = screen.getByRole('dialog', { name: /New Behavioral Simulation/ });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByRole('button', { name: /Close new behavioral simulation dialog/ })).toBeInTheDocument();
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));

    pressEscape();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('associates every step-2 text field with its label', async () => {
    render(<CreateBehavioralTestModal isOpen onClose={vi.fn()} studyId="study_1" onTestCreated={vi.fn()} />);

    // Step 1 → pick the pricing test to reach the configuration form.
    fireEvent.click(screen.getByText('Pricing Sensitivity'));

    expect(screen.getByLabelText('Test Name')).toHaveValue('Pricing Sensitivity Simulation');
    expect(screen.getByLabelText(/Proposed Price/)).toBeInTheDocument();
    expect(screen.getByLabelText('Billing Period')).toBeInTheDocument();
    expect(screen.getByLabelText(/Current Alternative Personas Use/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Detailed Scenario Context/)).toBeInTheDocument();
  });
});
