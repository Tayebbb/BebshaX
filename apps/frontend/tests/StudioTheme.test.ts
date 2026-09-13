import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import postcss, { type Declaration } from 'postcss';
import { createElement } from 'react';
import { render, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RequestIdTag } from '../src/components/common/RequestIdTag';

type Theme = 'dark' | 'light';
type Tokens = Record<string, string>;
type Color = readonly [red: number, green: number, blue: number, alpha: number];

const stylesheet = postcss.parse(readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../src/index.css'),
  'utf8',
));
const landingStylesheet = postcss.parse(readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../src/components/landing/studio.css'),
  'utf8',
));
const uiStylesheet = postcss.parse(readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../src/components/ui/ui.css'),
  'utf8',
));
const newStudyStylesheet = postcss.parse(readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../src/components/dashboard/views/newstudy.css'),
  'utf8',
));
const studiesStylesheet = postcss.parse(readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../src/components/dashboard/views/studies.css'),
  'utf8',
));
const textRoles = ['--text-primary', '--text-secondary', '--text-muted', '--text-faint', '--text-label'];
const surfaceRoles = ['--bg-primary', '--bg-secondary', '--bg-card', '--bg-card-hover'];
const accentRoles = ['--accent-primary', '--accent-hover', '--accent-teal', '--accent-teal-bright', '--accent-cyan'];

function readTokens(theme: Theme, source = stylesheet): Tokens {
  const tokens: Tokens = {};
  source.walkRules((rule) => {
    if (rule.parent?.type !== 'root') return;
    const applies = rule.selectors.some((selector) => selector === ':root'
      || (theme === 'light' && /^\[data-theme=(?:'light'|"light"|light)\]$/.test(selector)));
    if (applies) {
      rule.walkDecls(/^--/, (declaration) => {
        tokens[declaration.prop] = declaration.value;
      });
    }
  });
  return tokens;
}

function resolveValue(value: string, tokens: Tokens, visited: string[] = []): string {
  return value.replace(/var\(\s*(--[\w-]+)\s*\)/g, (_reference: string, token: string) => {
    if (visited.includes(token)) throw new Error(`Circular token reference: ${token}`);
    if (tokens[token] === undefined) throw new Error(`Missing token: ${token}`);
    return resolveValue(tokens[token], tokens, [...visited, token]);
  });
}

function parseColor(value: string): Color {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'transparent') return [0, 0, 0, 0];
  const hex = /^#([\da-f]{3,4}|[\da-f]{6}|[\da-f]{8})$/.exec(normalized);
  if (hex) {
    const digits = hex[1].length <= 4
      ? [...hex[1]].map((digit) => digit.repeat(2)).join('')
      : hex[1];
    return [
      Number.parseInt(digits.slice(0, 2), 16),
      Number.parseInt(digits.slice(2, 4), 16),
      Number.parseInt(digits.slice(4, 6), 16),
      digits.length === 8 ? Number.parseInt(digits.slice(6, 8), 16) / 255 : 1,
    ];
  }
  const rgb = /^rgba?\(([^)]+)\)$/.exec(normalized);
  if (rgb) {
    const parts = postcss.list.comma(rgb[1]);
    const channels = parts.map(Number);
    const alpha = channels[3] ?? 1;
    if ([3, 4].includes(parts.length) && parts.every((part) => part.trim() !== '')
      && channels.every(Number.isFinite) && channels.slice(0, 3).every((channel) => channel >= 0 && channel <= 255)
      && alpha >= 0 && alpha <= 1) {
      return [channels[0], channels[1], channels[2], alpha];
    }
  }
  throw new Error(`Unsupported color: ${value}`);
}

function composite(foreground: Color, background: Color): Color {
  const alpha = foreground[3] + background[3] * (1 - foreground[3]);
  if (alpha === 0) return [0, 0, 0, 0];
  const channels = foreground.slice(0, 3).map((channel, index) => (
    channel * foreground[3] + background[index] * background[3] * (1 - foreground[3])
  ) / alpha);
  return [channels[0], channels[1], channels[2], alpha];
}

