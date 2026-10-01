const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('docs/app.js','utf8');
const code=src.slice(src.indexOf('function threadBox('),src.indexOf('// Common Personnel presentation'));
function setup(state,{ok=true}={}){
  let done=0;const calls=[];
  const ctx={el:(tag,attrs={},...children)=>({tag,attrs,children,append(...items){this.children.push(...items);}}),
    offerForm:()=>({tag:'form',children:[]}),notify:()=>{},pyJSON:query=>{calls.push(query);return {ok,why:'Not enough cap room'};}};
  vm.createContext(ctx);
  vm.runInContext(src.slice(src.indexOf('const DISPLAY_ABBR ='),src.indexOf('const COLOR =')),ctx);
  vm.runInContext(code,ctx);
  const box=ctx.threadBox({id:1,state,kind:'fa_offseason',ask:22,years:3,rival:{team:'Arizona',apy:20,years:3},counter:{apy:21,years:3}},()=>done++);
  const walk=n=>[n,...(n.children||[]).filter(x=>x&&typeof x==='object').flatMap(walk)];
  const nodes=walk(box),buttons=nodes.filter(n=>n.tag==='button');
  return {nodes,buttons,labels:buttons.flatMap(n=>n.children),calls,done:()=>done};
}
const match=setup('match_requested');assert.deepEqual(match.labels,['Match and Sign','Let Him Go']);assert.equal(match.nodes.some(n=>n.tag==='form'),false);
match.buttons[0].attrs.onclick();assert.match(match.calls[0],/'match'/);assert.equal(match.done(),1);
const decline=setup('match_requested');decline.buttons[1].attrs.onclick();assert.match(decline.calls[0],/'withdraw'/);
const counter=setup('countered');assert.deepEqual(counter.labels,['Accept Counter']);assert.equal(counter.nodes.some(n=>n.tag==='form'),true);
const waiting=setup('waiting');assert.deepEqual(waiting.labels,['Rescind Offer']);assert.equal(waiting.nodes.some(n=>n.tag==='form'),false);
for(const state of ['accepted','declined','expired','broken_off'])assert.equal(setup(state).buttons.length,0);
const failure=setup('match_requested',{ok:false});failure.buttons[0].attrs.onclick();assert.equal(failure.done(),0);assert.equal(failure.nodes.find(n=>n.attrs?.role==='alert').textContent,'Not enough cap room');
console.log('Negotiation stages: exclusive match choice, current counter only, waiting/closed suppression, failed action remains visible');
