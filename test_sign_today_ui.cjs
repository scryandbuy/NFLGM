const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('docs/app.js','utf8');
let calls=[],feedback=[],refreshes=0,result={ok:true,state:'accepted'};
const context={el:(tag,attrs,...children)=>({tag,attrs,children}),
  pyJSON:call=>{calls.push(call);return result;},notify:r=>feedback.push(r)};
vm.createContext(context);
vm.runInContext(src.slice(src.indexOf('function signTodayButton('),src.indexOf('function offerForm(')),context);
const t={id:9,ask:2,years:1,sign_today_offer:{apy:2.32,years:1,bonus:.5,front_load:.5,promises:[]}};
for(const compact of [false,true]) {
 const b=context.signTodayButton(t,()=>refreshes++,compact);
 assert.match(b.children[0],/2\.32/);
 assert.match(b.attrs['data-tip'],/0\.50m signing bonus/);
 b.attrs.onclick();
 assert.equal(calls.at(-1),"SESSION.personnel_act('offer', tid=9, apy=2.32, years=1, bonus=0.5, front_load=0.5, sign_today=True)");
 assert.equal(feedback.at(-1).state,'accepted');
 result={ok:false,why:'Not enough available cap room.'};b.attrs.onclick();
 assert.equal(feedback.at(-1).why,result.why);
 // Defensive compatibility: older engines must not silently hide a refusal.
 result={ok:true,state:'open',line:'Another club is talking to him.'};b.attrs.onclick();
 assert.equal(feedback.at(-1).ok,false);assert.equal(feedback.at(-1).why,result.line);
 result={ok:true,state:'accepted'};
}
assert.equal(refreshes,6);
assert.equal(context.signTodayButton({id:9},()=>{}).tag,'span');
assert.match(src,/acts\.append\(signTodayButton\(t, onDone\)\)/);
assert.match(src,/signTodayButton\(v\.threads\.find/);
console.log('Sign Today UI: displayed terms, submitted terms, both entry points, and visible failures pass.');
