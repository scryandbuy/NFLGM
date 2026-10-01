const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('docs/app.js','utf8');
class Element {
 constructor(tag,attrs={},kids=[]){this.tag=tag;this.attrs=attrs;this.kids=kids;this.removed=false;}
 append(...kids){this.kids.push(...kids);}
 set innerHTML(v){this.kids=[];}
 remove(){this.removed=true;}
}
const el=(tag,attrs={},...kids)=>new Element(tag,attrs,kids);
const text=n=>typeof n==='string'?n:(n?.kids||[]).map(text).join(' ');
const all=n=>[n,...(n?.kids||[]).flatMap(k=>typeof k==='object'?all(k):[])];
let saved=0,closed=0,taken=false;
const ctx={el,document:{body:el('body'),createTextNode:text=>text},showAbbr:x=>x,
 pyJSON:cmd=>{if(cmd.startsWith('SESSION.half_take'))taken=!taken;return {live:{recs:[{i:0,text:'Protect',why:'Pressure',side:'offence',taken}]}};},
 saveLiveJournalNotified:async()=>{saved++;}};
vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('function playerMention('),src.indexOf('function renderRecapBody(')),ctx);
vm.runInContext(src.slice(src.indexOf('function renderRecapBody('),src.indexOf('function renderInbox(')),ctx);
vm.runInContext(src.slice(src.indexOf('const halfConfirmed ='),src.indexOf('// Team reports share')),ctx);
let body=ctx.renderRecapBody({kind:'result',recap:{intro:'A game',sections:[{title:'Pregame plan',reviews:[{title:'Run it',conclusion:'Positive',findings:[{label:'Running',verdict:'positive',text:'Eight yards per run'}]}]}]}});
assert.equal(all(body).filter(n=>n.tag==='h4').length,1);
assert.ok(text(body).includes('Eight yards per run'));
assert.ok(all(body).some(n=>n.attrs?.class==='recap-finding positive'));
const old=ctx.renderRecapBody({kind:'result',body:'Win\n\nPREGAME PLAN\nRun more\n\nHALFTIME ADJUSTMENTS\nThese are observed results, not proof of cause; opponent adjustments and game situation also mattered.'});
assert.equal(all(old).filter(n=>n.tag==='h4').length,2);
assert.ok(!text(old).includes('not proof of cause'));
assert.equal(text(ctx.renderRecapBody({body:'Ordinary mail'})),'Ordinary mail');
const snaps=ctx.renderRecapBody({snap_counts:{
 offense:{total:60,rows:[{name:'A. Quarterback',snaps:60},{name:'B. Reserve',snaps:0}]},
 defense:{total:82,rows:[{name:'C. Defender',snaps:75}]},note:'Includes overtime.'}});
assert.deepEqual(all(snaps).filter(n=>n.tag==='h4').map(text),['Offense','Defense']);
assert.equal(all(snaps).filter(n=>n.tag==='table').length,2);
assert.ok(text(snaps).includes('0/60'));
assert.ok(text(snaps).includes('75/82'));
assert.ok(text(snaps).includes('Includes overtime.'));
(async()=>{
 vm.runInContext("halfConfirmed['game-halftime']=true",ctx);
 ctx.openHalftime({home:{abbr:'GB'},away:{abbr:'LAC'}},{adjustment_period:'overtime',score:{home:24,away:24}},'game-overtime',()=>closed++);
 let overlay=ctx.document.body.kids.at(-1);
 assert.ok(text(overlay).includes('Overtime Adjustments'));
 assert.ok(text(overlay).includes('before the overtime kickoff'));
 assert.equal(vm.runInContext("halfConfirmed['game-overtime']",ctx),undefined);
 await all(overlay).find(n=>n.tag==='button'&&text(n)==='Take').attrs.onclick();
 assert.equal(saved,1);assert.ok(taken);
 all(overlay).find(n=>n.tag==='button'&&text(n)==='Confirm').attrs.onclick();
 assert.ok(vm.runInContext("halfConfirmed['game-overtime']",ctx));assert.equal(closed,1);assert.ok(overlay.removed);
 assert.ok(src.includes('const breakKey = `${gkey}-${overtime'));
 console.log('Recap sections, legacy/plain mail, OT modal, independent confirmation and saved choices pass');
})().catch(e=>{console.error(e);process.exitCode=1;});
