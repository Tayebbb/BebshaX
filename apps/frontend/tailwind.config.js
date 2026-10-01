/** Tailwind is used by a subset of console components (modals, segmentation,
 * interviews, behavioral views) that were authored with utility classes.
 * Preflight is OFF: the app's own base/reset lives in src/index.css and the
 * rest of the UI is inline-styled — Tailwind must never restyle it globally.
 */
const accent = 'rgb(var(--accent-rgb) / <alpha-value>)';
const accentHover = 'rgb(var(--accent-hover-rgb) / <alpha-value>)';
function accentScale() {
  return { 300: accentHover, 400: accent, 500: accent, 600: accent };
}

/** @type {import('tailwindcss').Config} */
export default {
  content: { relative: true, files: ['./index.html', './src/**/*.{ts,tsx}'] },
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      // Legacy teal/cyan utilities follow the theme accent (blue) instead of
      // hardcoded teal; channels are defined in src/index.css per theme.
      colors: {
        teal: accentScale(),
        cyan: accentScale(),
      },
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
