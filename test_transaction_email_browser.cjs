const fs = require('fs');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const src = fs.readFileSync('docs/app.js','utf8');
const cell = text => ({text, mentions:[]});
const sides = [
  {title:'NJ and DAL make a trade · New Jersey Receive',team:'NYJ',rows:[[{text:'Trey McBride (TE, 90)',mentions:[{kind:'player',id:'trey',start:0,end:12}]}]]},
  {title:'NJ and DAL make a trade · Dallas Receive',team:'DAL',rows:[[cell('Chase Kashubara (DT, 77)')],[cell('a 2033 third-round pick')],[cell('a 2032 second-round pick')],[cell('a 2032 third-round pick')]]},
  {title:'BUF and NO make a trade · Buffalo Receive',team:'BUF',rows:[[cell('Erik McCoy (C, 86)')]]},
  {title:'BUF and NO make a trade · New Orleans Receive',team:'NO',rows:[[cell('a 2032 seventh-round pick')],[cell('a 2033 second-round pick')],[cell('a 2032 fourth-round pick')]]}
];
(async()=>{
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    const page = await browser.newPage();
    await page.setContent('<section class="inbox-board"><div class="mailbox" style="display:block"><div class="pane"><div class="inbox-reading-top"><div class="inbox-eyebrow">League</div><span class="inbox-status">Read</span></div><h3>Transactions</h3><div class="from">2030 · Week 9</div></div></div></section>');
    await page.addStyleTag({content:fs.readFileSync('docs/style.css','utf8')});
    await page.addStyleTag({content:'body{--team-accent:#ffb612}.inbox-board{margin:0!important}.mailbox{min-height:0!important;height:auto!important}.pane{min-height:0!important;height:auto!important}'});
    await page.addScriptTag({content:src.slice(0,src.indexOf('let py =')) + src.slice(src.indexOf('function playerMention('),src.indexOf('function renderRecapBody(')) + src.slice(src.indexOf('function teamTheme('),src.indexOf('function tradeSelection('))});
    await page.evaluate(sides => document.querySelector('.pane').append(renderMailBody({mail_sections:sides})), sides);
    for (const width of [800,540,320]) {
      await page.setViewportSize({width,height:1000});
      const result = await page.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,
        groups:document.querySelectorAll('.mail-exchange').length,cols:getComputedStyle(document.querySelector('.mail-exchange-sides')).gridTemplateColumns,
        exchangeHeight:document.querySelector('.mail-exchange').getBoundingClientRect().height,
        text:document.querySelector('.mail-content').textContent}));
      assert.ok(result.scroll<=result.width,JSON.stringify(result));
      assert.equal(result.groups,2);
      assert.ok(!result.text.includes('make a trade'));
      assert.ok(result.text.includes('2032 R2/R3'));
      if(width===800) { assert.equal(result.cols.split(' ').length,2); assert.ok(result.exchangeHeight<120,JSON.stringify(result)); }
      if(width===320) assert.equal(result.cols.split(' ').length,1);
      console.log(width,result.cols,'no overflow');
      if(width===800 && process.env.MAIL_SCREENSHOT) await page.locator('.pane').screenshot({path:process.env.MAIL_SCREENSHOT});
    }
    await page.locator('a[href="#club/player/trey"]').click();
    assert.ok(page.url().endsWith('#club/player/trey'));
    console.log('Responsive transaction email and player navigation passed.');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
