const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const src = fs.readFileSync('docs/app.js', 'utf8');
const code = src.slice(src.indexOf('function openTradeOffer('), src.indexOf('\nfunction openTalks('));
function setup({ok=true, status='open', counter=null, hash='#portal/inbox'}={}) {
  const calls=[], themes=[], body=[];
  let reloads=0, rails=0;
  const draft={other:'DEN',a:[{kind:'player',id:'user-player'}],b:[{kind:'pick',id:'2027-3-DEN'}]};
  const v={ok:true,id:7,buyer:{abbr:'DEN',name:'Denver'},me:{abbr:'GB',name:'Green Bay'},
    they:[{kind:'pick',id:'2027-3-DEN',label:'2027 round 3 pick'}],you:[{kind:'player',id:'user-player',label:'Example',pos:'HB',age:25,ovr:80,apy:2}],
    open:status==='open',status,counter,read:'Fair return',expires:0};
  const ctx={JSON, Number, document:{body:{append(x){body.push(x);}}},location:{hash},tradeState:{},showAbbr:abbr=>abbr,
    el:(tag,attrs={},...children)=>({tag,attrs,children,removed:false,style:{setProperty(){}},append(...x){this.children.push(...x);},remove(){this.removed=true;}}),
    applyTeamTheme:(node,team)=>{themes.push(team.abbr);return {base:'#123',accent:'#abc'};},
    pyJSON:query=>{calls.push(query);if(query.includes('trade_offer_view'))return v;if(query==='SESSION.portal()')return {rail:{}};if(query.includes('trade_offer_answer'))return {ok,counter:draft};return {};},
    notify:()=>{},renderRail:()=>rails++,renderTrades:()=>reloads++};
  vm.createContext(ctx);vm.runInContext(code,ctx);ctx.openTradeOffer(7,()=>reloads++);
  const walk=node=>[node,...(node.children||[]).filter(x=>typeof x==='object').flatMap(walk)];
  const buttons=()=>walk(body[0]).filter(x=>x.tag==='button');
  const click=text=>{const b=buttons().find(x=>x.children.includes(text));assert.ok(b,text);b.attrs.onclick();};
  return {ctx,body,calls,themes,click,buttons,draft,rails:()=>rails,reloads:()=>reloads};
}
for(const [label,action] of [['Accept','accept'],['Decline','decline'],['Counter','counter']]) {
  const t=setup();t.click(label);
  assert.ok(t.calls.includes(`SESSION.trade_offer_answer(7, "${action}")`));
  assert.equal(t.rails(),1,'resolve refreshes header blockers');
  assert.equal(t.body[0].removed,true);
  assert.deepEqual(t.themes,['DEN','DEN','GB'],'each panel uses its own team');
  if(action==='counter') {
    assert.equal(t.ctx.location.hash,'#personnel/trades');
    assert.equal(t.ctx.tradeState.counter_id,7);
    assert.deepEqual(t.ctx.tradeState.a,t.draft.a);
    assert.deepEqual(t.ctx.tradeState.b,t.draft.b);
  } else assert.equal(t.reloads(),1);
}
const failed=setup({ok:false});failed.click('Accept');
assert.equal(failed.body[0].removed,false,'failed trade stays open');assert.equal(failed.rails(),0);
const resume=setup({status:'countered',counter:{state:'draft'}});resume.click('Continue Counter');assert.equal(resume.ctx.tradeState.counter_id,7);
const closed=setup({status:'countered',counter:{state:'accepted'}});assert.equal(closed.buttons().length,1,'closed counter only has Close');
const same=setup({hash:'#personnel/trades'});same.click('Counter');assert.equal(same.reloads(),1,'same-route counter renders immediately');
console.log('Trade popup actions, failure retention, resume, team themes and header refresh passed.');
