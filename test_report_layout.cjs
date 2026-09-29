const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('docs/app.js','utf8');
function el(tag,attrs={},...kids){return {tag,attrs,kids,dataset:{pid:attrs['data-pid']},classList:{toggle(){}},style:{},append(...x){this.kids.push(...x)},replaceChildren(...x){this.kids=x},querySelectorAll(){return this.kids.filter(x=>x?.attrs?.['data-pid'])}}}
const nodes={page:el('main'),crumb:el('span'),nav:{querySelectorAll:()=>[]}};
const c={el,$:s=>nodes[s.slice(1)],renderRail(){},secondRow(){},clubNav(){return[]},scheduleSeasonPicker(){return el('select')},location:{hash:''},regressionPopup(){}};vm.createContext(c);
vm.runInContext(src.slice(src.indexOf('function reportBoard'),src.indexOf('// the roster\'s development')),c);
vm.runInContext(src.slice(src.indexOf('function renderRegression'),src.indexOf('// THE ATTRIBUTE BLOCK')),c);
const row=(pid,name)=>({pid,name,pos:'QB',age:35,no:10,before:88,after:85,delta:-3,still_here:true,cols:[{rows:[{label:'Throw Power',v:80,delta:-4}]}]});
c.renderRegression({rail:{},club:{abbr:'GB',name:'Green Bay',color:'#203731',accent:'#ffb612'},year:2026,years:[2026],hit:2,total_lost:6,rows:[row('1','First'),row('2','Second')]});
const board=nodes.page.kids[0], layout=board.kids[2], table=layout.kids[0].kids[0], detail=layout.kids[1];
assert.equal(detail.kids[1].kids[0],'First');
const second=table.kids[2];second.kids[5].kids[0].attrs.onclick();assert.equal(detail.kids[1].kids[0],'Second');
console.log('Regression: populated detail, historical attribute values, and selection passed');
