import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');

if (process.env.NODE_ENV === 'production' || ['production', 'staging'].includes(process.env.BEBSHAX_ENVIRONMENT)) {
  process.stderr.write('The backend development launcher cannot run in production or staging. Use npm start.\n');
  process.exit(1);
}

const venvWin = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
const venvUnix = path.join(rootDir, '.venv', 'bin', 'python');
const pythonCmd = [venvWin, venvUnix].find((candidate) => fs.existsSync(candidate));

if (!pythonCmd) {
  process.stderr.write('Missing project virtual environment. Follow docs/SETUP.md before starting the API.\n');
  process.exit(1);
}

process.stdout.write('Development API: http://127.0.0.1:8000. Database and migrations must already be ready.\n');

const uvicornArgs = ['-m', 'uvicorn', 'bebshax.main:app', '--host', '127.0.0.1', '--port', '8000', '--reload', '--reload-dir', 'apps/backend/bebshax'];
const backend = spawn(pythonCmd, uvicornArgs, {
  cwd: rootDir,
  shell: false,
  stdio: 'inherit',
  env: { ...process.env, PYTHONUNBUFFERED: '1' },
});

backend.on('error', () => {
  process.stderr.write('Backend process could not start. Check the project environment.\n');
  process.exitCode = 1;
});

backend.on('exit', (code, signal) => {
  process.exitCode = code ?? (signal === 'SIGINT' ? 130 : 1);
});
process.on('SIGINT', () => backend.kill('SIGINT'));
process.on('SIGTERM', () => backend.kill('SIGTERM'));
