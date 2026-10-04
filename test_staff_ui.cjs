const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('docs/app.js','utf8');
class Element{
  constructor(tag,attrs={},...children){this.tag=tag;this.attrs=attrs;this.children=children;this.classList={add(){}};}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(k,v){this.attrs[k]=v;}
  querySelectorAll(tag){return walk(this).filter(n=>n!==this&&n.tag===tag);}
}
const walk=n=>[n,...(n.children||[]).filter(x=>x instanceof Element).flatMap(walk)];
const text=n=>n==null?'':typeof n==='string'?n:(n.children||[]).map(text).join(' ');
let page,calls=[],talks=[];
const roles=['oc','dc','st','scout'];
const card=(role,i)=>({role_key:role,role:role.toUpperCase(),name:`Coach ${i}`,rating:80,prestige:60,age:45,years:2,salary:2,ask:3,extend_ask:3,traits:[],unit_ranks:[12],specialty:'Development'});
const fixture=()=>({rail:{year:2028,club:{abbr:'GB'}},cards:roles.map(card),budget:{total:23,payroll:18,available:5,head_coach:{salary:10}},poaches:[],offseason:false,staff_locked:false,renewal_step:false,pools:Object.fromEntries(roles.map(r=>[r,Array.from({length:17},(_,i)=>card(r,i+10))]))});
let v=fixture();
const ctx={console,location:{hash:'#frontoffice/staff/overview'},document:{getElementById:()=>({scrollIntoView(){}})},
el:(...a)=>new Element(...a),renderRail(){},applyTeamTheme(n,t){n.theme=t.abbr;},persPage(){page=new Element('main');return page;},foSecond(){},foBoard:()=>new Element('section'),staffTraits:()=>new Element('div'),ord:()=> 'th',confirm:()=>true,
openStaffTalk:(...a)=>talks.push(a),notify(){},advance(){calls.push('advance');},pyJSON(code){calls.push(code);return code.includes('frontoffice_act')?{ok:true}:v;}};
vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf("let foStaffRole = 'oc';"),source.indexOf('function renderCap(v)')),ctx);
const render=()=>ctx.renderStaff(v),button=label=>walk(page).find(n=>n.tag==='button'&&text(n)===label),buttons=label=>walk(page).filter(n=>n.tag==='button'&&text(n)===label);
render();
assert.equal(page.children[0].theme,'GB');
assert.equal(buttons('Release').length,4,'all staff editable midseason');
assert.equal(buttons('Interview').length,17,'full market, not top eight');
assert.equal(walk(page).filter(n=>n.attrs.class==='staff-person').length,4);
assert.ok(walk(page).some(n=>n.attrs.class==='staff-market-scroll'&&n.attrs.role==='region'));
assert.ok(!text(page).includes("Staff salaries use the owner's budget"));
button('Extend Contract').attrs.onclick();assert.equal(talks.length,1);
button('Release').attrs.onclick();assert.ok(calls.some(c=>c.includes('staff_release')));
button('Staff Renewals').attrs.onclick();assert.equal(ctx.location.hash,'#frontoffice/staff/renewals');
v.cards[0].expiring=true;v.cards[0].years=0;v.renewal_step=true;render();
assert.equal(buttons('Let Expire').length,1);assert.equal(buttons('Release').length,0);
assert.ok(button('Explore Replacements'));button('Let Expire').attrs.onclick();assert.ok(calls.some(c=>c.includes('staff_expiry')&&c.includes('leave=True')));
v.cards[0].let_expire=true;render();assert.ok(button('Undo Let Expire'));
v.staff_locked=true;render();assert.equal(button('Negotiate Renewal').attrs.disabled,'');assert.equal(button('Undo Let Expire').attrs.disabled,'');
v=fixture();v.renewal_step=true;render();assert.ok(!text(page).includes('New Year: Cap & Contracts'));assert.ok(!walk(page).some(n=>n.attrs.class==='staff-calendar'));assert.ok(text(page).includes('No Expiring Staff Contracts'));button('Advance To Player Re-signings').attrs.onclick();assert.ok(calls.includes('advance'));
console.log('Staff UI passed: overview/renewals, midseason controls, all 17 candidates, expiry/undo, live lock, empty-state advance.');
