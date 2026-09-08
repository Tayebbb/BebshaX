import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { PromptInputBox } from '@/components/ui/ai-prompt-box';
import { DemoOne } from '@/components/ui/demo';

describe('PromptInputBox Component', () => {
  it('renders input box with placeholder and action buttons', () => {
    render(<PromptInputBox placeholder="Type your interview prompt..." />);
    
    expect(screen.getByPlaceholderText('Type your interview prompt...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /search/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /think/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /canvas/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /voice input/i })).toBeInTheDocument();
  });

  it('triggers onSend with typed text when clicking the send button', () => {
    const handleSend = vi.fn();
    render(<PromptInputBox onSend={handleSend} placeholder="Ask a question..." />);

    const textarea = screen.getByPlaceholderText('Ask a question...');
    fireEvent.change(textarea, { target: { value: 'How often do you make online purchases?' } });

    const sendBtn = screen.getByRole('button', { name: /send message/i });
    fireEvent.click(sendBtn);

    expect(handleSend).toHaveBeenCalledTimes(1);
    expect(handleSend).toHaveBeenCalledWith('How often do you make online purchases?', []);
  });

  it('formats prompt with prefix when toggling search mode', () => {
    const handleSend = vi.fn();
    render(<PromptInputBox onSend={handleSend} placeholder="Ask a question..." />);

    const searchToggle = screen.getByRole('button', { name: /search/i });
    fireEvent.click(searchToggle);

    const textarea = screen.getByPlaceholderText('Search research knowledge...');
    fireEvent.change(textarea, { target: { value: 'competitor pricing' } });

    const sendBtn = screen.getByRole('button', { name: /send message/i });
    fireEvent.click(sendBtn);

    expect(handleSend).toHaveBeenCalledWith('[Search: competitor pricing]', []);
  });

  it('renders the DemoOne showcase container without crashing', () => {
    render(<DemoOne />);
    expect(screen.getByText('BebshaX · AI Research Prompt Box')).toBeInTheDocument();
    expect(screen.getByText('Synthetic Persona Interview Input')).toBeInTheDocument();
  });
});
