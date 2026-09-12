import { spawn, spawnSync } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');

if (process.env.NODE_ENV === 'production' || ['production', 'staging'].includes(process.env.BEBSHAX_ENVIRONMENT)) {
  process.stderr.write('The dev launcher is not a production supervisor. Use the reviewed release images.\n');
  process.exit(1);
}

console.log('\x1b[36m%s\x1b[0m', '════════════════════════════════════════════════════════════');
console.log('\x1b[36m%s\x1b[0m', '🚀 BebshaX Full-Stack Platform Launcher (Backend + Frontend)');
console.log('\x1b[36m%s\x1b[0m', '════════════════════════════════════════════════════════════');

process.stdout.write('Development only. Database startup/migrations and operator credentials are explicit prerequisites.\n');
process.stdout.write('Live conversation uses approved remote providers; CPU selection and cached examples are separate.\n');

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
const frontend = spawn(npmCmd, ['run', 'dev', '--workspace', 'apps/frontend', '--', '--host', '127.0.0.1', '--strictPort'], {
  cwd: rootDir,
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
