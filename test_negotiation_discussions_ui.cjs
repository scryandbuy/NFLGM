const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('docs/app.js','utf8');
function node(tag,attrs={},...children){return {tag,attrs,children,style:{setProperty(){}},append(...xs){this.children.push(...xs)},replaceChildren(...xs){this.children=xs},addEventListener(){},querySelectorAll(){return[]}};}
const ctx={el:node,requestAnimationFrame:fn=>fn(),tradeState:{a:[],b:[]},playerMention:(_,name)=>name,jerseyNo:x=>x};
vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('function tradeSelection('),src.indexOf('function renderTradeSide(')),ctx);
const own={club:{name:'Green Bay'},roster:[{pid:'q',short:'Quarterback',pos:'QB'},{pid:'t',short:'Tackle',pos:'LT'}],picks:[{id:'2030-1-GB',words:'2030 First Round',own_words:'Own',round:1}]};
const ui={mode:'players',query:'',position:'',scroll:0};
const picker=ctx.renderTradePicker(own,[],ui,()=>{},'a');
const [tools,rows]=picker.children,position=tools.children.find(n=>n.tag==='select');
assert.equal(rows.children.length,2);
position.attrs.onchange({target:{value:'LT'}});assert.equal(rows.children.length,1);assert(JSON.stringify(rows).includes('Tackle'));assert(!JSON.stringify(rows).includes('Quarterback'));
tools.children[1].attrs.onclick({currentTarget:tools.children[1]});assert.equal(position.hidden,true);assert(JSON.stringify(rows).includes('2030 First Round'));
tools.children[0].attrs.onclick({currentTarget:tools.children[0]});assert.equal(position.hidden,false);assert.equal(rows.children.length,1);
const another=ctx.tradePickerState('DEN');assert(!another.position);assert.equal(ui.position,'LT');
const page=node('main');let proposalCalls=0,discussionCalls=0;
Object.assign(ctx,{renderRail(){},persPage:()=>page,persSecond(){},$:()=>({}),window:{scrollY:0,scrollTo(){}},applyTeamTheme(){},teamTheme:()=>({base:'#000'}),showAbbr:x=>x,
 renderTradeSide:()=>{proposalCalls++;return node('section')},renderTradeSummary:()=>node('footer'),renderTradeDiscussion:()=>{discussionCalls++;return node('section')},pyJSON(){throw Error('Rendering must not submit anything')}});
vm.runInContext(src.slice(src.indexOf('function renderTrades('),src.indexOf('function signTodayButton(')),ctx);
const view={rail:{},other:{abbr:'DEN'},clubs:[],can_trade:true,me:{...own,club:{abbr:'GB'}},them:{...own,club:{abbr:'DEN'}},discussion:{stage:'talk'}};
ctx.renderTrades(view);assert.equal(discussionCalls,1);assert.equal(proposalCalls,0);
ctx.renderTrades({...view,discussion:{stage:'ready'}});assert.equal(discussionCalls,2);assert.equal(proposalCalls,0);
ctx.renderTrades({...view,discussion:{stage:'proposal'}});assert.equal(discussionCalls,2);assert.equal(proposalCalls,2);
ctx.tradeState.counter_id=99;ctx.renderTrades(view);assert.equal(proposalCalls,4,'saved incoming counter stays usable');
assert(src.includes("'Open Proposal'"));
console.log('Trade conversation/proposal separation, full assets, per-team position filtering, pick visibility and incoming counters pass.');
