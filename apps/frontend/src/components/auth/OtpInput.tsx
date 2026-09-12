import React, { useRef, useEffect, useState } from 'react';

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
  const readDigits = () => Array.from({ length }, (_, index) => (
    /^[0-9]$/.test(value[index] ?? '') ? value[index] : ''
  ));
  const [entry, setEntry] = useState(() => ({ value, digits: readDigits() }));
  let digits = entry.digits;
  if (entry.value !== value || digits.length !== length) {
    digits = readDigits();
    setEntry({ value, digits });
  }

  useEffect(() => {
    if (autoFocus && !disabled && inputRefs.current[0]) {
      inputRefs.current[0].focus();
    }
  }, [autoFocus, disabled]);

  const updateDigits = (nextDigits: string[]) => {
    const nextValue = nextDigits.join('');
    setEntry({ value: nextValue, digits: nextDigits });
    onChange(nextValue);
  };

  const enterDigits = (index: number, raw: string) => {
    if (disabled) return;
    const cleaned = raw.replace(/\D/g, '');
    if (cleaned.length > length) return;
    if (!cleaned) {
      if (!raw) {
        updateDigits(digits.map((digit, position) => position === index ? '' : digit));
      }
      return;
    }

    const start = cleaned.length >= length ? 0 : index;
    updateDigits(digits.map((digit, position) => (
      position >= start && position < start + cleaned.length ? cleaned[position - start] : digit
    )));
    inputRefs.current[Math.min(start + cleaned.length, length - 1)]?.focus();
  };

  const handleKeyDown = (index: number, event: React.KeyboardEvent<HTMLInputElement>) => {
    if (disabled) return;
    if (event.key === 'Backspace' || event.key === 'Delete') {
      event.preventDefault();
      const position = event.key === 'Backspace' && !digits[index] && index > 0 ? index - 1 : index;
      updateDigits(digits.map((digit, digitIndex) => digitIndex === position ? '' : digit));
      inputRefs.current[position]?.focus();
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      const position = event.key === 'ArrowLeft' ? Math.max(0, index - 1) : Math.min(length - 1, index + 1);
      inputRefs.current[position]?.focus();
    }
  };

  const handlePaste = (index: number, event: React.ClipboardEvent<HTMLInputElement>) => {
    event.preventDefault();
    const pasted = event.clipboardData.getData('text');
    if (/\d/.test(pasted)) enterDigits(index, pasted);
  };

  return (
    <div
      role="group"
      aria-label={ariaLabelledBy ? undefined : 'Verification code'}
      aria-labelledby={ariaLabelledBy}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '4px',
        width: '100%',
        margin: '12px 0 20px 0',
      }}
    >
      {Array.from({ length }).map((_, index) => (
        <input
          key={index}
          ref={(el) => (inputRefs.current[index] = el)}
          type="text"
          name={`otp-${index + 1}`}
          inputMode="numeric"
          pattern="[0-9]"
          required
          autoComplete={index === 0 ? 'one-time-code' : 'off'}
          maxLength={length}
          disabled={disabled}
          value={digits[index] || ''}
          onChange={(event) => enterDigits(index, event.target.value)}
          onKeyDown={(event) => handleKeyDown(index, event)}
          onPaste={(event) => handlePaste(index, event)}
          onClick={(event) => event.currentTarget.select()}
          aria-label={`Digit ${index + 1}`}
          style={{
            width: '44px',
            minWidth: '44px',
            flex: '0 0 44px',
            boxSizing: 'border-box',
            height: '52px',
            borderRadius: '6px',
            border: '1px solid var(--border-control)',
            background: 'var(--bg-card)',
            color: 'var(--text-main)',
            fontSize: '1.35rem',
            fontWeight: 700,
            textAlign: 'center',
            transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
          }}
          onFocus={(e) => {
            e.currentTarget.select();
            e.target.style.borderColor = 'var(--focus-ring)';
            e.target.style.boxShadow = '0 0 0 2px var(--focus-ring)';
          }}
          onBlur={(e) => {
            e.target.style.borderColor = 'var(--border-control)';
            e.target.style.boxShadow = 'none';
          }}
        />
      ))}
    </div>
  );
};
