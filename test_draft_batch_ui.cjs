const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('docs/app.js','utf8'),ctx={};vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('async function completeDraftBatch('),source.indexOf('function guardDraftRoute(')),ctx);
(async()=>{
  for(const scenario of ['complete','stop','error','save_error']) {
    let calls=0,saves=0,paints=0;const progress=[];
    const result=await ctx.completeDraftBatch({
      step(){calls++;if(scenario==='error'&&calls===2)throw Error('pick failed');return {ok:true,picks:1,complete:calls===3};},
      paint:async()=>{paints++;},progress:(n,saving)=>progress.push([n,saving]),
      stopped:()=>scenario==='stop'&&calls===1,
      save:async()=>{saves++;if(scenario==='save_error')throw Error('disk full');}
    });
    assert.equal(saves,1,scenario+' saves once, including interrupted work');
    assert.ok(paints>=calls+1,'paint opportunity before each pick and saving');
    if(scenario==='complete'){assert.equal(calls,3);assert.equal(result.picks,3);}
    if(scenario==='stop'){assert.equal(calls,1);assert.equal(result.interrupted,true);}
    if(scenario==='error'){assert.ok(result.error);assert.equal(result.picks,1);}
    if(scenario==='save_error')assert.ok(result.saveError);
    assert.equal(progress.at(-1)[1],true);
  }
  const guard={draftRunning:{hash:'#draft/day'},history:{replaceState(...args){this.hash=args[2];}}};vm.createContext(guard);
  vm.runInContext(source.slice(source.indexOf('function guardDraftRoute('),source.indexOf('async function runDraftBatch(')),guard);
  assert.equal(guard.guardDraftRoute(),true);assert.equal(guard.history.hash,'#draft/day');
  guard.draftRunning=null;assert.equal(guard.guardDraftRoute(),false);
  assert.ok(source.includes("if (draftRunning) return; if (['sim_to_me','sim_round','sim_draft'].includes(name))"));
  assert.ok(source.includes('SESSION.draft_batch_step('));
  const headerCalls=[];
  const header={draftRunning:null,pyJSON:()=>({active:true,round:2}),runDraftBatch:async(mode,round)=>headerCalls.push([mode,round])};
  vm.createContext(header);
  vm.runInContext(source.slice(source.indexOf('async function advance()'),source.indexOf('// A changed hash')),header);
  await header.advance();assert.deepEqual(headerCalls,[['sim_draft',2]],'header full auto uses the cooperative runner');
  header.draftRunning={};await header.advance();assert.equal(headerCalls.length,1,'running draft rejects duplicate header activation');
  console.log('Passed cooperative paint, completion, interruption, error save, save failure, navigation guard, and header full-auto routing');
})().catch(e=>{console.error(e);process.exitCode=1;});
