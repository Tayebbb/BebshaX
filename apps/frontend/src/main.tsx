import React from 'react';
import ReactDOM from 'react-dom/client';
// Self-hosted fonts (@fontsource) — latin subset only: the product ships no
// i18n layer, and the full packages pull cyrillic/greek/vietnamese @font-face
// blocks into the render-blocking stylesheet. Space Grotesk and Unbounded are
// dashboard-only and load with the dashboard chunk.
import '@fontsource/plus-jakarta-sans/latin-400.css';
import '@fontsource/plus-jakarta-sans/latin-500.css';
import '@fontsource/plus-jakarta-sans/latin-600.css';
import '@fontsource/plus-jakarta-sans/latin-700.css';
import '@fontsource/plus-jakarta-sans/latin-800.css';
import '@fontsource/plus-jakarta-sans/latin-400-italic.css';
import '@fontsource/plus-jakarta-sans/latin-600-italic.css';
import '@fontsource/jetbrains-mono/latin-400.css';
import '@fontsource/jetbrains-mono/latin-500.css';
import '@fontsource/jetbrains-mono/latin-600.css';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
