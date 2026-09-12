import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { pythonExecutable, runPython } from './ops/python.mjs';

export function productionCommand(python) {
  return [
    'deploy/runtime_config.py', python, '-m', 'uvicorn', 'bebshax.main:app',
    '--host', '127.0.0.1', '--port', '8000', '--workers', '1', '--timeout-graceful-shutdown', '25',
  ];
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (!['production', 'staging'].includes(process.env.BEBSHAX_ENVIRONMENT)) {
    process.stderr.write('npm start requires BEBSHAX_ENVIRONMENT=production or staging and the settings in docs/SETUP.md.\n');
    process.exitCode = 1;
  } else {
    try {
      runPython(productionCommand(pythonExecutable()));
    } catch (error) {
      process.stderr.write(`${error.message}\n`);
      process.exitCode = 1;
    }
  }
}