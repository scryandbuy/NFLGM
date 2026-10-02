// Exercise the shipped offer form's events without loading an entire league.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(tag, attrs, children) { this.tag=tag; this.attrs={...attrs}; Object.assign(this,attrs); this.children=children; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children=children; }
  setAttribute(key,value) { this.attrs[key]=value; }
  querySelectorAll(selector) {
    const found=[];
    for(const child of this.children) if(child instanceof Element) {
      if(selector[0]==='.' ? (child.attrs.class||'').split(' ').includes(selector.slice(1)) : child.tag===selector) found.push(child);
      found.push(...child.querySelectorAll(selector));
    }
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0]||null; }
}
const calls=[], timers=[];
let invalid=false;
const context={el:(tag,attrs,...children)=>new Element(tag,attrs,children), setTimeout:fn=>timers.push(fn),
  pyJSON:code=>{calls.push(code);return invalid?{ok:false,why:'Invalid bonus'}:
    {ok:true,year1:19,total:95,hits:[19,19,19,19,19],years:[2026,2027,2028,2029,2030],
      interest:{interest:'Terms meet his expectations',reasons:['More money secured upfront']}};},
  extensionImpact:()=>new Element('div',{},[]), notify:()=>{}};
vm.createContext(context);
const source=fs.readFileSync('docs/app.js','latin1');
vm.runInContext(source.slice(source.indexOf('function offerForm('),source.indexOf('// one line per open talk')),context);
const form=context.offerForm({id:1,pid:'player',ask:20,years:2},'fa_offseason',()=>{},
  {apy:19,years:5,bonus:40,front_load:.85,promises:['no_trade']});
timers.shift()();
assert.match(calls.at(-1),/apy=19, years=5, bonus=40, front_load=0.85/);
assert.match(calls.at(-1),/promises=\["no_trade"\]/);
assert.match(form.querySelector('.offer-interest').textContent,/More money secured upfront/);
const buttons=form.querySelectorAll('button');
const noTrade=buttons.find(b=>b.children.includes('No Trade'));
assert.equal(noTrade.attrs['aria-pressed'],'true');
noTrade.onclick({currentTarget:noTrade});
assert.match(calls.at(-1),/promises=\[\]/);
const shape=buttons.find(b=>b.children.includes('Back-Load'));
shape.onclick({currentTarget:shape});
assert.match(calls.at(-1),/front_load=0.15/);
invalid=true;
form.querySelectorAll('input')[0].oninput();
assert.equal(form.querySelector('.offer-interest').textContent,'');
assert.equal(form.querySelector('.extension-impact-slot').hidden,false);
console.log('Offer form: preset package, promises, structure, live interest and invalid-state checks passed.');
