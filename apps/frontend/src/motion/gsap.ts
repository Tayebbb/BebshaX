/**
 * Central GSAP module — the single import point for motion code.
 *
 * All GSAP usage in the app goes through this module so easing/duration
 * defaults, plugin registration, and reduced-motion handling stay coherent.
 */
import { gsap } from 'gsap';
import { useGSAP } from '@gsap/react';

gsap.registerPlugin(useGSAP);

// House motion character: calm, controlled, physically plausible.
gsap.defaults({ ease: 'power3.out', duration: 0.6, overwrite: 'auto' });

/** True when the user asked the OS to minimise motion, or when running under vitest. */
export function prefersReducedMotion(): boolean {
  if (import.meta.env.MODE === 'test') return true;
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

export { gsap, useGSAP };
