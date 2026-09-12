import { spawnSync } from 'node:child_process';
import { closeSync, mkdirSync, openSync, readFileSync, writeFileSync } from 'node:fs';
import { devNull } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const worker = process.argv[2] === '--worker';
const [label, executable, ...args] = process.argv.slice(worker ? 3 : 2);
if (!label || !/^[a-z0-9-]+$/.test(label) || !executable) {
  process.stderr.write('Usage: node scripts/ops/run-check.mjs LABEL EXECUTABLE [ARGS...]\n');
  process.exit(2);
}

const output = path.join(root, '.tmp', 'ops');
if (process.platform === 'win32' && !worker) {
  const result = spawnSync(process.execPath, [fileURLToPath(import.meta.url), '--worker', label, executable, ...args], {
    cwd: root, detached: true, stdio: 'ignore', windowsHide: true, timeout: 30 * 60 * 1000,
  });
  const receipt = JSON.parse(readFileSync(path.join(output, `${label}.json`), 'utf8'));
  const code = receipt.exitCode ?? result.status ?? 1;
  process.stdout.write(`${label}: ${code === 0 ? 'PASS' : 'FAIL'} (exit ${code}); .tmp/ops/${label}.log\n`);
  process.exit(code);
}
const temporary = path.join(output, 'tmp');
mkdirSync(temporary, { recursive: true });
const inherited = ['PATH', 'Path', 'SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT', 'HOME', 'USERPROFILE', 'CI',
  'ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432', 'ProgramData', 'ALLUSERSPROFILE'];
const environment = Object.fromEntries(inherited.filter((key) => process.env[key]).map((key) => [key, process.env[key]]));
Object.assign(environment, {
  TMP: temporary,
  TEMP: temporary,
  TMPDIR: temporary,
  PIP_CONFIG_FILE: devNull,
  PIP_DISABLE_PIP_VERSION_CHECK: '1',
  PIP_CACHE_DIR: path.join(output, 'pip-cache'),
  UV_CACHE_DIR: path.join(output, 'uv-cache'),
  UV_NO_CONFIG: '1',
  UV_PYTHON_DOWNLOADS: 'never',
  PYTHONNOUSERSITE: '1',
  PYTHONUNBUFFERED: '1',
  PYTHONDONTWRITEBYTECODE: '1',
  BEBSHAX_FRONTEND_VERIFY: '1',
  VITE_API_BASE: '/api',
  VITE_MOCK: 'false',
  VITE_NEON_AUTH_URL: '',
  NPM_CONFIG_USERCONFIG: path.join(output, 'npm-user-config'),
  NPM_CONFIG_GLOBALCONFIG: path.join(output, 'npm-global-config'),
  NPM_CONFIG_CACHE: path.join(output, 'npm-cache'),
  COMPOSE_DISABLE_ENV_FILE: '1',
  DOCKER_CONFIG: path.join(output, 'docker-config'),
  OMP_NUM_THREADS: '2',
  OPENBLAS_NUM_THREADS: '2',
  MKL_NUM_THREADS: '2',
  NUMEXPR_NUM_THREADS: '2',
});

const report = path.join(output, `${label}.json`);
const log = path.join(output, `${label}.log`);
const started = new Date().toISOString();
writeFileSync(report, JSON.stringify({ label, started, status: 'running' }, null, 2));
const descriptor = openSync(log, 'w');
const result = spawnSync(executable, args, {
  cwd: root,
  env: environment,
  encoding: 'utf8',
  windowsHide: true,
  stdio: ['ignore', descriptor, descriptor],
  timeout: 29 * 60 * 1000,
});
closeSync(descriptor);
const exitCode = result.status ?? 1;
writeFileSync(report, JSON.stringify({
  label,
  started,
  finished: new Date().toISOString(),
  exitCode,
  signal: result.signal,
  errorCode: result.error?.code ?? null,
  log: path.relative(root, log).replaceAll('\\', '/'),
}, null, 2));
process.stdout.write(`${label}: ${exitCode === 0 ? 'PASS' : 'FAIL'} (exit ${exitCode}); .tmp/ops/${label}.log\n`);
process.exitCode = exitCode;