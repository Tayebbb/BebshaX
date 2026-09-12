import React, { useEffect, useId, useRef } from 'react';
import { X, ShieldCheck, FileText } from 'lucide-react';
import { useDialogA11y } from '../../utils/useDialogA11y';

interface LegalModalProps {
  isOpen: boolean;
  onClose: () => void;
  type: 'terms' | 'privacy';
}

export const LegalModal: React.FC<LegalModalProps> = ({ isOpen, onClose, type }) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useDialogA11y(dialogRef, isOpen, onClose);

  useEffect(() => {
    if (!isOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previousOverflow; };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div
      className="bx-backdrop"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 200,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'var(--scrim)',
        padding: '16px',
      }}
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="bx-modal"
        style={{
          width: '100%',
          maxWidth: '560px',
          maxHeight: 'calc(100dvh - 32px)',
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-soft)',
          borderRadius: '8px',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.6)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          color: 'var(--text-main)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid var(--fill-soft-2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
            {type === 'terms' ? (
              <FileText size={20} color="var(--text-secondary)" style={{ flexShrink: 0 }} />
            ) : (
              <ShieldCheck size={20} color="var(--text-secondary)" style={{ flexShrink: 0 }} />
            )}
            <h2 id={titleId} style={{ fontSize: '1.1rem', fontWeight: 700, margin: 0, color: 'var(--text-main)', overflowWrap: 'anywhere' }}>
              {type === 'terms' ? 'BebshaX Terms of Service' : 'BebshaX Privacy Policy'}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            title="Close legal dialog"
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-secondary)',
              width: '44px',
              height: '44px',
              flexShrink: 0,
              cursor: 'pointer',
              padding: '4px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: '6px',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Scrollable Content */}
        <div
          style={{
            padding: '24px',
            overflowY: 'auto',
            minHeight: 0,
            overscrollBehavior: 'contain',
            fontSize: '0.88rem',
            lineHeight: 1.6,
            color: 'var(--text-secondary)',
          }}
        >
          {type === 'terms' ? (
            <div>
              <p style={{ marginTop: 0 }}>
                <strong>1. Acceptance of Terms:</strong> By accessing or using the BebshaX synthetic persona research platform, you agree to be bound by these terms. BebshaX provides synthetic customer interviews and product-market fit simulations in which every persona attribute is labelled by how it was derived.
              </p>
              <p>
                <strong>2. Legitimate Free-Tier & Zero API Budget Protocol:</strong> BebshaX operates with a strict zero-API-budget routing architecture. Users must not attempt to evade provider rate limits, automate abusive request flooding, or create duplicate accounts.
              </p>
              <p>
                <strong>3. Synthetic Simulation Results:</strong> Generated personas, interviews, and market validation outputs are simulated models designed to accelerate exploratory product research. They complement, but do not replace, primary human qualitative validation.
              </p>
              <p style={{ marginBottom: 0 }}>
                <strong>4. Account Security:</strong> You are responsible for safeguarding your credentials. BebshaX authenticates sessions via secure JWT tokens and Neon Auth protocols.
              </p>
            </div>
          ) : (
            <div>
              <p style={{ marginTop: 0 }}>
                <strong>1. Data Collection:</strong> BebshaX collects your account email, name, and the research study descriptions you provide to synthesize relevant target personas and simulate user interviews.
              </p>
              <p>
                <strong>2. Synthetic Research:</strong> Generated source personas are synthetic. Their profiles and interview responses are exploratory research inputs, not observations of real customers or proof of market demand.
              </p>
              <p>
                <strong>3. Remote Model Processing:</strong> Interviews and other AI features may send research inputs to remote model providers. Those providers apply their own data handling, retention, and training policies. Do not submit real personal data, confidential information, or private customer records.
              </p>
              <p style={{ marginBottom: 0 }}>
                <strong>4. Stored Research:</strong> Studies, generated personas, and interview history can be stored to support ongoing research. Use the available workspace controls to manage saved research.
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '16px 24px',
            borderTop: '1px solid var(--fill-soft-2)',
            display: 'flex',
            justifyContent: 'flex-end',
            flexShrink: 0,
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '8px 20px',
              minWidth: '44px',
              minHeight: '44px',
              borderRadius: '8px',
              background: 'var(--accent-teal)',
              color: 'var(--text-on-accent)',
              border: 'none',
              fontWeight: 700,
              fontSize: '0.85rem',
              cursor: 'pointer',
            }}
          >
            I Understand
          </button>
        </div>
      </div>
    </div>
  );
};
