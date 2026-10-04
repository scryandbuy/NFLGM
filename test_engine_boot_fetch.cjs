const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { performance } = require('node:perf_hooks');

const source = fs.readFileSync('docs/app.js', 'utf8');
const start = source.indexOf('async function loadEngineFiles(');
const end = source.indexOf('async function bootEngine()', start);
assert.ok(start >= 0 && end > start);
const context = { ENGINE: '/engine/' };
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);

const manifest = {
  build: 'test-stamp',
  modules: Array.from({ length: 20 }, (_, i) => `module_${i}`),
  data: ['ratings.csv', 'names.json', 'players.bin', 'settings.csv'],
};
const files = [...manifest.modules.map(name => `${name}.py`), ...manifest.data];
const missing = 'module_3.py';

function response(file) {
  if (file === missing) return { ok: false };
  const body = Buffer.from(`content:${file}`);
  return {
    ok: true,
    text: async () => body.toString('utf8'),
    arrayBuffer: async () => body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength),
  };
}

function fixture(delay = 0, fail = null) {
  const writes = [], progress = [], requested = [];
  let active = 0, peak = 0;
  const writeFile = (path, data) => {
    writes.push([path, typeof data === 'string' ? data : Buffer.from(data).toString('hex')]);
  };
  async function fetchFile(url) {
    const file = url.slice('/engine/'.length).split('?')[0];
    requested.push(url);
    active++;
    peak = Math.max(peak, active);
    try {
      if (delay) await new Promise(resolve => setTimeout(resolve, delay));
      if (file === fail) throw new Error(`failed:${file}`);
      return response(file);
    } finally {
      active--;
    }
  }
  return { writes, progress, requested, writeFile, fetchFile,
    say: (...args) => progress.push(args), get peak() { return peak; } };
}

async function serialBaseline(manifest, port) {
  let loaded = 0;
  for (const file of files) {
    const result = await port.fetchFile(`/engine/${file}?v=${manifest.build}`);
    if (!result.ok) { port.say('missing ' + file); continue; }
    const data = file.endsWith('.py') || file.endsWith('.json')
      ? await result.text() : new Uint8Array(await result.arrayBuffer());
    port.writeFile('/' + file, data);
    loaded++;
    port.say('loading engine… ' + file, 18 + 62 * loaded / files.length);
  }
}

(async () => {
  const parallel = fixture(3);
  const startParallel = performance.now();
  await context.loadEngineFiles(manifest, { writeFile: parallel.writeFile }, parallel.fetchFile, parallel.say);
  const parallelMs = performance.now() - startParallel;
  const serial = fixture(3);
  const startSerial = performance.now();
  await serialBaseline(manifest, serial);
  const serialMs = performance.now() - startSerial;

  assert.deepEqual(parallel.writes, serial.writes);
  assert.deepEqual(parallel.progress, serial.progress);
  assert.deepEqual(parallel.requested, serial.requested);
  assert.equal(parallel.peak, 8);
  assert.equal(serial.peak, 1);
  assert.equal(parallel.writes.length, files.length - 1);
  assert.ok(parallel.requested.every((url, i) => url === `/engine/${files[i]}?v=test-stamp`));

  const actualManifest = JSON.parse(fs.readFileSync('docs/engine/manifest.json', 'utf8'));
  const full = fixture(1);
  await context.loadEngineFiles(actualManifest, { writeFile: full.writeFile }, full.fetchFile, full.say);
  assert.equal(full.writes.length, actualManifest.modules.length + actualManifest.data.length);
  assert.equal(full.peak, 8);
  assert.deepEqual(full.writes.map(([path]) => path),
    [...actualManifest.modules.map(name => '/' + name + '.py'),
      ...actualManifest.data.map(name => '/' + name)]);

  const failed = fixture(1, 'module_5.py');
  await assert.rejects(
    () => context.loadEngineFiles(manifest, { writeFile: failed.writeFile }, failed.fetchFile, failed.say),
    /failed:module_5.py/,
  );
  assert.deepEqual(failed.writes.map(([path]) => path),
    files.slice(0, 5).filter(file => file !== missing).map(file => '/' + file));
  assert.ok(!failed.writes.some(([path]) => path === '/module_6.py'));

  console.log(`Engine boot fetch: ordered parity, 8-request bound, missing/error parity; synthetic 3 ms responses ${parallelMs.toFixed(1)} ms parallel vs ${serialMs.toFixed(1)} ms serial.`);
})().catch(error => { console.error(error); process.exitCode = 1; });
