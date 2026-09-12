import { createInterface } from 'node:readline';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const verifier = fileURLToPath(new URL('./verify-frontend.mjs', import.meta.url));
const input = createInterface({ input: process.stdin, output: process.stdout, terminal: false });
process.stdout.write('Frontend verification worker ready. Send a JSON argument array or "quit".\n');
input.on('line', (line) => {
  if (line.trim() === 'quit') {
    input.close();
    return;
  }
  try {
    const args = JSON.parse(line);
    if (!Array.isArray(args) || args.some((argument) => typeof argument !== 'string')) {
      throw new Error('Expected a JSON array of verifier arguments');
    }
    const result = spawnSync(process.execPath, [verifier, ...args], { stdio: ['ignore', 'inherit', 'inherit'] });
    process.stdout.write(`Verification process exit: ${result.status ?? 'unavailable'}\n`);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : 'Invalid verification request'}\n`);
  }
});