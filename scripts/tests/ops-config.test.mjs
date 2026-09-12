import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const root = new URL('../../', import.meta.url);
const read = (path) => readFileSync(new URL(path, root), 'utf8');

test('compose never re-enables a retired host inference provider', () => {
  const compose = read('docker-compose.yml');
  assert.doesNotMatch(compose, /ollama|host\.docker\.internal|host-gateway/i);
});

test('compose requires an explicit opt-in to demo mode', () => {
  const compose = read('docker-compose.yml');
  assert.doesNotMatch(compose, /BEBSHAX_DEMO_MODE[^\n]*true/i);
});

test('compose forwards an optional processing policy without preapproving any providers', () => {
  const compose = read('docker-compose.yml');
  assert.match(compose, /^\s+BEBSHAX_REMOTE_PROCESSING_POLICY:\s*$/m);
  assert.doesNotMatch(compose, /synthetic_providers|private_providers|synthetic_openrouter_upstreams|private_openrouter_upstreams/);
});

test('API image consumes hash locks and the reviewed immutable Python image', () => {
  const dockerfile = read('apps/backend/Dockerfile');
  const python = JSON.parse(read('deploy/images.json')).images.python;
  for (const from of dockerfile.split('\n').filter((line) => line.startsWith('FROM '))) {
    assert.ok(from.includes(`python:${python.tag}@${python.digest}`));
  }
  assert.match(dockerfile, /COPY deploy\/python\/runtime\.lock/);
  assert.match(dockerfile, /--require-hashes/);
  assert.match(dockerfile, /--no-build-isolation/);
  assert.match(dockerfile, /USER 10001:10001/);
  assert.equal(dockerfile.match(/^CMD\s/gm)?.length, 1);
  assert.equal(dockerfile.match(/^ENTRYPOINT\s/gm)?.length, 1);
  assert.match(dockerfile, /COPY deploy\/runtime_probe\.py/);
  assert.equal(read('apps/backend/requirements.txt').trim(), '-r requirements.lock');
});