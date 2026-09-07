import React from 'react';

export type BadgeTone = 'neutral' | 'success' | 'warn' | 'error' | 'info';

interface BadgeProps {
  tone?: BadgeTone;
  /** Renders a status dot before the text (text is mandatory — colour alone never carries state). */
  dot?: boolean;
  live?: boolean;
  mono?: boolean;
  children: React.ReactNode;
  title?: string;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ tone = 'neutral', dot, live, mono, children, title, className }) => (
  <span
    className={`bx-badge${tone !== 'neutral' ? ` bx-badge--${tone}` : ''}${mono ? ' bx-badge--mono' : ''}${className ? ` ${className}` : ''}`}
    title={title}
  >
    {dot && <span className={`bx-dot${tone !== 'neutral' ? ` bx-dot--${tone}` : ''}${live ? ' bx-dot--live' : ''}`} aria-hidden="true" />}
    {children}
  </span>
);
