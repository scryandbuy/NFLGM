"""Render production markup/styles against the audited franchise view, no engine actions."""
from pathlib import Path
import json
import re

out=Path('outputs/upcoming-fa');out.mkdir(parents=True,exist_ok=True)
s=Path('docs/app.js').read_text(encoding='utf-8')
def chunk(a,b):return s[s.index(a):s.index(b)]
ui=chunk('const DISPLAY_ABBR','const esc =')+chunk('const PERS =','function crest(')+chunk('function teamTheme(','function tradeSelection(')+chunk('const upcomingFA =','let faPos =')+chunk('function faFilterGroups(','function renderFA(')
for name in ['ovrCell','fitCell','stripe']:
    ui+='\n'+next(line for line in s.splitlines() if line.startswith('function '+name+'('))
ui+='\nfunction renderRail(){}\nfunction secondRow(items,current){document.querySelector("#second").replaceChildren(...items.map(([label,href])=>el("a",{href,"aria-current":href===current?"page":null},label)));}\n'
view=json.loads((out/'view.json').read_text(encoding='utf-8'))
ui+='\nrenderUpcomingFA('+json.dumps(view)+');'
html=Path('docs/index.html').read_text(encoding='utf-8')
html=re.sub(r'<script.*?</script>','',html,flags=re.S)
html=re.sub(r'<link rel="stylesheet"[^>]+>','<link rel="stylesheet" href="style.css">',html)
html=html.replace('<div id="boot">','<div id="boot" hidden>').replace('id="rail" hidden','id="rail"').replace('id="page" hidden','id="page"')
for ident,value in [('clubname','Green Bay'),('crest','GB'),('coach','Your Franchise'),('st-week','Week 4'),('st-year','2033')]:
    html=re.sub(r'(id="'+ident+r'"[^>]*>)[^<]*',lambda m:m[1]+value,html)
html=html.replace('</body>','<script src="preview.js"></script></body>')
(out/'index.html').write_text(html,encoding='utf-8')
(out/'preview.js').write_text(ui,encoding='utf-8')
(out/'style.css').write_text(Path('docs/style.css').read_text(encoding='utf-8'),encoding='utf-8')
print(out)
