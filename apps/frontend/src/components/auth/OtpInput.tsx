import React, { useRef, useEffect } from 'react';

interface OtpInputProps {
  value: string;
  onChange: (value: string) => void;
  length?: number;
  disabled?: boolean;
  autoFocus?: boolean;
  /** Associates the digit group with an external label element. */
  'aria-labelledby'?: string;
}

export const OtpInput: React.FC<OtpInputProps> = ({
  value,
  onChange,
  length = 6,
  disabled = false,
  autoFocus = true,
  'aria-labelledby': ariaLabelledBy,
}) => {
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Split current value into array of single chars
  const digits = Array.from({ length }, (_, i) => value[i] || '');

  useEffect(() => {
    if (autoFocus && inputRefs.current[0]) {
      inputRefs.current[0].focus();
    }
  }, [autoFocus]);

  const handleChange = (index: number, e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    // Extract only digits
    const cleaned = raw.replace(/\D/g, '');

    if (!cleaned) {
      // Empty
      const newDigits = [...digits];
      newDigits[index] = '';
      onChange(newDigits.join(''));
      return;
    }

    if (cleaned.length > 1) {
      // Pasted or multiple digits entered in single box
      const newDigits = [...digits];
      for (let i = 0; i < cleaned.length && index + i < length; i++) {
        newDigits[index + i] = cleaned[i];
      }
      const finalVal = newDigits.join('').slice(0, length);
      onChange(finalVal);
      const nextFocusIdx = Math.min(index + cleaned.length, length - 1);
      inputRefs.current[nextFocusIdx]?.focus();
      return;
    }

    const newDigits = [...digits];
    newDigits[index] = cleaned[0];
    const finalVal = newDigits.join('');
    onChange(finalVal);

    // Auto-advance to next input
    if (index < length - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace') {
      if (!digits[index] && index > 0) {
        // Current is already empty, move to previous and clear it
        const newDigits = [...digits];
        newDigits[index - 1] = '';
        onChange(newDigits.join(''));
        inputRefs.current[index - 1]?.focus();
      }
    } else if (e.key === 'ArrowLeft' && index > 0) {
      inputRefs.current[index - 1]?.focus();
    } else if (e.key === 'ArrowRight' && index < length - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, length);
    if (!pasted) return;

    const newDigits = Array.from({ length }, (_, i) => pasted[i] || '');
    onChange(newDigits.join(''));

    const focusIdx = Math.min(pasted.length, length - 1);
    inputRefs.current[focusIdx]?.focus();
  };

  return (
    <div
      role="group"
      aria-labelledby={ariaLabelledBy}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '8px',
        width: '100%',
        margin: '12px 0 20px 0',
      }}
      onPaste={handlePaste}
    >
      {Array.from({ length }).map((_, index) => (
        <input
          key={index}
          ref={(el) => (inputRefs.current[index] = el)}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={1}
          disabled={disabled}
          value={digits[index] || ''}
          onChange={(e) => handleChange(index, e)}
          onKeyDown={(e) => handleKeyDown(index, e)}
          aria-label={`Digit ${index + 1}`}
          style={{
            width: '46px',
            height: '52px',
            borderRadius: '10px',
            border: digits[index]
              ? '2px solid var(--accent-teal)'
              : '1px solid var(--border-subtle)',
            background: 'var(--bg-secondary)',
            color: 'var(--text-main)',
            fontSize: '1.35rem',
            fontWeight: 700,
            textAlign: 'center',
            outline: 'none',
            transition: 'all 0.15s ease',
            boxShadow: digits[index] ? '0 0 0 3px var(--accent-subtle)' : 'none',
          }}
          onFocus={(e) => {
            e.target.style.borderColor = 'var(--accent-teal)';
            e.target.style.boxShadow = '0 0 0 3px var(--accent-glow)';
          }}
          onBlur={(e) => {
            if (!digits[index]) {
              e.target.style.borderColor = 'var(--border-subtle)';
              e.target.style.boxShadow = 'none';
            }
          }}
        />
      ))}
    </div>
  );
};
