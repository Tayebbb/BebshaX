import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { productionCommand } from '../start.mjs';
import { pythonExecutable } from '../ops/python.mjs';

const root = new URL('../../', import.meta.url);

test('ops JavaScript entry points parse without starting any service', () => {
  for (const relative of ['scripts/dev.js', 'scripts/run_backend.js', 'scripts/start.mjs', 'scripts/ops/python.mjs',
    'scripts/ops/run-check.mjs', 'scripts/ops/npm-graph.mjs', 'scripts/ops/web-config.mjs']) {
    const result = spawnSync(process.execPath, ['--check', fileURLToPath(new URL(relative, root))], { encoding: 'utf8' });
    assert.equal(result.status, 0, `${relative}: ${result.stderr}`);
  }
});

test('dev launcher does not inspect credentials or implicitly start a database', () => {
  const source = readFileSync(new URL('scripts/dev.js', root), 'utf8');
  assert.equal(source.includes('readFileSync'), false);
  assert.equal(source.includes('docker compose up'), false);
  assert.equal(source.includes("'--host', '127.0.0.1', '--strictPort'"), true);
});

test('backend development launcher rejects production before starting any services', () => {
  const launcher = fileURLToPath(new URL('scripts/run_backend.js', root));
  const source = readFileSync(launcher, 'utf8');
  assert.doesNotMatch(source, /execSync|docker\s+compose|readFileSync/);
  assert.match(source, /NODE_ENV/);
  for (const environment of [{ NODE_ENV: 'production' }, { BEBSHAX_ENVIRONMENT: 'staging' }]) {
    const result = spawnSync(process.execPath, [launcher], {
      cwd: fileURLToPath(root), encoding: 'utf8', env: environment, timeout: 5000,
    });
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, /development|production/i);
    assert.equal(result.stdout, '');
  }
});

test('production start validates configuration and uses one non-reloading loopback API worker', () => {
  assert.deepEqual(productionCommand('project-python'), [
    'deploy/runtime_config.py', 'project-python', '-m', 'uvicorn', 'bebshax.main:app',
    '--host', '127.0.0.1', '--port', '8000', '--workers', '1', '--timeout-graceful-shutdown', '25',
  ]);
  const result = spawnSync(process.execPath, [fileURLToPath(new URL('scripts/start.mjs', root))], {
    encoding: 'utf8', env: {}, timeout: 5000,
  });
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, /BEBSHAX_ENVIRONMENT/);
});

test('Python command selection never falls back to an unreviewed global interpreter', () => {
  assert.throws(() => pythonExecutable(fileURLToPath(root), 'win32', () => false), /Missing project virtual environment/);
  assert.match(pythonExecutable(fileURLToPath(root), 'win32', () => true), /\.venv[\\/]Scripts[\\/]python\.exe$/);
  assert.match(pythonExecutable(fileURLToPath(root), 'linux', () => true), /\.venv[\\/]bin[\\/]python$/);
});

test('root build and frontend tests consume the workspace graph and start is not development', () => {
  const manifest = JSON.parse(readFileSync(new URL('package.json', root), 'utf8'));
  assert.equal(manifest.scripts.start, 'node scripts/start.mjs');
  assert.equal(manifest.scripts.build, 'npm run build --workspace apps/frontend');
  assert.match(manifest.scripts['test:frontend'], /--workspace apps\/frontend/);
  assert.doesNotMatch(JSON.stringify(manifest.scripts), /--prefix/);
  assert.match(manifest.scripts.test, /test:ops.*test:backend.*test:ml.*test:frontend/);
});

test('Vite development and preview bind only loopback without dropping TypeScript alias checks', () => {
  const config = readFileSync(new URL('apps/frontend/vite.config.ts', root), 'utf8');
  assert.match(config, /server:\s*\{[^}]*host: '127\.0\.0\.1'[^}]*strictPort: true/s);
  assert.match(config, /preview:\s*\{[^}]*host: '127\.0\.0\.1'[^}]*strictPort: true/s);
  const typescript = readFileSync(new URL('apps/frontend/tsconfig.json', root), 'utf8');
  assert.doesNotMatch(typescript, /"baseUrl"|"ignoreDeprecations"/);
  assert.match(typescript, /"@\/\*":\s*\["\.\/src\/\*"\]/);
});

test('legacy local inference executables and preflight are retired', () => {
  for (const relative of ['scripts/benchmark_ollama.py', 'scripts/smoke_ollama.py', 'scripts/demo_preflight.py']) {
    assert.equal(existsSync(new URL(relative, root)), true);
    const source = readFileSync(new URL(relative, root), 'utf8');
    assert.match(source, /raise SystemExit/);
    assert.match(source, /retired/);
    assert.doesNotMatch(source, /import |httpx|subprocess|write_text|unlink/);
  }
});

test('setup consumes the locked installer and leaves configuration files alone', () => {
  const source = readFileSync(new URL('scripts/setup.py', root), 'utf8');
  assert.match(source, /"dependencies\.py"\), "install"/);
  assert.equal(source.includes('env_path.read_text'), false);
  assert.equal(source.includes('env_path.write_text'), false);
  assert.equal(source.includes('ensure_env_file'), false);
  assert.equal(source.includes('if args.migrate:'), true);
});