const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const src = fs.readFileSync(path.join(__dirname, 'docs/app.js'), 'utf8');
const helpers = src.slice(src.indexOf('function gameDayIndicators('));
const context = vm.createContext({});
vm.runInContext(helpers, context);
const state = (...args) => JSON.parse(JSON.stringify(context.gameDayIndicators(...args)));
const g = {home: {abbr:'GB',name:'Green Bay',nick:'PACKERS'}, away: {abbr:'MIN',name:'Minnesota',nick:'VIKINGS'}, drives:[
  {quarter:2,off:'GB',plays:[
    {type:'complete',text:'Catch',quarter:2},
    {type:'timeout',text:'Timeout, GB (2 left).',quarter:2,timeout_side:'home',timeouts_left:2},
    {type:'timeout',text:'Timeout, MIN (1 left).',quarter:2,timeout_side:'away',timeouts_left:1}]},
  {quarter:3,off:'MIN',plays:[{type:'run',text:'Run',quarter:3}]}
]};
assert.deepEqual(state(g,1,1).timeouts,{GB:3,MIN:3});
assert.deepEqual(state(g,1,2).timeouts,{GB:2,MIN:3});
assert.deepEqual(state(g,1,3).timeouts,{GB:2,MIN:1});
assert.deepEqual(state(g,2,1).timeouts,{GB:3,MIN:3});
assert.deepEqual(state(g,1,null,{halftime_open:true,adjustment_period:'halftime'}).timeouts,{GB:3,MIN:3});
assert.deepEqual(state(g,1,null,{halftime_open:true,adjustment_period:'overtime',playoffs:false}).timeouts,{GB:2,MIN:2});
assert.deepEqual(state(g,1,null,{halftime_open:true,adjustment_period:'overtime',playoffs:true}).timeouts,{GB:3,MIN:3});
assert.equal(state(g,2,null).possession,null);
assert.equal(state(g,0,0,{possession:'MIN'}).possession,'MIN');
assert.equal(state(g,1,null,{possession:null}).possession,null);
const legacy = structuredClone(g);
delete legacy.drives[0].plays[1].timeout_side;
delete legacy.drives[0].plays[1].timeouts_left;
assert.equal(state(legacy,1,2).timeouts.GB,2);
const turnover=structuredClone(g);
turnover.drives[0].plays=[{type:'interception',text:'Intercepted',quarter:2}];
assert.equal(state(turnover,1,1).possession,'MIN');
turnover.drives[0].plays[0].nullified=true;
assert.equal(state(turnover,1,1).possession,'GB');
console.log('13 scoreboard-state assertions passed');

async function browserCheck() {
  const {chromium} = require('C:/Users/HP/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1280,height:400}});
    await page.setContent('<main class="gameday-page" style="display:block;padding:35px;--team-base:#203731;--team-readable:#ffbf18"><section class="sheet game-scoreboard"><div class="bigbug" id="bug"></div></section></main>');
    await page.addStyleTag({path:path.join(__dirname,'docs/style.css')});
    const elSource=src.slice(src.indexOf('const el ='),src.indexOf('const esc ='));
    await page.addScriptTag({content:elSource+'\n'+helpers});
    await page.evaluate(({home,away})=>{
      const indicators={possession:'GB',timeouts:{GB:1,MIN:3}};
      const bug=document.querySelector('#bug');
      bug.append(el('div',{class:'side'},gameDayTeamStatus(away,'4–3',indicators),el('div',{class:'score',style:'margin-left:auto'},17)),
        el('div',{class:'mid'},el('div',{class:'q'},'Q4 · 1:24'),el('div',{class:'dd'},'2nd & 6 · MIN 34')),
        el('div',{class:'side home-side',style:'flex-direction:row-reverse;text-align:right'},gameDayTeamStatus(home,'5–2',indicators),el('div',{class:'score',style:'margin-right:auto'},20)));
    },g);
    assert.equal(await page.locator('.timeout-dot').count(),6);
    assert.equal(await page.locator('.timeout-dot.available').count(),4);
    assert.equal(await page.locator('.possession-football.has-ball').count(),1);
    assert.equal(await page.locator('.possession-football.has-ball').getAttribute('aria-label'),'Green Bay possession');
    assert.equal(await page.locator('.home-side .timeout-dots').getAttribute('aria-label'),'Green Bay: 1 timeout remaining');
    const shot=process.argv[2];
    if(shot) await page.screenshot({path:path.resolve(shot)});
    // A spent timeout empties the same three-dot row, including the last one.
    await page.evaluate(()=>document.querySelector('.home-side .team-status').replaceWith(gameDayTeamStatus(
      {abbr:'GB',name:'Green Bay',nick:'PACKERS'},'5–2',{possession:'MIN',timeouts:{GB:0,MIN:3}})));
    assert.equal(await page.locator('.home-side .timeout-dot').count(),3);
    assert.equal(await page.locator('.home-side .timeout-dot.available').count(),0);
    assert.equal(await page.locator('.home-side .possession-football.has-ball').count(),0);
    console.log('8 browser indicator assertions passed');
  } finally { await browser.close(); }
}
browserCheck().catch(error=>{console.error(error);process.exitCode=1;});
