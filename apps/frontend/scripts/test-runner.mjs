import { spawnSync } from 'node:child_process';
import { realpathSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');

export function createTestInvocation(frontendDirectory, args = []) {
  const cwd = realpathSync.native(frontendDirectory);
  const require = createRequire(resolve(cwd, 'package.json'));
  const entry = realpathSync.native(resolve(dirname(require.resolve('vitest/package.json')), 'vitest.mjs'));
  return {
    cwd,
    args: [entry, 'run', ...args],
    env: { ...process.env, BEBSHAX_FRONTEND_VERIFY: '1' },
  };
}

export function runTests(args = []) {
  const invocation = createTestInvocation(frontend, args);
  const result = spawnSync(process.execPath, invocation.args, {
    cwd: invocation.cwd,
    env: invocation.env,
    stdio: 'inherit',
  });
  if (result.error) process.stderr.write(`${result.error.message}\n`);
  return result.status ?? 1;
}

if (process.argv[1] && realpathSync.native(process.argv[1]) === realpathSync.native(fileURLToPath(import.meta.url))) {
  process.exitCode = runTests(process.argv.slice(2));
}