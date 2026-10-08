// Full browser engine, temporary browser profile and read-only exported input.
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const input=process.argv[2],out=process.argv[3];if(!input||!out)throw Error('Pass save and report paths');
const source=fs.readFileSync('docs/app.js','utf8');
const chunk=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b));
const script=`let py;const ENGINE='/engine/',say=()=>{},notify=()=>{};
${chunk('async function loadEngineFiles(', 'function cutPenaltyText(')}
${chunk('let autosaveQueued', 'function pyJSON(')}
${chunk('function idb()', '// ---------------------------------------------------------------- the rail')}
`;
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost');
 if(url.pathname==='/save'){res.setHeader('Content-Type','application/json');fs.createReadStream(input).pipe(res);}
 else if(url.pathname.startsWith('/engine/')){
  const name=path.basename(url.pathname);const file=path.join('docs','engine',name);
  if(!fs.existsSync(file)){res.writeHead(404);res.end();return;}
  fs.createReadStream(file).pipe(res);
 }else{res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Large save runtime test</title>');}
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage();page.on('console',m=>{if(m.type()==='error')console.error(m.text());});
  await page.goto(`http://127.0.0.1:${server.address().port}`);await page.addScriptTag({content:script});
  await page.evaluate(()=>bootEngine());console.log('Browser Python engine loaded.');
  await page.evaluate(async()=>{const blob=await(await fetch('/save')).blob();await loadSessionFromBlob(blob);});
  console.log('Large exported franchise imported.');
  const initial=await page.evaluate(()=>JSON.parse(py.runPython(`json.dumps(dict(year=SESSION.L.year,players=len(SESSION.L.players),transactions=len(SESSION.L.transactions),archives=len(SESSION.gamedays),rng=json.dumps(SESSION.rng.bit_generator.state,sort_keys=True)))`)));
  // Hash the portable export incrementally; do not create another huge string
  // merely to test the new bounded transfer.
  await page.evaluate(()=>py.runPython(`
import hashlib
def audit_digest():
    h = hashlib.sha256()
    for piece in json.JSONEncoder(default=S.LG._session_json_default,separators=(',', ':')).iterencode(SESSION._save_data()):
        h.update(piece.encode())
    return h.hexdigest()
audit_expected = audit_digest()
`));
  const expected=await page.evaluate(()=>py.runPython('audit_expected'));
  await page.evaluate(()=>saveGame());console.log('Batched checkpoint persisted.');
  const readback=await page.evaluate(async()=>{
   window.auditSaved=await loadSave();
   const hash=await crypto.subtle.digest('SHA-256',await auditSaved.text.arrayBuffer());
   return {sha256:[...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join(''),bytes:auditSaved.text.size};
  });
  assert.equal(readback.sha256,expected);
  await page.evaluate(()=>{py.runPython('SESSION = None\nimport gc\ngc.collect()');});
  await page.evaluate(async()=>{
   await loadSessionFromBlob(auditSaved.text);
   py.globals.set('_META',JSON.stringify(auditSaved.snapshot));
   try{py.runPython('SESSION.resume_incremental(json.loads(_META))');}finally{py.globals.delete('_META');}
   window.auditSaved=null;
  });
  console.log('Browser snapshot reloaded.');
  const resumed=await page.evaluate(()=>JSON.parse(py.runPython(`json.dumps(dict(year=SESSION.L.year,players=len(SESSION.L.players),transactions=len(SESSION.L.transactions),archives=len(SESSION.gamedays),rng=json.dumps(SESSION.rng.bit_generator.state,sort_keys=True)))`)));
  assert.deepEqual(resumed,initial);
  const heaps=[];
  const cdp=await page.context().newCDPSession(page);await cdp.send('Performance.enable');
  for(let i=0;i<3;i++){
   await page.evaluate(()=>saveGame());
   await cdp.send('HeapProfiler.collectGarbage');
   const metrics=await cdp.send('Performance.getMetrics');
   heaps.push(+(metrics.metrics.find(x=>x.name==='JSHeapUsedSize').value/1048576).toFixed(2));
  }
  assert.ok(heaps[2]-heaps[0]<10,'unchanged saves must not retain new full copies');
  assert.equal(await page.evaluate(()=>py.FS.analyzePath('/nflgm-import-save.json').exists),false);
  const {rng,...counts}=initial;
  const report={...counts,rng_unchanged:true,portable_export_byte_identical:true,readback_bytes:readback.bytes,import_resume_equal:true,temporary_file_removed:true,repeated_save_js_heap_mib:heaps};
  fs.writeFileSync(out,JSON.stringify(report,null,2));console.log(report);
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
