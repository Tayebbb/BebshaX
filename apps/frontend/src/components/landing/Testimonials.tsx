import React from 'react';
import { Star, CheckCircle2 } from 'lucide-react';

export const Testimonials: React.FC = () => {
  const reviews = [
    {
      quote:
        'BebshaX replaced four disconnected reporting dashboards and three weekly sync meetings. We caught a major enterprise churn spike before it cost us six figures.',
      author: 'Marcus Vance',
      role: 'Chief Operating Officer',
      company: 'LogixFlow Global',
      metric: 'Saved $180k in churn ARR',
      stars: 5,
    },
    {
      quote:
        'The ability to test what-if price simulations against verified event rows gave our executive committee complete conviction to launch our new subscription tiers.',
      author: 'Evelyn Reed',
      role: 'VP Strategy & Growth',
      company: 'FinTrack Systems',
      metric: '+34% net revenue expansion',
      stars: 5,
    },
    {
      quote:
        'Finally an intelligence tool that doesn’t just output colorful charts and leave you hanging. The automated playbooks are immediately actionable for my team.',
      author: 'Tariq Al-Mansoor',
      role: 'Head of Product Operations',
      company: 'Kinetix Media',
      metric: '4.2× faster decision velocity',
      stars: 5,
    },
  ];

  return (
    <section
      id="testimonials"
      style={{
        position: 'relative',
        padding: '100px 0',
        zIndex: 1,
        background: '#000000',
      }}
    >
      <div
        style={{
          maxWidth: '1240px',
          margin: '0 auto',
          padding: '0 24px',
        }}
      >
        {/* Section Header */}
        <div style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 64px auto' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              borderRadius: '9999px',
              background: 'rgba(255, 255, 255, 0.05)',
              border: 'none',
              outline: 'none',
              color: '#FFFFFF',
              fontSize: '0.75rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: '16px',
            }}
          >
            Customer Validation
          </div>

          <h2
            style={{
              fontSize: 'clamp(2rem, 3.8vw, 3rem)',
              fontWeight: 800,
              letterSpacing: '-0.03em',
              marginBottom: '16px',
              color: '#FFFFFF',
            }}
          >
            Loved by operations and{' '}
            <span className="text-gradient-blue">
              growth leaders.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            Discover how leading teams turn complex telemetry into decisive revenue and operational gains.
          </p>
        </div>

        {/* Testimonials Grid (No outlines) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '20px',
          }}
        >
          {reviews.map((rev, i) => (
            <div
              key={i}
              className="clean-card"
              style={{
                padding: '32px 28px',
                borderRadius: '18px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                background: '#09090C',
                border: 'none',
                outline: 'none',
              }}
            >
              <div>
                {/* 5-Star Rating */}
                <div style={{ display: 'flex', gap: '3px', marginBottom: '18px' }}>
                  {[...Array(rev.stars)].map((_, s) => (
                    <Star key={s} size={14} fill="#F6C878" color="#F6C878" />
                  ))}
                </div>

                <p
                  style={{
                    fontSize: '0.92rem',
                    color: '#FFFFFF',
                    lineHeight: '1.6',
                    marginBottom: '24px',
                    fontStyle: 'italic',
                  }}
                >
                  "{rev.quote}"
                </p>
              </div>

              <div>
                {/* Metric Achievement Badge (No outline) */}
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '4px 10px',
                    borderRadius: '9999px',
                    background: 'rgba(246, 200, 120, 0.1)',
                    border: 'none',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    color: '#F6C878',
                    marginBottom: '18px',
                  }}
                >
                  <CheckCircle2 size={12} color="#F6C878" />
                  <span>{rev.metric}</span>
                </div>

                {/* Author Info */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div
                    style={{
                      width: '36px',
                      height: '36px',
                      borderRadius: '50%',
                      background: '#FFFFFF',
                      color: '#000000',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontWeight: 800,
                      fontSize: '0.85rem',
                      border: 'none',
                    }}
                  >
                    {rev.author.charAt(0)}
                  </div>
                  <div>
                    <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#FFFFFF' }}>
                      {rev.author}
                    </div>
                    <div style={{ fontSize: '0.78rem', color: '#71717A' }}>
                      {rev.role} • {rev.company}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
