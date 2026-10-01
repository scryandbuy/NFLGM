const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('docs/app.js','utf8');
const tasks=[],dialogs=[],opened=[],calls=[];let acknowledged=false,level=0,otherDialog=false;
const listeners={};
function el(tag,attrs,...children){return {tag,attrs,children,events:{},open:false,
 append(...xs){this.children.push(...xs);},addEventListener(name,fn){this.events[name]=fn;},
 showModal(){this.open=true;},focus(){},remove(){this.removed=true;},close(){this.open=false;this.events.close();listeners.close();}};}
const context={py:{},el,applyTeamTheme(){},notify:r=>{throw Error(JSON.stringify(r));},openPlayer:(...args)=>opened.push(args),
 queueMicrotask:fn=>tasks.push(fn),document:{body:{append:node=>dialogs.push(node)},
 querySelector:()=>otherDialog||dialogs.some(d=>d.open),addEventListener:(name,fn)=>listeners[name]=fn},
 pyJSON:code=>{calls.push(code);if(code==='SESSION.development_notices()')return {club:{abbr:'GB'},players:acknowledged?[]:[{pid:'p',name:'Test Player',unlocks:level,can_unlock:true}]};
 assert.equal(code,`SESSION.dismiss_ceiling_notice("p", ${level})`);acknowledged=true;return {ok:true};}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('let ceilingNoticeQueued'),source.indexOf('// the development sheet:')),context);
const flush=()=>{while(tasks.length)tasks.shift()();};
function button(node,label){if(node.tag==='button'&&node.children.includes(label))return node;for(const c of node.children||[]){if(c&&typeof c==='object'){const b=button(c,label);if(b)return b;}}}
context.queueCeilingNoticeCheck();context.queueCeilingNoticeCheck();flush();
assert.equal(dialogs.length,1,'re-renders coalesce into one popup');
assert.ok(JSON.stringify(dialogs[0].children).includes('Unlock a higher ceiling by spending XP.'));
button(dialogs[0],'Open Development').attrs.onclick();flush();
assert.deepEqual(opened,[['p','Development']]);
context.queueCeilingNoticeCheck();flush();assert.equal(dialogs.length,1,'same ceiling stays acknowledged');
level=1;acknowledged=false;context.queueCeilingNoticeCheck();flush();assert.equal(dialogs.length,2,'higher ceiling notifies again');
button(dialogs[1],'Got it').attrs.onclick();flush();
acknowledged=false;otherDialog=true;context.queueCeilingNoticeCheck();flush();assert.equal(dialogs.length,2);
otherDialog=false;listeners.close();flush();assert.equal(dialogs.length,3,'deferred popup appears when another dialog closes');
assert.match(source,/AUTO_SAVE_METHODS\.add\('dismiss_ceiling_notice'\)/);
assert.match(source,/function renderRail\(r\)\s*{[^]*?queueCeilingNoticeCheck\(\)/);
console.log('Ceiling popups: coalesced, acknowledged, linked to Development, repeated for new ceilings, and deferred behind dialogs.');
