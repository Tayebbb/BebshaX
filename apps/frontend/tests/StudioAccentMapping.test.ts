import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const css = readFileSync(resolve(root, 'src/index.css'), 'utf8');
const config = readFileSync(resolve(root, 'tailwind.config.js'), 'utf8');

describe('Tailwind teal and cyan follow the theme accent', () => {
  it.each(['teal', 'cyan'])('%s is overridden with the accent scale', (name) => {
    expect(config).toMatch(new RegExp(`${name}:\\s*accentScale\\(\\)`));
  });

  it('builds the scale from accent channel tokens so opacity modifiers keep working', () => {
    expect(config).toContain("'rgb(var(--accent-rgb) / <alpha-value>)'");
    expect(config).toContain("'rgb(var(--accent-hover-rgb) / <alpha-value>)'");
    for (const shade of ['300', '400', '500', '600']) {
      expect(config).toMatch(new RegExp(`${shade}:\\s*accent(?:Hover)?\\b`));
    }
  });

  it.each([':root', "\\[data-theme='light'\\]"])('defines both accent channels in %s', (selector) => {
    const block = new RegExp(`${selector}\\s*\\{[\\s\\S]*?\\n\\}`).exec(css)?.[0] ?? '';
    expect(block).toMatch(/--accent-rgb:\s*\d+ \d+ \d+;/);
    expect(block).toMatch(/--accent-hover-rgb:\s*\d+ \d+ \d+;/);
  });

  it('does not repaint teal or cyan text back to teal in light mode', () => {
    expect(css).not.toMatch(/\[data-theme='light'\] \.text-(?:teal|cyan)-/);
  });

  it('keeps accent channels in step with the hex accent tokens', () => {
    const hex = (value: string) => value.replace('#', '').match(/../g)!.map((pair) => Number.parseInt(pair, 16)).join(' ');
    const dark = /:root\s*\{[\s\S]*?\n\}/.exec(css)![0];
    const light = /\[data-theme='light'\]\s*\{[\s\S]*?\n\}/.exec(css)![0];
    for (const [block, name] of [[dark, 'dark'], [light, 'light']] as const) {
      const primary = /--accent-primary:\s*(#[0-9a-f]{6});/i.exec(block)![1];
      const hover = /--accent-hover:\s*(#[0-9a-f]{6});/i.exec(block)![1];
      expect(/--accent-rgb:\s*([\d ]+);/.exec(block)![1], `${name} accent`).toBe(hex(primary));
      expect(/--accent-hover-rgb:\s*([\d ]+);/.exec(block)![1], `${name} hover`).toBe(hex(hover));
    }
  });
});
