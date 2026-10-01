const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('docs/app.js','utf8');
const frames=new Map(),timers=new Map(),events={},microtasks=[],snapshots=[];let id=0,value=0;
const ctx={document:{visibilityState:'visible',addEventListener:(key,fn)=>events[key]=fn},window:{addEventListener:(key,fn)=>events[key]=fn},
 requestAnimationFrame:fn=>{frames.set(++id,fn);return id;},cancelAnimationFrame:n=>frames.delete(n),
 setTimeout:(fn,delay)=>{timers.set(++id,{fn,delay});return id;},clearTimeout:n=>timers.delete(n),queueMicrotask:fn=>microtasks.push(fn),
 saveGameNotified:()=>{snapshots.push(value);return Promise.resolve();}};
vm.createContext(ctx);vm.runInContext(src.slice(src.indexOf('let autosaveQueued'),src.indexOf('function pyJSON')),ctx);
const frame=()=>{const [key,fn]=frames.entries().next().value;frames.delete(key);fn();};
const timer=delay=>{const [key,{fn}]=[...timers].find(([,x])=>x.delay===delay);timers.delete(key);fn();};
value=1;ctx.queueAutosave();value=2;ctx.queueAutosave();assert.equal(frames.size,1);assert.equal(snapshots.length,0);
frame();assert.equal(snapshots.length,0,'frame callback must not serialize before paint');timer(0);assert.deepEqual(snapshots,[2],'rapid decisions captured together');assert.equal(timers.size,0);
value=3;ctx.queueAutosave();events.pagehide();assert.deepEqual(snapshots,[2,3],'pagehide captures pending state immediately');assert.equal(frames.size,0);assert.equal(timers.size,0);
value=4;ctx.queueAutosave();ctx.document.visibilityState='hidden';events.visibilitychange();assert.deepEqual(snapshots,[2,3,4]);
value=5;ctx.queueAutosave();assert.equal(frames.size,0);microtasks.shift()();assert.equal(snapshots.at(-1),5,'hidden actions do not depend on frames');
ctx.document.visibilityState='visible';value=6;ctx.queueAutosave();timer(200);assert.equal(snapshots.at(-1),6,'throttled frame fallback persists');assert.equal(frames.size,0);
// Explicit save captures all pending mutations and cancels a redundant autosave.
ctx.py={runPython:()=>String(value)};ctx.busy=()=>{};ctx.queueSave=(kind,text)=>{snapshots.push(Number(text));return Promise.resolve();};
vm.runInContext(src.slice(src.indexOf('function saveGame('),src.indexOf('async function saveGameNotified(')),ctx);
value=7;ctx.queueAutosave();ctx.saveGame();assert.equal(snapshots.at(-1),7);assert.equal(frames.size,0);assert.equal(timers.size,0);events.pagehide();assert.equal(snapshots.filter(x=>x===7).length,1);
console.log('Autosave paints first, coalesces rapid actions, captures on pagehide/hidden, and preserves explicit save');
