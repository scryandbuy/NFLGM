const fs = require('fs'), vm = require('vm'), assert = require('assert');
const src = fs.readFileSync('docs/app.js','utf8');
function el(tag, attrs={}, ...children) {
  return {tag, ...attrs, children,
    append(...items) {this.children.push(...items);},
    querySelector(selector) {return find(this, n => (n.class || '').split(' ').includes(selector.slice(1)));}
  };
}
function find(node, predicate) {
  if (!node || typeof node !== 'object') return null;
  if (predicate(node)) return node;
  for (const child of node.children || []) {const hit=find(child,predicate);if(hit)return hit;}
  return null;
}
const club={abbr:'GB',name:'Green Bay',color:'#203731',accent:'#ffb612'};
function view(round) {
  return {rail:{club,year:2027},year_next:2027,live:true,
    current:{team:club,round,sel:(round-1)*32+12,slot:`${round}.12`,needs:[]},
    mine_next:[{sel:44}],on_user:round===2,picks_away:32,results:[],clock:[],my_needs:[],
    order:[1,2,3].map(r=>({round:r,sel:(r-1)*32+12,slot:`${r}.12`,team:club,now:r===round,mine:true}))};
}
let page, latest=view(1), ok=true;
const ctx={el,boardRound:null,offersCache:null,location:{hash:'#draft/day'},
  renderRail(){},drSecond(){},featureHero(){},notify(){},ord:()=> 'th',showAbbr:x=>x,
  teamTheme:()=>({base:club.color,accent:club.accent}),
  persPage:()=>page=el('main'),draftAvailableSources:new Map(),
  draftAvailableView:()=>({key:'GB',source:'consensus',rows:[],top:null,label:'Consensus',note:'',read:''}),
  pyJSON:code=>code.includes('draft_act') ? {ok} : latest};
vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('function renderDraftDay('),src.indexOf('\nlet offersCache')),ctx);
ctx.renderDraftDay(latest);
assert.equal(ctx.boardRound,1);
latest=view(2);
find(page,n=>n.tag==='button'&&n.children.includes('Sim to Your Pick')).onclick();
assert.equal(ctx.boardRound,2,'sim across rounds follows the pick');
assert.ok(find(page,n=>n.children?.includes('Round 2 of 3')));
find(page,n=>n['aria-label']==='Previous round').onclick();
assert.equal(ctx.boardRound,1,'manual previous-round browsing remains available');
ok=false;
find(page,n=>n.tag==='button'&&n.children.includes('Next Pick')).onclick();
assert.equal(ctx.boardRound,1,'failed actions do not move the board');
ok=true;latest=view(3);
find(page,n=>n.tag==='button'&&n.children.includes('Next Pick')).onclick();
assert.equal(ctx.boardRound,3,'one-pick advancement also follows a round boundary');
console.log('Passed: cross-round simulation, manual browsing, failed action, one-pick round advance');
