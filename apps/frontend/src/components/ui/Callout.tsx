import React from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from 'lucide-react';

export type CalloutTone = 'neutral' | 'info' | 'success' | 'warn' | 'error';

interface CalloutProps {
  tone?: CalloutTone;
  title?: React.ReactNode;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  icon?: React.ReactNode;
  /** Errors are announced; everything else is polite status. */
  role?: 'alert' | 'status' | 'note';
  className?: string;
  style?: React.CSSProperties;
}

const DEFAULT_ICON: Record<CalloutTone, React.ReactNode> = {
  neutral: <Info size={16} />,
  info: <Info size={16} />,
  success: <CheckCircle2 size={16} />,
  warn: <AlertTriangle size={16} />,
  error: <AlertCircle size={16} />,
};

export const Callout: React.FC<CalloutProps> = ({ tone = 'neutral', title, children, actions, icon, role, className, style }) => {
  const resolvedRole = role ?? (tone === 'error' ? 'alert' : tone === 'neutral' ? undefined : 'status');
  return (
    <div
      role={resolvedRole}
      className={`bx-callout${tone !== 'neutral' ? ` bx-callout--${tone}` : ''}${className ? ` ${className}` : ''}`}
      style={style}
    >
      <span className="bx-callout__icon" aria-hidden="true">
        {icon ?? DEFAULT_ICON[tone]}
      </span>
      <div className="bx-callout__body">
        {title && <div className="bx-callout__title">{title}</div>}
        {children}
        {actions && <div className="bx-callout__actions">{actions}</div>}
      </div>
    </div>
  );
};
