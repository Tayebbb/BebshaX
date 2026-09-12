const { spawnSync } = require("node:child_process");
const { randomUUID } = require("node:crypto");
const { mkdirSync, writeFileSync } = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../../../..");
const [label, ...args] = process.argv.slice(2);
if (!label || !/^[a-z0-9-]+$/.test(label) || args.length === 0) {
  throw new Error("Provide a lowercase run label followed by scoped pytest arguments.");
}
const output = path.join(root, ".tmp", `owned-${label}`);
const invocationId = randomUUID();
const runDirectory = path.join(output, invocationId);
const temporary = path.join(runDirectory, "temporary");
mkdirSync(temporary, { recursive: true });
const code = [
  "import sys, tempfile",
  "assert sys.version_info[:2] == (3, 12), 'The project Python 3.12 venv is required'",
  "tempfile.tempdir = sys.argv.pop(1)",
  "from pydantic_settings import DotEnvSettingsSource",
  "DotEnvSettingsSource._read_env_files = lambda source: {}",
  "import pytest",
  "raise SystemExit(pytest.main(sys.argv[1:]))",
].join("; ");
const started = Date.now();
writeFileSync(path.join(runDirectory, "started.json"), JSON.stringify({ invocationId, launcherPid: process.pid, started, args }));
const result = spawnSync(path.join(root, ".venv", "Scripts", "python.exe"), [
  "-X", "utf8", "-c", code, temporary, ...args, "--no-cov", "--tb=short",
  `--basetemp=${path.join(runDirectory, "fixtures")}`,
  `--junitxml=${path.join(runDirectory, "junit.xml")}`,
], { cwd: root, encoding: "utf8", maxBuffer: 8 * 1024 * 1024 });
writeFileSync(path.join(runDirectory, "pytest.log"), `${result.stdout || ""}${result.stderr || ""}`);
const receipt = {
  invocationId, runDirectory, launcherPid: process.pid, childPid: result.pid,
  status: result.status, signal: result.signal, error: result.error?.message,
  elapsedMs: Date.now() - started, args,
};
writeFileSync(path.join(runDirectory, "result.json"), JSON.stringify(receipt, null, 2));
writeFileSync(path.join(output, "result.json"), JSON.stringify(receipt, null, 2));
process.stdout.write(`${JSON.stringify(receipt)}\n${result.stdout || ""}${result.stderr || ""}`);
process.exitCode = result.status ?? 1;