// Verify the codec in the same Python/WASM runtime shipped by the game.
const fs=require('fs'),http=require('http'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync('incremental_save.py','utf8');
const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Python codec compatibility</title>');});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage();await page.goto(`http://127.0.0.1:${server.address().port}`);
  const report=await page.evaluate(async source=>{
   const {loadPyodide}=await import('https://cdn.jsdelivr.net/pyodide/v0.29.5/full/pyodide.mjs');
   const py=await loadPyodide({indexURL:'https://cdn.jsdelivr.net/pyodide/v0.29.5/full/'});
   py.runPython(source);
   return JSON.parse(py.runPython(`
import time
data={'year':2030,'_stop':['week',4], 'players':{str(i):{'xp':i,'history':[{'week':j,'gain':float(j)/3} for j in range(100)]} for i in range(1000)}}
writer=Snapshot()
start=time.perf_counter();full=json.dumps(data,separators=(',',':'));full_seconds=time.perf_counter()-start
first=json.loads(writer.prepare(data,str))
batched=Snapshot({'epoch':writer.epoch})
merged={'puts':{}}
batch_count=0
for payload in batched.prepare_batches(data,str):
    piece=json.loads(payload)
    merged['puts'].update(piece.pop('puts'))
    merged.update(piece)
    batch_count+=1
assert merged==first
assert batched.hashes==writer.hashes
assert batch_count>1
data['players']['12']['xp']+=1
start=time.perf_counter();delta=writer.prepare(data,str);delta_seconds=time.perf_counter()-start
change=json.loads(delta)
assert list(change['puts'])==[record_id(['players','12'])]
assert json.loads(change['puts'][record_id(['players','12'])]['text'])==data['players']['12']
data['_stop']=['week',5]
week_change=json.loads(writer.prepare(data,str))
assert not week_change['reset']
assert list(week_change['puts'])==[record_id(['_stop',0])]
json.dumps({'runtime':'Pyodide 0.29.5','full_bytes':len(full),'delta_bytes':len(delta),'full_seconds':full_seconds,'delta_seconds':delta_seconds,'changed_records':len(change['puts']),'batches':batch_count,'batched_checkpoint_equal':True})
`));
  },source);
  assert.equal(report.changed_records,1);console.log(report);
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
