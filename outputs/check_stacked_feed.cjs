// Real renderer + production CSS, with current/live/legacy engine view fixtures.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=process.argv[2] || 'outputs/broadcast';
const src=fs.readFileSync('docs/app.js','utf8');
const chunk=(a,b)=>src.slice(src.indexOf(a),src.indexOf(b));
// Keep initialization out: extract only helpers and the Game Day functions.
const ui=`
${chunk('const DISPLAY_ABBR','const $ =')}
${chunk('const $ =','const esc =')}
${chunk('function ord(','function offerSheetActions')}
${chunk('let gameDayStepBusy','// ---------------------------------------------------------------- Club:')}
${chunk('function teamTheme(','function applyTeamTheme')}
${chunk('const halfConfirmed','// Team reports share')}
${chunk('function gameDayIndicators(','let salaryState')}
let currentView,steps=[],copies=[];
const renderRail=()=>{},featureHero=()=>{};
const weekName=n=>n>=19?['Wild Card','Divisional','Conference','Championship'][n-19]:'Week '+n;
function pyJSON(code){
 if(code==='SESSION.gameday_view()')return currentView;
 if(code==='SESSION.portal()')return {rail:currentView.rail};
 if(code.startsWith('SESSION.live_step')){steps.push(JSON.parse(code.match(/\\((.*)\\)/)[1]));return currentView;}
 if(code.startsWith('SESSION.half_take'))return currentView;
 throw Error(code);
}
async function saveLiveJournalNotified(){} async function saveGameNotified(){}
function copyText(t){copies.push(t)}
function load(v){currentView=v;renderGameDay(v)}
`;
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1461,height:1188}}), errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const css=fs.readFileSync('docs/style.css','utf8');
 await page.setContent('<div id="crumb"></div><nav id="nav"></nav><div id="second"></div><main id="page"></main>');
 await page.addStyleTag({content:css});await page.addScriptTag({content:ui});
 const fixture=name=>JSON.parse(fs.readFileSync(path.join(root,name+'.json'),'utf8'));
 const load=async name=>page.evaluate(v=>load(v),fixture(name));
 await load('live');
 assert.equal(await page.locator('.timeout-dot').count(),6);
 assert.deepEqual(await page.locator('[data-live-step]').allTextContents(),['Next Play','Next Drive','To Final']);
 await page.getByRole('button',{name:'Next Play',exact:true}).click();
 await page.getByRole('button',{name:'Next Drive',exact:true}).click();
 await page.getByRole('button',{name:'To Final',exact:true}).click();
 assert.deepEqual(await page.evaluate(()=>steps),['play','drive','finish']);
 for(const width of [1461,1024,768,390]){
  await page.setViewportSize({width,height:1188});
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  const before=await page.locator('.gd-team-stats').boundingBox();
  await page.getByRole('button',{name:'All Stats',exact:true}).click();
  const after=await page.locator('.gd-team-stats').boundingBox();
  assert.equal(before.height,after.height,`fixed team height ${width}`);
  const fit=await page.evaluate(()=>{
   const wrap=document.querySelector('.gd-team-scroll'),table=wrap.querySelector('table'),last=table.querySelector('tr>*:last-child');
   return {content:wrap.scrollWidth<=wrap.clientWidth,table:table.getBoundingClientRect().right<=wrap.getBoundingClientRect().right-6,
    page:document.documentElement.scrollWidth<=innerWidth,home:last.textContent};
  });
  assert(fit.content&&fit.table&&fit.page,JSON.stringify({width,fit}));
  assert(fit.home);
 }
 await page.setViewportSize({width:1461,height:1188});
 await load('final');
 assert.equal(await page.locator('.gd-latest').count(),0);
 assert.equal(await page.locator('.gd-heading').count(),0);
 assert.equal(await page.locator('.gd-log').count(),1);
 assert.equal(await page.locator('.gd-live-column .gd-log').count(),1);
 assert.equal(await page.locator('.gd-lower .gd-log').count(),0);
 await page.getByRole('button',{name:'Every Play',exact:true}).click();
 assert.equal(await page.locator('.gd-log .gd-play').count(),fixture('final').game.drives.flatMap(d=>d.plays).filter(p=>p.text).length);
 await page.locator('.gd-log').evaluate(e=>{e.scrollTop=0;e.dispatchEvent(new Event('scroll'));});
 await page.getByRole('button',{name:'All Stats',exact:true}).click();
 assert.equal(await page.locator('.gd-log').evaluate(e=>e.scrollTop),0);
 await page.locator('.gd-log').evaluate(e=>{e.scrollTop=e.scrollHeight;e.dispatchEvent(new Event('scroll'));});
 await page.getByRole('button',{name:'Overview',exact:true}).click();
 assert(await page.locator('.gd-log').evaluate(e=>e.scrollHeight-e.clientHeight-e.scrollTop<8));
 console.log('PASS: one stacked feed under field, all events retained, scroll position preserved, heading removed');
 
 assert.equal(await page.locator('[data-live-step]').count(),0);
 for(const category of ['Passing','Rushing','Receiving','Defense','Blocking','Kicking','Punting','Returns','Snaps']){
  await page.getByRole('button',{name:category,exact:true}).click();
  assert.equal(Math.round((await page.locator('.gd-player-stats').boundingBox()).height),420);
  assert(await page.locator('.gd-player-table tbody tr').count()>0);
 }
 await page.getByRole('button',{name:'Defense',exact:true}).click();
 await page.getByRole('button',{name:'Sacks',exact:true}).click();
 assert.equal(await page.locator('.gd-player-table th[aria-sort="descending"]').count(),1);
 await page.getByLabel('Player statistics team',{exact:true}).selectOption(fixture('final').game.me);
 assert(await page.locator('.gd-player-table tbody a').count()>3);
 assert(await page.locator('.gd-player-scroll').evaluate(e=>e.scrollHeight>e.clientHeight));
 assert((await page.locator('.gd-player-table tbody a').first().getAttribute('href')).startsWith('#club/player/'));
 await page.getByRole('button',{name:'Scoring',exact:true}).click();
 assert.equal(await page.locator('.gd-log .gd-play:not(.score)').count(),0);
 await page.getByRole('button',{name:'Copy',exact:true}).click();
 assert((await page.evaluate(()=>copies[0])).length>20);
 await page.screenshot({path:path.join(root,'broadcast-final.png'),fullPage:true});
 await load('halftime');
 assert(await page.locator('[data-live-step="finish"]').isDisabled());
 assert(await page.locator('[data-live-step="resume"]').isDisabled());
 await page.getByRole('button',{name:'Halftime Plan',exact:true}).click();
 await page.getByRole('button',{name:'Confirm',exact:true}).click();
 assert(!await page.locator('[data-live-step="resume"]').isDisabled());
 const overtime=fixture('halftime');overtime.live.adjustment_period='overtime';
 await page.evaluate(v=>load(v),overtime);
 assert(await page.locator('[data-live-step="resume"]').isDisabled(),'separate OT confirmation');
 await load('legacy');
 await page.getByRole('button',{name:'Blocking',exact:true}).click();
 assert((await page.locator('.gd-player-stats').innerText()).includes('not recorded'));
 const injured=fixture('live');injured.game.injuries=[{pid:'injury-test',name:'Injured Player',team:injured.game.home.abbr,pos:'CB',kind:'concussion',status:'Out for this game'}];
 await page.evaluate(v=>load(v),injured);await page.locator('.gd-injuries summary').click();
 assert.equal(await page.locator('.gd-injuries a').getAttribute('href'),'#club/player/injury-test');
 assert((await page.locator('.gd-injuries').innerText()).includes('Out for this game'));
 await load('live');await page.screenshot({path:path.join(root,'broadcast-live.png'),fullPage:true});
 assert.deepEqual(errors,[]);await browser.close();
 console.log('PASS: live controls, fixed stats at four widths, all nine categories, sorting/team filters, player links, scrolling, halftime/OT locks, legacy saves, no page errors');
})().catch(e=>{console.error(e);process.exit(1)});
