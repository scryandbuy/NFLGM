const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('docs/app.js','utf8');
(async()=>{
 let checked=0;
 for(const [done,target,live=false] of [['Week 1 live','#gameday'],['Cutdown','#personnel/wire'],['Camp','#portal'],['You are on the clock','#draft/day'],['Practice complete','#gameplan/practice'],['staff','#frontoffice/staff/renewals'],
   ...['Wild Card','Divisional Round','Conference Championship','Championship Game'].map(round=>[`${round} live`,'#gameday',true])]) {
  for(const initial of new Set(['#portal','#league',target])) {
   let hash=initial,renders=0,routeEvents=0,saves=0,snapshotRenderCount=0;const events=[];
   const render=()=>{renders++;};
   const ctx={practiceSaving:false,practiceSaveRequired:false,autosaveQueued:true,document:{visibilityState:'visible'},
    location:{get hash(){return hash;},set hash(value){if(hash!==value){hash=value;events.push(()=>{routeEvents++;render();});}}},
    $:()=>({disabled:false}),notify(){},renderRail(){},renderGameDay:render,renderWire:render,renderStaff:render,renderDraftDay:render,renderPractice:render,refresh:render,
    cancelAutosaveSchedule(){},setTimeout,clearTimeout,
    requestAnimationFrame:fn=>setImmediate(()=>{events.splice(0).forEach(f=>f());fn();}),cancelAnimationFrame:clearImmediate,
    pyJSON:code=>code==='SESSION.blocking()'?[]:code==='SESSION.advance()'?{done,next:done==='staff'?{go:target}:live?{title:'Game Day',live:true}:null}:{},
    saveGame:async()=>{saves++;snapshotRenderCount=renders;},saveGameNotified:async()=>{saves++;snapshotRenderCount=renders;}};
   vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function advanceRoute('),source.indexOf('// ---------------------------------------------------------------- start')),ctx);
   await ctx.advanceInner();events.splice(0).forEach(f=>f());
   assert.equal(hash,target,done);assert.equal(renders,1,`${done} from ${initial} renders exactly once`);assert.equal(saves,1);
   assert.equal(routeEvents,initial===target?0:1);
   if(done!=='Practice complete')assert.equal(snapshotRenderCount,1,'page renders before full serialization');
   assert.equal(ctx.practiceSaveRequired,false);
   checked++;
  }
 }
 console.log(`Advance routes: ${checked} changed/same destinations including all playoff rounds, single render and save, paint before serialization passed`);
})().catch(e=>{console.error(e);process.exitCode=1;});
// A throttled tab must still save, and pagehide must see the dirty flag while
// Advance waits for paint rather than silently losing the pending snapshot.
(async()=>{
 const timers=new Map();let n=0,frame=null;
 const c={autosaveQueued:true,document:{visibilityState:'visible'},cancelAutosaveSchedule(){},
  setTimeout(fn){timers.set(++n,fn);return n;},clearTimeout(i){timers.delete(i);},
  requestAnimationFrame(fn){frame=fn;return 1;},cancelAnimationFrame(){frame=null;}};
 vm.createContext(c);vm.runInContext(source.slice(source.indexOf('async function paintBeforeAdvanceSave('),source.indexOf('async function advanceInner(')),c);
 const p=c.paintBeforeAdvanceSave();assert.equal(c.autosaveQueued,true,'pagehide can flush until saveGame captures');
 [...timers.values()][0]();await p;assert.equal(frame,null,'fallback clears stalled frame');
 c.document.visibilityState='hidden';await c.paintBeforeAdvanceSave();assert.equal(timers.size,0,'hidden tabs bypass paint wait');
 console.log('Advance save: dirty flag survives paint wait, throttled frame falls back, hidden tab saves immediately');
})().catch(e=>{console.error(e);process.exitCode=1;});
