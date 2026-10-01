const fs=require('fs'), vm=require('vm'), assert=require('node:assert/strict');
const src=fs.readFileSync('docs/app.js','utf8');
let calls=[], notices=[], reloads=0, fresh;
const ctx={Number,JSON,location:{hash:''},tradeState:{},
  el:(tag,attrs,...children)=>({tag,attrs,children,append(...nodes){this.children.push(...nodes);}}),
  pyJSON:code=>{calls.push(code); return code.startsWith('SESSION.inbox_message')?fresh:{ok:true};},
  notify:r=>notices.push(r)};
vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('function rosterReportCards('),src.indexOf('function linkHash(')),ctx);
const flatten=n=>[n,...(n.children||[]).filter(x=>typeof x==='object').flatMap(flatten)];
for(const source of ['fa','ps','waiver','trade']) {
  const r={pid:'p1',name:'Example',pos:'CB',ovr:83,source,owner:'MIN',pick:{id:'2026-5-MIN'},available:true,status:'Review opportunity'};
  const m={id:42,recommendations:[r]}; fresh=m;
  const view=ctx.rosterReportCards(m,()=>reloads++);
  const buttons=flatten(view).filter(n=>n.tag==='button');
  assert.equal(buttons.length,2);
  assert.ok(flatten(view).some(n=>n.tag==='a' && n.attrs.href==='#club/player/p1'));
  buttons[0].attrs.onclick();
  if(source==='trade') { assert.equal(ctx.location.hash,'#personnel/trades'); assert.deepEqual(Array.from(ctx.tradeState.a),['2026-5-MIN']); }
  else if(source==='waiver') assert.equal(ctx.location.hash,'#personnel/wire');
  else assert.ok(calls.some(c=>c.includes(source==='ps'?"'poach_ps'":"'open_talks'")));
  buttons[1].attrs.onclick();
  assert.ok(calls.includes('SESSION.inbox_roster_dismiss(42, "p1")'));
  fresh={recommendations:[{...r,available:false}]}; const before=calls.length;
  buttons[0].attrs.onclick(); assert.equal(calls.length,before+1); assert.equal(notices.at(-1).ok,false);
  assert.equal(flatten(ctx.rosterReportCards(fresh,()=>{})).filter(n=>n.tag==='button').length,0);
}
console.log('Roster report links, four acquisition routes, dismissal and stale-click guard passed.');
