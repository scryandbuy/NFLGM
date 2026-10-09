// Fresh isolated Chromium process per variant. The user's browser is untouched.
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict');
const {execFileSync}=require('child_process');
const {chromium}=require('playwright');
const input=process.argv[2],out=process.argv[3];if(!input||!out)throw Error('Pass save and output directory');
const app=fs.readFileSync('docs/app.js','utf8');
const script=`let py;const ENGINE='/engine/',say=()=>{};${app.slice(app.indexOf('async function loadEngineFiles('),app.indexOf('function cutPenaltyText('))};`;
const sizing=fs.readFileSync('audit_retained_memory.py','utf8');
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost');
 if(url.pathname==='/save'){res.setHeader('Content-Type','application/json');fs.createReadStream(input).pipe(res);}
 else if(url.pathname.startsWith('/engine/')){
  const file=path.join('docs','engine',path.basename(url.pathname));
  if(!fs.existsSync(file)){res.writeHead(404);res.end();return;}
  fs.createReadStream(file).pipe(res);
 }else{res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Retained memory audit</title>');}
});
const mib=x=>+(x/1048576).toFixed(2);
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const reports=[];
 for(const mode of ['baseline','shared']){
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
   const page=await browser.newPage();
   await page.goto(`http://127.0.0.1:${server.address().port}`);await page.addScriptTag({content:script});
   await page.evaluate(()=>bootEngine());
   if(mode==='baseline')await page.evaluate(()=>py.runPython('import shared_json\nshared_json.load = json.load\nshared_json.loads = json.loads'));
   console.log(mode+': engine ready');
   const start=Date.now();
   await page.evaluate(async()=>{const file=await(await fetch('/save')).blob();await loadSessionFromBlob(file);py.runPython('import gc; gc.collect()');});
   const loadMs=Date.now()-start;
   const cdp=await page.context().newCDPSession(page);await cdp.send('HeapProfiler.collectGarbage');
   const wasmBytes=await page.evaluate(()=>py._module.HEAPU8.buffer.byteLength);
   const root=await browser.newBrowserCDPSession();
   const info=await root.send('SystemInfo.getProcessInfo');
   const ids=info.processInfo.filter(p=>p.type==='renderer').map(p=>Number(p.id));
   assert.ok(ids.length&&ids.every(Number.isSafeInteger));
   const rows=JSON.parse(execFileSync('powershell.exe',['-NoProfile','-Command',`Get-Process -Id ${ids.join(',')} | Select-Object Id,WorkingSet64,PrivateMemorySize64 | ConvertTo-Json -Compress`],{encoding:'utf8'}));
   const processes=Array.isArray(rows)?rows:[rows];
   const working=processes.reduce((n,p)=>n+p.WorkingSet64,0);
   const privateBytes=processes.reduce((n,p)=>n+p.PrivateMemorySize64,0);
   // Take OS measurements before the object-graph inspection's temporary seen set.
   await page.evaluate(code=>py.FS.writeFile('/audit_retained_memory.py',code),sizing);
   const retained=await page.evaluate(()=>py.runPython('from audit_retained_memory import retained_size\nretained_size(SESSION)'));
   const fingerprint=await page.evaluate(()=>py.runPython(`
import hashlib
h=hashlib.sha256()
for piece in json.JSONEncoder(default=S.LG._session_json_default,separators=(',', ':')).iterencode(SESSION._save_data()):
    h.update(piece.encode())
h.hexdigest()
`));
   const report={mode,build_id:await page.evaluate(()=>window.ENGINE_BUILD),load_ms:loadMs,wasm_capacity_mib:mib(wasmBytes),renderer_working_set_mib:mib(working),renderer_private_bytes_mib:mib(privateBytes),retained_session_mib:mib(retained),portable_export_sha256:fingerprint};
   reports.push(report);console.log(report);
  }finally{await browser.close();}
 }
 assert.equal(reports[0].portable_export_sha256,reports[1].portable_export_sha256);
 assert.ok(reports[1].retained_session_mib<reports[0].retained_session_mib*.85,'retained franchise objects must materially shrink');
 fs.writeFileSync(path.join(out,'browser-retained.json'),JSON.stringify(reports,null,2));
 server.close();
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
