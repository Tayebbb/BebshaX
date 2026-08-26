import { spawn, execSync } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');

console.log('\x1b[36m%s\x1b[0m', '═══════════════════════════════════════════════════');
console.log('\x1b[36m%s\x1b[0m', '🚀 BebshaX Backend & Database Launcher');
console.log('\x1b[36m%s\x1b[0m', '═══════════════════════════════════════════════════');

// 1. Attempt to start Docker Database Container (db on port 5433)
console.log('\x1b[33m%s\x1b[0m', '🐳 Starting Docker Database Container (db on port 5433)...');
try {
  const dockerResult = execSync('docker compose up -d db', {
    cwd: rootDir,
    stdio: 'pipe',
    encoding: 'utf-8',
  });
  console.log('\x1b[32m%s\x1b[0m', '✅ Database container is running on localhost:5433');
  if (dockerResult && dockerResult.trim()) {
    console.log(`   ${dockerResult.trim()}`);
  }
} catch (err) {
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

console.log('\x1b[36m%s\x1b[0m', `🚀 Starting FastAPI Backend at http://127.0.0.1:8000 ...`);

// 3. Start Backend uvicorn server with proper quoting for spaces in paths
const uvicornArgs = ['-m', 'uvicorn', 'bebshax.main:app', '--host', '127.0.0.1', '--port', '8000', '--reload'];
const backend = spawn(pythonCmd, uvicornArgs, {
  cwd: rootDir,
  shell: false,
  stdio: 'inherit',
  env: { ...process.env, PYTHONUNBUFFERED: '1' },
});

backend.on('error', (err) => {
  console.error('\x1b[31m[Backend Error]\x1b[0m', err);
});

function cleanup() {
  console.log('\n\x1b[33m%s\x1b[0m', '🛑 Stopping backend server...');
  try { backend.kill(); } catch {}
  process.exit();
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);
