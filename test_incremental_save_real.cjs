// Pass audit_incremental_save.py's output directory. Uses isolated real IndexedDB.
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=process.argv[2];if(!root)throw Error('Pass incremental audit output directory');
const source=fs.readFileSync('docs/app.js','utf8');
const script=`
let autosaveQueued=false;
const py={runPython(){throw Error('Unexpected persistence failure');}};
${source.slice(source.indexOf('function idb()'),source.indexOf('// ---------------------------------------------------------------- the rail'))}
async function runReal(){
 let checkpoint=await(await fetch('/checkpoint.json')).json();
 await queueSave('snapshot',checkpoint);checkpoint=null;
 const deltas=await(await fetch('/deltas.json')).json();
 for(const delta of deltas)await queueSave('snapshot',delta);
 let saved=await loadSave();
 const bytes=new Uint8Array(await saved.text.arrayBuffer());
 const digest=await crypto.subtle.digest('SHA-256',bytes);
 const hash=[...new Uint8Array(digest)].map(v=>v.toString(16).padStart(2,'0')).join('');
 const expected=await(await fetch('/expected.json')).json();
 if(hash!==expected.sha256)throw Error('Browser readback differs from full export');
 if(bytes.length!==expected.bytes)throw Error('Browser save size differs from export');
 return {full_export_bytes:bytes.length,readback_exact:true,delta_writes:deltas.length,
  delta_payload_bytes:deltas.map(d=>JSON.stringify(d).length),records:Object.keys(saved.snapshot.hashes).length};
}
`;
const server=http.createServer((req,res)=>{
 if(['/checkpoint.json','/deltas.json','/expected.json'].includes(req.url)){
  res.setHeader('Content-Type','application/json');fs.createReadStream(path.join(root,req.url.slice(1))).pipe(res);
 }else{res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Save parity test</title>');}
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);await page.addScriptTag({content:script});
  const report=await page.evaluate(()=>runReal());assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(root,'browser-parity.json'),JSON.stringify(report,null,2));console.log(report);
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
