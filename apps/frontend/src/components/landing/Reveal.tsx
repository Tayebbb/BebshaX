import React, { useEffect, useRef, useState } from 'react';

interface RevealProps {
  children: React.ReactNode;
  /** entrance variant — mask: clipped rise (default) · rise: translate+fade */
  variant?: 'mask' | 'rise';
  /** stagger slot, multiplied by 70ms */
  index?: number;
  as?: keyof JSX.IntrinsicElements;
  className?: string;
}

/** IntersectionObserver-driven scene entrance. Reveals once, then unobserves —
 *  zero cost after entry. */
export const Reveal: React.FC<RevealProps> = ({
  children,
  variant = 'mask',
  index = 0,
  as = 'div',
  className,
}) => {
  const ref = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (
      typeof IntersectionObserver === 'undefined' ||
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      setVisible(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          io.disconnect();
        }
      },
      // amount-of-element AND amount-of-viewport thresholds: tall sections
      // (> ~5 viewports) can never hit an element-ratio threshold, so any
      // intersection at all past a small viewport margin counts.
      { threshold: 0, rootMargin: '0px 0px -6% 0px' }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const Tag = as as React.ElementType;
  return (
    <Tag
      ref={ref}
      className={`lp-reveal lp-reveal--${variant}${visible ? ' is-in' : ''}${className ? ` ${className}` : ''}`}
      style={{ ['--lp-i' as string]: index }}
    >
      {children}
    </Tag>
  );
};
