import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// Measured 2026-10-01 on a fresh production build: the `ui` barrel re-exported
// an unused prompt box, so the two routes importing `Button` from it pulled a
// 170 KB framer-motion chunk (and a global `*:focus-visible` style injected at
// import time); a hand-made lucide group was modulepreloaded on the landing
// page for every dashboard route's icons (32 KB).

// Same cwd-relative convention as ExhibitionInterviewLifecycle.test.tsx.
const read = (path: string) => readFileSync(path, 'utf8');

describe('Bundle hygiene', () => {
  it('keeps framer-motion and the unused prompt box out of the ui barrel', () => {
    const barrel = read('src/components/ui/index.ts');
    expect(barrel).not.toMatch(/ai-prompt-box/);
    expect(barrel).not.toMatch(/framer-motion/);
  });

  it('does not force every route\'s icons into one landing-preloaded chunk', () => {
    const config = read('vite.config.ts');
    expect(config).not.toMatch(/lucide-react/);
    expect(config).toMatch(/vendor-react/);
  });
});
