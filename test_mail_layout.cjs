const fs = require('fs');
const vm = require('vm');
const assert = require('node:assert/strict');
const src = fs.readFileSync('docs/app.js', 'utf8');
const el = (tag, attrs={}, ...children) => ({tag,attrs,children,append(...nodes){this.children.push(...nodes);}});
const ctx = {el, document:{createTextNode:text=>({text})}, encodeURIComponent,
  applyTeamTheme(node, team){node.theme=team.abbr;}};
vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('function playerMention('),src.indexOf('function renderRecapBody(')),ctx);
const all = node => [node, ...(node.children || []).flatMap(all)];
const links = node => all(node).filter(n=>n.tag==='a');
// Identical names belong to distinct players. A non-BMP prefix uses two code units.
const body = '🏈 Mike Smith (WR, $10.5m)\nMike Smith (HB, $2m)';
const second = body.indexOf('Mike Smith', 4);
const msg = {body, body_rows:body.split('\n'), mentions:{body:[
  {kind:'player',id:'first',start:3,end:13},
  {kind:'player',id:'second',start:second,end:second+10}
]}};
let rendered = ctx.renderMailBody(msg);
assert.equal(rendered.children.length, 1);
assert.deepEqual(links(rendered).map(n=>n.attrs.href), ['#club/player/first','#club/player/second']);
assert.equal(rendered.children[0].attrs.class,'mail-prose');
const cell = text=>({text,mentions:[]});
rendered=ctx.renderMailBody({mail_intro:cell('Two signings'),mail_sections:[{
  title:'Signings', columns:['Player','Salary'], rows:[[
    {text:'Mike Smith',mentions:[{kind:'player',id:'a',start:0,end:10}]},cell('$10.5m')
  ],[cell('<script>bad()</script>'),cell('$2m')]]
}]});
assert.equal(all(rendered).filter(n=>n.tag==='th').length,2);
assert.equal(all(rendered).filter(n=>n.tag==='td').length,4);
assert.equal(links(rendered)[0].attrs.href,'#club/player/a');
assert.equal(all(rendered).filter(n=>n.tag==='script').length,0);
assert.ok(all(rendered).some(n=>n.text==='<script>bad()</script>'));
rendered=ctx.renderMailBody({body:'A short confirmation.',body_rows:['A short confirmation.']});
assert.equal(rendered.children.length,1);
rendered=ctx.renderMailBody({mail_layout:'trade',mail_sections:[
  {title:'Green Bay Receive',team:'GB',rows:[[cell('Player A')],[cell('2027 R1')]]},
  {title:'Minnesota Receive',team:'MIN',rows:[[cell('Player B')]]}
]});
assert.ok(rendered.attrs.class.includes('mail-trade'));
assert.equal(rendered.children.length,2);
assert.deepEqual(rendered.children.map(n=>n.theme),['GB','MIN']);
assert.equal(all(rendered).filter(n=>n.attrs?.class==='mail-body-row').length,3);
// Old saved digests and new grouped digests show identical exchanges. Player
// links survive the compact rating layout; picks retain multiplicity/provenance.
const asset = {text:'Trey McBride (TE, 90)',mentions:[{kind:'player',id:'trey',start:0,end:12}]};
const trades = [
  {title:'NJ and DAL make a trade · New Jersey Receive',team:'NJ',rows:[[asset]]},
  {title:'NJ and DAL make a trade · Dallas Receive',team:'DAL',rows:[[cell('a 2033 third-round pick')],[cell('a 2032 second-round pick')],[cell('a 2032 second-round pick')],[cell('2032 R4 (GB)')]]},
  {title:'Signings',columns:[],rows:[[cell('A signing remains visible.')]]},
  {title:'BUF and NO make a trade · Buffalo Receive',team:'BUF',rows:[[cell('Erik McCoy (C, 86)')]]},
  {title:'BUF and NO make a trade · New Orleans Receive',team:'NO',rows:[[cell('a 2032 seventh-round pick')]]}
];
const snapshot = JSON.stringify(trades);
const legacyRendered = ctx.renderMailBody({mail_sections:trades});
assert.equal(JSON.stringify(trades),snapshot);
assert.equal(all(legacyRendered).filter(n=>n.attrs?.class==='mail-exchange').length,2);
assert.equal(links(legacyRendered)[0].attrs.href,'#club/player/trey');
assert.deepEqual(all(legacyRendered).filter(n=>n.theme).map(n=>n.theme),['NJ','DAL','BUF','NO']);
const textOf = n => typeof n === 'string' ? n : n.text || (n.children || []).map(textOf).join(' ');
const tradeText = textOf(legacyRendered);
assert.ok(tradeText.includes('2032 R2/R2'));
assert.ok(tradeText.includes('2032 R4 (GB)'));
assert.ok(tradeText.includes('A signing remains visible.'));
assert.ok(!tradeText.includes('make a trade'));
const current = trades.map((s,i) => i===2 ? s : {...s,trade_group:i<2?'first':'second',title:s.title.split(' · ')[1]});
assert.equal(textOf(ctx.renderMailBody({mail_sections:current})),tradeText);
// Unmatched legacy halves are never paired with a different trade.
assert.equal(ctx.mailTradePair({mail_sections:[trades[0],trades[4]]},0),null);
assert.ok(!src.includes('Going into ${v.year + 1}'));
console.log('Mail sections, columns, legacy rows, namesake links, UTF-16 offsets, and safe text rendering passed.');
