const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('docs/app.js','utf8');
function fixture(failLoad=false,failJournal=false){
 const nodes={'#boot':{remove(){delete nodes['#boot'];}},'#resume':{},'#importfile':{}};
 const globals=new Map(),calls=[];
 const ctx={saved:{text:'large save',journal:{step:3}},engineReady:true,entering:false,
  $:key=>nodes[key],updateBootActions(){},say(){},bootHash(){},refresh(){},notify(){},
  setTimeout:fn=>fn(),saveGame:async()=>{},py:{globals,runPython(code){
    calls.push(code);
    if(failLoad&&code.includes('Session.load'))throw Error('invalid save');
    if(failJournal&&code.includes('apply_live_journal'))throw Error('invalid journal');
  }},loadSessionFromBlob:async()=>{
    calls.push('Session.load_file');
    if(failLoad)throw Error('invalid save');
  }};
 vm.createContext(ctx);
 return {ctx,nodes,globals,calls};
}
(async()=>{
 const resume=source.slice(source.indexOf("  $('#resume').onclick ="),source.indexOf("  $('#advance').onclick ="));
 for(const [failLoad,failJournal] of [[false,false],[false,true],[true,false]]){
  const {ctx,nodes,globals,calls}=fixture(failLoad,failJournal);
  vm.runInContext(resume,ctx);await nodes['#resume'].onclick();
  assert.equal(globals.size,0,'Python must release save and journal text, even on failure');
  assert.equal(ctx.saved.text,failLoad?'large save':null,'failed load must remain retryable');
  if(failJournal)assert.equal(calls.filter(c=>c.includes('Session.load')).length,2);
 }
 const importCode=source.slice(source.indexOf("  $('#importfile').onchange ="),source.indexOf("  $('#back').onclick ="));
 for(const fail of [false,true]){
  const {ctx,nodes,globals}=fixture(fail);
  vm.runInContext(importCode,ctx);
  const target={files:[{text:async()=>'imported save'}],value:'file'};
  await nodes['#importfile'].onchange({target});
  assert.equal(globals.size,0);assert.equal(target.value,'');
 }
 console.log('Save/import text released after success and failure; resume retry and journal fallback preserved.');
})().catch(e=>{console.error(e);process.exitCode=1;});
