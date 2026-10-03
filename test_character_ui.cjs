const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const src = fs.readFileSync('docs/app.js', 'utf8');
const context = {el: (tag, attrs = {}, ...children) => ({tag, attrs, children, append(...xs) {this.children.push(...xs);}})};
vm.createContext(context);
vm.runInContext(src.slice(src.indexOf('function characterReport('), src.indexOf('const TRAIT_META')), context);
const rows = [
  {label:'Work ethic', status:'unknown', summary:'Not assessed', explanation:'Your scout trusts the tape.'},
  {label:'Discipline', status:'concern', summary:'Avoidable-penalty concerns', source:'Film assessment', confidence:'Limited', explanation:'An uncertain read.', game_record:'2 committed, 1 accepted, 5 enforced yards.'}
];
const result = context.characterReport(rows);
assert.equal(result.children.length, 2);
const text = JSON.stringify(result);
for (const words of ['Not assessed', 'Film assessment', 'Limited confidence', '2 committed', '5 enforced yards']) assert.ok(text.includes(words));
assert.ok(!text.includes('undefined'));
assert.ok(!text.includes('null confidence'));
assert.ok(src.includes('characterReport(v.character_report)'));
assert.ok(!src.includes('Gains XP faster and keeps his condition'));
assert.ok(!src.includes('The slowest to improve, and condition slips'));
console.log('Character UI: separate observed assessments, confidence/source, factual penalties, and corrected work-ethic copy.');
