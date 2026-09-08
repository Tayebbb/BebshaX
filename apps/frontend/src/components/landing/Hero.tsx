import React, { useEffect, useLayoutEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';
import { startScrollEngine } from './scrollEngine';

interface HeroProps {
  onOpenApp?: () => void;
}

/**
 * Counts up when the element enters the viewport; respects reduced motion.
 * The tween writes textContent directly rather than setState: three counters
 * at 60fps for 1.1s would otherwise push ~200 React commits through the hero
 * during the exact window the rest of the page is still hydrating.
 */
const CountUp: React.FC<{ to: number }> = ({ to }) => {
  const ref = useRef<HTMLSpanElement | null>(null);

  // Seeding the text runs before paint: a plain useEffect fires after it, so
  // the three above-the-fold stat numbers would paint zero-width and shift on
  // the next frame — CLS on the exact page this is optimizing.
  useLayoutEffect(() => {
    const el = ref.current;
    // The span is rendered childless so React provably owns nothing inside it;
    // the tween below writes textContent directly and a reconcile can never
    // reset it out from under the animation.
    if (el) el.textContent = '0';
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (
      typeof IntersectionObserver === 'undefined' ||
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      el.textContent = String(to);
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
          el.textContent = String(Math.round(to * eased));
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

  return <span ref={ref} />;
};

const STATS: Array<{ value: number; label: React.ReactNode }> = [
  {
    value: 5,
    label: (
      <>
        Guided steps from a rough idea to a <strong style={{ color: 'var(--lp-text)', fontWeight: 600 }}>decision report you can act on</strong>
      </>
    ),
  },
  {
    value: 3,
    label: (
      <>
        Labels on every persona attribute: <strong style={{ color: 'var(--lp-text)', fontWeight: 600 }}>evidence, inference, or assumption</strong>
      </>
    ),
  },
  {
    value: 0,
    label: (
      <>
        API keys required. Works on <strong style={{ color: 'var(--lp-text)', fontWeight: 600 }}>free providers and a local model</strong>
      </>
    ),
  },
];

export const Hero: React.FC<HeroProps> = ({ onOpenApp }) => {
  const { isAuthenticated } = useAuth();
  const { navigate } = useNavigation();
  const ctaRef = useRef<HTMLButtonElement | null>(null);
  const sectionRef = useRef<HTMLElement | null>(null);

  useEffect(() => startScrollEngine(sectionRef.current), []);

  const handlePrimaryAction = () => {
    if (isAuthenticated) {
      onOpenApp?.();
      return;
    }
    navigate('/auth/signup');
  };

  // magnetic pull: the button leans toward a nearby cursor and settles back.
  // The box is measured once per hover — measuring per mousemove forces a
  // synchronous layout on every pointer event.
  const ctaBox = useRef<{ cx: number; cy: number } | null>(null);
  const measureCta = () => {
    const el = ctaRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    ctaBox.current = { cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
  };
  const onCtaMove = (e: React.MouseEvent<HTMLButtonElement>) => {
    const el = ctaRef.current;
    if (!el || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (!ctaBox.current) measureCta();
    const box = ctaBox.current;
    if (!box) return;
    const dx = e.clientX - box.cx;
    const dy = e.clientY - box.cy;
    el.style.setProperty('--lp-mx', `${dx * 0.14}px`);
    el.style.setProperty('--lp-my', `${dy * 0.22}px`);
  };
  const onCtaLeave = () => {
    const el = ctaRef.current;
    ctaBox.current = null;
    if (!el) return;
    el.style.setProperty('--lp-mx', '0px');
    el.style.setProperty('--lp-my', '0px');
  };

  return (
    <section
      ref={sectionRef}
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
      {/* Depth plane 1 — category label (fastest parallax, first to dim) */}
      <div className="lp-hero-layer lp-hero-layer--badges" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '14px' }}>
        <div
          className="lp-soft"
          style={{ ['--lp-i' as string]: 0, display: 'inline-flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem', color: 'var(--lp-text-muted)', letterSpacing: '0.04em' }}
        >
          <span style={{ color: 'var(--lp-gold)', opacity: 0.6 }}>[</span>
          <span><strong style={{ color: 'var(--lp-text)', fontWeight: 700 }}>Synthetic Persona Research</strong></span>
          <span style={{ color: 'var(--lp-gold)', opacity: 0.6 }}>]</span>
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
          Pressure-test your idea against realistic customers in minutes, and see exactly where every answer came from.
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
              {/* counting from 0 to 0 reads as a broken animation next to its neighbours */}
              {s.value === 0 ? <span>0</span> : <CountUp to={s.value} />}
            </div>
            <div style={{ fontSize: '0.82rem', color: 'var(--lp-text-muted)', lineHeight: '1.4' }}>{s.label}</div>
          </div>
        ))}
      </div>
    </section>
  );
};
