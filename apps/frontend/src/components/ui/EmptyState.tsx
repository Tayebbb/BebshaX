import React from 'react';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: React.ReactNode;
  /** Why it matters / what would fill it — never just "No data". */
  description?: React.ReactNode;
  actions?: React.ReactNode;
  compact?: boolean;
  as?: 'h1' | 'h2' | 'h3' | 'div';
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ icon, title, description, actions, compact, as = 'h3', className }) => {
  const Title = as;
  return (
    <div className={`bx-empty${compact ? ' bx-empty--compact' : ''}${className ? ` ${className}` : ''}`}>
      {icon && (
        <div className="bx-empty__icon" aria-hidden="true">
          {icon}
        </div>
      )}
      <Title className="bx-empty__title">{title}</Title>
      {description && <p className="bx-empty__desc">{description}</p>}
      {actions && <div className="bx-empty__actions">{actions}</div>}
    </div>
  );
};
