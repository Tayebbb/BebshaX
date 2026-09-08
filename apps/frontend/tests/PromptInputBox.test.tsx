import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { useState } from 'react';
import { PromptInputBox, PromptInputBoxProps } from '../src/components/ui/PromptInputBox';

function Harness(props: Partial<PromptInputBoxProps> & { onSend: PromptInputBoxProps['onSend'] }) {
  const [value, setValue] = useState('');
  return <PromptInputBox value={value} onValueChange={setValue} aria-label="Message" {...props} />;
}

describe('PromptInputBox', () => {
  it('disables send until there is content, then sends on click', () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);
    const send = screen.getByLabelText('Send message');
    expect(send).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'hello' } });
    expect(send).toBeEnabled();
    fireEvent.click(send);
    expect(onSend).toHaveBeenCalledWith('hello', []);
  });

  it('sends on Enter and inserts newline on Shift+Enter', () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);
    const input = screen.getByLabelText('Message');
    fireEvent.change(input, { target: { value: 'q' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSend).toHaveBeenCalledWith('q', []);
  });

  it('shows a stop control while loading and never sends', () => {
    const onSend = vi.fn();
    const onStop = vi.fn();
    render(<Harness onSend={onSend} onStop={onStop} isLoading />);
    const stop = screen.getByLabelText('Stop generation');
    fireEvent.click(stop);
    expect(onStop).toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
  });

  it('hides the attach button unless attachments are allowed', () => {
    const { rerender } = render(<Harness onSend={vi.fn()} />);
    expect(screen.queryByLabelText('Attach image')).toBeNull();
    rerender(<Harness onSend={vi.fn()} allowAttachments />);
    expect(screen.getByLabelText('Attach image')).toBeInTheDocument();
  });

  it('renders leftActions and footer', () => {
    render(<Harness onSend={vi.fn()} leftActions={<span>Turn 1 of 8</span>} footer="route note" />);
    expect(screen.getByText('Turn 1 of 8')).toBeInTheDocument();
    expect(screen.getByText('route note')).toBeInTheDocument();
  });
});
