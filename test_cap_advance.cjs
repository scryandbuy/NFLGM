const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const src = fs.readFileSync('docs/app.js', 'utf8');
let notices = [], calls = [];
const context = {
  location: {hash: '#portal'},
  practiceSaving: false, practiceSaveRequired: false,
  notify: n => notices.push(n), busy: () => {}, setTimeout: () => {}, renderRail: () => {},
  pyJSON: code => {
    calls.push(code);
    if (code === 'SESSION.blocking()') return [{kind:'cap', subject:'You are $3.00m over the cap', go:'#frontoffice/cap'}];
    if (code === 'SESSION.portal()') return {rail:{}};
    throw Error('Unexpected engine call: ' + code);
  },
};
vm.createContext(context);
vm.runInContext(src.slice(src.indexOf('async function advanceInner()'), src.indexOf('// ---------------------------------------------------------------- start')), context);
(async () => {
  await vm.runInContext('advanceInner()', context);
  assert.equal(context.location.hash, '#frontoffice/cap');
  assert.match(notices[0].why, /Open Cap to choose your contract moves/);
  assert.equal(calls.includes('SESSION.advance()'), false);
  console.log('Cap block opens the Cap page without advancing the engine.');
})().catch(e => { console.error(e); process.exitCode = 1; });
