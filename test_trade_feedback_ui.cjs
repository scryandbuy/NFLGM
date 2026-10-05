const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('docs/app.js','utf8');
const code=src.slice(src.indexOf('function showTradeResult('),src.indexOf('function renderTrades('));
const dialogs=[];
const ctx={JSON,Number,tradeState:{other:'BAL',a:[{kind:'player',id:'brown'}],b:[{kind:'player',id:'hamilton'}]},showAbbr:x=>x,
 document:{body:{append(x){dialogs.push(x);}}},
 el:(tag,attrs={},...children)=>({tag,attrs,children,append(...xs){this.children.push(...xs)},addEventListener(){},showModal(){this.open=true},focus(){},close(){this.open=false}})};
vm.createContext(ctx);vm.runInContext(src.slice(src.indexOf('function playerMention('),src.indexOf('function messageText(')),ctx);vm.runInContext(code,ctx);
const view={can_trade:true,me:{club:{abbr:'GB'},roster:[{pid:'brown',name:'Isaac Brown'}],picks:[]},them:{club:{abbr:'BAL'},roster:[{pid:'hamilton',name:'Kyle Hamilton'}],picks:[]},package:{interest:65,interest_band:'high',read:'Need more value',my_read:'unwanted text'}};
const tree=ctx.renderTradeSummary(view,()=>{});
assert(!JSON.stringify(tree).includes('unwanted text'));
const actions=tree.children[0];const propose=actions.children.findIndex(x=>x.children?.includes('Propose'));
assert.equal(actions.children[propose-1].attrs.class,'trade-interest');
assert.equal(actions.children[propose-1].attrs['data-band'],'high');
ctx.showTradeResult({done:false,why:'We need more value.'},view,[],[]);
assert(JSON.stringify(dialogs.at(-1)).includes('Trade Rejected'));
assert(!JSON.stringify(dialogs.at(-1)).includes('roster after'));
ctx.showTradeResult({done:true},view,ctx.tradeState.a,ctx.tradeState.b);
const text=JSON.stringify(dialogs.at(-1));for(const value of ['Trade Accepted','GB receives','BAL receives','Isaac Brown','Kyle Hamilton'])assert(text.includes(value));
console.log('Trade bar placement, popup rejection and accepted package verified.');

assert(text.includes('#club/player/brown'));assert(text.includes('#club/player/hamilton'));
const rowCode=src.slice(src.indexOf('function tradeAssetRow('),src.indexOf('function renderTradePackage('));ctx.jerseyNo=x=>x;vm.runInContext(rowCode,ctx);
for(const selected of [false,true]){const row=ctx.tradeAssetRow({roster:[{pid:'same-name-2',short:'J. Smith',pos:'HB',yrs:1,hit:1,penalty:0,ovr:80}]},{kind:'player',id:'same-name-2'},selected,()=>{},'a');assert(JSON.stringify(row).includes('#club/player/same-name-2'));}
