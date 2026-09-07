import { spawn, spawnSync, execSync } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');

console.log('\x1b[36m%s\x1b[0m', '════════════════════════════════════════════════════════════');
console.log('\x1b[36m%s\x1b[0m', '🚀 BebshaX Full-Stack Platform Launcher (Backend + Frontend)');
console.log('\x1b[36m%s\x1b[0m', '════════════════════════════════════════════════════════════');

// 1. Attempt to start Docker Database Container (db on port 5433)
console.log('\x1b[33m%s\x1b[0m', '🐳 Checking Docker Database Container (db on port 5433)...');
try {
  // --wait blocks until the pg_isready healthcheck passes — without it the
  // backend races a cold-booting Postgres and fails its first connections.
  const dockerResult = execSync('docker compose up -d --wait db', {
    cwd: rootDir,
    stdio: 'pipe',
    encoding: 'utf-8',
  });
  console.log('\x1b[32m%s\x1b[0m', '✅ Database container is running on localhost:5433');
  if (dockerResult && dockerResult.trim()) {
    console.log(`   ${dockerResult.trim()}`);
  }
} catch {
  console.log('\x1b[33m%s\x1b[0m', 'ℹ️ Local Docker container skipped or daemon not responding.');
  console.log('\x1b[33m%s\x1b[0m', '   Using configured cloud database from .env / Neon Postgres.');
}

// Warn-only demo-readiness hint — never blocks or exits (daily-dev tool).
// Mirrors backend env precedence: real environment beats .env. Prints host:port
// only, never credentials or full URLs.
try {
  const dotenv = {};
  const envPath = path.join(rootDir, '.env');
  if (fs.existsSync(envPath)) {
    for (const raw of fs.readFileSync(envPath, 'utf-8').split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || line.startsWith('#') || !line.includes('=')) continue;
      const idx = line.indexOf('=');
      dotenv[line.slice(0, idx).trim()] = line.slice(idx + 1).trim().replace(/^['"]|['"]$/g, '');
    }
  }
  const envVal = (name) => process.env[name] ?? dotenv[name] ?? '';
  // Default mirrors bebshax/config.py Settings.database_url
  const dbUrl = envVal('BEBSHAX_DATABASE_URL') || 'postgresql+asyncpg://bebshax:bebshax@localhost:5433/bebshax';
  let dbHost = '?';
  let dbPort = '?';
  try {
    const parsed = new URL(dbUrl.replace(/^postgresql\+[a-z0-9]+:/i, 'postgresql:'));
    dbHost = parsed.hostname || '?';
    dbPort = parsed.port || '5432';
  } catch {}
  const dbLocal = (dbHost === 'localhost' || dbHost === '127.0.0.1') && dbPort === '5433';
  const demoOn = ['true', '1', 'yes', 'on'].includes(envVal('BEBSHAX_DEMO_MODE').toLowerCase());
  if (!dbLocal || !demoOn) {
    const reasons = [];
    if (!dbLocal) reasons.push(`database is ${dbHost}:${dbPort} (offline demo needs localhost:5433)`);
    if (!demoOn) reasons.push('BEBSHAX_DEMO_MODE is not true');
    console.log('\x1b[33m%s\x1b[0m', '┌────────────────────────────────────────────────────────────');
    console.log('\x1b[33m%s\x1b[0m', '│ ⚠ NOT demo-ready (fine for daily dev):');
    for (const reason of reasons) {
      console.log('\x1b[33m%s\x1b[0m', `│   • ${reason}`);
    }
    console.log('\x1b[33m%s\x1b[0m', '│   run: .venv\\Scripts\\python scripts\\demo_preflight.py');
    console.log('\x1b[33m%s\x1b[0m', '└────────────────────────────────────────────────────────────');
  }
} catch {
  // hint is best-effort only — never interfere with startup
}

// 2. Locate Python executable in virtual environment
let pythonCmd = 'python';
const venvWin = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
const venvUnix = path.join(rootDir, '.venv', 'bin', 'python');

if (fs.existsSync(venvWin)) {
  pythonCmd = venvWin;
} else if (fs.existsSync(venvUnix)) {
  pythonCmd = venvUnix;
}

console.log('\x1b[36m%s\x1b[0m', '🌐 Backend API:  http://127.0.0.1:8000  (Health: /api/health)');
console.log('\x1b[36m%s\x1b[0m', '💻 Frontend App: http://localhost:5173');
console.log('\x1b[36m%s\x1b[0m', '────────────────────────────────────────────────────────────');

// 3. Start FastAPI Backend
let shuttingDown = false;

// frontend is spawned through a shell wrapper (npm.cmd); plain .kill() on
// Windows stops the wrapper and orphans the Vite node process underneath.
function killTree(child) {
  if (!child || child.exitCode !== null) return;
  try {
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
    } else {
      child.kill();
    }
  } catch {}
}

const backend = spawn(pythonCmd, ['-m', 'uvicorn', 'bebshax.main:app', '--host', '127.0.0.1', '--port', '8000', '--reload'], {
  cwd: rootDir,
  shell: false,
  stdio: 'pipe',
  env: { ...process.env, PYTHONUNBUFFERED: '1' },
});

backend.stdout.on('data', (data) => {
  process.stdout.write(`\x1b[34m[Backend]\x1b[0m ${data}`);
});

backend.stderr.on('data', (data) => {
  process.stderr.write(`\x1b[34m[Backend]\x1b[0m ${data}`);
});

backend.on('error', (err) => {
  console.error('\x1b[31m[Backend Error]\x1b[0m', err);
});

// A backend that dies (config FATAL, migration drift, port in use) used to
// leave Vite happily serving a UI with no API behind it. Non-zero exit = stop
// everything loudly. Exit code 0 / signal-kills (our own cleanup, uvicorn
// reload churn) are left alone — the warn-only behaviors above stay warn-only.
backend.on('exit', (code, signal) => {
  if (shuttingDown || code === 0 || code === null) return;
  console.error('\x1b[31m%s\x1b[0m', '┌────────────────────────────────────────────────────────────');
  console.error('\x1b[31m%s\x1b[0m', `│ FATAL: backend exited with code ${code}${signal ? ` (${signal})` : ''} — stopping the frontend.`);
  console.error('\x1b[31m%s\x1b[0m', '│ Read the [Backend] lines above (config FATAL / migration drift / port 8000 busy).');
  console.error('\x1b[31m%s\x1b[0m', '└────────────────────────────────────────────────────────────');
  shuttingDown = true;
  killTree(frontend);
  process.exit(code);
});

// 4. Start Vite Frontend
const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const frontend = spawn(npmCmd, ['run', 'dev'], {
  cwd: path.join(rootDir, 'apps', 'frontend'),
  shell: true,
  stdio: 'pipe',
});

frontend.stdout.on('data', (data) => {
  process.stdout.write(`\x1b[32m[Frontend]\x1b[0m ${data}`);
});

frontend.stderr.on('data', (data) => {
  process.stderr.write(`\x1b[32m[Frontend]\x1b[0m ${data}`);
});

frontend.on('error', (err) => {
  console.error('\x1b[31m[Frontend Error]\x1b[0m', err);
});

function cleanup() {
  shuttingDown = true;
  console.log('\n\x1b[33m%s\x1b[0m', '🛑 Shutting down backend & frontend servers...');
  try { backend.kill(); } catch {}
  killTree(frontend);
  process.exit();
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);
