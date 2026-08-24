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
        background: '#080909',
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
          padding: '0 32px',
        }}
      >
        {/* Multi-Column Sitemap Grid Matching Image */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
            gap: '36px 20px',
            marginBottom: '100px',
          }}
        >
          {columns.map((col, idx) => (
            <div key={idx}>
              <div
                style={{
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  color: '#FFFFFF',
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
                        color: '#71717A',
                        textDecoration: 'none',
                        transition: 'color 0.2s ease',
                        lineHeight: 1.4,
                        display: 'inline-block',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.color = '#FFFFFF')}
                      onMouseLeave={(e) => (e.currentTarget.style.color = '#71717A')}
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Large Fancy Translucent BebshaX Logo Watermark Matching Image */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '24px',
            userSelect: 'none',
            pointerEvents: 'none',
            paddingTop: '20px',
          }}
        >
          {/* Subtle Geometric Wireframe Emblem */}
          <div
            style={{
              opacity: 0.12,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <svg width="100" height="100" viewBox="0 0 100 100" fill="none" stroke="#FFFFFF" strokeWidth="2.5">
              <polygon points="50,15 85,80 15,80" fill="none" />
              <line x1="50" y1="15" x2="50" y2="80" />
              <line x1="15" y1="80" x2="85" y2="80" />
              <circle cx="50" cy="15" r="4" fill="#FFFFFF" />
              <circle cx="85" cy="80" r="4" fill="#FFFFFF" />
              <circle cx="15" cy="80" r="4" fill="#FFFFFF" />
              <circle cx="50" cy="55" r="4" fill="#FFFFFF" />
            </svg>
          </div>

          {/* Big Stylized Wordmark */}
          <div
            style={{
              fontSize: 'clamp(3.8rem, 11vw, 9.5rem)',
              fontWeight: 800,
              letterSpacing: '-0.04em',
              color: 'rgba(255, 255, 255, 0.07)',
              lineHeight: 1,
              fontFamily: 'var(--font-sans)',
            }}
          >
            Bebsha<span style={{ color: 'rgba(246, 200, 120, 0.12)' }}>X</span>
          </div>
        </div>

        {/* Bottom Micro Row */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginTop: '30px',
            paddingTop: '20px',
            borderTop: '1px solid rgba(255, 255, 255, 0.04)',
            fontSize: '0.75rem',
            color: '#52525B',
          }}
        >
          <div>© {new Date().getFullYear()} BebshaX. Evidence-grounded synthetic personas, interviewed over routed free LLM tiers.</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#10B981' }} />
            <span style={{ color: '#71717A' }}>Local model as final fallback</span>
          </div>
        </div>
      </div>
    </footer>
  );
};
