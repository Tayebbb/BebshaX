import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));

export function pythonExecutable(projectRoot = root, platform = process.platform, exists = existsSync) {
  const executable = path.join(projectRoot, '.venv', ...(platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python']));
  if (!exists(executable)) throw new Error('Missing project virtual environment. Follow docs/SETUP.md; no global Python fallback is used.');
  return executable;
}

export function runPython(arguments_) {
  try {
    const child = spawn(pythonExecutable(), arguments_, {
      cwd: root, shell: false, stdio: 'inherit', env: { ...process.env, PYTHONUNBUFFERED: '1' },
    });
    const interrupt = () => child.kill('SIGINT');
    const terminate = () => child.kill('SIGTERM');
    process.once('SIGINT', interrupt);
    process.once('SIGTERM', terminate);
    child.once('error', () => {
      process.stderr.write('The project Python command could not start.\n');
      process.exitCode = 1;
    });
    child.once('close', (code, signal) => {
      process.removeListener('SIGINT', interrupt);
      process.removeListener('SIGTERM', terminate);
      process.exitCode = code ?? (signal === 'SIGINT' ? 130 : 1);
    });
    return child;
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
    return null;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv.length < 3) {
    process.stderr.write('Usage: node scripts/ops/python.mjs [PYTHON ARGUMENTS...]\n');
    process.exitCode = 2;
  } else {
    runPython(process.argv.slice(2));
  }
}