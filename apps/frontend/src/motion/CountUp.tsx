import React, { useRef } from 'react';
import { gsap, useGSAP, prefersReducedMotion } from './gsap';

interface CountUpProps {
  /** Target value. Changing it tweens from the currently displayed value. */
  value: number;
  /** Formats the in-flight value for display. Defaults to rounded locale string. */
  format?: (v: number) => string;
  duration?: number;
  className?: string;
  style?: React.CSSProperties;
}

const defaultFormat = (v: number) => Math.round(v).toLocaleString();

/**
 * Animated numeric readout. Counts up from 0 on mount (and between values on
 * update) using a GSAP tween on a proxy object — only textContent changes, no
 * layout work. Renders the final value immediately under reduced motion/tests.
 */
export function CountUp({ value, format = defaultFormat, duration = 0.9, className, style }: CountUpProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const displayed = useRef(0);

  useGSAP(
    () => {
      const el = ref.current;
      if (!el) return;
      if (prefersReducedMotion()) {
        displayed.current = value;
        el.textContent = format(value);
        return;
      }
      const proxy = { v: displayed.current };
      gsap.to(proxy, {
        v: value,
        duration,
        ease: 'power2.out',
        onUpdate: () => {
          displayed.current = proxy.v;
          el.textContent = format(proxy.v);
        },
      });
    },
    { dependencies: [value] },
  );

  return (
    <span ref={ref} className={className} style={style}>
      {format(value)}
    </span>
  );
}
