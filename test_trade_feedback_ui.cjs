const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('docs/app.js','utf8');
const code=src.slice(src.indexOf('function notify('),src.indexOf('// Each team owns'))+
  src.slice(src.indexOf('function tradeFeedbackKey('),src.indexOf('function renderTrades('));
const nodes={'#action-feedback':{hidden:false},'#action-feedback-text':{textContent:'old'},'#dismiss-feedback':{}};
const ctx={JSON,tradeState:{other:'ARI',a:[],b:[]},showAbbr:x=>x,$:s=>nodes[s],
 el:(tag,attrs={},...children)=>{const e={tag,attrs,children,textContent:children.filter(x=>typeof x==='string').join(''),hidden:attrs.hidden!=null,dataset:{read:attrs['data-read']},append(...xs){this.children.push(...xs);}};if(attrs.id)nodes['#'+attrs.id]=e;return e;}};
vm.createContext(ctx);vm.runInContext(code,ctx);
const message="We're still competing, and this deal would weaken our lineup too much.";
const view={can_trade:true,them:{club:{abbr:'ARI'}},package:{read:message,verdict:'blocked',my_read:'Change the package.',roster_after:{me:53},cap_after:{me:10}}};
ctx.renderTradeSummary(view,()=>{});ctx.notify({ok:false,why:message});
assert.equal(nodes['#action-feedback'].hidden,true,'no top notification');
assert.equal(nodes['#trade-action-feedback'].hidden,true,'existing bottom verdict is not duplicated');
ctx.notify({ok:false,why:'The full counteroffer is no longer available.'});
assert.equal(nodes['#trade-action-feedback'].hidden,false,'distinct failures remain visible at bottom');
ctx.renderTradeSummary(view,()=>{});
assert.equal(nodes['#trade-action-feedback'].hidden,false,'failure survives unchanged rerender');
ctx.tradeState.a=[{kind:'player',id:'new-player'}];ctx.renderTradeSummary(view,()=>{});
assert.equal(nodes['#trade-action-feedback'].hidden,true,'editing package clears stale action feedback');
delete nodes['#trade-action-feedback'];ctx.notify({ok:false,why:'Save failed.'});
assert.equal(nodes['#action-feedback'].hidden,false,'other screens retain their error feedback');
console.log('Trade feedback: bottom only, no duplicate, rerender persistence, stale clearing, other pages preserved.');
