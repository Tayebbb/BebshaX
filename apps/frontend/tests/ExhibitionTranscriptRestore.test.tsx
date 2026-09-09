import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { StudyWorkflowView } from '../src/components/dashboard/views/StudyWorkflowView';
import { api } from '../src/services/api';
import type { Conversation, Persona, Study } from '../src/types';

const timestamp = '2026-09-09T10:00:00Z';
const persona: Persona = {
  id: 'persona_restore', business_id: 'business_restore', name: 'Synthetic Office Manager',
  status: 'active', version: 1, archetype: 'Office Manager', tagline: 'Synthetic fixture',
  demographics: {
    age: 35, gender: 'Unspecified', occupation: 'Office Manager', income_bracket: 'Unknown',
    location: 'Test City', education: 'Unknown',
  },
  attributes: [], consistency_score: 0, grounding_ratio: 0, critic_notes: '',
  generation_model: 'test/fixture', created_at: timestamp,
};
const study = {
  id: 'study_restore_gate', title: 'Transcript restoration', type: 'interviews',
  prompt: 'Research synthetic office purchasing preferences.', status: 'in_progress', step: 4,
  is_demo: false, persona_count: 1, persona_ids: [persona.id], personas_data: [persona],
  copilot_messages: [], suggested_roles: [], script_questions: ['How do you purchase supplies?'],
  created_at: timestamp, updated_at: timestamp,
} satisfies Study;
const conversation: Conversation = {
  id: 'conversation_restore_gate', persona_id: persona.id, objective: study.prompt,
  status: 'active', created_at: timestamp,
  turns: [{ id: 'saved_reply', role: 'assistant', content: 'Previously saved response.', timestamp }],
};
const storageKey = `bebshax_conv_${study.id}_${persona.id}`;

describe('Study transcript restoration', () => {
  let previousMockMode: boolean;

  beforeEach(() => {
    previousMockMode = api.isMockMode();
    api.setMockMode(true);
    localStorage.clear();
    localStorage.setItem(storageKey, conversation.id);
    vi.spyOn(api, 'getStudy').mockResolvedValue(study);
    vi.spyOn(api, 'getStudyReports').mockResolvedValue([]);
    vi.spyOn(api, 'listStudyInterviews').mockResolvedValue({ interviews: [], total: 0 });
    vi.spyOn(api, 'getEvidenceSummary').mockRejectedValue(new Error('Evidence unavailable'));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    api.setMockMode(previousMockMode);
    localStorage.clear();
  });

  it.each(['success', 'failure'] as const)(
    'blocks early submission and releases the composer after restoration %s',
    async (outcome) => {
      let resolveRestore!: (value: Conversation) => void;
      let rejectRestore!: (error: Error) => void;
      const restoration = new Promise<Conversation>((resolve, reject) => {
        resolveRestore = resolve;
        rejectRestore = reject;
      });
      const getConversation = vi.spyOn(api, 'getConversation').mockReturnValue(restoration);
      const startConversation = vi.spyOn(api, 'startConversation').mockResolvedValue(conversation);
      const sendMessage = vi.spyOn(api, 'sendMessage').mockResolvedValue({
        userTurn: { id: 'new_question', role: 'user', content: 'A follow-up question.', timestamp },
        assistantTurn: { id: 'new_reply', role: 'assistant', content: 'New follow-up response.', timestamp },
      });
      render(
        <StudyWorkflowView
          studyId={study.id} initialStep={4} initialType="interviews" initialPrompt=""
          onExit={vi.fn()} onStepChange={vi.fn()}
        />,
      );
      await waitFor(() => expect(getConversation).toHaveBeenCalledWith(conversation.id));
      const input = screen.getByRole('textbox', { name: 'Follow-up interview question' });
      const form = input.closest('form');
      expect(form).not.toBeNull();
      expect(input).toBeDisabled();
      fireEvent.change(input, { target: { value: 'An early question.' } });
      fireEvent.submit(form!);
      expect(sendMessage).not.toHaveBeenCalled();
      expect(startConversation).not.toHaveBeenCalled();

      await act(async () => {
        if (outcome === 'success') resolveRestore(conversation);
        else rejectRestore(new Error('Saved conversation unavailable'));
      });
      await waitFor(() => expect(input).toBeEnabled());
      if (outcome === 'success') {
        expect(screen.getByText('Previously saved response.')).toBeInTheDocument();
      } else {
        expect(localStorage.getItem(storageKey)).toBeNull();
      }
      fireEvent.change(input, { target: { value: 'A follow-up question.' } });
      fireEvent.submit(form!);
      expect(await screen.findByText('New follow-up response.')).toBeInTheDocument();
      expect(sendMessage).toHaveBeenCalledTimes(1);
      if (outcome === 'success') {
        expect(startConversation).not.toHaveBeenCalled();
        expect(screen.getByText('Previously saved response.')).toBeInTheDocument();
      } else {
        expect(startConversation).toHaveBeenCalledTimes(1);
      }
    },
  );
});