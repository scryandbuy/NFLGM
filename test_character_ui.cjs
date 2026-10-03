const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const src = fs.readFileSync('docs/app.js', 'utf8');
const context = {el: (tag, attrs = {}, ...children) => ({tag, attrs, children, append(...xs) {this.children.push(...xs);}})};
vm.createContext(context);
vm.runInContext(src.slice(src.indexOf('function characterReport('), src.indexOf('const TRAIT_META')), context);
const rows = [
  {label:'Work Ethic', status:'unknown', summary:'Not assessed', explanation:'Your scout trusts the tape.'},
  {label:'Discipline', status:'unknown', summary:'Not assessed', explanation:'', game_record:'2 committed, 1 accepted, 5 enforced yards.'},
  {label:'Discipline', status:'concern', summary:'Avoidable-penalty concerns', source:'Film assessment', confidence:'Limited', explanation:'An uncertain read.'}
];
const result = context.characterReport(rows);
assert.equal(result.children.length, 3);
const text = JSON.stringify(result);
for (const words of ['Work Ethic', 'Not assessed', 'Your scout trusts the tape.', 'Film assessment', 'Limited confidence']) assert.ok(text.includes(words));
assert.ok(!text.includes('2 committed'));
assert.ok(!text.includes('No assessment is available'));
assert.ok(!text.includes('undefined'));
assert.ok(!text.includes('null confidence'));
assert.ok(src.includes('characterReport(v.character_report)'));
assert.ok(!src.includes('Gains XP faster and keeps his condition'));
assert.ok(!src.includes('The slowest to improve, and condition slips'));
console.log('Character UI: concise unknown reads, no penalty row, and preserved assessment context.');
