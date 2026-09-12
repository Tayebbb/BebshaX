import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { NewStudyView } from '../src/components/dashboard/views/NewStudyView';

describe('NewStudyView Component', () => {
  it('renders research prompt headline, placeholder, and submit button', () => {
    const handleStart = vi.fn();
    render(<NewStudyView onStartStudy={handleStart} />);

    expect(screen.getByText('What do you want to find out?')).toBeInTheDocument();
    expect(
      screen.getByText('Explore questions and assumptions with synthetic personas.')
    ).toBeInTheDocument();
    expect(screen.getByText('Research question', { selector: 'label' })).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText(/Describe your business idea/i);
    expect(textarea).toBeInTheDocument();

    const submitBtn = screen.getByLabelText(/Start research study/i);
    expect(submitBtn).toBeInTheDocument();
  });

  it('renders all 4 study modes and describes only the selected hypothetical exploration', () => {
    const handleStart = vi.fn();
    render(<NewStudyView onStartStudy={handleStart} />);

    expect(screen.getByRole('radio', { name: 'User Interviews' })).toBeChecked();
    expect(
      screen.getByText(/Explore hypothetical routines, needs, and pain points/i)
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', { name: 'Concept & Demand' }));
    expect(
      screen.getByText(/not measured demand or product-market fit/i)
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', { name: 'Message Testing' }));
    expect(
      screen.getByText(/synthetic personas might interpret a message/i)
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', { name: 'Pricing & WTP' }));
    expect(
      screen.getByText(/not measured willingness to pay or price elasticity/i)
    ).toBeInTheDocument();
    expect(handleStart).not.toHaveBeenCalled();
  });

  it('shows validation warning when submitting with empty prompt', async () => {
    const handleStart = vi.fn();
    render(<NewStudyView onStartStudy={handleStart} />);

    const form = screen.getByPlaceholderText(/Describe your business idea/i).closest('form');
    expect(form).not.toBeNull();
    fireEvent.submit(form!);

    await waitFor(() => {
      expect(
        screen.getByText('Describe your product idea before starting the study.')
      ).toBeInTheDocument();
    });
    expect(handleStart).not.toHaveBeenCalled();
  });

  it('calls onStartStudy with the selected type and entered idea only when submitted', async () => {
    const handleStart = vi.fn().mockResolvedValue(undefined);
    render(<NewStudyView onStartStudy={handleStart} />);

    // Select "Pricing & WTP" when empty
    fireEvent.click(screen.getByText('Pricing & WTP'));

    const textarea = screen.getByPlaceholderText(/Describe your business idea/i);
    fireEvent.change(textarea, {
      target: { value: 'AI tool for doctors to automate clinical note transcription' },
    });

    const submitBtn = screen.getByLabelText(/Start research study/i);
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(handleStart).toHaveBeenCalledWith(
        'ab_test',
        'AI tool for doctors to automate clinical note transcription'
      );
    });
  });

  it('supports Ctrl+Enter to submit prompt', async () => {
    const handleStart = vi.fn().mockResolvedValue(undefined);
    render(<NewStudyView onStartStudy={handleStart} />);

    const textarea = screen.getByPlaceholderText(/Describe your business idea/i);
    fireEvent.change(textarea, {
      target: { value: 'Hyperlocal grocery delivery platform with 15-minute SLA' },
    });

    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true });

    await waitFor(() => {
      expect(handleStart).toHaveBeenCalledWith(
        'interviews',
        'Hyperlocal grocery delivery platform with 15-minute SLA'
      );
    });
  });
});
