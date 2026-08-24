import React from 'react';
import { X, ShieldCheck, FileText } from 'lucide-react';

interface LegalModalProps {
  isOpen: boolean;
  onClose: () => void;
  type: 'terms' | 'privacy';
}

export const LegalModal: React.FC<LegalModalProps> = ({ isOpen, onClose, type }) => {
  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 200,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(8, 9, 9, 0.75)',
        backdropFilter: 'blur(6px)',
        padding: '16px',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '560px',
          maxHeight: '80vh',
          backgroundColor: '#121414',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          borderRadius: '16px',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.6)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          color: '#E4E4E7',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {type === 'terms' ? (
              <FileText size={20} color="#F6C878" />
            ) : (
              <ShieldCheck size={20} color="#F6C878" />
            )}
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, margin: 0, color: '#F4F4F5' }}>
              {type === 'terms' ? 'BebshaX Terms of Service' : 'BebshaX Privacy Policy'}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'none',
              border: 'none',
              color: '#A1A1AA',
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
            fontSize: '0.88rem',
            lineHeight: 1.6,
            color: '#D4D4D8',
          }}
        >
          {type === 'terms' ? (
            <div>
              <p style={{ marginTop: 0 }}>
                <strong>1. Acceptance of Terms:</strong> By accessing or using the BebshaX synthetic persona research platform, you agree to be bound by these terms. BebshaX provides empirical evidence-grounded synthetic customer interviews and product-market fit simulations.
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
                <strong>2. Grounded Dataset Provenance:</strong> Persona attributes are tagged with strict provenance classifications (<code style={{ color: '#F6C878' }}>OBSERVED</code>, <code style={{ color: '#F6C878' }}>INFERRED</code>, <code style={{ color: '#F6C878' }}>SYNTHETIC</code>) and grounded against open behavioral corpora.
              </p>
              <p>
                <strong>3. Privacy & Zero PII Leakage:</strong> We never share your proprietary study concepts with third-party advertisers. All LLM inferences are routed through stateless free model pools with complete 14-field provenance tracking.
              </p>
              <p style={{ marginBottom: 0 }}>
                <strong>4. Data Retention:</strong> You have full rights to export or delete your generated personas, research studies, and episodic interview memories at any time.
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '16px 24px',
            borderTop: '1px solid rgba(255, 255, 255, 0.08)',
            display: 'flex',
            justifyContent: 'flex-end',
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '8px 20px',
              borderRadius: '8px',
              background: '#F6C878',
              color: '#18181B',
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
