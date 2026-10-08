// Isolated browser storage; never opens or alters the user's franchise database.
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict');
const {execFileSync}=require('child_process');
const {chromium}=require('playwright');
const root=process.argv[2];if(!root)throw Error('Pass audit_save_memory.py output directory');
const old=execFileSync('git',['show','aab7593:docs/app.js'],{encoding:'utf8',maxBuffer:5e6});
const current=fs.readFileSync('docs/app.js','utf8');
const slice=s=>s.slice(s.indexOf('function idb()'),s.indexOf('// ---------------------------------------------------------------- the rail'));
const server=http.createServer((req,res)=>{
 if(req.url==='/checkpoint'){res.setHeader('Content-Type','application/json');fs.createReadStream(path.join(root,'legacy.ndjson')).pipe(res);}
 else{res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Save memory audit</title>');}
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const reports=[];
 try{
  for(const [mode,source] of [['legacy',old],['bounded',current]]){
   const context=await browser.newContext(),page=await context.newPage();
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(`http://127.0.0.1:${server.address().port}`);
   await page.addScriptTag({content:`let autosaveQueued=false;const py={runPython(){throw Error('Unexpected failure');}};${slice(source)}`});
   await page.evaluate(async()=>{let checkpoint=await(await fetch('/checkpoint')).json();await queueSave('snapshot',checkpoint);checkpoint=null;});
   const cdp=await context.newCDPSession(page);await cdp.send('Performance.enable');
   const heap=async()=> (await cdp.send('Performance.getMetrics')).metrics.find(x=>x.name==='JSHeapUsedSize').value;
   await cdp.send('HeapProfiler.collectGarbage');const before=await heap();
   let running=true;const samples=[];
   const sampling=(async()=>{while(running){samples.push(await heap());await new Promise(r=>setTimeout(r,30));}})();
   const start=Date.now();await page.evaluate(async()=>{window.auditSaved=await loadSave();});const ms=Date.now()-start;
   running=false;await sampling;samples.push(await heap());
   await cdp.send('HeapProfiler.collectGarbage');const retained=await heap();
   const result=await page.evaluate(async()=>{
    const bytes=typeof auditSaved.text==='string'?new TextEncoder().encode(auditSaved.text):new Uint8Array(await auditSaved.text.arrayBuffer());
    const hash=await crypto.subtle.digest('SHA-256',bytes);
    return {bytes:bytes.length,sha256:[...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('')};
   });
   assert.deepEqual(result,JSON.parse(fs.readFileSync(path.join(root,'expected.json'),'utf8')));
   assert.deepEqual(errors,[]);
   const mib=x=>+(x/1048576).toFixed(2);
   reports.push({mode,load_ms:ms,before_js_heap_mib:mib(before),peak_sampled_js_heap_mib:mib(Math.max(...samples)),retained_js_heap_mib:mib(retained),byte_identical:true});
   console.log(reports.at(-1));await context.close();
  }
  assert.ok(reports[1].retained_js_heap_mib<reports[0].retained_js_heap_mib/2,'resume must release large JavaScript strings');
  fs.writeFileSync(path.join(root,'browser-memory.json'),JSON.stringify(reports,null,2));
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
