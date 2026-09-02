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
      screen.getByText('Ask anything about your business idea, or pick any study type below.')
    ).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText(/Describe your business idea/i);
    expect(textarea).toBeInTheDocument();

    const submitBtn = screen.getByLabelText(/Start research study/i);
    expect(submitBtn).toBeInTheDocument();
  });

  it('renders all 4 study types with descriptions', () => {
    const handleStart = vi.fn();
    render(<NewStudyView onStartStudy={handleStart} />);

    expect(screen.getByText('User Interviews')).toBeInTheDocument();
    expect(
      screen.getByText(/Simulate in-depth discovery interviews with synthetic personas/i)
    ).toBeInTheDocument();

    expect(screen.getByText('Concept & Demand')).toBeInTheDocument();
    expect(
      screen.getByText(/Validate product-market fit, value proposition desirability/i)
    ).toBeInTheDocument();

    expect(screen.getByText('Message Testing')).toBeInTheDocument();
    expect(
      screen.getByText(/Test pitch clarity, value proposition framing/i)
    ).toBeInTheDocument();

    expect(screen.getByText('Pricing & WTP')).toBeInTheDocument();
    expect(
      screen.getByText(/Validate price elasticity, subscription ceilings/i)
    ).toBeInTheDocument();
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

  it('calls onStartStudy with selected type and entered idea when card clicked or submitted', async () => {
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
