const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const src = fs.readFileSync('docs/app.js', 'utf8');
class Element {
  constructor(tag, attrs = {}, ...children) { this.tag=tag; this.attrs=attrs; this.children=children; this.style={}; this.classList={add(){},toggle(){}}; this.value=attrs.value || ''; }
  append(...children) { this.children.push(...children); }
  set innerHTML(_) { this.children=[]; }
}
const nodes = n => n instanceof Element ? [n,...n.children.flatMap(nodes)] : [];
const text = n => n instanceof Element ? n.children.map(text).join('') : String(n ?? '');
let page, copied, requests=[];
const ctx={console, el:(...args)=>new Element(...args), renderRail(){}, lgSecond(){}, applyTeamTheme(){},
  persPage(){return page=new Element('main');}, leagueBoard:()=>new Element('section'),
  leagueFinish:(s,p)=>p.append(s), leagueYear:()=>new Element('select'), showAbbr:x=>x,
  stripe:x=>x, clubLink:(a,n)=>n, showTeamText:x=>x, transactionWhen:()=>'',
  teamTheme:()=>({}), coachingMoveRow:r=>new Element('div',{class:'coach'},r.person),
  showTransactionTrade(){}, copyText:s=>{copied=s;}, location:{}};
vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('function teamCapPlanning('),src.indexOf('function renderTeam(')),ctx);
const cap={year:2029,space:7.8,committed:390,limit:401.6,next:false,next_year:2030,committed_next:374.5,limit_next:437.8};
assert.equal(ctx.teamCapPlanning(cap).year,2030);
assert.equal(ctx.teamCapPlanning(cap).committed,374.5);
const upcoming={...cap,year:2030,space:63.3,committed:374.5,limit:437.8,next:true,pending_offers:2};
assert.equal(ctx.teamCapPlanning(upcoming),upcoming,'before rollover, headline and planning detail share the upcoming ledger');
assert.equal(cap.year,2029,'in season, current-cap metric still uses its current year');
vm.runInContext(src.slice(src.indexOf("let statsTab = 'Leaders';"),src.indexOf('let allProTab=')),ctx);
const rows=Array.from({length:145},(_,i)=>({pid:String(i),name:i===144?'Nic Scourton':'Player '+String(i).padStart(3,'0'),pos:'LEDG',team:'GB',row:[145-i,i===144?13:1]}));
const view={rail:{club:{}},year:2029,week:22,years:[2029],tables:{defense:{cols:['Tkl','Sacks'],rows}},boxes:[],advanced:[]};
vm.runInContext("statsTab='Defense'",ctx);ctx.renderStats(view);
const bodyRows=()=>nodes(page).filter(n=>n.tag==='tr'&&n.attrs.class==='stats-team-row');
assert.equal(bodyRows().length,40);
for (const label of ['Tkl', 'Sacks']) {
  const h=nodes(page).find(n=>n.tag==='th'&&text(n)===label);
  assert.equal(h.attrs.class,'n');
  assert.ok(h.children[0].attrs.style.includes('text-align:right'));
}
const button=label=>nodes(page).find(n=>n.tag==='button'&&text(n)===label);
button('Next').attrs.onclick();assert.equal(bodyRows().length,40);assert.ok(text(page).includes('41–80 of 145'));
button('Sacks').attrs.onclick();assert.ok(text(bodyRows()[0]).includes('Nic Scourton'));assert.equal(bodyRows().length,40);
const search=nodes(page).find(n=>n.tag==='input');search.value='scourton';search.oninput();assert.equal(bodyRows().length,1);assert.ok(text(page).includes('1–1 of 1'));
search.value='';search.oninput();button('Sacks').attrs.onclick();assert.ok(!text(bodyRows()[0]).includes('Nic Scourton'));
// A historical rebuild gets a fresh table state instead of retaining page 4.
ctx.renderStats({...view,year:2028});assert.ok(text(page).includes('1–40 of 145'));
vm.runInContext("let txGroup='All',txClub='all',txQuery='',txOffset=0;",ctx);
const ledger=Array.from({length:155},(_,i)=>({year:2029,kind:'sign',group:'Signings',tag:'Signing',person:i===154?'Will Johnson':'Player '+i,line:i===154?'Will Johnson old signing':'Player '+i,team:{abbr:'GB',name:'Green Bay'},detail:'3 years',mine:true,division:'United North'}));
ctx.pyJSON=command=>{
  requests.push(command);
  const state=vm.runInContext('({group:txGroup,club:txClub,query:txQuery,offset:txOffset})',ctx);
  const all=ledger.filter(r=>!state.query||r.person.toLowerCase().includes(state.query.toLowerCase()));
  const offset=command.includes('n=None')?0:state.offset;
  return {rows:command.includes('n=None')?all:all.slice(offset,offset+60),total:all.length,offset,filtered:true};
};
vm.runInContext(src.slice(src.indexOf('function transactionPage('),src.indexOf("let statsTab = 'Leaders';")),ctx);
ctx.renderTransactions({rail:{club:{abbr:'GB',name:'Green Bay'}},groups:['Signings'],my_division:'United North'});
const transactionRows=()=>nodes(page).filter(n=>n.attrs.class==='transaction-row');
assert.equal(transactionRows().length,60);
button('Older').attrs.onclick();assert.equal(transactionRows().length,60);assert.ok(text(page).includes('61–120 of 155'));
button('Older').attrs.onclick();assert.equal(transactionRows().length,35);assert.ok(text(page).includes('121–155 of 155'));
const txSearch=nodes(page).find(n=>n.tag==='input');txSearch.value='Will Johnson';txSearch.oninput();assert.equal(transactionRows().length,1);assert.ok(text(page).includes('Will Johnson'));
txSearch.value='';txSearch.oninput();button('Copy').attrs.onclick();assert.equal(copied.split('\n').length,155);assert.equal(transactionRows().length,60);
assert.ok(requests.some(x=>x.includes('offset=120, n=60')));
assert.ok(!src.includes('txShown'), 'all coaching/pagination routes reset the current offset');
console.log('League tables: full-data sorting/search,40-row DOM bound; transactions filter/page/export with60-row DOM bound passed.');
