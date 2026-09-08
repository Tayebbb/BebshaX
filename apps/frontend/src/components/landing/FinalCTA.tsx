import React from 'react';
import { ArrowRight } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';

interface FinalCTAProps {
  onOpenApp?: () => void;
}

export const FinalCTA: React.FC<FinalCTAProps> = ({ onOpenApp }) => {
  const { isAuthenticated } = useAuth();
  const { navigate } = useNavigation();

  const handlePrimaryAction = () => {
    if (isAuthenticated) {
      onOpenApp?.();
      return;
    }
    navigate('/auth/signup');
  };

  return (
    <section
      style={{
        position: 'relative',
        padding: '80px 0 100px 0',
        zIndex: 1,
        background: 'var(--lp-bg)',
      }}
    >
      <div
        style={{
          maxWidth: '1240px',
          margin: '0 auto',
          padding: '0 24px',
        }}
      >
        {/* Main Banner Card (No outline / border) */}
        <div
          className="clean-card"
          style={{
            borderRadius: '24px',
            background: 'var(--lp-surface)',
            border: 'none',
            outline: 'none',
            padding: 'clamp(32px, 6vw, 56px) clamp(20px, 5vw, 48px)',
            overflow: 'hidden',
            position: 'relative',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))',
            gap: '40px',
            alignItems: 'center',
          }}
        >
          {/* Left Column: Heading + CTA */}
          <div style={{ maxWidth: '540px', zIndex: 1 }}>
            <p
              style={{
                fontSize: 'clamp(1.1rem, 2vw, 1.35rem)',
                color: 'var(--lp-text-muted)',
                marginBottom: '8px',
                fontWeight: 500,
              }}
            >
              No API keys, no data connection, no fine-tuning.
            </p>

            <h2
              style={{
                fontSize: 'clamp(2.2rem, 4vw, 3.4rem)',
                fontWeight: 800,
                color: 'var(--lp-text)',
                letterSpacing: '-0.035em',
                lineHeight: 1.1,
                marginBottom: '36px',
              }}
            >
              Describe a business. Meet its personas.
            </h2>

            <button
              onClick={handlePrimaryAction}
              style={{
                padding: '13px 28px',
                borderRadius: '9999px',
                background: 'var(--lp-contrast-bg)',
                color: 'var(--lp-contrast-fg)',
                border: 'none',
                outline: 'none',
                fontSize: '0.9rem',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                whiteSpace: 'nowrap',
                transition: 'background 0.2s ease',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--lp-contrast-bg-hover)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--lp-contrast-bg)')}
            >
              <span>{isAuthenticated ? 'Launch Console' : 'Create your account'}</span>
              <ArrowRight size={15} color="var(--lp-contrast-fg)" />
            </button>
          </div>

          {/* Right Column: Isometric Geometric Art with Emerald/Gold Backlight.
              The monolith is fixed dark artwork — deliberately constant in both
              themes, like a rendered product object on the page. */}
          <div
            style={{
              position: 'relative',
              height: '240px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {/* Glowing Emerald Backlight */}
            <div
              style={{
                position: 'absolute',
                width: '180px',
                height: '180px',
                background: 'radial-gradient(circle, rgba(16, 185, 129, 0.4) 0%, rgba(246, 200, 120, 0.2) 50%, transparent 70%)',
                filter: 'blur(40px)',
                zIndex: 0,
              }}
            />

            {/* Futuristic Layered Monolith Block Illustration */}
            <div
              style={{
                position: 'relative',
                zIndex: 1,
                width: '180px',
                height: '180px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <svg viewBox="0 0 200 200" width="180" height="180" fill="none">
                {/* Isometric Cube Node 1 */}
                <polygon
                  points="100,25 165,60 100,95 35,60"
                  fill="#181820"
                />
                <polygon
                  points="35,60 100,95 100,140 35,105"
                  fill="#0D0D12"
                />
                <polygon
                  points="100,95 165,60 165,105 100,140"
                  fill="#121218"
                />

                {/* Center Glowing Core */}
                <circle cx="100" cy="60" r="14" fill="#F6C878" filter="drop-shadow(0 0 8px #F6C878)" />
                <path d="M96 55 L104 60 L96 65" stroke="#000000" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
