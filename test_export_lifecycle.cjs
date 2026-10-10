const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('docs/app.js','utf8');
const handler=source.slice(source.indexOf("  $('#export').onclick"),source.indexOf("  $('#import').onclick"));
let boot=false,fail=false,release,dialog,downloads=0,queued=0,routed=0,notifications=[];
const button={},advance={disabled:false};
const ctx={exportInProgress:false,draftRunning:null,gameDayStepBusy:false,saveWriting:false,autosaveQueued:true,
 location:{hash:'#portal'},HashChangeEvent:class{},setTimeout:()=>{},
 $:selector=>selector==='#export'?button:selector==='#advance'?advance:selector==='#boot'?boot:null,
 pyJSON:()=>({year:2034,stop:'week-6'}),notify:r=>notifications.push(r),
 cancelAutosaveSchedule:()=>{},queueAutosave:()=>queued++,
 window:{dispatchEvent:()=>routed++},URL:{createObjectURL:()=> 'blob:test',revokeObjectURL:()=>{}},
 document:{body:{append:()=>{}},createElement:()=>({click(){downloads++;},remove(){}})},
 el:(tag)=>{const node={addEventListener:()=>{},showModal(){this.open=true;},close(){this.open=false;},remove(){this.removed=true;}};if(tag==='dialog')dialog=node;return node;},
 exportSessionBlob:async progress=>{await new Promise(r=>release=r);progress(123);if(fail)throw Error('compression failed');return {size:123};}
};
vm.createContext(ctx);vm.runInContext(handler,ctx);
(async()=>{
 boot=true;await button.onclick();assert.equal(downloads,0);assert.match(notifications.pop().why,/Wait/);boot=false;
 const pending=button.onclick();assert.ok(ctx.exportInProgress && dialog.open);
 await button.onclick();assert.equal(downloads,0,'duplicate clicks do not start a second export');
 ctx.location.hash='#club';release();await pending;
 assert.equal(downloads,1);assert.ok(dialog.removed && !ctx.exportInProgress);assert.equal(queued,1);assert.equal(routed,1);
 fail=true;const failed=button.onclick();release();await failed;
 assert.equal(downloads,1);assert.match(notifications.at(-1).why,/compression failed/);
 assert.ok(dialog.removed && !ctx.exportInProgress);assert.equal(queued,2);
 console.log('Export starts after boot, prevents duplicates, resumes autosave/routes, and recovers from failure.');
})().catch(e=>{console.error(e);process.exitCode=1;});
