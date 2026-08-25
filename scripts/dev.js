import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');

// Locate python executable
let pythonCmd = 'python';
const venvWin = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
const venvUnix = path.join(rootDir, '.venv', 'bin', 'python');

if (fs.existsSync(venvWin)) {
  pythonCmd = venvWin;
} else if (fs.existsSync(venvUnix)) {
  pythonCmd = venvUnix;
}

console.log('\x1b[36m%s\x1b[0m', '🚀 Starting BebshaX Backend (Port 8000) & Frontend (Port 5173)...');

// Start FastAPI Backend
const backend = spawn(pythonCmd, ['-m', 'uvicorn', 'bebshax.main:app', '--port', '8000', '--reload'], {
  cwd: rootDir,
  shell: true,
  stdio: 'pipe',
  env: { ...process.env, PYTHONUNBUFFERED: '1' }
});

backend.stdout.on('data', (data) => {
  process.stdout.write(`\x1b[34m[Backend]\x1b[0m ${data}`);
});

backend.stderr.on('data', (data) => {
  process.stderr.write(`\x1b[34m[Backend]\x1b[0m ${data}`);
});

// Start Frontend
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

function cleanup() {
  console.log('\n\x1b[33m%s\x1b[0m', 'Shutting down servers...');
  try { backend.kill(); } catch {}
  try { frontend.kill(); } catch {}
  process.exit();
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);
