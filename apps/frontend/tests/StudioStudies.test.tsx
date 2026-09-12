import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NewStudyView } from '../src/components/dashboard/views/NewStudyView';
import { StudiesDashboardView } from '../src/components/dashboard/views/StudiesDashboardView';
import { api } from '../src/services/api';
import type { Study, StudyType } from '../src/types';

const studyTypes: { label: string; type: StudyType }[] = [
  { label: 'User Interviews', type: 'interviews' },
  { label: 'Concept & Demand', type: 'landing_page_test' },
  { label: 'Message Testing', type: 'message_testing' },
  { label: 'Pricing & WTP', type: 'ab_test' },
];

const studyId = 'studio-study-pricing';
const studyTitle = 'Student planner pricing';
const otherStudyTitle = 'Message clarity follow-up';
const deleteDialogName = /delete.*study/i;
const confirmDeleteName = /^delete(?: study)?$/i;

function deferred<Result>() {
  let resolve!: (value: Result | PromiseLike<Result>) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<Result>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function makeStudy(id: string, title: string): Study {
  return {
    id,
    title,
    type: 'interviews',
    status: 'draft',
    persona_count: 0,
    persona_ids: [],
    created_at: '2026-09-10T00:00:00Z',
    updated_at: '2026-09-10T00:00:00Z',
  };
}

function getStudyRow(title: string): HTMLElement {
  const row = screen.getAllByRole('listitem').find((item) => (
    within(item).queryByRole('button', { name: title }) !== null
  ));
  if (!row) throw new Error(`Study row not found: ${title}`);
  return row;
}

function expectResearchTotals(values: string[]): void {
  const totals = screen.getByLabelText('Research totals');
  expect(within(totals).getAllByRole('term').map((term) => term.textContent)).toEqual([
    'Studies', 'In progress', 'Completed', 'Synthetic personas',
  ]);
  expect(within(totals).getAllByRole('definition').map((value) => value.textContent)).toEqual(values);
}

async function renderStudies() {
  const onOpenStudy = vi.fn();
  render(<StudiesDashboardView onCreateStudy={vi.fn()} onOpenStudy={onOpenStudy} />);
  await screen.findByRole('button', { name: studyTitle });
  const row = getStudyRow(studyTitle);
  return {
    onOpenStudy,
    row,
    otherRow: getStudyRow(otherStudyTitle),
    list: screen.getByRole('list'),
    optionsButton: within(row).getByRole('button', { name: /study options/i }),
  };
}

function queryDeleteDialog(): HTMLElement | null {
  return screen.queryByRole('alertdialog', { name: deleteDialogName })
    ?? screen.queryByRole('dialog', { name: deleteDialogName });
}

async function findDeleteDialog(): Promise<HTMLElement> {
  return waitFor(() => {
    const dialog = screen.queryByRole('alertdialog', { name: deleteDialogName })
      ?? screen.getByRole('dialog', { name: deleteDialogName });
    expect(dialog).toBeVisible();
    return dialog;
  });
}

async function openDeleteConfirmation(optionsButton: HTMLElement): Promise<HTMLElement> {
  const previousCalls = vi.mocked(api.deleteStudy).mock.calls.length;
  optionsButton.focus();
  fireEvent.click(optionsButton);
  const menu = screen.getByRole('menu', { name: /study options/i });
  await act(async () => {
    fireEvent.click(within(menu).getByRole('menuitem', { name: /^delete$/i }));
  });
  expect(api.deleteStudy).toHaveBeenCalledTimes(previousCalls);
  return findDeleteDialog();
}

function activateWithEnter(control: HTMLElement): void {
  expect(control).toHaveFocus();
  const useNativeActivation = fireEvent.keyDown(control, { key: 'Enter', code: 'Enter' });
  if (useNativeActivation && control instanceof HTMLButtonElement && !control.disabled) {
    fireEvent.click(control, { detail: 0 });
  }
  fireEvent.keyUp(control, { key: 'Enter', code: 'Enter' });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('Studio launcher selection and explicit submission', () => {
  it.each(studyTypes)('changing the selected type to $label never starts or submits an entered prompt', async ({ label }) => {
    const onStartStudy = vi.fn().mockResolvedValue(undefined);
    const onFormSubmit = vi.fn();
    render(
      <div onSubmitCapture={onFormSubmit}>
        <NewStudyView onStartStudy={onStartStudy} />
      </div>,
    );

    expect(screen.getByRole('heading', { name: 'What do you want to find out?' })).toBeVisible();
    const promptInput = screen.getByRole('textbox', { name: 'Business idea description' });
    const previousLabel = label === 'User Interviews' ? 'Message Testing' : 'User Interviews';
    fireEvent.click(screen.getByRole('radio', { name: previousLabel }));
    expect(onStartStudy).not.toHaveBeenCalled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    const enteredPrompt = '  Compare student planner pricing and value  ';
    fireEvent.change(promptInput, { target: { value: enteredPrompt } });
    for (const selectedLabel of [label, previousLabel, label]) {
      await act(async () => {
        fireEvent.click(screen.getByRole('radio', { name: selectedLabel }));
      });
      expect(screen.getByRole('radio', { name: selectedLabel })).toBeChecked();
      expect(onStartStudy).not.toHaveBeenCalled();
      expect(onFormSubmit).not.toHaveBeenCalled();
      expect(promptInput).toHaveValue(enteredPrompt);
      expect(screen.getByRole('button', { name: 'Start research study' })).toBeEnabled();
    }
  });

  it.each(studyTypes)('explicit Start research study submits $label with a trimmed prompt once while pending', async ({ label, type }) => {
    const creation = deferred<void>();
    const onStartStudy = vi.fn().mockReturnValue(creation.promise);
    render(<NewStudyView onStartStudy={onStartStudy} />);

    fireEvent.click(screen.getByRole('radio', { name: label }));
    expect(screen.getByRole('radio', { name: label })).toBeChecked();
    expect(onStartStudy).not.toHaveBeenCalled();
    const promptInput = screen.getByRole('textbox', { name: 'Business idea description' });
    fireEvent.change(promptInput, {
      target: { value: ' \n  Compare student planner pricing and value  \t' },
    });
    const startButton = screen.getByRole('button', { name: 'Start research study' });
    expect(startButton).toBeEnabled();

    await act(async () => {
      fireEvent.click(startButton);
      fireEvent.click(startButton);
      fireEvent.keyDown(promptInput, { key: 'Enter', ctrlKey: true });
      fireEvent.keyDown(promptInput, { key: 'Enter', metaKey: true });
    });
    expect(onStartStudy).toHaveBeenCalledTimes(1);
    expect(onStartStudy).toHaveBeenCalledWith(type, 'Compare student planner pricing and value');
    expect(startButton).toBeDisabled();

    await act(async () => { creation.resolve(undefined); });
    expect(screen.getByRole('button', { name: 'Start research study' })).toBeEnabled();
    expect(onStartStudy).toHaveBeenCalledTimes(1);
  });

  it('retains the failed create prompt and selected type so retry succeeds without re-entry', async () => {
    const onStartStudy = vi.fn()
      .mockRejectedValueOnce(new Error('Study creation is temporarily unavailable.'))
      .mockResolvedValueOnce(undefined);
    render(<NewStudyView onStartStudy={onStartStudy} />);
    const promptInput = screen.getByRole('textbox', { name: 'Business idea description' });
    const enteredPrompt = '  Compare student planner pricing and value  \n';
    fireEvent.change(promptInput, { target: { value: enteredPrompt } });
    fireEvent.click(screen.getByRole('radio', { name: 'Pricing & WTP' }));

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Start research study' }));
    });
    expect(await screen.findByRole('alert')).toHaveTextContent('Study creation is temporarily unavailable.');
    expect(promptInput).toHaveValue(enteredPrompt);
    expect(promptInput).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('radio', { name: 'Pricing & WTP' })).toBeChecked();
    expect(screen.getByRole('button', { name: 'Start research study' })).toBeEnabled();
    expect(onStartStudy).toHaveBeenCalledTimes(1);
    expect(onStartStudy).toHaveBeenLastCalledWith('ab_test', enteredPrompt.trim());

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Start research study' }));
    });
    expect(onStartStudy).toHaveBeenCalledTimes(2);
    expect(onStartStudy).toHaveBeenLastCalledWith('ab_test', enteredPrompt.trim());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(promptInput).toHaveValue(enteredPrompt);
    expect(promptInput).toHaveAttribute('aria-invalid', 'false');
    expect(screen.getByRole('radio', { name: 'Pricing & WTP' })).toBeChecked();
    expect(screen.getByRole('button', { name: 'Start research study' })).toBeEnabled();
  });

  it('plain Enter in the textarea remains native editing and never starts or submits a study', async () => {
    const onStartStudy = vi.fn().mockResolvedValue(undefined);
    const onFormSubmit = vi.fn();
    render(
      <div onSubmitCapture={onFormSubmit}>
        <NewStudyView onStartStudy={onStartStudy} />
      </div>,
    );
    const promptInput = screen.getByRole('textbox', { name: 'Business idea description' });
    const enteredPrompt = 'Compare student planner pricing\nand subscription value';
    fireEvent.change(promptInput, { target: { value: enteredPrompt } });
    promptInput.focus();

    await act(async () => {
      expect(fireEvent.keyDown(promptInput, { key: 'Enter', code: 'Enter' })).toBe(true);
      fireEvent.keyUp(promptInput, { key: 'Enter', code: 'Enter' });
    });
    expect(promptInput).toHaveFocus();
    expect(promptInput).toHaveValue(enteredPrompt);
    expect(onStartStudy).not.toHaveBeenCalled();
    expect(onFormSubmit).not.toHaveBeenCalled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start research study' })).toBeEnabled();
  });

  it('an example prompt fills and focuses the textarea without changing type or starting a study', async () => {
    const onStartStudy = vi.fn().mockResolvedValue(undefined);
    render(<NewStudyView onStartStudy={onStartStudy} />);
    const promptInput = screen.getByRole('textbox', { name: 'Business idea description' });
    fireEvent.change(promptInput, { target: { value: 'An unfinished question' } });
    fireEvent.click(screen.getByRole('radio', { name: 'Message Testing' }));
    const examplePrompt = 'An AI study planner for students with a 250 BDT/month tier';

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: examplePrompt }));
    });
    expect(promptInput).toHaveValue(examplePrompt);
    expect(promptInput).toHaveFocus();
    expect(screen.getByRole('radio', { name: 'Message Testing' })).toBeChecked();
    expect(screen.getByRole('button', { name: 'Start research study' })).toBeEnabled();
    expect(onStartStudy).not.toHaveBeenCalled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('Studio studies deletion and keyboard actions', () => {
  beforeEach(() => {
    vi.spyOn(api, 'getStudies').mockResolvedValue([
      makeStudy(studyId, studyTitle),
      makeStudy('studio-study-messaging', otherStudyTitle),
    ]);
    vi.spyOn(api, 'deleteStudy').mockResolvedValue(true);
  });

  it('keeps research totals unknown while loading or rejected and restores real totals after retry', async () => {
    const initialLoad = deferred<Study[]>();
    const retryLoad = deferred<Study[]>();
    vi.mocked(api.getStudies)
      .mockReturnValueOnce(initialLoad.promise)
      .mockReturnValueOnce(retryLoad.promise);
    render(<StudiesDashboardView onCreateStudy={vi.fn()} onOpenStudy={vi.fn()} />);

    expect(screen.getByRole('status', { name: 'Loading your studies' })).toHaveAttribute('aria-busy', 'true');
    expectResearchTotals(['-', '-', '-', '-']);
    expect(within(screen.getByLabelText('Research totals')).getAllByLabelText('Loading')).toHaveLength(4);
    expect(screen.queryByText('No saved studies yet.')).not.toBeInTheDocument();

    await act(async () => { initialLoad.reject(new Error('Saved studies are temporarily unavailable.')); });
    expect(await screen.findByRole('alert')).toHaveTextContent('Saved studies are temporarily unavailable.');
    expectResearchTotals(['-', '-', '-', '-']);
    expect(within(screen.getByLabelText('Research totals')).getAllByLabelText('Unavailable')).toHaveLength(4);
    expect(screen.queryByText('No saved studies yet.')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(api.getStudies).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('status', { name: 'Loading your studies' })).toBeVisible();
    expectResearchTotals(['-', '-', '-', '-']);
    expect(within(screen.getByLabelText('Research totals')).getAllByLabelText('Loading')).toHaveLength(4);

    await act(async () => {
      retryLoad.resolve([
        { ...makeStudy(studyId, studyTitle), persona_count: 3 },
        { ...makeStudy('studio-study-messaging', otherStudyTitle), status: 'completed', persona_count: 2 },
      ]);
    });
    expect(await screen.findByRole('button', { name: studyTitle })).toBeVisible();
    expect(screen.getByRole('button', { name: otherStudyTitle })).toBeVisible();
    expectResearchTotals(['2', '1', '1', '5']);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Loading your studies' })).not.toBeInTheDocument();
    expect(api.getStudies).toHaveBeenCalledTimes(2);
  });

  it('opens the saved study step from both its title and View Study and defaults an unsaved step to one', async () => {
    vi.mocked(api.getStudies).mockResolvedValueOnce([
      { ...makeStudy(studyId, studyTitle), step: 4, type: 'ab_test' },
      makeStudy('studio-study-messaging', otherStudyTitle),
    ]);
    const { row, optionsButton, onOpenStudy } = await renderStudies();
    expect(row).toHaveTextContent('Step 4');
    expect(row).toHaveTextContent('Pricing & WTP');
    fireEvent.click(within(row).getByRole('button', { name: studyTitle }));
    expect(onOpenStudy).toHaveBeenNthCalledWith(1, studyId, 4);

    fireEvent.click(optionsButton);
    const menu = screen.getByRole('menu', { name: /study options/i });
    fireEvent.click(within(menu).getByRole('menuitem', { name: /view study/i }));
    expect(onOpenStudy).toHaveBeenNthCalledWith(2, studyId, 4);
    expect(menu).not.toBeInTheDocument();
    expect(optionsButton).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(screen.getByRole('button', { name: otherStudyTitle }));
    expect(onOpenStudy).toHaveBeenNthCalledWith(3, 'studio-study-messaging', 1);
    expect(onOpenStudy).toHaveBeenCalledTimes(3);
    expect(api.deleteStudy).not.toHaveBeenCalled();
  });

  it('opens a public completed demo report without inventing research data or including demos in own totals', async () => {
    const report = {
      executive_summary: 'Synthetic findings for a student planner.',
      key_findings: ['The pricing assumptions need validation.'],
      recommendations: ['Validate with observed customers.'],
    };
    vi.mocked(api.getStudies).mockResolvedValueOnce([
      { ...makeStudy('studio-demo-report', 'Public student planner report'), is_demo: true, status: 'completed', step: 5, report },
      { ...makeStudy('studio-demo-fallback', 'Another public report'), is_demo: true, status: 'in_progress', step: 5, persona_count: 7, report },
      makeStudy(studyId, studyTitle),
      { ...makeStudy('studio-study-messaging', otherStudyTitle), status: 'completed', persona_count: 3 },
    ]);
    const { row, list, onOpenStudy } = await renderStudies();
    const demoButton = screen.getByRole('button', { name: /Public student planner report.*Explore Report/i });
    expect(demoButton).toHaveTextContent('Public example with a finished decision report');
    expect(demoButton).not.toHaveTextContent(/personas?|interviews?|minutes?|turns?/i);
    expect(row).toHaveTextContent('No personas yet');
    expect(list).not.toHaveTextContent(/Public student planner report|Another public report/);
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expectResearchTotals(['2', '1', '1', '3']);

    fireEvent.click(demoButton);
    expect(onOpenStudy).toHaveBeenCalledExactlyOnceWith('studio-demo-report', 5);
    expect(api.deleteStudy).not.toHaveBeenCalled();
  });

  it('uses explicit demo visibility rather than ownership for the public example report shortcut', async () => {
    const publicDemo: Study = {
      ...makeStudy('studio-public-demo', 'Public planner report'),
      is_demo: true,
      user_id: 'studio-example-owner',
      status: 'completed',
      step: 5,
      report: { executive_summary: 'Synthetic example report.', key_findings: [], recommendations: [] },
    };
    vi.mocked(api.getStudies).mockResolvedValueOnce([
      { ...publicDemo, id: 'studio-private-report', title: 'Private planner report', user_id: 'studio-owner', is_demo: false },
      publicDemo,
      { ...publicDemo, id: 'studio-ownerless-demo', title: 'Ownerless report example', user_id: undefined, status: 'in_progress' },
      makeStudy(studyId, studyTitle),
      makeStudy('studio-study-messaging', otherStudyTitle),
    ]);
    const { list, onOpenStudy } = await renderStudies();
    expect(within(list).getByRole('button', { name: 'Private planner report' })).toBeVisible();
    expect(within(list).queryByRole('button', { name: 'Public planner report' })).not.toBeInTheDocument();
    const exampleButton = screen.getByRole('button', { name: /Public planner report.*Explore Report/i });
    expect(exampleButton).toHaveTextContent('Public example with a finished decision report');
    fireEvent.click(exampleButton);
    expect(onOpenStudy).toHaveBeenCalledExactlyOnceWith(publicDemo.id, 5);
  });

  it('intersects status with case-insensitive title or prompt search and Clear filters restores all studies', async () => {
    vi.mocked(api.getStudies).mockResolvedValueOnce([
      { ...makeStudy(studyId, studyTitle), prompt: 'Planner pricing assumptions', persona_count: 2 },
      { ...makeStudy('studio-study-messaging', otherStudyTitle), status: 'completed', prompt: 'A planner subscription message', persona_count: 3 },
      { ...makeStudy('studio-study-active', 'Delivery research'), status: 'in_progress', prompt: 'Planner delivery timing', persona_count: 1 },
    ]);
    await renderStudies();
    const searchInput = screen.getByRole('textbox', { name: 'Search your studies' });
    const filters = screen.getByRole('group', { name: 'Filter studies' });
    const visibleTitles = () => screen.getAllByRole('listitem').map((row) => (
      within(row).getAllByRole('button')[0].textContent
    ));
    fireEvent.change(searchInput, { target: { value: 'PLANNER' } });
    fireEvent.click(within(filters).getByRole('button', { name: 'Completed' }));
    expect(visibleTitles()).toEqual([otherStudyTitle]);
    expect(within(filters).getByRole('button', { name: 'Completed' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(within(filters).getByRole('button', { name: 'In Progress' }));
    expect(visibleTitles()).toEqual([studyTitle, 'Delivery research']);
    fireEvent.change(searchInput, { target: { value: 'STUDENT' } });
    expect(visibleTitles()).toEqual([studyTitle]);
    fireEvent.click(within(filters).getByRole('button', { name: 'Completed' }));
    expect(screen.getByText('No studies match your filter.')).toBeVisible();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
    expectResearchTotals(['3', '2', '1', '6']);

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(searchInput).toHaveValue('');
    expect(within(filters).getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(filters).getByRole('button', { name: 'Completed' })).toHaveAttribute('aria-pressed', 'false');
    expect(visibleTitles()).toEqual([studyTitle, otherStudyTitle, 'Delivery research']);
    expectResearchTotals(['3', '2', '1', '6']);
    expect(api.getStudies).toHaveBeenCalledTimes(1);
  });

  it('requires deletion confirmation, visibly reports rejection, preserves rows, and retries without duplicate requests', async () => {
    const retry = deferred<boolean>();
    const deleteStudy = vi.mocked(api.deleteStudy)
      .mockRejectedValueOnce(new Error('Could not delete this study. Please try again.'))
      .mockReturnValueOnce(retry.promise);
    const { optionsButton, row, otherRow, list, onOpenStudy } = await renderStudies();
    const dialog = await openDeleteConfirmation(optionsButton);
    expect(dialog).toHaveTextContent(studyTitle);

    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: confirmDeleteName }));
    });
    const alert = await screen.findByRole('alert');
    expect(alert).toBeVisible();
    expect(alert).toHaveTextContent(/delet/i);
    expect(deleteStudy).toHaveBeenCalledTimes(1);
    expect(deleteStudy).toHaveBeenLastCalledWith(studyId);
    expect(row).toBeInTheDocument();
    expect(otherRow).toBeInTheDocument();
    expect(within(list).getAllByRole('listitem', { hidden: true })).toHaveLength(2);

    const retryDialog = queryDeleteDialog() ?? await openDeleteConfirmation(optionsButton);
    const retryButton = within(retryDialog).getByRole('button', { name: confirmDeleteName });
    expect(retryButton).toBeEnabled();
    await act(async () => {
      fireEvent.click(retryButton);
      fireEvent.click(retryButton);
    });
    expect(deleteStudy).toHaveBeenCalledTimes(2);
    expect(deleteStudy).toHaveBeenLastCalledWith(studyId);
    expect(row).toBeInTheDocument();
    expect(otherRow).toBeInTheDocument();
    expect(within(list).getAllByRole('listitem', { hidden: true })).toHaveLength(2);

    await act(async () => { retry.resolve(true); });
    await waitFor(() => { expect(row).not.toBeInTheDocument(); });
    expect(queryDeleteDialog()).not.toBeInTheDocument();
    expect(otherRow).toBeVisible();
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(deleteStudy).toHaveBeenCalledTimes(2);
    expect(onOpenStudy).not.toHaveBeenCalled();
  });

  it('cancelling deletion keeps both rows and never calls the delete API', async () => {
    const { optionsButton, row, otherRow, onOpenStudy } = await renderStudies();
    const dialog = await openDeleteConfirmation(optionsButton);
    fireEvent.click(within(dialog).getByRole('button', { name: /^cancel$/i }));

    await waitFor(() => { expect(queryDeleteDialog()).not.toBeInTheDocument(); });
    expect(row).toBeVisible();
    expect(otherRow).toBeVisible();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(api.deleteStudy).not.toHaveBeenCalled();
    expect(onOpenStudy).not.toHaveBeenCalled();
  });

  it('ArrowDown opens the action menu and Enter confirms deletion from an accessible dialog with safe Cancel focus', async () => {
    const deletion = deferred<boolean>();
    vi.mocked(api.deleteStudy).mockReturnValueOnce(deletion.promise);
    const { optionsButton, row, otherRow, onOpenStudy } = await renderStudies();
    optionsButton.focus();
    fireEvent.keyDown(optionsButton, { key: 'ArrowDown', code: 'ArrowDown' });

    const menu = await screen.findByRole('menu', { name: /study options/i });
    expect(optionsButton).toHaveAttribute('aria-expanded', 'true');
    const viewAction = within(menu).getByRole('menuitem', { name: /view study/i });
    await waitFor(() => { expect(viewAction).toHaveFocus(); });
    fireEvent.keyDown(viewAction, { key: 'ArrowDown', code: 'ArrowDown' });
    const deleteAction = within(menu).getByRole('menuitem', { name: /^delete$/i });
    expect(deleteAction).toHaveFocus();
    activateWithEnter(deleteAction);

    const dialog = await findDeleteDialog();
    expect(api.deleteStudy).not.toHaveBeenCalled();
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleName(deleteDialogName);
    expect(dialog).toHaveAccessibleDescription(/delet|remov|cannot be undone|permanent/i);
    expect(dialog).toHaveTextContent(studyTitle);
    const cancelButton = within(dialog).getByRole('button', { name: /^cancel$/i });
    await waitFor(() => { expect(cancelButton).toHaveFocus(); });
    const confirmButton = within(dialog).getByRole('button', { name: confirmDeleteName });
    expect(confirmButton).toBeEnabled();
    expect(confirmButton.tabIndex).toBe(0);
    confirmButton.focus();
    await act(async () => { activateWithEnter(confirmButton); });
    expect(api.deleteStudy).toHaveBeenCalledTimes(1);
    expect(api.deleteStudy).toHaveBeenCalledWith(studyId);
    expect(row).toBeInTheDocument();

    await act(async () => { deletion.resolve(true); });
    await waitFor(() => { expect(row).not.toBeInTheDocument(); });
    expect(queryDeleteDialog()).not.toBeInTheDocument();
    expect(otherRow).toBeVisible();
    expect(onOpenStudy).not.toHaveBeenCalled();
  });

  it('Escape dismisses the action menu and returns focus to its Study options trigger', async () => {
    const { optionsButton, row, onOpenStudy } = await renderStudies();
    optionsButton.focus();
    activateWithEnter(optionsButton);
    const menu = screen.getByRole('menu', { name: /study options/i });
    const deleteAction = within(menu).getByRole('menuitem', { name: /^delete$/i });
    deleteAction.focus();
    fireEvent.keyDown(deleteAction, { key: 'Escape', code: 'Escape' });

    await waitFor(() => { expect(menu).not.toBeInTheDocument(); });
    expect(optionsButton).toHaveAttribute('aria-expanded', 'false');
    expect(optionsButton).toHaveFocus();
    expect(row).toBeVisible();
    expect(api.deleteStudy).not.toHaveBeenCalled();
    expect(onOpenStudy).not.toHaveBeenCalled();
  });

  it('Escape dismisses deletion confirmation and returns focus to its Study options trigger without deleting', async () => {
    const { optionsButton, row, onOpenStudy } = await renderStudies();
    const dialog = await openDeleteConfirmation(optionsButton);
    const cancelButton = within(dialog).getByRole('button', { name: /^cancel$/i });
    await waitFor(() => { expect(cancelButton).toHaveFocus(); });
    fireEvent.keyDown(cancelButton, { key: 'Escape', code: 'Escape' });

    await waitFor(() => { expect(queryDeleteDialog()).not.toBeInTheDocument(); });
    expect(screen.queryByRole('menu', { name: /study options/i })).not.toBeInTheDocument();
    expect(optionsButton).toHaveFocus();
    expect(row).toBeVisible();
    expect(api.deleteStudy).not.toHaveBeenCalled();
    expect(onOpenStudy).not.toHaveBeenCalled();
  });

  it('supports ArrowUp, Home and End in the menu and wraps Tab focus inside deletion confirmation', async () => {
    const { optionsButton, onOpenStudy } = await renderStudies();
    optionsButton.focus();
    fireEvent.keyDown(optionsButton, { key: 'ArrowUp', code: 'ArrowUp' });
    const menu = await screen.findByRole('menu', { name: /study options/i });
    const viewAction = within(menu).getByRole('menuitem', { name: /view study/i });
    const deleteAction = within(menu).getByRole('menuitem', { name: /^delete$/i });
    await waitFor(() => { expect(deleteAction).toHaveFocus(); });
    fireEvent.keyDown(deleteAction, { key: 'Home', code: 'Home' });
    expect(viewAction).toHaveFocus();
    fireEvent.keyDown(viewAction, { key: 'End', code: 'End' });
    expect(deleteAction).toHaveFocus();
    fireEvent.keyDown(deleteAction, { key: 'ArrowUp', code: 'ArrowUp' });
    expect(viewAction).toHaveFocus();
    fireEvent.keyDown(viewAction, { key: 'ArrowUp', code: 'ArrowUp' });
    expect(deleteAction).toHaveFocus();
    await act(async () => { activateWithEnter(deleteAction); });

    const dialog = await findDeleteDialog();
    const cancelButton = within(dialog).getByRole('button', { name: /^cancel$/i });
    const confirmButton = within(dialog).getByRole('button', { name: confirmDeleteName });
    await waitFor(() => { expect(cancelButton).toHaveFocus(); });
    fireEvent.keyDown(cancelButton, { key: 'Tab', code: 'Tab', shiftKey: true });
    expect(confirmButton).toHaveFocus();
    fireEvent.keyDown(confirmButton, { key: 'Tab', code: 'Tab' });
    expect(cancelButton).toHaveFocus();
    expect(dialog).toBeVisible();
    expect(api.deleteStudy).not.toHaveBeenCalled();
    expect(onOpenStudy).not.toHaveBeenCalled();
  });

  it('blocks pending deletion dismissal and duplicates, retains a false result, and focuses the empty workspace after retry', async () => {
    const deletion = deferred<boolean>();
    vi.mocked(api.getStudies).mockResolvedValueOnce([makeStudy(studyId, studyTitle)]);
    vi.mocked(api.deleteStudy).mockReturnValueOnce(deletion.promise);
    const onOpenStudy = vi.fn();
    render(<StudiesDashboardView onCreateStudy={vi.fn()} onOpenStudy={onOpenStudy} />);
    await screen.findByRole('button', { name: studyTitle });
    const row = getStudyRow(studyTitle);
    const dialog = await openDeleteConfirmation(within(row).getByRole('button', { name: /study options/i }));
    const confirmButton = within(dialog).getByRole('button', { name: confirmDeleteName });
    const cancelButton = within(dialog).getByRole('button', { name: /^cancel$/i });
    await act(async () => {
      fireEvent.click(confirmButton);
      fireEvent.click(confirmButton);
    });
    expect(api.deleteStudy).toHaveBeenCalledTimes(1);
    expect(api.deleteStudy).toHaveBeenCalledWith(studyId);
    expect(confirmButton).toBeDisabled();
    expect(cancelButton).toBeDisabled();
    await act(async () => {
      fireEvent.click(cancelButton);
      fireEvent.keyDown(dialog, { key: 'Escape', code: 'Escape' });
      fireEvent.pointerDown(document.body, { pointerType: 'mouse', button: 0 });
      fireEvent.click(document.body);
    });
    expect(dialog).toBeVisible();
    expect(row).toBeInTheDocument();
    expect(api.deleteStudy).toHaveBeenCalledTimes(1);

    await act(async () => { deletion.resolve(false); });
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Deletion was not confirmed. Please try again.');
    expect(dialog).toBeVisible();
    expect(row).toBeInTheDocument();
    expect(confirmButton).toBeEnabled();
    expect(cancelButton).toBeEnabled();
    await act(async () => { fireEvent.click(confirmButton); });
    expect(api.deleteStudy).toHaveBeenCalledTimes(2);
    expect(api.deleteStudy).toHaveBeenLastCalledWith(studyId);
    await waitFor(() => { expect(queryDeleteDialog()).not.toBeInTheDocument(); });
    expect(row).not.toBeInTheDocument();
    const emptyHeading = screen.getByRole('heading', { name: 'Your first study starts with a question.' });
    expect(emptyHeading).toBeVisible();
    await waitFor(() => {
      expect(document.activeElement).not.toBe(document.body);
      expect(document.activeElement).toHaveAttribute('tabindex', '-1');
      expect(document.activeElement).toContainElement(emptyHeading);
    });
    expect(screen.getByRole('button', { name: 'Start your first study' })).toBeEnabled();
    expect(onOpenStudy).not.toHaveBeenCalled();
  });
});