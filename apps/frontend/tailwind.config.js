/** Tailwind is used by a subset of console components (modals, segmentation,
 * interviews, behavioral views) that were authored with utility classes.
 * Preflight is OFF: the app's own base/reset lives in src/index.css and the
 * rest of the UI is inline-styled — Tailwind must never restyle it globally.
 */
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.25s ease-out both',
      },
    },
  },
  plugins: [],
};
