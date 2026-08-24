import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { StudyWorkflowView } from '../src/components/dashboard/views/StudyWorkflowView';
import { api } from '../src/services/api';

describe('Study Design Copilot LLM Conversational Initiation & Persona Roles Generation', () => {
  beforeEach(() => {
    api.setMockMode(true);
    vi.restoreAllMocks();
  });

  const renderWorkflow = (initialPrompt?: string) => {
    return render(
      <StudyWorkflowView
        studyId="tj6FY3cXDO8oxpuxeAMb"
        initialStep={1}
        initialType="interviews"
        initialPrompt={initialPrompt || ''}
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );
  };

  it('automatically triggers Copilot LLM analysis when initial prompt is provided', async () => {
    renderWorkflow(
      'i want to make a study planner ai website for student and basic plan will cost 250 taaka per month'
    );

    // Initial user bubble should appear
    expect(
      screen.getByText(
        'i want to make a study planner ai website for student and basic plan will cost 250 taaka per month'
      )
    ).toBeInTheDocument();

    // Assistant response explaining User Interviews and asking about target users
    await waitFor(() => {
      expect(
        screen.getByText(/Got it — you're exploring a(n)? education or student-focused product/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/What level of students/i)
      ).toBeInTheDocument();
    });
  });

  it('progresses through multi-turn dialogue, shows role selection, generates grounded personas in Step 2, and advances to Step 3', async () => {
    renderWorkflow(
      'i want to make a study planner ai website for student and basic plan will cost 250 taaka per month'
    );

    await waitFor(() => {
      expect(
        screen.getByText(/Got it — you're exploring a(n)? education or student-focused product/i)
      ).toBeInTheDocument();
    });

    // Turn 2: User responds with location
    const input = screen.getByPlaceholderText(/Type here to answer or give more context/i);
    fireEvent.change(input, { target: { value: 'specifically for bangladeshi students' } });
    const sendBtn = screen.getByLabelText(/Send prompt/i);
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(screen.getByText('specifically for bangladeshi students')).toBeInTheDocument();
      expect(
        screen.getByText(/Is this B2C for students directly/i)
      ).toBeInTheDocument();
    });

    // Turn 3: User responds with audience breadth
    const input2 = screen.getByPlaceholderText(/Type here to answer or give more context/i);
    fireEvent.change(input2, { target: { value: 'include Bangladeshi students broadly' } });
    const sendBtn2 = screen.getByLabelText(/Send prompt/i);
    fireEvent.click(sendBtn2);

    // Synthesized RESEARCH GOAL Card should appear
    await waitFor(() => {
      expect(screen.getByText('RESEARCH GOAL')).toBeInTheDocument();
      expect(
        screen.getByText(/Validate whether your education or student-focused product solves a genuine need/i)
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Approve/i })).toBeInTheDocument();
    });

    // Click Approve -> Opens SUGGESTED ROLES FOR YOUR STUDY
    const approveBtn = screen.getByRole('button', { name: /Approve/i });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(screen.getByText(/SUGGESTED ROLES FOR YOUR STUDY/i)).toBeInTheDocument();
      expect(screen.getAllByText(/UNIVERSITY STUDENT/i)[0]).toBeInTheDocument();
      expect(screen.getAllByText(/COLLEGE APPLICANT/i)[0]).toBeInTheDocument();
      expect(screen.getAllByText(/BUSY HIGH SCHOOLER/i)[0]).toBeInTheDocument();
      expect(screen.getByText(/Persona Panel Configured/i)).toBeInTheDocument();
    });

    // Click Generate Personas -> Advances to Step 2 (Personas)
    const generateBtn = screen.getAllByRole('button', { name: /Generate Personas/i })[0];
    fireEvent.click(generateBtn);

    // Verify Step 2 Grounded Personas rendered
    await waitFor(
      () => {
        expect(screen.getByText('Nusrat Jahan')).toBeInTheDocument();
        expect(screen.getByText('The Frugal Striver')).toBeInTheDocument();
        expect(screen.getByText('Farzana Rahman')).toBeInTheDocument();
        expect(screen.getByText('Tanjila Akter')).toBeInTheDocument();
        expect(screen.getByText('Total Personas')).toBeInTheDocument();
      },
      { timeout: 3000 }
    );

    // Click View Full Profile on Nusrat Jahan
    const viewProfileBtns = screen.getAllByText(/View full profile/i);
    fireEvent.click(viewProfileBtns[0]);

    await waitFor(() => {
      expect(screen.getByText(/GROUNDED BEHAVIORAL CLAIMS & PROVENANCE/i)).toBeInTheDocument();
    });

    // Close Modal
    const closeBtn = screen.getAllByRole('button').find((b) => b.querySelector('svg.lucide-x'));
    if (closeBtn) fireEvent.click(closeBtn);

    // Click Generate Script -> Advances to Step 3
    const generateScriptBtn = screen.getByRole('button', { name: /Generate Script/i });
    fireEvent.click(generateScriptBtn);

    await waitFor(() => {
      expect(screen.getByText('Interview Script & Probing Rules')).toBeInTheDocument();
    });
  });
});
