import '@testing-library/jest-dom/vitest';

// Polyfill scrollTo and scrollIntoView for jsdom environment
if (typeof window !== 'undefined') {
  window.scrollTo = () => {};
  // jsdom lacks matchMedia; components query prefers-reduced-motion.
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;
  }
}
if (typeof Element !== 'undefined' && Element.prototype) {
  Element.prototype.scrollIntoView = () => {};
}
