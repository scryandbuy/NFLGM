const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const src = fs.readFileSync('docs/app.js', 'utf8');
const calls = [];
let unread = true, rendered;
const ctx = {Number, pyJSON(code) {
  calls.push(code);
  if (code === 'SESSION.inbox_read(8)') { unread = false; return {ok:true}; }
  assert.equal(code, 'SESSION.inbox_view()');
  return {rail:{club:{abbr:'GB'}}, inbox:{rows:[{id:8, unread}]}};
}, renderInbox(v) { rendered = v; }};
vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('function openInboxMessage('), src.indexOf('function renderInbox(')), ctx);
ctx.openInboxMessage(8);
assert.equal(rendered.inbox.rows[0].unread, false);
assert.deepEqual(calls, ['SESSION.inbox_view()', 'SESSION.inbox_read(8)', 'SESSION.inbox_view()']);
assert.ok(!src.includes('SESSION.portal_full()'));
console.log('Focused inbox loading and read refresh passed.');
