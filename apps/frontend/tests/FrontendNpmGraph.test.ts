import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { describe, expect, it } from 'vitest';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const graphUrl = pathToFileURL(resolve(frontend, '../../scripts/ops/npm-graph.mjs')).href;
const graph = {
  checkManifests(rootManifest: object, frontendManifest: object, lock: object): Record<string, string | null> {
    const result = spawnSync(process.execPath, ['--input-type=module', '-e', `
      const { checkManifests } = await import(process.argv[1]);
      const input = JSON.parse(process.argv[2]);
      try {
        process.stdout.write(JSON.stringify({ selected: checkManifests(input.rootManifest, input.frontendManifest, input.lock) }));
      } catch (error) {
        process.stdout.write(JSON.stringify({ error: error.message }));
      }
    `, graphUrl, JSON.stringify({ rootManifest, frontendManifest, lock })], { encoding: 'utf8' });
    if (result.status !== 0) throw new Error(result.stderr || result.error?.message || 'Graph process failed');
    const parsed: { selected?: Record<string, string | null>; error?: string } = JSON.parse(result.stdout);
    if (parsed.error) throw new Error(parsed.error);
    if (!parsed.selected) throw new Error('Graph process returned no selected versions');
    return parsed.selected;
  },
};

const fixture = (viteVersion: string) => {
  const rootManifest = { workspaces: ['apps/frontend'] };
  const frontendManifest = { dependencies: { vite: `^${viteVersion}` } };
  const lock = {
    lockfileVersion: 3,
    packages: {
      '': {},
      'apps/frontend': { ...frontendManifest },
      'node_modules/vite': { version: viteVersion },
      'node_modules/rolldown': { version: '1.2.8' },
      'node_modules/lightningcss': { version: '1.33.0' },
      'node_modules/esbuild': { version: '0.21.5' },
      'node_modules/rollup': { version: '4.63.1' },
    },
  };
  return { rootManifest, frontendManifest, lock };
};

describe('Frontend authoritative npm graph', () => {
  it('selects Rolldown and Lightning CSS for Vite 8 instead of the legacy build engines', () => {
    const { rootManifest, frontendManifest, lock } = fixture('8.2.2');
    const selected = graph.checkManifests(rootManifest, frontendManifest, lock);

    expect(selected).toMatchObject({ vite: '8.2.2', rolldown: '1.2.8', lightningcss: '1.33.0' });
    expect(selected).not.toHaveProperty('rollup');
    expect(selected).not.toHaveProperty('esbuild');
  });

  it('retains the legacy build-engine checks for a Vite 5 lock', () => {
    const { rootManifest, frontendManifest, lock } = fixture('5.4.21');
    const selected = graph.checkManifests(rootManifest, frontendManifest, lock);

    expect(selected).toMatchObject({ vite: '5.4.21', esbuild: '0.21.5', rollup: '4.63.1' });
    expect(selected).not.toHaveProperty('rolldown');
  });

  it('resolves the workspace-scoped engine version before a hoisted copy', () => {
    const { rootManifest, frontendManifest, lock } = fixture('8.2.2');
    const scopedLock = {
      ...lock,
      packages: { ...lock.packages, 'apps/frontend/node_modules/rolldown': { version: '1.2.4' } },
    };

    expect(graph.checkManifests(rootManifest, frontendManifest, scopedLock).rolldown).toBe('1.2.4');
  });

  it('rejects a mismatched workspace manifest before reporting selected versions', () => {
    const { rootManifest, frontendManifest, lock } = fixture('8.2.2');
    const mismatched = { ...frontendManifest, dependencies: { vite: '^7.3.6' } };

    expect(() => graph.checkManifests(rootManifest, mismatched, lock)).toThrow(/Root lock.*dependencies differ/);
  });
});