import { createRef, useRef, type ReactNode, type RefObject } from 'react';
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import '@testing-library/jest-dom';
import { StartInterviewModal } from '../src/components/dashboard/modals/StartInterviewModal';
import { CreateBehavioralTestModal } from '../src/components/dashboard/modals/CreateBehavioralTestModal';
import { api } from '../src/services/api';
import type { SyntheticPersona } from '../src/types';
import { useDialogA11y } from '../src/utils/useDialogA11y';

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

function FocusTrapDialog({ children, initialFocus, suspended = false, onClose = () => {}, label = 'Focus test' }: {
  children: ReactNode;
  initialFocus?: RefObject<HTMLElement | null>;
  suspended?: boolean;
  onClose?: () => void;
  label?: string;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  useDialogA11y(dialogRef, true, onClose, { initialFocus, suspended });
  return <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={label}>{children}</div>;
}

describe('useDialogA11y tabbable controls', () => {
  it.each([
    { name: 'buttons with tabIndex -1', excluded: <button tabIndex={-1}>Excluded control</button> },
    { name: 'buttons with another negative tabIndex', excluded: <button tabIndex={-2}>Excluded control</button> },
    { name: 'hidden buttons', excluded: <button hidden>Excluded control</button> },
    { name: 'hidden ancestors', excluded: <div hidden><button>Excluded control</button></div> },
    { name: 'inert ancestors', excluded: <div ref={(node) => node?.setAttribute('inert', '')}><button>Excluded control</button></div> },
    { name: 'aria-hidden ancestors', excluded: <div aria-hidden="true"><button>Excluded control</button></div> },
    { name: 'hidden inputs', excluded: <input type="hidden" tabIndex={0} /> },
    { name: 'disabled buttons', excluded: <button disabled>Excluded control</button> },
    { name: 'disabled fieldsets', excluded: <fieldset disabled><button>Excluded control</button></fieldset> },
    { name: 'display-none ancestors', excluded: <div style={{ display: 'none' }}><button>Excluded control</button></div> },
    { name: 'visibility-hidden ancestors', excluded: <div style={{ visibility: 'hidden' }}><button>Excluded control</button></div> },
  ])('excludes $name from initial focus and both Tab wrap directions', async ({ excluded }) => {
    render(
      <FocusTrapDialog>
        {excluded}
        <button>First control</button>
        <button>Last control</button>
        {excluded}
      </FocusTrapDialog>,
    );
    const first = screen.getByRole('button', { name: 'First control' });
    const last = screen.getByRole('button', { name: 'Last control' });

    await waitFor(() => expect(first).toHaveFocus());
    fireEvent.keyDown(first, { key: 'Tab', shiftKey: true });
    expect(last).toHaveFocus();
    fireEvent.keyDown(last, { key: 'Tab' });
    expect(first).toHaveFocus();
  });

  it('preserves an explicit negative-tabIndex initial focus target and restores the opener', async () => {
    const initialFocus = createRef<HTMLButtonElement>();
    const opener = <button>Open dialog</button>;
    const { rerender } = render(<div>{opener}</div>);
    const trigger = screen.getByRole('button', { name: 'Open dialog' });
    trigger.focus();

    rerender(
      <div>
        {opener}
        <FocusTrapDialog initialFocus={initialFocus}>
          <button ref={initialFocus} tabIndex={-1}>Dialog introduction</button>
          <button>First control</button>
        </FocusTrapDialog>
      </div>,
    );

    await waitFor(() => expect(screen.getByRole('button', { name: 'Dialog introduction' })).toHaveFocus());
    rerender(<div>{opener}</div>);
    expect(trigger).toHaveFocus();
  });
});

describe('useDialogA11y pending and nested focus', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('focuses an empty dialog through a negative-tabIndex container fallback', () => {
    render(<FocusTrapDialog><p role="status">Saving</p></FocusTrapDialog>);

    act(() => { vi.runOnlyPendingTimers(); });

    expect(screen.getByRole('dialog')).toHaveAttribute('tabindex', '-1');
    expect(screen.getByRole('dialog')).toHaveFocus();
  });

  it.each([false, true])('prevents Tab escape with no tabbable controls (shift=%s)', (shiftKey) => {
    render(<FocusTrapDialog><button disabled>Saving</button></FocusTrapDialog>);
    act(() => { vi.runOnlyPendingTimers(); });

    expect(fireEvent.keyDown(document, { key: 'Tab', shiftKey })).toBe(false);

    expect(screen.getByRole('dialog')).toHaveFocus();
  });

  it('recovers focus when the focused button is replaced by a pending status', async () => {
    const { rerender } = render(<FocusTrapDialog><button>Save</button></FocusTrapDialog>);
    act(() => { vi.runOnlyPendingTimers(); });
    expect(screen.getByRole('button', { name: 'Save' })).toHaveFocus();

    await act(async () => {
      rerender(<FocusTrapDialog><p role="status" tabIndex={-1}>Saving</p></FocusTrapDialog>);
    });

    expect(screen.getByRole('dialog')).toHaveFocus();
    expect(fireEvent.keyDown(document, { key: 'Tab' })).toBe(false);
  });

  it('uses an updated explicit negative-tabIndex initial focus ref during pending replacement', async () => {
    const initialFocus = createRef<HTMLButtonElement>();
    const { rerender } = render(
      <FocusTrapDialog initialFocus={initialFocus}><button key="save" ref={initialFocus}>Save</button></FocusTrapDialog>,
    );
    act(() => { vi.runOnlyPendingTimers(); });

    await act(async () => {
      rerender(
        <FocusTrapDialog initialFocus={initialFocus}>
          <button key="cancel">Cancel</button>
          <button key="status" ref={initialFocus} tabIndex={-1}>Saving status</button>
        </FocusTrapDialog>,
      );
    });

    expect(screen.getByRole('button', { name: 'Saving status' })).toHaveFocus();
    expect(fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })).toBe(false);
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
  });

  it.each([
    { name: 'disabled', attributes: { disabled: true } },
    { name: 'hidden', attributes: { hidden: true } },
    { name: 'negative tabIndex', attributes: { tabIndex: -1 } },
  ])('recomputes the Tab loop when a focused control becomes $name', async ({ attributes }) => {
    const { rerender } = render(
      <FocusTrapDialog><button>Changing control</button><button>Remaining control</button></FocusTrapDialog>,
    );
    act(() => { vi.runOnlyPendingTimers(); });

    await act(async () => {
      rerender(
        <FocusTrapDialog>
          <button {...attributes}>Changing control</button><button>Remaining control</button>
        </FocusTrapDialog>,
      );
    });

    expect(fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })).toBe(false);
    expect(screen.getByRole('button', { name: 'Remaining control' })).toHaveFocus();
  });

  it('recomputes the Tab loop when an element loses its tabIndex attribute', async () => {
    const { rerender } = render(
      <FocusTrapDialog><div tabIndex={0}>Changing control</div><button>Remaining control</button></FocusTrapDialog>,
    );
    act(() => { vi.runOnlyPendingTimers(); });

    await act(async () => {
      rerender(
        <FocusTrapDialog><div>Changing control</div><button>Remaining control</button></FocusTrapDialog>,
      );
    });

    expect(fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })).toBe(false);
    expect(screen.getByRole('button', { name: 'Remaining control' })).toHaveFocus();
  });

  it('leaves autofocus, focus recovery, Tab, and Escape to a child while the parent is suspended', async () => {
    const closeParent = vi.fn();
    const closeChild = vi.fn();
    const dialogs = (parentLabel: string) => (
      <FocusTrapDialog suspended onClose={closeParent} label="Parent dialog">
        <button>{parentLabel}</button>
        <FocusTrapDialog onClose={closeChild} label="Child dialog">
          <button>Child first</button><button>Child last</button>
        </FocusTrapDialog>
      </FocusTrapDialog>
    );
    const { rerender } = render(dialogs('Parent control'));
    act(() => { vi.runOnlyPendingTimers(); });
    expect(screen.getByRole('button', { name: 'Child first' })).toHaveFocus();

    await act(async () => { rerender(dialogs('Parent changed')); });
    const last = screen.getByRole('button', { name: 'Child last' });
    last.focus();
    expect(fireEvent.keyDown(last, { key: 'Tab' })).toBe(false);
    expect(screen.getByRole('button', { name: 'Child first' })).toHaveFocus();

    pressEscape();
    expect(closeChild).toHaveBeenCalledOnce();
    expect(closeParent).not.toHaveBeenCalled();
  });
});

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
