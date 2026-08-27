/**
 * One-shot codemod: map the app's closed dark-palette hex/rgba literals to the
 * semantic CSS variables defined in src/index.css, so the light theme
 * (html[data-theme="light"]) restyles every view. Dark mode stays
 * pixel-identical because each token's dark value IS the replaced literal.
 *
 * Scope: app surfaces only (dashboard, auth page, interview). The marketing
 * landing page and the legacy white AuthModal keep their hand-tuned looks.
 *
 * Run:  node scripts/codemod-theme-tokens.mjs [--check]
 * Idempotent; --check exits 1 if any file would change.
 */
import { readdirSync, readFileSync, statSync, writeFileSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const SCOPES = [
  'src/components/dashboard',
  'src/components/auth',
  'src/components/interview',
  'src/components/common',
];
const SINGLE_FILES = ['src/App.tsx'];
const EXCLUDE = new Set(['AuthModal.tsx']); // legacy white modal, deliberate design

const walk = (dir) => {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (/\.(tsx|css)$/.test(entry) && !EXCLUDE.has(entry)) out.push(full);
  }
  return out;
};

// Order matters: longer/more-specific literals first.
const MAP = [
  // white-alpha text washes (css drift layers, labels)
  [/rgba\(255,\s*255,\s*255,\s*0\.9\d*\)/g, 'var(--text-main)'],
  [/rgba\(255,\s*255,\s*255,\s*0\.(7|8)\d*\)/g, 'var(--text-primary)'],
  [/rgba\(255,\s*255,\s*255,\s*0\.(5|6)\d*\)/g, 'var(--text-secondary)'],
  // white-alpha fills & hairlines
  [/rgba\(255,\s*255,\s*255,\s*0\.0[2-5]\d*\)/g, 'var(--fill-soft)'],
  [/rgba\(255,\s*255,\s*255,\s*0\.0[6-9]\d*\)/g, 'var(--fill-soft-2)'],
  [/rgba\(255,\s*255,\s*255,\s*0\.[12]\d*\)/g, 'var(--border-soft)'],
  // teal washes
  [/rgba\(20,\s*184,\s*166,\s*0\.0\d+\)/g, 'var(--accent-subtle)'],
  [/rgba\(20,\s*184,\s*166,\s*0\.1\d*\)/g, 'var(--accent-subtle)'],
  [/rgba\(20,\s*184,\s*166,\s*0\.2\d*\)/g, 'var(--accent-glow)'],
  [/rgba\(20,\s*184,\s*166,\s*0\.3\d*\)/g, 'var(--border-hover)'],
  // frosted glass tiers (dark ink washes that must flip to white glass)
  [/rgba\(13,\s*17,\s*17,\s*0\.(8|9)\d*\)/g, 'var(--glass-strong)'],
  [/rgba\(17,\s*22,\s*22,\s*0\.(8|9)\d*\)/g, 'var(--glass-strong)'],
  [/rgba\(19,\s*20,\s*21,\s*0\.(8|9)\d*\)/g, 'var(--glass-strong)'],
  [/rgba\(8,\s*10,\s*10,\s*0\.(8|9)\d*\)/g, 'var(--glass-strong)'],
  [/rgba\(13,\s*17,\s*17,\s*0\.(6|7)\d*\)/g, 'var(--glass-mid)'],
  [/rgba\(13,\s*17,\s*17,\s*0\.(4|5)\d*\)/g, 'var(--glass-soft)'],
  // backgrounds
  [/#080909\b/gi, 'var(--bg-pure)'],
  [/#080A0A\b/gi, 'var(--bg-pure)'],
  [/#0D1111\b/gi, 'var(--bg-secondary)'],
  [/#111616\b/gi, 'var(--bg-card)'],
  [/#161C1C\b/gi, 'var(--bg-card-hover)'],
  [/#161B1B\b/gi, 'var(--bg-card-hover)'],
  [/#141A1A\b/gi, 'var(--bg-card-hover)'],
  // borders
  [/#202727\b/gi, 'var(--border-subtle)'],
  [/#1E2626\b/gi, 'var(--border-subtle)'],
  [/#283333\b/gi, 'var(--border-medium)'],
  [/#2A3333\b/gi, 'var(--border-medium)'],
  [/#2E3A3A\b/gi, 'var(--border-medium)'],
  [/#334155\b/gi, 'var(--border-medium)'],
  // text
  [/#FFFFFF\b/gi, 'var(--text-main)'],
  [/#F4F7F7\b/gi, 'var(--text-primary)'],
  [/#D1D5DB\b/gi, 'var(--text-primary)'],
  [/#E5E7EB\b/gi, 'var(--text-primary)'],
  [/#B6C2C2\b/gi, 'var(--text-label)'],
  [/#8D9999\b/gi, 'var(--text-secondary)'],
  [/#6E7A7A\b/gi, 'var(--text-muted)'],
  [/#5F6B6B\b/gi, 'var(--text-muted)'],
  [/#535D5D\b/gi, 'var(--text-faint)'],
  [/#4B5563\b/gi, 'var(--text-faint)'],
  [/#6B7280\b/gi, 'var(--text-muted)'],
  [/#9CA3AF\b/gi, 'var(--text-muted)'],
  [/#5B6666\b/gi, 'var(--text-faint)'],
  [/#DFE8E8\b/gi, 'var(--text-primary)'],
  [/#F87171\b/gi, 'var(--status-error-text)'],
  [/#041110\b/gi, 'var(--text-on-accent)'],
  [/#fff\b/gi, 'var(--text-main)'],
  // accents that must darken for light-mode contrast
  [/#22D3EE\b/gi, 'var(--accent-cyan)'],
  [/#2DD4BF\b/gi, 'var(--accent-teal-bright)'],
  [/#5EEAD4\b/gi, 'var(--accent-teal-bright)'],
  [/#34D399\b/gi, 'var(--status-success-text)'],
  [/#10B981\b/gi, 'var(--accent-emerald)'],
  [/#FCA5A5\b/gi, 'var(--status-error-text)'],
  [/#F6C878\b/gi, 'var(--status-warn-text)'],
  // long-tail dark surfaces (pills, inputs, tracks) and slate greys
  [/#141818\b/gi, 'var(--bg-card-hover)'],
  [/#111717\b/gi, 'var(--bg-card-hover)'],
  [/#162020\b/gi, 'var(--bg-card-hover)'],
  [/#151D1D\b/gi, 'var(--bg-card-hover)'],
  [/#1E2330\b/gi, 'var(--bg-card-hover)'],
  [/#1E293B\b/gi, 'var(--bg-card-hover)'],
  [/#0F172A\b/gi, 'var(--bg-card)'],
  [/#12151C\b/gi, 'var(--bg-card)'],
  [/#0D0F14\b/gi, 'var(--bg-secondary)'],
  [/#042F2E\b/gi, 'var(--accent-subtle)'],
  [/#1A2222\b/gi, 'var(--border-subtle)'],
  [/#1F2C2C\b/gi, 'var(--border-medium)'],
  [/#223030\b/gi, 'var(--border-medium)'],
  [/#233333\b/gi, 'var(--border-medium)'],
  [/#202E2E\b/gi, 'var(--border-medium)'],
  [/#2A3130\b/gi, 'var(--border-medium)'],
  [/#2A3434\b/gi, 'var(--border-medium)'],
  [/#94A3B8\b/gi, 'var(--text-secondary)'],
  [/#9299A5\b/gi, 'var(--text-secondary)'],
  [/#A0AFAF\b/gi, 'var(--text-secondary)'],
  [/#64748B\b/gi, 'var(--text-muted)'],
  [/#7F9191\b/gi, 'var(--text-muted)'],
  [/#718282\b/gi, 'var(--text-muted)'],
  [/#CBD5E1\b/gi, 'var(--text-primary)'],
  [/#C8D2D2\b/gi, 'var(--text-primary)'],
  [/#C8D4D4\b/gi, 'var(--text-primary)'],
  [/#F1F5F9\b/gi, 'var(--text-primary)'],
  [/#F8FAFC\b/gi, 'var(--text-primary)'],
  [/#F5F7FA\b/gi, 'var(--text-primary)'],
  [/#E2E8F0\b/gi, 'var(--text-primary)'],
  // dark text on teal CTAs must NOT flip with the page background token
  [/color:\s*'var\(--bg-pure\)'/g, "color: 'var(--text-on-accent)'"],
];

const checkOnly = process.argv.includes('--check');
const files = [
  ...SCOPES.flatMap((s) => walk(path.join(root, s))),
  ...SINGLE_FILES.map((f) => path.join(root, f)),
];

let changed = 0;
for (const file of files) {
  const before = readFileSync(file, 'utf8');
  let after = before;
  for (const [re, replacement] of MAP) {
    after = after.replace(re, replacement);
  }
  if (after !== before) {
    changed += 1;
    const rel = path.relative(root, file);
    if (!checkOnly) {
      writeFileSync(file, after, 'utf8');
      console.log(`tokenized ${rel}`);
    } else {
      console.log(`would change ${rel}`);
    }
  }
}

console.log(`${checkOnly ? 'files needing tokenization' : 'files tokenized'}: ${changed}`);
if (checkOnly && changed > 0) process.exit(1);
