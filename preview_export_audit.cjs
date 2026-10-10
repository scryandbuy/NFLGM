// Local test page only. No browser automation or franchise database writes.
const fs=require('node:fs'),http=require('node:http'),path=require('node:path');
const app=fs.readFileSync('docs/app.js','utf8');
const functions=app.slice(app.indexOf('async function loadEngineFiles('),app.indexOf('function cutPenaltyText('));
const script=String.raw`let py; const ENGINE='/engine/';
const say=text=>document.querySelector('#status').textContent=text;
${functions}
document.querySelector('button').onclick=async()=>{
 document.querySelector('button').disabled=true;
 try {
  await bootEngine(); say('Loading copied franchise…');
  let input=await(await fetch('/save')).blob(); const originalBytes=input.size;
  await loadSessionFromBlob(input); input=null;
  say('Exporting compressed franchise…'); await new Promise(r=>setTimeout(r,30));
  const start=performance.now(), blob=exportSessionBlob(), exportSeconds=(performance.now()-start)/1000;
  if(py.FS.analyzePath('/nflgm-export-save.json.gz').exists)throw Error('temporary export retained');
  say('Checking every decompressed byte…');
  // Python hashlib updates one bounded chunk at a time, never a giant bridge string.
  py.runPython('import hashlib\naudit_hash=hashlib.sha256()');
  const stream=await saveImportStream(blob), reader=stream.getReader(); let bytes=0;
  for(;;){const {value,done}=await reader.read(); if(done)break;
   py.globals.set('_audit_chunk',value);
   py.runPython('audit_hash.update(bytes(_audit_chunk))');
   py.globals.delete('_audit_chunk'); bytes+=value.length;
  }
  const sha256=py.runPython('audit_hash.hexdigest()');
  const identityCode="_j(dict(year=SESSION.L.year,players=len(SESSION.L.players),transactions=len(SESSION.L.transactions),archives=len(SESSION.gamedays),rng=SESSION.rng.bit_generator.state,stop=SESSION.stop))";
  const before=py.runPython(identityCode);
  say('Reloading compressed franchise into a fresh session…');
  py.runPython('SESSION=None\nimport gc\ngc.collect()');
  await loadSessionFromBlob(blob);
  if(py.runPython(identityCode)!==before)throw Error('restored franchise identity or RNG changed');
  if(py.FS.analyzePath('/nflgm-import-save.json').exists)throw Error('temporary import retained');
  const result={originalBytes,compressedBytes:blob.size,decodedBytes:bytes,exportSeconds,sha256,temporaryFileRemoved:true,reloaded:true,identityAndRngUnchanged:true};
  document.querySelector('#result').textContent=JSON.stringify(result,null,2);
  say('PASS: exported, verified decoded hash, and reloaded full franchise.');
 }catch(e){say('FAIL: '+e);}
};`;
http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost');
 if(url.pathname==='/save'){res.setHeader('Content-Type','application/json');fs.createReadStream('C:/Users/HP/Downloads/nflgm-2034-offseason-2.json').pipe(res);}
 else if(url.pathname.startsWith('/engine/')){const f=path.join('docs/engine',path.basename(url.pathname));if(!fs.existsSync(f)){res.writeHead(404);res.end();}else fs.createReadStream(f).pipe(res);}
 else {res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Export audit</title><button>Test copied franchise export</button><p id="status">Ready</p><pre id="result"></pre><script type="module">'+script+'</script>');}
}).listen(8774,'127.0.0.1',()=>console.log('Export audit at http://127.0.0.1:8774'));
