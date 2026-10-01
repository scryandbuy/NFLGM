const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('docs/app.js', 'utf8');
class Element {
  constructor(tag, attrs = {}, ...children) { this.tag = tag; this.attrs = attrs; this.children = children; this.disabled = attrs.disabled != null; }
  append(...children) { this.children.push(...children); }
  addEventListener(name, fn) { this.attrs['on' + name] = fn; }
  querySelectorAll(selector) {
    const tags = selector.split(',').map(x => x.trim());
    return this.children.flatMap(x => x instanceof Element ? [...(tags.includes(x.tag) ? [x] : []), ...x.querySelectorAll(selector)] : []);
  }
  showModal() { this.open = true; }
  close() { this.open = false; this.attrs.onclose?.(); }
  remove() { this.removed = true; }
  focus() {}
}
const events = {}, docEvents = {}, calls = [], themedTeams = [], body = new Element('body');
let state = {key:'2026:1:GB', locked:false, dirty:false, started:false}, page, failure = false;
const fixture = () => ({rail:{club:{name:'Green Bay',abbr:'GB'}}, plan_state:{...state}, week:1,
  opp:{name:'Minnesota',abbr:'MIN'}, suggestions:[{i:0,text:'Advice A',why:'Reason',taken:true,side:'offense'},
    {i:1,text:'Advice B',why:'Reason',taken:false,skipped:true,side:'defense'}],
  leans:[{key:'tempo',side:'offense',label:'Tempo',base:.5,value:.5,min:.3,max:.7}],
  depth:{value:[.5,.3,.2],base:[.5,.3,.2],labels:['Short','Medium','Deep']},
  protection:{value:'six',options:[{key:'six',word:'Six-man'}]},their_wrs:[],wr_out:[],
  unit_table:[],stars:[],injured:[],record:'0–0'});
const context = {
  console, URL, Number, Promise,
  window:{addEventListener:(name, fn)=>events[name]=fn},
  document:{body,addEventListener:(name, fn)=>docEvents[name]=fn},
  location:{hash:'#gameplan/week',href:'http://localhost/#gameplan/week',origin:'http://localhost',pathname:'/'},
  history:{replaceState(_s,_t,url){context.restored=url;}},
  $: selector=>body.children.find(x=>!x.removed && '#' + x.attrs?.id === selector),
  el:(...args)=>new Element(...args), py:{},
  notify(result){context.notice=result;},
  saveGame:async()=>{if(failure)throw Error('disk full');},
  renderRail(){},persPage(){page=new Element('main');return page;},featureHero(){},
  applyTeamTheme(_node, team){themedTeams.push(team.abbr);},
  showAbbr:x=>x,surname:x=>x,ord:()=>'',
  pyJSON(code) {
    calls.push(code);
    if(code.includes("plan_view('status')"))return {...state};
    if(code.includes('plan_view'))return fixture();
    if(code.includes("plan_act('save')"))state={...state,locked:true,dirty:false};
    else if(code.includes("plan_act('save_failed')"))state={...state,locked:false,dirty:true};
    else if(code.includes("plan_act('reopen')"))state={...state,locked:false};
    else state={...state,dirty:true};
    context.updateGameplanState({...state});
    return {ok:true,plan_state:{...state}};
  },
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('// ---------------------------------------------------------------- Game Plan'),source.indexOf('// ---------------------------------------------------------------- flow')),context);
context.gpSecond=()=>{};
const run=code=>vm.runInContext(code,context);
function button(label) {return page.querySelectorAll('button').find(x=>x.children.includes(label));}
function reset(next={}) {state={key:'2026:1:GB',locked:false,dirty:false,started:false,...next};context.updateGameplanState({...state});}

(async()=>{
  reset({dirty:true});context.renderThisWeek(fixture());
  assert.ok(button('Accept All'));
  await context.saveSundayPlan(()=>context.renderThisWeek(fixture()));
  assert.ok(!button('Accept All'));assert.ok(!button('Save Plan for Sunday'));
  assert.ok(button('Re-Open Game Plan'));assert.ok(!button('Undo'));assert.ok(!button('Restore'));
  assert.ok(page.querySelectorAll('input').every(x=>x.disabled));
  button('Re-Open Game Plan').attrs.onclick();
  assert.ok(button('Undo'));assert.ok(button('Restore'));assert.ok(button('Accept All'));
  assert.ok(!context.gameplanUnsaved());
  reset({locked:true});context.renderReport(fixture());
  assert.ok(themedTeams.includes('MIN'));
  assert.ok(button('Re-Open Game Plan'));assert.ok(!button("Accept All and Open This Week's Plan"));
  assert.ok(!button('Accept'));assert.ok(!button('Undo'));

  reset({dirty:true});failure=true;
  await context.saveSundayPlan(()=>context.renderThisWeek(fixture()));
  assert.equal(state.locked,false);assert.equal(state.dirty,true);
  assert.match(context.notice.why,/could not be saved/);
  assert.ok(button('Save Plan for Sunday'));
  failure=false;
  run('gameplanPendingDepth = [45, 35, 20]');
  calls.length=0;
  await context.saveSundayPlan(()=>{});
  assert.ok(calls[0].includes('set_depth'));assert.ok(calls[1].includes("plan_act('save')"));
  assert.ok(!context.gameplanUnsaved());

  const oldURL='http://localhost/#gameplan/week';
  context.location.hash='#club';reset({dirty:true});
  assert.equal(context.guardGameplanRoute({oldURL}),true);
  assert.equal(context.restored,oldURL);
  assert.ok(body.children.some(x=>x.attrs?.id==='gameplan-warning' && x.open));
  context.location.hash='#gameplan/report';
  assert.equal(context.guardGameplanRoute({oldURL}),false);
  let prevented=false;
  events.beforeunload({preventDefault(){prevented=true;}});assert.ok(prevented);
  reset({key:'2026:2:GB'});prevented=false;
  events.beforeunload({preventDefault(){prevented=true;}});assert.ok(!prevented);
  context.location.hash='#club';assert.equal(context.guardGameplanRoute({oldURL}),false);
  reset({dirty:true});context.location.hash='#gameplan/week';prevented=false;
  docEvents.click({target:{closest:()=>({href:'http://localhost/#club'})},preventDefault(){prevented=true;},stopImmediatePropagation(){}});
  assert.ok(prevented);
  console.log('Game plan UI: lock/reopen, both pages, save failure, pending inputs, navigation and unload guards passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
