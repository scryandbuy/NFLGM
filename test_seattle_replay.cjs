const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('docs/app.js', 'utf8');
const definition = source.match(/function replayPlayPoints\(play\) \{[\s\S]*?\n\}/)[0];
const score = vm.runInNewContext(`(${definition})`);

test('replay credits blocked-punt touchdown and try to the recovering defense', () => {
  const plays = [{type:'punt',td:true,scoring_side:'defense'},
                 {type:'extra_point',made:true,scoring_side:'defense'}];
  assert.equal(plays.reduce((sum,p)=>sum+score(p),0),-7);
  assert.equal(score({type:'two_point',made:true,scoring_side:'defense'}),-2);
  assert.equal(score({type:'punt',safety:true}),-2);
});
test('ordinary scoring, failed attempts and nullified plays remain correct', () => {
  assert.equal(score({type:'complete',td:true}),6);
  assert.equal(score({type:'field_goal',made:true}),3);
  assert.equal(score({type:'field_goal',made:false}),0);
  assert.equal(score({type:'extra_point',made:true}),1);
  assert.equal(score({type:'punt',td:true,scoring_side:'defense',nullified:true}),0);
  assert.equal(score({type:'kickoff'}),0);
});
