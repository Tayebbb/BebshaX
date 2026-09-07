import React from 'react';

interface MetricProps {
  label: React.ReactNode;
  /** Pass `null` for "not measured" — renders an em dash, never a fabricated 0. */
  value: React.ReactNode | null;
  /** The honest footnote: what the number is derived from, or that it is not a measurement. */
  note?: React.ReactNode;
  className?: string;
}

export const Metric: React.FC<MetricProps> = ({ label, value, note, className }) => {
  const missing = value === null || value === undefined || value === '';
  return (
    <div className={`bx-metric${className ? ` ${className}` : ''}`}>
      <span className="bx-metric__label">{label}</span>
      <span className={`bx-metric__value${missing ? ' bx-metric__value--muted' : ''}`} aria-label={missing ? 'not measured' : undefined}>
        {missing ? '—' : value}
      </span>
      {note && <span className="bx-metric__note">{note}</span>}
    </div>
  );
};
