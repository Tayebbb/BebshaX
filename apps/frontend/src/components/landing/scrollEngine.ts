/**
 * Landing scroll engine — one rAF loop, lerped scroll position exposed as
 * CSS custom properties on <html>:
 *
 *   --lp-scroll   smoothed scrollY in px (drives parallax translate3d)
 *   --lp-hero-p   smoothed 0..1 progress through the hero fold (drives fades)
 *
 * Native scrolling is never hijacked — only the VISUALS lag the real scroll
 * with inertia, which is what reads as "buttery". The loop self-suspends
 * when the value settles, so idle pages cost zero frames.
 */

let raf: number | null = null;
let current = 0;
let target = 0;
let users = 0;
let listening = false;

const EASE = 0.12;
const root = () => document.documentElement;

function frame() {
  raf = null;
  const delta = target - current;
  if (Math.abs(delta) < 0.05) {
    current = target;
  } else {
    current += delta * EASE;
    raf = requestAnimationFrame(frame);
  }
  const heroH = Math.max(1, Math.min(window.innerHeight, 1080));
  root().style.setProperty('--lp-scroll', current.toFixed(2));
  root().style.setProperty('--lp-hero-p', Math.min(1, current / heroH).toFixed(4));
}

function onScroll() {
  target = window.scrollY;
  if (raf === null) raf = requestAnimationFrame(frame);
}

export function startScrollEngine(): () => void {
  users++;
  if (!listening) {
    listening = true;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      // no smoothing — mirror instantly so parallax stays static-correct
      current = target = window.scrollY;
      frame();
    } else {
      current = target = window.scrollY;
      window.addEventListener('scroll', onScroll, { passive: true });
      frame();
    }
  }
  return () => {
    users--;
    if (users <= 0) {
      users = 0;
      listening = false;
      window.removeEventListener('scroll', onScroll);
      if (raf !== null) cancelAnimationFrame(raf);
      raf = null;
    }
  };
}
