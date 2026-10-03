const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('docs/app.js', 'utf8');
const start = source.indexOf('function developmentPanel(');
const end = source.indexOf('// THE YEAR CHOOSER', start);
function el(tag, attrs, ...children) {
  return {tag, attrs, children, append(...items) { this.children.push(...items); }};
}
let data;
const context = {el, pyJSON: () => data};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const defaults = {bank:776, dev:'x1.00', bought:8, practice_earned:7992, rows:[],
  unlock_cost:7240, unlock_ok:false, auto:false, ovr:71, pos:'RT', development_ovr:73};
function rendered(overrides) {
  data = {...defaults, ...overrides};
  return JSON.stringify(context.developmentPanel('p', () => {}));
}
let text = rendered({ceiling:'72–90', ceiling_estimated:true});
assert.ok(text.includes('every 500 career snaps'));
assert.ok(text.includes('each completed season'));
assert.ok(!text.includes('Confirmed development ceiling'));
text = rendered({ceiling:73, ceiling_estimated:false, ceiling_reason:'reached', at_ceiling:true, learning_penalty:2.4});
assert.ok(text.includes('Confirmed development ceiling'));
assert.ok(text.includes('Underlying development overall: 73'));
assert.ok(text.includes('displayed overall to 71'));
assert.ok(text.includes('Unlock +1 to resume attribute growth'));
assert.ok(!text.includes('above his 71'));
text = rendered({ceiling:85, ceiling_estimated:false, ceiling_reason:'age', at_ceiling:false});
assert.ok(text.includes('Confirmed at age 28'));
assert.ok(!text.includes('Development ceiling reached'));
console.log('Development panel: estimate rules, age confirmation, and position-learning explanation passed.');
