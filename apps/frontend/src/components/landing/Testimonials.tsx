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
            className="glass-panel"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              borderRadius: '9999px',
              background: 'rgba(37, 99, 235, 0.08)',
              border: '1px solid rgba(37, 99, 235, 0.2)',
              color: '#2563EB',
              fontSize: '0.78rem',
              fontWeight: 800,
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
              color: '#0F172A',
            }}
          >
            Loved by operations and{' '}
            <span className="text-gradient-blue">
              growth leaders.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#475569', lineHeight: '1.6' }}>
            Discover how leading teams turn complex telemetry into decisive revenue and operational gains.
          </p>
        </div>

        {/* Testimonials Grid in Translucent Glass */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '24px',
          }}
        >
          {reviews.map((rev, i) => (
            <div
              key={i}
              className="glass-card"
              style={{
                padding: '36px 30px',
                borderRadius: '24px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                background: 'rgba(255, 255, 255, 0.68)',
                backdropFilter: 'blur(20px)',
                WebkitBackdropFilter: 'blur(20px)',
                border: '1px solid rgba(255, 255, 255, 0.85)',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <div>
                {/* 5-Star Rating */}
                <div style={{ display: 'flex', gap: '4px', marginBottom: '20px' }}>
                  {[...Array(rev.stars)].map((_, s) => (
                    <Star key={s} size={16} fill="#2563EB" color="#2563EB" />
                  ))}
                </div>

                <p
                  style={{
                    fontSize: '0.98rem',
                    color: '#0F172A',
                    lineHeight: '1.65',
                    marginBottom: '24px',
                    fontStyle: 'italic',
                  }}
                >
                  "{rev.quote}"
                </p>
              </div>

              <div>
                {/* Metric Achievement Badge */}
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '6px 12px',
                    borderRadius: '8px',
                    background: 'rgba(37, 99, 235, 0.08)',
                    border: '1px solid rgba(37, 99, 235, 0.2)',
                    fontSize: '0.78rem',
                    fontWeight: 700,
                    color: '#2563EB',
                    marginBottom: '20px',
                  }}
                >
                  <CheckCircle2 size={13} color="#2563EB" />
                  <span>{rev.metric}</span>
                </div>

                {/* Author Info */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div
                    style={{
                      width: '40px',
                      height: '40px',
                      borderRadius: '50%',
                      background: 'linear-gradient(135deg, #2563EB 0%, #3B82F6 100%)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#FFFFFF',
                      fontWeight: 800,
                      fontSize: '0.9rem',
                    }}
                  >
                    {rev.author.charAt(0)}
                  </div>
                  <div>
                    <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0F172A' }}>
                      {rev.author}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#64748B' }}>
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
