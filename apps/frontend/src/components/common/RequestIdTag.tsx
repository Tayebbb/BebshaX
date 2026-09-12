import React, { useEffect, useRef, useState } from 'react';
import { Check, Copy } from 'lucide-react';

/** Small monospace "Request ID: …" tag with a copy button. Renders nothing when
 * there is no id — an error without a traceable request must not pretend to have one. */
export const RequestIdTag: React.FC<{ requestId?: string | null; style?: React.CSSProperties }> = ({
  requestId,
  style,
}) => {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const copyAttempt = useRef(0);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setCopyState('idle');
    return () => {
      copyAttempt.current += 1;
      if (copyTimer.current !== null) clearTimeout(copyTimer.current);
      copyTimer.current = null;
    };
  }, [requestId]);

  if (!requestId) return null;
  const copied = copyState === 'copied';

  const copy = () => {
    const attempt = ++copyAttempt.current;
    if (copyTimer.current !== null) clearTimeout(copyTimer.current);
    copyTimer.current = null;
    setCopyState('idle');
    const fail = () => {
      if (copyAttempt.current === attempt) setCopyState('failed');
    };

    try {
      const clipboard = navigator.clipboard;
      if (typeof clipboard?.writeText !== 'function') {
        fail();
        return;
      }
      clipboard.writeText(requestId).then(() => {
        if (copyAttempt.current !== attempt) return;
        setCopyState('copied');
        copyTimer.current = setTimeout(() => {
          copyTimer.current = null;
          setCopyState('idle');
        }, 1500);
      }).catch(fail);
    } catch {
      fail();
    }
  };

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '6px',
        fontFamily: 'var(--font-mono, monospace)',
        fontSize: 'var(--fs-xs)',
        color: 'var(--text-muted)',
        overflowWrap: 'anywhere',
        ...style,
      }}
    >
      <span>
        Request ID: <span style={{ color: 'var(--text-secondary)' }}>{requestId}</span>
      </span>
      <button
        type="button"
        className="bx-request-id-copy"
        onClick={copy}
        aria-label={copied ? 'Request ID copied' : 'Copy request ID'}
        title={copied ? 'Copied' : 'Copy request ID'}
        style={{
          background: 'transparent',
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
      {copyState === 'failed' && (
        <span role="status" style={{ fontFamily: 'var(--font-sans)', color: 'var(--text-secondary)' }}>
          Copy unavailable. Select and copy the request ID manually.
        </span>
      )}
    </span>
  );
};
