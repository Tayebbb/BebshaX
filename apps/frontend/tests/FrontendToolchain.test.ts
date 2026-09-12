import { spawnSync } from 'node:child_process';
import { realpathSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';

interface TestInvocation {
  cwd: string;
  args: string[];
  env: NodeJS.ProcessEnv;
}

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const runnerUrl = pathToFileURL(resolve(frontend, 'scripts/test-runner.mjs'));
const runner: {
  createTestInvocation: (frontend: string, args?: readonly string[]) => TestInvocation;
} = await import(runnerUrl.href);

describe('Frontend test runner boundary', () => {
  afterEach(() => vi.unstubAllEnvs());

  it('uses canonical paths for both the working directory and Vitest entry', () => {
    const alternatePath = process.platform === 'win32'
      ? frontend.replace(/^[A-Z]:/, (drive) => drive.toLowerCase())
      : resolve(frontend, 'tests', '..');
    const invocation = runner.createTestInvocation(alternatePath);

    expect(invocation.cwd).toBe(realpathSync.native(frontend));
    expect(invocation.args[0]).toBe(realpathSync.native(invocation.args[0]));
    expect(invocation.args[1]).toBe('run');
  });

  it('forwards test filters and worker flags without mutating the supplied arguments', () => {
    const args = Object.freeze(['tests/LandingPage.test.tsx', '--maxWorkers=1', '--no-file-parallelism']);
    const invocation = runner.createTestInvocation(frontend, args);

    expect(invocation.args.slice(1)).toEqual(['run', ...args]);
    expect(args).toEqual(['tests/LandingPage.test.tsx', '--maxWorkers=1', '--no-file-parallelism']);
  });

  it('isolates environment-file loading without changing the parent environment', () => {
    vi.stubEnv('BEBSHAX_FRONTEND_VERIFY', '0');
    const invocation = runner.createTestInvocation(frontend);

    expect(invocation.env.BEBSHAX_FRONTEND_VERIFY).toBe('1');
    expect(process.env.BEBSHAX_FRONTEND_VERIFY).toBe('0');
  });
});

describe('Frontend utility CSS boundary', () => {
  it('generates layout utilities when the preview starts from the repository root', () => {
    const configUrl = pathToFileURL(resolve(frontend, 'postcss.config.js')).href;
    const source = `
      import postcss from 'postcss';
      import tailwindcss from 'tailwindcss';
      import config from ${JSON.stringify(configUrl)};
      const result = await postcss([tailwindcss(config.plugins.tailwindcss)]).process(
        '@tailwind utilities;', { from: ${JSON.stringify(resolve(frontend, 'src/index.css'))} }
      );
      process.stdout.write(JSON.stringify({
        grid: result.css.includes('.grid {'),
        wrapping: result.css.includes('.flex-wrap {'),
        padding: result.css.includes('.p-6 {'),
        columns: result.css.includes('.grid-cols-2 {')
      }));
    `;
    const result = spawnSync(process.execPath, ['--input-type=module', '-e', source], {
      cwd: resolve(frontend, '../..'),
      encoding: 'utf8',
    });
    expect(result.status, result.stderr).toBe(0);
    expect(JSON.parse(result.stdout)).toEqual({ grid: true, wrapping: true, padding: true, columns: true });
  });
});