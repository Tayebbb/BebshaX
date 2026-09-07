import React from 'react';

interface ConfidenceBarProps {
  /** 0–1 ratio. `null` renders an honest "not measured" bar, never 0%. */
  value: number | null | undefined;
  label: string;
  /** Text shown right of the bar; defaults to a percentage. */
  valueLabel?: string;
  /** Colour by meaning: ≥0.5 success, >0 warn, 0 muted. Override when the metric is not a coverage ratio. */
  tone?: 'auto' | 'accent' | 'success' | 'warn' | 'muted';
  className?: string;
}

const toneFor = (v: number): 'success' | 'warn' | 'muted' => (v >= 0.5 ? 'success' : v > 0 ? 'warn' : 'muted');

export const ConfidenceBar: React.FC<ConfidenceBarProps> = ({ value, label, valueLabel, tone = 'auto', className }) => {
  const measured = typeof value === 'number' && Number.isFinite(value);
  const clamped = measured ? Math.min(1, Math.max(0, value as number)) : 0;
  const resolvedTone = !measured ? 'muted' : tone === 'auto' ? toneFor(clamped) : tone;
  const text = valueLabel ?? (measured ? `${Math.round(clamped * 100)}%` : 'not measured');
  return (
    <div
      className={`bx-conf${resolvedTone !== 'accent' ? ` bx-conf--${resolvedTone}` : ''}${className ? ` ${className}` : ''}`}
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={measured ? Math.round(clamped * 100) : undefined}
      aria-valuetext={text}
    >
      <div className="bx-conf__label">
        <span>{label}</span>
      </div>
      <div className="bx-conf__track">
        <div className="bx-conf__fill" style={{ width: `${clamped * 100}%` }} />
      </div>
      <span className="bx-conf__value">{text}</span>
    </div>
  );
};