function luminance(color: Color): number {
  const [red, green, blue] = color.slice(0, 3).map((channel) => {
    const srgb = channel / 255;
    return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrast(foreground: Color, background: Color): number {
  if (background[3] !== 1) throw new Error('Contrast requires an opaque background');
  const foregroundLuminance = luminance(composite(foreground, background));
  const backgroundLuminance = luminance(background);
  return (Math.max(foregroundLuminance, backgroundLuminance) + 0.05)
    / (Math.min(foregroundLuminance, backgroundLuminance) + 0.05);
}

function tokenColor(token: string, tokens: Tokens): Color {
  return parseColor(resolveValue(`var(${token})`, tokens));
}

function gradientColors(value: string): Color[] {
  const gradient = /^linear-gradient\(([\s\S]+)\)$/.exec(value.trim());
  if (!gradient) throw new Error(`Unsupported gradient: ${value}`);
  const segments = postcss.list.comma(gradient[1]);
  const stops = /^(?:to\s|[-\d.]+(?:deg|grad|rad|turn)$)/.test(segments[0])
    ? segments.slice(1)
    : segments;
  if (stops.length < 2) throw new Error('A primary gradient needs at least two color stops');
  return stops.map((stop) => parseColor(postcss.list.space(stop)[0]));
}

function declarationValue(selector: string, property: string, source = stylesheet): string {
  let value: string | undefined;
  source.walkRules((rule) => {
    if (rule.parent?.type === 'root' && rule.selectors.includes(selector)) {
      rule.walkDecls(property, (declaration) => { value = declaration.value; });
    }
  });
  if (value === undefined) throw new Error(`Missing ${property} for ${selector}`);
  return value;
}

function controlElement(theme: Theme, tag: keyof HTMLElementTagNameMap, className = '', focused = true, pressed = false): HTMLElement {
  const parent = document.createElement('div');
  parent.dataset.theme = theme;
  const element = document.createElement(tag);
  element.className = className;
  if (focused) {
    element.setAttribute('data-test-focus', '');
    element.setAttribute('data-test-focus-visible', '');
    parent.setAttribute('data-test-focus-within', '');
  }
  if (pressed) element.setAttribute('data-test-active', '');
  parent.append(element);
  return element;
}

function selectorSpecificity(selector: string): number {
  const unwrapped = selector.replace(/:not\(([^()]*)\)/g, '$1');
  const attributes = unwrapped.match(/\[[^\]]*\]/g) ?? [];
  const withoutAttributes = unwrapped.replace(/\[[^\]]*\]/g, '');
  const identifiers = withoutAttributes.match(/#[\w-]+/g) ?? [];
  const classes = withoutAttributes.match(/\.[\w-]+|:[\w-]+/g) ?? [];
  const types = withoutAttributes.replace(/#[\w-]+|\.[\w-]+|::?[\w-]+/g, '').match(/[a-z][\w-]*/gi) ?? [];
  return identifiers.length * 10000 + (attributes.length + classes.length) * 100 + types.length;
}

function winningStyle(element: HTMLElement, properties: string[], source = stylesheet, width = 1440, coarse = false): string | undefined {
  let winner: { value: string; important: boolean; specificity: number } | undefined;
  const consider = (declaration: Declaration, specificity: number) => {
    if (!properties.includes(declaration.prop)) return;
    const important = Boolean(declaration.important);
    if (!winner || (important && !winner.important)
      || (important === winner.important && specificity >= winner.specificity)) {
      winner = { value: declaration.value, important, specificity };
    }
  };
  source.walkRules((rule) => {
    if (rule.parent?.type === 'atrule') {
      const media = rule.parent;
      if (media.name !== 'media') return;
      const applies = postcss.list.comma(media.params).some((query) => query.split(/\s+and\s+/).every((clause) => {
        const widthCondition = /^\(\s*(min|max)-width:\s*(\d+)px\s*\)$/.exec(clause.trim());
        if (widthCondition) return widthCondition[1] === 'min'
          ? width >= Number(widthCondition[2]) : width <= Number(widthCondition[2]);
        return /^\(\s*pointer:\s*coarse\s*\)$/.test(clause.trim()) && coarse;
      }));
      if (!applies) return;
    } else if (rule.parent?.type !== 'root') return;
    const matching = rule.selectors.filter((selector) => !selector.includes('::') && element.matches(
      selector.replace(/:(focus-visible|focus-within|focus|hover|active)(?![\w-])/g, '[data-test-$1]'),
    ));
    if (!matching.length) return;
    const specificity = Math.max(...matching.map(selectorSpecificity));
    rule.nodes.forEach((node) => {
      if (node.type === 'decl') consider(node, specificity);
    });
  });
  for (let index = 0; index < element.style.length; index += 1) {
    const property = element.style.item(index);
    consider(postcss.decl({
      prop: property,
      value: element.style.getPropertyValue(property),
      important: element.style.getPropertyPriority(property) === 'important',
    }), 1000000);
  }
  return winner?.value;
}

function focusOutline(theme: Theme, source = stylesheet): string {
  const outline = winningStyle(controlElement(theme, 'button'), ['outline'], source);
  if (!outline) throw new Error(`Missing global focus outline for ${theme}`);
  return outline;
}

function borderColor(element: HTMLElement): string | undefined {
  const border = winningStyle(element, ['border', 'border-color']);
  if (border === undefined) return undefined;
  const parts = postcss.list.space(border);
  return parts[parts.length - 1];
}

function checkControlContrast(element: HTMLElement, role: string, tokens: Tokens, theme: Theme): void {
  const filter = winningStyle(element, ['filter']);
  const brightness = filter?.match(/^brightness\(([\d.]+)\)$/);
  const multiplier = brightness ? Number(brightness[1]) : 1;
  const [red, green, blue, alpha] = tokenColor(role, tokens);
  const color: Color = [red * multiplier, green * multiplier, blue * multiplier, alpha];
  for (const surfaceRole of ['--bg-pure', ...surfaceRoles]) {
    for (const fill of ['transparent', '--fill-soft', '--fill-soft-2']) {
      const surface = tokenColor(surfaceRole, tokens);
      const background = fill === 'transparent' ? surface : composite(tokenColor(fill, tokens), surface);
      expect.soft(contrast(color, background), `${theme}: ${element.className || element.tagName} ${role} on ${surfaceRole} / ${fill}`)
        .toBeGreaterThanOrEqual(3);
    }
  }
}

describe('Studio theme contrast measurement', () => {
  it('cascades root and light definitions in source order without reading component overrides', () => {
    const source = postcss.parse(`
      :root { --ink: #111; --alias: var(--ink); }
      [data-theme="light"] { --ink: #eee; }
      .card { --ink: #f00; }
      :root { --surface: #fff; }
      @media (max-width: 600px) { :root { --ink: #0f0; } }
    `);
    expect(resolveValue('var(--alias)', readTokens('dark', source))).toBe('#111');
    expect(resolveValue('var(--alias)', readTokens('light', source))).toBe('#eee');
    expect(readTokens('light', source)['--surface']).toBe('#fff');
  });

  it('rejects missing and circular token references instead of skipping contrast checks', () => {
    expect(() => resolveValue('var(--missing)', {})).toThrow('Missing token');
    expect(() => resolveValue('var(--ink)', { '--ink': 'var(--alias)', '--alias': 'var(--ink)' }))
      .toThrow('Circular token reference');
  });

  it('measures the winning focus outline including importance, specificity, and source order', () => {
    const source = postcss.parse(`
      *:focus-visible { outline: 2px solid #111; }
      :focus-visible { outline: 3px solid #222 !important; }
      [data-theme='light'] :focus-visible { outline: 3px solid #333 !important; }
      :focus-visible { outline: 3px solid #444 !important; }
      :focus-visible { outline: 3px solid #555; }
    `);
    expect(focusOutline('dark', source)).toBe('3px solid #444');
    expect(focusOutline('light', source)).toBe('3px solid #333');
  });

  it('detects class and inline focus overrides instead of accepting an unused global declaration', () => {
    const source = postcss.parse(`
      :focus-visible { outline: 3px solid #111 !important; }
      .control { outline: none !important; }
      .control:focus-visible { outline: 3px solid #222; }
    `);
    const control = controlElement('dark', 'button', 'control');
    control.style.outline = '3px solid #333';
    expect(winningStyle(control, ['outline'], source)).toBe('none');
    control.style.setProperty('outline', '3px solid #444', 'important');
    expect(winningStyle(control, ['outline'], source)).toBe(control.style.outline);
  });

  it('measures the known black/white and identical-color contrast boundaries', () => {
    expect(contrast(parseColor('#000'), parseColor('#fff'))).toBe(21);
    expect(contrast(parseColor('#abc'), parseColor('#abc'))).toBe(1);
  });

  it('composites translucent text and surfaces before calculating contrast', () => {
    const background = composite(parseColor('rgba(255, 255, 255, 0.5)'), parseColor('#000'));
    expect(background).toEqual([127.5, 127.5, 127.5, 1]);
    expect(contrast(parseColor('rgba(0, 0, 0, 0.5)'), background)).toBeCloseTo(2.6175, 3);
    expect(composite(parseColor('#0000'), parseColor('#fff0'))).toEqual([0, 0, 0, 0]);
    expect(contrast(parseColor('transparent'), parseColor('#fff'))).toBe(1);
  });

  it('parses every gradient stop without splitting rgba channel commas', () => {
    expect(gradientColors('linear-gradient(180deg, #fff 0%, rgba(0, 0, 0, 0.5) 50%, #000 100%)'))
      .toEqual([[255, 255, 255, 1], [0, 0, 0, 0.5], [0, 0, 0, 1]]);
    expect(gradientColors('linear-gradient(#fff, #000)')).toHaveLength(2);
  });

  it('rejects unsupported colors and incomplete backgrounds rather than inventing a passing ratio', () => {
    expect(() => parseColor('not-a-color')).toThrow('Unsupported color');
    expect(() => parseColor('rgba(0, 0, 0, 2)')).toThrow('Unsupported color');
    expect(() => contrast(parseColor('#fff'), parseColor('transparent'))).toThrow('opaque background');
    expect(() => gradientColors('none')).toThrow('Unsupported gradient');
    expect(() => gradientColors('linear-gradient(180deg, #fff)')).toThrow('at least two');
  });
});

describe.each<Theme>(['dark', 'light'])('%s studio theme', (theme) => {
  const tokens = readTokens(theme);
  const canvas = tokenColor('--bg-pure', tokens);
  const textCases = textRoles.map((textRole) => {
    const measurements = surfaceRoles.map((surfaceRole) => ({
      surfaceRole,
      ratio: contrast(tokenColor(textRole, tokens), composite(tokenColor(surfaceRole, tokens), canvas)),
    }));
    return { textRole, measurements, minimum: Math.min(...measurements.map(({ ratio }) => ratio)).toFixed(2) };
  });
  const accentFills = [
    ...accentRoles.map((role) => ({ role, color: tokenColor(role, tokens) })),
    ...gradientColors(resolveValue(tokens['--accent-gradient'], tokens))
      .map((color, index) => ({ role: `--accent-gradient stop ${index + 1}`, color })),
  ];
  const accentMeasurements = accentFills.map(({ role, color }) => ({
    role,
    ratio: contrast(tokenColor('--text-on-accent', tokens), composite(color, canvas)),
  }));
  const minimumAccent = Math.min(...accentMeasurements.map(({ ratio }) => ratio)).toFixed(2);

  it('uses the pinned blue and contrasting label color for primary commands', () => {
    expect(tokenColor('--accent-primary', tokens)).toEqual(parseColor(theme === 'dark' ? '#8cb4ff' : '#175cd3'));
    expect(tokenColor('--text-on-accent', tokens)).toEqual(parseColor(theme === 'dark' ? '#07172f' : '#ffffff'));
  });

  it('maps legacy teal, cyan, and gold accents to the same blue command roles', () => {
    for (const role of ['--accent-teal', '--accent-cyan', '--accent-gold-primary']) {
      expect.soft(tokenColor(role, tokens), role).toEqual(tokenColor('--accent-primary', tokens));
    }
    for (const role of ['--accent-teal-bright', '--accent-gold-hover']) {
      expect.soft(tokenColor(role, tokens), role).toEqual(tokenColor('--accent-hover', tokens));
    }
  });

  it('keeps the legacy gradient API visually flat without a colored glow', () => {
    for (const color of gradientColors(resolveValue(tokens['--accent-gradient'], tokens))) {
      expect.soft(color).toEqual(tokenColor('--accent-primary', tokens));
    }
    expect(tokens['--shadow-glow']).toBe('none');
  });

  it('paints primary app buttons with a flat contrast-tested fill and no reflection', () => {
    const button = controlElement(theme, 'button', 'bx-btn bx-btn--primary', false);
    expect(winningStyle(button, ['background', 'background-color'], uiStylesheet)).toBe('var(--accent-primary)');
    expect(winningStyle(button, ['box-shadow'], uiStylesheet)).toBe('none');
    const label = parseColor(resolveValue(winningStyle(button, ['color'], uiStylesheet)!, tokens));
    expect(contrast(label, tokenColor('--accent-primary', tokens))).toBeGreaterThanOrEqual(4.5);
    button.setAttribute('data-test-hover', '');
    const hover = parseColor(resolveValue(winningStyle(button, ['background', 'background-color'], uiStylesheet)!, tokens));
    expect(contrast(label, hover)).toBeGreaterThanOrEqual(4.5);
  });

  it('uses neutral navigation selection with blue reserved for the active icon', () => {
    const button = controlElement(theme, 'button', 'bx-nav-item', false);
    const icon = document.createElement('span');
    icon.className = 'bx-nav-item__icon';
    button.append(icon);
    expect(winningStyle(icon, ['color'], uiStylesheet)).toBe('var(--text-muted)');
    button.setAttribute('aria-current', 'page');
    expect(winningStyle(icon, ['color'], uiStylesheet)).toBe('var(--accent-primary)');
    const background = composite(
      parseColor(resolveValue(winningStyle(button, ['background'], uiStylesheet)!, tokens)),
      tokenColor('--bg-glass', tokens),
    );
    expect(Math.max(...background.slice(0, 3)) - Math.min(...background.slice(0, 3))).toBeLessThanOrEqual(12);
    const label = parseColor(resolveValue(winningStyle(button, ['color'], uiStylesheet)!, tokens));
    expect(contrast(label, background)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(textCases)('$textRole clears 4.5:1 on shared surfaces (minimum $minimum:1)', ({ textRole, measurements }) => {
    for (const { surfaceRole, ratio } of measurements) {
      expect.soft(ratio, `${theme}: ${textRole} on ${surfaceRole}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it(`keeps primary labels readable on accent fills and every gradient stop (minimum ${minimumAccent}:1)`, () => {
    for (const { role, ratio } of accentMeasurements) {
      expect.soft(ratio, `${theme}: --text-on-accent on ${role}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('defines the focus ring as the opaque primary accent', () => {
    expect(tokens['--focus-ring']).toBe('var(--accent-primary)');
    expect(tokenColor('--focus-ring', tokens)[3]).toBe(1);
  });

  it.each(['--focus-ring', '--border-control'])('%s clears 3:1 on shared surfaces and form fills', (role) => {
    const color = tokenColor(role, tokens);
    expect(color[3]).toBe(1);
    if (role === '--border-control') expect(new Set(color.slice(0, 3)).size).toBe(1);
    for (const surfaceRole of ['--bg-pure', ...surfaceRoles]) {
      const surface = composite(tokenColor(surfaceRole, tokens), canvas);
      for (const fill of ['transparent', '--fill-soft', '--fill-soft-2']) {
        const background = fill === 'transparent' ? surface : composite(tokenColor(fill, tokens), surface);
        expect.soft(contrast(color, background), `${theme}: ${role} on ${surfaceRole} / ${fill}`)
          .toBeGreaterThanOrEqual(3);
      }
    }
  });

  it('uses the opaque focus token in the winning global outline, not a translucent override', () => {
    const outline = focusOutline(theme);
    const [width, style, color] = postcss.list.space(resolveValue(outline, tokens));
    expect.soft(outline).toBe('3px solid var(--focus-ring)');
    expect(width).toBe('3px');
    expect(style).toBe('solid');
    for (const role of ['--bg-pure', ...surfaceRoles]) {
      expect.soft(contrast(parseColor(color), tokenColor(role, tokens)), `${theme}: winning outline on ${role}`)
        .toBeGreaterThanOrEqual(3);
    }
  });

  it.each([false, true])('keeps keyboard rings on legacy buttons when pressed=%s despite outline resets', (pressed) => {
    for (const className of ['primary-hero-btn', 'indigo-btn', 'gold-btn', 'secondary-hero-btn', 'secondary-btn', 'nav-link-btn', 'mobile-nav-btn']) {
      const button = controlElement(theme, 'button', className, true, pressed);
      expect.soft(winningStyle(button, ['outline']), `${theme}: ${className} focus outline`).toBe('3px solid var(--focus-ring)');
      checkControlContrast(button, '--focus-ring', tokens, theme);
    }
  });

  it.each([false, true])('uses readable field boundaries matching the keyboard outline when focused=%s', (focused) => {
    for (const [tag, className] of [['input', ''], ['select', ''], ['textarea', ''], ['textarea', 'ns-textarea'], ['textarea', 'bx-prompt-input']] as const) {
      const field = controlElement(theme, tag, className, focused);
      const role = focused ? '--focus-ring' : '--border-control';
      expect.soft(borderColor(field), `${theme}: ${tag}.${className} border`).toBe(`var(${role})`);
      if (focused) expect.soft(winningStyle(field, ['outline']), `${theme}: ${tag}.${className} outline`).toBe('3px solid var(--focus-ring)');
      checkControlContrast(field, role, tokens, theme);
    }
  });

  it.each([false, true])('puts the composer boundary on its wrapper when focused=%s', (focused) => {
    for (const className of ['ns-composer', 'bx-prompt-card', 'bx-prompt', 'ai-prompt-box']) {
      const input = controlElement(theme, 'textarea', 'bx-prompt-input', focused);
      const composer = input.parentElement!;
      composer.className = className;
      expect.soft(borderColor(composer), `${theme}: ${className} border`).toBe(`var(${focused ? '--focus-ring' : '--border-control'})`);
      if (focused) {
        expect.soft(winningStyle(composer, ['outline']), `${theme}: ${className} outer outline`).toBe('3px solid var(--focus-ring)');
        expect.soft(winningStyle(input, ['outline']), `${theme}: ${className} inner outline`).toBe('none');
      }
    }
  });

  it.each([false, true])('keeps outlined button boundaries readable when pressed=%s', (pressed) => {
    for (const className of ['secondary-hero-btn', 'secondary-btn']) {
      const button = controlElement(theme, 'button', className, false, pressed);
      expect.soft(borderColor(button), `${theme}: ${className} normal border`).toBe('var(--border-control)');
      checkControlContrast(button, '--border-control', tokens, theme);
      button.setAttribute('data-test-focus-visible', '');
      expect.soft(borderColor(button), `${theme}: ${className} focused border`).toBe('var(--focus-ring)');
    }
  });

  it('gives the rendered copy button 32px desktop and 44px mobile/coarse targets with a readable border', () => {
    const { container } = render(createElement(RequestIdTag, { requestId: 'req_target_size' }));
    container.dataset.theme = theme;
    const button = within(container).getByRole('button', { name: 'Copy request ID' });
    expect.soft(borderColor(button)).toBe('var(--border-control)');
    for (const viewport of [{ width: 1440, coarse: false, minimum: 32 }, { width: 390, coarse: false, minimum: 44 }, { width: 1024, coarse: true, minimum: 44 }]) {
      for (const property of ['min-width', 'min-height']) {
        const value = winningStyle(button, [property], stylesheet, viewport.width, viewport.coarse);
        expect.soft(value, `${theme}: ${property} at ${viewport.width}px / coarse=${viewport.coarse}`).toMatch(/^\d+px$/);
        expect.soft(Number.parseFloat(value ?? ''), `${theme}: ${property} target`).toBeGreaterThanOrEqual(viewport.minimum);
      }
    }
  });

  it('retains decorative hairlines instead of treating them as control boundaries', () => {
    expect(declarationValue('.clean-card', 'border')).toBe('1px solid var(--border-soft)');
  });

  it('uses opaque neutral surfaces, including legacy glass aliases', () => {
    for (const role of ['--bg-pure', ...surfaceRoles, '--bg-glass', '--glass-strong', '--glass-mid', '--glass-soft']) {
      const color = tokenColor(role, tokens);
      expect.soft(color[3], `${theme}: ${role} opacity`).toBe(1);
      expect.soft(Math.max(...color.slice(0, 3)) - Math.min(...color.slice(0, 3)), `${theme}: ${role} neutrality`)
        .toBeLessThanOrEqual(12);
    }
    if (theme === 'dark') expect(luminance(canvas)).toBe(0);
    else expect(luminance(canvas)).toBeGreaterThan(0.85);
  });
});

describe('Pitch-black dark canvas contract', () => {
  const tokens = readTokens('dark');

  it.each(['--bg-pure', '--bg-primary'])('uses opaque black for the shared %s canvas', (token) => {
    expect(tokenColor(token, tokens)).toEqual([0, 0, 0, 1]);
  });

  it.each(['--studio-bg', '--studio-band'])('uses opaque black for public-page %s backgrounds', (token) => {
    expect(parseColor(declarationValue('.studio-landing', token, landingStylesheet))).toEqual([0, 0, 0, 1]);
  });

  it.each(['--ambient-a', '--ambient-b', '--ambient-c'])('does not tint the canvas through %s', (token) => {
    expect(tokenColor(token, tokens)[3]).toBe(0);
  });
});

describe('Studio theme typography and material rules', () => {
  const tokens = readTokens('dark');

  it.each([
    ['--font-sans', 'Plus Jakarta Sans'],
    ['--font-display', 'Plus Jakarta Sans'],
    ['--font-mono', 'JetBrains Mono'],
  ])('leads %s with the existing self-hosted %s family', (token, family) => {
    expect(postcss.list.comma(tokens[token])[0].replace(/['"]/g, '')).toBe(family);
  });

  it('keeps the metadata type floor at 0.75rem or larger', () => {
    expect(tokens['--fs-xs']).toMatch(/^\d+(?:\.\d+)?rem$/);
    expect(Number.parseFloat(tokens['--fs-xs'])).toBeGreaterThanOrEqual(0.75);
  });

  it('uses a fixed rem size for the largest shared heading', () => {
    expect(tokens['--fs-3xl']).toMatch(/^\d+(?:\.\d+)?rem$/);
  });

  it.each([
    ['--r-xs', 4], ['--r-sm', 6], ['--r-md', 8], ['--r-lg', 8], ['--r-xl', 12],
  ] as const)('keeps %s within its %ipx control, card, or modal limit', (token, maximum) => {
    expect(tokens[token]).toMatch(/^\d+px$/);
    expect(Number.parseFloat(tokens[token])).toBeLessThanOrEqual(maximum);
  });

  it('keeps existing heading and label tracking at zero', () => {
    expect(declarationValue('h1', 'letter-spacing')).toBe('0');
    stylesheet.walkDecls('letter-spacing', (declaration) => {
      expect.soft(declaration.value, declaration.parent?.toString()).toBe('0');
    });
  });

  it('does not paint decorative radial washes behind the canvas', () => {
    expect(declarationValue('.bx-ambient', 'background')).not.toContain('radial-gradient(');
  });

  it('keeps shared cards stationary and free of stacked reflections', () => {
    expect(declarationValue('.clean-card', 'box-shadow')).toBe('none');
    expect(declarationValue('.clean-card', 'transition')).not.toMatch(/transform|width/);
    expect(declarationValue('.bx-lift:hover', 'transform')).toBe('none');
    expect(declarationValue('.bx-lift:hover', 'box-shadow')).toBe('none');
  });

  it('keeps honest live status indicators static without a decorative pulse', () => {
    expect(declarationValue('.bx-dot--live::after', 'content', uiStylesheet)).toBe('none');
  });

  it('centers the launcher at an 800px measure with a 32px task heading and one composer surface', () => {
    expect(declarationValue('.ns-inner', 'max-width', newStudyStylesheet)).toBe('50rem');
    expect(declarationValue('.ns-inner', 'margin', newStudyStylesheet)).toBe('0 auto');
    expect(declarationValue('.ns-title', 'font', newStudyStylesheet)).toBe('600 2rem/1.25 var(--font-display)');
    expect(declarationValue('.ns-composer', 'background', newStudyStylesheet)).toBe('var(--bg-card)');
    expect(declarationValue('.ns-composer', 'box-shadow', newStudyStylesheet)).toBe('none');
  });

  it('uses compact semibold page headings instead of dashboard hero typography', () => {
    expect(declarationValue('.bx-title', 'font-weight', uiStylesheet)).toBe('600');
    expect(declarationValue('.bx-title--display', 'font-size', uiStylesheet)).toBe('var(--fs-2xl)');
    expect(declarationValue('.sd-display', 'font', studiesStylesheet)).toBe('600 1.75rem/1.3 var(--font-display)');
  });

  it('keeps summary figures and the example-study band unframed', () => {
    expect(declarationValue('.bx-metric', 'background', uiStylesheet)).toBe('transparent');
    expect(declarationValue('.bx-metric', 'box-shadow', uiStylesheet)).toBe('none');
    expect(declarationValue('.bx-figure', 'border-left', uiStylesheet)).toBe('none');
    expect(declarationValue('.sd-demo', 'background', studiesStylesheet)).toBe('transparent');
    expect(declarationValue('.sd-demo', 'border-radius', studiesStylesheet)).toBe('0');
  });
});