const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('docs/app.js','utf8');
const calls = []; let reloads = 0;
const context = {
  el: (tag,attrs,...children) => ({tag,attrs,children}),
  pyJSON: call => {calls.push(call); return {ok:true}}, notify(){}
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function gameplanSuggestion'),source.indexOf('function renderThisWeek')),context);
function button(node,label) {
  if(node?.tag==='button' && node.children.includes(label)) return node;
  for(const child of node?.children || []) {const found=button(child,label); if(found)return found;}
}
let row=context.gameplanSuggestion({i:2,text:'Advice',why:'Reason',taken:false,skipped:false},()=>reloads++);
button(row,'Skip').attrs.onclick();
assert.equal(calls.pop(),"SESSION.plan_act('skip', i=2, skip=True)");
assert.equal(reloads,1);
row=context.gameplanSuggestion({i:2,text:'Advice',why:'Reason',taken:false,skipped:true},()=>reloads++);
assert.ok(JSON.stringify(row).includes('Skipped'));
button(row,'Restore').attrs.onclick();
assert.equal(calls.pop(),"SESSION.plan_act('skip', i=2, skip=False)");
button(row,'Accept').attrs.onclick();
assert.equal(calls.pop(),"SESSION.plan_act('take', i=2)");
row=context.gameplanSuggestion({i:2,text:'Advice',why:'Reason',taken:true},()=>reloads++);
button(row,'Undo').attrs.onclick();
assert.equal(calls.pop(),"SESSION.plan_act('untake', i=2)");
assert.ok(!button(row,'Skip'));
console.log('This Week advice: Skip, Restore, Accept and Undo call the session and refresh.');
