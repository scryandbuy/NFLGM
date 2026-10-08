// Render the actual UI and CSS against view fixtures from a running draft.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const src=fs.readFileSync('docs/app.js','utf8'),root=process.argv[2]||'outputs/draft-broadcast';
const chunk=(a,b)=>src.slice(src.indexOf(a),src.indexOf(b));
const ui=`${chunk('const DISPLAY_ABBR','const $ =')}${chunk('const $ =','const esc =')}
${chunk('function featureHero(','function stripe(')}
${chunk('function ord(','function offerSheetActions')}
${chunk('function persPage(','function contractShapeEditor') .split('\n').slice(0,2).join('\n')}
${chunk('function teamTheme(','function tradeSelection(')}
${src.split('\n').find(x=>x.startsWith('function ovrCell('))}
${chunk('const draftAvailableSources =','let draftRunning =')}
${chunk('const draftDaySelections =','let offersCache = null;')}
let boardRound=null,offersCache=null,draftRunning=null,tradeState={},currentView,nextView,commands=[],accept=true,ok=true;
const renderRail=()=>{},drSecond=()=>{},notify=()=>{};
window.confirm=()=>accept;
function pyJSON(code){commands.push(code);if(code.includes("draft_act('offers')"))return {ok:true,offers:[{i:2,team:currentView.order[0].team,summary:['R2 pick','R3 pick']}]};if(code.includes('draft_act'))return {ok};return nextView||currentView;}
function runDraftBatch(mode,round){commands.push([mode,round]);boardRound=null;load(nextView||currentView);}
function load(v){currentView=v;renderDraftDay(v);}
`;
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1461,height:1188}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.setContent('<main id="page"></main>');await page.addStyleTag({content:fs.readFileSync('docs/style.css','utf8')});await page.addScriptTag({content:ui});
 const initial=JSON.parse(fs.readFileSync(path.join(root,'initial.json'),'utf8'));
 const progress=JSON.parse(fs.readFileSync(path.join(root,'progress.json'),'utf8'));
 const restored=JSON.parse(fs.readFileSync(path.join(root,'reload.json'),'utf8'));
 await page.evaluate(v=>load(v),progress);
 assert.equal(await page.locator('.dd-tile').count(),32);
 assert.equal(await page.locator('.dd-tile.done').count(),4);
 assert.equal(await page.locator('.dd-rounds button').count(),7);
 assert.doesNotMatch(await page.locator('.dd-board').innerText(),/selections made|Team colors/);
 for(const row of progress.order.filter(q=>q.round===1&&!q.done&&!q.mine&&!q.now)){
  const tile=page.locator('.dd-tile').filter({has:page.locator('.dd-tile-head>span',{hasText:new RegExp('^'+row.sel+'$')})});
  assert.equal(await tile.locator('.dd-tile-name').innerText(),'');
  assert.doesNotMatch(await tile.innerText(),/Round|Rd /);
 }
 for(const width of [1461,1024,768,390,320]){
  await page.setViewportSize({width,height:1188});
  const size=await page.evaluate(()=>({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth}));
  assert(size.sw<=size.cw+1,`overflow at ${width}: ${JSON.stringify(size)}`);
  for(const cls of ['.dd-tile','.dd-candidate'])assert.equal(await page.locator(cls).evaluateAll(ns=>ns.filter(n=>n.scrollWidth>n.clientWidth+1).length),0,cls+' clips at '+width);
 }
 await page.setViewportSize({width:1461,height:1188});
 await page.screenshot({path:path.join(root,'draft-desktop.png'),fullPage:true});
 const picked=progress.order.find(q=>q.done);await page.locator('.dd-tile.done').first().click();
 assert.equal(await page.locator('.dd-detail-name').getAttribute('href'),'#club/player/'+picked.pid);
 const target=progress.order.find(q=>q.round===1&&!q.done&&!q.mine);
 await page.getByRole('button',{name:new RegExp('^Pick '+target.sel+',')}).click();await page.getByRole('button',{name:'Trade for This Pick',exact:true}).click();
 assert.deepEqual(await page.evaluate(()=>tradeState.b),[target.id]);
 assert.equal(await page.evaluate(()=>location.hash),'#personnel/trades');
 await page.evaluate(v=>{location.hash='#draft/day';load(v);},restored);
 assert.equal(await page.locator('.dd-tile.done').count(),4,'reload preserves drafted rows');
 await page.getByRole('button',{name:'Your Board',exact:true}).click();
 assert.equal(await page.locator('.dd-detail-name').innerText(),restored.board[0].name);
 await page.getByRole('button',{name:'Consensus',exact:true}).click();
 assert.equal(await page.locator('.dd-detail-name').innerText(),restored.best[0].name);
 // Crossing a round follows the actual current pick; manual round browsing survives failed actions.
 const user=structuredClone(restored),pick=user.order.find(q=>q.round===2&&q.mine);
 user.on_user=true;user.current={...pick,needs:['CB']};user.mine_next=[pick];user.picks_away=0;user.order.forEach(q=>q.now=q.sel===pick.sel);
 await page.evaluate(v=>nextView=v,user);await page.getByRole('button',{name:'Sim to Your Pick',exact:true}).click();
 assert.equal(await page.getByRole('button',{name:'Round 2',exact:true}).getAttribute('aria-pressed'),'true');
 await page.getByRole('button',{name:'Round 1',exact:true}).click();await page.evaluate(()=>ok=false);await page.getByRole('button',{name:'Auto Pick',exact:true}).click();
 assert.equal(await page.getByRole('button',{name:'Round 1',exact:true}).getAttribute('aria-pressed'),'true');
 await page.evaluate(()=>{ok=true;commands=[];accept=false;});
 await page.locator('.dd-candidate').nth(1).click();
 await page.locator('.dd-detail-actions .go').click();assert.equal(await page.evaluate(()=>commands.length),0,'canceled draft does not pick');
 await page.evaluate(()=>accept=true);await page.locator('.dd-detail-actions .go').click();
 assert((await page.evaluate(()=>commands[0])).includes(JSON.stringify(user.best[1].pid)),'manual pick uses selected prospect');
 await page.getByRole('button',{name:'Trade Down',exact:true}).click();assert.equal(await page.locator('.dd-offer').count(),1);
 await page.getByRole('button',{name:'Decline',exact:true}).click();assert.equal(await page.locator('.dd-offer').count(),0);
 await page.evaluate(v=>{v.best=[];v.board=[];v.mine_next=[];v.on_user=false;load(v);},structuredClone(initial));
 assert.match(await page.locator('.dd-candidates').innerText(),/No eligible prospects/);
 assert.match(await page.locator('.dd-next').innerText(),/No picks remaining/);
 await page.evaluate(v=>{v.live=false;v.last=null;v.note='The draft comes after the Spring.';load(v);},structuredClone(initial));
 assert.equal(await page.locator('.dd-clock').count(),0);
 assert.deepEqual(errors,[]);await browser.close();
 console.log('Draft browser checks passed: responsive layout, approved removals, real drafted player links, trade pick loading, board sources, selected player confirmation, offers, round following, empty states and saved draft reload.');
})().catch(e=>{console.error(e);process.exit(1);});
