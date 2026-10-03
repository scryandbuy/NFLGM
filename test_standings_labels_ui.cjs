const fs=require('fs'), vm=require('vm'), assert=require('node:assert/strict');
const src=fs.readFileSync('docs/app.js','utf8');
class Element {
  constructor(tag,attrs={},...children){this.tag=tag;this.attrs=attrs;this.children=children;this.style={setProperty(){}};this.classList={add(){}};}
  append(...children){this.children.push(...children);}
  querySelector(q){return descendants(this).find(e=>e.attrs.class?.split(' ').includes(q.slice(1)));}
}
function descendants(n){return n instanceof Element?[n,...n.children.flatMap(descendants)]:[];}
const text=n=>n instanceof Element?n.children.map(text).join(''):String(n??'');
let page;
const ctx={console,el:(...a)=>new Element(...a),renderRail(){},lgSecond(){},
  persPage(){return page=new Element('main');},
  clubLink:(a,n)=>new Element('a',{href:'#club/team/'+a},n),
  formDots:f=>new Element('div',{class:'form'},...f.map(x=>new Element('i',{class:x}))),
  leagueBoard:()=>new Element('section',{class:'stats-board league-board report-board'}),
  leagueYear:()=>new Element('select'),leagueFinish:(s,p)=>p.append(s),
  applyTeamTheme(){},showAbbr:a=>a};
vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('const CLINCH_LABELS'),src.indexOf('function leagueBoard(')),ctx);
vm.runInContext(src.slice(src.indexOf('function statsTeamRow('),src.indexOf('function renderAwards(')),ctx);
const rows=['z','y','x','e',''].map((clinch,i)=>({clinch,club:{abbr:'T'+i,name:'Team '+i},w:16-i*3,l:1+i*3,t:0,pct:.8,pf:400,pa:300,pd:100,div_rec:'5–1',arrow:0,form:['w','w','l','w','w']}));
const view={rail:{club:{}},year:2028,years:[2028],notes:[],divisions:[{name:'United North',rows}],conferences:{United:rows},league_rows:rows,picture:[]};
const snapshots=[];
for(const mode of ['Divisions','Conference','League']){
  vm.runInContext(`standingsView=${JSON.stringify(mode)}`,ctx);ctx.renderStandings(view);
  const marks=descendants(page).filter(e=>e.attrs.class==='clinch');
  assert.deepEqual(marks.map(text),['z','y','x','e']);
  assert.ok(marks.every(e=>e.attrs['aria-label']&&e.attrs['data-tip']));
  assert.equal(descendants(page).filter(e=>e.attrs.class==='standings-team-cell'&&e.tag==='td').length,5);
  snapshots.push(page);
}
for(const mode of ['Leaders','Advanced']){
  vm.runInContext(`statsTab=${JSON.stringify(mode)}`,ctx);
  const boxes=['Passing Yards','Passing TD','Rushing Yards','Receptions'].map((title,i)=>({title,unit:['yds','TD','yds','rec'][i],rows:[{name:'Example Player',pid:'P1',pos:'QB',team:'GB',v:4990}]}));
  ctx.renderStats({rail:{club:{}},year:2028,week:18,years:[2028],boxes,advanced:boxes});
  const headings=descendants(page).filter(e=>e.tag==='h4');
  assert.deepEqual(headings.map(text),boxes.map(b=>b.title));
  assert.ok(headings.every(e=>!descendants(e).some(n=>n.tag==='small')));
}
if(process.argv[2]){
  const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
  const html=n=>n instanceof Element?`<${n.tag} ${Object.entries(n.attrs).filter(([k,v])=>typeof v!=='function'&&v!=null).map(([k,v])=>`${k}="${esc(v)}"`).join(' ')}>${n.children.map(html).join('')}</${n.tag}>`:esc(n??'');
  fs.writeFileSync(process.argv[2],`<!doctype html><meta charset="utf-8"><title>Standings alignment check</title><style>${fs.readFileSync('docs/style.css','utf8')}body{padding:25px}main{margin-bottom:30px}</style>${snapshots.map(html).join('')}${html(page)}`);
}
console.log('Three standings views: clinch markers and labels verified. Leaders/Advanced: duplicate unit labels removed.');
