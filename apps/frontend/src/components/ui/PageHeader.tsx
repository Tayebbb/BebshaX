import React from 'react';

interface PageHeaderProps {
  /** Small uppercase context line above the title (e.g. section name). */
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  /** One sentence: what this page is for. */
  description?: React.ReactNode;
  actions?: React.ReactNode;
  display?: boolean;
  /** Heading level — every view owns exactly one h1. */
  as?: 'h1' | 'h2';
  id?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({ eyebrow, title, description, actions, display, as = 'h1', id }) => {
  const Heading = as;
  return (
    <div className="bx-page-header">
      <div className="bx-page-header__text">
        {eyebrow && <div className="bx-eyebrow">{eyebrow}</div>}
        <Heading id={id} className={`bx-title${display ? ' bx-title--display' : ''}`}>
          {title}
        </Heading>
        {description && <p className="bx-lede">{description}</p>}
      </div>
      {actions && <div className="bx-page-header__actions">{actions}</div>}
    </div>
  );
};
