import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';
import { startScrollEngine } from './scrollEngine';

interface HeroProps {
  onOpenApp?: () => void;
}

/** Counts up when the element enters the viewport; respects reduced motion. */
const CountUp: React.FC<{ to: number }> = ({ to }) => {
  const ref = useRef<HTMLSpanElement | null>(null);
  const [value, setValue] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (
      typeof IntersectionObserver === 'undefined' ||
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      setValue(to);
      return;
    }
    let raf = 0;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        io.disconnect();
        const t0 = performance.now();
        const dur = 1100;
        const tick = (t: number) => {
          const p = Math.min(1, (t - t0) / dur);
          const eased = 1 - Math.pow(1 - p, 4); // strong decel — numbers land softly
          setValue(Math.round(to * eased));
          if (p < 1) raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
      },
      { threshold: 0.6 }
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [to]);

  return <span ref={ref}>{value}</span>;
};

const STATS: Array<{ value: number; label: React.ReactNode }> = [
  {
    value: 16,
    label: (
      <>
        Fixed task types, routed across <strong style={{ color: 'var(--lp-text)', fontWeight: 600 }}>7 routing pools</strong>
      </>
    ),
  },
  {
    value: 14,
    label: (
      <>
        Failure kinds, each with an <strong style={{ color: 'var(--lp-text)', fontWeight: 600 }}>explicit routing policy</strong>
      </>
    ),
  },
  {
    value: 0,
    label: (
      <>
        API keys required — <strong style={{ color: 'var(--lp-text)', fontWeight: 600 }}>keyless providers plus local Ollama</strong>
      </>
    ),
  },
];

export const Hero: React.FC<HeroProps> = ({ onOpenApp }) => {
  const { isAuthenticated } = useAuth();
  const { navigate } = useNavigation();
  const ctaRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => startScrollEngine(), []);

  const handlePrimaryAction = () => {
    if (isAuthenticated) {
      onOpenApp?.();
      return;
    }
    navigate('/auth/signup');
  };

  // magnetic pull: the button leans toward a nearby cursor and settles back
  const onCtaMove = (e: React.MouseEvent<HTMLButtonElement>) => {
    const el = ctaRef.current;
    if (!el || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const r = el.getBoundingClientRect();
    const dx = e.clientX - (r.left + r.width / 2);
    const dy = e.clientY - (r.top + r.height / 2);
    el.style.setProperty('--lp-mx', `${dx * 0.14}px`);
    el.style.setProperty('--lp-my', `${dy * 0.22}px`);
  };
  const onCtaLeave = () => {
    const el = ctaRef.current;
    if (!el) return;
    el.style.setProperty('--lp-mx', '0px');
    el.style.setProperty('--lp-my', '0px');
  };

  return (
    <section
      style={{
        position: 'relative',
        height: '100vh',
        minHeight: '760px',
        maxHeight: '1080px',
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        alignItems: 'center',
        textAlign: 'center',
        paddingTop: '110px',
        paddingBottom: '56px',
        paddingLeft: '24px',
        paddingRight: '24px',
        boxSizing: 'border-box',
        overflow: 'hidden',
        zIndex: 1,
      }}
    >
      {/* Depth plane 1 — badges (fastest parallax, first to dim) */}
      <div className="lp-hero-layer lp-hero-layer--badges" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '14px' }}>
        <div
          className="lp-soft"
          style={{ ['--lp-i' as string]: 0, display: 'inline-flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem', color: 'var(--lp-text-muted)', letterSpacing: '0.04em' }}
        >
          <span style={{ color: 'var(--lp-gold)', opacity: 0.6 }}>[</span>
          <span><strong style={{ color: 'var(--lp-text)', fontWeight: 700 }}>Synthetic Persona Research</strong></span>
          <span style={{ color: 'var(--lp-gold)', opacity: 0.6 }}>]</span>
        </div>

        <div
          className="lp-soft"
          style={{ ['--lp-i' as string]: 1, display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '6px 20px', borderRadius: '9999px', background: 'rgba(var(--lp-fill-rgb), 0.04)', fontSize: '0.78rem', color: 'var(--lp-text-dim)' }}
        >
          <span>Runs on free provider tiers — </span>
          <span style={{ fontStyle: 'italic', color: 'var(--lp-gold)' }}>zero API keys required to start</span>
        </div>
      </div>

      {/* Depth plane 2 — the opening shot */}
      <div className="lp-hero-layer lp-hero-layer--title" style={{ maxWidth: '1020px', margin: '0 auto', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '20px 0' }}>
        <h1 className="lp-hero-title">
          <span className="lp-line" style={{ ['--lp-i' as string]: 0 }}>
            <span>Evidence in.</span>
          </span>
          <span className="lp-line" style={{ ['--lp-i' as string]: 1 }}>
            <span style={{ fontStyle: 'italic', color: 'var(--lp-gold)' }}>Personas out.</span>
          </span>
          <span className="lp-line" style={{ ['--lp-i' as string]: 2 }}>
            <span>Then interview them.</span>
          </span>
        </h1>

        <p
          className="lp-soft"
          style={{ ['--lp-i' as string]: 4, fontSize: 'clamp(0.95rem, 1.5vw, 1.15rem)', color: 'var(--lp-text-dim)', maxWidth: '680px', lineHeight: 1.6, marginBottom: '38px', fontWeight: 400 }}
        >
          Describe your business. BebshaX generates personas whose every attribute is labelled OBSERVED, INFERRED or SYNTHETIC against public research datasets — then you interview them in multi-turn conversations routed across free LLM providers, with a local model as the final fallback.
        </p>

        <button
          ref={ctaRef}
          className="lp-cta lp-soft"
          style={{ ['--lp-i' as string]: 5 }}
          onClick={handlePrimaryAction}
          onMouseMove={onCtaMove}
          onMouseLeave={onCtaLeave}
        >
          {isAuthenticated ? 'Launch Console' : 'Generate your first persona'}
        </button>
      </div>

      {/* Depth plane 3 — grounding stats (slowest parallax, anchored) */}
      <div
        className="lp-hero-layer lp-hero-layer--stats"
        style={{ width: '100%', maxWidth: '1080px', margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '24px', alignItems: 'flex-end' }}
      >
        {STATS.map((s, i) => (
          <div key={i} className="lp-soft" style={{ ['--lp-i' as string]: 6 + i }}>
            <div style={{ fontSize: 'clamp(2rem, 3.5vw, 2.8rem)', fontWeight: 800, color: 'var(--lp-gold)', letterSpacing: '-0.03em', marginBottom: '6px' }}>
              <CountUp to={s.value} />
            </div>
            <div style={{ fontSize: '0.82rem', color: 'var(--lp-text-muted)', lineHeight: '1.4' }}>{s.label}</div>
          </div>
        ))}
      </div>

      <div className="lp-scroll-cue" aria-hidden="true" />
    </section>
  );
};
