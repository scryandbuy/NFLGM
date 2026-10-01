// NFL GM — the browser app. Python engine in Pyodide; this file renders views and calls actions.

const ENGINE = 'engine/';
const CLUBS = ['ARI','ATL','BAL','BUF','CAR','CHI','CIN','CLE','DAL','DEN','DET','GB','HOU','IND','JAX','KC','LV','LAC','LA','MIA','MIN','NE','NO','NYG','NYJ','PHI','PIT','SF','SEA','TB','TEN','WAS'];
const DISPLAY_ABBR = {LAC:'CA', NYG:'NY', NYJ:'NJ'};
const showAbbr = abbr => DISPLAY_ABBR[abbr] || abbr;
// Presentation only: historical prose keeps canonical IDs in the saved data.
const showTeamText = text => String(text ?? '').replace(/\b(?:LAC|NYG|NYJ)\b/g, showAbbr);
const COLOR = {ARI:'#97233f',ATL:'#a71930',BAL:'#241773',BUF:'#00338d',CAR:'#0085ca',CHI:'#0b162a',CIN:'#fb4f14',CLE:'#311d00',DAL:'#003594',DEN:'#fb4f14',DET:'#0076b6',GB:'#203731',HOU:'#03202f',IND:'#002c5f',JAX:'#006778',KC:'#c8102e',LV:'#000000',LAC:'#0080c6',LA:'#003594',MIA:'#008e97',MIN:'#4f2683',NE:'#002244',NO:'#d3bc8d',NYG:'#0b2265',NYJ:'#125740',PHI:'#004c54',PIT:'#ffb612',SF:'#aa0000',SEA:'#002244',TB:'#d50a0a',TEN:'#0c2340',WAS:'#5a1414'};
const BOOT_TEAM = {ARI:['Arizona','#ffb612'],ATL:['Atlanta','#a71930'],BAL:['Baltimore','#9e7c0c'],BUF:['Buffalo','#c60c30'],CAR:['Carolina','#bfc0bf'],CHI:['Chicago','#c83803'],CIN:['Cincinnati','#fb4f14'],CLE:['Cleveland','#ff3c00'],DAL:['Dallas','#869397'],DEN:['Denver','#fb4f14'],DET:['Detroit','#b0b7bc'],GB:['Green Bay','#ffb612'],HOU:['Houston','#a71930'],IND:['Indianapolis','#e5e8ed'],JAX:['Jacksonville','#d7a22a'],KC:['Kansas City','#ffb81c'],LV:['Las Vegas','#a5acaf'],LAC:['California','#ffc20e'],LA:['Los Angeles','#ffa300'],MIA:['Miami','#fc4c02'],MIN:['Minnesota','#ffc62f'],NE:['New England','#c60c30'],NO:['New Orleans','#d3bc8d'],NYG:['New York','#a71930'],NYJ:['New Jersey','#d9e2dd'],PHI:['Philadelphia','#a5acaf'],PIT:['Pittsburgh','#ffb612'],SF:['San Francisco','#b3995d'],SEA:['Seattle','#69be28'],TB:['Tampa Bay','#ff7900'],TEN:['Tennessee','#4b92db'],WAS:['Washington','#ffb612']};

const $ = s => document.querySelector(s);
const el = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) { if (k === 'class') e.className = v; else if (k === 'html') e.innerHTML = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v !== null && v !== undefined) e.setAttribute(k, v); } for (const k of kids) if (k !== null && k !== undefined) e.append(k.nodeType ? k : document.createTextNode(String(k))); return e; };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

let py = null, team = null, view = null;

// ---------------------------------------------------------------- boot
const boot = { bar: $('#bootbar'), line: $('#bootline') };
const say = (t, pct) => { boot.line.closest('.boot-progress').hidden = false; boot.line.textContent = t; if (pct != null) { boot.bar.style.width = pct + '%'; boot.bar.parentElement.setAttribute('aria-valuenow', String(pct)); } };

// Shared identity navigation. Indexed once, then only newly rendered text is visited.
const NameLinks = (() => {
  let key = null, names = new Map(), pattern = null;
  const pending = new Set(), scopes = new WeakMap();
  let queued = false;
  const ignored = 'a,button,input,select,textarea,script,style,[contenteditable], [data-no-entity-links],.nm small';
  const escape = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const href = r => r.kind === 'player' ? '#club/player/' + encodeURIComponent(r.id) : '#league/team/' + encodeURIComponent(r.id);
  function setCatalog(data) {
    if (!data) return;
    key = data.key; names = new Map();
    for (const r of data.entities) {
      for (const label of new Set([r.name,...(r.aliases || [])])) {
        const k = label.toLocaleLowerCase();
        if (!names.has(k)) names.set(k, []);
        if (!names.get(k).some(x=>x.kind===r.kind && x.id===r.id)) names.get(k).push(r);
      }
    }
    pattern = names.size ? new RegExp([...names.keys()].sort((a,b)=>b.length-a.length).map(escape).join('|'), 'giu') : null;
    enqueue(document.body);
  }
  function sync() {
    if (typeof py === 'undefined' || !py) return;
    const data = JSON.parse(py.runPython(`_j(__import__('inbox').entity_catalog(SESSION.L, ${key ? JSON.stringify(key) : 'None'}))`));
    setCatalog(data);
  }
  function scope(node, refs) { scopes.set(node, refs || []); return node; }
  function resolve(name, parent) {
    const candidates = names.get(name.toLocaleLowerCase()) || [];
    for (let p=parent; p; p=p.parentElement) {
      const local = scopes.get(p)?.filter(r=>r.name.toLocaleLowerCase()===name.toLocaleLowerCase());
      if (local?.length === 1 && candidates.some(r=>r.kind===local[0].kind && r.id===local[0].id)) return local[0];
    }
    return candidates.length === 1 ? candidates[0] : null;
  }
  function convert(node) {
    const parent=node.parentElement;
    if (!parent || parent.closest(ignored) || !pattern || !node.textContent.trim()) return;
    const text=node.textContent, parts=[];let last=0;
    const cell=parent.closest('td');
    if (cell && /Home State/i.test(cell.closest('table')?.querySelector('tr')?.children[cell.cellIndex]?.textContent || '')) return;
    pattern.lastIndex=0;
    for (const m of text.matchAll(pattern)) {
      const end=m.index+m[0].length;
      if ((m.index && /[\p{L}\p{N}_]/u.test(text[m.index-1])) || (end<text.length && /[\p{L}\p{N}_]/u.test(text[end]))) continue;
      const target=resolve(m[0],parent);if(!target)continue;
      if (target.kind==='team' && m[0].length<=3 && (m[0]!==m[0].toUpperCase() || (m[0]==='NO' && text.trim()!=='NO'))) continue;
      // A player's home state is biography, not a reference to its team.
      if (target.kind==='team' && /Home State:\s*$/i.test(text.slice(0,m.index))) continue;
      parts.push(document.createTextNode(text.slice(last,m.index)));
      const link=document.createElement('a');link.className='entity-link';link.href=href(target);link.textContent=target.kind==='team' ? showAbbr(m[0]) : m[0];
      link.setAttribute('aria-label',`${target.name}: ${target.kind==='player'?'player card':'team overview'}`);
      link.addEventListener('click',e=>e.stopPropagation());
      parts.push(link);last=end;
    }
    if(!parts.length)return;
    parts.push(document.createTextNode(text.slice(last)));node.replaceWith(...parts);
  }
  function flush() {
    queued=false;observer.disconnect();
    const roots=[...pending];pending.clear();
    for(const root of roots) {
      if(!root.isConnected || roots.some(other=>other!==root && other.contains(root)))continue;
      if(root.nodeType===Node.TEXT_NODE){convert(root);continue;}
      if(root.nodeType!==Node.ELEMENT_NODE || root.closest(ignored))continue;
      const walk=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),nodes=[];
      while(walk.nextNode())nodes.push(walk.currentNode);
      nodes.forEach(convert);
    }
    observer.observe(document.body,{childList:true,subtree:true,characterData:true});
  }
  function enqueue(node) {if(!node)return;pending.add(node);if(!queued){queued=true;queueMicrotask(flush);}}
  const observer=new MutationObserver(records=>{for(const r of records){if(r.type==='characterData')enqueue(r.target);else for(const n of r.addedNodes)enqueue(n);}});
  observer.observe(document.body,{childList:true,subtree:true,characterData:true});
  return {sync,setCatalog,scope,flush};
})();
// End shared identity navigation.

async function bootEngine() {
  say('booting Python…', 4);
  const { loadPyodide } = await import('https://cdn.jsdelivr.net/pyodide/v0.29.5/full/pyodide.mjs');
  py = await loadPyodide({ indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.29.5/full/' });
  say('loading numpy and pandas…', 18);
  await py.loadPackage(['numpy', 'pandas', 'networkx']);      // networkx: the schedule builder's matching
  // the manifest is always re-checked with the server, and every engine file carries the
  // build stamp in its URL, so a new push is picked up on the next load instead of after
  // the browser's ten-minute cache expires
  const manifest = await (await fetch(ENGINE + 'manifest.json?t=' + Date.now(), { cache: 'no-store' })).json();
  window.ENGINE_BUILD = (manifest.build || '0').slice(0, 7);
  const files = [...manifest.modules.map(m => m + '.py'), ...manifest.data];
  let n = 0;
  for (const f of files) {
    const r = await fetch(ENGINE + f + '?v=' + (manifest.build || '0'));
    if (!r.ok) { say('missing ' + f); continue; }
    if (f.endsWith('.py') || f.endsWith('.json')) py.FS.writeFile('/' + f, await r.text());
    else py.FS.writeFile('/' + f, new Uint8Array(await r.arrayBuffer()));
    n++; say('loading engine… ' + f, 18 + 62 * n / files.length);
  }
  py.runPython(`import sys, os; sys.path.insert(0, '/'); os.chdir('/')`);
  py.runPython(`import json, session as S\nSESSION = None\ndef _j(x): return json.dumps(x)`);
  say('engine ready.', 84);
}

function cutPenaltyText(v, year) { return `$${v.penalty.toFixed(1)}m ${year == null ? 'this year' : year}${v.penalty_next ? ` + $${v.penalty_next.toFixed(1)}m ${year == null ? 'next year' : year + 1}` : ''}`; }
const AUTO_SAVE_METHODS = new Set(['club_act', 'personnel_act', 'frontoffice_act', 'draft_act', 'plan_act', 'practice_act', 'plan_take_all', 'trade_offer_answer', 'resign_act', 'exit_answer', 'inbox_offer_sheet', 'inbox_hurt_action', 'inbox_mark_all', 'inbox_read', 'inbox_later', 'inbox_delete', 'inbox_clear_read']);
const READ_ONLY_ACTIONS = new Set(['personnel_act:ask', 'personnel_act:gather', 'personnel_act:offer_preview', 'frontoffice_act:restructure_preview', 'draft_act:read_trade_up', 'draft_act:offers', 'plan_act:save', 'plan_act:save_failed']);
AUTO_SAVE_METHODS.add('inbox_roster_dismiss');
AUTO_SAVE_METHODS.add('dismiss_ceiling_notice');
let autosaveQueued = false;
let autosaveFrame = null, autosaveTimer = null;
function cancelAutosaveSchedule() {
  if (autosaveFrame !== null) cancelAnimationFrame(autosaveFrame);
  if (autosaveTimer !== null) clearTimeout(autosaveTimer);
  autosaveFrame = autosaveTimer = null;
}
function flushAutosave() {
  if (!autosaveQueued) return;
  autosaveQueued = false;
  cancelAutosaveSchedule();
  // Capture immediately, even if an earlier IndexedDB write is still pending.
  // queueSave preserves snapshot write order; pagehide must not defer capture.
  return saveGameNotified(true);
}
function queueAutosave() {
  if (autosaveQueued) return;
  autosaveQueued = true;
  if (document.visibilityState === 'hidden') { queueMicrotask(flushAutosave); return; }
  // One frame plus a task lets the changed UI paint before Python serializes.
  // The fallback also saves in throttled windows where frames stop arriving.
  autosaveTimer = setTimeout(flushAutosave, 200);
  autosaveFrame = requestAnimationFrame(() => {
    autosaveFrame = null;
    clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(flushAutosave, 0);
  });
}
if (typeof window !== 'undefined') window.addEventListener('pagehide', flushAutosave);
if (typeof document !== 'undefined') document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') void flushAutosave();
});
function pyJSON(code) {
  const result = JSON.parse(py.runPython(`_j(${code})`));
  if (result?.plan_state) updateGameplanState(result.plan_state);
  const call = code.match(/^SESSION\.([A-Za-z_][A-Za-z_0-9]*)\(\s*(?:'([^']*)'|"([^"]*)")?/);
  if (call && AUTO_SAVE_METHODS.has(call[1]) && !READ_ONLY_ACTIONS.has(`${call[1]}:${call[2] || call[3] || ''}`)
      && result !== false && result !== null && result?.ok !== false && !result?.error) queueAutosave();
  return result;
}

async function newGame(abbr) {
  say(`building the league for ${abbr}… (about a minute the first time)`, 88);
  await new Promise(r => setTimeout(r, 30));
  py.runPython(`SESSION = S.Session.new(${JSON.stringify(abbr)})`);
  say('ready.', 100);
}

// ---------------------------------------------------------------- save / load (IndexedDB)
function idb() { return new Promise((res, rej) => { const r = indexedDB.open('nflgm', 1); r.onupgradeneeded = () => r.result.createObjectStore('saves'); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); }); }
let saveQueue = Promise.resolve();
function queueSave(kind, value) {
  const write = async () => {
    const db = await idb();
    try {
      await new Promise((res, rej) => {
        const tx = db.transaction('saves', 'readwrite');
        const saves = tx.objectStore('saves');
        if (kind === 'full') { saves.put(value, 'main'); saves.delete('live_journal'); }
        else saves.put(value, 'live_journal');
        tx.oncomplete = res; tx.onerror = () => rej(tx.error);
      });
    } finally { db.close(); }
  };
  const pending = saveQueue.then(write, write);
  saveQueue = pending.catch(() => {});
  return pending;
}
function saveGame(silent = false) {
  autosaveQueued = false;
  cancelAutosaveSchedule();
  const text = py.runPython(`SESSION.save()`);
  return queueSave('full', text);
}
async function saveGameNotified(silent = false) {
  try { await saveGame(silent); }
  catch (e) { notify({ ok: false, why: 'The save failed: ' + String(e) }); }
}
function saveLiveJournal() {
  const journal = pyJSON('SESSION.live_journal()');
  return journal ? queueSave('journal', journal) : Promise.resolve();
}
async function saveLiveJournalNotified() {
  try { await saveLiveJournal(); }
  catch (e) { notify({ ok: false, why: 'The live game save failed: ' + String(e) }); }
}
async function loadSave() {
  const db = await idb();
  return new Promise(res => {
    const tx = db.transaction('saves', 'readonly'); const saves = tx.objectStore('saves');
    const main = saves.get('main'), journal = saves.get('live_journal');
    tx.oncomplete = () => { db.close(); res({ text: main.result || null, journal: journal.result || null }); };
    tx.onerror = () => { db.close(); res({ text: null, journal: null }); };
  });
}

// ---------------------------------------------------------------- the rail
function renderRail(r) {
  NameLinks.sync();
  syncGameplanState();
  queueCeilingNoticeCheck();
  // Overview owns its full-width page treatment; other routes use their own boards.
  $('#page').classList.remove('overview-page');
  $('#rail').hidden = false;
  const c = $('#crest'); c.textContent = showAbbr(r.club.abbr); c.style.background = r.club.color;
  personnelRailTeam = r.club; const palette = applyTeamTheme($('#rail'), r.club); document.documentElement.style.setProperty('--club', palette.base); document.documentElement.style.setProperty('--club-2', palette.accent);
  $('#clubname').textContent = r.club.name.toUpperCase(); $('#coach').textContent = r.coach;   // the title has its own line in the markup
  $('#st-record').textContent = r.record; $('#st-place').textContent = r.place; $('#st-cap').textContent = r.cap; const capLab = $('#st-cap').nextElementSibling; if (capLab) capLab.textContent = r.cap_next ? `${r.cap_year} Cap Space` : 'Cap Space'; $('#st-prestige').textContent = r.prestige ?? '—';
  $('#st-week').textContent = r.clock.line; $('#st-year').textContent = r.clock.sub + (window.ENGINE_BUILD ? ` · build ${window.ENGINE_BUILD}` : '');
  const badge = $('#badge'); badge.hidden = !r.inbox_unread; badge.textContent = r.inbox_unread;
  const adv = $('#advance');
  const hard = r.blocking.filter(b => b.kind !== 'live');
  if (r.blocking.length && r.blocking[0].kind === 'live') { adv.classList.remove('blocked', 'hard'); $('#adv-title').textContent = r.advance.title; $('#adv-sub').textContent = r.advance.sub || ''; }
  else if (r.advance.tone) { adv.classList.add('blocked'); adv.classList.toggle('hard', r.advance.tone === 'danger'); $('#adv-title').textContent = r.advance.title; $('#adv-sub').textContent = r.advance.sub || ''; }
  else if (hard.length) { adv.classList.add('blocked', 'hard'); $('#adv-title').textContent = 'Fix Before You Advance'; $('#adv-sub').textContent = hard.length === 1 ? hard[0].subject : `${hard.length} items block the advance`; }
  else { adv.classList.remove('blocked', 'hard'); $('#adv-title').textContent = r.advance.title; $('#adv-sub').textContent = r.advance.sub || ''; }
}

// ---------------------------------------------------------------- the Portal
function sheet(title, small, ...body) { return el('section', { class: 'sheet' }, el('h2', {}, title, small ? el('small', {}, small) : null), ...body); }
function featureHero(page, team, kicker, title, subtitle, metrics = []) {
  applyTeamTheme(page, team);
  const facts = el('div', { class: 'feature-hero-facts' });
  for (const [value, label] of metrics) facts.append(el('div', {}, el('strong', {}, String(value ?? '—')), el('span', {}, label)));
  page.append(el('header', { class: 'feature-hero c12' },
    el('div', {}, el('div', { class: 'feature-kicker' }, kicker), el('h1', {}, title), el('p', {}, subtitle)), facts));
}
// the last name, keeping a suffix with it: 'Marvin Mims Jr.' -> 'Mims Jr.', 'Odell Beckham III' -> 'Beckham III'
function surname(name) { const p = String(name || '').trim().split(' '); if (p.length >= 2 && /^(Jr\.?|Sr\.?|II|III|IV|V)$/.test(p[p.length - 1])) return p.slice(-2).join(' '); return p[p.length - 1] || ''; }
function stripe(abbr, text) { return el('span', { class: 'stripe', style: `--c:${COLOR[abbr] || '#555'}` }, text ?? showAbbr(abbr)); }
// a club's name as a link to its team page (your own club goes to Club)
function clubLink(abbr, text) { return el('a', {class:'clublink entity-link', href:`#league/team/${encodeURIComponent(abbr)}`, onclick:e=>e.stopPropagation()}, stripe(abbr, text)); }
function formDots(f, big = false) { return el('div', { class: 'form' + (big ? ' big-form' : '') }, ...f.map(x => el('i', { class: x }))); }

// the desk card's second button: where the decision is made
const DESK_GO = { Trade: ['Trades', '#personnel/trades'], Contract: ['Negotiate', '#personnel/extensions'], Staff: ['Staff', '#frontoffice/staff'], Assistants: ['Game Plan', '#gameplan/week'], Wire: ['Waivers', '#personnel/wire'] };
function deskAction(kind) { const g = DESK_GO[kind]; return g ? el('a', { class: 'btn go', href: g[1] }, g[0]) : ''; }

let mailSel = null;
function openInboxMessage(id) {
  view = pyJSON('SESSION.inbox_view()');
  const row = view.inbox.rows.find(r => r.id === Number(id));
  inboxFilter = 'all';
  mailSel = row ? row.id : null;
  if (row?.unread) {
    pyJSON(`SESSION.inbox_read(${row.id})`);
    view = pyJSON('SESSION.inbox_view()');
  }
  renderInbox(view);
}

function playerMention(pid, name) {
  return el('a', {class:'entity-link', href:'#club/player/'+encodeURIComponent(pid), onclick:e=>e.stopPropagation()}, name);
}

function messageText(message, field) {
  const text = message[field] || '', node = el('span');
  let end = 0;
  for (const ref of message.mentions?.[field] || []) {
    if (ref.start < end || ref.end > text.length || ref.end <= ref.start || ref.kind !== 'player') continue;
    node.append(document.createTextNode(text.slice(end,ref.start)), playerMention(ref.id,text.slice(ref.start,ref.end)));
    end = ref.end;
  }
  node.append(document.createTextNode(text.slice(end)));
  return node;
}

function renderRecapBody(message) {
  if (message.recap && message.snap_counts) {
    const wrapper = el('div', {class:'combined-game-report'});
    const analysis = renderRecapBody({...message, snap_counts:null});
    const snaps = renderRecapBody({...message, recap:null});
    snaps.hidden = true;
    const tabs = el('div', {class:'tabs', role:'tablist', 'aria-label':'Postgame report'});
    const buttons = ['Analysis', 'Snap Counts'].map((label,i) => el('button', {
      role:'tab', 'aria-selected':String(i===0), 'aria-pressed':String(i===0),
      onclick:()=>{ analysis.hidden=i!==0; snaps.hidden=i!==1;
        buttons.forEach((b,j)=>{b.setAttribute('aria-selected',String(i===j));b.setAttribute('aria-pressed',String(i===j));}); }
    },label));
    tabs.append(...buttons); wrapper.append(tabs,analysis,snaps); return wrapper;
  }
  if (message.snap_counts) {
    const report = message.snap_counts, columns = el('div', {class:'snap-count-columns'});
    for (const unit of ['offense', 'defense']) {
      const data = report[unit] || {total:0, rows:[]};
      const positions = unit === 'offense' ? ['QB','HB','FB','WR','TE','LT','LG','C','RG','RT'] : ['LEDG','DT','REDG','MIKE','WILL','SAM','CB','FS','SS'];
      const positionRank = p => positions.includes(p) ? positions.indexOf(p) : positions.length;
      const sortedRows = [...data.rows].sort((a,b) => b.snaps-a.snaps || positionRank(a.pos)-positionRank(b.pos) || a.name.localeCompare(b.name) || String(a.pid).localeCompare(String(b.pid)));
      const table = el('table', {class:'snap-count-table'},
        el('thead', {}, el('tr', {}, el('th', {scope:'col'}, 'Player'), el('th', {scope:'col'}, 'Snaps'))));
      const rows = el('tbody', {});
      for (const player of sortedRows) rows.append(el('tr', {}, el('td', {}, player.pid != null ? playerMention(player.pid,player.name) : player.name), el('td', {}, `${player.snaps}/${data.total}`)));
      table.append(rows);
      columns.append(el('section', {}, el('h4', {}, unit === 'offense' ? 'Offense' : 'Defense'), table));
    }
    return el('div', {class:'mbody snap-count-report'}, columns, el('p', {class:'snap-count-note'}, report.note || ''));
  }
  let report = message.recap;
  // Older saved reviews retain their section design without inventing new analysis.
  if (!report && message.kind === 'result' && (message.body || '').includes('PREGAME PLAN\n')) {
    const chunks = message.body.replace('These are observed results, not proof of cause; opponent adjustments and game situation also mattered.', '').replace('Plan results describe what happened with those choices; they do not isolate their effect from execution or the opponent.', '').trim().split('\n\n');
    report = {intro: chunks.shift(), sections: chunks.map(chunk => {
      const lines = chunk.split('\n'); return {title: lines.shift(), lines, reviews: []};
    })};
  }
  if (!report) return el('div', {class:'mbody'}, messageText(message,'body'));
  const body = el('div', {class:'mbody coaching-recap'}, el('p', {class:'recap-intro'}, report.intro));
  for (const section of report.sections || []) {
    const panel = el('section', {class:'recap-section'}, el('h4', {}, section.title));
    for (const line of section.lines || []) panel.append(el('p', {}, line));
    for (const review of section.reviews || []) {
      const choice = el('article', {class:'recap-choice'}, el('h5', {}, review.title), el('p', {class:'recap-conclusion'}, review.conclusion));
      for (const finding of review.findings || []) {
        const verdict = ['positive','negative','mixed','limited','ungraded'].includes(finding.verdict) ? finding.verdict : 'ungraded';
        choice.append(el('p', {class:`recap-finding ${verdict}`}, el('b', {}, finding.label + ' · '), finding.text));
      }
      panel.append(choice);
    }
    body.append(panel);
  }
  return body;
}

function renderInbox(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.className = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Portal'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'portal'));
  document.body.classList.remove('no-second');
  $('#second').innerHTML = `<a href="#portal">Overview</a><a aria-current="page" href="#portal/inbox">Inbox <em>${v.inbox.total}</em></a>`;
  const reload = () => renderInbox(pyJSON('SESSION.inbox_view()'));
  const s = el('section', { class: 'sheet c12 inbox-board' });
  applyTeamTheme(s, v.rail.club || {});
  const metrics = el('div', {class:'inbox-metrics'});
  for (const [n,label] of [[v.inbox.total,'Messages'],[v.inbox.decide,'Need a Decision'],[v.inbox.unread,'Unread']]) metrics.append(el('div',{},el('strong',{},String(n)),el('span',{},label)));
  s.append(el('div',{class:'inbox-hero'},el('div',{},el('div',{class:'inbox-eyebrow'},v.rail.club.name || v.rail.club.abbr),el('h1',{},'INBOX')),metrics));
  // the filters and the page-level actions
  const tools = el('div', { class: 'mailtools' });
  for (const [k, label, count] of [['all', 'All', v.inbox.total], ['club', 'Your Team', v.inbox.rows.filter(r => r.tag !== 'League').length], ['league', 'League', v.inbox.rows.filter(r => r.tag === 'League').length], ['decide', 'Needs Decision', v.inbox.decide], ['unread', 'Unread', v.inbox.unread]])
    tools.append(el('button', { class: 'chip', 'aria-pressed': String(inboxFilter === k), onclick: () => { inboxFilter = k; mailSel = null; renderInbox(v); } }, `${label} `, el('em', {}, count)));
  const rows = v.inbox.rows.filter(r => (inboxFilter !== 'decide' || r.decide) && (inboxFilter !== 'unread' || r.unread || r.id === mailSel) && (inboxFilter !== 'league' || r.tag === 'League') && (inboxFilter !== 'club' || r.tag !== 'League'));
  if (mailSel == null || !rows.some(r => r.id === mailSel)) mailSel = rows.length ? rows[0].id : null;
  const cur = rows.find(r => r.id === mailSel) || null;
  const messageTools = el('div',{class:'inbox-message-tools'},
    el('button', { class: 'btn', disabled: cur && cur.unread ? null : '', onclick: () => { pyJSON(`SESSION.inbox_read(${cur.id})`); reload(); } }, 'Mark Read'),
    el('button', { class: 'btn', disabled: cur && !cur.decide ? null : '', 'data-tip': 'Remove this message', onclick: () => { notify(pyJSON(`SESSION.inbox_delete(${cur.id})`)); mailSel = null; reload(); } }, 'Delete'));
  tools.append(el('span',{class:'inbox-tool-space'}),
    el('button', { class: 'btn quiet', onclick: () => { pyJSON('SESSION.inbox_mark_all()'); reload(); } }, 'Mark All Read'),
    el('button', { class: 'btn quiet', 'data-tip': 'Remove every read message that needs no decision', onclick: () => { if (confirm('Clear every read message that needs no decision?')) { pyJSON('SESSION.inbox_clear_read()'); mailSel = null; reload(); } } }, 'Clear Read'));
  s.append(tools);
  const box = el('div', { class: 'mailbox' });
  const list = el('div', { class: 'list' });
  for (const r of rows) list.append(el('button', { type:'button', 'aria-pressed':String(r.id === mailSel), class: 'row' + (r.unread ? ' unread' : '') + (r.block ? ' block' : '') + (r.id === mailSel ? ' sel' : ''), onclick: () => { mailSel = r.id; if (r.unread) pyJSON(`SESSION.inbox_read(${r.id})`); const keepList = list.scrollTop, keepPage = window.scrollY; renderInbox(pyJSON('SESSION.inbox_view()')); const nl = document.querySelector('.mailbox .list'); if (nl) nl.scrollTop = keepList; window.scrollTo(0, keepPage); } },
    el('span', { class: 'dot' }), el('div', { style: 'min-width:0' }, el('div',{class:'inbox-label' + (r.block ? ' urgent' : '')},r.block ? 'Action Required' : r.decide ? 'Decision' : r.tag), el('div', { class: 'subj' }, r.subject), el('div',{class:'inbox-preview'},r.body), el('div', { class: 'from' }, `${r.tag}${r.from ? ' · ' + r.from : ''}`)), el('span', { class: 'meta' }, r.when || '')));
  if (!rows.length) list.append(el('div', { class: 'empty' }, inboxFilter === 'all' ? 'Nothing yet.' : inboxFilter === 'decide' ? 'Nothing waiting on a decision.' : inboxFilter === 'league' ? 'Nothing from around the league yet.' : 'All read.'));
  const pane = el('div', { class: 'pane' });
  if (cur) {
    const m = pyJSON(`SESSION.inbox_message(${cur.id})`);
    NameLinks.scope(pane, m.entities);
    pane.append(el('div',{class:'inbox-reading-top'},el('div',{class:'inbox-eyebrow'},m.from || m.tag),cur.decide ? el('span',{class:'inbox-status'},cur.block ? 'Action Required' : 'Needs a decision') : el('span',{class:'inbox-status'},m.status === 'open' || m.status === 'read' ? 'Read' : m.status),messageTools));
    const structuredRecap = m.recap || m.snap_counts || (m.kind === 'result' && (m.body || '').includes('PREGAME PLAN\n'));
    const messageBody = structuredRecap ? renderRecapBody(m) : (m.mentions?.body?.length
      ? el('div', { class: 'mbody' }, messageText(m,'body'))
      : el('div', { class: 'mbody' }, ...(m.body_rows || [m.body || '']).map(line => el('div', { class: 'mail-body-row' }, line))));
    pane.append(el('h3', {}, messageText(m,'subject')), el('div', { class: 'from' }, `${m.tag || cur.tag}${m.from ? ' · ' + m.from : ''}${m.when ? ' · ' + m.when : ''}`), messageBody);
    if (m.kind === 'roster_report') pane.append(rosterReportCards(m, reload));
    if (m.kind === 'trade_offer') pane.append(el('div', { class: 'acts' }, el('button', { class: 'btn go', onclick: () => openTradeOffer(cur.id, reload) }, cur.decide ? 'Open Trade Offer' : 'View Trade Offer')));
    else if (m.actions && m.actions.length) { const a = el('div', { class: 'acts', style: 'margin-top:16px' }); for (const act of m.actions) a.append(el('button', { class: 'btn' + (act.primary ? ' go' : ''), onclick: () => { location.hash = act.go || `#portal/inbox/${cur.id}`; } }, act.label)); pane.append(a); }
    else if (m.kind === 'injury_decision' && ['unread', 'open'].includes(m.status) && m.pid) pane.append(el('div', { class: 'acts', style: 'margin-top:16px' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.inbox_hurt_action(${Number(m.id)}, play=True)`)); reload(); } }, 'Play Him'), el('button', { class: 'btn', onclick: () => { notify(pyJSON(`SESSION.inbox_hurt_action(${Number(m.id)}, play=False)`)); reload(); } }, 'Sit Him'), hasPlayerReference(m,m.pid) ? null : el('a', { class: 'btn quiet', href: '#club/player/' + m.pid }, 'His Card')));
    else if (cur.decide && m.kind === 'offer_sheet') pane.append(offerSheetActions(cur.id, reload));
    else if (cur.decide && m.kind === 'roster' && m.link) pane.append(el('div',{class:'acts'},el('a',{class:'btn go',href:linkHash(m.link)},'Manage Roster →'),el('a',{class:'btn quiet',href:'#club/ps'},'View Practice Squad')));
    else if (cur.decide) {
      const destination = m.link ? linkHash(m.link) : ({ staff:'#frontoffice/staff', gameplan:'#gameplan/week', game_plan:'#gameplan/week', exit:'#frontoffice/exit', contract_year:'#personnel/extensions', offer_sheet:'#personnel/extensions', match_request:'#personnel/fa' })[m.kind];
      if (destination) pane.append(el('div', { class: 'acts' }, el('a', { class: 'btn go', href: destination }, m.kind === 'match_request' || m.kind === 'offer_sheet' ? 'View Player' : 'Handle Decision')));
    }
    else if (m.link && !(m.link.startsWith('player:') && hasPlayerReference(m,m.link.slice(7))) && !(m.kind === 'negotiation' && /signs|signed|agreed|declined|walked away|ended|fell through/i.test(m.subject + ' ' + (m.body || '').slice(0, 60)))) pane.append(el('div', { class: 'acts', style: 'margin-top:16px' }, el('a', { class: 'btn' + (m.kind === 'negotiation' ? ' go' : ''), href: linkHash(m.link) }, m.kind === 'negotiation' ? 'Continue the Negotiation' : 'Go There')));
    if (cur.decide) pane.append(el('div',{class:'inbox-decision-note'},'This decision stays open until it is resolved.'));
  } else pane.append(el('div', { class: 'empty' }, 'Select a message.'));
  box.append(list, pane); s.append(box); page.append(s);
}
function rosterReportCards(message, reload) {
  const list = el('div', {class:'roster-advice'});
  const labels = {fa:'Free agent', ps:'Practice squad', waiver:'Waiver claim', trade:'Trade target'};
  for (const r of message.recommendations || []) {
    const card = el('section', {class:'roster-advice-item'});
    card.append(el('div', {class:'inbox-eyebrow'}, labels[r.source] || 'Roster opportunity'),
      el('h4', {}, `${r.name} · ${r.pos} · ${r.ovr} OVR${r.dev ? ' · ' + r.dev : ''}`),
      el('p', {}, r.reason), el('p', {class:'roster-advice-cost'}, r.cost),
      el('div', {class:'from'}, r.status));
    const acts = el('div', {class:'acts'}, el('a', {class:'btn', href:'#club/player/'+r.pid}, 'View Player'));
    if (r.available) {
      acts.append(el('button', {class:'btn go', onclick:() => {
        // Refresh availability when clicked, not just when the email was opened.
        const fresh = pyJSON(`SESSION.inbox_message(${Number(message.id)})`);
        const current = (fresh.recommendations || []).find(q => q.pid === r.pid);
        if (!current?.available) { notify({ok:false,why:'This opportunity is no longer available.'}); reload(); return; }
        if (r.source === 'trade') {
          tradeState = {other:r.owner, a:r.pick ? [r.pick.id] : [], b:[r.pid], keep:true};
          location.hash = '#personnel/trades';
        } else if (r.source === 'waiver') location.hash = '#personnel/wire';
        else {
          const call = r.source === 'ps' ? `SESSION.personnel_act('poach_ps', pid=${JSON.stringify(r.pid)})` : `SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind='fa_inseason')`;
          const result = pyJSON(call); notify(result);
          if (result.ok) location.hash = '#personnel/fa';
        }
      }}, r.source === 'trade' ? 'Review Trade' : r.source === 'waiver' ? 'Review Claim' : 'Open Negotiation'),
      el('button', {class:'btn quiet', onclick:() => { notify(pyJSON(`SESSION.inbox_roster_dismiss(${Number(message.id)}, ${JSON.stringify(r.pid)})`)); reload(); }}, 'Dismiss'));
    }
    card.append(acts); list.append(card);
  }
  return list;
}
function hasPlayerReference(message, pid) { return (message.entities || []).some(r => r.kind === 'player' && String(r.id) === String(pid)); }
function linkHash(link) {
  if (!link) return '#portal';
  const [a, b] = String(link).split(':');
  const MAP = { 'club': '#club', 'club:depth': '#club/depth', 'club:regression': '#club/regression', 'club:ps': '#club/ps', 'league:bracket': '#league/bracket', 'front_office:review': '#frontoffice/review', 'front_office:exit': '#frontoffice/exit', 'personnel:fa': '#personnel/fa', 'personnel:waivers': '#personnel/wire', 'player': '#club/player/', 'league:standings': '#league', 'league:schedule': '#league/schedule', 'league:coaching': '#league/coaching', 'league:awards': '#league/awards', 'league:almanac': '#league/almanac', 'front_office:owner': '#frontoffice', 'front_office:staff': '#frontoffice/staff', 'personnel:extensions': '#personnel/extensions', 'personnel:retain': '#personnel/retain', 'draft:board': '#draft/board' };
  if (a === 'player') return '#club/player/' + b;
  if (String(link).startsWith('club:player:')) return '#club/player/' + String(link).split(':')[2];
  if (a === 'gameplan') return b === 'practice' ? '#gameplan/practice' : '#gameplan';
  if (link === 'fa' || link === 'personnel:free_agency') return '#personnel/fa';
  if (a === 'negotiation') { const kind = String(link).split(':')[1] || ''; return kind === 'extension' ? '#personnel/extensions' : kind.startsWith('fa') ? '#personnel/fa' : '#personnel/fa'; }
  return MAP[link] || MAP[a] || '#portal';
}

function renderPortal(v) {
  const page = $('#page'); page.hidden = false; page.innerHTML = '';
  page.className = 'overview-page'; applyTeamTheme(page, v.rail.club); page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Portal';
  $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'portal'));
  document.body.classList.remove('no-second');
  $('#second').innerHTML = `<a aria-current="page" href="#portal">Overview</a><a href="#portal/inbox">Inbox <em>${v.inbox.total}</em></a>`;

  // the matchup
  const m = v.matchup;
  const match = el('section', { class: 'sheet c12 overview-match' });
  if (!m) {
    const bk=v.bracket;
    const games=bk && !bk.missing ? [...bk.confs.flatMap(c=>[...c.wc,...c.div,...(c.conf_game?[c.conf_game]:[])]),...(bk.final?[bk.final]:[])] : [];
    const next=games.find(g=>g.me && !g.done);
    const title=bk ? (bk.champion ? 'Season Complete' : 'Playoffs') : (v.phase_title || 'Offseason');
    const summary=next ? `Next playoff game: ${next.away.name} at ${next.home.name}` : bk?.champion ? `${bk.champion.name} are the champions` : bk ? 'Follow the current round and your team’s progress in the bracket below.' : 'Complete the current offseason step, then use Advance to continue.';
    match.append(el('h2',{},title),el('div',{class:'pad'},summary));
  }
  else if (m.bye) match.append(el('h2', {}, `${v.rail.clock.line === 'Camp' ? 'Opening Game · ' : 'Next Game · '}${weekName(m.week)}`, el('small', {}, 'Bye Week')), el('div', { class: 'empty' }, 'No game this week.'));
  else {
    match.append(el('h2', {}, `${v.rail.clock.line === 'Camp' ? 'Opening Game · ' : 'Next Game · '}${weekName(m.week)} ${m.away ? 'at' : 'vs'} ${esc(m.them.club.name)}`, el('small', {}, m.header || m.forecast || '')));
    const side = (c, right) => el('div', { class: 'side', style: right ? 'flex-direction:row-reverse;text-align:right' : '' }, el('div', { class: 'cr', style: `background:${c.club.color}` }, showAbbr(c.club.abbr)), el('div', {}, el('div', { class: 'nm' }, c.club.nick), el('div', { class: 'rec' }, `${c.record} · ${c.place}`)));
    const bug = el('div', { class: 'bug', style: 'grid-template-columns:auto 1fr auto;padding:12px 12px 4px' },
      side(m.me, false),
      el('div', { class: 'mid' }, el('div', { class: 'lbl' }, 'Estimated Win Chance'), el('div', { class: 'wp' }, `${m.wp}%`),
        el('div', { class: 'wpbar' }, el('i', { style: `width:${m.wp}%;background:${m.me.club.color}` }), el('i', { style: `width:${100 - m.wp}%;background:${m.them.club.color}` })),
        el('div', { class: 'lbl', style: 'margin-top:6px;text-transform:none;letter-spacing:0' }, m.line || '')),
      side(m.them, true));
    const facts = el('div', { class: 'facts2', style: 'grid-template-columns:1fr 1fr' },
      el('div', {}, el('span', {}, `${m.me.club.nick} Injuries`), el('b', {}, m.injuries.me.join(' · ') || 'None')),
      el('div', { style: 'text-align:right' }, el('span', {}, `${m.them.club.nick} Injuries`), el('b', {}, m.injuries.them.join(' · ') || 'None')));
    const formRow = el('div', { class: 'form-row' }, el('div', {}, el('div', { class: 'lbl' }, `${m.me.club.nick} Last Five`), formDots(m.form.me, true)), el('div', {}, el('div', { class: 'lbl' }, `${m.them.club.nick} Last Five`), formDots(m.form.them, true)));
    const left = el('div', { class: 'm-side' }, bug, facts, formRow);
    const right = el('div', { class: 'm-right' },
      el('div', { class: 'mh' }, 'Opponent Watch', el('a', { class: 'more', href: '#gameplan/report' }, 'Scouting Report →')),

      el('div', { class: 'men-row', style: 'border-top:1px solid var(--rule)' }, ...m.watch.map(w => el('div', {}, el('div', { class: 'lbl' }, 'Players to Watch'), el('button', { class: 'man', onclick: () => { location.hash = '#club/player/' + w.pid; } }, el('div', { class: 'no', style: `background:${m.them.club.color};color:#fff` }, jerseyNo(w.no) ?? w.pos), el('div', { class: 'nm' }, w.name.split(' ')[0][0] + '. ' + w.name.split(' ').slice(1).join(' '), el('small', {}, `${w.pos}${w.note ? ' · ' + w.note : ''}`)), el('div', { class: 'ov' }, w.ovr))))));
    match.append(el('div', { class: 'match', style: 'grid-template-columns:1fr 1.1fr' }, left, right));
    match.append(el('div', { class: 'foot' }, el('a', { class: 'btn go', href: '#gameplan' }, 'Set Game Plan'), el('a', { class: 'btn', href: '#gameplan/report' }, 'Opponent Report'), el('a', { class: 'btn', href: '#club/depth' }, 'Depth Chart'), el('button', { class: 'btn quiet', onclick: e => { const b = document.getElementById('series'); if (b) b.hidden = !b.hidden; } }, 'Series History')));
    match.append(el('div', { id: 'series', class: 'read', hidden: '', style: 'margin:0 14px 12px' }, m.series && m.series.length ? m.series.map(g => `${weekName(g.week)}: ${g.away} ${g.ap} at ${g.home} ${g.hp}`).join(' · ') : 'The teams have not met this season. Past seasons\' meetings will show here as the almanac fills.'));
  }
  page.append(match);

  // on your desk: the card by kind, with the decision on it
  const desk = el('section', { class: 'sheet c12' }, el('h2', {}, 'Action Required', el('small', {}, `${v.desk_total ?? v.desk.length} waiting`)));
  if (!v.desk.length) desk.append(el('div', { class: 'empty' }, 'Nothing needs you before the next advance.'));
  else desk.append(el('div', { class: 'cards' }, ...v.desk.map(c => {
    const card = el('div', { class: 'card', style: `--k:${c.kind === 'Trade' ? 'var(--live)' : c.kind === 'Contract' ? 'var(--club-2)' : 'var(--decide)'}` });
    if (c.raw_kind === 'trade_offer' && c.buyer) {
      card.append(el('div', { class: 'h' }, el('div', { class: 'k' }, `Trade Offer · ${c.buyer.name}` + (c.expires ? ` · Expires after week ${c.expires}` : '')), el('div', { class: 's' }, c.subject)),
        el('div', { class: 'facts2', style: 'grid-template-columns:1fr 1fr;padding:6px 0' }, el('div', {}, el('span', {}, 'They Send'), el('b', {}, c.they_send || '—')), el('div', {}, el('span', {}, 'Value Gap'), el('b', { style: c.gap != null ? (c.gap >= 0 ? 'color:var(--ok)' : 'color:var(--danger)') : '' }, c.gap != null ? `${c.gap >= 0 ? '+' : '−'}$${Math.abs(c.gap).toFixed(1)}m` : '—'))),
        el('div', { class: 'b' }, `You send ${c.you_send}. ${c.read || ''}`),
        el('div', { class: 'a' }, el('button', { class: 'btn go', onclick: () => { try { pyJSON(`__import__('inbox').accept(SESSION.L, ${c.id}, SESSION.user_team)`); notify({ ok: true, line: 'Trade accepted.' }); } catch (e) { notify({ ok: false, why: 'The offer could not be completed.' }); } refresh(); } }, 'Accept'),
          el('button', { class: 'btn', onclick: () => openTradeOffer(c.id, refresh) }, 'Open'),
          el('button', { class: 'btn', onclick: () => { tradeState = { other: c.buyer.abbr, a: (c.payload.gets || []).map(String), b: (c.payload.sends || []).map(x => (x && x.pick) ? `${x.year}-${x.round}-${x.original}` : String(x)), keep: true }; location.hash = '#personnel/trades'; } }, 'Counter'),
          el('button', { class: 'btn quiet', onclick: () => { pyJSON(`__import__('inbox').decline(SESSION.L, ${c.id})`); refresh(); } }, 'Decline')));
    } else if (c.ask != null || c.raw_kind === 'contract_year') {
      card.append(el('div', { class: 'h' }, el('div', { class: 'k' }, 'Contracts · Final Year'), el('div', { class: 's' }, c.subject)),
        el('div', { class: 'facts2', style: 'grid-template-columns:1fr 1fr;padding:6px 0' }, el('div', {}, el('span', {}, 'Agent Asks'), el('b', {}, c.ask != null ? `$${c.ask.toFixed(1)}m` : 'Ask him')), el('div', {}, el('span', {}, 'Years Left'), el('b', {}, c.years_left ?? '—'))),
        el('div', { class: 'b' }, c.line || c.body),
        el('div', { class: 'a' }, el('button', { class: 'btn go', onclick: () => { pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(c.pid)}, kind='extension')`); location.hash = '#personnel/extensions'; } }, 'Negotiate'), el('button', { class: 'btn quiet', onclick: () => { pyJSON(`SESSION.inbox_later(${c.id})`); notify({ok:true,line:'Kept in your inbox for later.'}); refresh(); } }, 'Later')));
    } else {
      card.append(el('div', { class: 'h' }, el('div', { class: 'k' }, c.kind), el('div', { class: 's' }, c.subject)), el('div', { class: 'b' }, c.body),
        el('div', { class: 'a', style: 'display:flex;gap:6px' }, el('button', { class: 'btn', onclick: () => location.hash = `#portal/inbox/${c.id}` }, 'Open'), deskAction(c.kind)));
    }
    return card;
  })));
  desk.classList.add('overview-actions'); page.prepend(desk);
  const hero=el('section',{class:'overview-hero c12'},el('div',{},el('div',{class:'inbox-eyebrow'},v.rail.club.name),el('h1',{},'OVERVIEW'),el('p',{},`${v.rail.clock.line} · ${v.rail.year}`)),el('div',{class:'overview-phase'},el('strong',{},v.phase_title || v.rail.advance.title),el('span',{},v.rail.advance.sub || '')));
  page.prepend(hero);
  if(v.team_status) { const t=v.team_status; const status=el('section',{class:'sheet c12 pad overview-status'},el('h2',{},'Team Status'),el('div',{class:'facts2',style:'grid-template-columns:repeat(4,1fr)'},...[[`${t.active}/${t.limit}`,'Active roster'],[v.rail.cap,'Cap space'],[t.unavailable,'Unavailable'],[v.desk_total ?? v.desk.length,'Pending decisions']].map(([value,label])=>el('div',{},el('span',{},label),el('b',{},String(value)))))); match.after(status); }

  // THE BRACKET, once the playoffs start: the field, live, between the desk and the money
  if (v.bracket && !v.bracket.missing) {
    const bk = el('section', { class: 'sheet c12' }, el('h2', {}, `${v.bracket.year || ''} Playoffs`, el('small', {}, v.bracket.champion ? `Champion: ${v.bracket.champion.name}` : v.bracket.live ? 'the bracket, live' : v.bracket.note || 'the field')));
    bk.append(bracketTree(v.bracket)); match.after(bk);
  }

  if(v.bracket?.error) match.after(el('section',{class:'sheet c12 pad',role:'alert'},v.bracket.note));

  // standings and season
  const st = v.standings;
  const table = el('table', {}, el('tr', {}, el('th', {}, ''), el('th', {}, 'Team'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', {}, 'Form'), el('th', { class: 'n' }, 'PF'), el('th', { class: 'n' }, 'PA'), el('th', { class: 'n' }, 'PD')),
    ...st.rows.map(r => el('tr', { class: r.me ? 'me' : '' }, el('td', {}, ''), el('td', {}, stripe(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', {}, formDots(r.form)), el('td', { class: 'n' }, r.pf), el('td', { class: 'n' }, r.pa), el('td', { class: 'n' }, (r.pd > 0 ? '+' : '') + r.pd))));
  const stS = sheet(st.division, '', table, el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#league' }, 'Full Standings')));
  stS.classList.add('c6'); page.append(stS);

  const recent=v.season.games.filter(g=>g.result).slice(-5).reverse();
  const results=el('div',{class:'overview-results'},...(recent.length ? recent.map(g=>el('a',{href:'#league/schedule',class:'overview-result'},el('strong',{class:g.result==='W'?'good':g.result==='L'?'bad':''},g.result),el('span',{},`${weekName(g.week)} · ${g.home?'vs':'at'} ${g.opp}`),el('b',{},g.score))) : [el('div',{class:'empty'},'No results yet. Season statistics available after Week 1.')]));
  const seS = sheet('Recent Results', v.rail.record, results, el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#league/schedule' }, 'Schedule'), el('a', { class: 'btn', href: '#league/stats' }, 'Stats'), el('a', { class: 'btn quiet', href: '#league' }, 'Playoff Picture')));
  seS.classList.add('c6'); page.append(seS);
  const room=v.room.counts;
  const summaries=el('section',{class:'overview-summaries c12'},
    el('a',{href:'#frontoffice/cap'},el('span',{},'CAP OUTLOOK'),el('strong',{},v.cap.space+' available'),el('small',{},'View contracts and future commitments →')),
    el('a',{href:'#club'},el('span',{},'LOCKER ROOM'),el('strong',{},`${room.Unhappy + room.Unsettled} players unsettled or unhappy`),el('small',{},'Review your roster →')),
    el('a',{href:'#frontoffice/owner'},el('span',{},'OWNER & JOB SECURITY'),el('strong',{},v.front_office.job),el('small',{},v.front_office.expects || v.front_office.owner_mood)));
  page.append(summaries);
}

function ord(n) { return n === 1 ? 'st' : n === 2 ? 'nd' : n === 3 ? 'rd' : 'th'; }

function offerSheetActions(id, reload) {
  const controls = el('div', {class:'acts'});
  for (const [action, label] of [['match', 'Match Offer'], ['decline', 'Decline Offer']]) {
    controls.append(el('button', {class:'btn' + (action === 'match' ? ' go' : ''), onclick: () => {
      const result = pyJSON(`SESSION.inbox_offer_sheet(${Number(id)}, ${JSON.stringify(action)})`);
      notify(result.ok ? {ok:true, line:result.outcome === 'matched' ? 'Offer matched.' : result.outcome === 'departed' ? 'Offer declined; the player joins the other team.' : 'The offer is no longer valid.'} : result);
      renderRail(pyJSON('SESSION.portal()').rail);
      reload();
    }}, label));
  }
  return controls;
}


// ---------------------------------------------------------------- Game Day
function renderGameDay(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  page.className = 'gameday-page';
  $('#crumb').textContent = 'Game Day';
  $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'gameday'));
  $('#second').innerHTML = ''; document.body.classList.add('no-second');
  featureHero(page, v.rail.club, v.week ? `${weekName(v.week)} / ${v.rail.year}` : `Season / ${v.rail.year}`, 'GAME DAY', v.preview ? 'The matchup and the decisions before kickoff.' : 'The score, the play feed, and your sideline controls.', [[v.week ? weekName(v.week) : '—', 'Week'], [v.preview ? (v.no_game ? 'No game' : v.bye ? 'Bye' : 'Preview') : v.live?.open ? 'Live' : 'Final', 'Game state']]);
  if (v.empty) { page.append(el('section', { class: 'sheet c12' }, el('h2', {}, 'Game Day'), el('div', { class: 'empty' }, v.line))); return; }
  if (v.preview) {
    // the week has not been played: the preview of this week's game, and the button that plays it
    const s = el('section', { class: 'sheet c12 gameday-surface game-preview' }, el('h2', {}, 'Matchup Preview', el('small', {}, v.no_game ? 'No game this round' : v.bye ? 'Bye week' : `${v.matchup.away ? 'at' : 'vs'} ${v.matchup.them.club.name} · ${v.matchup.header || ''}`)));
    if (v.bye) { s.append(el('div', { class: 'empty' }, v.line)); }
    else {
      const m = v.matchup;
      s.append(el('div', { class: 'bigbug' },
        el('div', { class: 'side' }, el('div', { class: 'cr', style: `background:${m.me.club.color}` }, showAbbr(m.me.club.abbr)), el('div', {}, el('div', { class: 'nm' }, m.me.club.nick), el('div', { class: 'rec' }, `${m.me.record} · ${m.me.place}`))),
        el('div', { class: 'mid' }, el('div', { class: 'q' }, 'Kickoff Sunday'), el('div', { class: 'dd' }, `Win Probability ${m.wp}%`), el('div', { class: 'q', style: 'font-size:12.5px;color:var(--ink-3);margin-top:4px' }, m.line || '')),
        el('div', { class: 'side', style: 'flex-direction:row-reverse;text-align:right' }, el('div', { class: 'cr', style: `background:${m.them.club.color}` }, showAbbr(m.them.club.abbr)), el('div', {}, el('div', { class: 'nm' }, m.them.club.nick), el('div', { class: 'rec' }, `${m.them.record} · ${m.them.place}`)))));
      s.append(el('div', { class: 'facts2', style: 'grid-template-columns:1fr 1fr;padding:6px 14px' }, el('div', {}, el('span', {}, `${m.me.club.nick} Injuries`), el('b', {}, m.injuries.me.join(' · ') || 'None')), el('div', { style: 'text-align:right' }, el('span', {}, `${m.them.club.nick} Injuries`), el('b', {}, m.injuries.them.join(' · ') || 'None'))));
      s.append(el('div', { class: 'read', style: 'margin:0 14px 10px' }, el('b', {}, 'Assistants: '), m.say));
      s.append(el('div', { class: 'read', style: 'margin:0 14px 12px;color:var(--ink-2)' }, v.plan_set ? 'Your game plan for this week is set.' : "You have not changed the coordinators' plan this week; the game reads their plan as it stands."));
    }
    s.append(el('div', { class: 'foot' }, el('button', { class: 'btn go', onclick: () => { $('#advance').click(); } }, v.week >= 19 ? `${v.bye ? 'Sim' : 'Play'} the ${weekName(v.week)}` : `Sim ${weekName(v.week)}`), el('a', { class: 'btn', href: '#gameplan' }, 'Game Plan'), el('a', { class: 'btn', href: '#gameplan/report' }, 'Opponent Report'), el('a', { class: 'btn quiet', href: '#club/depth' }, 'Depth Chart')));
    page.append(s); return;
  }
  const g = v.game;
  const top = el('section', { class: 'sheet c12 gameday-surface game-scoreboard' });
  // the Sunday scoreboard
  const sb = el('div', { class: 'scoreboard' });
  const strips = {};
  for (const s of v.scores) {
    const hw = s.hs > s.as_, aw = s.as_ > s.hs;
    const card = el('div', { class: 'sb' + (s.mine ? ' mine' : '') },
      el('div', { class: 'row' + (aw && !s.mine ? ' w' : '') }, stripe(s.away.abbr), el('b', { class: 'as' }, s.mine ? '' : s.as_)),
      el('div', { class: 'row' + (hw && !s.mine ? ' w' : '') }, stripe(s.home.abbr), el('b', { class: 'hs' }, s.mine ? '' : s.hs)),
      el('div', { class: 'st' }, el('span', {}, s.mine ? 'In progress' : 'Final' + (s.ot ? ' · OT' : ''))));
    if (s.mine) strips.mine = { card, s };
    sb.append(card);
  }
  top.append(sb);
  if (!g) { top.append(el('div', { class: 'empty' }, 'Your team was on its bye this week.')); page.append(top); return; }
  // the big bug: it follows the reveal (score, quarter and clock, situation, win probability), Final once the game is played out
  const me = g.me_home ? g.home : g.away, them = g.me_home ? g.away : g.home;
  const rec = r => `${r[0]}–${r[1]}`;
  const bug = el('div', { class: 'bigbug' }); top.insertBefore(bug, sb);
  const lineScore = el('table', { class: 'linescore' }); top.insertBefore(lineScore, sb);
  const drawBug = (shown, shownPlays) => {
    const final = !live && shown >= g.drives.length && shownPlays == null;
    const d = g.drives[Math.max(0, shown - 1)] || { plays: [], quarter: 1, score: '0–0', off: g.home.abbr, n: 0 }; const revealed = (shownPlays != null ? vis(d).slice(0, shownPlays) : vis(d));
    const currentQuarter = shownPlays == null ? (d.scoring_quarter || d.quarter) : ([...revealed].reverse().find(p => p.quarter)?.quarter || d.quarter);
    const atBreak = shownPlays == null && shown < g.drives.length && g.drives[shown].quarter > currentQuarter;
    let hs = g.hs, as_ = g.as_;
    if (live) { hs = live.score.home; as_ = live.score.away; }
    else if (!final) { const prev = g.drives[shown - 2]; const src = (shownPlays != null ? prev : d); const sc = src ? String(src.score).split('–') : ['0', '0']; hs = +sc[0]; as_ = +sc[1]; if (shownPlays != null) { const add = (n, toOff) => { if ((d.off === g.home.abbr) === toOff) hs += n; else as_ += n; }; for (const p of revealed) { const points = replayPlayPoints(p); if (points) add(Math.abs(points), points > 0); } } }
    const lastPlay = revealed.length ? revealed[revealed.length - 1] : null;
    const headParts = lastPlay && lastPlay.head ? lastPlay.head.split(' · ') : [];
    const clock = atBreak ? '0:00' : (headParts.length >= 3 ? headParts[headParts.length - 1] : '');
    const wpNow = g.wp[Math.min(g.wp.length - 1, Math.max(0, shown - 1))];
    const myScore = g.me_home ? hs : as_, theirScore = g.me_home ? as_ : hs;
    const won = myScore > theirScore, tie = myScore === theirScore;
    const indicators = gameDayIndicators(g, shown, shownPlays, live, v.week >= 19);
    bug.innerHTML = '';
    bug.append(
      el('div', { class: 'side' }, el('div', { class: 'cr', style: `background:${g.away.color}` }, showAbbr(g.away.abbr)), gameDayTeamStatus(g.away, rec(g.away_rec), indicators), el('div', { class: 'score', style: 'margin-left:auto' }, as_)),
      el('div', { class: 'mid' }, el('div', { class: 'q' }, final ? 'Final' + (g.ot ? ' · Overtime' : '') : atBreak ? (currentQuarter === 2 ? 'Halftime' : currentQuarter >= 4 ? 'End of Regulation' : `End of Q${currentQuarter}`) : `${currentQuarter >= 5 ? 'OT' : 'Q' + currentQuarter}${clock ? ' · ' + clock : ''}`), el('div', { class: 'dd' }, final ? (tie ? 'A tie' : won ? `${me.name} wins` : `${them.name} wins`) : atBreak ? `${showAbbr(d.off)} ${String(d.result || '').toLowerCase()}`.trim() : (lastPlay && lastPlay.head ? lastPlay.head.split(' · ').slice(0, 2).join(' · ') : `Drive ${d.n}`)), el('div', { class: 'q', style: 'font-size:12.5px;color:var(--ink-3);margin-top:4px' }, (wpNow == null ? '' : `Win Probability ${wpNow}%`) + (g.env && g.env.conditions ? `${wpNow == null ? '' : ' · '}${g.env.conditions}` : ''))),
      el('div', { class: 'side home-side', style: 'flex-direction:row-reverse;text-align:right' }, el('div', { class: 'cr', style: `background:${g.home.color}` }, showAbbr(g.home.abbr)), gameDayTeamStatus(g.home, rec(g.home_rec), indicators), el('div', { class: 'score', style: 'margin-right:auto' }, hs)));
    lineScore.innerHTML = '';
    if (g.quarters && g.quarters[g.home.abbr]) {
      const Q = g.quarters; const upto = final ? 5 : currentQuarter; const hasOT = Q[g.home.abbr][4] || Q[g.away.abbr][4];
      lineScore.append(el('tr', {}, el('th', {}, ''), ...['Q1', 'Q2', 'Q3', 'Q4'].concat(hasOT ? ['OT'] : []).map(q => el('th', {}, q)), el('th', {}, 'T')));
      for (const ab of [g.away.abbr, g.home.abbr]) lineScore.append(el('tr', {}, el('td', {}, showAbbr(ab)), ...Q[ab].slice(0, hasOT ? 5 : 4).map((x, qi) => el('td', {}, final || qi < upto - 1 ? x : qi === upto - 1 ? (ab === g.home.abbr ? hs : as_) - Q[ab].slice(0, qi).reduce((a, b) => a + b, 0) : '')), el('td', { style: 'font-weight:700' }, ab === g.home.abbr ? hs : as_)));
    }
  };
  // win probability by drive
  const W = 720, H = 70; const pts = g.wp.map((p, i) => [i / Math.max(1, g.wp.length - 1) * W, H - 4 - (p / 100) * (H - 8)]);
  const svgNS = 'http://www.w3.org/2000/svg'; const svg = document.createElementNS(svgNS, 'svg'); svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('preserveAspectRatio', 'none');
  const mk = (tag, attrs) => { const e = document.createElementNS(svgNS, tag); for (const [k, val] of Object.entries(attrs)) e.setAttribute(k, val); return e; };
  svg.append(mk('line', { x1: 0, y1: H / 2, x2: W, y2: H / 2, stroke: '#3a424c' }));
  [0.25, 0.5, 0.75].forEach(f => svg.append(mk('line', { x1: f * W, y1: 0, x2: f * W, y2: H, stroke: '#2e353e' })));
  svg.append(mk('polyline', { fill: 'none', stroke: me.color, 'stroke-width': 2, points: pts.map(p => p.join(',')).join(' ') }));
  const t1 = mk('text', { x: 4, y: 12, fill: '#7b8593', 'font-size': 10, 'font-family': 'Big Shoulders Text' }); t1.textContent = showAbbr(me.abbr); const t2 = mk('text', { x: 4, y: H - 4, fill: '#7b8593', 'font-size': 10, 'font-family': 'Big Shoulders Text' }); t2.textContent = showAbbr(them.abbr); svg.append(t1, t2);
  const wpc = el('div', { class: 'wpchart' }); wpc.append(svg); top.append(wpc);
  const wpLine = svg.querySelector('polyline');
  const drawWp = (shown, shownPlays) => { const n = Math.max(1, (shownPlays != null ? shown - 1 : shown)); wpLine.setAttribute('points', pts.slice(0, Math.min(pts.length, n + 1)).map(p => p.join(',')).join(' ')); };
  page.append(top);

  // the ticker, revealed by drive
  const tick = el('section', { class: 'sheet c8 gameday-surface game-feed' });
  const live = v.live && v.live.open ? v.live : null;
  const gkey = `${g.home.abbr}-${g.away.abbr}-${v.week || ''}-${v.year || ''}`;
  const saved = live ? { shown: Math.max(1, g.drives.length), shownPlays: null } : (gdReveal[gkey] || { shown: 1, shownPlays: 0 });
  let shown = saved.shown, shownPlays = saved.shownPlays;      // shownPlays: within the last shown drive, how many plays are revealed (null = all)
  const body = el('div', { class: 'ticker' });
  const filt = { mode: 'all' };
  const draw = () => {
    body.innerHTML = '';
    g.drives.slice(0, shown).forEach((d, di) => {
      const last = di === shown - 1; const plays = (last && shownPlays != null) ? vis(d).slice(0, shownPlays) : d.plays;
      body.append(el('div', { class: 'drive' }, (last && shownPlays != null) ? `Drive ${d.n} · ${d.off} · Q${d.quarter}` : `Q${d.quarter} · ${d.head || `Drive ${d.n} · ${d.off}`} · ${d.score}`));
      for (const p of plays) {
        if (!p.text) continue;
        if (p.nullified && ['key', 'score'].includes(filt.mode)) continue;
        if (filt.mode === 'key' && !['score', 'turnover', 'loss'].includes(p.kind) && !(p.type === 'complete' && /for (\d\d) yards/.test(p.text) && +p.text.match(/for (\d\d) yards/)[1] >= 15)) continue;
        if (filt.mode === 'score' && p.kind !== 'score') continue;
        const line = el('div', { class: 'pl ' + p.kind }); if (p.head) line.append(el('span', { class: 'dn' }, p.head), '  '); line.append(p.text); body.append(line);
      }
    });
    tick.querySelector('h2 small').textContent = live ? (live.halftime_open ? (live.adjustment_period === 'overtime' ? 'Overtime adjustments' : 'Halftime') : `Live · drive ${g.drives.length}`) : (shown >= g.drives.length && shownPlays == null) ? 'Final' : `Drive ${shown} of ${g.drives.length}` + (shownPlays != null ? ` · play ${shownPlays} of ${vis(g.drives[shown - 1]).length}` : '');
    body.scrollTop = body.scrollHeight;
    gdReveal[gkey] = { shown, shownPlays };
    drawBug(shown, shownPlays); drawLiveBox(shown, shownPlays); drawRead(shown >= g.drives.length && shownPlays == null); drawWp(shown, shownPlays);
    if (strips.mine) { const fin = !live && shown >= g.drives.length && shownPlays == null; const { card, s } = strips.mine; card.querySelector('.as').textContent = fin ? s.as_ : ''; card.querySelector('.hs').textContent = fin ? s.hs : ''; card.querySelector('.st span').textContent = fin ? 'Final' + (s.ot ? ' · OT' : '') : 'In progress'; }
  };
  const vis = d => d.plays.filter(p => p.text);
  // the first drive opens one play at a time too
  const nextPlay = () => { const d = g.drives[shown - 1]; const n = vis(d).length; if (shownPlays == null || shownPlays >= n) { if (shownPlays != null && shownPlays >= n) shownPlays = null; if (shown >= g.drives.length) { shownPlays = null; draw(); return; } shown++; shownPlays = 1; } else shownPlays++; if (shownPlays >= vis(g.drives[shown - 1]).length) shownPlays = null; draw(); };
  const quarterEnd = q => { let i = g.drives.findIndex(d => d.quarter > q); return i < 0 ? g.drives.length : i; };   // how many drives are in through the end of quarter q
  const nextQuarter = () => { shownPlays = null; const q = g.drives[Math.min(shown, g.drives.length) - 1].quarter; const end = quarterEnd(q); shown = (shown >= end) ? quarterEnd(q + 1) : end; draw(); };
  const step = async mode => { const y = window.scrollY; const r = pyJSON(`SESSION.live_step(${JSON.stringify(mode)})`); renderGameDay(r); window.scrollTo(0, y); if (r.live && r.live.open) await saveLiveJournalNotified(); else { renderRail(pyJSON('SESSION.portal()').rail); await saveGameNotified(); } };
  const ctrl = live ? el('div', { class: 'ctrl2' },
    el('button', { class: 'btn', disabled: live.halftime_open ? '' : null, onclick: () => step('play') }, 'Next Play'),
    el('button', { class: 'btn go', disabled: live.halftime_open ? '' : null, onclick: () => step('drive') }, 'Next Drive'),
    el('button', { class: 'btn', disabled: live.halftime_open || live.at === 'overtime' || (g.drives.length && g.drives[g.drives.length - 1].quarter > 2) ? '' : null, onclick: () => step('half') }, 'To Halftime'),
    el('button', { class: 'btn', disabled: live.halftime_open ? '' : null, onclick: () => step('finish') }, 'Finish Game'),
    el('span', { class: 'sep' }),
    (() => { const t = el('div', { class: 'tabs' }); ['all', 'key', 'score'].forEach(m => t.append(el('button', { 'aria-pressed': String(m === 'all'), onclick: e => { filt.mode = m; t.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); draw(); } }, { all: 'Every Play', key: 'Key Plays', score: 'Scoring' }[m]))); return t; })())
  : el('div', { class: 'ctrl2' },
    el('button', { class: 'btn', 'data-tip': 'One snap at a time', onclick: nextPlay }, 'Next Play'),
    el('button', { class: 'btn go', 'data-tip': 'Through the end of this drive, or the next one if this one is in', onclick: () => { if (shownPlays != null) { shownPlays = null; } else shown = Math.min(g.drives.length, shown + 1); draw(); } }, 'Next Drive'),
    el('button', { class: 'btn', 'data-tip': 'Through the end of the quarter', onclick: nextQuarter }, 'Next Quarter'),
    el('button', { class: 'btn', 'data-tip': 'Through the end of the second quarter', onclick: () => { shownPlays = null; shown = Math.max(shown, quarterEnd(2)); draw(); } }, 'To Halftime'),
    el('button', { class: 'btn', onclick: () => { shownPlays = null; shown = g.drives.length; draw(); } }, 'Finish Game'),
    el('span', { class: 'sep' }),
    (() => { const t = el('div', { class: 'tabs' }); ['all', 'key', 'score'].forEach(m => t.append(el('button', { 'aria-pressed': String(m === 'all'), onclick: e => { filt.mode = m; t.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); draw(); } }, { all: 'Every Play', key: 'Key Plays', score: 'Scoring' }[m]))); return t; })());
  const copyPbp = el('button', { class: 'btn quiet', style: 'width:auto;padding:3px 10px;font-size:14px', 'data-tip': 'Copy the play-by-play shown so far as text' , onclick: () => {
    const lines = [`${showAbbr(g.away.abbr)} at ${showAbbr(g.home.abbr)} · ${v.week ? weekName(v.week) : ''} ${v.year || ''}`];
    g.drives.slice(0, shown).forEach((d, di) => { const last = di === shown - 1; const plays = (last && shownPlays != null) ? vis(d).slice(0, shownPlays) : d.plays;
      lines.push(`${d.quarter >= 5 ? 'OT' : 'Q' + d.quarter} · ${d.head || `Drive ${d.n} · ${showAbbr(d.off)}`} · ${d.score}`); for (const p of plays) if (p.text) lines.push(`${p.head ? p.head + ' ' : ''}${p.text}`); });
    if (!live && shown === g.drives.length && shownPlays == null) lines.push(`Final${g.ot ? ' (OT)' : ''}: ${showAbbr(g.home.abbr)} ${g.hs}, ${showAbbr(g.away.abbr)} ${g.as_}`);
    copyText(lines.join('\n'), copyPbp); } }, 'Copy');
  tick.append(el('h2', {}, 'Play by Play', el('small', {}, ''), copyPbp), ctrl);
  if (live && live.halftime_open) {
    const overtime = live.adjustment_period === 'overtime';
    const breakKey = `${gkey}-${overtime ? 'overtime' : 'halftime'}`;
    const confirmed = !!halfConfirmed[breakKey];
    const breakLabel = overtime ? 'Overtime' : 'Halftime';
    const card = el('div', { class: 'read', style: 'margin:0 14px 10px;padding:12px 14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap' });
    card.append(el('b', {}, `${breakLabel} · ${showAbbr(g.away.abbr)} ${live.score.away}, ${showAbbr(g.home.abbr)} ${live.score.home}`),
      el('button', { class: 'btn' + (confirmed ? '' : ' go'), onclick: () => openHalftime(g, live, breakKey, () => { const y = window.scrollY; renderGameDay(pyJSON('SESSION.gameday_view()')); window.scrollTo(0, y); }) }, `${breakLabel} Adjustments${confirmed ? ' · confirmed' : ''}`),
      el('span', { class: 'count' }, confirmed ? 'Adjustments confirmed.' : `Review the adjustments and confirm to unlock ${overtime ? 'overtime' : 'the second half'}.`),
      el('button', { class: 'btn go', style: 'margin-left:auto', disabled: confirmed ? null : '', 'data-tip': confirmed ? null : `Confirm the ${breakLabel.toLowerCase()} adjustments first`, onclick: () => step('resume') }, overtime ? 'Start Overtime' : 'Start the Second Half'));
    tick.append(card);
  }
  tick.append(body);
  page.append(tick);

  // the right column: team stats and the assistants' read; the box score sits under the ticker at its width
  const right = el('section', { class: 'sheet c4 gameday-surface game-side' });
  const boxSheet = el('section', { class: 'sheet c8 gameday-surface game-box' });
  const boxHead = el('h2', {}, 'Box Score', el('small', {}, 'Live')); boxSheet.append(boxHead);
  const box = el('table', { class: 'box' }); boxSheet.append(box);
  const th = (...c) => el('tr', {}, ...c.map((x, i) => el('th', {}, x)));
  const awayFirst = arr => [...arr.filter(r => r.team === g.away.abbr), ...arr.filter(r => r.team !== g.away.abbr)];
  const drawFullBox = () => {
    box.innerHTML = ''; boxHead.querySelector('small').textContent = 'Final';
    const P = awayFirst(g.box.passing), R = awayFirst(g.box.rushing), C = awayFirst(g.box.receiving), D = awayFirst(g.box.defense);
    box.append(th('Passing', 'C/A', 'Yds', 'TD', 'INT', 'Lng')); P.forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.ca), el('td', {}, r.yds), el('td', {}, r.td), el('td', {}, r.int_), el('td', {}, r.lng ?? ''))));
    box.append(th('Rushing', 'Att', 'Yds', 'TD', '', 'Lng')); R.forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.att), el('td', {}, r.yds), el('td', {}, r.td), el('td', {}, ''), el('td', {}, r.lng ?? ''))));
    box.append(th('Receiving', 'Tgt', 'Rec', 'Yds', 'TD', 'Lng')); C.forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.tgt), el('td', {}, r.rec), el('td', {}, r.yds), el('td', {}, r.td), el('td', {}, r.lng ?? ''))));
    box.append(th('Defense', 'Tkl', 'Sk', 'INT', 'PD', 'TD')); D.forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.tkl), el('td', {}, r.sk), el('td', {}, r.int_), el('td', {}, r.pd), el('td', {}, r.td || 0))));
  };
  const drawLiveBox = (shown, shownPlays) => {
    drawTeamStats(shown, shownPlays);
    if (shown >= g.drives.length && shownPlays == null) { drawFullBox(); return; }
    boxHead.querySelector('small').textContent = 'Live'; box.innerHTML = '';
    const pass = {}, rush = {}, recv = {};
    const revealed = []; g.drives.slice(0, shown).forEach((d, di) => { const last = di === shown - 1; revealed.push(...((last && shownPlays != null) ? d.plays.filter(p => p.text).slice(0, shownPlays) : d.plays)); });
    for (const p of revealed) {
      if (!p.type) continue; const y = p.yards || 0;
      if (['complete', 'incomplete', 'drop', 'interception'].includes(p.type) && p.passer) { const k = p.off + '|' + p.passer; const r = pass[k] = pass[k] || { team: p.off, name: p.passer, cmp: 0, att: 0, yds: 0, td: 0, int_: 0 }; r.att++; if (p.type === 'complete') { r.cmp++; r.yds += y; if (p.td) r.td++; } if (p.type === 'interception') r.int_++; }
      if (['complete', 'incomplete', 'drop', 'interception'].includes(p.type) && p.target) { const k = p.off + '|' + p.target; const r = recv[k] = recv[k] || { team: p.off, name: p.target, tgt: 0, rec: 0, yds: 0, td: 0 }; r.tgt++; if (p.type === 'complete') { r.rec++; r.yds += y; if (p.td) r.td++; } }
      if (['run', 'scramble'].includes(p.type) && (p.carrier || p.passer)) { const who = p.carrier || p.passer; const k = p.off + '|' + who; const r = rush[k] = rush[k] || { team: p.off, name: who, att: 0, yds: 0, td: 0, lng: 0 }; r.att++; r.yds += y; if (p.td) r.td++; r.lng = Math.max(r.lng, y); }
    }
    const top = (o, key, n) => awayFirst(Object.values(o).sort((a, b) => b[key] - a[key])).slice(0, n);
    box.append(th('Passing', 'C/A', 'Yds', 'TD', 'INT')); top(pass, 'att', 4).forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, `${r.cmp}/${r.att}`), el('td', {}, r.yds), el('td', {}, r.td), el('td', {}, r.int_))));
    box.append(th('Rushing', 'Att', 'Yds', 'TD', 'Lng')); top(rush, 'att', 6).forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.att), el('td', {}, r.yds), el('td', {}, r.td), el('td', {}, r.lng))));
    box.append(th('Receiving', 'Tgt', 'Rec', 'Yds', 'TD')); top(recv, 'tgt', 10).forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.tgt), el('td', {}, r.rec), el('td', {}, r.yds), el('td', {}, r.td))));
    if (!Object.keys(pass).length && !Object.keys(rush).length) box.append(el('tr', {}, el('td', { colspan: '5' }, el('div', { class: 'empty' }, 'Step through the game; the box fills as plays are revealed.'))));
  };

  // team stats side by side: the full book at Final, and until then the totals of the plays revealed so far
  let tsTable = null;
  if (g.team_stats && g.team_stats[g.home.abbr]) {
    right.append(el('h2', {}, 'Team Stats', el('small', { class: 'ts-note' }, 'Live')));
    tsTable = el('table', { class: 'box' }); right.append(tsTable);
  }
  const drawTeamStats = (shown, shownPlays) => {
    if (!tsTable) return;
    const final = !live && shown >= g.drives.length && shownPlays == null;
    tsTable.innerHTML = ''; tsTable.append(el('tr', {}, el('th', {}, ''), el('th', {}, showAbbr(g.away.abbr)), el('th', {}, showAbbr(g.home.abbr))));
    right.querySelector('.ts-note').textContent = final ? 'Final' : 'Live';
    let A, H;
    if (final) { A = g.team_stats[g.away.abbr]; H = g.team_stats[g.home.abbr]; }
    else {
      const mk = () => ({ plays: 0, yards: 0, pass_yds: 0, rush_yds: 0, first_downs: 0, turnovers: 0, sacks_allowed: 0, penalties: 0, ypp: 0, third: '—', fourth: '—', red_zone: '—', top: '—', _3a: 0, _3c: 0, _4a: 0, _4c: 0, _rz: 0, _rztd: 0, _secs: 0 });
      const T = { [g.away.abbr]: mk(), [g.home.abbr]: mk() };
      const SCRIM = ['run', 'scramble', 'complete', 'incomplete', 'drop', 'interception', 'sack'];
      g.drives.slice(0, shown).forEach((d, di) => { const last = di === shown - 1; const partial = last && shownPlays != null; const plays = partial ? d.plays.filter(p => p.text).slice(0, shownPlays) : d.plays; const t = T[d.off]; if (!t) return;
        const clocks = plays.map(p => p.clock).filter(c => c != null);
        if (clocks.length >= 2) t._secs += Math.max(0, clocks[0] - clocks[clocks.length - 1]);
        plays.forEach((p, k) => { if (!p.type || p.nullified) return; const y = p.yards || 0;
          if (['run', 'scramble'].includes(p.type)) { t.plays++; t.yards += y; t.rush_yds += y; }
          else if (['complete', 'incomplete', 'drop', 'interception', 'sack'].includes(p.type)) { t.plays++; if (p.type === 'complete') { t.yards += y; t.pass_yds += y; } if (p.type === 'sack') { t.yards += y; t.pass_yds += y; t.sacks_allowed++; } if (p.type === 'interception') t.turnovers++; }
          else if (p.type === 'penalty') t.penalties++;
          if (p.kind === 'turnover' && !['interception', 'punt'].includes(p.type) && !p.safety) t.turnovers++;
          // third and fourth down: converted when the next scrimmage snap is a first down, or the play scored
          if (SCRIM.includes(p.type) && (p.down === 3 || p.down === 4)) { const next = plays.slice(k + 1).find(q => q.down != null && SCRIM.includes(q.type)); const conv = !p.defensive_td && (p.td || (next && next.down === 1) || (!next && !partial && d.result === 'Touchdown')); if (p.down === 3) { t._3a++; if (conv) t._3c++; } else { t._4a++; if (conv) t._4c++; } }
        });
        if (!partial) { t.first_downs += (d.first_downs || 0); if ((d.end != null && d.end >= 80) || /Touchdown/.test(d.result || '')) { t._rz++; if (/Touchdown/.test(d.result || '')) t._rztd++; } }   // the drive's end is on a 0-100 line toward the goal; inside the 20 is 80 and up
      });
      for (const t of Object.values(T)) { t.ypp = t.plays ? (t.yards / t.plays).toFixed(1) : '0.0'; t.third = t._3a ? `${t._3c}/${t._3a}` : '—'; t.fourth = t._4a ? `${t._4c}/${t._4a}` : '—'; t.red_zone = t._rz ? `${t._rztd}/${t._rz}` : '—'; t.top = t._secs ? `${Math.floor(t._secs / 60)}:${String(Math.round(t._secs % 60)).padStart(2, '0')}` : '—'; }
      A = T[g.away.abbr]; H = T[g.home.abbr];
    }
    for (const [k, label] of [['yards', 'Total Yards'], ['plays', 'Plays'], ['ypp', 'Yards per Play'], ['pass_yds', 'Passing'], ['rush_yds', 'Rushing'], ['first_downs', 'First Downs'], ['third', 'Third Down'], ['fourth', 'Fourth Down'], ['red_zone', 'Red Zone TD'], ['turnovers', 'Turnovers'], ['sacks_allowed', 'Sacks Allowed'], ['penalties', 'Penalties'], ['top', 'Possession']])
      tsTable.append(el('tr', {}, el('td', {}, label), el('td', {}, String(A[k] ?? '—')), el('td', {}, String(H[k] ?? '—'))));
  };
  const readBox = el('div', { class: 'readbox' }); right.append(readBox);
  const drawRead = (final) => { readBox.innerHTML = ''; if (!(g.reads && g.reads.length)) return; readBox.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, "Assistants' Read", el('small', {}, final ? '' : 'at the final'))); if (final) for (const r of g.reads) readBox.append(el('div', { class: 'pad', style: 'font-size:15.5px;color:var(--ink-2);padding-top:4px' }, r)); else readBox.append(el('div', { class: 'pad', style: 'font-size:14px;color:var(--ink-3)' }, 'The assistants read the game when it is over.')); };
  page.append(right, boxSheet);
  draw();
}

// ---------------------------------------------------------------- Club: roster, card, depth chart
let clubView = 'Overview', clubTab = 'active';
let inboxFilter = 'all';
function secondRow(items, current) {
  document.body.classList.remove('no-second');
  const s = $('#second'); s.innerHTML = '';
  for (const [label, hash] of items) s.append(el('a', { href: hash, 'aria-current': hash === current ? 'page' : null }, label));
}
function pill(word) { return el('span', { class: 'pill ' + word.toLowerCase() }, word); }
// THE DEVELOPMENT TIERS, one look everywhere: Normal (white), Rare (blue), Epic (purple), Legendary (orange-red)
const DEV_CLASS = { Normal: 'd-normal', Rare: 'd-rare', Epic: 'd-epic', Legendary: 'd-legend', Slow: 'd-slow' };
const DEV_NAME = { normal: 'Normal', star: 'Rare', superstar: 'Epic', xfactor: 'Legendary', slow: 'Slow', Star: 'Rare', Superstar: 'Epic', 'X-Factor': 'Legendary', Normal: 'Normal', Rare: 'Rare', Epic: 'Epic', Legendary: 'Legendary', Slow: 'Slow' };
const DEV_TIP = { Normal: 'Earns XP at the ordinary rate', Rare: 'Earns XP faster than most', Epic: 'Earns XP far faster; a franchise piece', Legendary: 'The rarest tier: the fastest growth in the game', Slow: 'Earns XP slower than most' };
// SCHEMES ON THE CARD: his fit to every scheme on his side, green a very good fit, yellow average, red a very bad
// fit, gray where the scheme has no effect on his position; your club's scheme marked
function schemeBlock(rows) {
  const box = el('div', {}, el('div', { class: 'h5', style: 'margin:12px 0 4px' }, 'Schemes'));
  const list = el('div', { class: 'schemes' });
  for (const r of rows) list.append(el('div', { class: 'sch ' + r.band + (r.mine ? ' mine' : ''), 'data-tip': r.fit == null ? `${r.name}: no effect on his position. ${r.words}` : `${r.name}: ${r.fit > 0 ? '+' : ''}${r.fit} to his grade. ${r.words}` }, el('span', { class: 'nm' }, r.name), r.mine ? el('small', {}, 'yours') : ''));
  box.append(list); return box;
}
function devTag(word, big) { const name = DEV_NAME[word] || 'Normal'; return el('span', { class: 'dev ' + (DEV_CLASS[name] || 'd-normal') + (big ? ' big' : ''), 'data-tip': DEV_TIP[name] || null }, name); }
function condBar(c) { return el('span', { class: 'cond' }, el('i', { class: c < 60 ? 'low' : c < 80 ? 'mid' : '', style: `width:${c}%` })); }
function ovrCell(o) { return el('span', { class: 'ovr ' + (o >= 88 ? 't1' : o >= 76 ? 't2' : 't3') }, o); }
function fitCell(f) { return el('span', { class: 'fit ' + (f > 0.05 ? 'p' : f < -0.05 ? 'm' : 'z') }, (f > 0 ? '+' : '') + f.toFixed(1)); }
// a jersey number of 0 is a number; only a missing one falls through to the position
function jerseyNo(n) { return (n === null || n === undefined || n === '') ? undefined : n; }
function playerExperience(season) { return Number(season) === 1 ? 'Rookie' : season ? `${season}${ord(season)} season` : ''; }
function who(r) { return el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, jerseyNo(r.no) ?? r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, [r.home_state, playerExperience(r.season_no)].filter(Boolean).join(' · ')))); }

let rosterSide = 'All', rosterQuery = '', rosterSel = null;
let viewClub = null;   // null = your own club; an abbreviation = another club's page, read-only
const CLUB_LIST = () => (view && view.rail && view.rail.clubs) ? view.rail.clubs : Object.keys(COLOR).sort().map(a => ({ abbr: a, name: a }));
function clubSelect(current, onPick) {
  const sel = el('select', { class: 'btn team-picker', 'aria-label': 'Choose a team', 'data-tip': "Choose any of the 32 teams" });
  const clubs = pyJSON('SESSION.club_list()');
  for (const c of clubs) sel.append(el('option', { value: c.abbr, selected: c.abbr === current ? '' : null }, `${c.name}${c.mine ? ' (User)' : ''}`));
  sel.onchange = () => onPick(sel.value);
  return sel;
}
function clubNav(abbr, mine, current) {
  // the club's own sub-tabs: your team keeps its pages, another team's live under its team page
  if (mine) return [['Roster', '#club'], ['Depth Chart', '#club/depth'], ['Practice Squad', '#club/ps'], ['Injured Reserve', '#club/ir'], ['Progression', '#club/progression'], ['Regression', '#club/regression'], ['Schedule', '#club/schedule']];
  return [['Roster', `#club/team/${abbr}/roster`], ['Depth Chart', `#club/team/${abbr}/depth`], ['Practice Squad', `#club/team/${abbr}/ps`], ['Injured Reserve', `#club/team/${abbr}/ir`], ['Schedule', `#league/team/${abbr}/schedule`]];
}

function renderRoster(v) {
  renderRail(v.rail);
  const mine = v.mine !== false; const abbr = v.club_abbr || v.rail.club.abbr;
  const page = $('#page'); page.innerHTML = ''; page.className = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Team'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'club'));
  secondRow(clubNav(abbr, mine, null), mine ? (clubTab === 'ps' ? '#club/ps' : clubTab === 'ir' ? '#club/ir' : '#club') : (clubTab === 'ps' ? `#club/team/${abbr}/ps` : clubTab === 'ir' ? `#club/team/${abbr}/ir` : `#club/team/${abbr}/roster`));
  const sheet = el('section', { class: 'sheet c12 roster-board' });
  sheet.style.setProperty('--roster-team', teamTheme(v.rail.club).base);
  sheet.style.setProperty('--roster-accent', teamTheme(v.rail.club).accent);
  const metric = (value, label) => el('div', {}, el('b', {}, value), el('small', {}, label));
  sheet.append(el('header', {class:'roster-hero'},
    el('div', {}, el('div', {class:'roster-team-name'}, v.rail.club.name || abbr), el('h1', {}, 'ROSTER'),
      v.count > 53 ? el('small', {class:'roster-limit'}, `${v.count - 53} players over the regular-season limit`) : el('small', {}, 'Team personnel')),
    el('div', {class:'roster-metrics'}, metric(`${v.count} / 53`, 'Active'), metric(`$${v.cap_total.toFixed(1)}m`, 'Cap committed'), metric(v.rail.cap, 'Cap space'))));
  const tabs = el('div', { class: 'tabs' });
  for (const [k, label, n] of [['active', 'Active', v.count], ['ps', 'Practice Squad', v.practice.length], ['injured', 'Injured', v.injured.length]])
    tabs.append(el('button', { 'aria-pressed': String(clubTab === k), onclick: () => { clubTab = k; const want = mine ? (k === 'ps' ? '#club/ps' : k === 'ir' ? '#club/ir' : k === 'active' ? '#club' : null) : (k === 'ps' ? `#club/team/${abbr}/ps` : k === 'active' ? `#club/team/${abbr}/roster` : null); if (want && location.hash !== want) { location.hash = want; } else renderRoster(v); } }, label + ' ', el('em', {}, n)));
  const views = el('div', { class: 'tabs', style: 'margin-left:14px' });
  for (const k of ['Overview', 'Ratings', 'Contract', 'Stats']) views.append(el('button', { 'aria-pressed': String(clubView === k), onclick: () => { clubView = k; renderRoster(v); } }, k));
  const sides = el('div', { class: 'chips' });
  for (const k of ['All', 'Offense', 'Defense', 'Specialists']) sides.append(el('button', { class: 'chip', 'aria-pressed': String(rosterSide === k), onclick: () => { rosterSide = k; renderRoster(v); } }, k));
  const search = el('input', { type: 'search', class: 'find', placeholder: 'Find a player', value: rosterQuery }); search.oninput = () => { rosterQuery = search.value; drawRows(); };
  const count = el('span', { class: 'count', style: 'margin-left:auto' });
  const pick = clubSelect(abbr, a => { const m = pyJSON('SESSION.club_list()').find(c => c.abbr === a); location.hash = m && m.mine ? (clubTab === 'ps' ? '#club/ps' : '#club') : `#club/team/${a}/${clubTab === 'ps' ? 'ps' : 'roster'}`; });
  tabs.classList.add('roster-membership'); views.classList.add('roster-views');
  sheet.append(el('div', {class:'roster-top-tools'}, tabs, pick), el('div', {class:'roster-filters'}, views, sides, search));
  const tbl = el('table', { class: 'tbl' });
  const H = (t, tip, n) => el('th', { 'data-tip': tip || null, class: n ? 'n' : null }, t);
  const heads = { Overview: [H('Player'), H('Pos', 'Position'), H('Age', null, 1), H('Ovr', 'Overall Rating', 1), H('Fit', "How well the player matches your coach's scheme", 1), H('Dev', 'Rate of XP Growth'), H('Condition', 'Game-day Freshness'), H('Morale', "Player's happiness"), H('Yrs', 'Years left on his contract', 1), H('Cap Hit', "This year's cap hit", 1), H('Penalty', 'Dead cap charged if player is cut/traded', 1), H('Status'), H('')],
                  Ratings: [H('Player'), H('Pos', 'Position'), H('Age', null, 1), H('Ovr', 'Overall Rating', 1), H('Ceiling', "The player's estimated potential", 1), H('Dev', 'Rate of XP Growth'), H('Fit', "How well the player matches your coach's scheme", 1), H('Morale', "Player's happiness"), H('')],
                  Contract: [H('Player'), H('Pos', 'Position'), H('Age', null, 1), H('Yrs', 'Years left on his contract', 1), H('Cap Hit', "This year's cap hit", 1), H('Penalty', 'Dead cap charged if player is cut/traded', 1), H('Status'), H('')],
                  Stats: [H('Player'), H('Pos', 'Position'), H('G', 'Games played', 1), H('This Season'), H('Comp%', 'Completion pct for a quarterback, catch pct for a receiver', 1), H('EPA', 'Expected points added per dropback, rush or target. Defense: shared on-field EPA per snap, divided equally among all 11 defenders; higher is better, not an individual grade.', 1), H('')] }[clubView];
  const hasStatus = ['Overview', 'Contract'].includes(clubView);
  if (clubTab === 'ps' || clubTab === 'ir') { heads.splice(heads.length - (hasStatus ? 2 : 1), hasStatus ? 2 : 1); heads.push(el('th', {}, clubTab === 'ir' ? 'IR' : '')); }
  const acts = r => el('td', {}, el('div', { class: 'row-act' },
    el('button', { 'aria-label': 'Card', 'data-tip': 'Open his card', onclick: e => { e.stopPropagation(); location.hash = '#club/player/' + r.pid; } }, '▣'),
    el('button', { 'aria-label': 'Extend', 'data-tip': 'Ask his agent and open the talks', onclick: e => { e.stopPropagation(); const res = pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind='extension')`); notify(res); if (res.ok) location.hash = '#personnel/extensions'; } }, '$'),
    el('button', { 'aria-label': 'Trade Block', 'data-tip': 'Put him in a trade package', onclick: e => { e.stopPropagation(); tradeState = { other: tradeState.other, a: [r.pid], b: [], keep: true }; location.hash = '#personnel/trades'; } }, '⇄')));
  const drawRows = () => {
    tbl.innerHTML = ''; tbl.append(el('tr', {}, ...heads));
    const q = rosterQuery.trim().toLowerCase(); let shown = 0;
    const rowsFor = () => clubTab === 'ps' ? [{ title: 'Practice Squad', rows: v.practice }] : clubTab === 'ir' ? [{ title: `Injured Reserve · ${v.ir_returns_left} returns left`, rows: v.ir || [] }] : clubTab === 'injured' ? [{ title: 'Injured', rows: v.injured }] : v.groups;
    for (const g of rowsFor()) {
      const rows = g.rows.filter(r => (rosterSide === 'All' || r.side === rosterSide.toLowerCase().replace('specialists', 'special')) && (!q || r.name.toLowerCase().includes(q) || (r.home_state || '').toLowerCase().includes(q) || r.pos.toLowerCase() === q));
      if (!rows.length) continue;
      tbl.append(el('tr', { class: 'grp' }, el('td', { colspan: String(heads.length) }, `${g.title} · ${rows.length}`)));
      for (const r of rows) {
        shown++;
        const cells = { Overview: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, fitCell(r.fit)), el('td', {}, devTag(r.dev)), el('td', {}, condBar(r.cond)), el('td', {}, pill(r.morale)), el('td', { class: 'n' }, r.yrs), el('td', { class: 'n' }, `$${r.hit.toFixed(1)}m`), el('td', { class: 'n', 'data-tip': cutPenaltyText(r) }, `$${r.penalty.toFixed(1)}m`, r.penalty_next ? el('small', {}, ` + $${r.penalty_next.toFixed(1)}m next yr`) : ''), el('td', {}, el('span', { class: 'inj' }, r.status))],
                        Ratings: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, r.pot_range ? `${r.pot_range[0]}–${r.pot_range[1]}` : (r.pot ?? '—')), el('td', {}, devTag(r.dev)), el('td', { class: 'n' }, fitCell(r.fit)), el('td', {}, pill(r.morale))],
                        Contract: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, r.yrs), el('td', { class: 'n' }, `$${r.hit.toFixed(1)}m`), el('td', { class: 'n', 'data-tip': cutPenaltyText(r) }, `$${r.penalty.toFixed(1)}m`, r.penalty_next ? el('small', {}, ` + $${r.penalty_next.toFixed(1)}m next yr`) : ''), el('td', {}, el('span', { class: 'inj' }, r.status))],
                        Stats: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.stats.games), el('td', { style: 'text-align:left;font-family:var(--mono);font-size:14px' }, r.stats.line), el('td', { class: 'n' }, r.stats.comp != null ? `${r.stats.comp}%` : '—'), el('td', { class: 'n', 'data-tip': r.stats.epa_note || null, style: r.stats.epa != null ? (r.stats.epa > 0 ? 'color:var(--ok)' : 'color:var(--danger)') : '' }, r.stats.epa != null ? (r.stats.epa > 0 ? '+' : '') + r.stats.epa.toFixed(2) : '—')] }[clubView]();
        if (clubTab === 'ps' || clubTab === 'ir') { if (hasStatus) cells.splice(cells.length - 1, 1); }   // the squad and IR pages carry no Status column and no card/agent/trade icons
        else if (!mine) { if (hasStatus) cells.splice(cells.length - 1, 1); cells.push(el('td', {}, el('div', { class: 'row-act' }, el('button', { 'aria-label': 'Card', 'data-tip': 'Open his card', onclick: e => { e.stopPropagation(); location.hash = '#club/player/' + r.pid; } }, '▣'), el('button', { 'aria-label': 'Trade', 'data-tip': 'Ask about him in a trade', onclick: e => { e.stopPropagation(); tradeState = { other: abbr, a: [], b: [r.pid] }; location.hash = '#personnel/trades'; } }, '⇄')))); }
        else cells.push(acts(r));
        if (clubTab === 'ir' && !mine) cells.push(el('td', {}, r.returnable ? `Placed week ${r.ir_week}` : 'Season'));
        if (clubTab === 'ir' && mine) cells.push(el('td', {}, el('div', { class: 'row-act', style: 'opacity:1' }, el('span', { class: 'muted', style: 'font-size:12px;margin-right:6px' }, r.returnable ? `placed wk ${r.ir_week}` : 'season'), el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', disabled: mine && r.can_activate ? null : '', 'data-tip': r.can_activate ? 'Back to the 53 (a spot must be open)' : (r.returnable ? 'Four weeks on the list and healthy first' : 'Placed for the season; no return'), onclick: () => { const res = pyJSON(`SESSION.club_act('ir_activate', pid=${JSON.stringify(r.pid)})`); notify(res); renderRoster(pyJSON('SESSION.club_roster()')); } }, 'Activate'))));
        if (clubTab === 'ps' && !mine) {
          cells.push(el('td', {}, el('div', { style: 'display:flex' }, el('button', { class: 'btn go', style: 'width:auto;padding:3px 8px;font-size:14px', 'data-tip': "Sign him to your 53; he must stay on it three weeks", onclick: () => { const res = pyJSON(`SESSION.personnel_act('poach_ps', pid=${JSON.stringify(r.pid)})`); notify(res.ok ? { ok: true, line: res.line } : res); if (res.ok) location.hash = '#personnel/fa'; } }, 'Sign to Your Roster'))));
        } else if (clubTab === 'ps') {
          const act = (name, extra) => { const res = pyJSON(`SESSION.club_act(${JSON.stringify(name)}, ${extra})`); notify(res); renderRoster(pyJSON('SESSION.club_roster()')); };
          cells.push(el('td', {}, el('div', { class: 'row-act', style: 'opacity:1' },
            el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', 'data-tip': 'Sign him to the 53 at the minimum', onclick: () => act('call_up', `pid=${JSON.stringify(r.pid)}`) }, 'Call Up'),
            el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', disabled: r.elevated_now ? '' : null, 'data-tip': v.playoff_elevations ? 'Dress him for this game · unlimited playoff elevations per player' : `Dress him Sunday and send him back after · ${r.elevations} of ${v.per_man_max} used`, onclick: () => act('elevate', `pids=[${JSON.stringify(r.pid)}]`) }, r.elevated_now ? 'Elevated' : v.playoff_elevations ? 'Elevate' : `Elevate · ${r.elevations}/${v.per_man_max}`),
            el('button', { class: 'btn warn', style: 'width:auto;padding:3px 8px;font-size:14px', onclick: () => { if (confirm(`Release ${r.name} from the practice squad?`)) act('release_ps', `pid=${JSON.stringify(r.pid)}`); } }, 'Release'))));
        }
        const tr = el('tr', { class: (/^Out/.test(r.status) ? 'out' : '') + (rosterSel === r.pid ? ' sel' : ''), onclick: e => { if (e.target.closest('.row-act') || e.target.closest('.who')) return; rosterSel = rosterSel === r.pid ? null : r.pid; drawRows(); drawFoot(); } }, ...cells);
        tbl.append(tr);
      }
    }
    count.textContent = `${shown} of ${v.count} on the roster · Cap $${v.cap_total.toFixed(1)}m`;
  };
  const foot = el('div', { class: 'foot roster-actions' });
  const drawFoot = () => {
    foot.innerHTML = '';
    if (!mine) { foot.append(el('span', { class: 'count' }, `${v.count} on the 53 · ${v.practice.length} on the practice squad`)); return; }
    const all = [...v.groups.flatMap(g => g.rows), ...v.practice, ...v.injured]; const r = all.find(x => x.pid === rosterSel);
    if (!r) { foot.append(el('span', { class: 'count' }, clubTab === 'ps' ? `Elevations this week: ${v.elevations_used} of ${v.elevations_max} · ` + (v.playoff_elevations ? 'unlimited playoff elevations per player' : `a player's ${v.per_man_max + 1}${ord(v.per_man_max + 1)} elevation signs him to the 53`) : 'Click a row to select a player, then act on him here.')); return; }
    foot.append(el('span', { class: 'count' }, el('b', {}, r.name), ` · ${r.pos} · ${r.ovr} · ${r.yrs} yr${r.yrs === 1 ? '' : 's'} · $${r.hit.toFixed(1)}m`),
      el('button', { class: 'btn', style: 'margin-left:auto', onclick: () => { location.hash = '#club/player/' + r.pid; } }, 'Card'),
      el('button', { class: 'btn go', onclick: () => { const res = pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind='extension')`); notify(res); if (res.ok) location.hash = '#personnel/extensions'; } }, 'Extend'),
      el('button', { class: 'btn', onclick: () => { tradeState = { other: tradeState.other, a: [r.pid], b: [], keep: true }; location.hash = '#personnel/trades'; } }, 'Trade Block'),
      el('button', { class: 'btn warn', onclick: () => { if (!confirm(`Cut ${r.name}? Penalty ${cutPenaltyText(r)}.`)) return; const res = pyJSON(`SESSION.club_act('cut', pid=${JSON.stringify(r.pid)})`); notify(res.ok ? { ok: true, line: `${res.name} released. Penalty ${cutPenaltyText(res)}.` } : res); rosterSel = null; renderRoster(pyJSON('SESSION.club_roster()')); } }, `Cut · Penalty $${r.penalty.toFixed(1)}m`));
  };
  sheet.append(el('div', {class:'roster-table-scroll'}, tbl), el('div', {class:'roster-count'}, count), foot); drawRows(); drawFoot();
  page.append(sheet);
}

const TRAIT_META = {
  'grinder': { k: 'work', tip: 'Outworks his rating. Gains XP faster and keeps his condition.' }, 'hard worker': { k: 'work', tip: 'Puts in the time. A little more development than most.' },
  'coasts': { k: 'work-', tip: 'Does the minimum. Develops slower than his talent says he should.' }, 'needs pushing': { k: 'work-', tip: 'Has to be driven. The slowest to improve, and condition slips.' },
  'wants to be paid': { k: 'money', tip: 'Money first. He will hold out for market value and will not take a discount.' }, 'money matters': { k: 'money', tip: 'Wants a fair number. Harder to extend cheaply.' },
  'not about the money': { k: 'money-', tip: 'Will leave money on the table for the right situation.' }, 'plays for the love of it': { k: 'money-', tip: 'Money is an afterthought. The easiest player on the roster to extend.' },
  'loyal': { k: 'loyal', tip: 'Wants to finish here. Likely to take less to stay.' }, 'settled': { k: 'loyal', tip: 'Comfortable where he is. Not looking to leave.' },
  'keeps his options open': { k: 'loyal-', tip: 'Will test the market when his deal is up.' }, 'follows the money': { k: 'loyal-', tip: 'No attachment to the club. Goes to the highest bidder.' },
  'wants the ball': { k: 'amb', tip: 'Needs a big role. Unhappy as a backup or in a rotation.' }, 'ambitious': { k: 'amb', tip: 'Wants to start and to matter. Morale depends on his snaps.' },
  'team-first': { k: 'amb-', tip: 'Accepts his role. Morale holds even when the snaps drop.' }, 'happy in a role': { k: 'amb-', tip: 'Content wherever you put him. The easiest player to keep happy.' },
  'even-keeled': { k: 'even', tip: 'Nothing about him stands out either way.' },
};
let cardTab = 'Overview', cardPid = null;
function openPlayer(pid, tab = 'Overview') {
  cardPid = pid; cardTab = tab;
  const hash = '#club/player/' + pid;
  if (location.hash === hash) renderCard(pyJSON(`SESSION.club_card(${JSON.stringify(pid)})`));
  else location.hash = hash;
}

function renderCard(v) {
  if (v.cls_year !== undefined && v.confidence !== undefined) return renderProspectCard(v);
  // a different player opens on Overview; the chosen tab sticks only while looking at the same player, so a link
  // from a list (extensions, the roster, a trade) never lands on whichever tab was open on the last card
  if (v.pid !== cardPid) { cardTab = 'Overview'; cardPid = v.pid; }
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.className = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Team'; secondRow([['Roster', '#club'], ['Depth Chart', '#club/depth'], ['Practice Squad', '#club/ps']], '');
  if (v.error) { page.append(el('section', { class: 'sheet c12' }, el('div', { class: 'empty' }, v.error))); return; }
  const s = el('section', { class: 'sheet c12 player-card' });
  applyTeamTheme(s, v.team || {});
  const cardColor = teamTheme(v.team || {}).accent;
  s.style.setProperty('--pc-accent', cardColor);
  const rgb = parseInt(cardColor.slice(1), 16);
  const brightness = (((rgb >> 16) & 255) * 299 + ((rgb >> 8) & 255) * 587 + (rgb & 255) * 114) / 1000;
  s.style.setProperty('--pc-on-accent', brightness > 145 ? '#111' : '#fff');
  s.style.setProperty('--pc-accent-ink', brightness > 145 ? cardColor : `color-mix(in srgb, ${cardColor} 55%, white)`);
  const col = v.team ? v.team.color : 'var(--rule-hi)';
  s.append(el('div', { class: 'head' },
    el('div', { class: 'jersey', style: `background:${col}` }, jerseyNo(v.no) ?? v.pos),
    el('div', {}, el('div', { class: 'hname' }, v.name.toUpperCase()),
      el('div', { class: 'hline' }, el('b', {}, v.pos), ` · ${v.age}${v.size ? ' · ' + v.size : ''}${v.home_state ? ' · Home State: ' + v.home_state : ''}${v.season_no ? ` · ${playerExperience(v.season_no)}` : ''} · ${v.draft}` + (v.team ? ` · ${v.team.name}` : ' · Free agent')),
      el('div', { class: 'hfacts' }, ...(v.free_agent ? [el('div', {}, el('span', {}, 'Status'), el('b', {}, v.on_wire ? 'On the wire' : 'Free agent')), el('div', {}, el('span', {}, 'Market'), el('b', {}, v.market_apy != null ? `~$${v.market_apy}m per year` : ''))] : [el('div', {}, el('span', {}, `Cap Hit ${v.rail.year}`), el('b', {}, `$${v.contract.hit.toFixed(1)}m`)), el('div', {}, el('span', {}, 'Penalty'), el('b', { 'data-tip': cutPenaltyText(v.contract) }, `$${v.contract.penalty.toFixed(1)}m`)), el('div', {}, el('span', {}, 'Trade Value'), el('b', { style: 'color:var(--ink-2)' }, v.interest))]))),
    el('div', { class: 'ovrbig' }, el('b', {}, v.ovr), el('span', {}, 'Overall · Scheme Fit ', el('strong', { class: 'fit-change ' + (v.fit >= 0 ? 'positive' : 'negative') }, `${v.fit >= 0 ? '+' : ''}${v.fit.toFixed(1)}`)))));
  // tabs and actions
  const tabs = el('div', { class: 'ctabs' });
  for (const t of ['Overview', 'Contract', 'Stats', 'Career', 'History'].concat(v.actions && v.actions.mine ? ['Development'] : [])) tabs.append(el('button', { 'aria-pressed': String(cardTab === t), onclick: () => { cardTab = t; renderCard(v); } }, t));
  const acts = el('div', { class: 'acts' });
  if (v.actions.mine) {
    acts.append(el('button', { class: 'btn' + (v.ext_eligible ? ' go' : ''), disabled: v.ext_eligible ? null : '', 'data-tip': v.ext_eligible ? `Ask his agent (~$${v.ext_ask ?? '?'}m) and open the talks` : 'Not eligible yet', onclick: () => { const r = pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(v.pid)}, kind='extension')`); notify(r); if (r.ok) location.hash = '#personnel/extensions'; } }, 'Extend'));
    if (v.rookie_option != null) acts.append(el('button', { class: 'btn go', 'data-tip': `Add the guaranteed fifth year at $${v.rookie_option.toFixed(1)}m`, onclick: () => { const r = pyJSON(`SESSION.personnel_act('rookie_option', pid=${JSON.stringify(v.pid)})`); notify(r); if (r.ok) renderCard(pyJSON(`SESSION.club_card(${JSON.stringify(v.pid)})`)); } }, `5th Year · $${v.rookie_option.toFixed(1)}m`));
    acts.append(el('button', { class: 'btn', 'data-tip': 'Open the restructure preview on his contract', onclick: () => { restructureFor = v.pid; location.hash = '#frontoffice/cap'; } }, 'Restructure'));
    const alts = v.grades.filter(g => !g.mine && g.pos !== 'Nickel');
    if (alts.length) { const sel = el('select', { class: 'btn' }); sel.append(el('option', { value: '' }, 'Position Change')); alts.forEach(g => sel.append(el('option', { value: g.pos }, `${g.pos} · ${g.ovr} Ovr`))); sel.onchange = () => { if (!sel.value) return; const r = pyJSON(`SESSION.club_act('position_change', pid=${JSON.stringify(v.pid)}, new_pos=${JSON.stringify(sel.value)})`); notify(r.ok ? { ok: true, line: `${r.name} moves to ${r.to}: ${r.penalty} points for ${r.games} games.` } : r); if (r.ok) renderCard(pyJSON(`SESSION.club_card(${JSON.stringify(v.pid)})`)); }; acts.append(sel); }
    acts.append(el('button', { class: 'btn', 'data-tip': 'Put him in a trade package and shop him', onclick: () => { tradeState = { other: tradeState.other, a: [v.pid], b: [], keep: true }; location.hash = '#personnel/trades'; } }, 'Trade Block'));
    acts.append(el('button', { class: 'btn warn', onclick: () => { if (!confirm(`Cut ${v.name}? Penalty ${cutPenaltyText(v.contract)}.`)) return; const r = pyJSON(`SESSION.club_act('cut', pid=${JSON.stringify(v.pid)})`); notify(r.ok ? { ok: true, line: `${r.name} released. Penalty ${cutPenaltyText(r)}.` } : r); location.hash = '#club'; } }, `Cut · Penalty $${v.contract.penalty.toFixed(1)}m`));
    acts.append(el('button', { class: 'btn', disabled: v.actions.ps_ok ? null : '', 'data-tip': v.actions.ps_ok ? (v.actions.vested ? 'A vested veteran: he goes straight to the practice squad' : 'He must clear waivers first; if no team claims him at the Advance he joins your practice squad') : 'The squad has no room for him under its rules', onclick: () => { if (!confirm(`Waive ${v.name} to the practice squad? Penalty ${cutPenaltyText(v.contract)}.${v.actions.vested ? '' : ' Another team may claim him first.'}`)) return; const r = pyJSON(`SESSION.club_act('to_squad', pid=${JSON.stringify(v.pid)})`); notify(r); if (r.ok) location.hash = '#club'; } }, 'Waive to Practice Squad'));
    if (v.actions.hurt && !v.actions.on_ir) acts.append(el('button', { class: 'btn', 'data-tip': 'Injured reserve: off the 53 now, salary counts in full; back after four weeks if a return is left', onclick: () => { const se = confirm(`Place ${v.name} on IR.\n\nOK = designated to return (four weeks minimum, uses one of the team's returns).\nCancel = ask again for season-ending.`); let res; if (se) res = pyJSON(`SESSION.club_act('ir', pid=${JSON.stringify(v.pid)})`); else if (confirm(`Place ${v.name} on IR for the season? He will not return this year.`)) res = pyJSON(`SESSION.club_act('ir', pid=${JSON.stringify(v.pid)}, season_ending=True)`); else return; notify(res); if (res.ok) location.hash = '#club/ir'; } }, 'Place on IR'));
    if (v.actions.on_ir) acts.append(el('button', { class: 'btn', 'data-tip': 'Back to the 53', onclick: () => { const res = pyJSON(`SESSION.club_act('ir_activate', pid=${JSON.stringify(v.pid)})`); notify(res); if (res.ok) location.hash = '#club'; } }, 'Activate from IR'));
  }
  acts.append(el('button', { class: 'btn quiet', onclick: () => history.back() }, 'Back'));
  tabs.append(acts); s.append(tabs);
  const h5 = (t, sub) => el('div', { class: 'h5' }, t, sub ? el('span', {}, sub) : '');
  const contractTable = style => {
    const ct = el('table', { class: 'contract', style: style || '' });
    ct.append(el('tr', {}, el('th', {}, 'Year'), el('th', {}, 'Base'), el('th', {}, 'Bonus'), el('th', {}, 'Cap Hit'), el('th', {}, 'Penalty')));
    v.contract.by_year.forEach((y, i) => ct.append(el('tr', { class: i === 0 ? 'now' : '' },
      el('td', {}, y.year), el('td', {}, y.base != null ? `$${y.base.toFixed(1)}m` : '—'),
      el('td', {}, y.bonus != null ? `$${y.bonus.toFixed(1)}m` : '—'),
      el('td', {}, `$${y.hit.toFixed(1)}m`),
      el('td', { 'data-tip': y.penalty != null ? cutPenaltyText(y, y.year) : '' },
        y.penalty != null ? `$${y.penalty.toFixed(1)}m` : '—'))));
    return ct;
  };
  if (cardTab === 'Overview') {
    const left = el('div', {});
    left.append(h5('Positions'));
    const pm = el('div', { class: 'posmap', style: `grid-template-columns:repeat(${Math.min(5, v.grades.length)},1fr)` }); v.grades.forEach(g => pm.append(el('div', { class: g.mine ? 'nat' : 'fam' }, g.pos))); left.append(pm);
    left.append(h5('Status'));
    left.append(el('div', { class: 'kv' }, el('span', {}, 'Role'), el('span', {}, v.role || '—'), el('span', {}, 'Snaps'), el('span', {}, v.snaps || 'None yet this season'), el('span', {}, 'Health'), el('span', {}, (v.out ? (v.out >= 99 ? 'Out for the season' : `Out; returns week ${v.out + 1}`) : 'Healthy') + (v.missed ? ` · ${v.missed} game${v.missed === 1 ? '' : 's'} missed` : ' · no games missed')), el('span', {}, 'Condition'), el('span', {}, `${v.cond}%`), el('span', {}, 'Position Change'), el('span', {}, v.pending)));
    const mid = el('div', {});
    mid.append(h5('Attributes'));
    const attrs = el('div', { class: 'attrs' });
    for (const c of v.cols) {
      const box = el('div', {}, el('div', { class: 'h5', style: 'margin-bottom:4px' }, c.title));
      const rowsOf = rows => { for (const r of rows) { const row = el('div', { class: 'arow ' + r.tier }, el('span', {}, r.label)); row.append(r.shift ? el('em', { class: 'fitd ' + (r.shift > 0 ? 'p' : 'm'), 'data-tip': r.shift > 0 ? `${r.scheme} counts this more` : `${r.scheme} counts this less` }, r.scheme || '') : el('em', {})); row.append(el('b', {}, r.v)); box.append(row); } };
      rowsOf(c.rows);
      if (c.extra && c.extra.rows && c.extra.rows.length) { box.append(el('div', { class: 'h5', style: 'margin:12px 0 4px' }, c.extra.title)); rowsOf(c.extra.rows); }
      if (c.title === 'Mental' && v.personality) { box.append(el('div', { class: 'h5', style: 'margin:12px 0 4px' }, 'Traits')); const tr = el('div', { class: 'traits' }); v.personality.split(',').map(x => x.trim()).filter(Boolean).forEach(w => { const m = TRAIT_META[w] || { k: 'even', tip: 'Nothing about him stands out.' }; tr.append(el('span', { class: 'trait ' + m.k, 'data-tip': m.tip }, w.replace(/\b\w/g, ch => ch.toUpperCase()))); }); box.append(tr); }
      if (c.title === 'Mental' && v.schemes) box.append(schemeBlock(v.schemes));
      attrs.append(box);
    }
    mid.append(attrs);
    const right = el('div', {});
    right.append(h5('Contract'));
    if (v.contract.by_year.length) right.append(contractTable());
    right.append(el('div', { class: 'kv', style: 'margin-top:8px' }, el('span', {}, 'Market'), el('span', {}, v.market_apy != null ? `About $${v.market_apy}m per year` : '—'), el('span', {}, 'Extension'), el('span', {}, v.ext_eligible ? `Eligible${v.ext_ask != null ? ` · agent's ask ~$${v.ext_ask}m` : ''}` : 'Not yet eligible')));
    if (!v.free_agent) right.append(h5('Trade Value', "the scout's read"), el('div', { class: 'kv' }, el('span', {}, 'Market'), el('span', {}, v.market), el('span', {}, 'Interest'), el('span', {}, v.interest_line)));
    s.append(el('div', { class: 'body' }, left, mid, right));
    const tiles = el('div', { class: 'tiles' },
      el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Morale'), el('div', { class: 'word' }, v.morale)),
      el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Condition'), el('div', { class: 'word' }, `${v.cond}%`), el('div', { class: 'sub' }, v.out ? `Out until week ${v.out}` : v.cond >= 85 ? 'Fresh' : v.cond >= 70 ? 'Carrying a load' : 'Worn down'), el('div', { class: 'cond', style: 'width:100%;height:8px;margin-top:8px' }, el('i', { class: v.cond < 60 ? 'low' : v.cond < 80 ? 'mid' : '', style: `width:${v.cond}%` }))),
      el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Development'), el('div', { class: 'word' }, devTag(v.dev, true)), el('div', { class: 'sub' }, v.dev_line)),
      el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Ceiling'), el('div', { class: 'word' }, v.ceiling), el('div', { class: 'sub' }, "your scouts' range for where he tops out")));
    s.append(tiles);
  } else if (cardTab === 'Contract') {
    const box = el('div', { class: 'pad' }, h5('Contract'));
    if (v.contract.by_year.length) box.append(contractTable('max-width:620px'));
    else box.append(el('div', { class: 'empty' }, 'No contract on file.'));
    box.append(el('div', { class: 'kv', style: 'margin-top:12px;max-width:620px' }, el('span', {}, 'Market'), el('span', {}, v.market_apy != null ? `About $${v.market_apy}m per year` : '—'), el('span', {}, 'Extension'), el('span', {}, v.ext_eligible ? `Eligible${v.ext_ask != null ? ` · agent's ask ~$${v.ext_ask}m` : ''}` : 'Not yet eligible'), el('span', {}, 'Penalty if cut now'), el('span', {}, cutPenaltyText(v.contract))));
    s.append(box);
  } else if (cardTab === 'Stats' || cardTab === 'Career') {
    const box = el('div', { class: 'pad' }, h5(cardTab === 'Stats' ? 'Season Stats' : 'Career', cardTab === 'Stats' ? `${v.rail.year} · ${v.games} game${v.games === 1 ? '' : 's'}` : `${v.seasons.length} season${v.seasons.length === 1 ? '' : 's'} on record`));
    const rows = cardTab === 'Stats' ? v.seasons.filter(sn => sn.year === v.rail.year) : v.seasons.slice().reverse();
    if (v.season.epa_note) box.append(el('p', { class: 'muted' }, v.season.epa_note));
    if (rows.length) { const t = el('table', { class: 'stab', style: 'max-width:900px' }); t.append(el('tr', {}, el('th', {}, 'Season'), el('th', {}, 'Team'), el('th', {}, 'G'), ...v.season.cols.map(c => el('th', {}, c)))); for (const sn of rows) t.append(el('tr', {}, el('td', {}, sn.year), el('td', {}, sn.team), el('td', {}, sn.games), ...sn.row.map(x => el('td', {}, String(x))))); box.append(t); }
    else box.append(el('div', { class: 'empty' }, cardTab === 'Stats' ? 'No snaps yet this season.' : 'No seasons on record yet.'));
    s.append(box);
  } else if (cardTab === 'Development') {
    s.append(developmentPanel(v.pid, () => renderCard(pyJSON(`SESSION.club_card(${JSON.stringify(v.pid)})`))));
  } else {
    const box = el('div', { class: 'pad' }, h5('History', 'moves, deals and changes on record'));
    const h = el('div', { class: 'histlist', style: 'max-width:720px' });
    for (const x of (v.history || [])) h.append(el('div', {}, el('time', {}, x.when), el('span', {}, x.line)));
    if (!(v.history || []).length) h.append(el('div', {}, el('time', {}, '—'), el('span', {}, 'Nothing on record yet.')));
    box.append(h); s.append(box);
  }
  page.append(s);
}

// Ceiling milestones are deliberate notifications, separate from routine action feedback.
let ceilingNoticeQueued = false, ceilingNoticeOpen = false;
function queueCeilingNoticeCheck() {
  if (ceilingNoticeQueued || ceilingNoticeOpen || !py) return;
  ceilingNoticeQueued = true;
  queueMicrotask(() => {
    ceilingNoticeQueued = false;
    if (ceilingNoticeOpen || document.querySelector('dialog[open]')) return;
    const report = pyJSON('SESSION.development_notices()');
    if (!report.players?.length) return;
    ceilingNoticeOpen = true;
    const dialog = el('dialog', {class:'retain-tag-dialog ceiling-dialog', 'aria-labelledby':'ceiling-notice-title'});
    applyTeamTheme(dialog, report.club);
    const body = el('div', {class:'retain-dialog-body'}, el('small', {}, 'PLAYER DEVELOPMENT'), el('h2', {id:'ceiling-notice-title'}, 'Ceiling reached'));
    let openPid = null;
    for (const player of report.players) body.append(el('div', {class:'ceiling-milestone'},
      el('p', {}, player.can_unlock
        ? `${player.name} has reached their overall ceiling. Unlock a higher ceiling by spending XP.`
        : `${player.name} has reached the maximum overall ceiling. It cannot be raised further.`),
      el('button', {class:'btn', onclick:() => { openPid = player.pid; dialog.close(); }}, 'Open Development')));
    const dismiss = el('button', {class:'btn go', onclick:() => dialog.close()}, 'Got it');
    dialog.append(body, el('div', {class:'retain-dialog-actions'}, dismiss));
    dialog.addEventListener('close', () => {
      for (const player of report.players) {
        const result = pyJSON(`SESSION.dismiss_ceiling_notice(${JSON.stringify(player.pid)}, ${player.unlocks})`);
        if (!result.ok) notify(result);
      }
      dialog.remove(); ceilingNoticeOpen = false;
      if (openPid) openPlayer(openPid, 'Development');
    }, {once:true});
    document.body.append(dialog); dialog.showModal(); dismiss.focus();
  });
}
// A milestone deferred behind a negotiation or another dialog gets its turn on close.
document.addEventListener('close', () => queueMicrotask(queueCeilingNoticeCheck), true);

// the development sheet: his bank, his ceiling, every attribute with the price of the next point
function developmentPanel(pid, reload) {
  const d = pyJSON(`SESSION.development(${JSON.stringify(pid)})`);
  const box = el('div', { class: 'pad' });
  if (d.error) { box.append(el('div', { class: 'empty' }, d.error)); return box; }
  const act = (name, extra) => { const r = pyJSON(`SESSION.club_act(${JSON.stringify(name)}, pid=${JSON.stringify(pid)}${extra ? ', ' + extra : ''})`); if (!r.ok) notify(r); reload(); };
  box.append(el('div', { class: 'tiles', style: 'grid-template-columns:repeat(4,1fr);margin-bottom:12px' },
    el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'XP Banked'), el('div', { class: 'word' }, d.bank.toLocaleString()), el('div', { class: 'sub' }, `earning ${d.dev} · ${d.bought} points bought in his career`), el('div', {class:'sub'}, `Practice earned: ${(d.practice_earned || 0).toLocaleString()} XP in his career`)),
    el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Ceiling'), el('div', { class: 'word' }, d.ceiling != null ? d.ceiling : '—'), el('div', { class: 'sub' }, d.ceiling_estimated ? "Your scouts' estimated range" : d.room != null ? `${d.room} above his ${d.ovr}` : 'uncapped')),
    el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Raise the Ceiling'), el('div', { class: 'word', style: 'font-size:18px' }, d.unlock_cost != null ? `${d.unlock_cost.toLocaleString()} XP` : '—'), el('div', { class: 'sub' }, el('button', { class: 'btn' + (d.unlock_ok ? ' go' : ''), disabled: d.unlock_ok ? null : '', style: 'padding:3px 10px;font-size:13px;margin-top:4px', 'data-tip': 'Raises his ceiling one point', onclick: () => act('unlock_ceiling') }, 'Unlock +1'))),
    el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Auto-Spend'), el('div', { class: 'word', style: 'font-size:18px' }, d.auto ? 'On' : 'Off'), el('div', { class: 'sub' }, el('button', { class: 'btn', style: 'padding:3px 10px;font-size:13px;margin-top:4px', 'data-tip': 'The assistants spend his XP weekly', onclick: () => act('auto_xp', `on=${d.auto ? 'False' : 'True'}`) }, d.auto ? 'Turn Off' : 'Turn On'), ' ', el('button', { class: 'btn quiet', style: 'padding:3px 10px;font-size:13px;margin-top:4px', 'data-tip': 'Spend his bank now, once', onclick: () => act('spend_by_read') }, 'Spend by Read')))));
  const t = el('table', { class: 'tbl', style: 'table-layout:fixed;width:100%' });
  const C = 'width:14%;text-align:center';
  t.append(el('tr', {}, el('th', { style: 'text-align:left' }, 'Attribute'), el('th', { class: 'n', style: C, 'data-tip': 'Where he started the season' }, 'Original'), el('th', { class: 'n', style: C, 'data-tip': 'Points bought into this attribute' }, 'Purchased'), el('th', { class: 'n', style: C }, 'Current'), el('th', { class: 'n', style: C, 'data-tip': 'XP for the next point; rises with every point bought and with age' }, 'Next Point'), el('th', { style: 'width:12%' }, '')));
  for (const r of d.rows) t.append(el('tr', { style: r.blocked ? 'opacity:.55' : '' }, el('td', { style: 'text-align:left' }, r.label), el('td', { class: 'n', style: C }, String(r.v - (r.bought || 0))), el('td', { class: 'n', style: C + (r.bought ? ';color:var(--ok)' : ';color:var(--ink-3)') }, String(r.bought || 0)), el('td', { class: 'n', style: C }, el('b', {}, String(r.v))), el('td', { class: 'n', style: C + (r.afford && !r.blocked ? '' : ';color:var(--ink-3)') }, r.cost.toLocaleString()),
    el('td', {}, el('button', { class: 'btn' + (r.afford && !r.blocked ? ' go' : ''), disabled: (r.afford && !r.blocked) ? null : '', style: 'padding:3px 10px;font-size:13px', 'data-tip': r.blocked || (r.afford ? 'Buy one point' : 'Not enough XP'), onclick: () => act('buy_point', `attr=${JSON.stringify(r.key)}`) }, 'Buy +1'))));
  box.append(t);
  return box;
}

// THE YEAR CHOOSER. Every season page carries it: the current year by default, every past season the game kept a
// record of behind it. `load(y)` re-renders the page for that year.
function yearChips(v, load) {
  const row = el('div', { class: 'chips yearchips' });
  const ys = (v.years && v.years.length ? v.years : [v.year]).slice().reverse();
  for (const y of ys) row.append(el('button', { class: 'chip', 'aria-pressed': String(y === v.year), onclick: () => load(y) }, y));
  return row;
}

// One viewport-level tooltip avoids clipping and keeps the note beside the hovered control.
const floatingTip = el('div', { id: 'floating-tooltip', role: 'tooltip' });
document.body.append(floatingTip);
let tipTarget = null;
function placeTip(x, y) {
  if (!tipTarget) return;
  const pad = 8, gap = 14, w = floatingTip.offsetWidth, h = floatingTip.offsetHeight;
  let left = x + gap, top = y + gap;
  if (left + w > window.innerWidth - pad) left = x - w - gap;
  if (top + h > window.innerHeight - pad) top = y - h - gap;
  floatingTip.style.left = `${Math.max(pad, Math.min(left, window.innerWidth - w - pad))}px`;
  floatingTip.style.top = `${Math.max(pad, Math.min(top, window.innerHeight - h - pad))}px`;
}
function showTip(target, x, y) {
  const message = target?.getAttribute('data-tip');
  if (!message) { hideTip(); return; }
  if (tipTarget !== target) hideTip();
  tipTarget = target;
  const ids = new Set((target.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
  ids.add('floating-tooltip');
  target.setAttribute('aria-describedby', [...ids].join(' '));
  // Native dialogs occupy the top layer; their tooltip must live there too.
  const host = target.closest('dialog') || document.body;
  if (floatingTip.parentElement !== host) host.append(floatingTip);
  floatingTip.textContent = message;
  floatingTip.classList.add('visible');
  placeTip(x, y);
}
function hideTip() {
  if (tipTarget) {
    const ids = (tipTarget.getAttribute('aria-describedby') || '').split(/\s+/)
      .filter(id => id && id !== 'floating-tooltip');
    if (ids.length) tipTarget.setAttribute('aria-describedby', ids.join(' '));
    else tipTarget.removeAttribute('aria-describedby');
  }
  tipTarget = null;
  floatingTip.classList.remove('visible');
  if (floatingTip.parentElement !== document.body) document.body.append(floatingTip);
}
document.addEventListener('mouseover', e => {
  const target = e.target?.closest?.('[data-tip]');
  if (target) showTip(target, e.clientX, e.clientY);
  else hideTip();
}, true);
document.addEventListener('mousemove', e => {
  if (tipTarget && !tipTarget.isConnected) hideTip();
  else if (tipTarget) placeTip(e.clientX, e.clientY);
}, true);
document.addEventListener('mouseout', e => {
  if (tipTarget && !tipTarget.contains(e.relatedTarget)) hideTip();
}, true);
document.addEventListener('focusin', e => {
  const target = e.target?.closest?.('[data-tip]');
  if (target) { const r = target.getBoundingClientRect(); showTip(target, r.left + r.width / 2, r.bottom); }
  else hideTip();
}, true);
document.addEventListener('focusout', e => { if (tipTarget && !tipTarget.contains(e.relatedTarget)) hideTip(); }, true);
window.addEventListener('scroll', hideTip, true);
window.addEventListener('resize', hideTip);
window.addEventListener('hashchange', hideTip);
document.addEventListener('close', hideTip, true);
document.addEventListener('keydown', e => { if (e.key === 'Escape') hideTip(); }, true);

// weeks 19 to 22 are the playoff rounds
function weekName(w) { return ({ 19: 'Wild Card', 20: 'Divisional Round', 21: 'Conference Championship', 22: 'Championship Game' })[w] || `Week ${w}`; }

// copy text to the clipboard, with a fallback for browsers that refuse the API
async function copyText(text, btn) {
  try { await navigator.clipboard.writeText(text); }
  catch (e) { const ta = document.createElement('textarea'); ta.value = text; document.body.append(ta); ta.select(); try { document.execCommand('copy'); } catch (e2) {} ta.remove(); }
  if (btn) { const was = btn.textContent; btn.textContent = 'Copied'; setTimeout(() => { btn.textContent = was; }, 1400); }
}

// Each break has its own confirmation; halftime approval cannot unlock overtime.
const halfConfirmed = {};
function openHalftime(g, live, gkey, onClose) {
  const overtime = live.adjustment_period === 'overtime';
  const overlay = el('div', { style: 'position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:900;display:flex;align-items:center;justify-content:center' });
  const box = el('section', { class: 'sheet', style: 'width:min(760px,92vw);max-height:84vh;overflow:auto' });
  const draw = () => {
    box.innerHTML = '';
    const v = pyJSON('SESSION.gameday_view()'); const recs = (v.live && v.live.recs) || [];
    box.append(el('h2', {}, overtime ? 'Overtime Adjustments' : 'Halftime Adjustments', el('small', {}, `${showAbbr(g.away.abbr)} ${live.score.away} · ${showAbbr(g.home.abbr)} ${live.score.home}`)));
    box.append(el('div', { class: 'pad', style: 'color:var(--ink-2)' }, recs.length ? (overtime ? "The assistants' read of regulation. Choose any changes before the overtime kickoff; your existing plan carries forward unless you adjust it." : "The assistants' read of the half. Choose any changes before the second-half kickoff.") : `The assistants have nothing to change at the break. Your plan carries into ${overtime ? 'overtime' : 'the second half'} as it stands.`));
    for (const r of recs) box.append(el('div', { style: 'display:flex;gap:12px;align-items:flex-start;padding:10px 16px;border-top:1px solid var(--rule)' },
      el('span', { class: 'tag ' + (r.side === 'offence' ? 'q' : 'out'), style: 'margin-top:3px' }, r.side === 'offence' ? 'OFFENSE' : 'DEFENSE'),
      el('div', { style: 'flex:1' }, el('div', { style: 'font-weight:700' }, r.text), el('div', { class: 'count' }, r.why)),
      el('button', { class: 'btn' + (r.taken ? ' go' : ''), style: 'width:auto;padding:4px 12px', onclick: async () => { pyJSON(`SESSION.half_take(${r.i}, ${r.taken ? 'False' : 'True'})`); draw(); await saveLiveJournalNotified(); } }, r.taken ? 'Taken' : 'Take')));
    box.append(el('div', { class: 'foot' }, el('button', { class: 'btn go', onclick: () => { halfConfirmed[gkey] = true; overlay.remove(); onClose(); } }, 'Confirm'), el('button', { class: 'btn quiet', onclick: () => { overlay.remove(); onClose(); } }, 'Close')));
  };
  draw(); overlay.append(box); document.body.append(overlay);
}

// Team reports share the same font, restrained surface, and viewed-team palette.
function reportBoard(team, title, metrics = []) {
  const board = el('section', { class: 'sheet c12 report-board', style: `--report-team:${teamTheme(team).base};--report-accent:${teamTheme(team).accent}` });
  board.append(el('header', { class: 'report-hero' }, el('div', {}, el('small', {}, team.name), el('h1', {}, title)),
    el('div', { class: 'report-metrics' }, ...metrics.map(([value,label]) => el('div', {}, el('b', {}, value), el('span', {}, label))))));
  return board;
}

// the roster's development at a glance
function renderProgression(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.className = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Team'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'club'));
  secondRow(clubNav(v.rail.club.abbr, true, null), '#club/progression');
  const reload = () => renderProgression(pyJSON('SESSION.progression()'));
  const s = reportBoard(v.rail.club, 'PROGRESSION', [[v.bank_total.toLocaleString(), 'XP BANKED'], [v.idle, 'READY TO SPEND']]);
  s.append(el('div', { class: 'tools report-controls' }, el('button', { class: 'btn' + (v.auto_all ? ' go' : ''), 'data-tip': 'Every player, spent weekly by the assistants', onclick: () => { notify(pyJSON(`SESSION.club_act('auto_xp', on=${v.auto_all ? 'False' : 'True'})`)); reload(); } }, v.auto_all ? 'Auto-Spend: On for All' : 'Turn Auto-Spend On for All'),
    el('button', { class: 'btn', 'data-tip': 'Spend every bank now, once', onclick: () => { const r = pyJSON(`SESSION.club_act('spend_by_read')`); if (!r.ok) notify(r); reload(); } }, 'Spend All by Read'),
    el('span', { class: 'count', style: 'margin-left:auto' }, 'Open a player for his Development tab')));
  const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', { class: 'n' }, 'Ceiling'), el('th', { class: 'n', 'data-tip': 'Remaining overall growth; shown as a range when the ceiling is uncertain' }, 'Room'), el('th', { class: 'n' }, 'XP Banked'), el('th', { class: 'n', 'data-tip': 'The cheapest next point' }, 'Next Point'), el('th', { class: 'n' }, 'Bought This Year'), el('th', {}, 'Auto'), el('th', {}, '')));
  for (const r of v.rows) t.append(el('tr', { class: r.can_buy && !r.auto ? 'report-ready' : '' }, el('td', {}, el('button', { class: 'who', onclick: () => { openPlayer(r.pid, 'Development'); } }, el('div', { class: 'no' }, r.no ?? r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `earning ${r.dev} · ${r.career} bought in his career`)))), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, r.ceiling ?? '—'), el('td', { class: 'n' }, r.room != null ? r.room : '—'), el('td', { class: 'n' }, r.bank.toLocaleString()), el('td', { class: 'n' }, r.cheapest ? r.cheapest.toLocaleString() : '—'), el('td', { class: 'n' }, r.bought),
    el('td', {}, el('button', { class: 'btn' + (r.auto ? ' go' : ' quiet'), style: 'padding:3px 8px;font-size:13px', onclick: () => { pyJSON(`SESSION.club_act('auto_xp', pid=${JSON.stringify(r.pid)}, on=${r.auto ? 'False' : 'True'})`); reload(); } }, r.auto ? 'On' : 'Off')),
    el('td', {}, el('button', { class: 'btn', style: 'padding:3px 8px;font-size:13px', disabled: r.can_buy ? null : '', 'data-tip': 'Spend his bank now by the read', onclick: () => { const result = pyJSON(`SESSION.club_act('spend_by_read', pid=${JSON.stringify(r.pid)})`); if (!result.ok) notify(result); reload(); } }, 'Spend'))));
  s.append(el('div', { class: 'report-table-scroll' }, t)); page.append(s);
}

function renderProspectCard(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.className = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Draft'; drSecond('board');
  if (v.error) { page.append(el('section', { class: 'sheet c12' }, el('div', { class: 'empty' }, v.error))); return; }
  const reload = () => renderProspectCard(pyJSON(`SESSION.club_card(${JSON.stringify(v.pid)})`));
  const s = el('section', { class: 'sheet c12' });
  s.append(el('div', { class: 'head' },
    el('div', { class: 'jersey', style: 'background:var(--sheet-3);color:var(--ink)' }, v.pos),
    el('div', {}, el('div', { class: 'hname' }, v.name.toUpperCase()),
      el('div', { class: 'hline' }, el('b', {}, v.pos), ` · ${v.cls_year} · ${v.age}${v.size ? ' · ' + v.size : ''} · Home State: ${v.home_state}${v.small ? ' · Small School' : ''}${v.taken ? ' · Drafted' : ''}`),
      el('div', { class: 'hfacts' }, el('div', { 'data-tip': "The league's grade, same scale as yours" }, el('span', {}, 'Consensus'), el('b', {}, v.cons != null ? `${v.cons}${v.cons_rank ? ' · #' + v.cons_rank : ''}` : '—')), el('div', { 'data-tip': "Yours minus the league's. Positive means the league undervalues him" }, el('span', {}, 'Gap'), el('b', { style: v.gap > 0 ? 'color:var(--ok)' : v.gap < 0 ? 'color:var(--danger)' : '' }, v.gap != null ? (v.gap > 0 ? '+' : '') + v.gap : '—')), el('div', { 'data-tip': 'Where the league expects him to go' }, el('span', {}, 'Projected'), el('b', {}, v.proj_range)), el('div', {}, el('span', {}, 'Your Board'), el('b', {}, v.dnd ? 'Do Not Draft' : v.on_board ? `#${v.on_board}` : 'Not placed')), el('div', {}, el('span', {}, 'Read'), el('b', { style: 'color:var(--ink-2)' }, v.confidence)))),
    el('div', { class: 'ovrbig' }, el('b', { 'data-tip': "Your scouts' read. Carries error; a visit tightens it" }, v.mine), el('span', {}, 'Estimated Overall · your scouts'), (v.fit || 0) !== 0 ? el('div', { class: 'pot', 'data-tip': "How he grades in your scheme, on your scouts' read" }, `In your scheme ${v.scheme_ovr} · `, el('span', { class: 'fit ' + (v.fit > 0 ? 'p' : 'm') }, (v.fit > 0 ? '+' : '') + v.fit.toFixed(1))) : '', el('div', { class: 'pot', 'data-tip': 'Where he can grow to. Wide means your scouts are unsure' }, `Ceiling ${v.ceiling}${v.my_round ? ' · Your Grade ' + v.my_round : ''}`))));
  const acts = el('div', { class: 'ctabs' }, el('span', { style: 'font-family:var(--display);font-weight:700;color:var(--ink-3);padding:8px 0' }, 'Prospect Card'));
  const a = el('div', { class: 'acts' });
  if (!v.taken) {
    if (v.on_clock) a.append(el('button', { class: 'btn go', onclick: () => { const r = pyJSON(`SESSION.draft_act('pick', pid=${JSON.stringify(v.pid)})`); notify(r); if (r.ok) location.hash = '#draft/day'; } }, 'Draft Player'));
    a.append(v.on_board ? el('button', { class: 'btn quiet', onclick: () => { pyJSON(`SESSION.draft_act('board', remove=${JSON.stringify(v.pid)})`); reload(); } }, 'Take Off Your Board') : el('button', { class: 'btn' + (v.on_clock ? '' : ' go'), onclick: () => { pyJSON(`SESSION.draft_act('board', add=${JSON.stringify(v.pid)})`); reload(); } }, 'Add to Your Board'));
    if (!v.spring_done) a.append(el('button', { class: 'btn' + (v.visited ? ' go' : ''), 'data-tip': v.visited ? 'Cancel the visit' : 'Scout this player further', onclick: () => { const r = pyJSON(`SESSION.draft_act('visit', pid=${JSON.stringify(v.pid)})`); if (!r.ok) notify(r); reload(); } }, v.visited ? 'Visiting' : 'Visit'));
    a.append(el('button', { class: 'btn quiet', 'data-tip': 'Keep him off your board on draft day', onclick: () => { pyJSON(`SESSION.draft_act('board', remove=${JSON.stringify(v.pid)})`); const cur = pyJSON(`SESSION.draft_view('board')`).user_board.dnd.map(x => x.pid); pyJSON(`SESSION.draft_act('board', dnd=${JSON.stringify(cur.concat([v.pid]))})`); reload(); } }, 'Do Not Draft'));
  }
  a.append(el('button', { class: 'btn quiet', onclick: () => history.back() }, 'Back'));
  acts.append(a); s.append(acts);
  const h5 = (t, sub) => el('div', { class: 'h5' }, t, sub ? el('span', {}, sub) : '');
  const left = el('div', {});
  left.append(h5('Combine', v.combine.every(c => c.v === '—') ? 'comes in the Spring' : ''));
  left.append(el('div', { class: 'kv' }, ...v.combine.flatMap(c => [el('span', {}, c.label), el('span', {}, c.v)])));
  left.append(h5('Flags'), el('div', { style: 'padding:4px 0 8px' }, ...(v.words.length ? v.words.map(wordTag) : [el('span', { class: 'muted', style: 'font-size:14.5px' }, 'None')])));
  left.append(h5('Medical'), el('div', { style: 'font-size:15px;color:var(--ink-2);padding-bottom:8px' }, v.medical));
  if (v.personality) left.append(h5('Character', 'from your visit'), el('div', { style: 'font-size:15px;color:var(--ink-2)' }, v.personality));
  const mid = el('div', {});
  mid.append(h5('Attributes', "your scouts' read"));
  const attrs = el('div', { class: 'attrs' });
  for (const c of v.cols) {
    const box = el('div', {}, el('div', { class: 'h5', style: 'margin-bottom:4px' }, c.title));
    const rowsOf = rows => { for (const r of rows) box.append(el('div', { class: 'arow ' + r.tier }, el('span', {}, r.label), el('em', {}), el('b', {}, r.v))); };
    rowsOf(c.rows); if (c.extra && c.extra.rows && c.extra.rows.length) { box.append(el('div', { class: 'h5', style: 'margin:12px 0 4px' }, c.extra.title)); rowsOf(c.extra.rows); }
    if (c.title === 'Mental' && v.schemes) box.append(schemeBlock(v.schemes));
    attrs.append(box);
  }
  mid.append(attrs);
  const right = el('div', {});
  right.append(h5('The Scouts', "the room's read"), el('div', { class: 'read' }, el('b', {}, 'Assistants: '), v.read));
  right.append(h5('Where He Goes', 'consensus against your board'), el('div', { class: 'kv' }, el('span', {}, 'Consensus'), el('span', {}, v.cons_rank ? `#${v.cons_rank} · picks ${v.proj_range}` : '—'), el('span', {}, 'Your Read'), el('span', {}, v.my_rank ? `#${v.my_rank}${v.my_round ? ' · ' + v.my_round + ' grade' : ''}` : '—'), el('span', {}, 'Ceiling'), el('span', {}, v.ceiling)));
  s.append(el('div', { class: 'body' }, left, mid, right));
  page.append(s);
}

let depthPkg = 'Base', depthSide = 'offense', depthFront = null, depthClub = null, depthOffense = null;
function renderDepth(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.className = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Team'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'club'));
  const mine = v.mine !== false; const abbr = v.club_abbr || v.rail.club.abbr;
  if (depthClub !== abbr) { depthClub = abbr; depthFront = null; depthOffense = null; }
  $('#crumb').textContent = 'Team'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'club'));
  secondRow(clubNav(abbr, mine, null), mine ? '#club/depth' : `#club/team/${abbr}/depth`);
  const loadDepth = p => pyJSON(`SESSION.club_depth(${JSON.stringify(p)}${mine ? '' : ', ' + JSON.stringify(abbr)}${depthFront ? `, front=${JSON.stringify(depthFront)}` : ''}${depthOffense ? `, offense=${JSON.stringify(depthOffense)}` : ''})`);
  const reload = () => renderDepth(loadDepth(v.package));
  const s = el('section', { class: 'sheet c12 depth-board' });
  const team = v.rail.club;
  const depthTheme = teamTheme(team);
  s.style.setProperty('--depth-team', depthTheme.base);
  s.style.setProperty('--depth-accent', depthTheme.accent);
  s.append(el('header', {class:'depth-hero'}, el('div', {class:'depth-team-name'}, team.name || abbr), el('h1', {}, 'DEPTH CHART'), el('span', {}, 'Personnel · ' + abbr)));

  // the side tabs, then the package
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' });
  for (const [k, l] of [['offense', 'Offense'], ['defense', 'Defense'], ['specialists', 'Special Teams']]) tabs.append(el('button', { 'aria-pressed': String(depthSide === k), onclick: () => { depthSide = k; renderDepth(v); } }, l));
  tabs.append(el('span', { style: 'margin-left:auto' }), clubSelect(abbr, a => { const m = pyJSON('SESSION.club_list()').find(c => c.abbr === a); location.hash = m && m.mine ? '#club/depth' : `#club/team/${a}/depth`; }));
  s.append(tabs);
  if (depthSide === 'offense') {
    const labels = {'11':'Three WR','12':'Two TE','13':'Three TE','21':'Two backs','22':'Two backs / Two TE','10':'Four WR','00':'Empty'};
    const pk = el('div', {class:'pkg'}, el('span', {}, 'Personnel'));
    for (const p of v.offense_packages || []) pk.append(el('button', {'aria-pressed':String(p === v.offense_package), onclick:()=>{depthOffense=p; reload();}}, `${p} · ${labels[p]}${p === v.offense_base ? ' · Base' : ''}`));
    s.append(pk);
  }
  if (depthSide === 'defense') {
    const pk = el('div', { class: 'pkg' }, el('span', {}, `${v.coach_front === 'multiple' ? 'Multiple · ' : ''}${v.defense_shape} · Package`));
    for (const p of v.packages) pk.append(el('button', { 'aria-pressed': String(p === v.package), onclick: () => { depthPkg = p; renderDepth(loadDepth(p)); } }, p));
    pk.append(el('span', { class: 'snaps' }, 'Drag within a column · double-click opens the player'));
    s.append(pk);
    if (v.available_fronts && v.available_fronts.length) {
      const fronts = el('div', { class: 'pkg depth-fronts' }, el('span', {}, 'View front'));
      for (const f of v.available_fronts) fronts.append(el('button', { 'aria-pressed': String(f === v.front), onclick: () => { depthFront = f; renderDepth(loadDepth(v.package)); } }, f));
      s.append(fronts);
    }
  }
  // Each unit follows the team's front and the selected package.
  const cols = [...v.sides[depthSide]];
  if (depthSide === 'offense') cols.sort((a,b)=>['QB','HB','FB','TE','WR','LT','LG','C','RG','RT'].indexOf(a.pos)-['QB','HB','FB','TE','WR','LT','LG','C','RG','RT'].indexOf(b.pos));
  const chart = el('div', { class: 'depth-groups' });
  const groups = new Map();
  for (const c of cols) {
    const groupName = depthSide === 'offense' ? (c.group === 'Line' ? 'Offensive Front' : 'Backfield & Targets') : depthSide === 'defense' ? (c.group === 'Secondary' ? 'Defensive Secondary' : 'Defensive Front & Linebackers') : c.group;
    if (!groups.has(groupName)) {
      const grid = el('div', { class: 'depth-unit-grid' });
      chart.append(el('section', { class: 'depth-unit' }, el('div', { class: 'depth-unit-head' }, groupName), grid));
      groups.set(groupName, grid);
    }
    const men = c.slots; const pinned = v.pins[c.pos] && v.pins[c.pos].length;
    const col = el('div', { class: 'dcol' + (pinned ? ' yours' : '') }, el('div', { class: 'pos' }, c.title, el('small', {}, `${men.filter(x=>x.start).length} starter${men.filter(x=>x.start).length===1?'':'s'}`)));
    const move = (i, dir) => { const order = men.map(m => m.pid); [order[i + dir], order[i]] = [order[i], order[i + dir]]; pyJSON(`SESSION.club_act('set_depth', pos=${JSON.stringify(c.pos)}, pids=${JSON.stringify(order)})`); reload(); };
    men.forEach((x, i) => {
      const fit = x.fit || 0;
      const decide = x.pending && mine ? el('span', { style: 'display:inline-flex;gap:3px;margin-top:4px' }, el('button', { class: 'btn go', style: 'padding:1px 8px;font-size:11px', onclick: e => { e.stopPropagation(); notify(pyJSON(`SESSION.club_act('hurt_decision', pid=${JSON.stringify(x.pid)}, play=True)`)); reload(); } }, 'Play'), el('button', { class: 'btn', style: 'padding:1px 8px;font-size:11px', onclick: e => { e.stopPropagation(); notify(pyJSON(`SESSION.club_act('hurt_decision', pid=${JSON.stringify(x.pid)}, play=False)`)); reload(); } }, 'Sit')) : null;
      const fitEl = x.flag_word ? el('span', { style: 'display:inline-flex;flex-direction:column;align-items:flex-start;gap:0' }, el('span', { class: 'tag ' + (x.flag === 'out' ? 'out' : 'q') }, x.flag_word), decide || '') : x.elevated ? el('span', { class: 'tag q', 'data-tip': 'Elevated from the practice squad for this game' }, 'Elevated') : x.playing_hurt ? el('span', { class: 'tag q' }, `Playing · ${x.playing_hurt}`) : el('span', { class: 'fit' }, 'Fit ', el('b', { class: fit > 0.05 ? 'up' : fit < -0.05 ? 'dn' : '' }, (fit > 0.05 ? '+' : fit < -0.05 ? '−' : '\u00a0') + Math.abs(fit).toFixed(1)));
      const plate = el('div', { class: 'plate3' + (x.start ? ' start' : '') + (x.flag === 'out' ? ' out' : ''), draggable: mine ? 'true' : 'false', 'data-tip': x.name },
        el('div', { class: 'row1' }, el('span', { class: 'no' }, String(i+1).padStart(2, '0')), el('span', { class: 'nm' }, surname(x.name) || x.name)),
        el('div', { class: 'row2' }, x.sub ? el('span', { class: 'fit' }, x.sub) : fitEl, el('span', { class: 'ov' }, x.ovr)));
      plate.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', JSON.stringify({ pid: x.pid, pos: c.pos })); plate.classList.add('dragging'); });
      plate.addEventListener('dragend', () => plate.classList.remove('dragging'));
      plate.addEventListener('dragover', e => { e.preventDefault(); plate.classList.add('over'); });
      plate.addEventListener('dragleave', () => plate.classList.remove('over'));
      plate.addEventListener('drop', e => { if (!mine) return; e.preventDefault(); plate.classList.remove('over'); let d; try { d = JSON.parse(e.dataTransfer.getData('text/plain')); } catch (_) { return; } if (!d || d.pos !== c.pos || d.pid === x.pid) return; const order = men.map(m => m.pid).filter(p => p !== d.pid); order.splice(order.indexOf(x.pid), 0, d.pid); pyJSON(`SESSION.club_act('set_depth', pos=${JSON.stringify(c.pos)}, pids=${JSON.stringify(order)})`); reload(); });
      plate.addEventListener('dblclick', () => { location.hash = '#club/player/' + x.pid; });
      col.append(plate);
    });
    if (!men.length) col.append(el('div', { class: 'plate3 none' }, 'Nobody'));
    groups.get(groupName).append(col);
  }
  for (const grid of groups.values()) grid.style.gridTemplateColumns = `repeat(${grid.children.length},minmax(0,1fr))`;
  s.append(chart);
  if (mine) s.append(el('div', { class: 'foot' }, el('button', { class: 'btn', 'data-tip': 'Best overall first at every spot', onclick: () => { pyJSON(`SESSION.club_act('reset_depth')`); reload(); } }, 'Auto-Fill by Rating'), el('button', { class: 'btn', 'data-tip': "Best at the spot in your scheme first, the way the coordinators would set it", onclick: () => { notify(pyJSON(`SESSION.club_act('fill_by_fit')`)); reload(); } }, 'Auto-Fill by Fit'),
    v.assistant && depthSide === 'defense' ? el('span', { class: 'read', style: 'margin:0 0 0 10px;padding:6px 10px;flex:1' }, el('b', {}, 'Assistants: '), v.assistant) : el('span', { class: 'count', style: 'margin-left:auto' }, 'Highlighted rows = selected starters')));
  else s.append(el('div', { class: 'foot' }, el('span', { class: 'count' }, 'Highlighted rows = selected starters')));
  page.append(s);
}

// ---------------------------------------------------------------- Personnel
const PERS = { trades: 'Trades', fa: 'Free Agency', wire: 'Waivers', retain: 'Retain Players', extensions: 'Extensions' };
let tradeState = { other: null, a: [], b: [] };
function persSecond(cur) { secondRow(Object.entries(PERS).map(([k, l]) => [l, '#personnel/' + k]), '#personnel/' + cur); $('#crumb').textContent = 'Personnel'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'personnel')); }
function persPage() { const page = $('#page'); page.innerHTML = ''; page.className = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)'; return page; }
function crest(c, size) { return el('div', { class: 'cr', style: `background:${c.color}${size ? `;height:${size}px;font-size:${Math.max(10, Math.round(size * 0.4))}px` : ''}` }, showAbbr(c.abbr)); }
// Successful actions are reflected by their page. Only failures need feedback,
// outside #page so an immediate re-render cannot erase the explanation.
function notify(r) {
  const feedback = $('#action-feedback');
  const failed = r?.ok === false || !!r?.error || (r?.ok !== true && !!r?.why);
  feedback.hidden = !failed;
  $('#action-feedback-text').textContent = failed ? (r.why || r.error || r.line || 'That did not work.') : '';
  $('#dismiss-feedback').onclick = () => { feedback.hidden = true; };
}

// Each team owns its panel palette; shared by trades, cards and negotiations.
let personnelRailTeam = null;
function teamTheme(team = {}) {
  const abbr = team.abbr;
  const base = ({DEN:'#002244', CIN:'#101820', PIT:'#101820', NO:'#101820'})[abbr] || team.color || COLOR[abbr] || '#303842';
  const accent = BOOT_TEAM[abbr]?.[1] || team.accent || '#c8d2dc';
  const n = parseInt(accent.replace('#', ''), 16);
  const bright = (((n >> 16) & 255) * 299 + ((n >> 8) & 255) * 587 + (n & 255) * 114) / 1000;
  return {base, accent, ink: bright > 145 ? '#111820' : '#fff', readable: bright > 145 ? accent : `color-mix(in srgb, ${accent} 65%, white)`};
}
function applyTeamTheme(node, team) {
  const t = teamTheme(team);
  for (const [k, value] of Object.entries(t)) node.style.setProperty('--team-' + k, value);
  return t;
}
function tradeSelection(items, own) {
  // Old draft/roster/counter links may still pass IDs. Resolve membership, not punctuation.
  const result = [];
  for (const item of items || []) {
    const id = typeof item === 'object' ? item.id : item;
    const kind = typeof item === 'object' ? item.kind : own.roster.some(p => String(p.pid) === String(id)) ? 'player' : 'pick';
    const found = kind === 'player' ? own.roster.some(p => String(p.pid) === String(id)) : kind === 'pick' && own.picks.some(p => String(p.id) === String(id));
    if (found && !result.some(x => x.kind === kind && String(x.id) === String(id))) result.push({kind, id});
  }
  return result;
}
function tradePickerState(key) {
  tradeState.pickers ||= {};
  return tradeState.pickers[key] ||= {mode:'players', query:'', scroll:0};
}
function tradeAssetRow(own, asset, remove, onChange, side) {
  const p = asset.kind === 'player' ? own.roster.find(p => String(p.pid) === String(asset.id)) : own.picks.find(p => String(p.id) === String(asset.id));
  if (!p) return '';
  const name = asset.kind === 'player' ? p.short : p.words;
  const row = el('div', {class:'trade-asset' + (remove ? ' selected' : ''), draggable: remove ? null : 'true'},
    el('span', {class:'trade-number'}, asset.kind === 'player' ? (jerseyNo(p.no) ?? p.pos) : `R${p.round}`),
    el('div', {class:'trade-name'}, name, el('small', {}, asset.kind === 'player' ? `${p.pos} · ${p.yrs} yrs · $${p.hit}m hit${remove ? ` · $${p.penalty}m penalty` : ''}` : `${p.own_words}${p.proj ? ' · ' + p.proj : ''}`)),
    el('b', {class:'trade-rating'}, asset.kind === 'player' ? p.ovr : ''),
    el('button', {class:'btn trade-add', 'aria-label':`${remove ? 'Remove' : 'Add'} ${name}`, onclick:() => onChange(asset, remove)}, remove ? '×' : '+'));
  if (!remove) row.addEventListener('dragstart', e => e.dataTransfer.setData('text/plain', JSON.stringify({side, asset})));
  return row;
}
function renderTradePackage(own, selected, onChange, side) {
  const box = el('div', {class:'trade-package', 'aria-label':'Selected trade assets'});
  if (!selected.length) box.append(el('div', {class:'empty'}, '+ Add players or picks below'));
  for (const asset of selected) box.append(tradeAssetRow(own, asset, true, onChange, side));
  box.addEventListener('dragover', e => {e.preventDefault(); box.classList.add('over');});
  box.addEventListener('dragleave', () => box.classList.remove('over'));
  box.addEventListener('drop', e => {
    e.preventDefault(); box.classList.remove('over');
    let data; try {data = JSON.parse(e.dataTransfer.getData('text/plain'));} catch (_) {return;}
    if (data.side === side && tradeSelection([data.asset], own).length) onChange(data.asset, false);
  });
  return box;
}
function renderTradePicker(own, selected, ui, onChange, side) {
  const wrap = el('div', {class:'trade-picker'}), tabs = el('div', {class:'trade-picker-tools'}), rows = el('div', {class:'trade-rows'});
  const draw = () => {
    rows.replaceChildren();
    const pool = ui.mode === 'players' ? own.roster.map(p => ({kind:'player', id:p.pid, text:`${p.short} ${p.name || ''} ${p.pos}`})) : own.picks.map(p => ({kind:'pick',id:p.id,text:`${p.words} ${p.own_words} ${p.proj || ''}`}));
    for (const a of pool) if (!selected.some(x => x.kind === a.kind && String(x.id) === String(a.id)) && a.text.toLowerCase().includes(ui.query.toLowerCase())) rows.append(tradeAssetRow(own, {kind:a.kind,id:a.id}, false, onChange, side));
    if (!rows.children.length) rows.append(el('div', {class:'empty'}, 'No matching assets.'));
    rows.scrollTop = ui.scroll;
  };
  for (const [key,label] of [['players','Players'],['picks',side === 'a' ? 'Your Picks' : 'Their Picks']]) tabs.append(el('button',{class:'btn','aria-pressed':String(ui.mode === key),onclick:e => {ui.mode=key;ui.scroll=0;tabs.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===e.currentTarget)));draw();}},label));
  tabs.append(el('input',{type:'search',placeholder:'Find a player or pick…',value:ui.query,'aria-label':`Search ${own.club.name} assets`,oninput:e=>{ui.query=e.target.value;ui.scroll=0;draw();}}));
  rows.addEventListener('scroll',()=>{ui.scroll=rows.scrollTop;});
  wrap.append(tabs, rows); draw();
  requestAnimationFrame(()=>{if(rows.isConnected) rows.scrollTop=ui.scroll;});
  return wrap;
}
function renderTradeSide(v, key, reload) {
  const own = key === 'a' ? v.me : v.them, selected = tradeState[key];
  const box = el('section',{class:'trade-side','data-team':own.club.abbr}); applyTeamTheme(box,own.club);
  const head = el('div',{class:'trade-side-head'},el('h2',{},own.club.name));
  head.append(el('div',{class:'trade-cap'},el('b',{},`$${own.cap.toFixed(1)}m`),el('small',{},'Cap space')));
  const onChange=(asset,remove)=>{
    const i=selected.findIndex(x=>x.kind===asset.kind && String(x.id)===String(asset.id));
    if(remove && i>=0) selected.splice(i,1); else if(!remove && i<0) selected.push(asset);
    tradeState.offers=null; reload(true);
  };
  box.append(head,el('div',{class:'trade-label'},key==='a'?'YOU SEND':'YOU RECEIVE'),renderTradePackage(own,selected,onChange,key),renderTradePicker(own,selected,tradePickerState(own.club.abbr),onChange,key));
  const notes=el('div',{class:'trade-notes'},el('div',{},el('h3',{},'Team needs'),el('span',{},own.needs.length?own.needs.join(' · '):'None pressing')));
  const surplus=el('div',{},el('h3',{},'Surplus players'));
  for(const x of own.surplus.slice(0,4)) {
    const p=own.roster.find(p=>p.pid===x.pid); if(!p) continue;
    surplus.append(el('button',{class:'trade-surplus',disabled:selected.some(a=>a.kind==='player'&&a.id===p.pid)?'':null,'data-tip':x.why,onclick:()=>onChange({kind:'player',id:p.pid},false)},p.short));
  }
  if(!own.surplus.length) surplus.append(el('span',{},'Nothing spare.'));
  notes.append(surplus); box.append(notes); return box;
}
function renderTradeSummary(v,reload) {
  const summary=el('div',{class:'trade-summary'});
  if(v.package) summary.append(el('div',{class:'trade-verdict '+v.package.verdict},el('b',{},`${showAbbr(v.them.club.abbr)}: ${v.package.verdict.toUpperCase()}. `),v.package.read,el('small',{},`${v.package.my_read} Your roster after: ${v.package.roster_after.me} · Your cap after: $${v.package.cap_after.me}m`)));
  const args=()=>`other=${JSON.stringify(tradeState.other)}, a_sends=${JSON.stringify(tradeState.a)}, b_sends=${JSON.stringify(tradeState.b)}`;
  const can=v.can_trade&&(tradeState.a.length||tradeState.b.length);
  const actions=el('div',{class:'trade-actions'},el('span',{},`${tradeState.a.length} assets sent · ${tradeState.b.length} received`),
    el('button',{class:'btn go',disabled:can?null:'',onclick:()=>{const r=pyJSON(`SESSION.personnel_act('propose', ${args()}${tradeState.counter_id != null ? ', counter_id='+Number(tradeState.counter_id) : ''})`);notify(r);if(r.done){tradeState.a=[];tradeState.b=[];tradeState.counter_id=null;}tradeState.offers=null;reload();}},'Propose'),
    el('button',{class:'btn',disabled:v.can_trade&&tradeState.b.length?null:'',onclick:()=>{const r=pyJSON(`SESSION.personnel_act('ask', ${args()})`);notify(r);if(!r.ok)return;tradeState.a=tradeSelection([...tradeState.a,...(r.adds||[]).map(id=>({kind:'pick',id}))],v.me);tradeState.offers=null;reload(true);}},'Ask What They Want'),
    el('button',{class:'btn',disabled:v.can_trade&&tradeState.a.length===1&&tradeState.a[0].kind==='player'?null:'',onclick:()=>{const pid=tradeState.a[0].id;const r=pyJSON(`SESSION.personnel_act('gather', pid=${JSON.stringify(pid)})`);notify(r);tradeState.offers={...r,pid};reload();}},'Gather Offers'),
    el('button',{class:'btn quiet',onclick:()=>{tradeState.a=[];tradeState.b=[];tradeState.offers=null;reload(true);}},'Clear'));
  summary.append(actions);return summary;
}
function renderTrades(v) {
  renderRail(v.rail); const page=persPage();persSecond('trades');
  tradeState.other=v.other.abbr;
  tradeState.a=tradeSelection(tradeState.a,v.me);tradeState.b=tradeSelection(tradeState.b,v.them);
  const reload=(persist=false)=>{if(persist && tradeState.counter_id != null){const r=pyJSON(`SESSION.personnel_act('save_trade_counter', msg_id=${Number(tradeState.counter_id)}, other=${JSON.stringify(tradeState.other)}, a_sends=${JSON.stringify(tradeState.a)}, b_sends=${JSON.stringify(tradeState.b)})`);if(!r.ok)notify(r);}const y=window.scrollY;renderTrades(pyJSON(`SESSION.personnel('trades', other=${JSON.stringify(tradeState.other)}, a_sends=${JSON.stringify(tradeState.a)}, b_sends=${JSON.stringify(tradeState.b)})`));window.scrollTo(0,y);};
  const s=el('section',{class:'sheet c12 trade-board'});applyTeamTheme(s,v.me.club);
  const partners=el('div',{class:'trade-team-emblems',role:'group','aria-label':'Choose trade partner'});
  for(const c of v.clubs) partners.append(el('button',{class:'trade-team-emblem',style:`--team-color:${teamTheme(c).base}`,'aria-label':c.name,'aria-pressed':String(c.abbr===v.other.abbr),'data-tip':c.name,onclick:()=>{if(c.abbr===tradeState.other)return;tradeState.counter_id=null;tradeState.other=c.abbr;tradeState.a=[];tradeState.b=[];tradeState.offers=null;reload();}},showAbbr(c.abbr)));
  s.append(el('div',{class:'trade-hero trade-partners'},partners));
  if(!v.can_trade)s.append(el('div',{class:'banner'},'The trade deadline has passed. Trades reopen after the season.'));
  if(v.draft_live)s.append(el('div',{class:'banner'},`Draft day · pick ${v.draft_live.slot} · ${showAbbr(v.draft_live.team)} on the clock. `,el('a',{class:'btn',href:'#draft/day'},'Back to the Draft')));
  s.append(el('div',{class:'trade-columns'},renderTradeSide(v,'a',reload),renderTradeSide(v,'b',reload)));
  if(tradeState.offers){
    const r=tradeState.offers, list=el('div',{class:'trade-offers'},el('h3',{},r.line||r.why||'Offers'));
    for(const o of r.offers||[])list.append(el('div',{class:'trade-offer'},crest(o.club,26),el('span',{},`${o.club.name}: ${o.words.join(' and ')}`),el('button',{class:'btn',onclick:()=>{tradeState.counter_id=null;tradeState.other=o.club.abbr;tradeState.a=[{kind:'player',id:r.pid}];tradeState.b=o.assets||o.ids;tradeState.offers=null;reload();}},'Open')));
    s.append(list);
  }
  s.append(renderTradeSummary(v,reload));page.append(s);
}

function offerForm(t, kind, onDone, preset) {
  const f = el('div', { class: 'msg you offer-panel' },
    el('div', { class: 'offer-panel-head' },
      el('div', { class: 'from' }, preset ? 'COUNTER PROPOSAL' : 'YOUR OFFER'),
      el('div', { class: 'offer-live' }, 'LIVE CONTRACT PREVIEW')
    )
  );
  const start = preset || {};
  const startYears = Math.max(1, +(start.years || t.years || 3)); const startBonus = start.bonus != null ? +start.bonus : Math.round((t.ask || 1) * (t.years || 3) * 0.3 * 2) / 2;
  const startApy = start.apy != null ? +start.apy : (t.ask ? t.ask * 0.97 : 1.0);
  const salary = el('input', { type: 'number', step: '0.1', min: '0.5', value: Math.max(0.5, startApy - startBonus / startYears).toFixed(1) });
  const apyOf = () => { const n = Math.max(1, +yrs.value || 1); return Math.round(((+salary.value || 0) + (+bonus.value || 0) / n) * 100) / 100; };
  const apy = { get value() { return String(apyOf()); } };
  const yrs = el('input', { type: 'number', min: '1', max: '7', value: String(start.years || t.years || 3) });
  const bonus = el('input', { type: 'number', step: '0.5', min: '0', value: start.bonus != null ? String(start.bonus) : String(Math.round((t.ask || 1) * (t.years || 3) * 0.3 * 2) / 2) });
  const shapeChips = el('div', { class: 'chips' }); let shape = 0.5;
  for (const [val, label] of [[0.85, 'Pay It Now'], [0.5, 'League Shape'], [0.15, 'Back-Load']]) shapeChips.append(el('button', { class: 'chip', 'aria-pressed': String(val === shape), onclick: e => { shape = val; shapeChips.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); preview(); } }, label));
  const y1 = el('b', {}, '—'), total = el('b', {}, '—'); const hitsRow = el('div', { class: 'hits' }); const yearHits = el('div', { class: 'offer year-hits' });
  const capImpact = el('div', { class: 'extension-impact-slot', 'aria-live': 'polite', hidden: true });
  const preview = () => {
    const r = pyJSON(`SESSION.personnel_act('offer_preview', pid=${JSON.stringify(t.pid)}, apy=${+apy.value || 0}, years=${+yrs.value || 1}, bonus=${+bonus.value || 0}, front_load=${shape})`);
    if (!r.ok) { capImpact.hidden = false; capImpact.replaceChildren(el('p', {}, r.why || 'Cap preview unavailable for these terms.')); yearHits.replaceChildren(); hitsRow.replaceChildren(); return; }
    y1.textContent = r.year1 != null ? `$${r.year1.toFixed(1)}m` : '—';
    total.textContent = `$${r.total}m`;
    const sy = f.querySelector('.summary-years'), sa = f.querySelector('.summary-apy');
    if (sy) sy.textContent = String(+yrs.value || 1);
    if (sa) sa.textContent = `$${apyOf().toFixed(1)}m`;
    { const s_ = +salary.value || 0, b = +bonus.value || 0, n = Math.max(1, +yrs.value || 1); breakdown.textContent = `${n} year${n === 1 ? '' : 's'} · $${s_.toFixed(1)}m salary + $${b.toFixed(1)}m signing bonus = $${apyOf().toFixed(1)}m a year, $${(s_ * n + b).toFixed(1)}m annualized total`; if (r.extension) breakdown.textContent += ` · ${r.existing_years} existing year${r.existing_years === 1 ? '' : 's'} retained; cap impact includes the existing deal and extension`; if (r.prorated) breakdown.textContent = `${n === 1 ? 'Remainder of this season' : n + ' seasons'} · $${apyOf().toFixed(1)}m annual rate · $${r.cash_this_season.toFixed(2)}m cash this season (including signing bonus) · $${r.year1.toFixed(2)}m current cap hit`; }
    capImpact.hidden = !r.extension;
    capImpact.replaceChildren(...(r.extension ? [extensionImpact(r)] : []));
    const visibleHits = r.hits.map((hit, i) => ({ hit, year: r.years[i], void: r.years[i] === r.expiry_year }));
    yearHits.hidden = !!r.extension; hitsRow.hidden = !!r.extension;
    const highestHit = Math.max(0.1, ...visibleHits.map(x => x.hit));
    yearHits.innerHTML = ''; visibleHits.forEach(x => yearHits.append(el('label', {}, `${x.void ? 'Void charge' : 'Cap hit'} · ${x.year}`, el('b', {}, `$${x.hit.toFixed(1)}m`))));
    hitsRow.innerHTML = ''; visibleHits.forEach(x => hitsRow.append(el('div', { class: 'hit' }, el('div', { class: 'hbar' }, el('i', { style: `height:${Math.min(100, x.hit / highestHit * 100)}%` })), el('span', {}, `${x.void ? 'Void charge · ' : ''}${x.year}`), el('b', {}, `$${x.hit.toFixed(1)}m`))));
  };
  salary.onchange = yrs.onchange = bonus.onchange = preview; salary.oninput = yrs.oninput = bonus.oninput = preview;
  const promises = el('div', { class: 'promise' }, el('span', {}, 'Promise:')); const chosen = [];
  for (const [k, l] of [['starting_role', 'Named the Starter'], ['captaincy', 'Captaincy'], ['no_trade', 'No Trade'], ['extension_by', 'Extension by a Set Year'], ['no_tag', 'No Franchise Tag']]) promises.append(el('button', { class: 'btn quiet', style: 'padding:2px 8px;font-size:14px', 'aria-pressed': 'false', onclick: e => { const i = chosen.indexOf(k); if (i < 0) chosen.push(k); else chosen.splice(i, 1); e.currentTarget.setAttribute('aria-pressed', String(i < 0)); } }, l));
  const breakdown = el('div', { class: 'count', style: 'padding:0 0 6px' });
  f.append(
    el('div', { class: 'offer-summary' },
      el('div', {}, el('span', {}, kind === 'extension' ? 'Added years' : 'Years'), el('b', { class: 'summary-years' }, String(start.years || t.years || 3))),
      el('div', {}, el('span', {}, 'Average per year'), el('b', { class: 'summary-apy' }, `$${apy.value}m`))
    ),
    el('div', { class: 'offer', style: 'grid-template-columns:repeat(4,1fr)' }, el('label', {}, kind === 'extension' ? 'Added years' : 'Years', yrs), el('label', {}, 'Salary ($m / yr)', salary), el('label', {}, 'Signing Bonus ($m)', bonus), el('label', {}, kind === 'extension' ? 'New money' : 'Total', total)), capImpact, yearHits, breakdown,
    el('div', { class: 'shape' }, el('span', {}, 'Shape'), shapeChips), hitsRow, promises);
  const acts = el('div', { class: 'acts' });
  acts.append(el('button', { class: 'btn go', onclick: () => { const r = pyJSON(`SESSION.personnel_act('offer', tid=${t.id}, apy=${+apy.value}, years=${+yrs.value}, bonus=${+bonus.value || 0}, front_load=${shape}, promises=${JSON.stringify(chosen)})`); notify(r); onDone(); } }, kind === 'fa_inseason' ? 'Offer (decides at Advance)' : preset ? 'Send Counter' : 'Send Offer'));
  if (kind === 'fa_inseason') acts.append(el('button', { class: 'btn', 'data-tip': 'His full ask, signed now', onclick: () => { const r = pyJSON(`SESSION.personnel_act('offer', tid=${t.id}, apy=${t.ask}, years=${t.years}, sign_today=True)`); notify(r); onDone(); } }, `Sign Today at $${t.ask}m`));
  acts.append(el('button', { class: 'btn quiet', 'data-tip': (t.offers && t.offers.length) ? 'Pull your offer and end the talks' : 'End the talks', onclick: () => { const r = pyJSON(`SESSION.personnel_act('withdraw', tid=${t.id})`); notify(r); onDone(); } }, (t.offers && t.offers.length) ? 'Rescind and Walk' : 'Let Him Go'));
  f.append(acts); setTimeout(preview, 0); return f;
}

// one line per open talk; click opens the conversation in its own window
function talkLine(t, reload) {
  const state = { open: 'awaiting your offer', waiting: 'agent deciding', countered: 'countered', match_requested: 'matching', accepted: 'agreed', declined: 'declined', expired: 'expired', broken_off: 'walked away' }[t.state] || t.state;
  const done = !['open', 'waiting', 'countered', 'match_requested'].includes(t.state);
  const ask=t.ask&&!done?`$${(+t.ask).toFixed(1)}m × ${t.years}`:'';
  return el('button', { class: 'talkline' + (done ? ' done' : ''), 'aria-label':`${done?'History':'Open'}: ${t.name}, ${state}`, 'data-tip':[t.opened?`Opened ${t.opened}`:'',state,ask].filter(Boolean).join(' · '), onclick: () => openTalks(t, reload) },
    el('span', { class: 'nm' }, t.name, el('small',{},t.pos)), el('span', { class: 'talk-state' }, state, ask?el('small',{},ask):''), el('span', { class: 'go' }, done ? 'History ›' : 'Open ›'));
}
// a concluded conversation offers a fresh start; the engine opens a new thread when the agent will take the call
function reopenTalks(t, reload) {
  const kind = t.kind; const page = kind === 'extension' ? 'extensions' : 'free_agency';
  const res = pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(t.pid)}, kind=${JSON.stringify(kind)})`);
  if (!res.ok) { notify(res); return; }
  const fresh = pyJSON(`SESSION.personnel(${JSON.stringify(page)})`); const nt = fresh.threads.find(x => x.id === res.thread) || fresh.threads.filter(x => x.pid === t.pid).pop();
  if (nt) openTalks(nt, reload); else reload();
}
// A TRADE OFFER, as a popup: what they send, what they want, the read, and Accept, Decline or Counter. Counter
// opens the Trades tab with both sides pre-loaded exactly as offered, to add to or change.
function openTradeOffer(id, after) {
  const v = pyJSON(`SESSION.trade_offer_view(${JSON.stringify(id)})`);
  if (!v.ok) { notify(v); return; }
  const overlay = el('div', { class: 'neg-overlay trade-offer-overlay' });
  const box = el('section', { class: 'sheet negotiation-sheet trade-offer-sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': `Trade offer from ${v.buyer.name}` });
  const theme = applyTeamTheme(box, v.buyer);
  box.style.setProperty('--club', theme.base); box.style.setProperty('--club-2', theme.accent);
  const close = () => { overlay.remove(); if (after) after(); };
  const answer = action => {
    const r = pyJSON(`SESSION.trade_offer_answer(${JSON.stringify(id)}, ${JSON.stringify(action)})`);
    notify(r);
    if (!r.ok) return;
    overlay.remove();
    renderRail(pyJSON('SESSION.portal()').rail);
    if (action === 'counter') {
      tradeState = { other: r.counter.other, a: r.counter.a, b: r.counter.b, counter_id: id, keep: true };
      if (location.hash === '#personnel/trades') {
        renderTrades(pyJSON(`SESSION.personnel('trades', other=${JSON.stringify(tradeState.other)}, a_sends=${JSON.stringify(tradeState.a)}, b_sends=${JSON.stringify(tradeState.b)})`));
      } else location.hash = '#personnel/trades';
    } else if (after) after();
  };
  box.append(el('div', { class: 'neg-topbar' }, el('div', { class: 'neg-identity' },
    el('div', { class: 'neg-avatar trade-offer-avatar' }, showAbbr(v.buyer.abbr)),
    el('div', { class: 'neg-title' }, el('div', { class: 'neg-kicker' }, 'INCOMING TRADE OFFER'),
      el('h2', {}, v.buyer.name), el('small', {}, v.expires != null ? `Expires after Week ${v.expires}` : 'Trade desk')),
    el('button', { class: 'btn quiet neg-close', onclick: close }, 'Close'))));
  const side = (title, items, team) => {
    const c = el('section', { class: 'trade-offer-side' }, el('h3', {}, title), el('small', { class: 'trade-offer-team' }, team.name));
    applyTeamTheme(c, team);
    for (const x of items) c.append(el('div', { class: 'trade-offer-asset' + (x.gone ? ' gone' : '') },
      el('span', { class: 'trade-offer-position' }, x.kind === 'pick' ? 'PICK' : x.pos || '—'),
      el('div', { class: 'nm' }, x.label, el('small', {}, x.gone ? 'No longer available' : x.kind === 'player' ? `Age ${x.age} · $${x.apy}m per year` : 'Draft capital')),
      x.kind === 'player' ? el('b', {}, `${x.ovr} OVR`) : ''));
    if (!items.length) c.append(el('div', { class: 'empty' }, 'No assets'));
    return c;
  };
  box.append(el('div', { class: 'trade-offer-columns' }, side('YOU RECEIVE', v.they, v.buyer), side('YOU SEND', v.you, v.me)));
  if (v.read) box.append(el('div', { class: 'trade-offer-read' }, el('h3', {}, 'Front office assessment'), el('p', {}, v.read)));
  const actions = el('div', { class: 'trade-offer-actions' });
  if (v.open) actions.append(
    el('button', { class: 'btn go', onclick: () => answer('accept') }, 'Accept'),
    el('button', { class: 'btn', onclick: () => answer('counter') }, 'Counter'),
    el('button', { class: 'btn quiet', onclick: () => answer('decline') }, 'Decline'));
  else {
    actions.append(el('span', {}, `Original offer: ${v.status}.`));
    if (v.status === 'countered' && ['draft', 'declined'].includes(v.counter?.state))
      actions.append(el('button', { class: 'btn go', onclick: () => answer('counter') }, 'Continue Counter'));
    else if (v.counter) actions.append(el('span', {}, `Counter: ${v.counter.state}.`));
  }
  box.append(actions); overlay.append(box); document.body.append(overlay);
}

function openTalks(t, reload) {
  const overlay = el('div', { class: 'neg-overlay', style: 'position:fixed;inset:0;z-index:900;display:flex;align-items:center;justify-content:center' });
  const box = el('section', { class: 'sheet negotiation-sheet', style: 'width:min(980px,95vw);max-height:92vh;overflow:auto' });
  applyTeamTheme(box, personnelRailTeam || {});
  box.style.setProperty('--club', teamTheme(personnelRailTeam || {}).base);
  box.style.setProperty('--club-2', teamTheme(personnelRailTeam || {}).accent);
  const close = () => { overlay.remove(); reload(); };
  const done = !['open', 'waiting', 'countered', 'match_requested'].includes(t.state);

  const stateLabel = t.state === 'waiting' ? 'AWAITING RESPONSE' :
    t.state === 'countered' ? 'COUNTER RECEIVED' :
    t.state === 'match_requested' ? 'COMPETING OFFER' :
    done ? 'TALKS CLOSED' : 'OPEN NEGOTIATION';

  const identity = el('div', { class: 'neg-identity' },
    el('div', { class: 'neg-avatar' }, t.pos || ''),
    el('div', { class: 'neg-title' },
      el('div', { class: 'neg-kicker' }, `${t.kind === 'extension' ? 'CONTRACT EXTENSION' : 'FREE AGENCY'} · NEGOTIATION DESK`),
      el('h2', {}, `${t.name} · ${t.pos}`),
      el('small', {}, t.opened ? `Talks opened ${t.opened}` : 'Negotiation opened')
    ),
    el('div', { class: 'neg-state' }, stateLabel),
    done ? el('button', { class: 'btn go', onclick: () => { overlay.remove(); reopenTalks(t, reload); } }, 'Open Talks Again') : '',
    el('button', { class: 'btn quiet neg-close', onclick: close }, 'Close')
  );

  box.append(el('div', { class: 'neg-topbar' }, identity));
  box.append(threadBox(t, () => {
    const fresh = pyJSON(`SESSION.personnel(${JSON.stringify(t.kind === 'extension' ? 'extensions' : 'free_agency')})`);
    const nt = fresh.threads.find(x => x.id === t.id);
    overlay.remove();
    if (nt && ['open', 'waiting', 'countered', 'match_requested'].includes(nt.state)) openTalks(nt, reload);
    else reload();
  }));

  overlay.append(box);
  document.body.append(overlay);
}

function extensionCapMetrics(cap, current = false) {
  return [[`$${cap.limit.toFixed(1)}m`, `${cap.year} Cap`],
    [`$${cap.committed.toFixed(1)}m`, `${cap.year} Committed`],
    [`$${cap.space.toFixed(1)}m`, current ? 'Current Cap Space' : 'Cap Space for Extensions']];
}
function extensionBudgets(current, next) {
  const budgets = el('div', { class: 'extension-budgets' });
  for (const [cap, now] of [[current, true], [next, false]]) {
    if (!cap) continue;
    const strip = el('section', { class: 'extension-cap-year' }, el('h3', {}, now ? 'This year' : 'Next year · projected'));
    const metrics = el('div', { class: 'extension-cap-metrics' });
    for (const [value, label] of extensionCapMetrics(cap, now)) metrics.append(el('div', {}, el('b', {}, value), el('small', {}, label)));
    strip.append(metrics); budgets.append(strip);
  }
  return budgets;
}
function extensionImpact(preview, title = 'Proposed extension · cap impact') {
  const rows = preview.cap_impact || [], current = rows[0];
  const money = n => `${n < 0 ? '−' : ''}$${Math.abs(n).toFixed(3)}m`;
  const delta = n => `${n > 0 ? '+' : ''}${money(n)}`;
  const box = el('section', { class: 'extension-impact' }, el('h3', {}, title));
  if (!current) return box;
  box.append(el('div', { class: 'extension-impact-now' }, el('span', {}, `This year · ${current.year}`),
    el('b', {}, `${delta(current.change)} cap change`), el('small', {}, `Player’s total cap hit: ${money(current.total)}`)));
  const table = el('table', { class: 'extension-impact-table' }, el('thead', {}, el('tr', {},
    ...['Year', 'Existing deal', 'Extension change', 'Total cap hit'].map(label => el('th', {}, label)))));
  const body = el('tbody');
  for (const [i, r] of rows.entries()) body.append(el('tr', { class: i === 0 ? 'current' : '' },
    el('td', {}, `${r.year}${i === 0 ? ' · This year' : r.year === preview.expiry_year ? ' · Void charge' : ''}`),
    el('td', {}, money(r.existing)), el('td', {}, delta(r.change)), el('td', {}, money(r.total))));
  table.append(body); box.append(el('div', { class: 'extension-impact-scroll' }, table),
    el('p', {}, 'Total cap hits include the existing contract plus this extension. Signing-bonus proration can add a charge this year.'));
  return box;
}
function threadBox(t, onDone) {
  const box = el('div', { class: 'thread negotiation-thread' });
  if (t.kind === 'extension' && t.extension_cap) {
    box.append(extensionBudgets(t.current_cap, t.extension_cap));
  } else if (t.cap) box.append(el('div', { class: 'msg note cap-strip' }, el('b', {}, `${t.cap.year} cap · `), `$${t.cap.limit}m limit, $${t.cap.committed}m committed, `, el('b', {}, `$${t.cap.space}m of room`), t.cap.next ? ' (next year, the ledger this deal lands on)' : ''));
  // the conversation as logged: every line with who said it, then the agent's temperament, then the decision
  const log = t.log && t.log.length ? t.log : [];
  if (!log.length) box.append(el('div', { class: 'msg' }, el('div', { class: 'from' }, `Agent · Before Any Offer`), el('div', { class: 'txt' }, t.ask ? el('span', {}, `He is asking `, el('b', {}, `$${t.ask}m × ${t.years}`), '.') : 'He would rather wait.')));
  for (const ln of log) box.append(el('div', { class: 'msg' + (ln.who === 'you' ? ' you' : '') }, el('div', { class: 'from' }, ln.who === 'you' ? 'You' : 'Agent'), el('div', { class: 'txt' }, ln.text)));
  if (t.ask && log.length) box.append(el('div', { class: 'msg note' }, el('b', {}, 'Ask · '), `$${t.ask}m × ${t.years}`));
  box.append(el('div', { class: 'msg note' }, t.agent_line || ''));
  const matching=t.state==='match_requested' && !!t.rival;
  const countered=t.state==='countered' && !!t.counter;
  if (t.kind === 'extension' && t.offer_cap_preview?.ok)
    box.append(extensionImpact(t.offer_cap_preview, countered ? 'Agent counter · cap impact' : 'Submitted offer · cap impact'));
  const feedback=el('div',{class:'msg note',role:'alert',hidden:true});
  const act=action=>{const r=pyJSON(`SESSION.personnel_act('${action}', tid=${t.id})`);notify(r);if(r.ok)onDone();else{feedback.hidden=false;feedback.textContent=r.why||'The decision could not be completed.';}};
  if (matching) box.append(el('div', { class: 'msg match rival-panel' }, el('div', { class: 'from' }, 'To Match'), el('div', { class: 'txt' }, `${showAbbr(t.rival.team)} has offered `, el('b', {}, `$${t.rival.apy}m × ${t.rival.years}`), '. Match it and he signs today.'), el('div', { class: 'acts' }, el('button', { class: 'btn go', onclick: () => { act('match'); } }, 'Match and Sign'), el('button', { class: 'btn quiet', onclick: () => { act('withdraw'); } }, 'Let Him Go'))));
  if (countered) box.append(el('div', { class: 'msg' }, el('div', { class: 'from' }, 'Counter'), el('div', { class: 'txt' }, el('b', {}, `$${t.counter.apy}m × ${t.counter.years}`), el('div', {}, t.counter.bonus != null ? `Signing bonus: $${Number(t.counter.bonus).toFixed(2)}m` : 'Signing bonus: standard structure'), el('small', {}, 'Even loading means equal base salaries in the new years; existing salary and bonus charges still apply.')), el('div', { class: 'acts' }, el('button', { class: 'btn go', onclick: () => { act('match_counter'); } }, 'Accept Counter'))));
  if (t.state === 'waiting') box.append(el('div', { class: 'msg note', style: 'display:flex;align-items:center;gap:12px' }, el('span', { style: 'flex:1' }, `Waiting on his answer${t.due ? ' · due ' + t.due : ''}.`), el('button', { class: 'btn quiet', 'data-tip': 'Pull the offer before he answers; the thread closes', onclick: () => { act('withdraw'); } }, 'Rescind Offer')));
  else if (['accepted', 'signed'].includes(t.state)) box.append(el('div', { class: 'msg note' }, 'Signed.'));
  else if (t.state === 'broken_off') box.append(el('div', { class: 'msg note' }, 'He has broken off talks.'));
  else if (t.state === 'declined') box.append(el('div', { class: 'msg note' }, 'He declined.'));
  else if (!matching && ['open','countered'].includes(t.state)) box.append(offerForm(t, t.kind, onDone, countered ? { apy: t.counter.apy, years: t.counter.years } : null));
  box.append(feedback);
  return box;
}


// Common Personnel presentation; original action buttons retain their engine handlers.
const personnelSelected = {fa:null, extensions:null};
function completedExtensionTerms(record) {
  return {
    outcome: ({extended:'Extended', tagged:'Franchise Tagged', 'option exercised':'Option Exercised'})[record.kind] || record.kind || 'Completed',
    term: record.kind === 'extended' ? (record.years == null ? '—' : `${record.years} added year${record.years === 1 ? '' : 's'}`) : '1 year',
    annual: Number.isFinite(record.apy) ? `$${record.apy.toFixed(1)}m` : '—'
  };
}
function finishPersonnel(page, v, kind, left, right, extra = []) {
  const club = v.rail.club, board = el('section',{class:`sheet c12 personnel-board personnel-${kind}`});
  applyTeamTheme(board, club);
  board.style.setProperty('--club', teamTheme(club).base);
  board.style.setProperty('--club-2', teamTheme(club).accent);
  const heading = left.querySelector('h2');
  const subtitle = heading?.querySelector('small')?.textContent || '';
  heading?.remove();
  const title = {fa:'FREE AGENCY',wire:'WAIVER WIRE',extensions:'EXTENSIONS'}[kind];
  const metrics = kind === 'fa' ? [[v.count,'Available'],[`$${v.cap_focus?.space ?? v.cap}m`,'Available cap room'],[`$${v.cap_focus?.pending_offers ?? 0}m`,'Held for offers'],[`$${v.committed_next}m / $${v.limit_next}m`,'Next year committed']] : kind === 'wire' ? [[v.my_priority ? `${v.my_priority}${ord(v.my_priority)}` : '—','Your priority'],[v.rows.length,'Available'],[v.awards,'Awards']] : [];
  const hero=el('div',{class:'personnel-hero'},el('div',{},el('small',{},club.name.toUpperCase()),el('h1',{},title),el('p',{},subtitle)));
  const stats=el('div',{class:'personnel-metrics'});
  for(const [value,label] of metrics) stats.append(el('div',{},el('b',{},value),el('small',{},label)));
  hero.append(stats);board.append(hero);
  if (kind === 'extensions') board.append(extensionBudgets(v.current_cap, v.extension_cap));
  left.className='personnel-main'; right.className='personnel-aside';
  const grid=el('div',{class:'personnel-columns'},left,right);board.append(grid);
  // Preserve seasonal content (tags/tenders) and the FA transaction feed.
  for(const item of extra){item.classList.add('personnel-extra');item.style.order='';board.append(item);}
  const existing=[...page.children].filter(node=>node!==left&&node!==right&&!extra.includes(node));
  for(const item of existing){item.classList.add('personnel-extra');board.append(item);}
  page.replaceChildren(board);
  for(const table of left.querySelectorAll(':scope > table')) {
    const wrap=el('div',{class:'personnel-table-scroll'});table.before(wrap);wrap.append(table);
  }
  if(kind==='wire') {
    right.append(el('div',{class:'personnel-help'},el('h3',{},'How claims work'),el('p',{},'Claims are awarded at the next advance. Your priority determines who gets the player.')));
    left.querySelector('.foot')?.append(el('a',{class:'btn',href:'#club'},'View Roster'));
    if(!v.rows.length&&wireTab==='wire'){
      const empty=left.querySelector('.empty');
      if(empty){empty.classList.add('personnel-wire-empty');empty.replaceChildren(el('div',{class:'personnel-empty-symbol','aria-hidden':'true'},'◇'),el('h3',{},'The wire is clear.'),el('p',{},'Players placed on waivers will appear here.'),el('a',{class:'btn',href:'#personnel/fa'},'Browse Free Agency'));}
    }
    return;
  }
  const detail=el('div',{class:'personnel-detail'});right.prepend(detail);
  const table=left.querySelector('table'); table.classList.add('personnel-player-table');
  const source=kind==='fa'?v.rows:(v[extTab]||[]);
  const completed=kind==='extensions'&&extTab==='done';
  const sourceByPid=new Map(source.map(r=>[String(r.pid),r]));
  const sourceByName=new Map(source.map(r=>[r.name,r]));
  let previous=null;
  const drawSelection=(row,record)=>{
    if(previous?.row===row)return;
    if(previous) {previous.cell.append(...previous.actions);previous.row.classList.remove('personnel-selected');previous.row.setAttribute('aria-selected','false');}
    detail.replaceChildren();personnelSelected[kind]=record.pid;
    row.classList.add('personnel-selected');row.setAttribute('aria-selected','true');
    const cell=row.lastElementChild;
    const actions=[...cell.children];
    const actionArea=el('div',{class:'personnel-detail-actions'},...actions);
    const deal=completed?completedExtensionTerms(record):null;
    const name=el('div',{class:'personnel-detail-name'},el('span',{class:'personnel-position'},record.display_pos || record.pos),el('div',{},el('h2',{},record.name),el('p',{},completed?record.pos:`${record.display_pos || record.pos} · ${record.age} · ${record.ovr} OVR`)));
    detail.append(name,el('p',{class:'personnel-detail-status'},completed?`${deal.outcome} · ${deal.term} · ${deal.annual} per year`:kind==='extensions'?`${record.tag_line || ''} · $${record.hit.toFixed(1)}m cap hit`:record.thread?'Negotiation in progress':'No talks started'),actionArea,el('a',{class:'btn quiet',href:'#club/player/'+record.pid},'Open Player'));
    previous={row,cell,actions};
  };
  const bindRows=()=>{
    previous=null;detail.replaceChildren();let first=null, selected=null;
    for(const row of table.querySelectorAll('tr')){
      const who=row.querySelector('button.who');if(!who)continue;
      const name=who.querySelector('.nm')?.firstChild?.textContent;
      const record=who.dataset.sourceIndex!=null?source[Number(who.dataset.sourceIndex)]:(sourceByPid.get(who.dataset.pid)||sourceByName.get(name));if(!record)continue;
      row.tabIndex=0;row.setAttribute('aria-label',`Select ${record.name}`);
      row.setAttribute('aria-selected','false');
      row.addEventListener('click',e=>{if(!e.target.closest('button,a'))drawSelection(row,record);});
      row.addEventListener('keydown',e=>{if(e.target===row&&(e.key==='Enter'||e.key===' ')){e.preventDefault();drawSelection(row,record);}});
      if(!first)first=[row,record];if(record.pid===personnelSelected[kind])selected=[row,record];
    }
    if(selected||first)drawSelection(...(selected||first));
    else detail.append(el('div',{class:'empty'},completed?'Select a completed decision to view its details.':'Select a player to view available actions.'));
  };
  bindRows();
  // Free-agency search redraws only the table, so refresh its detail selection afterward.
  const search=left.querySelector('input[type=search]');
  if(search&&kind!=='fa')search.addEventListener('input',bindRows);
  return bindRows;
}

let faPos = '', faPosition = '', faWatch = false, faRookie = false, faQuery = '';
function faFilterGroups(v) {
  const fallback={QB:['QB'],HB:['HB'],FB:['FB'],WR:['WR'],TE:['TE'],OL:['LT','LG','C','RG','RT'],DL:['LEDG','DT','REDG'],DB:['CB','FS','SS'],LB:['MIKE','WILL','SAM'],ST:['K','P','LS']};
  const supplied=new Map((v.position_filters||[]).map(g=>[g.group,g.positions]));
  return Object.entries(fallback).map(([group,positions])=>({group,positions:supplied.get(group)||positions.map(key=>({key,label:key}))}));
}
function faMatchesPosition(row,group,position) {
  if(!group)return true;
  const keys=position?[position]:group.positions.map(p=>p.key);
  return keys.some(key=>(row.filter_positions||[row.pos]).includes(key));
}
function renderFA(v) {
  renderRail(v.rail); const page = persPage(); persSecond('fa');
  const reload = () => renderFA(pyJSON(`SESSION.personnel('free_agency')`));
  const groups=faFilterGroups(v);
  if(faPosition&&!groups.find(g=>g.group===faPos)?.positions.some(p=>p.key===faPosition))faPosition='';
  let bindSelection=()=>{};
  const inSeason = v.in_season;
  const left = el('section', { class: 'sheet c8' }, el('h2', {}, v.fa_round ? `Free Agency · Round ${v.fa_round}` : 'Free Agency', el('small', {}, inSeason
    ? `${v.count} Available · ${v.weeks_left} week${v.weeks_left === 1 ? '' : 's'} left · Roster ${v.roster} · Practice Squad ${v.ps}`
    : `${v.top51 ? 'Top 51 · ' : ''}Available room is net of pending offers${v.fa_round ? ' · offers resolve when you advance' : ''}`)));
  const tools = el('div', { class: 'tools fa-filter-tools' });
  const positions=el('div',{class:'chips fa-position-options','aria-label':'Individual position'});
  const redraw=()=>{drawPositionChoices();drawRows();};
  const posChips = el('div', { class: 'chips fa-group-options','aria-label':'Position group' }); for (const g of ['All',...groups.map(g=>g.group)]) posChips.append(el('button', { class: 'chip', 'aria-pressed': String((faPos || 'All') === g), 'data-group':g, onclick: () => { faPos = g === 'All' ? '' : g;faPosition='';redraw(); } }, g));
  const drawPositionChoices=()=>{
    for(const button of posChips.querySelectorAll('button'))button.setAttribute('aria-pressed',String(button.dataset.group===(faPos||'All')));
    positions.replaceChildren();const group=groups.find(g=>g.group===faPos);positions.hidden=!group||group.positions.length<2;
    if(!positions.hidden)for(const p of [{key:'',label:`All ${faPos}`},...group.positions])positions.append(el('button',{class:'chip','aria-pressed':String(faPosition===p.key),onclick:()=>{faPosition=p.key;redraw();}},p.label));
  };
  const watchB = el('button', { class: 'chip', 'aria-pressed': String(faWatch), onclick:e => { faWatch = !faWatch;e.currentTarget.setAttribute('aria-pressed',String(faWatch));drawRows(); } }, `Watchlist · ${v.rows.filter(r => r.watch).length}`);
  const rookieB = el('button', { class: 'chip', 'aria-pressed': String(faRookie), 'data-tip': 'This year\'s undrafted rookies, on the market at the minimum', onclick:e => { faRookie = !faRookie;e.currentTarget.setAttribute('aria-pressed',String(faRookie));drawRows(); } }, `Undrafted · ${v.rows.filter(r => r.rookie).length}`);
  const search = el('input', { type: 'search', class: 'find', placeholder: 'Find a Player', value: faQuery }); search.oninput = () => { faQuery = search.value; drawRows(); };
  tools.append(posChips,positions, el('div', { class: 'chips' }, ...(inSeason ? [] : [watchB]), ...(v.rows.some(r => r.rookie) ? [rookieB] : [])), search);drawPositionChoices();
  left.append(tools);
  const tbl = el('table', { class: 'tbl' });
  const drawRows = () => {
    tbl.innerHTML = '';
    if (inSeason) tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', { class: 'n', 'data-tip': 'How he grades in your scheme' }, 'Fit'), el('th', { 'data-tip': 'His agent\'s number, a year' }, 'Ask'), el('th', { class: 'n', 'data-tip': 'What he costs this year, prorated to the weeks left' }, 'This Year'), el('th', {}, ''), el('th', {}, '')));
    else tbl.append(el('tr', {}, el('th', {}, ''), el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', { class: 'n', 'data-tip': 'How he grades in your scheme' }, 'Fit'), el('th', {}, 'Ask'), el('th', {}, 'Interest'), el('th', {}, 'Your Offer'), el('th', {}, '')));
    const q = faQuery.trim().toLowerCase();
    const rows = v.rows.filter(r => faMatchesPosition(r,groups.find(g=>g.group===faPos),faPosition) && (!faWatch || r.watch) && (!faRookie || r.rookie) && (!q || r.name.toLowerCase().includes(q)));
    for (const r of rows) {
      const displayPos=r.display_pos || r.pos;
      const who = el('td', {}, el('button', { class: 'who', 'data-pid':r.pid, onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, displayPos), el('div', { class: 'nm' }, r.name, el('small', {}, inSeason ? (r.hole || displayPos) : `${displayPos}${r.last ? ' · from ' + r.last : ''}`))));
      const askBtn = el('div', { style: 'display:flex;gap:4px' }, r.thread ? el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', onclick: () => { const th = v.threads.find(x => x.id === r.thread); if (th) openTalks(th, reload); } }, inSeason ? 'Talks' : 'Offer') : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', onclick: () => { const res = pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind=${JSON.stringify(inSeason ? 'fa_inseason' : 'fa_offseason')})`); if (!res.ok) { notify(res); reload(); return; } const fresh = pyJSON(`SESSION.personnel('free_agency')`); const th = fresh.threads.find(x => x.id === res.thread) || fresh.threads.filter(x => x.pid === r.pid).pop(); renderFA(fresh); if (th) openTalks(th, () => renderFA(pyJSON(`SESSION.personnel('free_agency')`))); } }, 'Ask the Agent'),
        inSeason && r.ps_ok ? el('button', { class: 'btn quiet', style: 'width:auto;padding:3px 8px;font-size:14px', 'data-tip': 'Sign him to the practice squad at the weekly rate; he can say no', onclick: () => { notify(pyJSON(`SESSION.personnel_act('sign_ps', pid=${JSON.stringify(r.pid)})`)); reload(); } }, 'Practice Squad') : '');
      if (inSeason) tbl.append(el('tr', {}, who, el('td', {}, displayPos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, fitCell(r.fit)), el('td', {}, r.ask ? `$${r.ask}m × ${r.years}` : el('span', { style: 'color:var(--ink-3)' }, '—')), el('td', { class: 'n' }, r.ask_now != null ? `$${r.ask_now.toFixed(2)}m` : '—'),
        el('td', {}, r.thread && r.ask ? el('button', { class: 'btn go', style: 'width:auto;padding:3px 8px;font-size:14px', 'data-tip': 'His full ask, signed now', onclick: () => { const t = v.threads.find(x => x.id === r.thread); const res = pyJSON(`SESSION.personnel_act('offer', tid=${r.thread}, apy=${t ? t.ask : r.ask}, years=${t ? t.years : r.years}, sign_today=True)`); notify(res); reload(); } }, 'Sign') : ''), el('td', {}, askBtn)));
      else tbl.append(el('tr', {}, el('td', {}, el('button', { class: 'star' + (r.watch ? ' on' : ''), 'data-tip': r.watch ? 'On your watchlist' : 'Add to your watchlist', onclick: () => { pyJSON(`SESSION.personnel_act('watch', pid=${JSON.stringify(r.pid)})`); reload(); } }, '★')), who, el('td', {}, displayPos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, fitCell(r.fit)),
        el('td', {}, r.ask ? `$${r.ask}m × ${r.years}` : el('span', { style: 'color:var(--ink-3)' }, '—')), el('td', {}, r.interest ? el('span', { class: 'pill ' + ({ 'Match Asked': 'unsettled', Agreed: 'happy', Countered: 'content', Mulling: 'content', Walked: 'unhappy' }[r.interest] || 'content') }, r.interest) : '', r.bidders ? el('small', { class: 'count', style: 'display:block', 'data-tip': 'Clubs with an offer lodged on him this round' }, `${r.bidders} club${r.bidders === 1 ? '' : 's'} in`) : ''), el('td', {}, r.my_offer || el('span', { style: 'color:var(--ink-3)' }, '—')), el('td', {}, askBtn)));
    }
    if (!rows.length) tbl.append(el('tr', {}, el('td', { colspan: '10' }, el('div', { class: 'empty' }, v.rows.length ? 'Nobody matches the filter.' : 'Nobody is on the market.'))));
    bindSelection();
  };
  left.append(tbl); drawRows();
  page.append(left);
  const right = el('section', { class: 'sheet c4' }, el('h2', {}, inSeason ? 'Talks' : 'Negotiation', el('small', {}, `${v.threads.length} open`)));
  { const live_ = ['open', 'waiting', 'countered', 'match_requested']; const ths = [...v.threads].sort((a, b) => (live_.includes(b.state) ? 1 : 0) - (live_.includes(a.state) ? 1 : 0) || b.id - a.id); for (const t of ths) right.append(talkLine(t, reload)); }
  if (!v.threads.length) right.append(el('div', { class: 'empty' }, inSeason ? 'Ask an agent to hear his number. Sign at the ask today, or make a one-week offer that decides at the Advance.' : 'Ask an agent to open talks; he weighs offers through each round of the market.'));
  const feedSheet = el('section', { class: 'sheet c4', style: 'order:2' }, el('h2', {}, 'Around the League Today', el('small', {}, 'latest signings')));
  const fd = el('div', { class: 'feed' }); for (const f of v.feed) fd.append(el('div', {}, el('span', {}, stripe(f.team.abbr)), el('span', {}, `${f.team.name} ${f.kind === 'signs' ? 'signed' : 'extended'} `, el('b', {}, f.name), `, ${f.pos}${f.years ? `, ${f.years} year${f.years === 1 ? '' : 's'}` : ''}${f.apy ? ` at $${f.apy}m a year` : ''}`), el('time', {}, f.week ? `Wk ${f.week}` : ''))); if (!v.feed.length) fd.append(el('div', { class: 'empty' }, 'Quiet so far.')); feedSheet.append(fd);
  page.append(right, feedSheet);
  bindSelection=finishPersonnel(page, v, 'fa', left, right, [feedSheet]);
}

let wireTab = 'wire';
function renderWire(v) {
  renderRail(v.rail); const page = persPage(); persSecond('wire');
  const reload = () => renderWire(pyJSON(`SESSION.personnel('waivers')`));
  const left = el('section', { class: 'sheet c8' }, el('h2', {}, 'Waiver Wire', el('small', {}, `You Hold ${v.my_priority ?? '—'}${v.my_priority ? ord(v.my_priority) : ''} Priority · Awards ${v.awards}`)));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' });
  for (const [k, label, n] of [['wire', 'On the Wire', v.rows.length], ['claims', 'Your Claims', v.claims.length], ['outbound', 'From Your Club', (v.outbound || []).length], ['awarded', 'Awarded This Week', (v.awarded || []).length]]) tabs.append(el('button', { 'aria-pressed': String(wireTab === k), onclick: () => { wireTab = k; renderWire(v); } }, label + ' ', el('em', {}, n)));
  left.append(tabs);
  const rows = wireTab === 'wire' ? v.rows : wireTab === 'claims' ? v.claims : wireTab === 'outbound' ? (v.outbound || []) : (v.awarded || []);
  const tbl = el('table', { class: 'tbl' });
  if (wireTab === 'outbound') {
    tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', { 'data-tip': 'What happens when the wire runs at the next advance' }, 'If He Clears'), el('th', { class: 'n', 'data-tip': 'Clubs with a claim in' }, 'Claims')));
    for (const r of rows) tbl.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name))), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', {}, r.intent), el('td', { class: 'n' }, r.claims)));
    if (!rows.length) tbl.append(el('tr', {}, el('td', { colspan: '6' }, el('div', { class: 'empty' }, 'None of your players are on the wire.'))));
  }
  else if (wireTab === 'awarded') { tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', {}, 'To'), el('th', {}, 'From'))); for (const r of rows) tbl.append(el('tr', { style: r.mine ? 'background:var(--sheet-2)' : '' }, el('td', {}, r.name), el('td', {}, r.pos), el('td', {}, r.team ? stripe(r.team.abbr, r.team.name) : ''), el('td', {}, r.frm || ''))); }
  else {
    tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', { class: 'n', 'data-tip': 'How he grades in your scheme' }, 'Fit'), el('th', {}, 'From'), el('th', { 'data-tip': 'The contract you take on' }, 'Inherited'), el('th', { class: 'n', 'data-tip': 'Dead cap if you cut him after' }, 'Penalty'), el('th', { class: 'n', 'data-tip': 'Accrued seasons' }, 'Accrued'), el('th', {}, '')));
    for (const r of rows) tbl.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos}${r.home_state ? ' · ' + r.home_state : ''}`)))), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, fitCell(r.fit)), el('td', {}, r.frm), el('td', {}, r.inherited), el('td', { class: 'n' }, `$${r.penalty.toFixed(1)}m`), el('td', { class: 'n' }, r.accrued),
      el('td', {}, r.claimed ? el('span', { class: 'badge-sm' }, 'Claimed') : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', onclick: () => { wireClaim = r.pid; renderWire(v); } }, 'Claim'))));
  }
  if (!rows.length && wireTab !== 'outbound') tbl.append(el('tr', {}, el('td', { colspan: '10' }, el('div', { class: 'empty' }, wireTab === 'wire' ? 'The wire is clear.' : wireTab === 'claims' ? 'No claims in.' : 'Nothing awarded yet this week.'))));
  left.append(tbl);
  left.append(el('div', { class: 'foot' }, el('span', { class: 'count' }, v.roster_full ? `A claim needs a roster spot: you are at ${v.roster}` : `Roster ${v.roster} · a claim fills the open spot`)));
  page.append(left);
  const right = el('section', { class: 'sheet c4' });
  const claim = wireClaim ? v.rows.find(r => r.pid === wireClaim) : null;
  if (claim) {
    right.append(el('h2', {}, 'Your Claim', el('small', {}, claim.name)));
    right.append(el('div', { class: 'read', style: 'margin:10px 12px' }, el('b', {}, 'Assistants: '), claim.read || ''));
    let releasePid = null;
    if (v.roster_full) {
      right.append(el('div', { class: 'h5', style: 'padding:0 12px' }, 'If Awarded, Release'));
      const sel = el('select', { class: 'btn', style: 'margin:6px 12px;width:calc(100% - 24px)' }); for (const c of v.cut_options) sel.append(el('option', { value: c.pid }, `${c.name} · ${c.pos} · ${c.ovr} · Penalty $${c.penalty}m`)); releasePid = v.cut_options.length ? v.cut_options[0].pid : null; sel.onchange = () => { releasePid = sel.value; }; right.append(sel);
    }
    right.append(el('div', { class: 'acts', style: 'padding:6px 12px 12px' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.personnel_act('claim', pid=${JSON.stringify(claim.pid)}${releasePid ? ', release_pid=' + JSON.stringify(releasePid) : ''})`)); wireClaim = null; reload(); } }, 'Put In the Claim'), el('button', { class: 'btn quiet', onclick: () => { wireClaim = null; renderWire(v); } }, 'Cancel')));
  } else if (v.claims.length) {
    right.append(el('h2', {}, 'Your Claim', el('small', {}, v.claims.map(c => c.name).join(', '))));
    for (const c of v.claims) right.append(el('div', { class: 'read', style: 'margin:10px 12px' }, el('b', {}, 'Assistants: '), c.read || ''), el('div', { class: 'acts', style: 'padding:0 12px 10px' }, el('button', { class: 'btn quiet', onclick: () => { notify(pyJSON(`SESSION.personnel_act('withdraw_claim', pid=${JSON.stringify(c.pid)})`)); reload(); } }, 'Withdraw Claim')));
  }
  right.append(el('h2', { style: claim || v.claims.length ? 'border-top:1px solid var(--rule-2)' : '' }, 'Priority Order', el('small', {}, 'This Week')));
  const pr = el('div', { class: 'pad' }); const mine = v.my_priority || 0;
  v.priority.forEach((c, i) => { const me = c.abbr === v.rail.club.abbr; if (i < 3 || me || i >= v.priority.length - 1) pr.append(el('div', { class: 'prio' + (me ? ' me' : '') }, el('span', { class: 'p' }, i + 1), stripe(c.abbr, c.name))); else if (i === 3) pr.append(el('div', { class: 'prio', style: 'color:var(--ink-3)' }, el('span', { class: 'p' }, '…'), `${Math.max(0, mine - 5)} more`)); });
  right.append(pr); page.append(right);
  finishPersonnel(page, v, 'wire', left, right);
}
let wireClaim = null;

let retainTab = 'rfa', pendingExtensionPid = null;
function renderRetain(v) {
  renderRail(v.rail); const page=persPage(); persSecond('retain');
  const rfa=retainTab==='rfa', club=v.rail.club;
  const reload=()=>renderRetain(pyJSON("SESSION.personnel('retain')"));
  const board=el('section',{class:'sheet c12 personnel-board retain-board'});
  applyTeamTheme(board,club);
  const money=n=>`$${Number(n).toFixed(3).replace(/0+$/,'').replace(/\.$/,'')}m`;
  const hero=el('div',{class:'personnel-hero'},el('div',{},el('small',{},club.name.toUpperCase()),el('h1',{},'RETAIN PLAYERS'),el('p',{},rfa?'Preserve your rights to restricted free agents.':'Keep your unrestricted free agents with a tag or a long-term deal.')));
  const metrics=el('div',{class:'personnel-metrics'},el('div',{},el('b',{},money(v.cap_space)),el('small',{},'Cap space')));
  metrics.append(rfa?el('div',{},el('b',{},money(v.pending_tenders)),el('small',{},'Pending tenders')):el('div',{},el('b',{},v.tag_used?'0 / 1':'1 / 1'),el('small',{},'Tag available')));
  hero.append(metrics);board.append(hero);
  const filters=el('div',{class:'retain-filters'});
  for(const key of ['rfa','ufa']) filters.append(el('button',{class:'btn',type:'button','aria-pressed':String(retainTab===key),onclick:()=>{retainTab=key;reload();}},key.toUpperCase()));
  board.append(filters);
  const rows=v[retainTab]||[];
  board.append(el('div',{class:'retain-section'},el('b',{},`${rfa?'Restricted':'Unrestricted'} free agents · ${rows.length} players`),el('span',{},v.open?(rfa?'One-year tender offers':'Expiring contracts'):'Retention window closed')));
  const table=el('table',{class:'tbl retain-table','aria-label':rfa?'Restricted free agents':'Unrestricted free agents'});
  const headings=rfa?['Player','Pos','Age','OVR','Tender offer','Tender']:['Player','Pos','Age','OVR','Franchise tag','Extension'];
  const cls=i=>i>=4?(rfa&&i===4?'n retain-amount':'retain-action'):i===2||i===3?'n':'';
  table.append(el('thead',{},el('tr',{},...headings.map((label,i)=>el('th',{scope:'col',class:cls(i)},label)))));
  const body=el('tbody');
  const act=(action,pid)=>{const result=pyJSON(`SESSION.resign_act(${JSON.stringify(action)},pid=${JSON.stringify(pid)})`);notify(result);reload();};
  const confirmTag=r=>{
    const dialog=el('dialog',{class:'retain-tag-dialog','aria-labelledby':'retain-tag-title'});applyTeamTheme(dialog,club);
    const cancel=el('button',{class:'btn',onclick:()=>dialog.close()},'Cancel');
    dialog.append(el('div',{class:'retain-dialog-body'},el('small',{},`${club.name.toUpperCase()} · FRANCHISE TAG`),el('h2',{id:'retain-tag-title'},'Apply franchise tag?'),el('h3',{},r.name),el('p',{},`${r.pos} · Age ${r.age} · ${r.ovr} OVR`),el('div',{class:'retain-tag-price'},el('span',{},'One-year tag'),el('b',{},money(r.tag_price))),el('p',{},'This uses your available tag. The player moves to Extensions, where you can negotiate a long-term deal.')),el('div',{class:'retain-dialog-actions'},cancel,el('button',{class:'btn go',onclick:()=>{dialog.close();act('tag',r.pid);}},'Confirm tag')));
    dialog.addEventListener('close',()=>dialog.remove(),{once:true});document.body.append(dialog);dialog.showModal();cancel.focus();
  };
  for(const r of rows){
    const cells=[el('button',{class:'who',onclick:()=>{location.hash='#club/player/'+r.pid;}},el('div',{class:'no'},r.pos),el('div',{class:'nm'},r.name)),r.pos,r.age,ovrCell(r.ovr)];
    if(rfa){
      cells.push(money(r.tender_price),r.tender?el('div',{class:'retain-pending'},el('b',{},'Tender pending'),el('small',{},'Activates on Advance'),el('button',{class:'btn quiet',disabled:v.open?null:'',onclick:()=>act('no_tender',r.pid)},'Withdraw')):el('button',{class:'btn go',disabled:v.open?null:'',onclick:()=>act('tender',r.pid)},'Tender'));
    }else{
      const can=v.open&&!v.tag_used&&r.can_tag;
      cells.push(el('button',{class:'btn',disabled:can?null:'','data-tip':can?null:v.tag_used?'Your tag has been used.':!v.open?'The tag window is closed.':'Tag limit reached.',onclick:()=>confirmTag(r)},v.tag_used?'Tag used':'Franchise tag'),el('button',{class:'btn go',disabled:r.eligible?null:'',onclick:()=>{pendingExtensionPid=r.pid;location.hash='#personnel/extensions';}},'Extension'));
    }
    body.append(el('tr',{},...cells.map((value,i)=>el('td',{class:cls(i),'data-label':headings[i]},value))));
  }
  if(!rows.length) body.append(el('tr',{},el('td',{colspan:6},el('div',{class:'empty'},v.open?`No ${retainTab.toUpperCase()}s awaiting a retention decision.`:'Retain Players opens during the offseason before free agency.'))));
  table.append(body);board.append(el('div',{class:'retain-table-wrap'},table));
  board.append(el('div',{class:'retain-foot'},rfa?'Chosen tenders activate when Franchise Tag and Re-Sign is advanced. Matching rights remain active through the offer-sheet window.':'Franchise-tag costs appear before confirmation. Extension opens the existing contract negotiation.'));
  if(rfa&&v.erfa.length)board.append(el('div',{class:'retain-foot'},`${v.erfa.length} exclusive-rights player${v.erfa.length===1?'':'s'} will be retained automatically at the minimum when affordable.`));
  page.append(board);
}

function renderExtensions(v) {
  renderRail(v.rail); const page = persPage(); persSecond('extensions');
  const reload = () => renderExtensions(pyJSON(`SESSION.personnel('extensions')`));
  const left = el('section', { class: 'sheet c7' }, el('h2', {}, 'Extensions', el('small', {}, 'Review current and future cap commitments')));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' });
  for (const [k, label, list] of [['expiring', 'Expiring', v.expiring], ['two_left', 'Two Years Left', v.two_left], ['done', 'Done This Year', v.done]]) tabs.append(el('button', { 'aria-pressed': String(extTab === k), onclick: () => { extTab = k; renderExtensions(v); } }, label + ' ', el('em', {}, list.length)));
  left.append(tabs);
  const rows = v[extTab] || [];
  const completed=extTab==='done';
  const tbl = el('table', { class: 'tbl' });
  if(completed){
    tbl.append(el('tr',{},...['Player','Pos','Decision','Term','Annual Value',''].map(label=>el('th',{},label))));
    for(const [i,r] of rows.entries()){
      const deal=completedExtensionTerms(r);
      tbl.append(el('tr',{},el('td',{},el('button',{class:'who','data-pid':r.pid,'data-source-index':i,onclick:()=>{location.hash='#club/player/'+r.pid;}},el('div',{class:'no'},r.pos),el('div',{class:'nm'},r.name))),el('td',{},r.pos),el('td',{},deal.outcome),el('td',{},deal.term),el('td',{class:'n'},deal.annual),el('td',{class:'acts'})));
    }
  }else{
  tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', {}, 'Morale'), el('th', { class: 'n' }, 'Cap Hit'), el('th', {}, 'Ask'), el('th', {}, 'Talks'), el('th', {}, '')));
  for (const r of rows) tbl.append(el('tr', {}, el('td', {}, el('button', { class: 'who', 'data-pid':r.pid, onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos} · ${r.tag_line || ''}${r.fa_class ? ' · ' + r.fa_class : ''}`)))), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', {}, pill(r.morale)), el('td', { class: 'n' }, `$${r.hit.toFixed(1)}m`), el('td', {}, r.ask_word), el('td', { class: 'talks' }, r.talks_word),
    el('td', { class: 'acts' }, r.thread ? el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', onclick: () => { const th = v.threads.find(t => t.id === r.thread); if (th) openTalks(th, reload); } }, 'Open Talks') : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', disabled: r.eligible ? null : '', onclick: () => { const res = pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind='extension')`); if (!res.ok) { notify(res); reload(); return; } const fresh = pyJSON(`SESSION.personnel('extensions')`); const th = fresh.threads.find(t => t.id === res.thread) || fresh.threads.filter(t => t.pid === r.pid).pop(); renderExtensions(fresh); if (th) openTalks(th, reload); } }, 'Ask the Agent'))));
  }
  if (!rows.length) tbl.append(el('tr', {}, el('td', { colspan: completed ? '6' : '9' }, el('div', { class: 'empty' }, completed ? 'No completed decisions this year.' : 'Nobody here.'))));
  left.append(tbl);
  const foot = el('div', { class: 'foot' });
  foot.append(el('a', { class: 'btn', href: '#frontoffice/cap' }, 'Restructure Instead'));
  if (v.tag && v.tag.tagged && !v.tag.open) foot.append(el('span', { class: 'count' }, `Franchise tag placed on ${v.tag.tagged}`));
  else if (v.tag && v.tag.none && !v.tag.open) foot.append(el('span', { class: 'count' }, 'No tag this year'));
  left.append(foot);
  left.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Promises', el('small', {}, 'What You Have Told Your Players')));
  const pt = el('table', { class: 'tbl' }); pt.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Promise'), el('th', {}, 'Made'), el('th', {}, 'Checked'), el('th', {}, 'Status')));
  for (const p of v.promises) pt.append(el('tr', {}, el('td', {}, p.name), el('td', {}, (v.promise_kinds && v.promise_kinds[p.kind]) || p.kind.replace(/_/g, ' ')), el('td', {}, p.made), el('td', {}, p.checked || (p.kind === 'starting_role' ? 'Week 4' : p.kind === 'extension_by' ? 'Offseason' : 'Ongoing')), el('td', {}, el('span', { class: 'pill ' + (p.status === 'kept' ? 'happy' : p.status === 'broken' ? 'unhappy' : 'content') }, p.status.charAt(0).toUpperCase() + p.status.slice(1)))));
  if (!v.promises.length) pt.append(el('tr', {}, el('td', { colspan: '5' }, el('div', { class: 'empty' }, 'None made.'))));
  left.append(pt);
  page.append(left);
  const right = el('section', { class: 'sheet c5' }, el('h2', {}, completed ? 'Completed Deal' : 'Negotiation', el('small', {}, completed ? 'This year' : `${v.threads.length} open`)));
  if(!completed){
  { const live_ = ['open', 'waiting', 'countered', 'match_requested']; const ths = [...v.threads].sort((a, b) => (live_.includes(b.state) ? 1 : 0) - (live_.includes(a.state) ? 1 : 0) || b.id - a.id); for (const t of ths) right.append(talkLine(t, reload)); }
  if (!v.threads.length) right.append(el('div', { class: 'empty' }, 'Ask an agent to hear his number. Offers are answered in one to three weeks by situation.'));
  }
  page.append(right);
  finishPersonnel(page, v, 'extensions', left, right);
  if(pendingExtensionPid){
    const pid=pendingExtensionPid;pendingExtensionPid=null;
    const result=pyJSON(`SESSION.personnel_act('open_talks',pid=${JSON.stringify(pid)},kind='extension')`);
    if(!result.ok){notify(result);return;}
    const fresh=pyJSON("SESSION.personnel('extensions')");
    const thread=fresh.threads.find(t=>t.id===result.thread)||fresh.threads.filter(t=>t.pid===pid).pop();
    renderExtensions(fresh);if(thread)openTalks(thread,reload);else notify(result);
  }
}
let extTab = 'expiring';

// ---------------------------------------------------------------- Front Office
const FO = { owner: 'Owner', review: 'Season Review', exit: 'Exit Meetings', identity: 'Identity', staff: 'Staff', cap: 'Cap' };
function foSecond(cur) { secondRow(Object.entries(FO).map(([k, l]) => [l, '#frontoffice/' + k]), '#frontoffice/' + cur); $('#crumb').textContent = 'Front Office'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'frontoffice')); }

function foBoard(v, title, metrics = []) {
  const board = reportBoard(v.rail.club, title, metrics);
  board.querySelector('h1')?.setAttribute('tabindex', '-1');
  board.classList.add('fo-board');
  return board;
}
function foYears(v, change) {
  const pick = el('select', {class:'btn', 'aria-label':'Season', onchange:e=>change(+e.target.value)});
  for (const year of v.years || [v.year]) pick.append(el('option', {value:year, selected:+year === +v.year ? '' : null}, String(year)));
  return pick;
}
function renderOwner(v) {
  renderRail(v.rail); const page=persPage(); foSecond('owner');
  const s=foBoard(v,'OWNER',[[v.job,'Job security']]);
  const left=el('div',{},el('div',{class:'fo-owner-name'},v.owner?.name || 'Owner',el('span',{class:'fo-status'},v.mood)));
  const facts=el('div',{class:'fo-summary'});
  for(const [value,label] of [[v.expects,'This year'],[v.draft_word,'Draft approach'],[`${Math.round(v.expected_pct*100)}%`,'Target win rate']]) facts.append(el('div',{},el('b',{},value),el('span',{},label)));
  left.append(facts,el('div',{class:'h5'},'SEASON EXPECTATION'),el('div',{class:'fo-summary'},el('div',{},el('b',{},v.prev_pct == null ? '—' : `${Math.round(v.prev_pct*100)}%`),el('span',{},'Last season')),el('div',{},el('b',{},v.drought ? `${v.drought} years` : 'None'),el('span',{},'Playoff drought'))));
  const right=el('div',{},el('div',{class:'h5'},'OWNER PRIORITIES'));
  for(const [key,label] of [['wins','Winning Now'],['young','Building Young'],['stars','Big Names'],['spend','Staff Spending']]) right.append(el('div',{class:'fo-weight'},el('span',{},label),el('div',{class:'bar'},el('i',{style:`width:${Math.max(0,Math.min(100,v.weights[key]*100))}%`}))));
  s.append(el('div',{class:'fo-owner-grid'},left,right),el('div',{class:'h5'},'STAFF BUDGET'));
  const budget=el('div',{class:'fo-summary'});
  for(const [value,label] of [[v.staff_budget.total,'Total budget'],[v.staff_budget.payroll,'Current payroll'],[v.staff_budget.available,'Available']]) budget.append(el('div',{},el('b',{},`$${value}m`),el('span',{},label)));
  s.append(budget,el('div',{class:'bar fo-budget'},el('i',{style:`width:${Math.max(0,Math.min(100,v.staff_budget.payroll/Math.max(1,v.staff_budget.total)*100))}%`})),el('p',{class:'count'},'Payroll includes the head coach.'),el('div',{class:'h5'},'SEASON REVIEWS'));
  for(const x of v.reviews) s.append(el('div',{class:'fo-history'},el('b',{},x.year),el('span',{},`${x.record || ''} · ${x.line || ''}`)));
  if(!v.reviews.length) s.append(el('p',{class:'count'},'Reviews appear after each season.'));
  s.append(el('a',{class:'btn fo-review-link',href:'#frontoffice/review'},'View Season Review')); page.append(s);
}

let idPreview = null, restructureFor = null;
function renderIdentity(v) {
  renderRail(v.rail); const page = persPage(); foSecond('identity');
  const reload = () => renderIdentity(pyJSON(`SESSION.frontoffice('identity'${idPreview ? ', preview=' + JSON.stringify(idPreview) : ''})`));
  const pv = v.preview;
  const s = foBoard(v, 'COACHING IDENTITY', [[v.identity.offense, 'Offense'], [v.identity.defense, 'Defense']]);
  // the archetypes, one row a side, centered; current marked, preview marked
  for (const side of ['offense', 'defense']) {
    s.append(el('div', {class:'h5'}, side === 'offense' ? 'OFFENSIVE IDENTITY' : 'DEFENSIVE IDENTITY'));
    const row = el('div', { class: 'arch center' });
    for (const a of v.archetypes.filter(x => x.side === side)) {
      const cls = (a.current ? 'now' : '') + (pv && pv.key === a.key ? ' preview' : '');
      row.append(el('button', { type:'button', class: cls, 'data-tip': a.words, onclick: () => { idPreview = a.current ? null : a.key; reload(); } }, a.name, el('small', {}, a.current ? `Your ${side}` : side)));
    }
    s.append(row);
  }
  if (pv) s.append(el('div', { class: 'confirm' }, el('span', {}, el('b', { class: 'pill' }, 'Previewing'), ` ${pv.name} on ${pv.side}. Nothing changes until you apply.`), el('div', { style: 'display:flex;gap:6px' }, el('button', { class: 'btn go', onclick: () => { const r = pyJSON(`SESSION.frontoffice_act('apply_identity', key=${JSON.stringify(pv.key)})`); notify({ ok: r.ok, line: r.ok ? `${r.name} is your identity now.` : r.why }); idPreview = null; reload(); } }, 'Apply Identity Change'), el('button', { class: 'btn quiet', onclick: () => { idPreview = null; reload(); } }, 'Discard'))));
  // roster fit by position and the leans
  const grid = el('div', { class: 'fitgrid' });
  const fitRows = pv ? pv.fit : v.fit;
  const fp = el('div', {}, el('div', { class: 'h5' }, 'Roster Fit by Position', el('span', {}, 'Scheme Grade Against ' + (pv ? pv.name : 'Your Identity'))));
  fitRows.forEach((r, i) => { const before = v.fit[i]; const moved = pv && Math.abs(r.fit - before.fit) >= 0.05; const col = r.fit > 0.05 ? 'var(--ok)' : r.fit < -0.05 ? 'var(--danger)' : 'var(--ink-3)'; fp.append(el('div', { class: 'fitrow' }, el('span', {}, r.group), el('div', { class: 't' }, el('i', { class: r.pct >= 75 ? '' : r.pct >= 50 ? 'mid' : 'low', style: `width:${r.pct}%` })), el('span', { class: 'v', style: `color:${col}`, 'data-tip': moved ? `${before.fit > 0 ? '+' : ''}${before.fit.toFixed(1)} now` : null }, (r.fit > 0 ? '+' : '') + r.fit.toFixed(1) + (moved ? (r.fit > before.fit ? ' ▲' : ' ▼') : '')))); });
  grid.append(fp);
  const ld = el('div', {}, el('div', { class: 'h5' }, 'Leans', el('span', {}, "Grey Is Every Scheme's Range · White Is This Scheme's Range · The Dot Is Where Your Scheme Sits")));
  for (const ln of (pv ? pv.leans : v.leans)) ld.append(el('div', { class: 'srow' }, el('span', { class: 'l' }, ln.label), el('div', { class: 'tr' }, el('div', { class: 'rail-line' }), el('div', { class: 'all', style: `left:${ln.all_lo}%;right:${100 - ln.all_hi}%` }), el('div', { class: 'band', style: `left:${ln.band_lo}%;right:${100 - ln.band_hi}%` }), el('div', { class: 'dot', style: `left:${ln.dot}%` })), el('span', { class: 'v' }, ln.value)));
  grid.append(ld); s.append(grid);
  // misfits and the assistants
  s.append(el('div', { class: 'h5', style: 'padding:10px 14px 4px' }, 'Misfits', el('span', {}, 'Players Who Grade Better Elsewhere')));
  const mis = pv ? pv.misfits : v.misfits; const mbox = el('div', { class: 'pad', style: 'padding-top:0' });
  for (const m of mis) mbox.append(el('div', { class: 'plate', style: 'margin-bottom:4px' }, el('div', { class: 'no' }, m.pos), el('div', { class: 'nm', style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + m.pid; } }, m.name, el('small', {}, `${m.pos} · Fit ${m.fit.toFixed(1)} · ${m.reason}`)), el('div', { class: 'ov' }, m.ovr)));
  if (!mis.length) mbox.append(el('div', { class: 'empty' }, 'Nobody grades badly in this identity.'));
  s.append(mbox);
  s.append(el('div', { class: 'read', style: 'margin:0 14px 12px' }, el('b', {}, 'Assistants: '), el('span', {}, pv ? pv.say : v.say)));
  s.append(el('div', { class: 'foot' }, el('button', { class: 'btn quiet', onclick: () => { const h = document.getElementById('idhist'); h.hidden = !h.hidden; } }, 'Identity History')));
  const h = el('div', { class: 'histlist', id: 'idhist', hidden: '', style: 'margin:0 14px 14px' }); for (const x of v.history.slice().reverse()) h.append(el('div', {}, el('time', {}, `${x.year} W${x.week ?? 0}`), el('span', {}, x.change))); if (!v.history.length) h.append(el('div', {}, el('time', {}, '—'), el('span', {}, 'The identity you inherited.')));
  s.append(h); page.append(s);
}

// the staff's trait chips: want traits gold, coaching traits green, a scout's strengths green and blind spots red, unknown gray
function staffTraits(c) {
  const box = el('div', { class: 'traits fo-staff-traits' });
  if (!c.traits || !c.traits.length) { box.append(el('span', { class: 'trait even' }, 'None')); return box; }
  for (const t of c.traits) box.append(el('span', { class: 'trait ' + ({ want: 'money', coach: 'work', pos: 'work', neg: 'unhappy-t', unknown: 'unknown' }[t.fam] || 'even'), 'data-tip': t.tip, tabindex: '0' }, t.name));
  return box;
}

// STAFF: an offer is submitted only from the dialog, using the existing engine actions.
function openStaffTalk(c, v, mode, reload) {
  const owned = mode === 'extend';
  let state = null;
  if (!owned) {
    const r = pyJSON(`SESSION.frontoffice_act('staff_interview', name=${JSON.stringify(c.name)})`);
    if (!r.ok) { notify(r); return; }
    state = r.state;
  }
  hideTip();
  const dialog = el('dialog', {class:'sheet negotiation-sheet fo-coach-dialog', 'aria-labelledby':'fo-coach-title'});
  applyTeamTheme(dialog, v.rail.club);
  const palette = teamTheme(v.rail.club);
  dialog.style.setProperty('--club', palette.base);
  dialog.style.setProperty('--club-2', palette.accent);
  const close = () => dialog.close();
  const closeButton = el('button', {class:'btn quiet neg-close', onclick:close}, 'Close');
  dialog.append(el('div', {class:'neg-topbar'}, el('div', {class:'neg-identity'},
    el('div', {class:'neg-avatar'}, c.role_key.toUpperCase()),
    el('div', {class:'neg-title'}, el('div', {class:'neg-kicker'}, owned ? 'STAFF EXTENSION' : 'STAFF INTERVIEW'),
      el('h2', {id:'fo-coach-title'}, c.name), el('small', {}, `${c.role} · ${c.specialty || 'Generalist'} · Age ${c.age}`)), closeButton)));
  const body = el('div', {class:'fo-coach-body'}); dialog.append(body);
  const years = el('input', {type:'number',min:'1',max:'5',step:'1',value:String(owned ? Math.max(3,c.years) : 3)});
  const salary = el('input', {type:'number',min:'0.01',step:'0.01',value:String(c.extend_ask || c.ask)});
  const response = el('div', {class:'read', role:'status', 'aria-live':'polite'});
  const draw = () => {
    body.replaceChildren();
    const ask = owned ? +c.extend_ask : +state.ask;
    const room = owned ? +c.offer_room : +(v.budget.offer_room ?? v.budget.available);
    const incumbent = v.cards.find(x => x.role_key === c.role_key && !x.empty);
    const unavailable = !owned && (!v.offseason ? 'Hiring opens in the offseason.' : incumbent ? `The ${c.role} job is filled by ${incumbent.name}. Release the incumbent from Current Staff before offering this job.` : ask > room+1e-9 ? 'His asking salary exceeds the available staff budget.' : '');
    body.append(el('div', {class:'fo-coach-summary'},
      el('div', {}, el('small', {}, 'RATING'), el('b', {}, c.rating)),
      el('div', {}, el('small', {}, 'PRESTIGE'), el('b', {}, c.prestige)),
      el('div', {}, el('small', {}, 'ANNUAL ASK'), el('b', {}, `$${ask.toFixed(2)}m`)),
      el('div', {}, el('small', {}, 'BUDGET FOR THIS JOB'), el('b', {}, `$${room.toFixed(2)}m`))));
    if (owned) body.append(el('p', {class:'count'}, `Current deal: $${(+c.salary).toFixed(2)}m per year · ${c.years} years remaining. A new offer replaces the remaining term.`));
    body.append(staffTraits(owned ? c : {traits:state.traits}));
    if (!owned) {
      const log = el('div', {class:'thread negotiation-thread fo-interview-log', 'aria-live':'polite'});
      for (const m of state.log) log.append(el('div', {class:'msg'+(m.who==='gm'?' you':'')}, el('div', {class:'from'}, m.who==='gm'?'You':c.name), el('div', {class:'txt'}, m.text)));
      body.append(log);
      const questions = c.role_key==='scout' ? [['hits','Ask about strengths'],['misses','Ask about blind spots'],['references','Ask for references']] : [['coaching','Ask about coaching'],['situation','Ask about his priorities'],['references','Ask for references']];
      const actions = el('div', {class:'acts'});
      for (const [key,label] of questions) actions.append(el('button', {class:'btn', disabled:state.asked.includes(key)?'':null, onclick:() => {
        const r = pyJSON(`SESSION.frontoffice_act('staff_interview', name=${JSON.stringify(c.name)}, question=${JSON.stringify(key)})`);
        if (!r.ok) { response.textContent=r.why || 'Unable to ask that question.'; return; }
        state=r.state; draw();
      }}, state.asked.includes(key) ? key==='references' && state.refs_due ? 'References pending' : 'Asked' : label));
      body.append(actions, el('p', {class:'count'}, state.all_known ? 'All traits revealed.' : `${state.n_hidden} trait${state.n_hidden===1?'':'s'} still unknown.${state.refs_due ? ' References return after advancing.' : ''}`));
    }
    const form = el('form', {class:'offer-panel fo-coach-offer', onsubmit:e => {
      e.preventDefault();
      if (unavailable || !form.reportValidity()) return;
      const code = owned ? `SESSION.frontoffice_act('staff_extend', role=${JSON.stringify(c.role_key)}, years=${+years.value}, salary=${+salary.value})` : `SESSION.frontoffice_act('staff_hire', name=${JSON.stringify(c.name)}, years=${+years.value})`;
      const r=pyJSON(code);
      if (r.ok) { notify({ok:true,line:owned ? `${c.name} extended.` : `${c.name} hired.`}); close(); }
      else response.textContent=r.why || 'The offer was declined.';
    }});
    years.required=true; salary.required=true;
    form.append(el('div', {class:'offer'}, el('label', {}, 'Contract years', years),
      owned ? el('label', {}, 'Annual salary ($m)', salary) : el('div', {class:'fo-coach-ask'}, `Offer at his ask: $${ask.toFixed(2)}m per year`)));
    if (unavailable) form.append(el('p', {class:'count'}, unavailable));
    form.append(response, el('div', {class:'acts'}, el('button', {class:'btn go',type:'submit',disabled:unavailable?'':null}, owned ? 'Submit Extension' : 'Offer Contract'), el('button', {class:'btn quiet',type:'button',onclick:close}, owned ? 'Cancel' : 'Leave Interview')));
    body.append(form);
  };
  dialog.addEventListener('close', () => { hideTip(); dialog.remove(); reload(); document.querySelector('.fo-board h1')?.focus(); });
  draw(); document.body.append(dialog); dialog.showModal(); closeButton.focus();
}

let foStaffRole = 'oc';
function renderStaff(v) {
  renderRail(v.rail); const page = persPage(); foSecond('staff');
  const reload = () => renderStaff(pyJSON(`SESSION.frontoffice('staff')`));
  const s = foBoard(v, 'STAFF', [[`$${v.budget.total}m`, 'Budget'], [`$${v.budget.payroll}m`, 'Payroll'], [`$${v.budget.available}m`, 'Available']]);
  s.append(el('p', {class:'count'}, `Payroll includes head coach $${v.budget.head_coach?.salary || 0}m`), el('div', {class:'h5'}, 'CURRENT STAFF'));
  const grid = el('div', { class: 'staffgrid', style: 'grid-template-columns:repeat(4,1fr)' });
  for (const c of v.cards) {
    if (c.empty) { grid.append(el('div', { class: 'scard open' }, `${c.role_name} · open. Hire from the pool below.`)); continue; }
    const card = el('div', { class: 'scard' }, el('div', { class: 'role' }, c.role + (c.hc_candidate ? ' · Head-Coaching Candidate' : '') + (c.disgruntled ? ' · Disgruntled' : '')), el('div', { class: 'nm' }, c.name),
      el('div', { class: 'kv' }, el('span', {}, 'Rating'), el('b', {}, c.rating), el('span', {}, 'Prestige'), el('b', {}, c.prestige), el('span', {}, 'Specialty'), el('span', {}, c.specialty || '—'), el('span', {}, 'Age'), el('span', {}, c.age), el('span', {}, 'Contract'), el('span', {}, `$${(+c.salary).toFixed(1)}m · Expires ${v.rail.year + c.years}`), el('span', {}, 'Asks'), el('span', {}, `$${(+c.extend_ask).toFixed(1)}m`), el('span', {}, `${c.role.replace(' Coordinator', '')} Rank`), el('span', {}, (c.unit_ranks || []).length ? c.unit_ranks.map(r => `${r}${ord(r)}`).join(' · ') : '—'), el('span', {}, 'Traits'), staffTraits(c)));
    const acts = el('div', { class: 'acts' });
    acts.append(el('button', { class: 'btn', onclick: () => openStaffTalk(c, v, 'extend', reload) }, 'Extend'));
    if (v.offseason) acts.append(el('button', { class: 'btn warn', onclick: () => { if (confirm(`Release ${c.name} from your staff?`)) { notify(pyJSON(`SESSION.frontoffice_act('staff_release', role=${JSON.stringify(c.role_key)})`)); reload(); } } }, 'Release'));
    card.append(acts); grid.append(card);
  }
  s.append(grid);
  // a club wants your coordinator: the conversation
  for (const p of v.poaches) {
    const box = el('div', { class: 'thread', style: 'margin:0 14px 12px;border:1px solid var(--rule)' }, el('div', { class: 'h5', style: 'padding:8px 12px 0' }, 'A Team Wants Your Coordinator', el('span', {}, `${p.to_club.name} · Head Coach`)));
    box.append(el('div', { class: 'msg' }, el('div', { class: 'from' }, `${p.coach} · ${p.role_name}`), el('div', { class: 'txt' }, p.opening)));
    box.append(el('div', { class: 'msg you' }, el('div', { class: 'from' }, 'You'), el('div', { class: 'txt' }, 'You are a big part of what we have built here. What would it take to keep you?')));
    box.append(el('div', { class: 'msg note' }, p.read));
    const yrs = el('input', { type: 'number', min: '1', max: '4', value: '2' }), per = el('input', { type: 'number', step: '0.1', min: String(p.salary), value: String(Math.min(p.hc_pay, Math.max(p.salary, p.room_without)).toFixed(1)) });
    box.append(el('div', { class: 'msg you' }, el('div', { class: 'from' }, 'Keep Him'), el('div', { class: 'offer' }, el('label', {}, 'New Years', yrs), el('label', {}, 'Per Year ($m)', per)),
      el('div', { class: 'txt', style: 'color:var(--ink-3);font-size:14px' }, `He is paid $${p.salary.toFixed(1)}m. A head-coaching job would pay him about $${p.hc_pay.toFixed(1)}m. Available without him: $${p.room_without.toFixed(1)}m.`),
      el('div', { class: 'acts' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.frontoffice_act('poach', tid=${p.id}, action='persuade', raise_years=${+yrs.value}, raise_to=${+per.value})`)); reload(); } }, 'Offer and Ask Again'),
        el('button', { class: 'btn', onclick: () => { notify(pyJSON(`SESSION.frontoffice_act('poach', tid=${p.id}, action='let_go')`)); reload(); } }, 'Let Him Go'),
        el('button', { class: 'btn warn', onclick: () => { notify(pyJSON(`SESSION.frontoffice_act('poach', tid=${p.id}, action='block')`)); reload(); } }, 'Block the Move'))));
    box.append(el('div', { class: 'msg note' }, el('b', {}, 'If you block him: '), p.block_read));
    s.append(box);
  }
  s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'The Pool', el('small', {}, v.offseason ? 'Interview Candidates · Hire Into an Open Job' : 'hiring reopens after the season')));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); const list = el('div', { class: 'pad' }); let role = foStaffRole;
  const draw = () => { list.innerHTML = ''; const grid2 = el('div', { class: 'staffgrid', style: 'grid-template-columns:repeat(4,1fr);padding:0' });
    for (const c of v.pools[role]) { const card = el('div', { class: 'scard' }, el('div', { class: 'nm' }, c.name), el('div', { class: 'role', style: 'text-transform:none;letter-spacing:0' }, c.background), el('div', { class: 'kv' }, el('span', {}, 'Rating'), el('b', {}, c.rating), el('span', {}, 'Prestige'), el('b', {}, c.prestige), el('span', {}, 'Age'), el('span', {}, c.age), el('span', {}, 'Asks'), el('span', {}, `$${(+c.ask).toFixed(1)}m`), el('span', {}, 'Traits'), staffTraits(c)),
        el('div', { class: 'acts' }, el('button', { class: 'btn go', onclick: () => openStaffTalk(c, v, 'interview', reload) }, 'Interview')));
      grid2.append(card); }
    list.append(grid2); };
  for (const [k, l] of [['oc', 'Offensive Coordinators'], ['dc', 'Defensive Coordinators'], ['st', 'Special Teams'], ['scout', 'Head Scouts']]) tabs.append(el('button', { 'aria-pressed': String(role === k), onclick: e => { role = k; foStaffRole = k; tabs.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); draw(); } }, l));
  s.append(tabs, list); draw(); page.append(s);
}

function renderCap(v) {
  renderRail(v.rail); const page = persPage(); foSecond('cap');
  const reload = () => renderCap(pyJSON(`SESSION.frontoffice('cap')`));
  const s = foBoard(v, 'SALARY CAP', [[`$${v.cap_space}m`, 'Available'], [`$${v.years[0].limit}m`, 'Limit']]);
  if(v.top51) s.append(el('p',{class:'count'},'Top 51 applies in the offseason.'));
  const yrs = el('div', { class: 'capyears' });
  const COL = { QB: '#c8102e', RB: '#4cc9f0', WR: '#ffb612', TE: '#3fb37f', OL: '#5aa9d6', DL: '#e5484d', LB: '#a78bfa', DB: '#f59e0b', ST: '#7b8593' };
  v.years.forEach((y, i) => {
    const st = el('div', { class: 'stack' }); for (const [g, val] of Object.entries(y.by)) if (val > 0) st.append(el('i', { style: `width:${(val / y.limit * 100).toFixed(1)}%;background:${COL[g]}`, 'data-tip': `${g} $${val}m` })); if (y.dead > 0) st.append(el('i', { style: `width:${(y.dead / y.limit * 100).toFixed(1)}%;background:#3a424c`, 'data-tip': `Penalty $${y.dead}m` }));
    const kv = el('div', { class: 'kv' }, el('span', {}, 'Committed'), el('span', {}, `$${y.committed}m`), el('span', {}, 'Penalty'), el('span', {}, `$${y.dead}m`));
    if (y.current) kv.append(el('span', {}, 'Paid to Departed Players'), el('span', {}, `$${y.earned || 0}m`), el('span', {}, 'Rookie Pool'), el('span', {}, '—'));
    else kv.append(el('span', {}, 'Expiring Into It'), el('span', {}, y.expiring_into.length ? y.expiring_into.join(', ') + (y.expiring_more ? `, ${y.expiring_more} more` : '') : 'Nobody'), el('span', {}, 'Rookie Pool'), el('span', {}, `$${y.rookie_pool}m est.`));
    kv.append(el('span', {}, 'Under Contract'), el('span', {}, `${y.under_contract} players`));
    yrs.append(el('div', { class: 'cy' }, el('h4', {}, `${y.year}${i === 0 ? ' Now' : ''}`, el('small', { 'data-tip': y.rollover ? `League cap plus $${y.rollover}m you have unspent now, which carries over` : null }, `Limit $${y.limit}m${y.rollover ? ` incl. $${y.rollover}m rollover` : y.est ? ' est.' : ''}`)), el('div', { class: 'big' + (y.space < 0 ? ' neg' : '') }, `${y.space < 0 ? '−' : ''}$${Math.abs(y.space).toFixed(1)}m`), el('div', { style: 'font-size:12.5px;color:var(--ink-3)' }, 'space'), st, kv));
  });
  s.append(yrs);
  const two = el('div', { class: 'restr' });
  const pvBox = el('div', {}, el('div', { class: 'h5' }, 'Restructure', el('span', {}, 'Convert Base to Bonus · Preview Before You Commit')), el('div', { class: 'read', id: 'pv' }, 'Pick a player from the ledger to see what converting base salary into signing bonus does to the books.'));
  const openPreview = r => {
    const p = pyJSON(`SESSION.frontoffice_act('restructure_preview', pid=${JSON.stringify(r.pid)})`); const box = $('#pv'); box.innerHTML = '';
    if (!p.ok) { box.append(p.why); return; }
    box.append(el('div', { class: 'plate', style: 'margin-bottom:8px' }, el('div', { class: 'no' }, p.player.pos), el('div', { class: 'nm' }, p.player.name, el('small', {}, `${p.player.pos} · $${p.player.hit}m Hit · ${p.player.yrs} Yrs Left`)), el('div', { class: 'ov' }, p.player.ovr)));
    const amt = el('input', { type: 'number', step: '0.5', min: '0.5', max: String(p.max_convert), value: String(p.convert) }), voids = el('input', { type: 'number', min: '0', max: '2', value: String(p.void_years || 0) });
    const delta = el('div', { class: 'delta' }); const say = el('div', { class: 'read', style: 'margin-top:8px' });
    const drawD = q => { delta.innerHTML = ''; const yr = q.cap_year || v.years[0].year; const later = q.added_later || []; delta.append(el('div', {}, el('div', { class: 'l' }, `Saved ${yr}`), el('div', { class: 'v good' }, `$${q.saves_now}m`)), el('div', {}, el('div', { class: 'l' }, `Added ${yr + 1}`), el('div', { class: 'v bad' }, later.length ? `$${later[0].toFixed(1)}m` : '—')), el('div', {}, el('div', { class: 'l' }, later.length > 1 ? `Added ${yr + 2}–${yr + later.length}` : 'Added later'), el('div', { class: 'v bad' }, later.length > 1 ? `$${later.slice(1).reduce((a, b) => a + b, 0).toFixed(1)}m` : '—')), el('div', {}, el('div', { class: 'l' }, `Penalty if Cut '${String(yr + 1).slice(2)}`), el('div', { class: 'v' }, `$${q.dead_if_cut_next_year}m`))); say.innerHTML = ''; say.append(el('b', {}, 'Assistants: '), q.say || ''); };
    const re = () => { const q = pyJSON(`SESSION.frontoffice_act('restructure_preview', pid=${JSON.stringify(r.pid)}, amount=${+amt.value}, void_years=${+voids.value})`); if (q.ok) drawD(q); };
    amt.onchange = re; voids.onchange = re;
    box.append(el('div', { class: 'offer' }, el('label', {}, 'Base to Convert ($m)', amt), el('label', {}, 'Void Years (0–2)', voids)), delta, say,
      el('div', { style: 'display:flex;gap:6px;margin-top:10px' }, el('button', { class: 'btn go', onclick: () => { const q = pyJSON(`SESSION.frontoffice_act('restructure', pid=${JSON.stringify(r.pid)}, amount=${+amt.value}, void_years=${+voids.value})`); notify({ ok: q.ok, line: q.ok ? `Restructured. Saves $${q.saves_now}m in ${q.cap_year}.` : q.why }); reload(); } }, 'Restructure'), el('button', { class: 'btn quiet', onclick: () => { box.innerHTML = ''; box.append('Pick a player from the ledger.'); } }, 'Pick Another Contract')));
    drawD(p);
  };
  // tags and tools
  pvBox.append(el('div', { class: 'h5', style: 'margin-top:14px' }, 'Tags and Tools', el('span', {}, `${v.tag_year} Offseason`)));
  const tt = el('div', { class: 'kv' });
  for (const t of v.tags) tt.append(el('span', {}, `Franchise Tag · ${t.pos}`), el('span', {}, `$${t.price}m · `, el('span', { style: 'cursor:pointer;text-decoration:underline dotted', onclick: () => { location.hash = '#club/player/' + t.pid; } }, surname(t.name))));
  if (!v.tags.length) tt.append(el('span', {}, 'Franchise Tag'), el('span', {}, 'No unrestricted free agent to tag next offseason'));
  tt.append(el('span', {}, 'Void Years Carried'), el('span', {}, v.void_carried ? `$${v.void_carried}m accelerating when the deals void` : 'None'), el('span', {}, 'Cuts and Trades'), el('span', { style: 'color:var(--ink-3)' }, v.june1_rule));
  pvBox.append(tt);
  pvBox.append(el('div', { class: 'h5', style: 'margin-top:14px' }, 'Largest Hits', el('span', {}, String(v.years[0].year))));
  for (const r of v.largest) pvBox.append(el('div', { class: 'fitrow', style: 'grid-template-columns:1fr 1fr 60px' }, el('span', { style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + r.pid; } }, `${r.name} · ${r.pos}`), el('div', { class: 'bar', style: 'height:8px' }, el('i', { style: `width:${Math.min(100, r.share * 4)}%;background:var(--club)` })), el('span', { class: 'v' }, `$${r.hit.toFixed(1)}m`)));
  pvBox.append(el('div', { class: 'h5', style: 'margin-top:14px' }, 'Penalty Detail', el('span', {}, `$${v.dead_total}m in ${v.years[0].year} · $${v.dead_next}m in ${v.years[1].year}`)));
  if (v.dead_rows.length) { const dt = el('table', { class: 'stab' }); dt.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'How'), el('th', {}, String(v.years[0].year)), el('th', {}, String(v.years[1].year)))); for (const r of v.dead_rows) dt.append(el('tr', {}, el('td', {}, `${r.name} · ${r.pos}`), el('td', {}, r.how + (r.week ? ` wk ${r.week}` : '')), el('td', {}, `$${r.dead.toFixed(1)}m`), el('td', {}, r.dead_next ? `$${r.dead_next.toFixed(1)}m` : '—'))); pvBox.append(dt); }
  else pvBox.append(el('div', { class: 'empty' }, v.dead_total ? 'Charges carried in from before this season.' : 'No penalty on the books.'));
  const ledger = el('div', {}, el('div', { class: 'h5' }, 'Ledger'));
  const tbl = el('table', { class: 'tbl' }); tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), ...v.years.map(y => el('th', { class: 'n' }, String(y.year))), el('th', { class: 'n', 'data-tip': `Charge in ${v.years[0].year} if released now` }, 'Penalty'), el('th', { class: 'n' }, 'Yrs'), el('th', {}, ''), el('th', {}, '')));
  for (const r of v.rows) tbl.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name))), el('td', {}, r.pos), ...r.hits.map(h => el('td', { class: 'n' }, h == null ? '—' : `$${h.toFixed(1)}m`)), el('td', { class: 'n' }, `$${r.penalty.toFixed(1)}m`), el('td', { class: 'n' }, r.yrs), el('td', {}, ...r.tags.map(t => el('span', { class: 'badge-sm', style: 'margin-right:4px' }, t))),
    el('td', {}, r.restructurable > 0.5 ? el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', onclick: () => openPreview(r) }, 'Restructure') : '')));
  ledger.append(el('div',{class:'report-table-scroll'},tbl), el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#personnel/extensions' }, 'Extensions')));
  two.append(ledger, pvBox); s.append(two); page.append(s);
  if (restructureFor) { const r = v.rows.find(x => x.pid === restructureFor); restructureFor = null; if (r) openPreview(r); }
}

// ---------------------------------------------------------------- Draft
const DR = { board: 'Your Board', spring: 'Spring Report', day: 'Draft Day', picks: 'Picks', results: 'Results' };
let boardRound = null, boardHideTaken = false;
let boardPos = 'All', boardFilt = { early: false, late: false, small: false, needs: false }, boardTab = 'class', boardQuery = '', boardSel = null, boardPage = 0, boardSort = 'rank', boardDir = 1;
// THE BOARD'S SORT. Every column but Flags sorts; click a head to sort by it, click again to flip. Numbers sort high
// first, text A to Z, blanks last either way.
const BOARD_KEYS = {
  rank: r => (r.my_rank == null ? null : -r.my_rank), name: r => (r.name || '').toLowerCase(), pos: r => r.pos || '', home_state: r => (r.home_state || '').toLowerCase(),
  mine: r => (r.mine == null ? null : +r.mine), scheme: r => (r.scheme_ovr ?? r.mine) == null ? null : +(r.scheme_ovr ?? r.mine),
  ceiling: r => { const m = String(r.ceiling || '').match(/(\d+)\D+(\d+)/); return m ? +m[2] + (+m[1]) / 1000 : null; },
  cons: r => (r.cons == null ? null : +r.cons), gap: r => (r.gap == null ? null : +r.gap),
  proj: r => { const m = String(r.proj_range || '').match(/(\d+)/); return m ? -(+m[1]) : null; },
};
const BOARD_TEXT = new Set(['name', 'pos', 'home_state']);
function boardSortRows(rows) {
  const key = BOARD_KEYS[boardSort] || BOARD_KEYS.rank; const text = BOARD_TEXT.has(boardSort);
  return rows.slice().sort((a, b) => {
    const ka = key(a), kb = key(b);
    if (ka == null && kb == null) return 0; if (ka == null) return 1; if (kb == null) return -1;
    const c = text ? String(ka).localeCompare(String(kb)) : (kb - ka);
    return (c || ((b.mine ?? 0) - (a.mine ?? 0))) * boardDir;
  });
}
function boardHead(label, key, cls, tip, redraw) {
  const on = boardSort === key;
  return el('th', { class: (cls || '') + ' sortable' + (on ? ' on' : ''), 'data-tip': (tip ? tip + '. ' : '') + 'Click to sort' + (on ? ', again to flip' : ''), onclick: () => { if (boardSort === key) boardDir = -boardDir; else { boardSort = key; boardDir = 1; } boardPage = 0; redraw(); } }, label, on ? el('span', { class: 'arrow' }, boardDir === 1 ? ' ▼' : ' ▲') : '');
}
function drSecond(cur) { secondRow(Object.entries(DR).map(([k, l]) => [l, '#draft/' + k]), '#draft/' + cur); $('#crumb').textContent = 'Draft'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'draft')); }
function gapCell(g) { if (g == null) return el('span', { class: 'gap' }, '—'); return el('span', { class: 'gap ' + (g > 0 ? 'up' : g < 0 ? 'dn' : '') }, (g > 0 ? '+' : '') + g); }
function flagTags(fl) { const s = el('span', {}); for (const f of fl || []) { const w = String(f); const key = ({ medical: 'Medical', character: 'Character', visit: 'Visited', visited: 'Visited', riser: 'Riser', faller: 'Faller', 'senior bowl': 'Senior Bowl', 'sr. bowl': 'Senior Bowl', 'small school': 'Small School', underclassman: 'Underclassman', 'pro day': 'Pro Day' })[w.toLowerCase()] || w; s.append(el('span', { class: 'flag ' + (FLAG_CLS[key] || 'ss'), 'data-tip': FLAG_TIPS[key] || null }, key)); } return s; }
const POS_GROUPS = ['All', 'QB', 'HB', 'WR', 'TE', 'OL', 'DL', 'LB', 'DB', 'ST'];
const POS_OF = { QB: ['QB'], HB: ['HB', 'FB'], WR: ['WR'], TE: ['TE'], OL: ['LT', 'LG', 'C', 'RG', 'RT'], DL: ['LEDG', 'DT', 'REDG'], LB: ['MIKE', 'WILL', 'SAM'], DB: ['CB', 'FS', 'SS'], ST: ['K', 'P', 'LS'] };

const NEED_POS = { QB: ['QB'], RB: ['HB', 'FB'], WR: ['WR'], TE: ['TE'], OL: ['LT', 'LG', 'C', 'RG', 'RT'], EDGE: ['LEDG', 'REDG'], DT: ['DT'], LB: ['MIKE', 'WILL', 'SAM'], CB: ['CB'], S: ['FS', 'SS'] };
const FLAG_TIPS = { Visited: 'You met with this player.', 'Senior Bowl': 'Your scouts saw him at the Senior Bowl.', 'Sr. Bowl': 'Your scouts saw him at the Senior Bowl.', 'Pro Day': 'Your scouts attended his pro day.', Medical: 'Durability concerns.', Character: 'Work ethic concerns.', Riser: 'Up fifteen or more spots on the consensus board this Spring.', Faller: 'Down fifteen or more spots on the consensus board this Spring.', 'Small School': 'Less tape on this player.', Underclassman: 'More room to grow.' };
const FLAG_CLS = { Medical: 'med', Character: 'chr', Visited: 'vis', Riser: 'up', Faller: 'dn', 'Sr. Bowl': 'sen', 'Senior Bowl': 'sen', 'Small School': 'small', Underclassman: 'under' };
const wordTag = w => el('span', { class: 'flag ' + (FLAG_CLS[w] || ''), 'data-tip': FLAG_TIPS[w] || null }, w);

function renderBoard(v) {
  renderRail(v.rail); const page = persPage(); drSecond('board');
  page.className = 'draft-page';
  featureHero(page, v.rail.club, `Draft / ${v.year}`, 'THE WAR ROOM', 'Your board, scouting reads, and next move in one place.', [[v.count, 'Prospects'], [v.slot || '—', 'First pick']]);
  const reload = () => renderBoard(pyJSON(`SESSION.draft_view('board')`));
  const onBoard = new Set(v.user_board.order.map(x => x.pid)), dnd = new Set(v.user_board.dnd.map(x => x.pid));
  page.append(el('div', { class: 'draft-intel c12' },
    el('div', {}, el('span', {}, 'TEAM NEEDS'), el('strong', {}, v.needs.slice(0, 4).join(' · ') || 'Best player available')),
    el('div', {}, el('span', {}, 'YOUR BOARD'), el('strong', {}, `${onBoard.size} ranked · ${dnd.size} do not draft`)),
    el('div', {}, el('span', {}, 'SCOUTING'), el('strong', {}, v.scout ? `${v.scout.name} · ${v.scout.rating}` : 'Your scouting room'))));
  const s = el('section', { class: 'sheet c12 draft-surface draft-board' }, el('h2', {}, 'Scouting Board', el('small', {}, 'Visits are locked in at Advance.')));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' });
  const taken = v.rows.filter(r => r.taken).length;
  if (taken) tabs.append(el('label', { class: 'chk', style: 'margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-size:14px;color:var(--ink-2)' }, el('input', { type: 'checkbox', checked: boardHideTaken ? '' : null, onchange: e => { boardHideTaken = e.target.checked; boardPage = 0; draw(); } }), 'Hide drafted'));
  let visitedTabCount = null;
  for (const [k, l, n] of [['class', `Class of ${v.year}`, v.count], ['board', 'Your Board', onBoard.size], ['visited', 'Visited', v.rows.filter(r => r.visited).length]]) {
    const count = el('em', {}, n);
    if (k === 'visited') visitedTabCount = count;
    tabs.append(el('button', { 'aria-pressed': String(boardTab === k), onclick: () => { boardTab = k; renderBoard(v); } }, l + ' ', count));
  }
  s.append(tabs);
  if (boardTab === 'board') { s.append(yourBoard(v, reload)); page.append(s); return; }
  const filt = el('div', { class: 'filt-pos' });
  for (const g of ['All', 'QB', 'OL', 'WR', 'EDGE', 'CB']) filt.append(el('button', { class: 'btn' + (boardPos === g ? ' go' : ''), onclick: () => { boardPos = g; boardPage = 0; renderBoard(v); } }, g));
  filt.append(el('span', { style: 'width:1px;background:var(--rule-2);margin:0 6px' }));
  for (const [k, label, tip] of [['needs', 'Needs', `Your needs: ${v.needs.join(', ') || 'none'}`], ['early', 'Rounds 1–3', 'Consensus in the first 96'], ['late', '4–7', 'Consensus after the first 96'], ['small', 'Small School', 'Outside the power conferences: your read is wider on these players']]) filt.append(el('button', { class: 'btn' + (boardFilt[k] ? ' go' : ''), 'data-tip': tip, onclick: () => { boardFilt[k] = !boardFilt[k]; if (k === 'early' && boardFilt.early) boardFilt.late = false; if (k === 'late' && boardFilt.late) boardFilt.early = false; boardPage = 0; renderBoard(v); } }, label));
  const search = el('input', { type: 'search', class: 'find', placeholder: 'Find a Prospect', value: boardQuery }); search.oninput = () => { boardQuery = search.value; boardPage = 0; draw(); }; filt.append(search);
  const visitText = () => `Visits ${v.visits.length} of ${v.visits_max}` + (v.spring_done ? ' · the spring has run' : ' · Visits must be scheduled by Step 11 in the Offseason.');
  const visitTally = el('span', { class: 'count', style: 'margin-left:auto;align-self:center' }, visitText());
  filt.append(visitTally);
  s.append(filt);
  const pager = el('div', { class: 'tools', style: 'justify-content:center;gap:12px' }); s.append(pager);
  const tbl = el('table', { class: 'tbl' });
  const draw = () => {
    tbl.innerHTML = '';
    const H = (label, key, cls, tip) => boardHead(label, key, cls, tip, draw);
    tbl.append(el('tr', {}, H('#', 'rank', 'n', 'Your board order'), H('Prospect', 'name', '', ''), H('Pos', 'pos', '', ''), H('Home State', 'home_state', '', 'Fictional player background'), H('Estimated Overall', 'mine', 'n', "Your scouts' read. Carries error; a visit tightens it"), H('Scheme Ovr', 'scheme', 'n', "How he grades in your scheme, on your scouts' read; the league's grade does not move"), H('Ceiling', 'ceiling', 'n', 'Where he can grow to. Wide means your scouts are unsure'), H('Consensus', 'cons', 'n', "The league's grade, same scale as yours"), H('Gap', 'gap', 'n', "Yours minus the league's. Positive means the league undervalues him"), H('Proj.', 'proj', 'n', 'Where the league expects him to go'), el('th', {}, 'Flags'), el('th', {}, '')));
    const q = boardQuery.trim().toLowerCase(); const GROUP = { QB: ['QB'], OL: ['LT', 'LG', 'C', 'RG', 'RT'], WR: ['WR', 'TE'], EDGE: ['LEDG', 'REDG', 'DT'], CB: ['CB', 'FS', 'SS'] };
    const needPos = new Set(v.needs.flatMap(g => NEED_POS[g] || []));
    const rows = v.rows.filter(r => (!boardHideTaken || !r.taken) && (boardTab !== 'visited' || r.visited) && (boardPos === 'All' || (GROUP[boardPos] || []).includes(r.pos)) && (!boardFilt.needs || needPos.has(r.pos)) && (!boardFilt.early || (r.cons_rank != null && r.cons_rank <= 96)) && (!boardFilt.late || (r.cons_rank != null && r.cons_rank > 96)) && (!boardFilt.small || r.small) && (!q || r.name.toLowerCase().includes(q) || (r.home_state || '').toLowerCase().includes(q)));
    const sorted = boardSortRows(rows);
    const PAGE = 100, pages = Math.max(1, Math.ceil(rows.length / PAGE)); if (boardPage >= pages) boardPage = pages - 1; if (boardPage < 0) boardPage = 0;
    pager.innerHTML = ''; pager.append(el('button', { class: 'btn', disabled: boardPage === 0 ? '' : null, onclick: () => { boardPage--; draw(); } }, '‹ Prev'), el('span', { class: 'count' }, `${rows.length ? boardPage * PAGE + 1 : 0}–${Math.min(rows.length, (boardPage + 1) * PAGE)} of ${rows.length}`), el('button', { class: 'btn', disabled: boardPage >= pages - 1 ? '' : null, onclick: () => { boardPage++; draw(); } }, 'Next ›'));
    const pageRows = sorted.slice(boardPage * PAGE, (boardPage + 1) * PAGE);
    for (const r of pageRows) tbl.append(el('tr', { class: (r.visited ? 'visited' : '') + (boardSel === r.pid ? ' sel' : ''), style: r.taken ? 'opacity:.4' : '', onclick: e => { if (e.target.closest('button')) return; boardSel = boardSel === r.pid ? null : r.pid; draw(); drawFoot(); } },
      el('td', { class: 'n' }, r.my_rank), el('td', {}, el('button', { class: 'who', onclick: e => { e.stopPropagation(); location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos} · ${r.cls_year}${r.size ? ' · ' + r.size : ''}`)))), el('td', {}, r.pos), el('td', {}, r.home_state), el('td', { class: 'n' }, ovrCell(r.mine), r.visit_move && r.visit_move.mine_from !== r.mine ? el('small', { class: 'count', style: 'display:block;font-size:11px', 'data-tip': `Your read moved from ${r.visit_move.mine_from} to ${r.mine} at the visit` }, `was ${r.visit_move.mine_from}`) : ''), el('td', { class: 'n' }, el('span', {}, r.scheme_ovr ?? r.mine), (r.fit || 0) !== 0 ? el('small', { class: 'fit ' + (r.fit > 0.05 ? 'p' : r.fit < -0.05 ? 'm' : 'z'), style: 'display:block;font-size:11.5px' }, (r.fit > 0 ? '+' : '') + r.fit.toFixed(1)) : ''), el('td', { class: 'n' }, r.ceiling), el('td', { class: 'n' }, r.cons != null ? r.cons : '—'), el('td', { class: 'n' }, gapCell(r.gap)), el('td', { class: 'n' }, r.proj_range), el('td', {}, ...r.words.map(wordTag)),
      el('td', {}, el('div', { style: 'display:flex;gap:4px' }, (v.spring_done || r.visit_locked) ? '' : el('button', { class: 'btn' + (r.visited ? ' go' : ''), style: 'width:auto;padding:2px 8px;font-size:14px', 'data-tip': r.visited ? 'Cancel the visit' : 'Scout this player further', onclick: e => { e.stopPropagation(); const res = pyJSON(`SESSION.draft_act('visit', pid=${JSON.stringify(r.pid)})`); if (!res.ok) { notify(res); return; } v.visits = res.visits; r.visited = res.visits.includes(r.pid); r.words = r.visited ? ['Visited', ...r.words.filter(w => w !== 'Visited')] : r.words.filter(w => w !== 'Visited'); visitTally.textContent = visitText(); visitedTabCount.textContent = v.rows.filter(x => x.visited).length; draw(); } }, r.visited ? 'Visiting' : 'Visit'),
        onBoard.has(r.pid) ? el('span', { class: 'badge-sm' }, `#${v.user_board.order.findIndex(x => x.pid === r.pid) + 1}`) : el('button', { class: 'btn', style: 'width:auto;padding:2px 8px;font-size:14px', 'data-tip': 'Add to Draft Board', onclick: () => { pyJSON(`SESSION.draft_act('board', add=${JSON.stringify(r.pid)})`); reload(); } }, 'Add')))));
    if (!rows.length) tbl.append(el('tr', {}, el('td', { colspan: '11' }, el('div', { class: 'empty' }, 'Nobody matches the filter.'))));
  };
  const foot = el('div', { class: 'foot' });
  const drawFoot = () => { foot.innerHTML = ''; const r = v.rows.find(x => x.pid === boardSel);
    if (v.on_clock) foot.append(el('button', { class: 'btn go', disabled: (r && !r.taken) ? null : '', onclick: () => { const rr = pyJSON(`SESSION.draft_act('pick', pid=${JSON.stringify(boardSel)})`); notify(rr); if (rr.ok) location.hash = '#draft/day'; } }, 'Draft Player'));
    foot.append(el('button', { class: 'btn', disabled: r ? null : '', onclick: () => { pyJSON(`SESSION.draft_act('board', add=${JSON.stringify(boardSel)})`); reload(); } }, 'Add to Your Board'), el('button', { class: 'btn', disabled: r ? null : '', onclick: () => { location.hash = '#club/player/' + boardSel; } }, 'Prospect Card'), el('span', { class: 'count', style: 'margin-left:auto' }, r ? `${r.name} · ${r.pos} · ${r.home_state}` : 'Click a row to select a prospect')); };
  s.append(el('div', { class: 'board-wrap' }, tbl), foot); draw(); drawFoot();
  page.append(s);
}

function yourBoard(v, reload) {
  const box = el('div', {});
  const byid = {}; for (const r of v.rows) byid[r.pid] = r;
  const list = el('div', { class: 'pad' });
  const tiers = { 1: `Tier 1 · Worth Your Pick at ${v.my_slot || '—'}`, 2: 'Tier 2 · Second-Round Grades', 3: 'Later Rounds' };
  const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', { class: 'n' }, '#'), el('th', {}, 'Player'), el('th', { class: 'n', 'data-tip': 'Where the league expects him to go' }, 'Proj.'), el('th', { class: 'n', 'data-tip': "Your scouts' read. Carries error; a visit tightens it" }, 'Est. Ovr'), el('th', {}, '')));
  let lastTier = null;
  const order = v.user_board.order.map(x => x.pid);
  v.user_board.order.forEach((x, i) => {
    const r = byid[x.pid]; if (!r) return;
    if (x.tier !== lastTier) { t.append(el('tr', { class: 'grp' }, el('td', { colspan: '5' }, tiers[x.tier]))); lastTier = x.tier; }
    t.append(el('tr', { draggable: 'true', 'data-pid': r.pid }, el('td', { class: 'n' }, i + 1), el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos} · ${r.home_state}${r.my_round && x.tier > 1 ? ' · Your Grade ' + r.my_round : ''}`)))), el('td', { class: 'n' }, r.proj_range), el('td', { class: 'n' }, ovrCell(r.mine)),
      el('td', {}, el('div', { style: 'display:flex;gap:4px' }, el('button', { class: 'btn', style: 'padding:2px 6px;font-size:14px', disabled: i === 0 ? '' : null, onclick: () => { const o = order.slice(); [o[i - 1], o[i]] = [o[i], o[i - 1]]; pyJSON(`SESSION.draft_act('board', order=${JSON.stringify(o)})`); reload(); } }, '▲'), el('button', { class: 'btn', style: 'padding:2px 6px;font-size:14px', disabled: i === order.length - 1 ? '' : null, onclick: () => { const o = order.slice(); [o[i + 1], o[i]] = [o[i], o[i + 1]]; pyJSON(`SESSION.draft_act('board', order=${JSON.stringify(o)})`); reload(); } }, '▼'),
        el('button', { class: 'btn quiet', style: 'padding:2px 6px;font-size:14px', 'data-tip': 'Do Not Draft', onclick: () => { const d = v.user_board.dnd.map(z => z.pid).concat([r.pid]); pyJSON(`SESSION.draft_act('board', remove=${JSON.stringify(r.pid)})`); pyJSON(`SESSION.draft_act('board', dnd=${JSON.stringify(d)})`); reload(); } }, '✕')))));
  });
  if (!order.length) t.append(el('tr', {}, el('td', { colspan: '5' }, el('div', { class: 'empty' }, "Your board is empty. Add prospects from the class, or Auto-Fill by Read to start from your scouts' order."))));
  if (v.user_board.dnd.length) { t.append(el('tr', { class: 'grp' }, el('td', { colspan: '5' }, 'Do Not Draft'))); for (const x of v.user_board.dnd) { const r = byid[x.pid]; if (!r) continue; t.append(el('tr', { style: 'opacity:.6' }, el('td', { class: 'n' }, '✕'), el('td', {}, el('div', { class: 'who' }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos} · ${r.home_state} · ${x.why}`)))), el('td', { class: 'n' }, '—'), el('td', { class: 'n' }, ovrCell(r.mine)), el('td', {}, el('button', { class: 'btn quiet', style: 'padding:2px 6px;font-size:14px', onclick: () => { pyJSON(`SESSION.draft_act('board', dnd=${JSON.stringify(v.user_board.dnd.map(z => z.pid).filter(z => z !== r.pid))})`); reload(); } }, 'Restore')))); } }
  // drag to order
  let dragPid = null;
  t.addEventListener('dragstart', e => { const tr = e.target.closest('tr[data-pid]'); if (tr) dragPid = tr.dataset.pid; });
  t.addEventListener('dragover', e => { if (e.target.closest('tr[data-pid]')) e.preventDefault(); });
  t.addEventListener('drop', e => { const tr = e.target.closest('tr[data-pid]'); if (!tr || !dragPid || tr.dataset.pid === dragPid) return; e.preventDefault(); const o = order.filter(p => p !== dragPid); o.splice(o.indexOf(tr.dataset.pid), 0, dragPid); pyJSON(`SESSION.draft_act('board', order=${JSON.stringify(o)})`); reload(); });
  list.append(t); box.append(list);
  box.append(el('div', { class: 'read', style: 'margin:0 14px 12px' }, el('b', {}, 'Assistants: '), v.read || ''));
  box.append(el('div', { class: 'foot' }, el('button', { class: 'btn go', onclick: () => notify({ ok: true, line: 'Your board is saved as you change it.' }) }, 'Save Board'), el('button', { class: 'btn', 'data-tip': "Your scouts' order, top to bottom", onclick: () => { notify(pyJSON(`SESSION.draft_act('board_autofill')`)); reload(); } }, 'Auto-Fill by Read'), el('button', { class: 'btn quiet', onclick: () => { if (confirm('Clear your board?')) { pyJSON(`SESSION.draft_act('board', reset=True)`); reload(); } } }, 'Reset'), el('span', { class: 'count', style: 'margin-left:auto' }, 'Drag to Order · Draft Day picks from the top of this board')));
  return box;
}

function renderSpring(v) {
  renderRail(v.rail); const page = persPage(); drSecond('spring');
  page.className = 'draft-page';
  featureHero(page, v.rail.club, `Draft / ${v.rail.year}`, 'SPRING REPORT', 'What the workouts, pro days, and visits changed.', [[v.visited?.length ?? 0, 'Visits'], [v.done ? v.risers.length + v.fallers.length : '—', 'Stock moves']]);
  const s = el('section', { class: 'sheet c12 draft-surface draft-spring' }, el('h2', {}, 'The Spring', el('small', {}, v.done ? v.events.map(e => `${e.event} ${e.n} moves`).join(' · ') : 'stock moves and flags')));
  if (!v.done) { s.append(el('div', { class: 'empty' }, v.note)); page.append(s); return; }
  const list = el('div', { class: 'pad' });
  const line = (kind, m) => el('div', { class: 'sprow' }, el('span', { class: 'flag ' + ({ Rises: 'up', Falls: 'dn', Flag: 'med' }[kind] || '') }, kind), el('span', {}, el('b', { style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + m.pid; } }, m.name), ` (${m.pos}, ${m.home_state}): ${m.line || `${m.frm} to ${m.to} after the ${m.event}`}`));
  for (const m of v.risers) list.append(line('Rises', m));
  for (const m of v.fallers) list.append(line('Falls', m));
  for (const m of v.flagged) list.append(line('Flag', m));
  if (!list.children.length) list.append(el('div', { class: 'empty' }, 'No stock moves or flags this spring.'));
  s.append(list);
  s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Your Visits', el('small', {}, `${v.visited.length} players · the second look`)));
  const vt = el('table', { class: 'tbl' }); vt.append(el('tr', {}, el('th', {}, 'Prospect'), el('th', {}, 'Pos'), el('th', { class: 'n', 'data-tip': "Your scouts' read. Carries error; a visit tightens it" }, 'Your Read'), el('th', { class: 'n', 'data-tip': 'Where he can grow to. Wide means your scouts are unsure' }, 'Ceiling'), el('th', { class: 'n', 'data-tip': "The league's grade, same scale as yours" }, 'Consensus'), el('th', { class: 'n', 'data-tip': "Yours minus the league's. Positive means the league undervalues him" }, 'Gap'), el('th', {}, 'Flags')));
  const was = (before, now) => (before != null && String(before) !== String(now)) ? el('small', { class: 'count', style: 'display:block;font-size:11.5px' }, `was ${before}`) : '';
  for (const r of v.visited) { const b = r.before || {}; vt.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, r.home_state)))), el('td', {}, r.pos), el('td', { class: 'n' }, ovrCell(r.mine), was(b.mine, r.mine)), el('td', { class: 'n' }, r.ceiling, was(b.ceiling, r.ceiling)), el('td', { class: 'n' }, r.cons_rank != null ? `#${r.cons_rank}` : '—', was(b.cons_rank != null ? `#${b.cons_rank}` : null, r.cons_rank != null ? `#${r.cons_rank}` : '—')), el('td', { class: 'n' }, gapCell(r.gap)), el('td', {}, ...(r.words || []).filter(w => w !== 'Visited').map(wordTag)))); }
  if (!v.visited.length) vt.append(el('tr', {}, el('td', { colspan: '7' }, el('div', { class: 'empty' }, 'You named no visits this year.'))));
  s.append(vt); page.append(s);
}

const draftAvailableSources = new Map();
function draftAvailableView(v) {
  const key = `${v.rail.club.abbr}:${v.rail.year}`;
  const source = draftAvailableSources.get(key) || (v.has_custom_board ? 'mine' : 'consensus');
  const rows = (source === 'mine' ? v.board : v.best) || [];
  const top = rows[0] || null;
  const label = source === 'mine' ? 'Your Board' : 'Consensus';
  const note = source === 'mine'
    ? (v.has_custom_board ? 'Your saved order, followed by your scouts’ rankings. Do Not Draft players are excluded.' : 'No custom order yet — using your scouts’ rankings.')
    : 'League-wide prospect rankings. Estimated overall still shows your scouts’ evaluation.';
  const read = source === 'mine'
    ? (v.has_custom_board ? v.read : (top ? `${top.name} is your scouts’ highest-ranked available player.` : 'No eligible players remain on your board.'))
    : (top ? `${top.name} is the highest-ranked available player on the consensus board${top.cons_rank ? ` (#${top.cons_rank})` : ''}.` : 'No prospects remain.');
  return {key, source, rows, top, label, note, read};
}

function renderDraftDay(v) {
  renderRail(v.rail); const page = persPage(); drSecond('day');
  page.className = 'draft-page';
  featureHero(page, v.rail.club, `Draft / ${v.year_next || v.rail.year}`, 'DRAFT DAY', 'The live board, available players, and trade decisions.', [[v.live ? (v.current?.sel ?? '—') : '—', 'On the clock'], [v.live ? (v.mine_next?.[0]?.sel ?? '—') : '—', 'Your next pick']]);
  const reload = () => renderDraftDay(pyJSON(`SESSION.draft_view('draft_day')`));
  if (!v.live) {
    const s = el('section', { class: 'sheet c12 draft-surface' }, el('h2', {}, v.year_next && !v.last ? `${v.year_next} Draft` : 'Draft Day'), el('div', { class: 'empty' }, v.note));
    if (v.last) { s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, `${v.last.year} Draft Results`, el('small', {}, `${v.last.rows.length} picks · ${v.last.trades} trades`))); const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Pick'), el('th', {}, 'Team'), el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Consensus'))); for (const r of v.last.rows) t.append(el('tr', { style: r.mine ? 'background:var(--sheet-2)' : '' }, el('td', {}, r.slot), el('td', {}, stripe(r.team.abbr, r.team.name)), el('td', { style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + r.pid; } }, r.name), el('td', {}, r.pos), el('td', { class: 'n' }, r.cons_rank ?? '—'))); s.append(t); }
    page.append(s); return;
  }
  const act = (name, extra) => { const r = pyJSON(`SESSION.draft_act(${JSON.stringify(name)}${extra ? ', ' + extra : ''})`); notify(r); if (r.done) { location.hash = '#draft/picks'; return; } if (r.ok !== false && ['sim_to_me', 'sim_round', 'sim_pick_one', 'pick'].includes(name)) boardRound = null; reload(); };
  const cur = v.current;
  const left = el('section', { class: 'sheet c8 draft-surface draft-clock' });
  // the clock
  left.append(el('div', { class: 'clockhead' }, el('div', { class: 'draft-clock-emblem', role: 'img', 'aria-label': cur.team.name, style: `--clock-team:${teamTheme(cur.team).base};--clock-accent:${teamTheme(cur.team).accent}` }, showAbbr(cur.team.abbr)), el('div', {}, el('div', { class: 'big' }, v.on_user ? 'You Are On the Clock' : `${cur.team.name} Is On the Clock`), el('div', { class: 'sub' }, `Round ${cur.round} · Pick ${cur.sel}` + (cur.needs && cur.needs.length ? ` · Needs ${cur.needs.join(', ')}` : ''))),
    el('div', { class: 'yours' }, v.mine_next.length ? el('div', {}, el('div', { class: 'big', style: 'font-size:20.5px' }, `You Pick ${v.mine_next[0].sel}${ord(v.mine_next[0].sel)}`), el('div', { class: 'sub' }, v.on_user ? 'Now' : v.picks_away === 1 ? 'One Pick Away' : v.picks_away != null ? `${['Two', 'Three', 'Four', 'Five', 'Six', 'Seven'][v.picks_away - 2] || v.picks_away} Picks Away` : '')) : el('div', { class: 'sub' }, 'No picks left'))));
  left.append(el('div', { class: 'ctrl2', style: 'padding:0 14px 10px' },
    el('button', { class: 'btn tip-left', 'data-tip': v.on_user ? 'Draft one player from your saved board, or your scouts’ rankings if no order is set. Respects Do Not Draft.' : 'Simulate exactly one pick', onclick: () => { offersCache = null; act('sim_pick_one'); } }, 'Next Pick'),
    el('button', { class: 'btn go', disabled: v.on_user ? '' : null, onclick: () => act('sim_to_me') }, 'Sim to Your Pick'),
    el('button', { class: 'btn', disabled: v.on_user ? '' : null, 'data-tip': 'Sim to the end of this round, or to your pick if it comes first', onclick: () => act('sim_round') }, 'Sim Round'),
    el('button', { class: 'btn quiet', onclick: () => { if (confirm('Run the rest of the draft? Your picks go to the top of your board.')) act('sim_draft'); } }, 'Sim Draft'),
    el('span', { class: 'sep' }),
    el('button', { class: 'btn', disabled: v.on_user ? null : '', 'data-tip': 'Gather offers for this pick', onclick: () => { const r = pyJSON(`SESSION.draft_act('offers')`); notify(r); if (r.ok) { offersCache = r.offers; reload(); } } }, 'Trade Down')));
  // the picks around the clock
  const nx = el('div', { class: 'picksmade' });
  const recent = v.results.slice(0, 3).reverse();
  for (const r of recent) nx.append(el('div', { class: 'pk' }, el('span', { class: 'n' }, r.slot), crest(r.team, 30), el('div', { class: 'who' }, el('div', { class: 'nm' }, r.name), el('small', {}, `${r.pos}`)), el('span', {})));
  for (const q of v.clock) {
    const now = q.sel === cur.sel;
    const tradeFor = q.mine ? null : () => { tradeState = { other: q.team.abbr, a: [], b: [q.id], keep: true, draft: true }; location.hash = '#personnel/trades'; };
    nx.append(el('div', { class: 'pk' + (q.mine ? ' next' : '') + (now ? ' now' : '') + (q.mine ? '' : ' tradeable'), 'data-tip': q.mine ? null : `Trade for pick ${q.slot}: opens the Trades tab with ${q.team.name}'s pick loaded`, onclick: tradeFor, style: q.mine ? '' : 'cursor:pointer' }, el('span', { class: 'n' }, q.slot), crest(q.team, 30), el('div', { class: 'who' }, el('div', { class: 'nm' }, now ? 'On the Clock' : q.mine ? 'Your Pick' : 'Trade for it'), el('small', {}, `${q.team.name}${q.needs && q.needs.length && !q.mine ? ' · Needs ' + q.needs.join(', ') : ''}`)), el('span', {})));
  }
  // (the strip of pick rows is not shown; the board below is the order)
  // THE PICK BOARD. Every slot of the draft, eight to a row, four rows a round. A made pick shows the player, his
  // position and the club; one to come shows the club and the number. Click a club's slot to trade for it.
  const rounds = [...new Set(v.order.map(q => q.round))];
  const nowRound = (v.order.find(q => q.now) || v.order[0] || {}).round || 1;
  if (boardRound == null || !rounds.includes(boardRound)) boardRound = nowRound;
  const board = el('div', { class: 'pickboard' });
  board.append(el('div', { class: 'pb-round' }, `Round ${boardRound}`, el('span', { class: 'count', style: 'margin-left:8px;text-transform:none;letter-spacing:0' }, boardRound === nowRound ? 'on the clock' : '')));
  for (const q of v.order.filter(x => x.round === boardRound)) {
    const tradeFor = (!q.done && !q.mine) ? () => { tradeState = { other: q.team.abbr, a: [], b: [q.id], keep: true, draft: true }; location.hash = '#personnel/trades'; } : null;
    const sq = el('div', { class: 'pb-sq' + (q.done ? ' done' : '') + (q.now ? ' now' : '') + (q.mine ? ' mine' : ''), style: `--c1:${q.team.color};--c2:${q.team.accent || '#fff'}` + (tradeFor ? ';cursor:pointer' : ''), 'data-tip': tradeFor ? `Trade for pick ${q.slot}` : null, onclick: tradeFor });
    sq.append(el('div', { class: 'pb-top' }, el('span', { class: 'ab' }, showAbbr(q.team.abbr)), el('span', { class: 'sl' }, q.slot)));
    if (q.done) sq.append(el('div', { class: 'pb-nm' }, q.name), el('div', { class: 'pb-pos' }, `${q.pos}${q.original ? ` · from ${showAbbr(q.original)}` : ''}`));
    else if (q.now && q.mine) sq.append(el('button', { class: 'btn go', style: 'width:auto;padding:3px 8px;font-size:12.5px;margin-top:2px', onclick: e => { e.stopPropagation(); location.hash = '#draft/board'; } }, 'Draft Player'));
    else sq.append(el('div', { class: 'pb-nm dim' }, q.now ? 'On the clock' : (q.mine ? 'Your pick' : q.team.name)), el('div', { class: 'pb-pos' }, q.original ? `from ${showAbbr(q.original)}` : ''));
    board.append(sq);
  }
  left.append(board);
  // the round pagers sit in the tool row, right of Trade Down
  const pagers = el('span', { class: 'pagers draft-round-pager' },
    el('button', { class: 'btn draft-round-arrow previous', 'aria-label': 'Previous round', 'data-tip': 'Previous round', disabled: boardRound <= rounds[0] ? '' : null, onclick: () => { boardRound = Math.max(rounds[0], boardRound - 1); renderDraftDay(v); } }, el('span', { class: 'round-chevron', 'aria-hidden': 'true' })),
    el('span', { class: 'count', 'aria-live': 'polite' }, `Round ${boardRound} of ${rounds[rounds.length - 1]}`),
    el('button', { class: 'btn draft-round-arrow next tip-right', 'aria-label': 'Next round', 'data-tip': 'Next round', disabled: boardRound >= rounds[rounds.length - 1] ? '' : null, onclick: () => { boardRound = Math.min(rounds[rounds.length - 1], boardRound + 1); renderDraftDay(v); } }, el('span', { class: 'round-chevron', 'aria-hidden': 'true' })));
  const toolRow = left.querySelector('.ctrl2'); if (toolRow) toolRow.append(pagers); else left.insertBefore(pagers, board);
  // offers for your pick
  if (v.on_user && offersCache && offersCache.length) {
    for (const o of offersCache) left.append(el('div', { class: 'card', style: '--k:var(--live);margin:0 14px 10px' }, el('div', { class: 'h' }, el('div', { class: 'k' }, `Trade Offer · ${o.team.name}`), el('div', { class: 's' }, `${o.team.name} offers ${o.summary.join(' and ')} for ${cur.slot}`)),
      el('div', { class: 'a' }, el('button', { class: 'btn go', onclick: () => { offersCache = null; act('accept_offer', `i=${o.i}`); } }, 'Accept'), el('button', { class: 'btn', onclick: () => { location.hash = '#personnel/trades'; } }, 'Counter'), el('button', { class: 'btn quiet', onclick: () => { offersCache = offersCache.filter(x => x.i !== o.i); reload(); } }, 'Decline'))));
  }
  page.append(left);
  const available = draftAvailableView(v);
  const sourcePicker = el('select', { class: 'draft-board-source', 'aria-label': 'Best available board', onchange: e => { draftAvailableSources.set(available.key, e.target.value); renderDraftDay(v); } },
    el('option', { value: 'consensus' }, 'Consensus'), el('option', { value: 'mine' }, 'Your Board'));
  sourcePicker.value = available.source;
  const right = el('section', { class: 'sheet c4 draft-surface draft-available' }, el('h2', {}, 'Best Available', sourcePicker));
  right.append(el('p', { class: 'draft-board-note' }, available.note));
  const bt = el('table', { class: 'tbl' }); bt.append(el('tr', {}, el('th', { class: 'n', 'data-tip': available.source === 'consensus' ? 'Consensus rank in the full draft class' : 'Rank on your available board' }, '#'), el('th', {}, 'Player'), el('th', { class: 'n', 'data-tip': 'Where the league expects him to go' }, 'Proj.'), el('th', { class: 'n', 'data-tip': "Your scouts' read. Carries error; a visit tightens it" }, 'Est. Ovr')));
  for (const r of available.rows.slice(0, 12)) bt.append(el('tr', { style: v.on_user ? 'cursor:pointer' : '', 'data-tip': v.on_user ? 'Click the row to draft him; the name opens his card' : null, onclick: e => { if (e.target.closest('.who')) return; if (v.on_user && confirm(`Draft ${r.name}, ${r.pos}, ${r.home_state} at ${cur.slot}?`)) act('pick', `pid=${JSON.stringify(r.pid)}`); } }, el('td', { class: 'n' }, available.source === 'consensus' ? (r.cons_rank ?? '—') : r.board_no), el('td', {}, el('button', { class: 'who', onclick: e => { e.stopPropagation(); location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, surname(r.name), el('small', {}, `${r.pos} · ${r.home_state}${r.my_round && r.my_rank > 32 ? ' · Your Grade ' + r.my_round : ''}`)))), el('td', { class: 'n' }, r.proj_range), el('td', { class: 'n' }, ovrCell(r.mine))));
  right.append(bt);
  right.append(el('div', { class: 'read', style: 'margin:10px 12px' }, el('b', {}, 'Assistants: '), available.read || ''));
  if (v.on_user && available.top) right.append(el('div', { class: 'pad', style: 'padding-top:0' }, el('button', { class: 'btn go', style: 'width:100%;justify-content:center', onclick: () => act('pick', `pid=${JSON.stringify(available.top.pid)}`) }, `Draft ${available.top.name}`, el('small', { style: 'margin-left:8px;font-weight:500' }, `${available.top.pos} · ${available.top.home_state} · ${available.label} #${available.source === 'consensus' ? (available.top.cons_rank ?? '—') : 1}`))));
  right.append(el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#draft/board' }, 'Your Board'), el('span', { class: 'count', 'data-tip': v.my_needs.join(', ') }, `Needs · ${v.my_needs.slice(0, 3).join(', ') || 'none'}`), el('button', { class: 'btn quiet', disabled: available.top ? null : '', onclick: () => { location.hash = '#club/player/' + available.top.pid; } }, 'Prospect Card')));
  page.append(right);
}
let offersCache = null;
const gdReveal = {};      // where each game's reveal stands, so leaving the page and coming back holds the place

let picksClub = 'mine', picksYear = null, picksYearFor = null, picksQuery = '';
function renderPicks(v) {
  renderRail(v.rail); const page = persPage(); drSecond('picks');
  page.className = 'draft-page';
  featureHero(page, v.rail.club, `Draft / ${v.rail.year}`, 'YOUR PICKS', 'What you own and where you pick next.', [[v.years.reduce((a, y) => a + y.picks.length, 0), 'Picks held'], [v.years.length, 'Drafts']]);
  const s = el('section', { class: 'sheet c12 draft-surface draft-picks' }, el('h2', {}, 'Your Picks', el('small', {}, `${v.years.reduce((a, y) => a + y.picks.length, 0)} picks over ${v.years.length} drafts`), el('button', { class: 'btn', style: 'margin-left:auto;width:auto', 'data-tip': 'Copy the last draft, every pick and trade, as text', onclick: function () { const r = pyJSON(`SESSION.draft_view('draft_text')`); if (!r.ok) { notify(r); return; } copyText(r.text, this); } }, 'Copy Draft'),
    el('button', { class: 'btn', style: 'width:auto', 'data-tip': 'Download the last draft as a spreadsheet: every pick with every attribute of every player', onclick: () => { const r = pyJSON(`SESSION.draft_view('draft_csv')`); if (!r.ok) { notify(r); return; } const blob = new Blob([r.text], { type: 'text/csv' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = r.name; document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(a.href); } }, 'Download Draft'),
    el('button', { class: 'btn', style: 'width:auto', 'data-tip': "Download the coming class as a spreadsheet: every prospect's true numbers beside your room's read", onclick: () => { const r = pyJSON(`SESSION.draft_view('class_csv')`); if (!r.ok) { notify(r); return; } const blob = new Blob([r.text], { type: 'text/csv' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = r.name; document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(a.href); } }, 'Download Class')));
  const yrs = el('div', { class: 'years' });
  for (const y of v.years) {
    const box = el('div', { class: 'ybox' }, el('h4', {}, y.this_draft ? `${y.year} Draft · this season's` : `${y.year} Draft`));
    for (const p of y.picks) box.append(el('div', { class: 'pkrow' }, el('span', { class: 'rd' }, `R${p.round}`), el('div', { class: 'nm' }, p.slot + (p.frm ? ` (From ${p.frm})` : ''), el('small', {}, p.note || ''))));
    yrs.append(box);
  }
  s.append(yrs);
  page.append(s);
}

// DRAFT RESULTS: every drafted player on record, by club and year
function renderDraftResults(v) {
  renderRail(v.rail); const page = persPage(); drSecond('results');
  page.className = 'draft-page';
  featureHero(page, v.rail.club, `Draft / ${v.default_year}`, 'DRAFT RESULTS', 'Every selection on record, with your original read beside it.', [[v.results.length, 'Players drafted'], [v.result_years.length, 'Classes']]);
  const s = el('section', { class: 'sheet c12 draft-surface draft-results' });
  // the tab opens on the draft the server names (this offseason's if held, else the coming one); the chosen year sticks
  // only within the same default, so a new season resets it instead of carrying last year's draft forward
  if (picksYearFor !== v.default_year) { picksYear = v.default_year; picksYearFor = v.default_year; }
  s.append(el('h2', {}, 'Draft Results', el('small', {}, `${v.results.length} drafted players on record`)));
  const tools = el('div', { class: 'tools' });
  const clubs = el('div', { class: 'chips' }); for (const [k, l] of [['mine', v.rail.club.name], ['all', 'All Teams'], ['div', v.my_division]]) clubs.append(el('button', { class: 'chip', 'aria-pressed': String(picksClub === k), onclick: () => { picksClub = k; renderDraftResults(v); } }, l));
  const yrsChips = el('div', { class: 'chips' }); for (const y of (v.result_years.includes(v.default_year) ? v.result_years : [v.default_year, ...v.result_years])) yrsChips.append(el('button', { class: 'chip', 'aria-pressed': String(picksYear === y), onclick: () => { picksYear = y; renderDraftResults(v); } }, y));
  const search = el('input', { type: 'search', class: 'find', placeholder: 'Find a Player', value: picksQuery }); search.oninput = () => { picksQuery = search.value; drawR(); };
  tools.append(clubs, yrsChips, search); s.append(tools);
  const rt = el('table', { class: 'tbl' });
  const drawR = () => {
    rt.innerHTML = ''; rt.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n', 'data-tip': 'Where he was drafted' }, 'Pick'), el('th', { class: 'n', 'data-tip': "Where the league's consensus ranked him going into the draft" }, 'Consensus'), el('th', { class: 'n', 'data-tip': 'His overall rating today' }, 'Overall')));
    const q = picksQuery.trim().toLowerCase();
    const rows = v.results.filter(r => (picksClub === 'all' || (picksClub === 'mine' && r.team && r.team.abbr === v.rail.club.abbr) || (picksClub === 'div' && r.division === v.my_division)) && (!picksYear || r.year === picksYear) && (!q || r.name.toLowerCase().includes(q)));
    for (const r of rows.slice(0, 200)) rt.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos} · ${r.home_state}${r.team ? ' · ' + showAbbr(r.team.abbr) : ''}`)))), el('td', {}, r.pos), el('td', { class: 'n' }, r.pick), el('td', { class: 'n' }, r.cons_was != null ? `#${r.cons_was}` : '—'), el('td', { class: 'n' }, ovrCell(r.ovr))));
    if (!rows.length) rt.append(el('tr', {}, el('td', { colspan: '5' }, el('div', { class: 'empty' }, (picksYear === v.default_year && !v.default_held) ? `The ${v.default_year} draft has not been held yet. Earlier drafts are on the year chips.` : v.results.length ? 'Nobody matches.' : 'The first class is drafted in the spring.'))));
  };
  s.append(rt); drawR(); page.append(s);
}

// ---------------------------------------------------------------- Team page (another club at a glance)
function renderTeam(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  page.className = 'team-profile-page'; applyTeamTheme(page, v.club);
  $('#crumb').textContent = 'League'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'league'));
  secondRow(clubNav(v.club.abbr, false, null), `#league/team/${v.club.abbr}`);
  const select = clubSelect(v.club.abbr, a => { const m = pyJSON('SESSION.club_list()').find(c => c.abbr === a); location.hash = m && m.mine ? '#club' : `#league/team/${a}`; });
  page.append(el('header', { class: 'team-profile-hero c12' }, el('div', { class: 'team-profile-intro' }, crest(v.club, 72), el('div', {}, el('div', { class: 'feature-kicker' }, `LEAGUE / ${v.place}`), el('h1', {}, v.club.name), el('p', {}, `${v.coach?.name || 'Head coach open'} · ${v.identity.offense} offense · ${v.identity.defense} defense`))), el('div', { class: 'team-profile-select' }, select)));
  page.append(el('div', { class: 'team-profile-metrics c12' }, ...[[v.record, 'Record'], [v.ranks.offense ? `${v.ranks.offense}${ord(v.ranks.offense)}` : '—', 'Offense'], [v.ranks.defense ? `${v.ranks.defense}${ord(v.ranks.defense)}` : '—', 'Defense'], [`$${v.cap.space}m`, 'Cap space']].map(([value, label]) => el('div', {}, el('strong', {}, value), el('span', {}, label)))));
  const left = el('section', { class: 'sheet c8 team-profile-main' });
  left.append(el('div', { class: 'team-profile-detail' }, el('span', {}, 'NEXT YEAR', el('b', {}, `$${v.cap.committed_next}m of $${v.cap.limit_next}m committed`)), el('span', {}, 'ROSTER', el('b', {}, `${v.roster_n} active · ${v.ps_n} practice squad${v.ir_n ? ` · ${v.ir_n} IR` : ''}`))));
  // the coaches
  const h5 = (t, sub) => el('div', { class: 'h5' }, t, sub ? el('span', {}, sub) : '');
  const st = el('div', { class: 'pad' }, h5('Coaching', `${v.identity.offense} · ${v.identity.defense}`));
  const kv = el('div', { class: 'kv' });
  if (v.coach) kv.append(el('span', {}, 'Head Coach'), el('span', {}, `${v.coach.name}${v.coach.background ? ' · ' + v.coach.background : ''}${v.coach.personnel ? ' · ' + v.coach.personnel + ' personnel' : ''}`));
  for (const [k, l] of [['oc', 'Offensive Coordinator'], ['dc', 'Defensive Coordinator'], ['st', 'Special Teams'], ['scout', 'Head Scout']]) { const c = v.staff[k]; kv.append(el('span', {}, l), el('span', {}, c ? `${c.name} (${c.rating}) · ${c.specialty}` : '—')); }
  st.append(kv); left.append(st);
  // the top five
  left.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Top Players'));
  const tt = el('table', { class: 'tbl' }); tt.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', { class: 'n' }, 'Deal')));
  for (const p of v.top) tt.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + p.pid; } }, el('div', { class: 'no' }, p.no ?? p.pos), el('div', { class: 'nm' }, p.name))), el('td', {}, p.pos), el('td', { class: 'n' }, p.age), el('td', { class: 'n' }, ovrCell(p.ovr)), el('td', { class: 'n' }, `$${p.apy}m × ${p.yrs}`)));
  left.append(tt);
  page.append(left);
  // the block
  const right = el('section', { class: 'sheet c4 team-profile-aside' }, el('h2', {}, 'Trading Block', el('small', {}, v.needs.length ? `needs ${v.needs.join(', ')}` : '')));
  const bt = el('table', { class: 'tbl' }); bt.append(el('tr', {}, el('th', {}, 'Player'), el('th', { class: 'n' }, 'Ovr'), el('th', {}, '')));
  for (const p of v.block) bt.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + p.pid; } }, el('div', { class: 'no' }, p.pos), el('div', { class: 'nm' }, p.name, el('small', {}, `${p.why} · $${p.apy}m`)))), el('td', { class: 'n' }, ovrCell(p.ovr)), el('td', {}, v.mine ? '' : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:13px', 'data-tip': 'Open a trade for him', onclick: () => { tradeState = { other: v.club.abbr, a: [], b: [p.pid] }; location.hash = '#personnel/trades'; } }, 'Ask'))));
  if (!v.block.length) bt.append(el('tr', {}, el('td', { colspan: '3' }, el('div', { class: 'empty' }, 'Nobody they would move right now.'))));
  right.append(bt);
  right.append(el('div', { class: 'foot' }, el('a', { class: 'btn', href: `#league/team/${v.club.abbr}/roster` }, 'Roster'), el('a', { class: 'btn', href: `#league/team/${v.club.abbr}/depth` }, 'Depth Chart'), el('a', { class: 'btn', href: `#league/team/${v.club.abbr}/ps` }, 'Practice Squad'), v.mine ? '' : el('a', { class: 'btn quiet', href: '#personnel/trades', onclick: () => { tradeState = { other: v.club.abbr, a: [], b: [] }; } }, 'Trade')));
  page.append(right);
}

// ---------------------------------------------------------------- League
const LG = { standings: 'Standings', schedule: 'Schedule', bracket: 'Playoffs', transactions: 'Transactions', stats: 'Stats', awards: 'Awards', coaching: 'Coaching', almanac: 'Almanac' };
function lgSecond(cur) { secondRow(Object.entries(LG).map(([k, l]) => [l, '#league/' + k]), '#league/' + cur); $('#crumb').textContent = 'League'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'league')); }
const TAGCLS = { Trade: 'trade', Signing: 'sign', Release: 'cut', Draft: 'draft', Extension: 'contract', Waivers: 'wire', 'Call-Up': 'squad', 'Practice Squad': 'squad', 'Injured Reserve': 'wire', IR: 'wire', Retirement: 'retire', Fired: 'cut', Hired: 'staff', Staff: 'staff', 'Franchise Tag': 'tagg', Restructure: 'contract', 'Position Change': 'squad', 'Hall of Fame': 'hall', Season: 'season' };

function renderStandings(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('standings');
  const board = el('section', {class:'standings-board c12'});
  board.style.setProperty('--stand-team', v.rail.club.color || '#203731');
  board.style.setProperty('--stand-accent', v.rail.club.accent || '#ffb612');
  board.append(el('header', {class:'standings-hero'}, el('div', {}, el('small', {}, 'LEAGUE'), el('h1', {}, 'STANDINGS')), el('div', {class:'standings-period'}, el('b', {}, `${v.year} SEASON`))));
  const layout = el('div', {class:'standings-layout'});
  const s = el('section', {class:'standings-main'});
  const controls = el('div', {class:'standings-controls'});
  const years = [...new Set([...(v.years || []), v.year].map(Number))].filter(Number.isFinite).sort((a,b)=>b-a);
  const year = el('select', {class:'team-picker standings-year', 'aria-label':'Standings season', disabled:years.length < 2 ? '' : null});
  for (const y of years) year.append(el('option', {value:y, selected:y === Number(v.year) ? '' : null}, y));
  year.onchange = () => renderStandings(pyJSON(`SESSION.league_view('standings', year=${Number(year.value)})`));
  controls.append(year); s.append(controls); layout.append(s); board.append(layout);
  if (v.thin) {
    const grid = el('div', { class: 'divgrid' });
    for (const d of (v.divisions || [])) { const t = el('table', { class: 'grid' }, el('thead', {}, el('tr', {}, el('th', {}, d.name), el('th', { class: 'n' }, 'W–L'), el('th', { class: 'n' }, 'Pct')))); const tb = el('tbody'); for (const r of d.rows) tb.append(el('tr', {}, el('td', {}, clubLink(r.club.abbr, r.club.name)), el('td', { class: 'n mono' }, r.record), el('td', { class: 'n mono' }, String(r.pct.toFixed(3)).replace(/^0/, '')))); t.append(tb); grid.append(t); }
    s.append(grid); if (!v.league_rows.length) s.append(el('div', { class: 'empty' }, 'No standings are kept for that season.')); for (const n of (v.notes || []).filter(Boolean)) s.append(el('div', { class: 'count', style: 'padding:6px 14px' }, n)); page.append(board); return; }
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); for (const k of ['Divisions', 'Conference', 'League']) tabs.append(el('button', { 'aria-pressed': String(standingsView === k), onclick: () => { standingsView = k; renderStandings(v); } }, k)); controls.append(tabs);
  const arrow = r => r.arrow > 0 ? el('span', { class: 'arr up' }, `▲${r.arrow}`) : r.arrow < 0 ? el('span', { class: 'arr dn' }, `▼${-r.arrow}`) : el('span', { class: 'arr' }, '–');
  const pd = r => el('td', { class: 'n', style: r.pd > 0 ? 'color:var(--ok)' : r.pd < 0 ? 'color:var(--danger)' : '' }, (r.pd > 0 ? '+' : '') + r.pd);
  if (standingsView === 'Conference') {
    for (const conf of ['Continental', 'United']) {
      const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, conf), el('th', { class: 'n' }, 'Seed'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', { class: 'n' }, 'T'), el('th', { class: 'n' }, 'Pct'), el('th', { class: 'n', 'data-tip': 'Point differential' }, 'PD'), el('th', { class: 'n', 'data-tip': 'Strength of victory' }, 'SOV'), el('th', { class: 'n', 'data-tip': 'Strength of schedule' }, 'SOS'), el('th', {}, 'Form')));
      for (const r of v.conferences[conf]) t.append(el('tr', { class: r.me ? 'standings-user' : '' }, el('td', {}, clubLink(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.seed ? el('span', { class: 'seed ' + (r.seed === 1 ? 'bye' : 'in') + (r.me ? ' me' : '') }, r.seed) : ''), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', { class: 'n' }, r.t), el('td', { class: 'n' }, r.pct.toFixed(3).replace(/^0/, '')), pd(r), el('td', { class: 'n' }, r.sov != null ? r.sov.toFixed(3).replace(/^0/, '') : '—'), el('td', { class: 'n' }, r.sos != null ? r.sos.toFixed(3).replace(/^0/, '') : '—'), el('td', {}, formDots(r.form))));
      s.append(t);
    }
  } else if (standingsView === 'League') {
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', { class: 'n' }, '#'), el('th', {}, 'Team'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', { class: 'n' }, 'T'), el('th', { class: 'n' }, 'Pct'), el('th', { class: 'n' }, 'PF'), el('th', { class: 'n' }, 'PA'), el('th', { class: 'n' }, 'PD'), el('th', {}, 'Form')));
    v.league_rows.forEach((r, i) => t.append(el('tr', { class: r.me ? 'standings-user' : '' }, el('td', { class: 'n' }, i + 1), el('td', {}, clubLink(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', { class: 'n' }, r.t), el('td', { class: 'n' }, r.pct.toFixed(3).replace(/^0/, '')), el('td', { class: 'n' }, r.pf), el('td', { class: 'n' }, r.pa), pd(r), el('td', {}, formDots(r.form)))));
    s.append(t);
  } else {
    const grid = el('div', { class: 'divgrid' });
    for (const d of v.divisions) {
      const box = el('div', { class: 'divbox' }, el('h4', {}, d.name)); const t = el('table', { class: 'tbl' });
      t.append(el('tr', {}, el('th', {}, 'Team'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', {}, 'Form'), el('th', { class: 'n', 'data-tip': 'Points for' }, 'PF'), el('th', { class: 'n', 'data-tip': 'Points against' }, 'PA'), el('th', { class: 'n', 'data-tip': 'Point differential' }, 'PD'), el('th', { class: 'n', 'data-tip': 'Record inside the division' }, 'Div'), el('th', { class: 'n', 'data-tip': 'Moved since last week' }, '')));
      for (const r of d.rows) t.append(el('tr', { class: r.me ? 'standings-user' : '' }, el('td', {}, clubLink(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', {}, formDots(r.form)), el('td', { class: 'n' }, r.pf), el('td', { class: 'n' }, r.pa), pd(r), el('td', { class: 'n' }, r.div_rec), el('td', { class: 'n' }, arrow(r))));
      box.append(t); grid.append(box);
    }
    s.append(grid);
  }
  if (v.notes.length) s.append(el('div', { class: 'legend-line' }, 'Ties: ' + v.notes.join(' ')));
  layout.append(pictureSheet(v)); page.append(board);
}
let standingsView = 'Divisions';
function pictureSheet(v) {
  const r = el('section', { class: 'standings-picture' }, el('h2', {}, 'Playoff Picture', el('small', {}, v.past ? 'Final seeds' : v.games_played ? 'Seeds as of today' : 'Preseason · provisional order')));
  for (const c of v.picture) {
    r.append(el('h4', { style: 'padding:8px 14px 0;font-size:15px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.06em' }, c.conf));
    const t = el('table', { class: 'tbl' });
    for (const x of c.seeds) t.append(el('tr', { class: x.me ? 'standings-user' : '' }, el('td', { style: 'width:34px' }, el('span', { class: 'seed ' + (x.bye ? 'bye' : 'in') + (x.me ? ' me' : '') }, x.seed)), el('td', {}, clubLink(x.club.abbr, x.club.name)), el('td', { class: 'n' }, x.record), el('td', {}, el('small', { style: 'color:var(--ink-3)' }, x.bye ? 'Bye' : x.div_winner ? 'Division' : 'Wild Card'))));
    if (c.hunt.length) t.append(el('tr', {class:'hunt-heading'}, el('td', {colspan:'4'}, 'IN THE HUNT')));
    for (const x of c.hunt) t.append(el('tr', { style: 'color:var(--ink-3)' + (x.me ? ';background:var(--sheet-2)' : '') }, el('td', {}, el('span', { class: 'seed bub' }, '·')), el('td', {}, clubLink(x.club.abbr, x.club.name)), el('td', { class: 'n' }, x.record), el('td', {}, el('small', {}, 'in the hunt'))));
    r.append(t);
  }
  return r;
}

function leagueBoard(v, title, note='') {
  const board=reportBoard(v.rail.club,title); board.classList.add('league-board');
  board.querySelector('.report-hero small').textContent='LEAGUE';
  if(note) board.append(el('p',{class:'league-note'},note));
  return board;
}
function leagueYear(v, change) {
  const pick=el('select',{class:'btn league-year','aria-label':'Season',onchange:e=>change(Number(e.target.value))});
  for(const y of (v.years || [v.year]).slice().reverse()) pick.append(el('option',{value:y,selected:Number(y)===Number(v.year)?'':null},String(y)));
  return pick;
}
function leagueFinish(board,page) {
  for(const table of board.querySelectorAll('table')) {
    if(table.parentElement.classList.contains('report-table-scroll')) continue;
    const wrap=el('div',{class:'report-table-scroll'});table.replaceWith(wrap);wrap.append(table);
  }
  page.append(board);
}

function renderSchedule(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('schedule');
  const s = leagueBoard(v, 'SCHEDULE', '');
  const teamPicker=el('select',{class:'btn team-picker','aria-label':'Schedule team',onchange:e=>{if(e.target.value)renderTeamSchedule(pyJSON(`SESSION.league_view('team_schedule', team=${JSON.stringify(e.target.value)}, year=${Number(v.year)})`));}});
  teamPicker.append(el('option',{value:''},'All teams'));
  for(const c of pyJSON('SESSION.club_list()'))teamPicker.append(el('option',{value:c.abbr},`${c.name}${c.mine?' (User)':''}`));
  s.querySelector('.report-hero').append(el('div',{class:'schedule-team-controls'},teamPicker));
  s.append(leagueYear(v, y => renderSchedule(pyJSON(`SESSION.league_view('schedule', year=${y})`))));
  if (v.missing) { s.append(el('div', { class: 'empty' }, 'No schedule is kept for that season.')); leagueFinish(s,page); return; }
  if (v.note) s.append(el('div', { class: 'count', style: 'padding:4px 14px' }, v.note));
  s.append(el('div', { class: 'tabs', style: 'padding:8px 14px 0' }, el('button', { 'aria-pressed': 'true' }, 'League Schedule'), el('button', { 'aria-pressed': 'false', onclick: () => renderTeamSchedule(pyJSON(`SESSION.league_view('team_schedule', year=${Number(v.year)})`)) }, 'Team Schedule')));
  const nav = el('div', { class: 'wknav' }, el('span', { class: 'lab' }, 'Week'));
  const wkList = Array.isArray(v.weeks) ? v.weeks : Array.from({ length: v.weeks || 18 }, (_, i) => i + 1);
  for (const w of wkList) nav.append(el('button', { 'aria-pressed': String(w === v.week), 'data-tip': w >= 19 ? weekName(w) : null, onclick: () => renderSchedule(pyJSON(`SESSION.league_view('schedule', week=${w}, year=${v.year})`)) }, w >= 19 ? ({ 19: 'WC', 20: 'DIV', 21: 'CONF', 22: 'Final' })[w] : w));
  s.append(nav);
  const done = v.games.some(g => g.done);
  s.append(el('div', { class: 'h5', style: 'padding:8px 14px 0' }, `${weekName(v.week)} · ${done ? 'Results' : 'Upcoming'}`, el('span', {}, done ? 'Click your game for the box score' : '')));
  const grid = el('div', { class: 'league-games' });
  for (const g of v.games) {
    const tm = (c, rec, win, at) => el('div', { class: 'tm' + (g.done ? (win ? ' w' : ' l') : '') }, at ? el('small', {}, 'at') : '', clubLink(c.abbr, c.name), el('small', {}, rec));
    const card = el('div', { class: 'game' + (g.mine ? ' mine' : '') + (g.done ? ' done' : '') },
      tm(g.away, g.away_rec, g.winner === g.away.abbr, false), el('div', { class: 'sc' }, g.done ? String(g.ap) : ''),
      tm(g.home, g.home_rec, g.winner === g.home.abbr, true), el('div', { class: 'sc' }, g.done ? String(g.hp) : ''),
      el('div', { class: 'note' }, (g.note || (g.done ? 'Final' : 'Upcoming')) + (g.box ? ' · Box Score →' : '')));
    if (g.box) { card.onclick = () => { location.hash = `#gameday/${v.week}`; }; card.style.cursor = 'pointer'; card.setAttribute('data-tip', 'Open the box score'); }
    grid.append(card);
  }
  s.append(grid);
  if(v.byes?.length && v.week <= 18) s.append(el('div',{class:'league-byes'},el('b',{},'BYE WEEK'),...v.byes.map(c=>clubLink(c.abbr,c.name)))); leagueFinish(s,page);
}

// REGRESSION: the season's losses stay in the table; each player's rating
// changes open in a compact card above the page.
function renderRegression(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.className = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Team'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'club'));
  secondRow(clubNav(v.club.abbr, true, null), '#club/regression');
  const s = reportBoard(v.club, 'REGRESSION', [[v.hit, 'PLAYERS DECLINED'], [v.total_lost ? `-${v.total_lost}` : '0', 'OVERALL POINTS']]);
  s.append(el('div', { class: 'report-controls' }, scheduleSeasonPicker(v, y => renderRegression(pyJSON(`SESSION.club_regression(year=${y})`))), el('span', { class: 'count' }, `Going into ${v.year + 1}`)));
  if (v.empty) { s.append(el('div', { class: 'empty' }, 'Regression is recorded during Retirements and Development.')); page.append(s); return; }
  // One row per player who lost overall; details open above the page.
  const tbl = el('table', { class: 'tbl' });
  tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Ovr Before'), el('th', { class: 'n' }, 'Ovr After'), el('th', { class: 'n' }, 'Regression'), el('th', {}, '')));
  if (!v.rows.length) tbl.append(el('tr', {}, el('td', { colspan: '6' }, el('div', { class: 'empty' }, 'Nobody on the club lost ground.'))));
  for (const r of v.rows) {
    tbl.append(el('tr', {},
      el('td', {}, el('button', { class: 'who', disabled: r.available === false ? '' : null, onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no', style: `background:${v.club.color};color:${v.club.accent || '#fff'}` }, r.no != null ? r.no : r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos} · ${r.age}${r.still_here ? '' : ' · no longer on the club'}`)))),
      el('td', {}, r.pos), el('td', { class: 'n' }, el('b', {}, r.before)), el('td', { class: 'n' }, el('b', {}, r.after)),
      el('td', { class: 'n' }, el('b', { style: 'color:var(--danger)' }, r.delta)),
      el('td', { class: 'acts' }, el('button', { class: 'btn', style: 'width:auto;padding:3px 10px;font-size:13.5px', onclick: () => regressionPopup(v, r) }, 'View Changes'))));
  }
  s.append(el('div', { class: 'report-table-scroll' }, tbl)); page.append(s);
}

// A compact player-style card showing only ratings that changed with age.
function regressionPopup(v, r) {
  const back = el('div', { class: 'popback reg-popback', onclick: e => { if (e.target === back) back.remove(); } });
  const box = el('section', { class: 'popbox reg-popbox', role: 'dialog', 'aria-modal': 'true', 'aria-label': `${r.name} rating changes`, style: `--reg-accent:${teamTheme(v.club).accent}` });
  const close = el('button', { class: 'btn', type: 'button', onclick: () => back.remove() }, 'Close');
  box.append(el('header', { class: 'reg-pop-head' },
    el('div', {}, el('small', {}, `${v.club.name} · REGRESSION`), el('h2', {}, r.name.toUpperCase()), el('p', {}, `${r.pos} · Age ${r.age} · Going into ${v.year + 1}`)),
    el('div', { class: 'reg-pop-score' }, el('span', {}, 'OVERALL'), el('strong', {}, `${r.before} → ${r.after}`), el('b', { class: r.delta < 0 ? 'loss' : 'gain' }, `${r.delta > 0 ? '+' : ''}${r.delta} OVR`)), close));
  if (r.partial) box.append(el('p', { class: 'reg-pop-note' }, 'This older record contains only ratings that changed.'));
  const groups = [], seen = new Set();
  const addGroup = (title, rows) => {
    const changed = rows.filter(a => a.delta && !seen.has(a.key));
    for (const a of changed) seen.add(a.key);
    if (changed.length) groups.push({ title, rows: changed });
  };
  for (const c of r.cols || []) {
    addGroup(c.title, c.rows || []);
    if (c.extra) addGroup(c.extra.title, c.extra.rows || []);
  }
  const grid = el('div', { class: 'reg-change-grid' });
  for (const group of groups) {
    const section = el('section', { class: 'reg-change-group' }, el('h3', {}, group.title));
    for (const a of group.rows) section.append(el('div', { class: 'reg-change-row' },
      el('span', {}, a.label), el('span', { class: 'reg-change-values' }, `${a.v - a.delta} → ${a.v}`),
      el('b', { class: a.delta < 0 ? 'loss' : 'gain' }, `${a.delta > 0 ? '+' : ''}${a.delta}`)));
    grid.append(section);
  }
  box.append(groups.length ? grid : el('p', { class: 'reg-pop-note' }, 'No whole-point rating changes were recorded.'));
  back.append(box); document.body.append(back);
  back.tabIndex = -1; back.focus();
  back.addEventListener('keydown', e => { if (e.key === 'Escape') back.remove(); });
}

// A TEAM'S SCHEDULE, under its own sub-tabs: the season as a strip of results, then one row a week with the
// opponent's stripe, home or away, the score and the result. Your own games open the box score.
function renderClubSchedule(v, mine) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.className = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Team'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'club'));
  secondRow(clubNav(v.team.abbr, mine, null), mine ? '#club/schedule' : `#league/team/${v.team.abbr}/schedule`);
  const s = reportBoard(v.team, 'SCHEDULE', [[v.record || '—', 'RECORD'], [(v.byes || []).join(', ') || '—', 'BYE WEEK']]);
  const teams=pyJSON('SESSION.club_list()');
  const load=(team,year)=>renderClubSchedule(pyJSON(`SESSION.league_view('team_schedule', team=${JSON.stringify(team)}, year=${Number(year)})`),!!teams.find(c=>c.abbr===team)?.mine);
  const controls=el('div',{class:'schedule-team-controls'},scheduleSeasonPicker(v,y=>load(v.team.abbr,y)),clubSelect(v.team.abbr,team=>load(team,v.year)));
  s.querySelector('.report-hero').append(controls);
  if (v.missing) { s.append(el('div', { class: 'empty' }, 'No schedule is kept for that season.')); page.append(s); return; }
  s.append(scheduleContent(v)); page.append(s);
}
function scheduleEntries(v) {
  const entries = new Map();
  for (const week of v.not_kept || []) entries.set(Number(week), {week:Number(week),missing:true});
  for (const week of v.byes || []) entries.set(Number(week), {week:Number(week),bye:true});
  for (const g of v.games || []) entries.set(Number(g.week), {week:Number(g.week),game:g});
  return [...entries.values()].sort((a,b)=>a.week-b.week);
}
function scheduleSeasonPicker(v,onChange) {
  const years=[...new Set([...(v.years||[]),v.year].map(Number))].filter(Number.isFinite).sort((a,b)=>b-a);
  const sel=el('select',{class:'btn','aria-label':'Schedule season',disabled:years.length<2?'':null,style:'width:auto;margin:8px 14px'});
  for(const year of years) sel.append(el('option',{value:year,selected:year===Number(v.year)?'':null},year));
  sel.onchange=()=>onChange(Number(sel.value)); return sel;
}
function scheduleContent(v) {
  const content = el('div', { class: 'schedule-report' });
  if (v.missing) {content.append(el('div',{class:'empty'},'No schedule is kept for that season.'));return content;}
  const strip = el('div', { class: 'rv-strip schedule-strip' });
  const list = el('div', { class: 'ts-list schedule-columns' });
  for(const entry of scheduleEntries(v)) {
    const g=entry.game;
    if(!g) {
      const label=entry.bye?'Bye':'Not kept in the record';
      strip.append(el('div',{class:'rv-g bye','data-tip':`${weekName(entry.week)} · ${label}`},el('small',{},entry.week),entry.bye?'BYE':'?'));
      list.append(el('div',{class:'ts-row bye'},el('span',{class:'wk'},weekName(entry.week)),el('span',{class:'opp'},label)));continue;
    }
    strip.append(el('div',{class:'rv-g '+(g.done?g.result.toLowerCase():''),'data-tip':`${weekName(g.week)} · ${g.opp.name}`},el('small',{},g.week),g.done?g.result:showAbbr(g.opp.abbr)));
    const row = el('div', { class: 'ts-row' + (g.done ? ' ' + g.result.toLowerCase() : '') + (g.box ? ' box' : ''), onclick: g.box ? event => { if (!event.target.closest('a')) location.hash = `#gameday/${g.week}`; } : null, style: g.box ? 'cursor:pointer' : '' },
      el('span', { class: 'wk', 'data-tip': g.week >= 19 ? weekName(g.week) : null }, g.week >= 19 ? ({ 19: 'WC', 20: 'DIV', 21: 'CONF', 22: 'Final' })[g.week] : `Wk ${g.week}`),
      el('span', { class: 'ha' }, g.home ? 'vs' : 'at'),
      el('span', { class: 'opp' }, clubLink(g.opp.abbr, g.opp.name), g.opp_rec ? el('small', {}, ` ${g.opp_rec}`) : ''),
      el('b', { class: 'res' }, g.done ? g.result : 'Upcoming'),
      el('span', { class: 'sc' }, g.done ? `${g.mine}–${g.theirs}` : ''));
    list.append(row);
  }
  content.append(strip,list); return content;
}
function renderTeamSchedule(v) {
  renderRail(v.rail); const page=persPage(); lgSecond('schedule');
  const s=reportBoard(v.team,'SCHEDULE',[[v.record||'—','RECORD']]);
  const load=(team,year)=>renderTeamSchedule(pyJSON(`SESSION.league_view('team_schedule', team=${JSON.stringify(team)}, year=${Number(year)})`));
  const sel=el('select',{class:'btn team-picker','aria-label':'Schedule team'});
  for(const c of v.clubs) sel.append(el('option',{value:c.abbr,selected:c.abbr===v.team.abbr?'':null},c.name));
  sel.onchange=()=>load(sel.value,v.year);
  s.querySelector('.report-hero').append(el('div',{class:'schedule-team-controls'},scheduleSeasonPicker(v,y=>load(v.team.abbr,y)),sel));
  s.append(el('div',{class:'report-controls'},el('button',{class:'btn',onclick:()=>renderSchedule(pyJSON(`SESSION.league_view('schedule', year=${Number(v.year)})`))},'League Schedule')),scheduleContent(v)); page.append(s);
}

let txGroup = 'All', txClub = 'all', txQuery = '', txShown = 60;
// THE SEASON REVIEW. The morning after: a hero in the club's colors with the record against the ask and the
// seventeen results as a strip, the owner's word, the units as ranked bars, the men who rose and fell as cards,
// next year's money as one bar, and the assistants' three notes.
function renderReview(v) {
  renderRail(v.rail); const page = persPage(); foSecond('review');
  const board=foBoard(v,'SEASON REVIEW'); page.append(board);
  board.append(foYears(v,y=>renderReview(pyJSON(`SESSION.frontoffice('season_review', year=${y})`))));
  const content=el('div',{class:'fo-review-content'}); board.append(content);
  if (v.missing) { content.append(el('section', { class: 'sheet c12' }, el('div', { class: 'empty' }, `No review was kept for ${v.year}.`))); return; }
  if (v.not_yet) { content.append(el('section', { class: 'sheet c12' }, el('div', { class: 'empty' }, `The ${v.year} review comes when the ${v.year} season is over.`))); return; }
  const c1 = v.club.color, c2 = v.club.accent || '#fff';
  const ordn = n => n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] || 'th');
  // hero
  const hero = el('section', { class: 'sheet c12 rv-hero', style: `--c1:${c1};--c2:${c2}` });
  const left = el('div', { class: 'rv-left' },
    el('div', { class: 'rv-kicker' }, `${v.year} · ${v.club.name}`),
    el('div', { class: 'rv-record' }, v.record),
    el('div', { class: 'rv-finish' }, `${v.finish}${v.div_rank ? ` · ${ordn(v.div_rank)} in the ${v.division}` : ''}${v.slot ? ` · pick ${v.slot}` : ''}`),
    v.expected ? el('div', { class: 'rv-ask' }, 'The owner asked for ', el('b', {}, v.expected), `. You finished at .${String(v.pct.toFixed(3)).slice(2)}.`) : el('div', { class: 'rv-ask' }, `You finished at .${String(v.pct.toFixed(3)).slice(2)}.${v.rebuilt ? ' Rebuilt from the record; the owner\'s word and the money were not kept.' : ''}`));
  const strip = el('div', { class: 'rv-strip' });
  for (const g of v.timeline) strip.append(g.bye ? el('div', { class: 'rv-g bye', 'data-tip': `${weekName(g.week)} · Bye` }, '') : el('div', { class: 'rv-g ' + g.result.toLowerCase(), 'data-tip': `${weekName(g.week)} · ${g.away ? 'at' : 'vs'} ${g.opp.name} · ${g.mine}–${g.theirs}` }, g.result));
  left.append(strip);
  const owner = v.owner ? el('div', { class: 'rv-owner' }, el('div', { class: 'rv-tag ' + v.owner.mood.toLowerCase() }, v.owner.mood), el('div', { class: 'rv-quote' }, v.owner.line), el('div', { class: 'rv-job' }, `Your seat: ${v.owner.job}`)) : el('div', { class: 'rv-owner' }, el('div', { class: 'rv-quote' }, 'The owner\'s word from that year was not kept.'));
  hero.append(left, owner); content.append(hero);
  // three columns
  const units = el('section', { class: 'sheet c4' }, el('h2', {}, 'The Units', el('small', {}, `offense ${v.sides.offense ? ordn(v.sides.offense) : '—'} · defense ${v.sides.defense ? ordn(v.sides.defense) : '—'}`)));
  if (!v.units.length) units.append(el('div', { class: 'count', style: 'padding:8px 14px' }, 'The unit grades from that year were not kept.'));
  const ub = el('div', { class: 'rv-units' });
  for (const u of v.units) { const r = u.rank || 32; const pct = 100 * (1 - (r - 1) / Math.max(1, u.of - 1)); ub.append(el('div', { class: 'rv-u' }, el('span', { class: 'lab' }, u.label), el('div', { class: 'bar' }, el('i', { style: `width:${pct}%;background:${r <= 8 ? 'var(--ok)' : r >= 24 ? 'var(--danger)' : 'var(--ink-3)'}` })), el('b', { class: r <= 8 ? 'good' : r >= 24 ? 'bad' : '' }, u.rank ? ordn(u.rank) : '—'))); }
  units.append(ub); content.append(units);
  const men = el('section', { class: 'sheet c4' }, el('h2', {}, 'The Players', el('small', {}, 'who rose, who fell')));
  const cardOf = p => el('div', { class: 'rv-card' + (p.up ? ' up' : ' down'), onclick: () => { location.hash = '#club/player/' + p.pid; }, style: 'cursor:pointer' }, el('div', { class: 'plate', style: `background:${c1};color:${c2}` }, p.no != null ? p.no : p.pos), el('div', { class: 'rv-body' }, el('div', { class: 'nm' }, p.name, el('small', {}, ` ${p.pos} · ${p.age}`)), el('div', { class: 'ln' }, p.line)), el('div', { class: 'rv-ovr' }, p.ovr));
  men.append(el('div', { class: 'h5', style: 'padding:6px 14px 0' }, 'Exceeded the grade')); for (const p of v.exceeded) men.append(cardOf(p));
  if (v.short.length) { men.append(el('div', { class: 'h5', style: 'padding:10px 14px 0' }, 'Fell short of it')); for (const p of v.short) men.append(cardOf(p)); }
  content.append(men);
  if (!v.cap) { content.append(el('section', { class: 'sheet c4' }, el('h2', {}, 'Next Year'), el('div', { class: 'count', style: 'padding:8px 14px' }, 'The money from that year was not kept.'))); return; }
  const money = el('section', { class: 'sheet c4' }, el('h2', {}, 'Next Year', el('small', {}, `$${v.cap.limit}m cap`)));
  const tot = Math.max(1, v.cap.limit); const w = x => `${Math.max(0, Math.min(100, 100 * x / tot)).toFixed(1)}%`;
  money.append(el('div', { class: 'rv-capbar' }, el('i', { class: 'com', style: `width:${w(v.cap.committed - v.cap.dead)}`, 'data-tip': `Committed $${(v.cap.committed - v.cap.dead).toFixed(1)}m` }), el('i', { class: 'dead', style: `width:${w(v.cap.dead)}`, 'data-tip': `Dead money $${v.cap.dead}m` }), el('i', { class: 'room', style: `width:${w(v.cap.room)}`, 'data-tip': `Room $${v.cap.room}m` })),
    el('div', { class: 'rv-caplegend' }, el('span', {}, el('i', { class: 'com' }), `Committed $${(v.cap.committed - v.cap.dead).toFixed(1)}m`), el('span', {}, el('i', { class: 'dead' }), `Dead $${v.cap.dead}m`), el('span', {}, el('i', { class: 'room' }), `Room $${v.cap.room}m`), v.cap.rollover ? el('span', { class: 'count' }, `incl. $${v.cap.rollover}m rollover`) : ''));
  money.append(el('div', { class: 'h5', style: 'padding:10px 14px 0' }, 'Deals up'));
  for (const p of v.pending) money.append(el('div', { class: 'rv-pend' + (p.starter ? ' starter' : ''), onclick: () => { location.hash = '#personnel/extensions'; }, style: 'cursor:pointer' }, el('span', { class: 'pos' }, p.pos), el('span', { class: 'nm' }, p.name, p.starter ? el('small', {}, ' · starter') : ''), el('b', {}, p.ovr), el('span', { class: 'apy' }, `$${p.apy}m`)));
  if (!v.pending.length) money.append(el('div', { class: 'count', style: 'padding:6px 14px' }, 'Nobody comes off contract.'));
  content.append(money);
}

// EXIT MEETINGS. A room, one man at a time: his question in his own words, his contract on the table, and your
// answers with what each one costs. Once you answer, his reply stays on the card.
let exitSelected = null;
function renderExit(v) {
  renderRail(v.rail); const page=persPage(); foSecond('exit');
  const meetings=v.meetings || [], pending=meetings.filter(m=>!m.answer).length;
  const board=foBoard(v,'EXIT MEETINGS',meetings.length ? [[pending,'Open'],[meetings.length-pending,'Answered']] : []);
  board.append(foYears(v,y=>renderExit(pyJSON(`SESSION.frontoffice('exit_interviews', year=${y})`))),el('p',{class:'count'},'Each player will remember what you tell him. A promise goes on the ledger.')); page.append(board);
  if(!meetings.length) { board.append(el('div',{class:'empty fo-empty'},(v.not_yet || v.pending) ? `The ${v.year} meetings come after your team's season.` : v.missing ? `No meetings were kept for ${v.year}.` : 'Nobody asked for a meeting this year.')); return; }
  if(!meetings.some(m=>m.pid===exitSelected)) exitSelected=meetings.find(m=>!m.answer)?.pid || meetings[0].pid;
  const queue=el('div',{class:'fo-queue'}), conversation=el('div',{class:'fo-conversation'});
  const draw=()=>{
    queue.replaceChildren(el('div',{class:'h5'},'MEETING QUEUE')); conversation.replaceChildren();
    for(const m of meetings) queue.append(el('button',{class:'fo-meeting'+(m.pid===exitSelected?' selected':''),onclick:()=>{exitSelected=m.pid;draw();}},el('b',{},m.no ?? m.pos),el('span',{},m.name,el('small',{},m.pos)),el('small',{},m.answer?'Answered':'Open')));
    const m=meetings.find(x=>x.pid===exitSelected);
    conversation.append(el('div',{class:'xm-who'},el('div',{class:'plate',style:'background:var(--report-team);color:var(--ink)'},m.no ?? m.pos),el('div',{},el('button',{class:'fo-player-link',onclick:()=>{location.hash='#club/player/'+m.pid;}},m.name),el('div',{class:'ln'},`${m.pos} · ${m.age} · ${m.ovr} OVR · ${m.years ? `${m.years} years left at $${m.apy}m` : 'Contract up'}`))),el('div',{class:'xm-quote'},m.quote));
    if(m.answer) {const option=m.options.find(o=>o.key===m.answer); conversation.append(el('div',{class:'xm-said'},el('p',{},'You: ',el('b',{},option?.label || m.answer)),el('p',{},m.said || ''))); return;}
    if(v.past) {conversation.append(el('p',{class:'count'},'No response was recorded.'));return;}
    const options=el('div',{class:'xm-opts'}); let selected=null;
    const submit=el('button',{class:'btn go',disabled:'',onclick:()=>{if(!selected)return;const r=pyJSON(`SESSION.exit_answer(${JSON.stringify(m.pid)}, ${JSON.stringify(selected)})`);if(!r.ok)notify(r);renderExit(pyJSON(`SESSION.frontoffice('exit_interviews')`));}},'Give Response');
    for(const o of m.options) options.append(el('button',{class:'xm-opt','aria-pressed':'false',onclick:e=>{selected=o.key;options.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed','false'));e.currentTarget.setAttribute('aria-pressed','true');submit.disabled=false;}},el('b',{},o.label),el('span',{},o.sub)));
    conversation.append(el('div',{class:'h5'},'CHOOSE YOUR RESPONSE'),options,el('div',{class:'foot'},submit));
  };
  board.append(el('div',{class:'fo-meetings'},queue,conversation));draw();
}

// the playoff bracket: seeds down the side, the rounds across, scores as they land
function renderBracket(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('bracket');
  const s = leagueBoard(v, 'PLAYOFFS', v.champion ? `Champion: ${v.champion.name}` : v.live ? 'Live postseason' : v.note || '');
  s.append(leagueYear(v, y => renderBracket(pyJSON(`SESSION.league_view('bracket', year=${y})`))));
  if (v.missing) { s.append(el('div', { class: 'empty' }, v.note || 'No bracket is kept for that season.')); leagueFinish(s,page); return; }
  s.append(el('div', { class: 'league-playoffs' }, bracketTree(v)),
    el('p',{class:'league-note'},'Division winners seed 1–4. Top seed receives a bye. Divisional round reseeds.'));
  leagueFinish(s,page);
}

// the bracket itself, so the portal can show it during the playoffs without the page chrome
function bracketTree(v) {
  // one team's line on a card: seed, stripe, abbreviation, score; the winner carries the marker, the loser dims
  const line = (c, seed, pts, done, won, me, record) => el('div', { class: 'bk-line' + (done ? (won ? ' win' : ' lose') : '') + (me ? ' me' : '') },
    el('span', { class: 'sd' }, seed || ''), el('span', { class: 'str', style: `background:${c.color}` }), el('span', { class: 'ab' }, showAbbr(c.abbr)), el('span', { class: 'rec' }, done ? '' : record || ''), el('b', {}, done ? (won ? '▸ ' : '') + pts : ''));
  const gameCard = (g, cls) => g ? el('div', { class: 'bk-game ' + (cls || '') + (g.me ? ' mine' : '') + (g.done ? ' done' : ''), style: `--match-accent:${g.done ? (g.winner === g.home.abbr ? g.home.accent : g.away.accent) : g.home.accent};--match-base:${g.done ? (g.winner === g.home.abbr ? g.home.color : g.away.color) : g.home.color}` },
    line(g.away, g.away_seed, g.as_, g.done, g.winner === g.away.abbr, g.away.abbr === v.rail.club.abbr, g.away_record),
    line(g.home, g.home_seed, g.hs, g.done, g.winner === g.home.abbr, g.home.abbr === v.rail.club.abbr, g.home_record),
    el('div', { class: 'foot' }, g.done ? 'Final' : g.round === 'SB' ? '' : `at ${g.home.name}`, g.round === 'SB' ? '' : el('span', {}, g.stadium || '')))
    : el('div', { class: 'bk-game tbd ' + (cls || '') }, el('div', { class: 'bk-line' }, el('span', { class: 'sd' }, ''), el('span', { class: 'str' }), el('span', { class: 'ab' }, 'TBD')), el('div', { class: 'bk-line' }, el('span', { class: 'sd' }, ''), el('span', { class: 'str' }), el('span', { class: 'ab' }, 'TBD')), el('div', { class: 'foot' }, 'to be decided'));
  const byeCard = (b, cls) => b ? el('div', { class: 'bk-game bye ' + cls + (b.me ? ' mine' : ''), style: `--match-accent:${b.club.accent};--match-base:${b.club.color}` }, line(b.club, 1, null, false, false, b.me, null), el('div', { class: 'foot' }, 'First-round bye')) : el('div', { class: cls });
  const tree = el('div', { class: 'bk-tree' });
  const side = (c, flip) => {
    // three wild card games plus the bye in one column; two divisional games; the championship. Rows are the tree's
    // 8 half-rows: a wild card slot spans 2, a divisional slot 4, the championship 8; the joins sit in the gap columns
    const f = flip ? ' r' : '';
    const wc = [byeCard(c.bye, 'bk-slot s2' + f), ...[0, 1, 2].map(i => gameCard(c.wc[i], 'bk-slot s2' + f))];
    const dv = [0, 1].map(i => gameCard(c.div[i], 'bk-slot s4' + f));
    const cf = gameCard(c.conf_game, 'bk-slot s8' + f);
    const cols = [el('div', { class: 'bk-col', 'data-name': 'Wild Card' }, ...wc), el('div', { class: 'bk-join j2' + f }, el('i', {}), el('i', {})), el('div', { class: 'bk-col', 'data-name': 'Divisional' }, ...dv), el('div', { class: 'bk-join j4' + f }, el('i', {})), el('div', { class: 'bk-col', 'data-name': c.conf + ' Championship' }, cf)];
    return flip ? cols.reverse() : cols;
  };
  const continental = v.confs.find(c => c.conf === 'Continental') || v.confs[0]; const united = v.confs.find(c => c.conf === 'United') || v.confs[1];
  if (continental) tree.append(...side(continental, false));
  // the middle: the Championship Game, its site, the champion beneath it
  const sb = el('div', { class: 'bk-col bk-final', 'data-name': `Championship Game ${v.site ? v.site.numeral : ''}` },
    el('div', { class: 'bk-slot s8' }, el('div', { class: 'bk-site' }, v.site ? `${v.site.stadium} · ${v.site.city}` : ''), gameCard(v.final, 'sb'),
      v.champion ? el('div', { class: 'bk-champ', style: `--c1:${v.champion.color};--c2:${v.champion.accent}` }, el('span', {}, v.champion.name), el('small', {}, 'Champions')) : ''));
  tree.append(el('div', { class: 'bk-join j8' }, el('i', {})), sb, el('div', { class: 'bk-join j8 r' }, el('i', {})));
  if (united) tree.append(...side(united, true));
  return el('div', { class: 'bk-scroll' }, tree);
}

function coachingMoveRow(c) {
  const theme = teamTheme(c.club);
  return el('div', { class: 'league-coach-move', style: `--coach-color:${theme.accent};--coach-readable:${theme.readable};--coach-base:${theme.base}` },
    el('span', { class: 'year' }, String(c.year)),
    el('div', { class: 'club' }, clubLink(c.club.abbr, c.club.name)),
    el('span', { class: 'action' }, c.action),
    el('div', { class: 'person' }, el('b', {}, c.person), el('small', {}, c.role)),
    el('span', { class: 'detail' }, c.detail || ''));
}
function filteredTransactions(v) {
  const q = txQuery.trim().toLowerCase();
  const rows = txGroup === 'Coaching' ? (v.coaching_moves || []).map(c => ({...c, team:c.club, mine:c.club.abbr === v.rail.club.abbr,
    group:'Coaching', tag:c.action, line:`${c.club.name} ${c.action}: ${c.person} · ${c.role}${c.detail ? ' · '+c.detail : ''}`, coaching:true})) : v.rows;
  return rows.filter(r => (txGroup === 'All' || r.group === txGroup) &&
    (txClub === 'all' || (txClub === 'mine' && r.mine) || (txClub === 'div' && (r.divisions || [r.division]).includes(v.my_division))) &&
    (!q || [r.line, showTeamText(r.line), r.team?.name, r.team?.abbr, showAbbr(r.team?.abbr), r.person, r.role, r.tag, r.detail, r.detail_secondary].filter(Boolean).join(' ').toLowerCase().includes(q)));
}
function transactionWhen(r) {
  if (r.period) return r.period;
  if (['offseason', 'free_agency', 'draft'].includes(r.phase)) return 'Offseason';
  if (r.phase === 'preseason') return 'Preseason';
  if (r.week) return ({19:'Wild Card',20:'Divisional Round',21:'Conference Championship',22:'Championship Game'})[r.week] || `Week ${r.week}`;
  return r.phase ? r.phase.charAt(0).toUpperCase() + r.phase.slice(1).replaceAll('_', ' ') : '';
}
function renderTransactions(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('transactions');
  const copyTx = el('button', { class: 'btn quiet transaction-copy', 'data-tip': 'Copy the list as filtered, every entry, as text', onclick: () => {
    const lines = filteredTransactions(v).map(r => [r.year, transactionWhen(r), r.tag, showTeamText(r.line)].filter(Boolean).join(' · '));
    copyText(lines.join('\n'), copyTx); } }, 'Copy');
  const s = leagueBoard(v, 'TRANSACTIONS', ''); s.classList.add('transactions-board');
  const tabs = el('div', { class: 'tabs transaction-tabs' });
  for (const g of ['All', ...v.groups]) tabs.append(el('button', { 'aria-pressed': String(txGroup === g), onclick: () => { txGroup = g; txShown = 60; renderTransactions(v); } }, g));
  const clubs = el('div', { class: 'chips' }); for (const [k, label] of [['all', 'All Teams'], ['mine', v.rail.club.name], ['div', v.my_division]]) clubs.append(el('button', { class: 'chip', 'aria-pressed': String(txClub === k), onclick: () => { txClub = k; txShown = 60; renderTransactions(v); } }, label));
  const search = el('input', { type: 'search', class: 'find', 'aria-label':'Find a player, coach or team', placeholder: 'Find a player, coach or team', value: txQuery }); search.oninput = () => { txQuery = search.value; txShown = 60; draw(); };
  s.append(tabs, el('div', { class: 'tools' }, clubs, search, copyTx));
  const list = el('div', {class:'league-transactions'}); s.append(list);
  const draw = () => {
    list.innerHTML = ''; const rows = filteredTransactions(v);
    list.classList.toggle('league-coach-moves', txGroup === 'Coaching');
    if (txGroup !== 'Coaching' && rows.length) list.append(el('div',{class:'transaction-columns','aria-hidden':'true'},...['WHEN','TEAM','MOVE','PLAYER / COACH','DETAILS',''].map(label=>el('span',{},label))));
    for (const r of rows.slice(0, txShown)) {
      if (r.coaching) { list.append(coachingMoveRow(r)); continue; }
      const link = r.link === 'trade' ? el('a', { class: 'transaction-open', href: '#personnel/trades', 'aria-label':'Open trades', 'data-tip':'Open trades' }, '›') : r.link === 'carousel' ? el('button', { class:'transaction-open', 'aria-label':'View coaching transactions', 'data-tip':'View coaching transactions', onclick:()=>{txGroup='Coaching';txShown=60;renderTransactions(v);} }, '›') : el('span', {});
      const theme = teamTheme(r.team || {});
      list.append(el('div', { class: 'transaction-row', style:`--transaction-base:${theme.base};--transaction-accent:${theme.accent};--transaction-readable:${theme.readable}` },
        el('time', {}, String(r.year ?? ''), el('small',{},transactionWhen(r))),
        el('div',{class:'transaction-team'},r.team ? clubLink(r.team.abbr,r.team.name) : 'League',el('small',{},r.team ? `${showAbbr(r.team.abbr)}${r.team.abbr === v.rail.club.abbr?' · YOUR TEAM':''}` : '')),
        el('span',{class:'transaction-action'},r.tag),
        el('div',{class:'transaction-person'},el('b',{},r.pid ? el('a',{class:'entity-link',href:'#club/player/'+encodeURIComponent(r.pid),onclick:e=>e.stopPropagation()},r.person || r.line) : r.person || r.line),el('small',{},r.role || '')),
        el('div',{class:'transaction-detail'},r.detail || '',r.detail_secondary ? el('small',{},r.detail_secondary) : ''),link));
    }
    if (!rows.length) list.append(el('div', { class: 'empty' }, 'Nothing matches.'));
    if (rows.length) list.append(el('div', { class: 'foot' }, rows.length > txShown ? el('button', { class: 'btn quiet', onclick: () => { txShown += 60; draw(); } }, 'Older') : '', el('span', { class: 'count' }, `${Math.min(txShown, rows.length)} of ${rows.length}`),el('span',{class:'count',style:'margin-left:auto'},'Most recent first')));
  };
  draw(); leagueFinish(s,page);
}

let statsTab = 'Leaders';
function statsTeamRow(tag, player, ...children) {
  const row = el(tag, { class: 'stats-team-row' + (tag === 'div' ? ' lrow' : '') }, ...children);
  applyTeamTheme(row, player.club || { abbr: player.team });
  return row;
}
function renderStats(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('stats');
  const s = leagueBoard(v, 'STATS', `${v.year} · Through Week ${v.week ?? '—'}`);
  s.classList.add('stats-board');
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); for (const k of ['Leaders', 'Passing', 'Rushing', 'Receiving', 'Defense', 'Blocking', 'Advanced', 'Team']) tabs.append(el('button', { 'aria-pressed': String(statsTab === k), onclick: () => { statsTab = k; renderStats(v); } }, k));
  const yrs=el('div',{class:'league-year-tools'},leagueYear(v,y=>renderStats(pyJSON(`SESSION.league_view('stats', year=${y})`))),el('a',{class:'btn',href:'#league/almanac'},'Career Stats →'));
  tabs.append(yrs); s.append(tabs);
  if(v.note) s.append(el('div',{class:'read'},v.note));
  const nm = r => el('div', { class: 'nm', style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + r.pid; } }, r.name, el('small', {}, `${r.pos} · ${showAbbr(r.team)}`));
  if (statsTab === 'Leaders' || statsTab === 'Advanced') {
    const boxes = statsTab === 'Leaders' ? v.boxes : v.advanced;
    const grid = el('div', { class: 'leaders' });
    for (const b of boxes) { const box = el('div', { class: 'lbox' }, el('h4', {}, b.title, el('small', {}, b.unit || ''))); if (b.note) box.append(el('p', { class: 'muted', style: 'padding:0 12px;font-size:12px;line-height:1.5' }, b.note)); b.rows.slice(0, 5).forEach((r, i) => box.append(statsTeamRow('div', r, el('span', { class: 'r' }, i + 1), nm(r), el('span', { class: 'v' }, r.v)))); grid.append(box); }
    if (!boxes.length) grid.append(el('div', { class: 'empty' }, 'No games played this season yet.'));
    s.append(grid);
  } else if (statsTab === 'Team') {
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Team'), el('th', { class: 'n' }, 'PF/G'), el('th', { class: 'n' }, 'PA/G'), el('th', { class: 'n' }, 'Yds/G'), el('th', { class: 'n' }, 'Pass/G'), el('th', { class: 'n' }, 'Rush/G'), el('th', { class: 'n' }, 'EPA/Play'), el('th', { class: 'n' }, 'Sacks'), el('th', { class: 'n' }, 'INT')));
    if(!v.team.length) t.append(el('tr',{},el('td',{colspan:'9'},'Team statistics were not retained for this season.')));
    for (const r of v.team) t.append(statsTeamRow('tr', r, el('td', {}, clubLink(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.pf), el('td', { class: 'n' }, r.pa), el('td', { class: 'n' }, r.ypg), el('td', { class: 'n' }, r.pyds), el('td', { class: 'n' }, r.ryds), el('td', { class: 'n', style: r.epa > 0 ? 'color:var(--ok)' : r.epa < 0 ? 'color:var(--danger)' : '' }, (r.epa > 0 ? '+' : '') + r.epa.toFixed(2)), el('td', { class: 'n' }, r.sacks), el('td', { class: 'n' }, r.ints)));
    s.append(t);
  } else {
    const tb = v.tables[statsTab.toLowerCase()];
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', { class: 'n' }, '#'), el('th', {}, 'Player'), el('th', {}, 'Team'), ...tb.cols.map(c => el('th', { class: 'n' }, c))));
    tb.rows.forEach((r, i) => t.append(statsTeamRow('tr', r, el('td', { class: 'n' }, i + 1), el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name))), el('td', {}, r.team ? stripe(r.team) : ''), ...r.row.map(x => el('td', { class: 'n' }, String(x))))));
    if (!tb.rows.length) t.append(el('tr', {}, el('td', { colspan: String(3 + tb.cols.length) }, el('div', { class: 'empty' }, 'No games played this season yet.'))));
    s.append(t);
  }
  leagueFinish(s,page);
}

let allProTab='All-Pro First Team';
function renderAwards(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('awards');
  const s = leagueBoard(v, 'AWARDS', '');
  s.append(leagueYear(v,y=>renderAwards(pyJSON(`SESSION.league_view('awards', year=${y})`))));
  if (v.note && !v.rows.length) { s.append(el('div', { class: 'empty' }, v.note)); leagueFinish(s,page); return; }
  const grid = el('div', { class: 'league-awards' });
  for (const r of v.rows) grid.append(el('div', { class: 'aw' + (r.mine ? ' mine' : ''), style: `--award-accent:${r.team?.accent || '#71909f'};--award-base:${r.team?.color || '#22323d'}` }, el('div', { class: 'code' }, r.code || ''), el('div', { class: 'a' }, r.award), el('div', { class: 'nm', style: r.pid ? 'cursor:pointer' : '', onclick: () => { if (r.pid) location.hash = '#club/player/' + r.pid; } }, r.name), el('div', { class: 'tm' }, r.team ? clubLink(r.team.abbr, r.team.name) : ''), el('div', { class: 'ln' }, `${r.pos ? r.pos + ' · ' : ''}${r.line || ''}`)));
  s.append(grid);
  const apTabs=el('div',{class:'tabs'}); s.append(apTabs);
  for (const [title, list] of [['All-Pro First Team', v.first], ['All-Pro Second Team', v.second]]) {
    if (!list || !list.length) continue;
    const selected=title===allProTab;
    apTabs.append(el('button',{'aria-pressed':String(selected),onclick:()=>{allProTab=title;renderAwards(v);}},title));
    if(!selected) continue;
    const two = el('div', { class: 'two ap-two' });
    for (const side of ['Offense', 'Defense']) {
      const t = el('table', { class: 'tbl league-allpro' }); t.append(el('tr', {}, el('th', {}, side), el('th', {}, 'Player'), el('th', {}, 'Team')));
      const isOff = p => ['QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT', 'K', 'P'].includes(p);
      const players = list.filter(x => isOff(x.pos) === (side === 'Offense'));
      if (side === 'Offense' && title === 'All-Pro Second Team' && !players.some(x => x.pos === 'FB')) {
        const hb = players.findIndex(x => x.pos === 'HB');
        players.splice(hb < 0 ? 0 : hb + 1, 0, { pos: 'FB', name: 'No eligible selection', empty: true });
      }
      for (const x of players) t.append(el('tr', { class: x.mine ? 'mine' : '' }, el('td', {}, x.pos), el('td', {}, x.empty ? el('span', { class: 'league-allpro-empty' }, x.name) : el('button', { class: 'league-allpro-player', onclick: () => { location.hash = '#club/player/' + x.pid; } }, x.name)), el('td', { class: 'team-cell' }, x.team ? clubLink(x.team.abbr, x.team.name) : '')));
      two.append(t);
    }
    s.append(two);
  }
  leagueFinish(s,page);
}

let coachTab = 'seats';
function renderCoaching(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('coaching');
  const s = leagueBoard(v, 'COACHING', v.note || '');
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); for (const [k, l] of [['seats', 'The Seats'], ['pool', 'The Pool']]) tabs.append(el('button', { 'aria-pressed': String(coachTab === k), onclick: () => { coachTab = k; renderCoaching(v); } }, l)); s.append(tabs);
  if (coachTab === 'seats') {
    const layout=el('div',{class:'league-coach-layout'}), detail=el('aside',{class:'league-coach-detail'});
    const t=el('table',{class:'tbl'}); t.append(el('tr',{},...['Team','Head Coach','Tenure','Record','Prestige','Job Security'].map(x=>el('th',{},x))));
    const select=r=>{
      for(const row of t.querySelectorAll('[data-team]')) row.classList.toggle('league-selected',row.dataset.team===r.club.abbr);
      detail.replaceChildren(el('div',{class:'h5'},'SELECTED COACH'),el('small',{},r.club.name),el('h2',{},r.coach),el('div',{class:'league-coach-metrics'},el('b',{},r.prestige ?? '—'),el('span',{},`Prestige · ${r.tenure+1}${ord(r.tenure+1)} year · ${r.record}`)),el('p',{},r.note || r.seat),el('div',{class:'h5'},'TEAM COACHING HISTORY'));
      for(const h of r.history || []) detail.append(el('div',{class:'league-coach-history'},el('b',{},h.name),el('span',{},`${h.frm ?? '—'}–${h.to ?? 'Present'}${h.record ? ' · '+h.record : ''}`)));
      if(!r.history?.length) detail.append(el('p',{},'No earlier coaching history retained.'));
    };
    for(const r of v.seats) t.append(el('tr',{'data-team':r.club.abbr},el('td',{},clubLink(r.club.abbr,r.club.name)),el('td',{},el('button',{class:'league-coach-button',onclick:()=>select(r)},r.coach)),el('td',{},`${r.tenure+1}${ord(r.tenure+1)} year`),el('td',{},r.record),el('td',{class:'n'},r.prestige ?? '—'),el('td',{},el('span',{class:'seat '+r.seat.toLowerCase().replace(' ','')},r.seat))));
    layout.append(t,detail);s.append(layout);if(v.seats.length)select(v.seats.find(r=>r.me || r.mine)||v.seats[0]);
  } else if (coachTab === 'pool') {
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Coach'), el('th', {}, 'Background'), el('th', { class: 'n' }, 'Prestige'), el('th', { class: 'n' }, 'Age')));
    for (const c of v.pool) t.append(el('tr', {}, el('td', {}, c.name), el('td', {}, c.background || ''), el('td', { class: 'n' }, c.prestige ?? '—'), el('td', { class: 'n' }, c.age ?? '—')));
    if (!v.pool.length) t.append(el('tr', {}, el('td', { colspan: '4' }, el('div', { class: 'empty' }, 'The pool fills as the season ends.'))));
    s.append(t);
  }
  leagueFinish(s,page);
}

let almTab = 'records';
function renderAlmanac(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('almanac');
  const s = leagueBoard(v, 'ALMANAC', v.note || `${v.seasons.length} seasons on record`);
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); for (const [k, l] of [['records', 'Records'], ['careers', 'Career Leaders'], ['hall', 'Hall of Fame'], ['champions', 'Champions'], ['ledger', 'Coaching Ledger']]) tabs.append(el('button', { 'aria-pressed': String(almTab === k), onclick: () => { almTab = k; renderAlmanac(v); } }, l)); s.append(tabs);
  if (almTab === 'records') {
    const two = el('div', { class: 'two league-records' });
    const rs = el('div', {}, el('div', { class: 'h5' }, 'Single Season', el('span', {}, 'Since 2026'))); const rc = el('div', {}, el('div', { class: 'h5' }, 'Career', el('span', {}, 'Active players highlighted')));
    for (const r of v.records) {
      if (r.season) rs.append(el('div', { class: 'lrow' }, el('div', { class: 'nm' }, r.stat, el('small', {}, `${r.season.name} · ${showAbbr(r.season.team)} · ${r.season.year}`)), el('span', { class: 'v' }, r.season.v)));
      if (r.career) rc.append(el('div', { class: 'lrow' }, el('div', { class: 'nm', style: r.career.active ? 'color:var(--club-2)' : '' }, r.stat, el('small', {}, `${r.career.name} · ${showAbbr(r.career.team)}`)), el('span', { class: 'v' }, r.career.v)));
    }
    if (!v.records.length) rs.append(el('div', { class: 'empty' }, 'Records are set as seasons close.'));
    two.append(rs, rc); s.append(two);
  } else if (almTab === 'careers') {
    const cg = el('div', { class: 'leaders' });
    for (const c of v.careers) { if (!c.rows.length) continue; const box = el('div', { class: 'lbox' }, el('h4', {}, c.title)); c.rows.forEach((r, i) => box.append(el('div', { class: 'lrow', style: r.mine ? 'background:var(--sheet-2)' : '' }, el('span', { class: 'r' }, i + 1), el('div', { class: 'nm', style: `cursor:pointer;${r.active ? 'color:var(--club-2)' : ''}`, onclick: () => { location.hash = '#club/player/' + r.pid; } }, r.name, el('small', {}, r.pos)), el('span', { class: 'v' }, r.v)))); cg.append(box); }
    s.append(cg);
  } else if (almTab === 'hall') {
    s.append(el('div', { class: 'h5', style: 'padding:10px 14px 0' }, 'Hall of Fame', el('span', {}, 'Voted Five Offseasons After Retirement')));
    const hall = el('div', { class: 'hall' });
    for (const h of v.hall) hall.append(el('div', { class: 'bust' }, el('div', { class: 'nm' }, h.name), el('div', { class: 'meta' }, `${h.pos}${h.clubs ? ' · ' + h.clubs : ''}${h.span ? ' · ' + h.span : ''}`), el('div', { class: 'why' }, h.why), el('div', { class: 'meta' }, `Inducted ${h.inducted}${h.first_ballot ? ' · First Ballot' : ''}`)));
    if (!v.hall.length) hall.append(el('div', { class: 'empty' }, 'Nobody has been inducted yet. A retired player is eligible five offseasons after he stops.'));
    s.append(hall);
    s.append(el('div', { class: 'read', style: 'margin:0 14px 14px' }, el('b', {}, `Next Ballot · ${v.next_ballot.year}: `), v.next_ballot.names.length ? `${v.next_ballot.names.join(', ')} eligible.` : 'Nobody comes eligible next offseason.'));
  } else if (almTab === 'champions') {
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Season'), el('th', {}, 'Champion'), el('th', {}, ''), el('th', {}, 'Runner-Up'), el('th', {}, 'Score')));
    for (const x of v.seasons) t.append(el('tr', { style: x.mine ? 'background:var(--sheet-2)' : '' }, el('td', {}, x.year), el('td', {}, x.champion ? clubLink(x.champion.abbr, x.champion.name) : '—'), el('td', {}, 'over'), el('td', {}, x.runner_up ? clubLink(x.runner_up.abbr, x.runner_up.name) : '—'), el('td', {}, x.score || '')));
    if (!v.seasons.length) t.append(el('tr', {}, el('td', { colspan: '5' }, el('div', { class: 'empty' }, 'The first champion is crowned in February.'))));
    s.append(t);
  } else {
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Team'), el('th', {}, 'Coach'), el('th', { class: 'n' }, 'From'), el('th', { class: 'n' }, 'To'), el('th', {}, 'Record')));
    for (const x of v.ledger) t.append(el('tr', {}, el('td', {}, clubLink(x.club.abbr, x.club.name)), el('td', {}, x.name), el('td', { class: 'n' }, x.frm ?? '—'), el('td', { class: 'n' }, x.current ? 'now' : (x.to ?? '—')), el('td', {}, x.record || '')));
    if (!v.ledger.length) t.append(el('tr', {}, el('td', { colspan: '5' }, el('div', { class: 'empty' }, 'The ledger fills as coaches come and go.'))));
    s.append(t);
  }
  leagueFinish(s,page);
}

// ---------------------------------------------------------------- Game Plan
let gameplanState = null, gameplanPendingDepth = null, gameplanSaving = false;
function updateGameplanState(state) {
  if (gameplanState?.key !== state.key) gameplanPendingDepth = null;
  gameplanState = state;
}
function gameplanUnsaved() { return !!(gameplanState?.dirty || gameplanPendingDepth); }
function syncGameplanState() {
  if (py) updateGameplanState(pyJSON("SESSION.plan_view('status')"));
}
function flushGameplanDepth() {
  if (!gameplanPendingDepth) return true;
  const [short, medium, deep] = gameplanPendingDepth;
  if (![short, medium, deep].every(Number.isFinite)) {
    notify({ ok: false, why: 'Enter three valid depth-of-target percentages.' }); return false;
  }
  const result = pyJSON(`SESSION.plan_act('set_depth', short=${short}, medium=${medium}, deep=${deep})`);
  if (!result.ok) { notify(result); return false; }
  gameplanPendingDepth = null;
  return true;
}
async function saveSundayPlan(reload) {
  if (gameplanSaving || !flushGameplanDepth()) return;
  const result = pyJSON("SESSION.plan_act('save')");
  if (!result.ok) { notify(result); return; }
  gameplanSaving = true;
  try {
    reload();
    await saveGame();
    notify({ ok: true, line: 'Game plan saved for Sunday.' });
  } catch (error) {
    pyJSON("SESSION.plan_act('save_failed')");
    notify({ ok: false, why: 'Your game plan could not be saved. Your choices are still here; please save again.' });
  } finally { gameplanSaving = false; reload(); }
}
function gameplanSaveControl(v, reload, label = 'Save Plan for Sunday') {
  if (v.plan_state?.started) return el('span', { class: 'count' }, 'Game started · Plan locked');
  return v.plan_state?.locked
    ? el('button', { class: 'btn go', disabled: gameplanSaving ? '' : null, onclick: () => { notify(pyJSON("SESSION.plan_act('reopen')")); reload(); } }, 'Re-Open Game Plan')
    : el('button', { class: 'btn go', onclick: () => saveSundayPlan(reload) }, label);
}
function warnUnsavedGameplan() {
  if ($('#gameplan-warning')) return;
  const dialog = el('dialog', { id: 'gameplan-warning', 'aria-labelledby': 'gameplan-warning-title', style: 'max-width:480px;background:var(--board);color:var(--ink);border:1px solid var(--rule-2);border-radius:12px;padding:24px' });
  const back = el('button', { class: 'btn go', onclick: () => { dialog.close(); location.hash = '#gameplan/week'; } }, 'Return to Game Plan');
  dialog.append(el('h2', { id: 'gameplan-warning-title' }, gameplanSaving ? 'Saving game plan' : 'Game plan not saved'),
    el('p', {}, gameplanSaving ? 'Please wait for your game plan to finish saving.' : 'You have not saved your game plan. Save Plan for Sunday before leaving so your choices are locked in.'), back);
  dialog.addEventListener('close', () => dialog.remove(), { once: true });
  document.body.append(dialog); dialog.showModal(); back.focus();
}
function guardGameplanRoute(event) {
  const oldHash = new URL(event.oldURL).hash;
  if (!oldHash.startsWith('#gameplan') || location.hash.startsWith('#gameplan')) return false;
  syncGameplanState();
  if (!gameplanUnsaved() && !gameplanSaving) return false;
  history.replaceState(null, '', event.oldURL);
  warnUnsavedGameplan();
  return true;
}
window.addEventListener('beforeunload', event => {
  if (!gameplanUnsaved() && !gameplanSaving) return;
  event.preventDefault(); event.returnValue = '';
});
// Catch links before changing the URL; hashchange also covers Back/Forward and script navigation.
document.addEventListener('click', event => {
  const a = event.target.closest?.('a[href]');
  if (!a || !location.hash.startsWith('#gameplan')) return;
  const target = new URL(a.href, location.href);
  if (target.origin === location.origin && target.pathname === location.pathname && target.hash.startsWith('#gameplan')) return;
  if (gameplanUnsaved() || gameplanSaving) { event.preventDefault(); event.stopImmediatePropagation(); warnUnsavedGameplan(); }
}, true);
const GPN = { week: 'This Week', practice: 'Practice', report: 'Opponent Report' };
function gpSecond(cur) { secondRow(Object.entries(GPN).map(([k, l]) => [l, '#gameplan/' + k]), '#gameplan/' + cur); $('#crumb').textContent = 'Game Plan'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'gameplan')); }
const pct = x => Math.round(x * 100);


let practiceSaving = false, practiceSaveRequired = false;
let practicePlayerUnit = 'offense';
function practiceFocus(plan, pid, checked) {
  const focus = plan.focus || [];
  if (checked && !focus.includes(pid) && focus.length >= 3) return false;
  plan.focus = checked ? [...new Set([...focus, pid])] : focus.filter(id => id !== pid);
  return true;
}
async function practiceCommand(action, plan, enabled) {
  if (practiceSaving) return false;
  practiceSaving = true;
  try {
    const args = action === 'auto' ? `, enabled=${enabled ? 'True' : 'False'}` : action === 'save' ? `, plan_json=${JSON.stringify(JSON.stringify(plan))}` : '';
    if (action !== 'retry') {
      const result = pyJSON(`SESSION.practice_act('${action}'${args})`);
      if (result?.ok === false || result?.error) { notify(result); return false; }
    }
    practiceSaveRequired = true;
    await saveGame();
    practiceSaveRequired = false;
    return true;
  } catch (error) {
    notify({ok:false, why:'Practice could not be saved. Retry Save before advancing. ' + String(error)});
    return false;
  } finally { practiceSaving = false; }
}
function renderPractice(v) {
  renderRail(v.rail); const page = persPage(); gpSecond('practice'); page.className = 'gameplan-page practice-page';
  featureHero(page, v.rail.club, `Week ${v.week || '—'} / Preparation`, 'PRACTICE', 'Balance preparation, development, and recovery.', [[v.completed ? 'Complete' : v.eligible ? 'Ready' : 'Inactive', 'This week']]);
  const surface = el('section', {class:'sheet c12 gameplan-surface practice-surface'}); page.append(surface);
  const reload = () => renderPractice(pyJSON('SESSION.practice_view()'));
  const plan = JSON.parse(JSON.stringify(v.plan || {units:{},individual:{},focus:[]})); plan.units ||= {}; plan.individual ||= {}; plan.focus ||= [];
  const locked = !v.eligible || v.completed;
  const select = (options, value, change) => {
    const control = el('select', {disabled:locked ? '' : null, onchange:e => change(e.target.value)});
    for (const [key,label] of options) control.append(el('option', {value:key, selected:key === value ? '' : null}, label));
    return control;
  };
  const management = el('input', {type:'checkbox', checked:v.auto ? '' : null, onchange:async e => { e.target.disabled = true; await practiceCommand('auto', null, e.target.checked); reload(); }});
  surface.append(el('div', {class:'practice-management'}, el('label', {}, management, ' Let assistants manage practice'), el('span', {class:'count'}, 'The same workload and development limits apply.')));
  if (v.note) surface.append(el('p', {class:'practice-note'}, v.note));
  if (!locked) {
    const units = el('div', {class:'practice-units'});
    for (const [unit,label] of [['offense','Offense'],['defense','Defense'],['special','Special teams']]) {
      const settings = plan.units[unit] ||= {intensity:'standard',reps:'balanced'};
      units.append(el('div', {}, el('h3', {}, label), el('label', {}, 'Intensity', select([['recovery','Recovery'],['light','Light'],['standard','Standard'],['hard','Hard']], settings.intensity, value => settings.intensity = value)), el('label', {}, 'Reps', select([['starters','Starter emphasis'],['balanced','Balanced'],['development','Development emphasis']], settings.reps, value => settings.reps = value))));
    }
    surface.append(units);
    surface.append(el('p', {class:'practice-note'}, 'Save your plan to update the forecast. Practice is only resolved when you run it.'));
  }
  if (!locked || v.completed) {
    const table = el('table', {class:'tbl practice-players'}, el('thead', {}, el('tr', {}, ...['Player','Position','Condition','Fatigue','Workload','Focus (up to 3)','XP / weekly max'].map(label => el('th', {}, label)))));
    const body = el('tbody'); table.append(body);
    for (const player of v.players || []) {
      const focus = el('input', {type:'checkbox', disabled:locked ? '' : null, 'aria-label':`Focus on ${player.name}`, checked:plan.focus.includes(player.pid) ? '' : null, onchange:e => { if (!practiceFocus(plan, player.pid, e.target.checked)) { e.target.checked = false; notify({ok:false,why:'Choose up to three focus players.'}); } }});
      body.append(el('tr', {}, el('td', {}, el('strong', {}, player.name), player.injured ? el('small', {}, 'Injured · restricted work') : null), el('td', {}, player.pos), el('td', {}, player.condition ?? '—'), el('td', {}, player.jaded ?? '—'), el('td', {}, select([['follow','Follow unit'],['limited','Limited'],['rest','Rest']], plan.individual[player.pid] || 'follow', value => { if (value === 'follow') delete plan.individual[player.pid]; else plan.individual[player.pid] = value; })), el('td', {}, focus), el('td', {class:'practice-xp', 'data-tip':player.xp_explanation || 'Save your plan to update projected XP.'}, player.practice_xp == null ? '—' : Math.round(player.practice_xp).toLocaleString(), el('small', {}, player.xp_ceiling == null ? '' : '/ ' + Number(player.xp_ceiling).toLocaleString()))));
    }
    const unitButtons = el('div', {class:'chips practice-unit-filter', 'aria-label':'Player unit'});
    const filterPlayers = () => {
      [...body.children].forEach((row, i) => { row.hidden = v.players[i].unit !== practicePlayerUnit; });
      [...unitButtons.children].forEach(button => button.setAttribute('aria-pressed', String(button.dataset.unit === practicePlayerUnit)));
    };
    for (const [unit, label] of [['offense','OFF'],['defense','DEF'],['special','ST']]) {
      unitButtons.append(el('button', {type:'button', class:'chip', 'data-unit':unit, onclick:() => { practicePlayerUnit = unit; filterPlayers(); }}, label));
    }
    filterPlayers();
    surface.append(el('details', {class:'practice-detail'}, el('summary', {}, 'Individual workloads & focus players'), unitButtons, el('div', {class:'practice-table-wrap'}, table)));
  }
  const report = v.completed ? v.result : v.preview;
  if (report) {
    const recap = el('div', {class:'practice-report'}, el('h3', {}, v.completed ? 'Practice report' : 'Saved plan forecast'));
    if (report.note) recap.append(el('p', {}, report.note));
    for (const line of report.summary || []) recap.append(el('p', {}, line));
    const metrics = el('div', {class:'practice-metrics'});
    for (const metric of report.metrics || []) metrics.append(el('div', {}, el('strong', {}, metric.value), el('span', {}, metric.label)));
    recap.append(metrics); surface.append(recap);
  }
  const actions = el('div', {class:'foot practice-actions'});
  if (practiceSaveRequired) actions.append(el('button', {class:'btn go', onclick:async () => { await practiceCommand('retry'); reload(); }}, 'Retry Save'));
  if (!locked) {
    actions.append(el('button', {class:'btn', onclick:async e => { e.target.disabled = true; await practiceCommand('save', plan); reload(); }}, 'Save Plan & Preview'));
    actions.append(el('button', {class:'btn go', onclick:async e => { e.target.disabled = true; if (await practiceCommand('save', plan)) await practiceCommand('run'); reload(); }}, 'Run Practice'));
  }
  actions.append(el('a', {class:'btn', href:'#gameplan/week'}, 'Game Plan'), el('a', {class:'btn', href:'#club/depth'}, 'Depth Chart'));
  surface.append(actions);
}

function gameplanSuggestion(x, reload, locked = false) {
  const act = (name, extra = '') => {
    notify(pyJSON(`SESSION.plan_act('${name}', i=${x.i}${extra})`));
    reload();
  };
  return el('div', { class: 'sug-row' + (x.taken ? ' on' : '') },
    el('div', { class: 't' }, x.text, el('small', {},
      `${x.target ? x.target + ' · ' : ''}${x.taken ? 'Accepted · ' : x.skipped ? 'Skipped · ' : ''}${x.why}`)),
    locked ? '' : el('div', { class: 'a', style: 'display:flex;gap:4px' },
      el('button', { class: x.taken ? 'btn quiet' : 'btn go', onclick: () => act(x.taken ? 'untake' : 'take') }, x.taken ? 'Undo' : 'Accept'),
      x.taken ? '' : el('button', { class: 'btn quiet', onclick: () => act('skip', `, skip=${x.skipped ? 'False' : 'True'}`) }, x.skipped ? 'Restore' : 'Skip')));
}

// Keep the center of each rail at the setting the wording calls neutral.
// The highlighted segment shows the range this coach permits this week.
const GAMEPLAN_SCALES = {
  pass_bias: [-0.25, 0, 0.25], play_action_rate: [0, 0.5, 1],
  motion_rate: [0, 0.581, 1], tempo: [0, 0.5, 1],
  blitz_rate: [0, 0.133, 0.4], man_rate: [0, 0.5, 1],
  shell_lean: [0, 0.5, 1], zone_aggression: [0, 0.5, 1],
  box_bias: [-0.5, 0, 0.5]
};
function gameplanScale(key, value) {
  const [lo, center, hi] = GAMEPLAN_SCALES[key];
  return Math.max(0, Math.min(100, value <= center
    ? 50 * (value - lo) / (center - lo)
    : 50 + 50 * (value - center) / (hi - center)));
}
function gameplanUnscale(key, percent) {
  const [lo, center, hi] = GAMEPLAN_SCALES[key];
  return percent <= 50 ? lo + (center - lo) * percent / 50
    : center + (hi - center) * (percent - 50) / 50;
}
function gameplanLeanWord(key, value) {
  if (key === 'pass_bias') return value < -0.02 ? 'Run more' : value > 0.02 ? 'Pass more' : 'Balanced';
  if (['play_action_rate', 'motion_rate', 'blitz_rate'].includes(key)) {
    const center = GAMEPLAN_SCALES[key][1];
    return value < center - 0.02 ? 'Less' : value > center + 0.02 ? 'More' : 'Standard';
  }
  if (key === 'tempo') return value < 0.4 ? 'Slower' : value > 0.6 ? 'Faster' : 'Normal';
  if (key === 'man_rate') return value < 0.42 ? 'Favor zone' : value > 0.58 ? 'Favor man' : 'Mixed';
  if (key === 'shell_lean') return value < 0.42 ? 'Favor single-high' : value > 0.58 ? 'Favor two-high' : 'Mixed';
  if (key === 'zone_aggression') return value < 0.42 ? 'Protect deeper routes' : value > 0.58 ? 'Attack short routes' : 'Balanced';
  if (key === 'box_bias') {
    const shift = Math.round(Math.abs(value) * 4 * 1e6) / 1e6;
    if (!shift) return 'Situational box';
    const direction = value < 0 ? 'Lighter' : 'Heavier';
    return shift <= 1 ? `${direction} box · ${Math.round(shift * 100)}% tendency`
      : `${direction} box · ${shift} defenders on average`;
  }
  return String(value);
}
function renderThisWeek(v) {
  renderRail(v.rail); const page = persPage(); gpSecond('week');
  page.className = 'gameplan-page';
  featureHero(page, v.rail.club, v.week ? `${weekName(v.week)} / Preparation` : 'Game Plan', 'GAME PLAN', 'Your coaches’ ideas and your game-week decisions.', [[v.week || '—', 'Week'], [showAbbr(v.opp?.abbr) || '—', 'Opponent']]);
  const reload = () => renderThisWeek(pyJSON(`SESSION.plan_view('this_week')`));
  const s = el('section', { class: 'sheet c12 gameplan-surface plan-week' });
  if (v.off) { s.append(el('h2', {}, 'This Week'), el('div', { class: 'empty' }, v.note)); page.append(s); return; }
  s.append(el('div', { class: 'plan-matchup' }, el('div', {}, el('span', {}, `WEEK ${v.week} · ${v.away ? 'AWAY' : 'HOME'}`), el('strong', {}, `${v.rail.club.name} ${v.away ? 'at' : 'vs'} ${v.opp.name}`)), el('a', { class: 'btn', href: '#gameplan/report' }, 'Opponent Report →')));
  // suggestions
  const sug = el('div', { class: 'sugs' });
  sug.append(el('div', { class: 'h5' }, "Assistants' Suggestions"));
  const locked = !!(v.plan_state?.locked || v.plan_state?.started);
  sug.append(el('p', { class: 'count' }, locked ? 'Saved for Sunday · Re-open to edit your choices' : gameplanUnsaved() ? 'Unsaved changes' : 'Open for editing'));
  for (const x of v.suggestions) sug.append(gameplanSuggestion(x, reload, locked));
  if (!v.suggestions.length) sug.append(el('div', { class: 'empty' }, 'The report has nothing to add this week; the plan is the coordinators\' own.'));
  else if (!locked) sug.append(el('div', { style: 'display:flex;gap:6px;padding:8px 0 0' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON('SESSION.plan_take_all()')); reload(); } }, 'Accept All'), el('span', { class: 'count', style: 'align-self:center' }, '')));
  s.append(sug);
  s.append(el('p', {class:'count', style:'padding:0 20px'}, 'These settings guide your team’s approach. Actual gameplay varies with the game situation.'));
  // preferences
  const plan = el('div', { class: 'plan plan-controls' });
  s.append(el('div', { class: 'plan-legend' },
    el('span', {}, el('i', { class: 'plan-dot' }), 'Your setting'),
    el('span', {}, el('i', { class: 'plan-default' }), 'Coach Default'),
    el('span', {}, el('i', { class: 'plan-diamond' }), 'Assistant suggestion'),
    el('span', {}, 'Brighter track = available adjustment range')));
  const side = (title, leans) => {
    const d = el('div', {}, el('h3', { class: 'h5' }, title));
    for (const ln of leans) {
      const pos = value => `${gameplanScale(ln.key, value).toFixed(2)}%`;
      const axes = ln.key === 'box_bias' ? ['Lighter', 'Situational', 'Heavier'] : ln.desc.split(' · ');
      const id = `gameplan-${ln.key}`;
      const output = el('output', { for: id, class: 'plan-current' }, ln.word);
      const marker = el('i', { class: 'plan-thumb', style: `left:${pos(ln.value)}` });
      const track = el('div', { class: 'plan-rail' },
        el('i', { class: 'plan-bar' }),
        el('i', { class: 'plan-allowed', style: `left:${pos(ln.min)};width:${(gameplanScale(ln.key, ln.max) - gameplanScale(ln.key, ln.min)).toFixed(2)}%` }),
        el('i', { class: 'plan-coach-tick', style: `left:${pos(ln.base)}` }));
      if (ln.ghost != null) track.append(el('i', { class: 'plan-suggestion', style: `left:${pos(ln.ghost)}`, 'data-tip': `Assistant suggestion: ${ln.ghost_word}` }));
      track.append(marker);
      const rng = el('input', { id, type: 'range', min: '0', max: '1000', step: '1', value: String(Math.round(gameplanScale(ln.key, ln.value) * 10)), 'aria-label': ln.label, 'aria-valuetext': ln.word });
      const selected = () => Math.max(ln.min, Math.min(ln.max, gameplanUnscale(ln.key, Number(rng.value) / 10)));
      rng.oninput = () => { const value = selected(); marker.style.left = pos(value); output.textContent = gameplanLeanWord(ln.key, value); rng.setAttribute('aria-valuetext', output.textContent); };
      rng.onchange = () => { const result = pyJSON(`SESSION.plan_act('set_lean', key=${JSON.stringify(ln.key)}, value=${selected()})`); if (!result.ok) notify(result); reload(); };
      track.append(rng);
      const below = el('div', { class: 'plan-below' }, el('span', {}, `Coach Default: ${gameplanLeanWord(ln.key, ln.base)}`));
      if (ln.ghost != null) below.append(el('button', { class: 'btn quiet', onclick: () => { const result = pyJSON(`SESSION.plan_act('set_lean', key=${JSON.stringify(ln.key)}, value=${ln.ghost})`); if (!result.ok) notify(result); reload(); } }, 'Apply suggestion'));
      d.append(el('div', { class: 'plan-setting' },
        el('div', { class: 'plan-setting-head' }, el('label', { for: id }, ln.label), output),
        track, el('div', { class: 'plan-axis' }, ...axes.map(word => el('span', {}, word))), below));
    }
    return d;
  };
  const off = side('Offense', v.leans.filter(l => l.side === 'offense')), deff = side('Defense', v.leans.filter(l => l.side === 'defense'));
  // depth mix as three numbers
  const dm = el('div', { class: 'plan-setting plan-depth' }, el('div', { class: 'plan-setting-head' }, el('span', {}, 'Depth of Target')), el('small', {}, 'Baseline mix; the game situation adjusts target depth.'));
  const depthValues = gameplanPendingDepth || v.depth.value.map(pct);
  const inputs = depthValues.map((x, i) => el('input', { type: 'number', min: '5', max: '90', value: String(x), style: 'width:56px;font-family:var(--mono);font-size:14.5px;background:var(--board);color:var(--ink);border:1px solid var(--rule-2);padding:4px 6px' }));
  inputs.forEach(input => input.addEventListener('input', () => { gameplanPendingDepth = inputs.map(x => Number(x.value)); }));
  const dmrow = el('div', { class: 'plan-depth-fields' }); v.depth.labels.forEach((l, i) => dmrow.append(el('label', {}, el('span', {}, `${l} %`), inputs[i]))); dmrow.append(el('button', { class: 'btn', onclick: () => { gameplanPendingDepth = inputs.map(x => Number(x.value)); if (flushGameplanDepth()) reload(); } }, 'Set'), el('span', { class: 'plan-depth-base' }, `Coach Default: ${v.depth.base.map(pct).join(' · ')}`));
  dm.append(dmrow); off.append(dm);
  plan.append(off, deff); s.append(plan);
  // decisions
  s.append(el('div', { class: 'h5', style: 'padding:10px 14px 6px' }, 'Game-Week Decisions'));
  const dec = el('div', { class: 'decide' });
  const prot = el('div', { class: 'dcard' }, el('div', { class: 'k' }, 'Protection'), el('div', { class: 's' }, v.protection.options.find(o => o.key === v.protection.value)?.word || v.protection.value)); const po = el('div', { class: 'opts' }); for (const o of v.protection.options) po.append(el('button', { class: 'btn chip' + (o.key === v.protection.value ? ' go' : ''), onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='protection', value=${JSON.stringify(o.key)})`); reload(); } }, o.word)); prot.append(po); dec.append(prot);
  const shadowWord = v.travel ? (v.travel_target ? `${v.my_cb1 ? v.my_cb1.name : 'CB1'} on ${v.travel_target.name}` : `${v.my_cb1 ? v.my_cb1.name : 'CB1'} follows their best receiver`) : 'Corners stay by side';
  const tr = el('div', { class: 'dcard' }, el('div', { class: 'k' }, 'Coverage · Shadow Their WR1?'), el('div', { class: 's' }, shadowWord));
  const tro = el('div', { class: 'opts' }, el('button', { class: 'btn chip' + (!v.travel ? ' go' : ''), onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='travel_target', value='')`); pyJSON(`SESSION.plan_act('set_decision', key='travel', value=False)`); reload(); } }, 'No Shadow'));
  for (const w of v.their_wrs) tro.append(el('button', { class: 'btn chip' + (v.travel && v.travel_target && v.travel_target.pid === w.pid ? ' go' : ''), 'data-tip': `${v.my_cb1 ? v.my_cb1.name : 'Your best corner'} follows him all game`, onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='travel_target', value=${JSON.stringify(w.pid)})`); reload(); } }, `${v.my_cb1 ? v.my_cb1.name : 'CB1'} on ${surname(w.name)} · ${w.ovr}`));
  tr.append(tro); dec.append(tr);
  const br = el('div', { class: 'dcard' }, el('div', { class: 'k' }, 'Coverage · Bracket a Star?'), el('div', { class: 's' }, v.bracket ? `Bracket ${surname(v.bracket.name)}` : (v.wr_out && v.wr_out.length ? `${v.wr_out[0]} Is Out · None` : 'None'))); const bo = el('div', { class: 'opts' }, el('button', { class: 'btn chip' + (!v.bracket ? ' go' : ''), onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='bracket', value='')`); reload(); } }, 'None')); for (const w of v.their_wrs) bo.append(el('button', { class: 'btn chip' + (v.bracket && v.bracket.pid === w.pid ? ' go' : ''), onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='bracket', value=${JSON.stringify(w.pid)})`); reload(); } }, `${w.name} · ${w.ovr}`)); br.append(bo); dec.append(br);
  s.append(dec);
  if (locked) s.querySelectorAll('button, input, select').forEach(control => { control.disabled = true; });
  s.append(el('div', { class: 'foot' }, gameplanSaveControl(v, reload, 'Save Preview Plan'), el('a', { class: 'btn', href: '#gameplan/report' }, 'Opponent Report'), locked ? '' : el('button', { class: 'btn quiet', onclick: () => { gameplanPendingDepth = null; notify(pyJSON(`SESSION.plan_act('reset')`)); reload(); } }, 'Use Coach Defaults'), el('span', { class: 'count', style: 'margin-left:auto' }, v.forecast && v.forecast.text ? v.forecast.text : '')));
  page.append(s);
}

function renderReport(v) {
  renderRail(v.rail); const page = persPage(); gpSecond('report');
  const locked = !!(v.plan_state?.locked || v.plan_state?.started);
  const reload = () => renderReport(pyJSON("SESSION.plan_view('report')"));
  page.className = 'gameplan-page';
  featureHero(page, v.rail.club, v.week ? `${weekName(v.week)} / Scouting` : 'Game Plan', 'OPPONENT REPORT', 'The tendencies, matchups, and players that matter this week.', [[v.week || '—', 'Week'], [showAbbr(v.opp?.abbr) || '—', 'Opponent']]);
  const s = el('section', { class: 'sheet c12 gameplan-surface plan-report' });
  if (v.off) { s.append(el('h2', {}, 'Opponent Report'), el('div', { class: 'empty' }, v.note)); page.append(s); return; }
  s.append(el('div', { class: 'plan-matchup' }, el('div', {}, el('span', {}, `WEEK ${v.week} · ${v.away ? 'AWAY' : 'HOME'}`), el('strong', {}, v.opp.name), el('small', {}, `${v.record}` + (v.coach?.name ? ` · ${v.coach.name}, prestige ${v.coach.prestige}` : ''))), el('a', { class: 'btn', href: '#gameplan/week' }, 'This Week’s Plan →')));
  // their tendencies against the league
  s.append(el('div', { class: 'h5', style: 'padding:10px 14px 6px' }, 'Their Tendencies', el('span', {}, v.tendencies ? `${v.tendencies.games} game${v.tendencies.games === 1 ? '' : 's'} on film · the white tick is the league average` : 'nothing on film yet')));
  const tg = el('div', { class: 'tendgrid' });
  const T = [['pass_rate', 'Pass Rate'], ['pa_rate', 'Play Action'], ['deep', 'Deep Shots'], ['two_high', 'Two-High'], ['blitz', 'Blitz'], ['man', 'Man Coverage'], ['fourth_go', 'Fourth-Down Go'], ['motion', 'Motion']];
  for (const [k, lab] of T) { const tv = v.tendencies ? v.tendencies[k] : null; const lg = v.league_tend ? v.league_tend[k] : null; tg.append(el('div', { class: 'tend', 'data-tip': `${showAbbr(v.opp.abbr)} ${tv ?? '—'}% · NFL ${lg ?? '—'}%` }, el('div', { class: 'l' }, lab), el('div', { class: 'bar' }, el('i', { style: `width:${tv ?? 0}%` }), lg != null ? el('em', { style: `left:${lg}%` }) : ''), el('div', { class: 'v' }, tv != null ? `${tv}%` : '—'))); }
  s.append(tg);
  // unit rankings, both clubs
  const two = el('div', { class: 'two' });
  const ut = el('div', {class:'report-unit-rankings'}, el('div', { class: 'h5' }, 'Team Rankings'), el('div', { class: 'side-row head' }, el('span', {}), el('span', { class: 'colhead' }, showAbbr(v.rail.club.abbr)), el('span', { class: 'colhead' }, showAbbr(v.opp.abbr))));
  const rk = r => el('span', { class: 'rk ' + (r == null ? '' : r <= 8 ? 'good' : r >= 24 ? 'bad' : 'mid-rk'), style: 'font-size:17px' }, r == null ? '—' : `${r}${ord(r)}`);
  for (const r of v.unit_table) ut.append(el('div', { class: 'side-row', title: r.metric }, el('span', { class: 'lab' }, r.label), el('span', {title:r.mine_value==null?'Complete season statistics unavailable':`${r.mine_value} ${r.metric}`}, rk(r.mine)), el('span', {title:r.theirs_value==null?'Complete season statistics unavailable':`${r.theirs_value} ${r.metric}`}, rk(r.theirs))));
  ut.append(el('div', {class:'muted', style:'font-size:11px;margin-top:8px'}, 'Regular season � per game � passing yards include sack losses. � means complete statistics are unavailable.'));
  const men = el('div', { class: 'report-players' }, el('div', { class: 'h5' }, 'Players Who Matter')); applyTeamTheme(men, v.opp); for (const p of v.stars) men.append(el('div', { class: 'plate', style: 'margin-bottom:4px;cursor:pointer', onclick: () => { location.hash = '#club/player/' + p.pid; } }, el('div', { class: 'no' }, p.pos), el('div', { class: 'nm' }, p.name, el('small', {}, p.pos)), el('div', { class: 'ov' }, p.ovr)));
  if (v.injured && v.injured.length) { men.append(el('div', { class: 'h5', style: 'margin-top:10px' }, 'Their Injuries')); for (const x of v.injured) men.append(el('div', { style: 'font-size:15px;color:var(--ink-2);padding:2px 0' }, typeof x === 'string' ? x : `${x.name} (${x.pos})${x.back ? ' · out to week ' + x.back : ' · out'}`)); }
  two.append(ut, men); s.append(two);
  // when each side has the ball, as on the Portal
  if (v.panels) {
    const P = v.panels; const grid = el('div', { class: 'two' });
    const panel = (title, rows, extra, leftHead, rightHead) => {
      const d = el('div', {}, el('div', { class: 'h5' }, title));
      const box = el('div', { class: 'sides' }, el('div', { class: 'side-row head', style: 'display:grid;grid-template-columns:1.4fr 1fr 34px 1fr' }, el('span', { class: 'lab', style: 'grid-column:1' }, 'Rank of'), el('span', { class: 'colhead', style: 'grid-column:2' }, leftHead.toUpperCase()), el('span', { class: 'mid', style: 'grid-column:3' }, 'vs'), el('span', { class: 'colhead', style: 'grid-column:4' }, rightHead.toUpperCase())));
      for (const r of rows) box.append(el('div', { class: 'side-row' }, el('span', { class: 'lab' }, r.label), rk(r.mine), el('span', { class: 'mid' }, 'vs'), rk(r.theirs)));
      (extra || []).forEach((t, i) => box.append(el('div', { class: 'side-row' + (i === 0 ? ' sep' : '') }, el('span', { class: 'lab' }, t.label, t.sub ? el('em', {}, t.sub) : ''), el('span', { class: 'rk', style: 'font-size:17px' }, t.left), el('span', { class: 'mid' }, 'vs'), el('span', { class: 'rk', style: 'font-size:17px' }, t.right))));
      d.append(box); return d;
    };
    grid.append(panel(`When ${v.rail.club.name} Has the Ball`, P.ours, P.ours_extra, `${showAbbr(v.rail.club.abbr)} Offense`, `${showAbbr(v.opp.abbr)} Defense`), panel(`When ${v.opp.name} Has the Ball`, P.theirs, P.theirs_extra, `${showAbbr(v.opp.abbr)} Offense`, `${showAbbr(v.rail.club.abbr)} Defense`));
    s.append(grid);
  }
  // what we would do
  s.append(el('div', { class: 'h5', style: 'padding:10px 14px 6px' }, 'What We Would Do', el('span', {}, 'act on This Week')));
  const cards = el('div', { class: 'cards' });
  for (const x of v.suggestions) cards.append(el('div', { class: 'card', style: `--k:${x.side === 'offense' ? 'var(--ok)' : 'var(--live)'};opacity:${x.taken || x.skipped ? '.75' : '1'}` }, el('div', { class: 'h' }, el('div', { class: 'k' }, x.side.charAt(0).toUpperCase() + x.side.slice(1) + (x.taken ? ' · accepted' : x.skipped ? ' · skipped' : '')), el('div', { class: 's' }, x.text)), el('div', { class: 'b' }, x.why),
    el('div', { class: 'b', style: 'margin-top:6px' }, el('span', { style: 'font-size:12.5px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.04em' }, 'Plan Change '), el('span', { style: 'font-family:var(--mono);font-size:14px' }, x.change || '—')),
    locked ? '' : el('div', { class: 'a' }, x.taken ? el('button', { class: 'btn quiet', onclick: () => { notify(pyJSON(`SESSION.plan_act('untake', i=${x.i})`)); renderReport(pyJSON(`SESSION.plan_view('report')`)); } }, 'Undo') : el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.plan_act('take', i=${x.i})`)); renderReport(pyJSON(`SESSION.plan_view('report')`)); } }, 'Accept'), x.taken ? '' : el('button', { class: 'btn quiet', onclick: () => { notify(pyJSON(`SESSION.plan_act('skip', i=${x.i}, skip=${x.skipped ? 'False' : 'True'})`)); renderReport(pyJSON(`SESSION.plan_view('report')`)); } }, x.skipped ? 'Restore' : 'Skip'))));
  if (!v.suggestions.length) cards.append(el('div', { class: 'empty' }, 'Nothing to add this week.'));
  s.append(cards, el('div', { class: 'foot' }, gameplanSaveControl(v, reload), locked ? '' : el('button', { class: 'btn', onclick: () => { notify(pyJSON('SESSION.plan_take_all()')); location.hash = '#gameplan/week'; } }, "Accept All and Open This Week's Plan"), el('a', { class: 'btn', href: '#gameplan/week' }, "Back to This Week's Plan")));
  page.append(s);
}

// ---------------------------------------------------------------- flow
function refresh() {
  // Message links select a row in the Inbox; no message has a separate page.
  if (location.hash.startsWith('#portal/inbox/')) { openInboxMessage(+location.hash.split('/').pop()); return; }
  if (location.hash === '#portal/inbox') { view = pyJSON('SESSION.inbox_view()'); renderInbox(view); return; }
  view = pyJSON('SESSION.portal()'); renderRail(view.rail); renderPortal(view);
}
// a fresh session starts at the portal overview whatever address the browser kept from last time
function bootHash() { if (location.hash && location.hash !== '#portal') history.replaceState(null, '', '#portal'); }

async function advance() {
  syncGameplanState();
  if (gameplanUnsaved() || gameplanSaving) { location.hash = '#gameplan/week'; warnUnsavedGameplan(); return; }
  try { await advanceInner(); }
  catch (e) {
    // whatever failed, the GM sees it and can send it on: the message, and where in the engine it happened
    console.error(e); const msg = String(e && e.message || e);
    $('#advance').disabled = false;
    notify({ ok: false, why: 'The advance failed. Copy this and send it:\n' + msg.slice(-1500) });
  }
}

async function advanceInner() {
  if (practiceSaving || practiceSaveRequired) { notify({ok:false, why:'Save your practice results before advancing. Open Practice and retry the save.'}); location.hash = '#gameplan/practice'; return; }
  // a block stops the click: a roster over 53 or under 46 sends you to fix it; a decision opens it
  const blocks = pyJSON('SESSION.blocking()');
  if (blocks.length && blocks[0].kind === 'live') { location.hash = '#gameday'; renderGameDay(pyJSON('SESSION.gameday_view()')); return; }
  if (blocks.length) { const b = blocks[0]; notify({ ok: false, why: `Blocked: ${b.subject}. ${b.kind === 'cap' ? 'Open Cap to choose your contract moves.' : b.kind === 'roster' ? 'Fix the roster first.' : 'Answer it (or decline) to advance.'}` }); renderRail(pyJSON('SESSION.portal()').rail); if (b.go) location.hash = b.go; else if (b.id != null) location.hash = `#portal/inbox/${b.id}`; return; }
  const adv = $('#advance'); adv.disabled = true;
  await new Promise(r => setTimeout(r, 30));
  let r = null;
  try { r = pyJSON('SESSION.advance()'); }
  catch (e) { adv.disabled = false; throw e; }
  adv.disabled = false;
  if (r && r.done === 'Blocked') { notify({ ok: false, why: r.why }); }
  else if (r && r.done === 'Practice complete') { practiceSaveRequired = true; try { await saveGame(); practiceSaveRequired = false; } finally { location.hash = '#gameplan/practice'; renderPractice(pyJSON('SESSION.practice_view()')); } return; }
  else if (r && r.done === 'Cutdown') { location.hash = '#personnel/wire'; renderWire(pyJSON(`SESSION.personnel('waivers')`)); }
  else if (r && r.done === 'Camp') { location.hash = '#portal'; refresh(); }
  else if (r && /^Week \d+ live$/.test(r.done)) { location.hash = '#gameday'; renderGameDay(pyJSON('SESSION.gameday_view()')); }
  else if (r && /^Week \d+ played$/.test(r.done)) { if (location.hash === '#gameday') renderGameDay(pyJSON('SESSION.gameday_view()')); else location.hash = '#gameday'; }
  else if (r && /^Week \d+$/.test(r.done)) { if (location.hash === '' || location.hash.startsWith('#portal')) refresh(); else if (location.hash === '#gameday') renderGameDay(pyJSON('SESSION.gameday_view()')); else location.hash = '#portal'; } else if (r && /on the clock/.test(r.done)) { location.hash = '#draft/day'; renderDraftDay(pyJSON(`SESSION.draft_view('draft_day')`)); } else refresh();
  await saveGameNotified();
}

// ---------------------------------------------------------------- start
(async function main() {
  const pick = $('#pick');
  let engineReady = false, entering = false;
  let saved = { text: null };
  function updateBootActions() {
    $('#start').disabled = !engineReady || !team || entering;
    $('#resume').disabled = !engineReady || !saved.text || entering;
    pick.querySelectorAll('button').forEach(b => { b.disabled = entering; });
  }
  function selectBootTeam(abbr) {
    if (entering || !CLUBS.includes(abbr)) return;
    team = abbr;
    const bootScreen = $('#boot');
    const inkFor = hex => { const n = parseInt(hex.slice(1), 16); return (((n >> 16) & 255) * 299 + ((n >> 8) & 255) * 587 + (n & 255) * 114) / 1000 > 145 ? '#111' : '#fff'; };
    bootScreen.style.setProperty('--boot-primary', COLOR[abbr]);
    bootScreen.style.setProperty('--boot-accent', BOOT_TEAM[abbr][1]);
    bootScreen.style.setProperty('--boot-primary-ink', inkFor(COLOR[abbr]));
    bootScreen.style.setProperty('--boot-action-ink', inkFor(BOOT_TEAM[abbr][1]));
    $('#selectedcode').textContent = showAbbr(abbr);
    $('#selectedname').textContent = BOOT_TEAM[abbr][0];
    $('#boot .boot-selected').hidden = false;
    pick.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.abbr === abbr)));
    updateBootActions();
  }
  for (const c of CLUBS) pick.append(el('button', { style: `--team-color:${COLOR[c]}`, 'data-abbr': c, 'aria-label': `Select ${BOOT_TEAM[c][0]}`, 'aria-pressed': String(c === team), onclick: () => selectBootTeam(c) }, showAbbr(c)));
  try { await bootEngine(); } catch (e) { say('The game could not load. Reload to try again. ' + e); $('#boot').classList.add('failed'); return; }
  engineReady = true;
  try { saved = await loadSave(); boot.line.closest('.boot-progress').hidden = true; }
  catch (e) { say('Browser saves are unavailable. You can start a new franchise and export it.'); }
  updateBootActions();
  $('#start').onclick = async () => {
    if (!engineReady || !team || entering) return;
    entering = true; updateBootActions();
    try { await newGame(team); }
    catch (e) { entering = false; updateBootActions(); say('Could not start the franchise. Try again. ' + e); return; }
    $('#boot').remove(); bootHash(); refresh(); await saveGameNotified();
  };
  $('#resume').onclick = async () => {
    if (!engineReady || !saved.text || entering) return;
    entering = true; updateBootActions(); say('Loading your save…', 90);
    try {
    await new Promise(r => setTimeout(r, 30));
    py.globals.set('_SAVE', saved.text); py.runPython(`SESSION = S.Session.load(_SAVE)`);
    let journalError = null;
    if (saved.journal) {
      try {
        py.globals.set('_LIVE_JOURNAL', JSON.stringify(saved.journal));
        py.runPython(`SESSION.apply_live_journal(json.loads(_LIVE_JOURNAL))`);
      } catch (e) {
        journalError = e;
        py.runPython(`SESSION = S.Session.load(_SAVE)`);
      }
    }
    $('#boot').remove(); bootHash(); refresh();
    if (journalError) notify({ ok: false, why: 'The latest live plays could not be restored. Your last full save was loaded.' });
    } catch (e) {
      if (!$('#boot')) throw e;
      entering = false; updateBootActions(); say('Could not load this save. You can retry or choose a team to start a new franchise. ' + e);
    }
  };
  $('#advance').onclick = advance;
  $('#save').onclick = saveGameNotified;
  document.querySelector('.quick-menu').addEventListener('click', e => { if (e.target.closest('a')) e.currentTarget.open = false; });
  // EXPORT AND IMPORT: the save as a file, for a backup or for sending a state to be looked at
  $('#export').onclick = () => {
    const text = py.runPython(`SESSION.save()`); const st = pyJSON(`SESSION.rail_state()`);
    const blob = new Blob([text], { type: 'application/json' }); const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = `nflgm-${st.year}-${st.stop}.json`; document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(a.href);
  };
  $('#import').onclick = () => { if (gameplanUnsaved() || gameplanSaving) { warnUnsavedGameplan(); return; } $('#importfile').click(); };
  $('#importfile').onchange = async e => {
    const f = e.target.files && e.target.files[0]; if (!f) return;
    const text = await f.text();
    try { py.globals.set('_import_text', text); py.runPython(`import session as S\nSESSION = S.Session.load(_import_text)`); await saveGame(); bootHash(); refresh(); notify({ ok: true, line: 'Save loaded.' }); }
    catch (err) { notify({ ok: false, why: 'That file could not be loaded as a save.' }); }
    e.target.value = '';
  };
  $('#back').onclick = () => history.back();
  const fwd = document.querySelector('.hist button[aria-label="Forward"]'); if (fwd) { fwd.disabled = false; fwd.onclick = () => history.forward(); }
  window.addEventListener('hashchange', event => { if (guardGameplanRoute(event)) return; if (location.hash.startsWith('#portal/inbox/')) openInboxMessage(+location.hash.split('/').pop()); else if (location.hash === '#portal/inbox') { view = pyJSON('SESSION.inbox_view()'); renderInbox(view); } else if (location.hash.startsWith('#portal') || location.hash === '') refresh(); else if (location.hash.startsWith('#gameday')) { const wk = location.hash.split('/')[1]; renderGameDay(pyJSON(wk ? `SESSION.gameday_view(week=${+wk})` : 'SESSION.gameday_view()')); } else if (location.hash.startsWith('#club/team/')) { const parts = location.hash.split('/'); const abbr = parts[2]; const sub = parts[3] || 'roster'; if (sub === 'depth') renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(depthPkg)}, ${JSON.stringify(abbr)})`)); else { clubTab = sub === 'ps' ? 'ps' : sub === 'ir' ? 'ir' : 'active'; renderRoster(pyJSON(`SESSION.club_roster(${JSON.stringify(abbr)})`)); } } else if (location.hash.startsWith('#club/player/')) renderCard(pyJSON(`SESSION.club_card(${JSON.stringify(location.hash.split('/').pop())})`)); else if (location.hash.startsWith('#club/depth')) renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(depthPkg)})`)); else if (location.hash.startsWith('#club')) { if (location.hash === '#club/schedule') renderClubSchedule(pyJSON(`SESSION.league_view('team_schedule')`), true); else if (location.hash === '#club/regression') renderRegression(pyJSON(`SESSION.club_regression()`)); else if (location.hash.startsWith('#club/progression')) renderProgression(pyJSON('SESSION.progression()')); else { clubTab = location.hash.startsWith('#club/ps') ? 'ps' : location.hash.startsWith('#club/ir') ? 'ir' : 'active'; renderRoster(pyJSON('SESSION.club_roster()')); } } else if (location.hash.startsWith('#gameplan')) { const sub = location.hash.split('/')[1] || 'week'; if (sub === 'practice') renderPractice(pyJSON('SESSION.practice_view()')); else if (sub === 'report') renderReport(pyJSON(`SESSION.plan_view('report')`)); else renderThisWeek(pyJSON(`SESSION.plan_view('this_week')`)); } else if (location.hash.startsWith('#league/team/')) { const parts = location.hash.split('/'); const abbr = parts[2]; const sub = parts[3] || ''; if (sub === 'roster' || sub === 'ps') { clubTab = sub === 'ps' ? 'ps' : 'active'; renderRoster(pyJSON(`SESSION.club_roster(${JSON.stringify(abbr)})`)); } else if (sub === 'depth') renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(depthPkg)}, ${JSON.stringify(abbr)})`)); else if (sub === 'schedule') renderClubSchedule(pyJSON(`SESSION.league_view('team_schedule', team=${JSON.stringify(abbr)})`), false); else renderTeam(pyJSON(`SESSION.team_page(${JSON.stringify(abbr)})`)); }
    else if (location.hash.startsWith('#league')) { const sub = location.hash.split('/')[1] || 'standings'; const fn = { standings: renderStandings, schedule: renderSchedule, bracket: renderBracket, transactions: renderTransactions, stats: renderStats, awards: renderAwards, coaching: renderCoaching, almanac: renderAlmanac }[sub] || renderStandings; fn(pyJSON(`SESSION.league_view(${JSON.stringify(sub in LG ? sub : 'standings')})`)); } else if (location.hash.startsWith('#draft')) { const sub = location.hash.split('/')[1] || 'board'; if (sub === 'day') renderDraftDay(pyJSON(`SESSION.draft_view('draft_day')`)); else if (sub === 'spring') renderSpring(pyJSON(`SESSION.draft_view('spring')`)); else if (sub === 'picks') renderPicks(pyJSON(`SESSION.draft_view('picks')`)); else if (sub === 'results') renderDraftResults(pyJSON(`SESSION.draft_view('picks')`)); else renderBoard(pyJSON(`SESSION.draft_view('board')`)); } else if (location.hash.startsWith('#frontoffice')) { const sub = location.hash.split('/')[1] || 'owner'; if (sub === 'identity') { idPreview = null; renderIdentity(pyJSON(`SESSION.frontoffice('identity')`)); } else if (sub === 'review') renderReview(pyJSON(`SESSION.frontoffice('season_review')`)); else if (sub === 'exit') renderExit(pyJSON(`SESSION.frontoffice('exit_interviews')`)); else if (sub === 'staff') renderStaff(pyJSON(`SESSION.frontoffice('staff')`)); else if (sub === 'cap') renderCap(pyJSON(`SESSION.frontoffice('cap')`)); else renderOwner(pyJSON(`SESSION.frontoffice('owner')`)); } else if (location.hash.startsWith('#personnel')) { const sub = location.hash.split('/')[1] || 'trades'; if (sub === 'fa') renderFA(pyJSON(`SESSION.personnel('free_agency')`)); else if (sub === 'wire') renderWire(pyJSON(`SESSION.personnel('waivers')`)); else if (sub === 'retain') renderRetain(pyJSON(`SESSION.personnel('retain')`)); else if (sub === 'extensions') renderExtensions(pyJSON(`SESSION.personnel('extensions')`)); else { if (!tradeState.keep) { tradeState.a = []; tradeState.b = []; tradeState.counter_id = null; } tradeState.keep = false; renderTrades(pyJSON(`SESSION.personnel('trades'${tradeState.other ? ', other=' + JSON.stringify(tradeState.other) : ''}, a_sends=${JSON.stringify(tradeState.a)}, b_sends=${JSON.stringify(tradeState.b)})`)); } } else { const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = '1fr'; page.append(el('section', { class: 'sheet' }, el('h2', {}, location.hash.slice(1).split('/')[0].replace(/^\w/, c => c.toUpperCase())), el('div', { class: 'empty' }, 'This page is next to be wired.'), el('div', { class: 'foot' }, el('button', { class: 'btn', onclick: () => { location.hash = '#portal'; } }, 'Back to Portal')))); } });
})();

// Signed points relative to the drive offense, including blocked-punt scores.
function replayPlayPoints(play) {
  if (play.nullified) return 0;
  if (play.safety) return -2;
  const sign = play.scoring_side === 'defense' ? -1 : 1;
  if (play.td) return 6 * sign;
  if (play.type === 'field_goal' && play.made) return 3 * sign;
  if (play.type === 'extra_point' && play.made !== false) return sign;
  if (play.type === 'two_point' && play.made) return 2 * sign;
  return 0;
}

// Follow only revealed events: do not leak the finished game's timeout totals.
function gameDayIndicators(g, shown, shownPlays, live = null, playoffs = false) {
  const home = g.home.abbr, away = g.away.abbr;
  const counts = { [home]: 3, [away]: 3 };
  const final = !live && shown >= g.drives.length && shownPlays == null;
  let period = 1, possession = away;
  const enterQuarter = quarter => {
    const next = quarter >= 5 ? 3 : quarter >= 3 ? 2 : 1;
    if (next > period) {
      const total = next === 3 && !(live?.playoffs ?? playoffs) ? 2 : 3;
      counts[home] = counts[away] = total;
      period = next;
    }
  };
  for (const [i, drive] of g.drives.slice(0, shown).entries()) {
    enterQuarter(drive.quarter || 1);
    possession = drive.off;
    const visible = (drive.plays || []).filter(p => p.text);
    const plays = i === shown - 1 && shownPlays != null ? visible.slice(0, shownPlays) : visible;
    for (const p of plays) {
      enterQuarter(p.quarter || drive.quarter || 1);
      if (p.type === 'timeout') {
        let team = p.timeout_side === 'home' ? home : p.timeout_side === 'away' ? away : p.timeout_team;
        let left = p.timeouts_left;
        // Older saves retained the ticker sentence but not timeout fields.
        const old = String(p.text).match(/^Timeout, (.+?) \((\d+) left\)/);
        if (!team && old) team = old[1] === 'HOME' ? home : old[1] === 'AWAY' ? away : old[1] === 'the offense' ? drive.off : old[1];
        if (left == null && old) left = Number(old[2]);
        if (team in counts && left != null && Number.isFinite(Number(left))) counts[team] = Math.max(0, Math.min(3, Number(left)));
      }
      if (!p.nullified && (p.type === 'interception' || p.fumble_lost)) possession = drive.off === home ? away : home;
    }
    if (i === shown - 1 && shownPlays == null && g.drives[shown]) possession = g.drives[shown].off;
  }
  if (live?.halftime_open) {
    enterQuarter(live.adjustment_period === 'overtime' ? 5 : 3);
    possession = null;
  } else if (live && 'possession' in live) possession = live.possession;
  if (final) possession = null;
  return { possession, timeouts: counts };
}

function gameDayTeamStatus(team, record, indicators) {
  const hasBall = indicators.possession === team.abbr;
  const football = el('span', { class: 'possession-football' + (hasBall ? ' has-ball' : ''),
    role: hasBall ? 'img' : null, 'aria-label': hasBall ? `${team.name || team.nick} possession` : null,
    'aria-hidden': hasBall ? null : 'true',
    html: '<svg viewBox="0 0 32 20" aria-hidden="true"><path d="M2 10C7-1 25-1 30 10C25 21 7 21 2 10Z" fill="#ac6537" stroke="#efc698" stroke-width="1.3"/><path d="M8 3.5C6.5 7 6.5 13 8 16.5M24 3.5C25.5 7 25.5 13 24 16.5" fill="none" stroke="#fff4dd" stroke-width="2"/><path d="M11 10H21M13 7.5V12.5M16 7.5V12.5M19 7.5V12.5" stroke="#fff4dd" stroke-width="1.3" stroke-linecap="round"/></svg>' });
  const remaining = indicators.timeouts[team.abbr];
  const dots = el('span', { class: 'timeout-dots', role: 'img',
    'aria-label': `${team.name || team.nick}: ${remaining} timeout${remaining === 1 ? '' : 's'} remaining` },
    ...[0, 1, 2].map(i => el('i', { class: 'timeout-dot' + (i < remaining ? ' available' : ''), 'aria-hidden': 'true' })));
  return el('div', { class: 'team-status' }, el('div', { class: 'nm' }, team.nick),
    el('div', { class: 'team-status-line' }, el('span', { class: 'rec' }, record), football), dots);
}
