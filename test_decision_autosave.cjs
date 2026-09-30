const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const src = fs.readFileSync('docs/app.js', 'utf8');
let response = {ok:true}, queued = [], saves = 0;
const context = {py:{runPython:()=>JSON.stringify(response)}, queueMicrotask:fn=>queued.push(fn), saveGameNotified:()=>{saves++;}};
vm.createContext(context);
vm.runInContext(src.slice(src.indexOf('function cutPenaltyText'), src.indexOf('async function newGame')), context);
function run(code, result) {
  response = result;
  const before = saves;
  vm.runInContext(`pyJSON(${JSON.stringify(code)})`, context);
  while (queued.length) queued.shift()();
  return saves - before;
}
for (const call of ["SESSION.inbox_offer_sheet(42, 'match')", "SESSION.inbox_offer_sheet(42, 'decline')", "SESSION.inbox_hurt_action(42, 'ir')", "SESSION.club_act('cut', pid='p')", "SESSION.trade_offer_answer(42, 'counter')", "SESSION.trade_offer_answer(42, 'accept')", "SESSION.trade_offer_answer(42, 'decline')", "SESSION.personnel_act('save_trade_counter', msg_id=42)"]) {
  assert.equal(run(call, {ok:true}), 1, call);
  assert.equal(run(call, {ok:false, why:'stale'}), 0, call);
}
assert.equal(run("SESSION.personnel_act('offer_preview', pid='p', apy=12, years=3)", {ok:true}), 0);
assert.equal(vm.runInContext('cutPenaltyText({penalty:10,penalty_next:20})', context), '$10.0m this year + $20.0m next year');
assert.equal(vm.runInContext('cutPenaltyText({penalty:30,penalty_next:0})', context), '$30.0m this year');
console.log('Decision autosave success/refusal, read-only preview, and penalty text passed.');
