const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('docs/app.js','utf8');
function el(tag,attrs={},...children){return {tag,attrs,children,style:{},append(...xs){this.children.push(...xs);}};}
function button(node,label){if(node.tag==='button'&&node.children.includes(label))return node;
 for(const c of node.children||[])if(c&&typeof c==='object'){const b=button(c,label);if(b)return b;}}
const page=el('main'),nav={querySelectorAll:()=>[]};let data;
const context={el,pyJSON:()=>data,renderRail(){},secondRow(){},clubNav(){},
 $:s=>s==='#page'?page:s==='#nav'?nav:{},reportBoard:()=>el('section'),ovrCell:x=>x};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function developmentPanel('),source.indexOf('// THE YEAR CHOOSER')),context);
vm.runInContext(source.slice(source.indexOf('function renderProgression('),source.indexOf('function renderProspectCard(')),context);
const base={bank:10,dev:'normal',bought:0,rows:[],auto:false,unlock_cost:100,unlock_ok:false};
for(const ready of [false,true]){
 data={...base,can_spend:ready};
 const b=button(context.developmentPanel('p',()=>{}),'Spend by Read');
 assert.equal(b.attrs.disabled,ready?null:'');
 page.children=[];
 context.renderProgression({rail:{club:{abbr:'GB'}},bank_total:10,idle:ready?1:0,rows:[
  {pid:'p',name:'Player',pos:'WR',age:29,ovr:92,bank:10,cheapest:20,can_buy:ready,bought:0,career:0,auto:false}]});
 assert.equal(button(page,'Spend').attrs.disabled,ready?null:'');
 assert.equal(button(page,'Spend All by Read').attrs.disabled,ready?null:'');
}
assert.ok(!source.includes('Ceiling Details'));
assert.ok(!source.includes('No eligible automatic upgrade'));
console.log('Spend buttons agree with backend readiness; no added ceiling controls or explanatory hovers.');
