const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('docs/app.js', 'utf8');
const line = source.split('\n').find(s => s.includes('if (v.actions.can_captain)'));
assert.ok(line, 'The player card offers the captain appointment action');
const calls = [], notices = [], renders = [];
let response = {ok: true};
const context = {
  v: {pid: 'p123', captain: false, actions: {can_captain: true}},
  acts: {children: [], append(node) {this.children.push(node);}},
  el: (tag, attrs, ...children) => ({tag, attrs, children}),
  pyJSON: code => {calls.push(code); return response;},
  notify: result => notices.push(result),
  renderCard: result => renders.push(result),
};
vm.createContext(context);
vm.runInContext(line, context);
let button = context.acts.children.pop();
assert.equal(button.children[0], 'Name Captain');
button.attrs.onclick();
assert.equal(calls[0], `SESSION.club_act('captain', pid="p123", on=True)`);
assert.equal(calls[1], `SESSION.club_card("p123")`);
assert.equal(renders.length, 1);
context.v.captain = true;
vm.runInContext(line, context);
button = context.acts.children.pop();
assert.equal(button.children[0], 'Remove Captaincy');
response = {ok: false, why: 'Only a player on your roster or injured reserve can be named captain.'};
button.attrs.onclick();
assert.equal(calls[2], `SESSION.club_act('captain', pid="p123", on=False)`);
assert.equal(renders.length, 1, 'Rejected appointments keep the current card');
assert.equal(notices.at(-1).ok, false);
context.v.actions.can_captain = false;
vm.runInContext(line, context);
assert.equal(context.acts.children.length, 0, 'No appointment control for an ineligible player');
assert.ok(source.includes("v.pos + (v.captain ? ' | Captain' : '')"), 'Cards show appointed captains');
console.log('Captain action: appointment/removal, error feedback, refresh, eligibility and visible title.');
