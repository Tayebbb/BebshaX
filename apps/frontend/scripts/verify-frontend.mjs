import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdirSync, openSync, closeSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(resolve(frontend, 'package.json'));
const [mode = 'test', ...files] = process.argv.slice(2);
if (!['test', 'build', 'theme:check', 'typecheck'].includes(mode) || files.some((file) => !/^tests\/[\w./-]+\.test\.tsx?$/.test(file) || file.includes('..'))) {
  throw new Error('Usage: verify-frontend.mjs test [tests/name.test.tsx] | build | theme:check | typecheck');
}
const outputDirectory = resolve(frontend, '.tmp');
mkdirSync(outputDirectory, { recursive: true });
const runId = `${mode.replace(':', '-')}-${Date.now()}-${randomUUID().slice(0, 8)}`;
const reportPath = resolve(outputDirectory, `${runId}.json`);
const logPath = resolve(outputDirectory, `${runId}.log`);
const log = openSync(logPath, 'w');
const args = ['--prefix', frontend, 'run', mode];
if (mode === 'test') {
  const major = Number(require('vitest/package.json').version.split('.')[0]);
  args.push('--', ...files, '--maxWorkers=1', '--no-file-parallelism');
  if (major < 4) args.push('--minWorkers=1');
  args.push('--reporter=json', `--outputFile=${reportPath}`);
}
const started = performance.now();
const isWindows = process.platform === 'win32';
const commandArgs = isWindows
  ? ['/d', '/s', '/c', `"npm.cmd ${args.map((argument) => `"${argument}"`).join(' ')}"`]
  : args;
const result = spawnSync(mode === 'typecheck' ? process.execPath : isWindows ? 'cmd.exe' : 'npm',
  mode === 'typecheck' ? [require.resolve('typescript/bin/tsc'), '--noEmit', '--project', resolve(frontend, 'tsconfig.json')] : commandArgs, {
  cwd: frontend,
  env: { ...process.env, BEBSHAX_FRONTEND_VERIFY: '1' },
  windowsVerbatimArguments: isWindows && mode !== 'typecheck',
  detached: true,
  windowsHide: true,
  stdio: ['ignore', log, log],
});
closeSync(log);
const summary = { runId, command: ['npm', ...args].join(' '), exitCode: result.status, durationMs: Math.round(performance.now() - started), logPath };
if (mode === 'test' && existsSync(reportPath)) {
  const report = JSON.parse(readFileSync(reportPath, 'utf8'));
  Object.assign(summary, {
    passed: report.numPassedTests,
    failed: report.numFailedTests,
    skipped: report.numPendingTests,
    files: report.testResults.length,
    suiteFailures: report.testResults.filter((suite) => suite.status === 'failed' && suite.message)
      .map((suite) => ({ name: suite.name, message: suite.message.slice(0, 1800) })),
    success: report.success && result.status === 0,
    failures: report.testResults.flatMap((suite) => suite.assertionResults.filter((test) => test.status === 'failed')
      .map((test) => ({ name: test.fullName, messages: test.failureMessages.map((message) => message.slice(0, 1200)) }))),
  });
} else {
  summary.output = readFileSync(logPath, 'utf8').slice(-10000);
}
writeFileSync(resolve(outputDirectory, `last-${mode.replace(':', '-')}.json`), JSON.stringify(summary, null, 2));
process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
process.exitCode = result.status ?? 1;