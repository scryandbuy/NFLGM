// Real DOM + IndexedDB stress test. Python spending correctness is tested separately.
const fs=require('fs'),http=require('http'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=process.argv[2];
if(!root)throw Error('Pass audit_xp_memory.py output directory');
const source=fs.readFileSync('docs/app.js','utf8');
const chunk=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b));
const script=`
const $=s=>document.querySelector(s);
${chunk('const el =','const esc =')}
let data,view,railDraws=0,notices=0;
const teamTheme=()=>({base:'#203731',accent:'#ffb612'});
const renderRail=()=>railDraws++,secondRow=()=>{},clubNav=()=>[],ovrCell=x=>x;
const openPlayer=()=>{},queueCeilingNoticeCheck=()=>notices++;
const notify=r=>{throw Error(r.why||JSON.stringify(r));};
const py={runPython:code=>{if(code==='SESSION.save()')return JSON.stringify(data);throw Error(code);}};
function pyJSON(code){
 if(code==='SESSION.progression()')return structuredClone(view);
 if(code.startsWith("SESSION.club_act('spend_by_read'")){
   const pid=JSON.parse(code.match(/pid=(.*)\\)/)[1]);
   const row=view.rows.find(r=>r.pid===pid);row.bank--;row.bought++;view.bank_total--;
   data.players[pid].xp=row.bank;
   queueAutosave();return {ok:true};
 }
 throw Error(code);
}
${chunk('let autosaveQueued','function pyJSON')}
${chunk('function idb()','async function loadSave()')}
${chunk('function reportBoard(','function renderProspectCard(')}
async function init(){
 data=await (await fetch('/save')).json();view=await (await fetch('/view')).json();
 renderProgression(view);
 window.target=view.rows.find(r=>r.can_buy&&r.bank>100).pid;
 window.untouched=document.querySelector('table').rows[2];
}
async function cycle(){
 for(let i=0;i<5;i++){
   const row=[...document.querySelectorAll('table tr')].find(r=>r.textContent.includes(view.rows.find(r=>r.pid===target).name));
   row.lastElementChild.querySelector('button').click();
 }
 await saveGame();
 return {railDraws,notices,nodes:document.querySelectorAll('*').length,untouched:untouched.isConnected};
}
`;
const server=http.createServer((req,res)=>{
 if(req.url==='/save'||req.url==='/view'){
  res.setHeader('Content-Type','application/json');
  fs.createReadStream(require('path').join(root,req.url==='/save'?'browser-save.json':'progression.json')).pipe(res);
 }else{
  res.setHeader('Content-Type','text/html');
  res.end('<!doctype html><div id="crumb"></div><nav id="nav"></nav><main id="page"></main><script>'+script+'</script>');
 }
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.evaluate(()=>init());
  const cdp=await page.context().newCDPSession(page);await cdp.send('Performance.enable');
  const heaps=[];let firstNodes;
  for(let i=0;i<20;i++){
   const result=await page.evaluate(()=>cycle());
   assert.equal(result.railDraws,1,'Spend must not rebuild the header');
   assert.equal(result.untouched,true,'unaffected rows must remain in the document');
   firstNodes??=result.nodes;assert.equal(result.nodes,firstNodes);
   await cdp.send('HeapProfiler.collectGarbage');
   const metrics=await cdp.send('Performance.getMetrics');
   heaps.push(metrics.metrics.find(m=>m.name==='JSHeapUsedSize').value);
  }
  const durable=await page.evaluate(async()=>{
   const db=await idb();
   return new Promise((resolve,reject)=>{
    const tx=db.transaction('saves','readonly'),req=tx.objectStore('saves').get('main');
    tx.oncomplete=()=>{db.close();resolve(JSON.parse(req.result).players[target].xp===view.rows.find(r=>r.pid===target).bank);};
    tx.onerror=()=>reject(tx.error);
   });
  });
  assert.ok(durable);assert.deepEqual(errors,[]);
  assert.ok(heaps.at(-1)-heaps[2]<40e6,'retained heap must settle instead of growing per click');
  const report={xp_clicks:100,large_save_writes:20,dom_nodes:firstNodes,
    first_heap_mb:+(heaps[0]/1e6).toFixed(1),last_heap_mb:+(heaps.at(-1)/1e6).toFixed(1),
    max_sampled_retained_heap_mb:+(Math.max(...heaps)/1e6).toFixed(1),durable,errors};
  fs.writeFileSync(require('path').join(root,'browser-report.json'),JSON.stringify(report,null,2));
  console.log(report);
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
