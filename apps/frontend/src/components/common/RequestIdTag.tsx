import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';

/** Small monospace "Request ID: …" tag with a copy button. Renders nothing when
 * there is no id — an error without a traceable request must not pretend to have one. */
export const RequestIdTag: React.FC<{ requestId?: string | null; style?: React.CSSProperties }> = ({
  requestId,
  style,
}) => {
  const [copied, setCopied] = useState(false);
  if (!requestId) return null;

  const copy = async () => {
    try {
      await navigator.clipboard?.writeText(requestId);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked — the id is still visible to select by hand.
    }
  };

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        fontFamily: 'var(--font-mono, monospace)',
        fontSize: '0.72rem',
        color: 'var(--text-muted)',
        ...style,
      }}
    >
      <span>
        Request ID: <span style={{ color: 'var(--text-secondary)' }}>{requestId}</span>
      </span>
      <button
        type="button"
        onClick={copy}
        aria-label={copied ? 'Request ID copied' : 'Copy request ID'}
        title={copied ? 'Copied' : 'Copy request ID'}
        style={{
          background: 'transparent',
          border: '1px solid var(--border-subtle)',
          borderRadius: '4px',
          padding: '1px 4px',
          color: 'inherit',
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
        }}
      >
        {copied ? <Check size={11} aria-hidden="true" /> : <Copy size={11} aria-hidden="true" />}
      </button>
    </span>
  );
};
