const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('docs/app.js', 'utf8');
const html = fs.readFileSync('docs/index.html', 'utf8');
const css = fs.readFileSync('docs/style.css', 'utf8');
const nodes = {
  '#action-feedback': {hidden: true},
  '#action-feedback-text': {textContent: ''},
  '#dismiss-feedback': {},
};
let result = {ok: true}, calls = [], refreshes = 0;
const context = {
  $: selector => { assert.ok(nodes[selector], selector); return nodes[selector]; },
  el: (tag, attrs, ...children) => ({tag, attrs, children}),
  pyJSON: call => { calls.push(call); return result; },
  setTimeout() { throw Error('Action feedback must not schedule a popup timer'); },
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function notify('), source.indexOf('// Each team owns its panel palette')), context);
vm.runInContext(source.slice(source.indexOf('function gameplanSuggestion'), source.indexOf('function renderThisWeek')), context);
function button(node, label) {
  if (node?.tag === 'button' && node.children.includes(label)) return node;
  for (const child of node?.children || []) { const found = button(child, label); if (found) return found; }
}
const row = context.gameplanSuggestion({i: 2, text: 'Advice', why: 'Reason', taken: false, skipped: false}, () => refreshes++);
button(row, 'Accept').attrs.onclick();
assert.equal(calls.pop(), "SESSION.plan_act('take', i=2)");
assert.equal(refreshes, 1);
assert.equal(nodes['#action-feedback'].hidden, true, 'Accept applies and refreshes without a popup');
result = {ok: false, why: 'Re-open your saved plan first.'};
button(row, 'Accept').attrs.onclick();
assert.equal(refreshes, 2);
assert.equal(nodes['#action-feedback'].hidden, false);
assert.equal(nodes['#action-feedback-text'].textContent, result.why);
nodes['#dismiss-feedback'].onclick();
assert.equal(nodes['#action-feedback'].hidden, true);
for (const failure of [{ok:false}, {error:'Save failed'}, {why:'Unavailable'}]) {
  context.notify(failure);
  assert.equal(nodes['#action-feedback'].hidden, false);
  assert.ok(nodes['#action-feedback-text'].textContent);
}
for (const success of [{ok:true,line:'Done'}, {ok:true,why:'Accepted'}, {done:'Week 1'}, null]) {
  context.notify(success);
  assert.equal(nodes['#action-feedback'].hidden, true);
}
assert.ok(html.indexOf('id="action-feedback"') < html.indexOf('<main id="page"'), 'Errors survive page re-render');
assert.doesNotMatch(source, /\bbusy\s*\(|position:fixed[^\n]*bottom:/, 'No shared or direct bottom banners remain');
assert.doesNotMatch(html, /id="busy"/);
assert.doesNotMatch(css, /\.busy\s*[{[]/);
console.log('Global action feedback: coach accept stays immediate; failures remain readable/dismissible; no bottom popup paths.');
