const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('docs/app.js', 'utf8');
let calls = 0, release, fail = false;
let buttons = [{disabled:false,dataset:{}},{disabled:true,dataset:{}}];
const context = vm.createContext({
 document:{querySelectorAll:s=>s==='[data-live-step]'?buttons:buttons.filter(b=>b.dataset.stepPending)},
 window:{scrollY:12,scrollTo(){}},
 pyJSON:()=>{ calls++; if(fail) throw Error('test failure'); return {live:{open:true}}; },
 renderGameDay:()=>{buttons=[{disabled:false,dataset:{}},{disabled:true,dataset:{}}];},
 saveLiveJournalNotified:()=>new Promise(r=>{release=r;})
});
vm.runInContext(source.slice(source.indexOf('let gameDayStepBusy'),source.indexOf('function renderGameDay')),context);
(async()=>{
 const first=context.advanceGameDay('drive',{detail:1});
 assert.equal(buttons[0].disabled,true);
 await context.advanceGameDay('drive',{detail:1}); assert.equal(calls,1);
 release(); await first;
 assert.equal(buttons[0].disabled,false); assert.equal(buttons[1].disabled,true);
 const second=context.advanceGameDay('drive',{detail:2}); assert.equal(calls,2);
 await context.advanceGameDay('drive',{detail:3}); assert.equal(calls,2);
 release();await second;
 const next=context.advanceGameDay('drive',{detail:3}); assert.equal(calls,3);release();await next;
 fail=true;await assert.rejects(context.advanceGameDay('play',{detail:1}));
 assert.equal(buttons[0].disabled,false);
 fail=false;const retry=context.advanceGameDay('play',{detail:0});release();await retry;
 assert.equal(calls,5);
 console.log('PASS: repeated input, double-click, next deliberate click, break lock, error recovery, keyboard input');
})().catch(e=>{console.error(e);process.exitCode=1;});
