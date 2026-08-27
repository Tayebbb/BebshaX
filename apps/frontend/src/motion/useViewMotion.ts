import { useRef } from 'react';
import type { RefObject } from 'react';
import { gsap, useGSAP, prefersReducedMotion } from './gsap';

/**
 * Choreographed view entrance: staggers the direct children of the container
 * (opacity + translateY only) whenever `deps` change. Total stagger time is
 * capped so long views never feel slow. Transforms are cleared afterwards so
 * sticky/fixed descendants keep working.
 *
 * Attach the returned ref to the view container. Safe to attach to several
 * conditionally-rendered containers when only one mounts at a time.
 */
export function useViewMotion<T extends HTMLElement = HTMLDivElement>(deps: unknown[]): RefObject<T> {
  const ref = useRef<T>(null);

  useGSAP(
    () => {
      const el = ref.current;
      if (!el || prefersReducedMotion()) return;
      const children = Array.from(el.children).filter((c) => c instanceof HTMLElement);
      if (children.length === 0) return;
      gsap.fromTo(
        children,
        { autoAlpha: 0, y: 16 },
        {
          autoAlpha: 1,
          y: 0,
          duration: 0.55,
          ease: 'power3.out',
          stagger: Math.min(0.06, 0.36 / children.length),
          clearProps: 'transform,opacity,visibility',
        },
      );
    },
    { dependencies: deps },
  );

  return ref;
}
