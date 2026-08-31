import { spawn, execSync } from 'child_process';
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
  console.log('\n\x1b[33m%s\x1b[0m', '🛑 Shutting down backend & frontend servers...');
  try { backend.kill(); } catch {}
  try { frontend.kill(); } catch {}
  process.exit();
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);
