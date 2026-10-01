const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('docs/app.js','utf8');
const el=(tag,attrs={},...children)=>({tag,attrs,children,append(...items){this.children.push(...items);}});
const all=n=>[n,...(n?.children||[]).filter(x=>x&&typeof x==='object').flatMap(all)];
const text=n=>typeof n==='object'?(n.children||[]).map(text).join(' '):String(n??'');
let page;
const ctx={el,renderRail:()=>{},persPage:()=>page=el('main'),persSecond:()=>{},
  finishPersonnel:()=>{},pendingExtensionPid:null,ovrCell:n=>{assert.ok(Number.isFinite(n));return n;},pill:n=>n,
  talkLine:()=>el('div'),location:{hash:''}};
vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('function completedExtensionTerms('),src.indexOf('function finishPersonnel(')),ctx);
vm.runInContext(src.slice(src.indexOf('function renderExtensions('),src.indexOf('// ---------------------------------------------------------------- Front Office')),ctx);
const active={pid:'p1',name:'Active QB',pos:'QB',age:28,ovr:88,hit:20,eligible:true};
const data={rail:{},expiring:[active],two_left:[{...active,pid:'p2',name:'Two Years QB'}],
  done:[{pid:'p1',name:'Signed QB',pos:'QB',kind:'extended',years:4,apy:40},
        {pid:'p1',name:'Signed QB',pos:'QB',kind:'tagged',years:null,apy:30},
        {pid:'p3',name:'Option WR',pos:'WR',kind:'option exercised',years:null,apy:15}],
  threads:[],promises:[]};
ctx.renderExtensions(data);
const clickTab=label=>all(page).find(n=>n.tag==='button'&&text(n).startsWith(label)).attrs.onclick();
clickTab('Done This Year');
assert.match(text(page),/Extended/);assert.match(text(page),/4 added years/);
assert.match(text(page),/Franchise Tagged/);assert.match(text(page),/Option Exercised/);
assert.match(text(page),/\$40.0m/);assert.match(text(page),/Annual Value/);
assert.doesNotMatch(text(page),/undefined|NaN|Ask the Agent|Open Talks/);
const who=all(page).filter(n=>n.attrs?.class==='who');
assert.deepEqual(who.map(n=>n.attrs['data-source-index']),[0,1,2]);
who[0].attrs.onclick();assert.equal(ctx.location.hash,'#club/player/p1');
clickTab('Expiring');assert.match(text(page),/Active QB/);assert.match(text(page),/Ask the Agent/);
clickTab('Two Years Left');assert.match(text(page),/Two Years QB/);
clickTab('Done This Year');
ctx.renderExtensions({...data,done:[]});assert.match(text(page),/No completed decisions this year/);
console.log('Extensions tabs: completed extensions, tags/options, empty history, duplicate-player records, player links, and switching back pass');
