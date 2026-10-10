// Exercise production transfer functions using real Blob/compression streams.
const fs = require('node:fs'), vm = require('node:vm'), zlib = require('node:zlib');
const assert = require('node:assert/strict');
const source = fs.readFileSync('docs/app.js', 'utf8');
const code = source.slice(source.indexOf('async function saveImportStream('), source.indexOf('async function bootEngine('));
const original = Buffer.from(JSON.stringify({name:'René 🏈', history:Array.from({length:50000}, (_,i)=>({week:i,text:'all franchise history retained'}))}));
const compressed = zlib.gzipSync(original);
let files = new Map(), loaded, maxRead = 0, failWrite = false, failExport = false;
const ctx = {Blob, Uint8Array, DecompressionStream, py:{
  runPython(command) {
    if (command.includes('export_file')) {
      files.set('/nflgm-export-save.json.gz', compressed);
      if (failExport) throw Error('export interrupted');
    } else if (command.includes('Session.load_file')) {
      loaded = Buffer.concat(files.get('/nflgm-import-save.json'));
      JSON.parse(loaded);
    } else throw Error('Unexpected command: '+command);
  },
  FS:{
    open(path, mode) { if (mode === 'w+') files.set(path, []); return {path, offset:0}; },
    close() {},
    read(file, dest, offset, size) {
      maxRead = Math.max(maxRead, size);
      const bytes = files.get(file.path).subarray(file.offset, file.offset + size);
      dest.set(bytes, offset); file.offset += bytes.length; return bytes.length;
    },
    write(file, bytes) { if (failWrite) throw Error('disk full'); files.get(file.path).push(Buffer.from(bytes)); },
    analyzePath(path) { return {exists:files.has(path)}; },
    unlink(path) { files.delete(path); },
  }
}};
vm.createContext(ctx); vm.runInContext(code, ctx);
(async()=>{
  const blob = ctx.exportSessionBlob();
  assert.deepEqual(Buffer.from(await blob.arrayBuffer()), compressed);
  assert.equal(files.size, 0); assert.ok(maxRead <= 256*1024);
  for (const input of [new Blob([original]), new Blob([compressed]), original.toString()]) {
    await ctx.loadSessionFromBlob(input);
    assert.deepEqual(loaded, original); assert.equal(files.size, 0);
  }
  for (const invalid of [new Blob([compressed.subarray(0, -8)]), new Blob(['bad json'])]) {
    await assert.rejects(ctx.loadSessionFromBlob(invalid)); assert.equal(files.size, 0);
  }
  failWrite = true;
  await assert.rejects(ctx.loadSessionFromBlob(blob), /disk full/); assert.equal(files.size, 0);
  failExport = true;
  assert.throws(()=>ctx.exportSessionBlob(), /export interrupted/); assert.equal(files.size, 0);
  console.log('Compressed and legacy imports match byte-for-byte; bounded export transfer and failure cleanup pass.');
})().catch(e=>{console.error(e);process.exitCode=1;});
