import React from 'react';

export const Footer: React.FC = () => {
  const columns = [
    {
      title: 'PRODUCT',
      links: [
        { label: 'Home', href: '#' },
        { label: 'The Console', href: '#product' },
        { label: 'How It Works', href: '#how-it-works' },
        { label: 'Capabilities', href: '#features' },
      ],
    },
    {
      title: 'ROUTING',
      links: [
        { label: 'Task to Pool Map', href: '#demo' },
        { label: 'Failure Taxonomy', href: '#intelligence' },
        { label: 'Local Fallback', href: '#features' },
        { label: 'Policy Layer', href: '#comparison' },
      ],
    },
    {
      title: 'WHO IT IS FOR',
      links: [
        { label: 'Founders', href: '#solutions' },
        { label: 'Product & UX Research', href: '#solutions' },
        { label: 'Researchers & Students', href: '#solutions' },
        { label: 'Teams With No API Budget', href: '#solutions' },
      ],
    },
    {
      title: 'GROUNDING',
      links: [
        { label: 'Provenance Classes', href: '#product' },
        { label: 'Consistency Rules', href: '#problem' },
        { label: 'Dataset Sources', href: '#intelligence' },
      ],
    },
    {
      title: 'ANSWERS',
      links: [
        { label: 'FAQ', href: '#faq' },
      ],
    },
  ];

  return (
    <footer
      style={{
        background: 'var(--lp-bg)',
        padding: '90px 0 60px 0',
        position: 'relative',
        zIndex: 1,
        overflow: 'hidden',
        border: 'none',
        outline: 'none',
      }}
    >
      <div
        style={{
          maxWidth: '1280px',
          margin: '0 auto',
          padding: '0 clamp(16px, 4vw, 32px)',
        }}
      >
        {/* Brand Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '20px',
            marginBottom: '48px',
            paddingBottom: '28px',
            borderBottom: '1px solid var(--lp-line-faint)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <img
              src="/logobebshax.jpeg"
              alt="BebshaX Logo"
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '9px',
                objectFit: 'contain',
                boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
              }}
            />
            <img
              src="/Bebshax.png"
              alt="BebshaX"
              className="bx-brand-wordmark"
              style={{
                height: '28px',
                objectFit: 'contain',
              }}
            />
          </div>
          <p style={{ margin: 0, fontSize: '0.84rem', color: 'var(--lp-text-muted)', maxWidth: '460px' }}>
            Evidence-grounded synthetic personas & routed multi-model research intelligence.
          </p>
        </div>

        {/* Multi-Column Sitemap Grid Matching Image */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 130px), 1fr))',
            gap: '36px 20px',
            marginBottom: '80px',
          }}
        >
          {columns.map((col, idx) => (
            <div key={idx}>
              <div
                style={{
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  color: 'var(--lp-text)',
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  marginBottom: '18px',
                }}
              >
                {col.title}
              </div>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {col.links.map((link, i) => (
                  <li key={i}>
                    <a
                      href={link.href}
                      style={{
                        fontSize: '0.8rem',
                        color: 'var(--lp-text-faint)',
                        textDecoration: 'none',
                        transition: 'color 0.2s ease',
                        lineHeight: 1.4,
                        display: 'inline-block',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--lp-text)')}
                      onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--lp-text-faint)')}
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Large Translucent BebshaX Brand Watermark */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 'clamp(12px, 3vw, 24px)',
            userSelect: 'none',
            pointerEvents: 'none',
            padding: '24px 0 12px 0',
            opacity: 0.12,
          }}
        >
          <img
            src="/logobebshax.jpeg"
            alt=""
            style={{
              width: 'clamp(44px, 7vw, 76px)',
              height: 'clamp(44px, 7vw, 76px)',
              borderRadius: 'clamp(10px, 1.8vw, 16px)',
              objectFit: 'contain',
            }}
          />
          <img
            src="/Bebshax.png"
            alt="BebshaX"
            className="bx-brand-wordmark"
            style={{
              height: 'clamp(36px, 6vw, 68px)',
              maxWidth: '80%',
              objectFit: 'contain',
            }}
          />
        </div>

        {/* Bottom Micro Row */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '12px',
            marginTop: '30px',
            paddingTop: '20px',
            borderTop: '1px solid var(--lp-line-faint)',
            fontSize: '0.75rem',
            color: 'var(--lp-text-ghost)',
          }}
        >
          <div>© {new Date().getFullYear()} BebshaX. Synthetic personas with every attribute labelled by how it is known, interviewed over routed free LLM tiers.</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--lp-green)' }} />
            <span style={{ color: 'var(--lp-text-faint)' }}>Local model as final fallback</span>
          </div>
        </div>
      </div>
    </footer>
  );
};
