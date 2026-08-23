import '@testing-library/jest-dom';

// Polyfill scrollTo and scrollIntoView for jsdom environment
if (typeof window !== 'undefined') {
  window.scrollTo = () => {};
}
if (typeof Element !== 'undefined' && Element.prototype) {
  Element.prototype.scrollIntoView = () => {};
}
