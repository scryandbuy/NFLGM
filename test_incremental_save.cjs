// Isolated browser persistence test: real IndexedDB, no user's browser storage.
const fs=require('fs'),http=require('http'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync('docs/app.js','utf8');
const chunk=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b));
const script=`
let resets=0,captures=0,nextSnapshot;
const py={runPython:code=>{
 if(code==='SESSION.reset_incremental()'){resets++;return;}
 if(code==='SESSION.save_incremental()'){captures++;return JSON.stringify(nextSnapshot);}
 throw Error(code);
}};
const notify=()=>{};
${chunk('let autosaveQueued','function pyJSON')}
${chunk('function idb()','// ---------------------------------------------------------------- the rail')}
const assert=(v,m)=>{if(!v)throw Error(m);};
function snap(revision,base,values,reset=false,epoch='franchise'){
 const puts={};for(const [k,v] of Object.entries(values))puts[JSON.stringify([k])]={hash:JSON.stringify(v),text:JSON.stringify(v)};
 if(reset) puts['@roots']={hash:'roots',text:JSON.stringify(['xp','trade','archive'].map(k=>[k,'value',null]))};
 return {format:1,epoch,revision,base,marker:'week4',reset,puts,deletes:[]};
}
const read=async()=>JSON.parse((await loadSave()).text);
async function run(){
 const results=[];
 await queueSave('full',JSON.stringify({legacy:true}));
 await queueSave('journal',{actions:[1]});
 let saved=await loadSave();assert(JSON.parse(saved.text).legacy&&saved.journal.actions[0]===1,'legacy load');results.push('legacy save + journal');
 const archive='historical-data-'.repeat(200000);
 await queueSave('snapshot',snap(1,0,{xp:100,trade:null,archive},true));
 saved=await loadSave();assert(JSON.parse(saved.text).archive===archive&&!saved.journal,'atomic migration');results.push('legacy migration');
 const originalWrite=writeSnapshot;
 let unblock;const gate=new Promise(r=>unblock=r);let entered=false;
 writeSnapshot=async(db,p)=>{if(!entered){entered=true;await gate;}return originalWrite(db,p);};
 const a=queueSave('snapshot',snap(2,1,{xp:90}));
 const b=queueSave('snapshot',snap(3,2,{xp:80,trade:{from:'GB',to:'MIN',pick:2}}));
 const c=queueSave('snapshot',snap(4,3,{xp:100}));
 assert(pendingSaves.length===1,'bounded pending snapshots');
 assert(pendingSaves[0].value.base===2&&pendingSaves[0].value.revision===4,'merged revision chain');
 unblock();await Promise.all([a,b,c]);writeSnapshot=originalWrite;
 let state=await read();assert(state.xp===100&&state.trade.pick===2&&state.archive===archive,'reversion/transaction side effects');results.push('rapid clicks + reversion + combined writes');
 // Abort after scheduling a record write: neither that record nor metadata may commit.
 let aborted=false;
 writeSnapshot=async(db,p)=>{
  const wrapped={transaction(...args){const tx=db.transaction(...args),objectStore=tx.objectStore.bind(tx);
   tx.objectStore=name=>{const store=objectStore(name),put=store.put.bind(store);store.put=(...args)=>{const r=put(...args);if(!aborted){aborted=true;tx.abort();}return r;};return store;};return tx;}};
  return originalWrite(wrapped,p);
 };
 const outcomes=await Promise.allSettled([
  queueSave('snapshot',snap(5,4,{xp:50})),queueSave('snapshot',snap(6,5,{trade:{pick:1}})),queueSave('journal',{actions:[2]})]);
 assert(outcomes.every(r=>r.status==='rejected'),'failed dependent saves must all reject');
 writeSnapshot=originalWrite;
 state=await read();assert(state.xp===100&&state.trade.pick===2,'aborted transaction preserved previous snapshot');
 assert(resets===1&&saveNeedsCheckpoint&&autosaveQueued,'failure marks dirty and requires checkpoint');
 await queueSave('snapshot',snap(1,0,{xp:50,trade:{pick:1},archive},true,'retry'));
 assert(!saveNeedsCheckpoint&&(await read()).xp===50,'full recovery checkpoint');results.push('atomic abort + dependent cancellation + recovery');
 await queueSave('journal',{actions:[1,2]});assert((await loadSave()).journal.actions.length===2,'live journal written');
 await queueSave('snapshot',snap(2,1,{xp:40},false,'retry'));
 assert(!(await loadSave()).journal,'snapshot supersedes journal');results.push('live journal ordering');
 // Exercise actual saveGame/flush wiring, including a visibility/pagehide capture.
 nextSnapshot=snap(3,2,{xp:30},false,'retry');queueAutosave();await flushAutosave();
 assert(captures===1&&(await read()).xp===30,'autosave calls incremental capture once');results.push('autosave flush');
 const bad=await Promise.allSettled([queueSave('snapshot',snap(4,1,{xp:20},false,'retry'))]);
 assert(bad[0].status==='rejected'&&saveConflict,'stale base rejected');
 let blocked=false;try{saveGame();}catch(e){blocked=true;}assert(blocked&&(await read()).xp===30,'conflict cannot overwrite another tab');results.push('stale revision protection');
 saveConflict=false;
 await queueSave('snapshot',snap(1,0,{xp:9,trade:null,archive:'new game'},true,'new-franchise'));
 saved=await loadSave();assert(JSON.parse(saved.text).archive==='new game'&&saved.snapshot.epoch==='new-franchise','new franchise replacement');
 let release;const hold=new Promise(r=>release=r);let first=true;
 writeSnapshot=async(db,p)=>{if(first){first=false;await hold;}return originalWrite(db,p);};
 const advanceWrites=[queueSave('snapshot',snap(2,1,{xp:8},false,'new-franchise')),
  queueSave('snapshot',snap(3,2,{xp:7},false,'new-franchise')),
  queueSave('snapshot',snap(4,3,{xp:6,trade:null,archive:'next week'},true,'new-franchise'))];
 release();await Promise.all(advanceWrites);writeSnapshot=originalWrite;
 assert((await read()).archive==='next week','checkpoint coalesced across pending delta');results.push('queued calendar checkpoint');
 const db=await idb();await new Promise((resolve,reject)=>{const tx=db.transaction('saves','readwrite');tx.objectStore('saves').delete('chunk:'+JSON.stringify(['xp']));tx.oncomplete=resolve;tx.onerror=reject;});db.close();
 let incomplete=false;try{await loadSave();}catch(e){incomplete=true;}assert(incomplete,'missing record fails visibly');results.push('new franchise + incomplete snapshot detection');
 return {checks:results,errors:[],captures,resets};
}
`;
const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Persistence test</title>');});
new (require('vm').Script)(script);
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);await page.addScriptTag({content:script});
  assert.deepEqual(errors,[]);
  const report=await page.evaluate(()=>run());assert.deepEqual(errors,[]);console.log(JSON.stringify(report,null,2));
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
