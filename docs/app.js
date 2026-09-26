// NFL GM — the browser app. Python engine in Pyodide; this file renders views and calls actions.

const ENGINE = 'engine/';
const CLUBS = ['ARI','ATL','BAL','BUF','CAR','CHI','CIN','CLE','DAL','DEN','DET','GB','HOU','IND','JAX','KC','LV','LAC','LA','MIA','MIN','NE','NO','NYG','NYJ','PHI','PIT','SF','SEA','TB','TEN','WAS'];
const COLOR = {ARI:'#97233f',ATL:'#a71930',BAL:'#241773',BUF:'#00338d',CAR:'#0085ca',CHI:'#0b162a',CIN:'#fb4f14',CLE:'#311d00',DAL:'#003594',DEN:'#fb4f14',DET:'#0076b6',GB:'#203731',HOU:'#03202f',IND:'#002c5f',JAX:'#006778',KC:'#c8102e',LV:'#000000',LAC:'#0080c6',LA:'#003594',MIA:'#008e97',MIN:'#4f2683',NE:'#002244',NO:'#d3bc8d',NYG:'#0b2265',NYJ:'#125740',PHI:'#004c54',PIT:'#ffb612',SF:'#aa0000',SEA:'#002244',TB:'#d50a0a',TEN:'#0c2340',WAS:'#5a1414'};

const $ = s => document.querySelector(s);
const el = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) { if (k === 'class') e.className = v; else if (k === 'html') e.innerHTML = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v !== null && v !== undefined) e.setAttribute(k, v); } for (const k of kids) if (k !== null && k !== undefined) e.append(k.nodeType ? k : document.createTextNode(String(k))); return e; };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

let py = null, team = 'KC', view = null;

// ---------------------------------------------------------------- boot
const boot = { bar: $('#bootbar'), line: $('#bootline') };
const say = (t, pct) => { boot.line.textContent = t; if (pct != null) boot.bar.style.width = pct + '%'; };

async function bootEngine() {
  say('booting Python…', 4);
  const { loadPyodide } = await import('https://cdn.jsdelivr.net/pyodide/v0.29.5/full/pyodide.mjs');
  py = await loadPyodide({ indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.29.5/full/' });
  say('loading numpy and pandas…', 18);
  await py.loadPackage(['numpy', 'pandas', 'networkx']);      // networkx: the schedule builder's matching
  // the manifest is always re-checked with the server, and every engine file carries the
  // build stamp in its URL, so a new push is picked up on the next load instead of after
  // the browser's ten-minute cache expires
  const manifest = await (await fetch(ENGINE + 'manifest.json', { cache: 'no-cache' })).json();
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

function pyJSON(code) { return JSON.parse(py.runPython(`_j(${code})`)); }

async function newGame(abbr) {
  say(`building the league for ${abbr}… (about a minute the first time)`, 88);
  await new Promise(r => setTimeout(r, 30));
  py.runPython(`SESSION = S.Session.new(${JSON.stringify(abbr)})`);
  say('ready.', 100);
}

// ---------------------------------------------------------------- save / load (IndexedDB)
function idb() { return new Promise((res, rej) => { const r = indexedDB.open('nflgm', 1); r.onupgradeneeded = () => r.result.createObjectStore('saves'); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); }); }
async function saveGame() {
  busy('Saving…');
  const text = py.runPython(`SESSION.save()`);
  const db = await idb(); await new Promise((res, rej) => { const tx = db.transaction('saves', 'readwrite'); tx.objectStore('saves').put(text, 'main'); tx.oncomplete = res; tx.onerror = () => rej(tx.error); });
  busy(null);
}
async function loadSave() { const db = await idb(); return new Promise(res => { const r = db.transaction('saves').objectStore('saves').get('main'); r.onsuccess = () => res(r.result || null); r.onerror = () => res(null); }); }

function busy(t) { const b = $('#busy'); if (t) { b.textContent = t; b.hidden = false; } else b.hidden = true; }

// ---------------------------------------------------------------- the rail
function renderRail(r) {
  $('#rail').hidden = false;
  const c = $('#crest'); c.textContent = r.club.abbr; c.style.background = r.club.color;
  document.documentElement.style.setProperty('--club', r.club.color); document.documentElement.style.setProperty('--club-2', r.club.accent);
  $('#clubname').textContent = r.club.name.toUpperCase(); $('#coach').textContent = `${r.coach} · Head Coach and GM`;
  $('#st-record').textContent = r.record; $('#st-place').textContent = r.place; $('#st-cap').textContent = r.cap; $('#st-prestige').textContent = r.prestige ?? '—';
  $('#st-week').textContent = r.clock.line; $('#st-year').textContent = r.clock.sub;
  const badge = $('#badge'); badge.hidden = !r.inbox_unread; badge.textContent = r.inbox_unread;
  const adv = $('#advance');
  if (r.blocking.length) { adv.classList.add('blocked'); const roster = r.blocking.find(b => b.kind === 'roster'); $('#adv-title').textContent = roster ? roster.subject.split(':')[0] : `${r.blocking.length} Decision${r.blocking.length > 1 ? 's' : ''}`; $('#adv-sub').textContent = roster ? roster.subject.split(': ')[1] : `Then ${r.advance.title}`; }
  else { adv.classList.remove('blocked'); $('#adv-title').textContent = r.advance.title; $('#adv-sub').textContent = r.advance.sub || ''; }
}

// ---------------------------------------------------------------- the Portal
function sheet(title, small, ...body) { return el('section', { class: 'sheet' }, el('h2', {}, title, small ? el('small', {}, small) : null), ...body); }
// the last name, keeping a suffix with it: 'Marvin Mims Jr.' -> 'Mims Jr.', 'Odell Beckham III' -> 'Beckham III'
function surname(name) { const p = String(name || '').trim().split(' '); if (p.length >= 2 && /^(Jr\.?|Sr\.?|II|III|IV|V)$/.test(p[p.length - 1])) return p.slice(-2).join(' '); return p[p.length - 1] || ''; }
function stripe(abbr, text) { return el('span', { class: 'stripe', style: `--c:${COLOR[abbr] || '#555'}` }, text ?? abbr); }
// a club's name as a link to its team page (your own club goes to Club)
function clubLink(abbr, text) { const s = stripe(abbr, text); s.classList.add('clublink'); s.style.cursor = 'pointer'; s.onclick = e => { e.stopPropagation(); location.hash = (view && view.rail && view.rail.club && view.rail.club.abbr === abbr) ? '#club' : `#league/team/${abbr}`; }; return s; }
function formDots(f, big = false) { return el('div', { class: 'form' + (big ? ' big-form' : '') }, ...f.map(x => el('i', { class: x }))); }

// the desk card's second button: where the decision is made
const DESK_GO = { Trade: ['Trades', '#personnel/trades'], Contract: ['Negotiate', '#personnel/extensions'], Staff: ['Staff', '#frontoffice/staff'], Assistants: ['Game Plan', '#gameplan/week'], Wire: ['Waivers', '#personnel/wire'] };
function deskAction(kind) { const g = DESK_GO[kind]; return g ? el('a', { class: 'btn go', href: g[1] }, g[0]) : ''; }

function inboxSheet(v) {
  const inbox = el('section', { class: 'sheet c12' }, el('h2', {}, 'Inbox', el('small', {}, `${v.inbox.total} Messages · ${v.inbox.decide} Need a Decision`)));
  const list = el('div', { class: inboxDense ? 'inbox-list dense' : 'inbox-list' });
  const drawInbox = () => {
    list.innerHTML = ''; let lastDay = null, n = 0;
    for (const r of v.inbox.rows) {
      if (inboxFilter === 'decide' && !r.decide) continue;
      if (inboxFilter === 'unread' && !r.unread) continue;
      if (inboxFilter === 'league' && r.tag !== 'League') continue;
      if (inboxFilter === 'club' && r.tag === 'League') continue;
      n++;
      const day = `${r.year} · Week ${r.week}`;
      if (day !== lastDay) { list.append(el('div', { class: 'dayh' }, day)); lastDay = day; }
      list.append(el('button', { class: 'row' + (r.unread ? ' unread' : ''), onclick: () => openMessage(r.id) }, el('div', {}, el('div', { class: 't' }, r.subject), inboxDense ? '' : el('div', { class: 'f' }, r.body)), el('span', { class: 'tag ' + tagClass(r.tag) }, r.tag)));
    }
    if (!n) list.append(el('div', { class: 'empty' }, inboxFilter === 'all' ? 'Nothing yet.' : inboxFilter === 'decide' ? 'Nothing waiting on a decision.' : inboxFilter === 'league' ? 'Nothing from around the league yet.' : 'All read.'));
  };
  const filt = el('div', { class: 'filt' });
  for (const [k, label, count] of [['all', 'All', v.inbox.total], ['club', 'Your Club', v.inbox.rows.filter(r => r.tag !== 'League').length], ['league', 'League', v.inbox.rows.filter(r => r.tag === 'League').length], ['decide', 'Decide', v.inbox.decide], ['unread', 'Unread', v.inbox.unread]])
    filt.append(el('button', { 'aria-pressed': String(inboxFilter === k), onclick: e => { inboxFilter = k; filt.querySelectorAll('button[data-f]').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); drawInbox(); }, 'data-f': k }, label + ' ', el('em', {}, count)));
  filt.append(el('span', { class: 'sep' }),
    el('button', { onclick: e => { inboxDense = !inboxDense; list.classList.toggle('dense', inboxDense); e.currentTarget.textContent = inboxDense ? 'Detailed' : 'Condensed'; drawInbox(); } }, inboxDense ? 'Detailed' : 'Condensed'),
    el('button', { style: 'margin-left:auto', onclick: () => { pyJSON('SESSION.inbox_mark_all()'); redrawInbox(); } }, 'Mark All Read'));
  inbox.append(filt, list); drawInbox();
  return inbox;
}

function redrawInbox() { if (location.hash === '#portal/inbox') { view = pyJSON('SESSION.portal_full()'); renderInbox(view); } else { view = pyJSON('SESSION.portal()'); renderRail(view.rail); renderPortal(view); } }

let mailSel = null;
function renderInbox(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Portal'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'portal'));
  document.body.classList.remove('no-second');
  $('#second').innerHTML = `<a href="#portal">Overview</a><a aria-current="page" href="#portal/inbox">Inbox <em>${v.inbox.total}</em></a><a href="#league/schedule">Calendar</a><a href="#league/transactions">News</a><a href="#frontoffice">Owner</a>`;
  const reload = () => renderInbox(pyJSON('SESSION.portal_full()'));
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Inbox', el('small', {}, `${v.inbox.total} Messages · ${v.inbox.decide} Need a Decision · ${v.inbox.unread} Unread`)));
  // the filters and the page-level actions
  const tools = el('div', { class: 'mailtools' });
  for (const [k, label, count] of [['all', 'All', v.inbox.total], ['club', 'Your Club', v.inbox.rows.filter(r => r.tag !== 'League').length], ['league', 'League', v.inbox.rows.filter(r => r.tag === 'League').length], ['decide', 'Decide', v.inbox.decide], ['unread', 'Unread', v.inbox.unread]])
    tools.append(el('button', { class: 'chip', 'aria-pressed': String(inboxFilter === k), onclick: () => { inboxFilter = k; renderInbox(v); } }, `${label} `, el('em', {}, count)));
  const rows = v.inbox.rows.filter(r => (inboxFilter !== 'decide' || r.decide) && (inboxFilter !== 'unread' || r.unread) && (inboxFilter !== 'league' || r.tag === 'League') && (inboxFilter !== 'club' || r.tag !== 'League'));
  if (mailSel == null || !rows.some(r => r.id === mailSel)) mailSel = rows.length ? rows[0].id : null;
  const cur = rows.find(r => r.id === mailSel) || null;
  tools.append(el('span', { style: 'width:1px;background:var(--rule-2);height:22px;margin:0 6px' }),
    el('button', { class: 'btn', disabled: cur && cur.unread ? null : '', onclick: () => { pyJSON(`SESSION.inbox_read(${cur.id})`); reload(); } }, 'Mark Read'),
    el('button', { class: 'btn', disabled: cur ? null : '', 'data-tip': 'Remove this message', onclick: () => { pyJSON(`SESSION.inbox_delete(${cur.id})`); mailSel = null; reload(); } }, 'Delete'),
    el('button', { class: 'btn quiet', onclick: () => { pyJSON('SESSION.inbox_mark_all()'); reload(); } }, 'Mark All Read'),
    el('button', { class: 'btn quiet', 'data-tip': 'Remove every read message that needs no decision', onclick: () => { if (confirm('Clear every read message that needs no decision?')) { pyJSON('SESSION.inbox_clear_read()'); mailSel = null; reload(); } } }, 'Clear Read'),
    el('span', { class: 'count' }, `${rows.length} shown`));
  s.append(tools);
  const box = el('div', { class: 'mailbox' });
  const list = el('div', { class: 'list' });
  for (const r of rows) list.append(el('div', { class: 'row' + (r.unread ? ' unread' : '') + (r.id === mailSel ? ' sel' : ''), onclick: () => { mailSel = r.id; if (r.unread) pyJSON(`SESSION.inbox_read(${r.id})`); renderInbox(pyJSON('SESSION.portal_full()')); } },
    el('span', { class: 'dot' }), el('div', { style: 'min-width:0' }, el('div', { class: 'subj' }, r.subject), el('div', { class: 'from' }, `${r.tag}${r.from ? ' · ' + r.from : ''}`)), el('span', { class: 'meta' }, r.when || '')));
  if (!rows.length) list.append(el('div', { class: 'empty' }, inboxFilter === 'all' ? 'Nothing yet.' : inboxFilter === 'decide' ? 'Nothing waiting on a decision.' : inboxFilter === 'league' ? 'Nothing from around the league yet.' : 'All read.'));
  const pane = el('div', { class: 'pane' });
  if (cur) {
    const m = pyJSON(`SESSION.inbox_message(${cur.id})`);
    pane.append(el('h3', {}, m.subject), el('div', { class: 'from' }, `${m.tag || cur.tag}${m.from ? ' · ' + m.from : ''}${m.when ? ' · ' + m.when : ''}`), el('div', { class: 'mbody' }, m.body || ''));
    if (m.actions && m.actions.length) { const a = el('div', { class: 'acts', style: 'margin-top:16px' }); for (const act of m.actions) a.append(el('button', { class: 'btn' + (act.primary ? ' go' : ''), onclick: () => { location.hash = act.go || `#portal/inbox/${cur.id}`; } }, act.label)); pane.append(a); }
    else if (m.kind === 'injury_decision' && m.status !== 'done' && m.pid) pane.append(el('div', { class: 'acts', style: 'margin-top:16px' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.club_act('hurt_decision', pid=${JSON.stringify(m.pid)}, play=True)`)); reload(); } }, 'Play Him'), el('button', { class: 'btn', onclick: () => { notify(pyJSON(`SESSION.club_act('hurt_decision', pid=${JSON.stringify(m.pid)}, play=False)`)); reload(); } }, 'Sit Him'), el('a', { class: 'btn quiet', href: '#club/player/' + m.pid }, 'His Card')));
    else if (cur.decide) pane.append(el('div', { class: 'acts', style: 'margin-top:16px' }, el('button', { class: 'btn go', onclick: () => { location.hash = `#portal/inbox/${cur.id}`; } }, 'Open the Decision')));
    else if (m.link) pane.append(el('div', { class: 'acts', style: 'margin-top:16px' }, el('a', { class: 'btn' + (m.kind === 'negotiation' ? ' go' : ''), href: linkHash(m.link) }, m.kind === 'negotiation' ? 'Continue the Negotiation' : 'Go There')));
  } else pane.append(el('div', { class: 'empty' }, 'Select a message.'));
  box.append(list, pane); s.append(box); page.append(s);
}
function linkHash(link) {
  if (!link) return '#portal';
  const [a, b] = String(link).split(':');
  const MAP = { 'club': '#club', 'club:depth': '#club/depth', 'player': '#club/player/', 'league:standings': '#league', 'league:schedule': '#league/schedule', 'league:coaching': '#league/coaching', 'league:awards': '#league/awards', 'league:almanac': '#league/almanac', 'front_office:owner': '#frontoffice', 'front_office:staff': '#frontoffice/staff', 'personnel:extensions': '#personnel/extensions', 'draft:board': '#draft/board' };
  if (a === 'player') return '#club/player/' + b;
  if (a === 'negotiation') { const kind = String(link).split(':')[1] || ''; return kind === 'extension' ? '#personnel/extensions' : kind.startsWith('fa') ? '#personnel/fa' : '#personnel/fa'; }
  return MAP[link] || MAP[a] || '#portal';
}

function renderPortal(v) {
  const page = $('#page'); page.hidden = false; page.innerHTML = '';
  page.className = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Portal';
  document.body.classList.remove('no-second');
  $('#second').innerHTML = `<a aria-current="page" href="#portal">Overview</a><a href="#portal/inbox">Inbox <em>${v.inbox.total}</em></a><a href="#league/schedule">Calendar</a><a href="#league/transactions">News</a><a href="#frontoffice/owner">Owner</a>`;

  // the matchup
  const m = v.matchup;
  const match = el('section', { class: 'sheet c12' });
  if (!m) match.append(el('h2', {}, 'Offseason'), el('div', { class: 'empty' }, 'The season is over. The Advance button walks the offseason one step at a time.'));
  else if (m.bye) match.append(el('h2', {}, `Week ${m.week}`, el('small', {}, 'Bye Week')), el('div', { class: 'empty' }, 'No game this week.'));
  else {
    match.append(el('h2', {}, `Week ${m.week} ${m.away ? 'at' : 'vs'} ${esc(m.them.club.name)}`, el('small', {}, m.header || m.forecast || '')));
    const side = (c, right) => el('div', { class: 'side', style: right ? 'flex-direction:row-reverse;text-align:right' : '' }, el('div', { class: 'cr', style: `background:${c.club.color}` }, c.club.abbr), el('div', {}, el('div', { class: 'nm' }, c.club.nick), el('div', { class: 'rec' }, `${c.record} · ${c.place}`)));
    const bug = el('div', { class: 'bug', style: 'grid-template-columns:auto 1fr auto;padding:12px 12px 4px' },
      side(m.me, false),
      el('div', { class: 'mid' }, el('div', { class: 'lbl' }, 'Win Probability'), el('div', { class: 'wp' }, `${m.wp}%`),
        el('div', { class: 'wpbar' }, el('i', { style: `width:${m.wp}%;background:${m.me.club.color}` }), el('i', { style: `width:${100 - m.wp}%;background:${m.them.club.color}` })),
        el('div', { class: 'lbl', style: 'margin-top:6px;text-transform:none;letter-spacing:0' }, m.line || '')),
      side(m.them, true));
    const facts = el('div', { class: 'facts2', style: 'grid-template-columns:1fr 1fr' },
      el('div', {}, el('span', {}, `${m.me.club.nick} Injuries`), el('b', {}, m.injuries.me.join(' · ') || 'None')),
      el('div', { style: 'text-align:right' }, el('span', {}, `${m.them.club.nick} Injuries`), el('b', {}, m.injuries.them.join(' · ') || 'None')));
    const formRow = el('div', { class: 'form-row' }, el('div', {}, el('div', { class: 'lbl' }, `${m.me.club.nick} Last Five`), formDots(m.form.me, true)), el('div', {}, el('div', { class: 'lbl' }, `${m.them.club.nick} Last Five`), formDots(m.form.them, true)));
    const left = el('div', { class: 'm-side' }, bug, facts, formRow);
    const right = el('div', { class: 'm-right' },
      el('div', { class: 'mh' }, 'Assistants Say', el('a', { class: 'more', href: '#gameplan/report' }, 'Full Opponent Report →')),
      el('div', { class: 'say', style: 'padding:0 12px 10px' }, m.say),
      el('div', { class: 'men-row', style: 'border-top:1px solid var(--rule)' }, ...m.watch.map(w => el('div', {}, el('div', { class: 'lbl' }, 'Players to Watch'), el('button', { class: 'man', onclick: () => { location.hash = '#club/player/' + w.pid; } }, el('div', { class: 'no', style: `background:${m.them.club.color};color:#fff` }, w.no || w.pos), el('div', { class: 'nm' }, w.name.split(' ')[0][0] + '. ' + w.name.split(' ').slice(1).join(' '), el('small', {}, `${w.pos}${w.note ? ' · ' + w.note : ''}`)), el('div', { class: 'ov' }, w.ovr))))));
    match.append(el('div', { class: 'match', style: 'grid-template-columns:1fr 1.1fr' }, left, right));
    match.append(el('div', { class: 'foot' }, el('a', { class: 'btn go', href: '#gameplan' }, 'Set Game Plan'), el('a', { class: 'btn', href: '#gameplan/report' }, 'Opponent Report'), el('a', { class: 'btn', href: '#club/depth' }, 'Depth Chart'), el('button', { class: 'btn quiet', onclick: e => { const b = document.getElementById('series'); if (b) b.hidden = !b.hidden; } }, 'Series History')));
    match.append(el('div', { id: 'series', class: 'read', hidden: '', style: 'margin:0 14px 12px' }, m.series && m.series.length ? m.series.map(g => `Week ${g.week}: ${g.away} ${g.ap} at ${g.home} ${g.hp}`).join(' · ') : 'The clubs have not met this season. Past seasons\' meetings will show here as the almanac fills.'));
  }
  page.append(match);

  // when we have the ball, when they do; what we would do
  if (m && !m.bye && m.panels) {
    const P = m.panels;
    const rkCell = r => el('span', { class: 'rk ' + (r == null ? '' : r <= 8 ? 'good' : r >= 24 ? 'bad' : 'mid-rk') }, r == null ? '—' : `${r}${ord(r)}`);
    const panel = (title, rows, extra, leftHead, rightHead) => {
      const s = el('section', { class: 'sheet c6' }, el('h2', {}, title));
      const box = el('div', { class: 'sides' }, el('div', { class: 'side-row head' }, el('span', {}), el('span', {}, leftHead), el('span', {}), el('span', {}, rightHead)));
      for (const r of rows) box.append(el('div', { class: 'side-row' }, el('span', { class: 'lab' }, r.label), rkCell(r.mine), el('span', { class: 'mid' }, 'vs'), rkCell(r.theirs)));
      (extra || []).forEach((t, i) => box.append(el('div', { class: 'side-row' + (i === 0 ? ' sep' : '') }, el('span', { class: 'lab' }, t.label, t.sub ? el('em', {}, t.sub) : ''), el('span', { class: 'rk', style: 'font-size:17px' }, t.left), el('span', { class: 'mid' }, 'vs'), el('span', { class: 'rk', style: 'font-size:17px' }, t.right))));
      s.append(box); return s;
    };
    page.append(panel(`When ${m.me.club.name} Has the Ball`, P.ours, P.ours_extra, `${m.me.club.abbr} Offense`, `${m.them.club.abbr} Defense`));
    page.append(panel(`When ${m.them.club.name} Has the Ball`, P.theirs, P.theirs_extra, `${m.them.club.abbr} Offense`, `${m.me.club.abbr} Defense`));
    const wwd = el('section', { class: 'sheet c12' }, el('h2', {}, 'What We Would Do', el('small', {}, P.suggestions.length ? `${P.taken.length} of ${P.suggestions.length} taken` : 'the assistants have nothing to add this week')));
    if (P.suggestions.length) {
      const cards = el('div', { class: 'cards', style: 'grid-template-columns:repeat(3,1fr)' });
      for (const sg of P.suggestions) {
        const on = P.taken.includes(sg.i);
        cards.append(el('div', { class: 'card', style: `--k:${sg.side === 'Offense' ? 'var(--ok)' : 'var(--live)'};opacity:${on ? '.75' : '1'}` },
          el('div', { class: 'h' }, el('div', { class: 'k' }, sg.side + (on ? ' · accepted' : '')), el('div', { class: 's' }, sg.text)), el('div', { class: 'b' }, sg.why),
          el('div', { class: 'b', style: 'margin-top:6px' }, el('span', { class: 'lbl', style: 'font-size:12.5px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.04em' }, 'Plan Change '), el('span', { style: 'font-family:var(--mono);font-size:14px' }, sg.change || '—')),
          el('div', { class: 'a' }, on ? el('button', { class: 'btn quiet', onclick: () => { pyJSON(`SESSION.plan_act('untake', i=${sg.i})`); refresh(); } }, 'Undo') : el('button', { class: 'btn go', onclick: () => { pyJSON(`SESSION.plan_act('take', i=${sg.i})`); refresh(); } }, 'Accept'), on ? '' : el('button', { class: 'btn quiet', onclick: e => e.currentTarget.closest('.card').remove() }, 'Skip'))));
      }
      wwd.append(cards, el('div', { class: 'foot' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON('SESSION.plan_take_all()')); location.hash = '#gameplan/week'; } }, 'Accept All and Open Game Plan'), el('a', { class: 'btn', href: '#gameplan/week' }, 'Open Game Plan')));
    }
    page.append(wwd);
  }

  // on your desk: the card by kind, with the decision on it
  const desk = el('section', { class: 'sheet c12' }, el('h2', {}, 'On Your Desk', el('small', {}, `${v.desk.length} waiting`)));
  if (!v.desk.length) desk.append(el('div', { class: 'empty' }, 'Nothing needs you before the next advance.'));
  else desk.append(el('div', { class: 'cards' }, ...v.desk.map(c => {
    const card = el('div', { class: 'card', style: `--k:${c.kind === 'Trade' ? 'var(--live)' : c.kind === 'Contract' ? 'var(--club-2)' : 'var(--decide)'}` });
    if (c.raw_kind === 'trade_offer' && c.buyer) {
      card.append(el('div', { class: 'h' }, el('div', { class: 'k' }, `Trade Offer · ${c.buyer.name}` + (c.expires ? ` · Expires after week ${c.expires}` : '')), el('div', { class: 's' }, c.subject)),
        el('div', { class: 'facts2', style: 'grid-template-columns:1fr 1fr;padding:6px 0' }, el('div', {}, el('span', {}, 'They Send'), el('b', {}, c.they_send || '—')), el('div', {}, el('span', {}, 'Value Gap'), el('b', { style: c.gap != null ? (c.gap >= 0 ? 'color:var(--ok)' : 'color:var(--danger)') : '' }, c.gap != null ? `${c.gap >= 0 ? '+' : '−'}$${Math.abs(c.gap).toFixed(1)}m` : '—'))),
        el('div', { class: 'b' }, `You send ${c.you_send}. ${c.read || ''}`),
        el('div', { class: 'a' }, el('button', { class: 'btn go', onclick: () => { try { pyJSON(`__import__('inbox').accept(SESSION.L, ${c.id}, SESSION.user_team)`); notify({ ok: true, line: 'Trade accepted.' }); } catch (e) { notify({ ok: false, why: 'The offer could not be completed.' }); } refresh(); } }, 'Accept'),
          el('button', { class: 'btn', onclick: () => { tradeState = { other: c.buyer.abbr, a: (c.payload.gets || []).map(String), b: [], keep: true }; location.hash = '#personnel/trades'; } }, 'Counter'),
          el('button', { class: 'btn quiet', onclick: () => { pyJSON(`__import__('inbox').decline(SESSION.L, ${c.id})`); refresh(); } }, 'Decline')));
    } else if (c.ask != null || c.raw_kind === 'contract_year') {
      card.append(el('div', { class: 'h' }, el('div', { class: 'k' }, 'Contracts · Final Year'), el('div', { class: 's' }, c.subject)),
        el('div', { class: 'facts2', style: 'grid-template-columns:1fr 1fr;padding:6px 0' }, el('div', {}, el('span', {}, 'Agent Asks'), el('b', {}, c.ask != null ? `$${c.ask.toFixed(1)}m` : 'Ask him')), el('div', {}, el('span', {}, 'Years Left'), el('b', {}, c.years_left ?? '—'))),
        el('div', { class: 'b' }, c.line || c.body),
        el('div', { class: 'a' }, el('button', { class: 'btn go', onclick: () => { pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(c.pid)}, kind='extension')`); location.hash = '#personnel/extensions'; } }, 'Negotiate'), el('button', { class: 'btn quiet', onclick: () => { pyJSON(`__import__('inbox').read(SESSION.L, ${c.id}); [setattr(_m, 'x', 0) for _m in []]`); pyJSON(`[_m.__setitem__('status', 'read') for _m in __import__('inbox')._box(SESSION.L) if _m['id'] == ${c.id}]`); refresh(); } }, 'Later')));
    } else {
      card.append(el('div', { class: 'h' }, el('div', { class: 'k' }, c.kind), el('div', { class: 's' }, c.subject)), el('div', { class: 'b' }, c.body),
        el('div', { class: 'a', style: 'display:flex;gap:6px' }, el('button', { class: 'btn', onclick: () => location.hash = `#portal/inbox/${c.id}` }, 'Open'), deskAction(c.kind)));
    }
    return card;
  })));
  page.append(desk);

  page.append(inboxSheet(v));

  // cap, room, front office
  const capG = v.cap.by_group; const total = Object.values(capG).reduce((a, b) => a + b, 0) + v.cap.dead;
  const colors = { QB: '#c8102e', OL: '#e0b400', WR: '#4cc9f0', DL: '#3fb37f', DB: '#8791a0', LB: '#b6bec9', TE: '#5a6472', RB: '#a0603a', ST: '#3a3f47' };
  const stack = el('div', { class: 'stack', style: 'margin-top:10px' }, ...Object.entries(capG).filter(([, x]) => x > 0).map(([g, x]) => el('i', { class: (100 * x / v.cap.cap) < 7 ? 'narrow' : '', style: `width:${100 * x / v.cap.cap}%;background:${colors[g]}`, 'data-tip': `${g}: $${x.toFixed(1)}m` }, el('span', {}, g))), el('i', { style: `width:${100 * v.cap.dead / v.cap.cap}%;background:#3a1216`, 'data-tip': `Dead Money: $${v.cap.dead.toFixed(1)}m` }));
  const capS = sheet('Cap', `${v.cap.years[0].year} · $${v.cap.cap}m Limit`, el('div', { class: 'pad' }, el('div', { class: 'big' }, v.cap.space, el('span', { class: 'muted', style: 'font-size:16px;font-family:var(--text);font-weight:500' }, ' Space')), stack,
    el('div', { class: 'bars', style: 'padding:10px 0 0;grid-template-columns:96px 1fr 70px' }, ...v.cap.years.flatMap(y => [el('div', { class: 'l' }, y.year), el('div', { class: 't' }, el('i', { style: `width:${Math.min(100, 100 * y.committed / y.cap)}%;background:var(--ink-2)` })), el('div', { class: 'v' }, `$${y.committed}/${y.cap}`)]))),
    el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#frontoffice/cap' }, 'Restructure'), el('a', { class: 'btn', href: '#personnel/extensions' }, 'Extensions'), el('a', { class: 'btn quiet', href: '#frontoffice/cap' }, 'Ledger')));
  capS.classList.add('c4'); page.append(capS);

  const rc = v.room.counts; const n = Object.values(rc).reduce((a, b) => a + b, 0) || 1;
  const roomS = sheet('The Room', `${n} Players · Morale`, el('div', { class: 'pad' },
    el('div', { class: 'bar' }, el('i', { style: `width:${100 * rc.Unhappy / n}%;background:var(--danger)` }), el('i', { style: `width:${100 * rc.Unsettled / n}%;background:var(--decide)` }), el('i', { style: `width:${100 * rc.Content / n}%;background:var(--rule-hi)` }), el('i', { style: `width:${100 * rc.Happy / n}%;background:var(--ok)` })),
    el('div', { class: 'leg' }, el('span', {}, el('i', { style: 'background:var(--danger)' }), `Unhappy ${rc.Unhappy}`), el('span', {}, el('i', { style: 'background:var(--decide)' }), `Unsettled ${rc.Unsettled}`), el('span', {}, el('i', { style: 'background:var(--rule-hi)' }), `Content ${rc.Content}`), el('span', {}, el('i', { style: 'background:var(--ok)' }), `Happy ${rc.Happy}`))),
    el('div', { class: 'plates', style: 'grid-template-columns:1fr;padding-top:2px' }, ...v.room.watch.map(p => el('button', { class: 'man', onclick: () => location.hash = `#club/player/${p.pid}` }, el('div', { class: 'no' }, p.no || p.pos), el('div', { class: 'nm' }, p.short, el('small', {}, p.note)), el('div', { class: 'ovr' }, p.ovr), el('i', { class: 'pin bad' })))),
    el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#club' }, 'Roster'), el('a', { class: 'btn', href: '#club/depth' }, 'Depth Chart'), el('a', { class: 'btn quiet', href: '#club/ps' }, 'Practice Squad')));
  roomS.classList.add('c4'); page.append(roomS);

  const fo = v.front_office;
  const foS = sheet('Front Office', `${v.owner_name || 'Owner'} · You`, el('div', { class: 'pad' },
    el('div', { class: 'big', style: 'font-size:30px' }, fo.owner_mood), el('div', { class: 'muted', style: 'font-size:15px;margin:2px 0 10px' }, fo.expects || ''),
    el('div', { class: 'kv' }, el('span', {}, 'Your Prestige'), el('b', {}, fo.prestige ?? '—'), el('span', {}, 'Job Security'), el('b', { style: fo.job === 'Hot Seat' ? 'color:var(--danger)' : fo.job === 'Warming' ? 'color:var(--decide)' : '' }, fo.job), el('span', {}, 'Scouting'), el('b', {}, fo.scouting_rank ? `${fo.scouting_rank}${ord(fo.scouting_rank)}` : '—'))),
    el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#frontoffice/identity' }, 'Coaching Identity'), el('a', { class: 'btn', href: '#draft' }, 'Scouting Board'), el('a', { class: 'btn quiet', href: '#league/almanac' }, 'Almanac')));
  foS.classList.add('c4'); page.append(foS);

  // standings and season
  const st = v.standings;
  const table = el('table', {}, el('tr', {}, el('th', {}, ''), el('th', {}, 'Club'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', {}, 'Form'), el('th', { class: 'n' }, 'PF'), el('th', { class: 'n' }, 'PA'), el('th', { class: 'n' }, 'PD')),
    ...st.rows.map(r => el('tr', { class: r.me ? 'me' : '' }, el('td', {}, ''), el('td', {}, stripe(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', {}, formDots(r.form)), el('td', { class: 'n' }, r.pf), el('td', { class: 'n' }, r.pa), el('td', { class: 'n' }, (r.pd > 0 ? '+' : '') + r.pd))));
  const stS = sheet(st.division, '', table, el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#league' }, 'Full Standings')));
  stS.classList.add('c6'); page.append(stS);

  const strip = el('div', { class: 'strip' }, ...v.season.games.map(g => g.bye ? el('div', { class: 'wk bye' }, '—', el('small', {}, 'bye')) : el('div', { class: 'wk' + (g.result ? ' ' + g.result.toLowerCase() : '') + ((view.rail.advance.title.match(/Week (\d+)/) || [])[1] == g.week ? ' now' : ''), 'data-tip': g.score ? `${g.home ? 'vs' : 'at'} ${g.opp} · ${g.score}` : null }, g.result || g.week, el('small', {}, `${g.home ? '' : '@'}${g.opp}`))));
  const nums = v.season.numbers || {}; const numRow = el('div', { class: 'facts2', style: 'grid-template-columns:repeat(4,1fr);padding:8px 0 0' }, el('div', {}, el('span', {}, 'Points For'), el('b', {}, nums.pf ?? '—')), el('div', {}, el('span', {}, 'Points Against'), el('b', {}, nums.pa ?? '—')), el('div', {}, el('span', {}, 'EPA per Play'), el('b', {}, nums.epa != null ? (nums.epa >= 0 ? '+' : '') + nums.epa.toFixed(2) : '—')), el('div', {}, el('span', {}, 'Pass Rush Win'), el('b', {}, nums.prw != null ? `${nums.prw}%` : '—')));
  const seS = sheet('The Season', view.rail.record, strip, numRow, el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#league/schedule' }, 'Schedule'), el('a', { class: 'btn', href: '#league/stats' }, 'Stats'), el('a', { class: 'btn quiet', href: '#league' }, 'Playoff Picture')));
  seS.classList.add('c6'); page.append(seS);
}

function tagClass(t) { return ({ Trade: 'trade', Contract: 'contract', Wire: 'wire', Squad: 'squad', Game: 'game', Scouting: 'scout', 'Locker Room': 'room', Assistants: 'assist', Owner: 'owner', Staff: 'owner' })[t] || ''; }
function ord(n) { return n === 1 ? 'st' : n === 2 ? 'nd' : n === 3 ? 'rd' : 'th'; }

function openMessage(id) {
  py.runPython(`import inbox as IB\nfor _m in IB._box(SESSION.L):\n    if _m['id'] == ${id} and _m['status'] == 'unread': _m['status'] = 'read'`);
  const m = pyJSON(`next(_m for _m in __import__('inbox')._box(SESSION.L) if _m['id'] == ${id})`);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = '1fr';
  const acts = el('div', { class: 'foot' });
  if (m.kind === 'injury_decision' && m.status !== 'done' && m.payload && m.payload.pid) {
    const pid = m.payload.pid;
    acts.append(el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.club_act('hurt_decision', pid=${JSON.stringify(pid)}, play=True)`)); location.hash = '#portal/inbox'; } }, 'Play Him'),
      el('button', { class: 'btn', onclick: () => { notify(pyJSON(`SESSION.club_act('hurt_decision', pid=${JSON.stringify(pid)}, play=False)`)); location.hash = '#portal/inbox'; } }, 'Sit Him'),
      el('a', { class: 'btn quiet', href: '#club/player/' + pid }, 'His Card'));
  } else if (m.kind === 'injury_decision') acts.append(el('span', { class: 'count' }, 'Decided.'));
  if (m.payload && m.payload.link) acts.append(el('a', { class: 'btn go', href: linkHash(m.payload.link) }, m.kind === 'negotiation' ? 'Continue the Negotiation' : 'Go There'));
  acts.append(el('button', { class: 'btn quiet', onclick: () => refresh() }, 'Back to Portal'));
  page.append(el('section', { class: 'sheet' }, el('h2', {}, m.subject, el('small', {}, `${m.sender || ''} · ${m.year} Week ${m.week}`)), el('div', { class: 'pad', style: 'max-width:70ch;line-height:1.5;color:var(--ink-2)' }, m.body), acts));
}


// ---------------------------------------------------------------- Game Day
function renderGameDay(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Game Day';
  $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'gameday'));
  $('#second').innerHTML = ''; document.body.classList.add('no-second');
  if (v.empty) { page.append(el('section', { class: 'sheet c12' }, el('h2', {}, 'Game Day'), el('div', { class: 'empty' }, v.line))); return; }
  if (v.preview) {
    // the week has not been played: the preview of this week's game, and the button that plays it
    const s = el('section', { class: 'sheet c12' }, el('h2', {}, `Week ${v.week} · Game Day`, el('small', {}, v.bye ? 'Bye week' : `${v.matchup.away ? 'at' : 'vs'} ${v.matchup.them.club.name} · ${v.matchup.header || ''}`)));
    if (v.bye) { s.append(el('div', { class: 'empty' }, v.line)); }
    else {
      const m = v.matchup;
      s.append(el('div', { class: 'bigbug' },
        el('div', { class: 'side' }, el('div', { class: 'cr', style: `background:${m.me.club.color}` }, m.me.club.abbr), el('div', {}, el('div', { class: 'nm' }, m.me.club.nick), el('div', { class: 'rec' }, `${m.me.record} · ${m.me.place}`))),
        el('div', { class: 'mid' }, el('div', { class: 'q' }, 'Kickoff Sunday'), el('div', { class: 'dd' }, `Win Probability ${m.wp}%`), el('div', { class: 'q', style: 'font-size:12.5px;color:var(--ink-3);margin-top:4px' }, m.line || '')),
        el('div', { class: 'side', style: 'flex-direction:row-reverse;text-align:right' }, el('div', { class: 'cr', style: `background:${m.them.club.color}` }, m.them.club.abbr), el('div', {}, el('div', { class: 'nm' }, m.them.club.nick), el('div', { class: 'rec' }, `${m.them.record} · ${m.them.place}`)))));
      s.append(el('div', { class: 'facts2', style: 'grid-template-columns:1fr 1fr;padding:6px 14px' }, el('div', {}, el('span', {}, `${m.me.club.nick} Injuries`), el('b', {}, m.injuries.me.join(' · ') || 'None')), el('div', { style: 'text-align:right' }, el('span', {}, `${m.them.club.nick} Injuries`), el('b', {}, m.injuries.them.join(' · ') || 'None'))));
      s.append(el('div', { class: 'read', style: 'margin:0 14px 10px' }, el('b', {}, 'Assistants: '), m.say));
      s.append(el('div', { class: 'read', style: 'margin:0 14px 12px;color:var(--ink-2)' }, v.plan_set ? 'Your game plan for this week is set.' : "You have not changed the coordinators' plan this week; the game reads their plan as it stands."));
    }
    s.append(el('div', { class: 'foot' }, el('button', { class: 'btn go', onclick: () => { $('#advance').click(); } }, `Sim Week ${v.week}`), el('a', { class: 'btn', href: '#gameplan' }, 'Game Plan'), el('a', { class: 'btn', href: '#gameplan/report' }, 'Opponent Report'), el('a', { class: 'btn quiet', href: '#club/depth' }, 'Depth Chart'), el('span', { class: 'count', style: 'margin-left:auto' }, 'Every club plays this week when you sim; the week itself moves on when you Advance.')));
    page.append(s); return;
  }
  const g = v.game;
  const top = el('section', { class: 'sheet c12' });
  // the Sunday scoreboard
  const sb = el('div', { class: 'scoreboard' });
  for (const s of v.scores) {
    const hw = s.hs > s.as_, aw = s.as_ > s.hs;
    sb.append(el('div', { class: 'sb' + (s.mine ? ' mine' : '') },
      el('div', { class: 'row' + (aw ? ' w' : '') }, stripe(s.away.abbr), el('b', {}, s.as_)),
      el('div', { class: 'row' + (hw ? ' w' : '') }, stripe(s.home.abbr), el('b', {}, s.hs)),
      el('div', { class: 'st' }, el('span', {}, 'Final' + (s.ot ? ' · OT' : '')))));
  }
  top.append(sb);
  if (!g) { top.append(el('div', { class: 'empty' }, 'Your club was on its bye this week.')); page.append(top); return; }
  // the big bug: it follows the reveal (score, quarter and clock, situation, win probability), Final once the game is played out
  const me = g.me_home ? g.home : g.away, them = g.me_home ? g.away : g.home;
  const rec = r => `${r[0]}–${r[1]}`;
  const bug = el('div', { class: 'bigbug' }); top.append(bug);
  const lineScore = el('table', { class: 'linescore' }); top.append(lineScore);
  const drawBug = (shown, shownPlays) => {
    const final = shown >= g.drives.length && shownPlays == null;
    const d = g.drives[Math.max(0, shown - 1)]; const revealed = (shownPlays != null ? vis(d).slice(0, shownPlays) : vis(d));
    const atBreak = shownPlays == null && shown < g.drives.length && g.drives[shown].quarter > d.quarter;   // the drive shown was the quarter's last
    let hs = g.hs, as_ = g.as_;
    if (!final) { const prev = g.drives[shown - 2]; const src = (shownPlays != null ? prev : d); const sc = src ? String(src.score).split('–') : ['0', '0']; hs = +sc[0]; as_ = +sc[1]; if (shownPlays != null) { const add = (n, toOff) => { if ((d.off === g.home.abbr) === toOff) hs += n; else as_ += n; }; for (const p of revealed) { if (p.type === 'field_goal' && p.made) add(3, true); else if (p.td) add(6, true); else if (p.type === 'extra_point' && p.made !== false) add(1, true); else if (p.type === 'two_point' && p.made) add(2, true); else if (p.safety) add(2, false); } } }
    const lastPlay = revealed.length ? revealed[revealed.length - 1] : null;
    const headParts = lastPlay && lastPlay.head ? lastPlay.head.split(' · ') : [];
    const clock = atBreak ? '0:00' : (headParts.length >= 3 ? headParts[headParts.length - 1] : '');
    const wpNow = g.wp[Math.min(g.wp.length - 1, Math.max(0, shown - 1))];
    const myScore = g.me_home ? hs : as_, theirScore = g.me_home ? as_ : hs;
    const won = myScore > theirScore, tie = myScore === theirScore;
    bug.innerHTML = '';
    bug.append(
      el('div', { class: 'side' }, el('div', { class: 'cr', style: `background:${g.away.color}` }, g.away.abbr), el('div', {}, el('div', { class: 'nm' }, g.away.nick), el('div', { class: 'rec' }, rec(g.away_rec) + (!final && d.off === g.away.abbr ? ' · Ball' : ''))), el('div', { class: 'score', style: 'margin-left:auto' }, as_)),
      el('div', { class: 'mid' }, el('div', { class: 'q' }, final ? 'Final' + (g.ot ? ' · Overtime' : '') : atBreak ? (d.quarter === 2 ? 'Halftime' : d.quarter >= 4 ? 'End of Regulation' : `End of Q${d.quarter}`) : `Q${d.quarter}${clock ? ' · ' + clock : ''}`), el('div', { class: 'dd' }, final ? (tie ? 'A tie' : won ? `${me.name} wins` : `${them.name} wins`) : atBreak ? `${d.off} ${String(d.result || '').toLowerCase()}`.trim() : (lastPlay && lastPlay.head ? lastPlay.head.split(' · ').slice(0, 2).join(' · ') : `Drive ${d.n} · ${d.off} ball`)), el('div', { class: 'q', style: 'font-size:12.5px;color:var(--ink-3);margin-top:4px' }, `Win Probability ${wpNow}%` + (g.env && g.env.conditions ? ` · ${g.env.conditions}` : ''))),
      el('div', { class: 'side', style: 'flex-direction:row-reverse;text-align:right' }, el('div', { class: 'cr', style: `background:${g.home.color}` }, g.home.abbr), el('div', {}, el('div', { class: 'nm' }, g.home.nick), el('div', { class: 'rec' }, rec(g.home_rec) + (!final && d.off === g.home.abbr ? ' · Ball' : ''))), el('div', { class: 'score', style: 'margin-right:auto' }, hs)));
    lineScore.innerHTML = '';
    if (g.quarters && g.quarters[g.home.abbr]) {
      const Q = g.quarters; const upto = final ? 5 : d.quarter; const hasOT = Q[g.home.abbr][4] || Q[g.away.abbr][4];
      lineScore.append(el('tr', {}, el('th', {}, ''), ...['Q1', 'Q2', 'Q3', 'Q4'].concat(hasOT ? ['OT'] : []).map(q => el('th', {}, q)), el('th', {}, 'T')));
      for (const ab of [g.away.abbr, g.home.abbr]) lineScore.append(el('tr', {}, el('td', {}, ab), ...Q[ab].slice(0, hasOT ? 5 : 4).map((x, qi) => el('td', {}, final || qi < upto - 1 ? x : qi === upto - 1 ? (ab === g.home.abbr ? hs : as_) - Q[ab].slice(0, qi).reduce((a, b) => a + b, 0) : '')), el('td', { style: 'font-weight:700' }, ab === g.home.abbr ? hs : as_)));
    }
  };
  // win probability by drive
  const W = 720, H = 70; const pts = g.wp.map((p, i) => [i / Math.max(1, g.wp.length - 1) * W, H - 4 - (p / 100) * (H - 8)]);
  const svgNS = 'http://www.w3.org/2000/svg'; const svg = document.createElementNS(svgNS, 'svg'); svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('preserveAspectRatio', 'none');
  const mk = (tag, attrs) => { const e = document.createElementNS(svgNS, tag); for (const [k, val] of Object.entries(attrs)) e.setAttribute(k, val); return e; };
  svg.append(mk('line', { x1: 0, y1: H / 2, x2: W, y2: H / 2, stroke: '#3a424c' }));
  [0.25, 0.5, 0.75].forEach(f => svg.append(mk('line', { x1: f * W, y1: 0, x2: f * W, y2: H, stroke: '#2e353e' })));
  svg.append(mk('polyline', { fill: 'none', stroke: me.color, 'stroke-width': 2, points: pts.map(p => p.join(',')).join(' ') }));
  const t1 = mk('text', { x: 4, y: 12, fill: '#7b8593', 'font-size': 10, 'font-family': 'Big Shoulders Text' }); t1.textContent = me.abbr; const t2 = mk('text', { x: 4, y: H - 4, fill: '#7b8593', 'font-size': 10, 'font-family': 'Big Shoulders Text' }); t2.textContent = them.abbr; svg.append(t1, t2);
  const wpc = el('div', { class: 'wpchart' }); wpc.append(svg); top.append(wpc);
  page.append(top);

  // the ticker, revealed by drive
  const tick = el('section', { class: 'sheet c8' });
  const gkey = `${g.home.abbr}-${g.away.abbr}-${v.week || ''}-${v.year || ''}`;
  const saved = gdReveal[gkey] || { shown: 1, shownPlays: 0 };
  let shown = saved.shown, shownPlays = saved.shownPlays;      // shownPlays: within the last shown drive, how many plays are revealed (null = all)
  const body = el('div', { class: 'ticker' });
  const filt = { mode: 'all' };
  const draw = () => {
    body.innerHTML = '';
    g.drives.slice(0, shown).forEach((d, di) => {
      const last = di === shown - 1; const plays = (last && shownPlays != null) ? vis(d).slice(0, shownPlays) : d.plays;
      body.append(el('div', { class: 'drive' }, (last && shownPlays != null) ? `Drive ${d.n} · ${d.off} · Q${d.quarter} · ${(d.head || '').split(' · ').slice(2, 3).join('')}` : `Q${d.quarter} · ${d.head || `Drive ${d.n} · ${d.off}`} · ${d.score}`));
      for (const p of plays) {
        if (!p.text) continue;
        if (filt.mode === 'key' && !['score', 'turnover', 'loss'].includes(p.kind) && !(p.type === 'complete' && /for (\d\d) yards/.test(p.text) && +p.text.match(/for (\d\d) yards/)[1] >= 15)) continue;
        if (filt.mode === 'score' && p.kind !== 'score') continue;
        const line = el('div', { class: 'pl ' + p.kind }); if (p.head) line.append(el('span', { class: 'dn' }, p.head), '  '); line.append(p.text); body.append(line);
      }
    });
    tick.querySelector('h2 small').textContent = (shown >= g.drives.length && shownPlays == null) ? 'Final' : `Drive ${shown} of ${g.drives.length}` + (shownPlays != null ? ` · play ${shownPlays} of ${vis(g.drives[shown - 1]).length}` : '');
    body.scrollTop = body.scrollHeight;
    gdReveal[gkey] = { shown, shownPlays };
    drawBug(shown, shownPlays); drawLiveBox(shown, shownPlays); drawRead(shown >= g.drives.length && shownPlays == null);
  };
  const vis = d => d.plays.filter(p => p.text);
  // the first drive opens one play at a time too
  const nextPlay = () => { const d = g.drives[shown - 1]; const n = vis(d).length; if (shownPlays == null || shownPlays >= n) { if (shownPlays != null && shownPlays >= n) shownPlays = null; if (shown >= g.drives.length) { shownPlays = null; draw(); return; } shown++; shownPlays = 1; } else shownPlays++; if (shownPlays >= vis(g.drives[shown - 1]).length) shownPlays = null; draw(); };
  const quarterEnd = q => { let i = g.drives.findIndex(d => d.quarter > q); return i < 0 ? g.drives.length : i; };   // how many drives are in through the end of quarter q
  const nextQuarter = () => { shownPlays = null; const q = g.drives[Math.min(shown, g.drives.length) - 1].quarter; const end = quarterEnd(q); shown = (shown >= end) ? quarterEnd(q + 1) : end; draw(); };
  const ctrl = el('div', { class: 'ctrl2' },
    el('button', { class: 'btn', 'data-tip': 'One snap at a time', onclick: nextPlay }, 'Next Play'),
    el('button', { class: 'btn go', 'data-tip': 'Through the end of this drive, or the next one if this one is in', onclick: () => { if (shownPlays != null) { shownPlays = null; } else shown = Math.min(g.drives.length, shown + 1); draw(); } }, 'Next Drive'),
    el('button', { class: 'btn', 'data-tip': 'Through the end of the quarter', onclick: nextQuarter }, 'Next Quarter'),
    el('button', { class: 'btn', 'data-tip': 'Through the end of the second quarter', onclick: () => { shownPlays = null; shown = Math.max(shown, quarterEnd(2)); draw(); } }, 'To Halftime'),
    el('button', { class: 'btn', onclick: () => { shownPlays = null; shown = g.drives.length; draw(); } }, 'Finish Game'),
    el('span', { class: 'sep' }),
    (() => { const t = el('div', { class: 'tabs' }); ['all', 'key', 'score'].forEach(m => t.append(el('button', { 'aria-pressed': String(m === 'all'), onclick: e => { filt.mode = m; t.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); draw(); } }, { all: 'Every Play', key: 'Key Plays', score: 'Scoring' }[m]))); return t; })());
  tick.append(el('h2', {}, 'Play by Play', el('small', {}, '')), ctrl, body);
  page.append(tick);

  // the right column: team stats and the assistants' read; the box score sits under the ticker at its width
  const right = el('section', { class: 'sheet c4' });
  const boxSheet = el('section', { class: 'sheet c8' });
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
    box.append(th('Defense', 'Tkl', 'Sk', 'INT', 'PD', '')); D.forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.tkl), el('td', {}, r.sk), el('td', {}, r.int_), el('td', {}, r.pd), el('td', {}, ''))));
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
    const final = shown >= g.drives.length && shownPlays == null;
    tsTable.innerHTML = ''; tsTable.append(el('tr', {}, el('th', {}, ''), el('th', {}, g.away.abbr), el('th', {}, g.home.abbr)));
    right.querySelector('.ts-note').textContent = final ? 'Final' : 'Live';
    let A, H;
    if (final) { A = g.team_stats[g.away.abbr]; H = g.team_stats[g.home.abbr]; }
    else {
      const mk = () => ({ plays: 0, yards: 0, pass_yds: 0, rush_yds: 0, first_downs: 0, turnovers: 0, sacks_allowed: 0, penalties: 0, ypp: 0, third: '—', fourth: '—', red_zone: '—', top: '—' });
      const T = { [g.away.abbr]: mk(), [g.home.abbr]: mk() };
      g.drives.slice(0, shown).forEach((d, di) => { const last = di === shown - 1; const plays = (last && shownPlays != null) ? d.plays.filter(p => p.text).slice(0, shownPlays) : d.plays; const t = T[d.off]; if (!t) return;
        for (const p of plays) { if (!p.type) continue; const y = p.yards || 0;
          if (['run', 'scramble'].includes(p.type)) { t.plays++; t.yards += y; t.rush_yds += y; }
          else if (['complete', 'incomplete', 'drop', 'interception', 'sack'].includes(p.type)) { t.plays++; if (p.type === 'complete') { t.yards += y; t.pass_yds += y; } if (p.type === 'sack') { t.yards += y; t.pass_yds += y; t.sacks_allowed++; } if (p.type === 'interception') t.turnovers++; }
          else if (p.type === 'penalty') t.penalties++;
          if (p.kind === 'turnover' && p.type !== 'interception' && !p.safety) t.turnovers++;
        }
        if (!(last && shownPlays != null)) t.first_downs += (d.first_downs || 0);
      });
      for (const t of Object.values(T)) t.ypp = t.plays ? (t.yards / t.plays).toFixed(1) : '0.0';
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
let inboxFilter = 'all', inboxDense = false;
function secondRow(items, current) {
  document.body.classList.remove('no-second');
  const s = $('#second'); s.innerHTML = '';
  for (const [label, hash] of items) s.append(el('a', { href: hash, 'aria-current': hash === current ? 'page' : null }, label));
}
function pill(word) { return el('span', { class: 'pill ' + word.toLowerCase() }, word); }
function condBar(c) { return el('span', { class: 'cond' }, el('i', { class: c < 60 ? 'low' : c < 80 ? 'mid' : '', style: `width:${c}%` })); }
function ovrCell(o) { return el('span', { class: 'ovr ' + (o >= 88 ? 't1' : o >= 76 ? 't2' : 't3') }, o); }
function fitCell(f) { return el('span', { class: 'fit ' + (f > 0.05 ? 'p' : f < -0.05 ? 'm' : 'z') }, (f > 0 ? '+' : '') + f.toFixed(1)); }
function who(r) { return el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.no || r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, [r.college, r.season_no ? `${r.season_no}${ord(r.season_no)} season` : null].filter(Boolean).join(' · ')))); }

let rosterSide = 'All', rosterQuery = '', rosterSel = null;
let viewClub = null;   // null = your own club; an abbreviation = another club's page, read-only
const CLUB_LIST = () => (view && view.rail && view.rail.clubs) ? view.rail.clubs : Object.keys(COLOR).sort().map(a => ({ abbr: a, name: a }));
function clubSelect(current, onPick) {
  const sel = el('select', { class: 'btn', style: 'width:auto;padding:4px 8px', 'data-tip': "Look at another club's roster and depth chart" });
  const clubs = pyJSON('SESSION.club_list()');
  for (const c of clubs) sel.append(el('option', { value: c.abbr, selected: c.abbr === current ? '' : null }, `${c.name}${c.mine ? ' (User)' : ''}`));
  sel.onchange = () => onPick(sel.value);
  return sel;
}
function clubNav(abbr, mine, current) {
  // the club's own sub-tabs: your club keeps its pages, another club's live under its team page
  if (mine) return [['Roster', '#club'], ['Depth Chart', '#club/depth'], ['Practice Squad', '#club/ps'], ['Injured Reserve', '#club/ir'], ['Progression', '#club/progression']];
  return [['Team', `#league/team/${abbr}`], ['Roster', `#league/team/${abbr}/roster`], ['Depth Chart', `#league/team/${abbr}/depth`], ['Practice Squad', `#league/team/${abbr}/ps`]];
}

function renderRoster(v) {
  renderRail(v.rail);
  const mine = v.mine !== false; const abbr = v.club_abbr || v.rail.club.abbr;
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = mine ? 'Club' : 'League'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === (mine ? 'club' : 'league')));
  secondRow(clubNav(abbr, mine, null), mine ? (clubTab === 'ps' ? '#club/ps' : clubTab === 'ir' ? '#club/ir' : '#club') : (clubTab === 'ps' ? `#league/team/${abbr}/ps` : `#league/team/${abbr}/roster`));
  const sheet = el('section', { class: 'sheet c12' });
  if (!mine) sheet.append(el('h2', {}, `${abbr} Roster`));
  const tabs = el('div', { class: 'tabs' });
  for (const [k, label, n] of [['active', 'Active', v.count], ['ps', 'Practice Squad', v.practice.length], ['injured', 'Injured', v.injured.length]])
    tabs.append(el('button', { 'aria-pressed': String(clubTab === k), onclick: () => { clubTab = k; const want = mine ? (k === 'ps' ? '#club/ps' : k === 'ir' ? '#club/ir' : k === 'active' ? '#club' : null) : (k === 'ps' ? `#league/team/${abbr}/ps` : k === 'active' ? `#league/team/${abbr}/roster` : null); if (want && location.hash !== want) { location.hash = want; } else renderRoster(v); } }, label + ' ', el('em', {}, n)));
  const views = el('div', { class: 'tabs', style: 'margin-left:14px' });
  for (const k of ['Overview', 'Ratings', 'Contract', 'Stats']) views.append(el('button', { 'aria-pressed': String(clubView === k), onclick: () => { clubView = k; renderRoster(v); } }, k));
  const sides = el('div', { class: 'chips' });
  for (const k of ['All', 'Offense', 'Defense', 'Specialists']) sides.append(el('button', { class: 'chip', 'aria-pressed': String(rosterSide === k), onclick: () => { rosterSide = k; renderRoster(v); } }, k));
  const search = el('input', { type: 'search', class: 'find', placeholder: 'Find a player', value: rosterQuery }); search.oninput = () => { rosterQuery = search.value; drawRows(); };
  const count = el('span', { class: 'count', style: 'margin-left:auto' });
  const pick = clubSelect(abbr, a => { const m = pyJSON('SESSION.club_list()').find(c => c.abbr === a); location.hash = m && m.mine ? (clubTab === 'ps' ? '#club/ps' : '#club') : `#league/team/${a}/${clubTab === 'ps' ? 'ps' : 'roster'}`; });
  sheet.append(el('div', { class: 'tools' }, pick, tabs, views, sides, search, count));
  const tbl = el('table', { class: 'tbl' });
  const H = (t, tip, n) => el('th', { 'data-tip': tip || null, class: n ? 'n' : null }, t);
  const heads = { Overview: [H('Player'), H('Pos', 'Position'), H('Age', null, 1), H('Ovr', 'Overall Rating', 1), H('Fit', "How well the player matches your coach's scheme", 1), H('Dev', 'Rate of XP Growth'), H('Condition', 'Game-day Freshness'), H('Morale', "Player's happiness"), H('Yrs', 'Years left on his contract', 1), H('Cap Hit', "This year's cap hit", 1), H('Penalty', 'Dead cap charged if player is cut/traded', 1), H('Status'), H('')],
                  Ratings: [H('Player'), H('Pos', 'Position'), H('Age', null, 1), H('Ovr', 'Overall Rating', 1), H('Ceiling', "The player's estimated potential", 1), H('Dev', 'Rate of XP Growth'), H('Fit', "How well the player matches your coach's scheme", 1), H('Morale', "Player's happiness"), H('')],
                  Contract: [H('Player'), H('Pos', 'Position'), H('Age', null, 1), H('Yrs', 'Years left on his contract', 1), H('Cap Hit', "This year's cap hit", 1), H('Penalty', 'Dead cap charged if player is cut/traded', 1), H('Status'), H('')],
                  Stats: [H('Player'), H('Pos', 'Position'), H('G', 'Games played', 1), H('This Season'), H('Comp%', 'Completion pct for a quarterback, catch pct for a receiver', 1), H('EPA', 'Expected points added per dropback, rush, target or defensive play by position', 1), H('')] }[clubView];
  const hasStatus = ['Overview', 'Contract'].includes(clubView);
  if (clubTab === 'ps' || clubTab === 'ir') { heads.splice(heads.length - (hasStatus ? 2 : 1), hasStatus ? 2 : 1); heads.push(el('th', {}, clubTab === 'ir' ? 'IR' : '')); }
  const acts = r => el('td', {}, el('div', { class: 'row-act' },
    el('button', { title: 'Card', 'data-tip': 'Open his card', onclick: e => { e.stopPropagation(); location.hash = '#club/player/' + r.pid; } }, '▣'),
    el('button', { title: 'Extend', 'data-tip': 'Ask his agent and open the talks', onclick: e => { e.stopPropagation(); const res = pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind='extension')`); notify(res); if (res.ok) location.hash = '#personnel/extensions'; } }, '$'),
    el('button', { title: 'Trade Block', 'data-tip': 'Put him in a trade package', onclick: e => { e.stopPropagation(); tradeState = { other: tradeState.other, a: [r.pid], b: [], keep: true }; location.hash = '#personnel/trades'; } }, '⇄')));
  const drawRows = () => {
    tbl.innerHTML = ''; tbl.append(el('tr', {}, ...heads));
    const q = rosterQuery.trim().toLowerCase(); let shown = 0;
    const rowsFor = () => clubTab === 'ps' ? [{ title: 'Practice Squad', rows: v.practice }] : clubTab === 'ir' ? [{ title: `Injured Reserve · ${v.ir_returns_left} returns left`, rows: v.ir || [] }] : clubTab === 'injured' ? [{ title: 'Injured', rows: v.injured }] : v.groups;
    for (const g of rowsFor()) {
      const rows = g.rows.filter(r => (rosterSide === 'All' || r.side === rosterSide.toLowerCase().replace('specialists', 'special')) && (!q || r.name.toLowerCase().includes(q) || (r.college || '').toLowerCase().includes(q) || r.pos.toLowerCase() === q));
      if (!rows.length) continue;
      tbl.append(el('tr', { class: 'grp' }, el('td', { colspan: String(heads.length) }, `${g.title} · ${rows.length}`)));
      for (const r of rows) {
        shown++;
        const cells = { Overview: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, fitCell(r.fit)), el('td', {}, el('span', { class: 'dev' + (r.dev === 'Star' || r.dev === 'Superstar' || r.dev === 'X-Factor' ? ' star' : '') }, r.dev)), el('td', {}, condBar(r.cond)), el('td', {}, pill(r.morale)), el('td', { class: 'n' }, r.yrs), el('td', { class: 'n' }, `$${r.hit.toFixed(1)}m`), el('td', { class: 'n' }, `$${r.penalty.toFixed(1)}m`), el('td', {}, el('span', { class: 'inj' }, r.status))],
                        Ratings: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, r.pot_range ? `${r.pot_range[0]}–${r.pot_range[1]}` : (r.pot ?? '—')), el('td', {}, el('span', { class: 'dev' + (r.dev === 'Star' || r.dev === 'Superstar' || r.dev === 'X-Factor' ? ' star' : '') }, r.dev)), el('td', { class: 'n' }, fitCell(r.fit)), el('td', {}, pill(r.morale))],
                        Contract: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, r.yrs), el('td', { class: 'n' }, `$${r.hit.toFixed(1)}m`), el('td', { class: 'n' }, `$${r.penalty.toFixed(1)}m`), el('td', {}, el('span', { class: 'inj' }, r.status))],
                        Stats: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.stats.games), el('td', { style: 'text-align:left;font-family:var(--mono);font-size:14px' }, r.stats.line), el('td', { class: 'n' }, r.stats.comp != null ? `${r.stats.comp}%` : '—'), el('td', { class: 'n', style: r.stats.epa != null ? (r.stats.epa > 0 ? 'color:var(--ok)' : 'color:var(--danger)') : '' }, r.stats.epa != null ? (r.stats.epa > 0 ? '+' : '') + r.stats.epa.toFixed(2) : '—')] }[clubView]();
        if (clubTab === 'ps' || clubTab === 'ir') { if (hasStatus) cells.splice(cells.length - 1, 1); }   // the squad and IR pages carry no Status column and no card/agent/trade icons
        else if (!mine) { if (hasStatus) cells.splice(cells.length - 1, 1); cells.push(el('td', {}, el('div', { class: 'row-act' }, el('button', { title: 'Card', 'data-tip': 'Open his card', onclick: e => { e.stopPropagation(); location.hash = '#club/player/' + r.pid; } }, '▣'), el('button', { title: 'Trade', 'data-tip': 'Ask about him in a trade', onclick: e => { e.stopPropagation(); tradeState = { other: abbr, a: [], b: [r.pid] }; location.hash = '#personnel/trades'; } }, '⇄')))); }
        else cells.push(acts(r));
        if (clubTab === 'ir') cells.push(el('td', {}, el('div', { class: 'row-act', style: 'opacity:1' }, el('span', { class: 'muted', style: 'font-size:12px;margin-right:6px' }, r.returnable ? `placed wk ${r.ir_week}` : 'season'), el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', disabled: r.can_activate ? null : '', 'data-tip': r.can_activate ? 'Back to the 53 (a spot must be open)' : (r.returnable ? 'Four weeks on the list and healthy first' : 'Placed for the season; no return'), onclick: () => { const res = pyJSON(`SESSION.club_act('ir_activate', pid=${JSON.stringify(r.pid)})`); notify(res); renderRoster(pyJSON('SESSION.club_roster()')); } }, 'Activate'))));
        if (clubTab === 'ps' && !mine) {
          cells.push(el('td', {}, el('div', { class: 'row-act', style: 'opacity:1' }, el('button', { class: 'btn go', style: 'width:auto;padding:3px 8px;font-size:14px', 'data-tip': "Sign him to your 53. Any club may; he leaves their squad when he signs, and must stay on your active roster three weeks", onclick: () => { const res = pyJSON(`SESSION.personnel_act('poach_ps', pid=${JSON.stringify(r.pid)})`); notify(res.ok ? { ok: true, line: res.line } : res); if (res.ok) location.hash = '#personnel/fa'; } }, 'Sign to Your Roster'))));
        } else if (clubTab === 'ps') {
          const act = (name, extra) => { const res = pyJSON(`SESSION.club_act(${JSON.stringify(name)}, ${extra})`); busy(res.ok ? (res.moves ? res.moves.map(m => `${m.name} ${m.how}`).join(', ') : `${res.name}: done.`) : res.why); setTimeout(() => busy(null), 2200); renderRoster(pyJSON('SESSION.club_roster()')); };
          cells.push(el('td', {}, el('div', { class: 'row-act', style: 'opacity:1' },
            el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', 'data-tip': 'Sign him to the 53 at the minimum', onclick: () => act('call_up', `pid=${JSON.stringify(r.pid)}`) }, 'Call Up'),
            el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', disabled: r.elevated_now ? '' : null, 'data-tip': `Dress him Sunday and send him back after · ${r.elevations} of ${v.per_man_max} used`, onclick: () => act('elevate', `pids=[${JSON.stringify(r.pid)}]`) }, r.elevated_now ? 'Elevated' : `Elevate · ${r.elevations}/${v.per_man_max}`),
            el('button', { class: 'btn warn', style: 'width:auto;padding:3px 8px;font-size:14px', onclick: () => { if (confirm(`Release ${r.name} from the practice squad?`)) act('release_ps', `pid=${JSON.stringify(r.pid)}`); } }, 'Release'))));
        }
        const tr = el('tr', { class: (/^Out/.test(r.status) ? 'out' : '') + (rosterSel === r.pid ? ' sel' : ''), onclick: e => { if (e.target.closest('.row-act') || e.target.closest('.who')) return; rosterSel = rosterSel === r.pid ? null : r.pid; drawRows(); drawFoot(); } }, ...cells);
        tbl.append(tr);
      }
    }
    count.textContent = `${shown} of ${v.count} on the roster · Cap $${v.cap_total.toFixed(1)}m` + (v.practice.length ? ` · Practice Squad $${v.ps_charge}m` : '');
  };
  const foot = el('div', { class: 'foot' });
  const drawFoot = () => {
    foot.innerHTML = '';
    if (!mine) { foot.append(el('span', { class: 'count' }, `${v.count} on the 53 · ${v.practice.length} on the practice squad`)); return; }
    const all = [...v.groups.flatMap(g => g.rows), ...v.practice, ...v.injured]; const r = all.find(x => x.pid === rosterSel);
    if (!r) { foot.append(el('span', { class: 'count' }, clubTab === 'ps' ? `Elevations this week: ${v.elevations_used} of ${v.elevations_max} · a player's ${v.per_man_max + 1}${ord(v.per_man_max + 1)} elevation signs him to the 53` : 'Click a row to select a player, then act on him here.')); return; }
    foot.append(el('span', { class: 'count' }, el('b', {}, r.name), ` · ${r.pos} · ${r.ovr} · ${r.yrs} yr${r.yrs === 1 ? '' : 's'} · $${r.hit.toFixed(1)}m`),
      el('button', { class: 'btn', style: 'margin-left:auto', onclick: () => { location.hash = '#club/player/' + r.pid; } }, 'Card'),
      el('button', { class: 'btn go', onclick: () => { const res = pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind='extension')`); notify(res); if (res.ok) location.hash = '#personnel/extensions'; } }, 'Extend'),
      el('button', { class: 'btn', onclick: () => { tradeState = { other: tradeState.other, a: [r.pid], b: [], keep: true }; location.hash = '#personnel/trades'; } }, 'Trade Block'),
      el('button', { class: 'btn warn', onclick: () => { if (!confirm(`Cut ${r.name}? Penalty $${r.penalty.toFixed(1)}m against this year's cap.`)) return; const res = pyJSON(`SESSION.club_act('cut', pid=${JSON.stringify(r.pid)})`); notify(res.ok ? { ok: true, line: `${res.name} released. Penalty $${res.penalty}m.` } : res); rosterSel = null; renderRoster(pyJSON('SESSION.club_roster()')); } }, `Cut · Penalty $${r.penalty.toFixed(1)}m`));
  };
  sheet.append(tbl, foot); drawRows(); drawFoot();
  page.append(sheet);
}

const TRAIT_META = {
  'grinder': { k: 'work', tip: 'Outworks his rating. Gains XP faster and keeps his condition.' }, 'hard worker': { k: 'work', tip: 'Puts in the time. A little more development than most.' },
  'coasts': { k: 'work-', tip: 'Does the minimum. Develops slower than his talent says he should.' }, 'needs pushing': { k: 'work-', tip: 'Has to be driven. The slowest to improve, and condition slips.' },
  'wants to be paid': { k: 'money', tip: 'Money first. He will hold out for market value and will not take a discount.' }, 'money matters': { k: 'money', tip: 'Wants a fair number. Harder to extend cheaply.' },
  'not about the money': { k: 'money-', tip: 'Will leave money on the table for the right situation.' }, 'plays for the love of it': { k: 'money-', tip: 'Money is an afterthought. The easiest man on the roster to extend.' },
  'loyal': { k: 'loyal', tip: 'Wants to finish here. Likely to take less to stay.' }, 'settled': { k: 'loyal', tip: 'Comfortable where he is. Not looking to leave.' },
  'keeps his options open': { k: 'loyal-', tip: 'Will test the market when his deal is up.' }, 'follows the money': { k: 'loyal-', tip: 'No attachment to the club. Goes to the highest bidder.' },
  'wants the ball': { k: 'amb', tip: 'Needs a big role. Unhappy as a backup or in a rotation.' }, 'ambitious': { k: 'amb', tip: 'Wants to start and to matter. Morale depends on his snaps.' },
  'team-first': { k: 'amb-', tip: 'Accepts his role. Morale holds even when the snaps drop.' }, 'happy in a role': { k: 'amb-', tip: 'Content wherever you put him. The easiest man to keep happy.' },
  'even-keeled': { k: 'even', tip: 'Nothing about him stands out either way.' },
};
let cardTab = 'Overview';
function renderCard(v) {
  if (v.cls_year !== undefined && v.confidence !== undefined) return renderProspectCard(v);
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Club'; secondRow([['Roster', '#club'], ['Depth Chart', '#club/depth'], ['Practice Squad', '#club/ps']], '');
  if (v.error) { page.append(el('section', { class: 'sheet c12' }, el('div', { class: 'empty' }, v.error))); return; }
  const s = el('section', { class: 'sheet c12' });
  const col = v.team ? v.team.color : 'var(--rule-hi)';
  s.append(el('div', { class: 'head' },
    el('div', { class: 'jersey', style: `background:${col}` }, v.no || v.pos),
    el('div', {}, el('div', { class: 'hname' }, v.name.toUpperCase()),
      el('div', { class: 'hline' }, el('b', {}, v.pos), ` · ${v.age}${v.size ? ' · ' + v.size : ''}${v.college ? ' · ' + v.college : ''}${v.season_no ? ` · ${v.season_no}${ord(v.season_no)} season` : ''} · ${v.draft}` + (v.team ? ` · ${v.team.name}` : ' · Free agent')),
      el('div', { class: 'hfacts' }, el('div', {}, el('span', {}, 'Contract'), el('b', {}, `$${v.contract.per_year.toFixed(1)}m`, el('small', {}, `per year · ${v.contract.years} yrs`))), el('div', {}, el('span', {}, `Cap Hit ${v.rail.year}`), el('b', {}, `$${v.contract.hit.toFixed(1)}m`)), el('div', {}, el('span', {}, 'Penalty'), el('b', {}, `$${v.contract.penalty.toFixed(1)}m`)), el('div', {}, el('span', {}, 'Trade Interest'), el('b', { style: 'color:var(--ink-2)' }, v.interest)), el('div', {}, el('span', {}, 'Morale'), el('b', { style: 'color:var(--ink-2)' }, v.morale)))),
    el('div', { class: 'ovrbig' }, el('b', {}, v.ovr), el('span', {}, `Overall · Scheme Fit ${v.fit >= 0 ? '+' : ''}${v.fit.toFixed(1)}`), el('div', { class: 'pot' }, `Ceiling ${v.ceiling} · ${v.dev}`))));
  // tabs and actions
  const tabs = el('div', { class: 'ctabs' });
  for (const t of ['Overview', 'Contract', 'Stats', 'Career', 'History'].concat(v.actions && v.actions.mine ? ['Development'] : [])) tabs.append(el('button', { 'aria-pressed': String(cardTab === t), onclick: () => { cardTab = t; renderCard(v); } }, t));
  const acts = el('div', { class: 'acts' });
  if (v.actions.mine) {
    acts.append(el('button', { class: 'btn' + (v.ext_eligible ? ' go' : ''), disabled: v.ext_eligible ? null : '', 'data-tip': v.ext_eligible ? `Ask his agent (~$${v.ext_ask ?? '?'}m) and open the talks` : 'Not eligible yet', onclick: () => { const r = pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(v.pid)}, kind='extension')`); notify(r); if (r.ok) location.hash = '#personnel/extensions'; } }, 'Extend'));
    acts.append(el('button', { class: 'btn', 'data-tip': 'Open the restructure preview on his contract', onclick: () => { restructureFor = v.pid; location.hash = '#frontoffice/cap'; } }, 'Restructure'));
    const alts = v.grades.filter(g => !g.mine && g.pos !== 'Nickel');
    if (alts.length) { const sel = el('select', { class: 'btn' }); sel.append(el('option', { value: '' }, 'Position Change…')); alts.forEach(g => sel.append(el('option', { value: g.pos }, `${g.pos} · ${g.ovr} Ovr`))); sel.onchange = () => { if (!sel.value) return; const r = pyJSON(`SESSION.club_act('position_change', pid=${JSON.stringify(v.pid)}, new_pos=${JSON.stringify(sel.value)})`); notify(r.ok ? { ok: true, line: `${r.name} moves to ${r.to}: ${r.penalty} points for ${r.games} games.` } : r); if (r.ok) renderCard(pyJSON(`SESSION.club_card(${JSON.stringify(v.pid)})`)); }; acts.append(sel); }
    acts.append(el('button', { class: 'btn', 'data-tip': 'Put him in a trade package and shop him', onclick: () => { tradeState = { other: tradeState.other, a: [v.pid], b: [], keep: true }; location.hash = '#personnel/trades'; } }, 'Trade Block'));
    acts.append(el('button', { class: 'btn warn', onclick: () => { if (!confirm(`Cut ${v.name}? Penalty $${v.contract.penalty.toFixed(1)}m against this year's cap.`)) return; const r = pyJSON(`SESSION.club_act('cut', pid=${JSON.stringify(v.pid)})`); notify(r.ok ? { ok: true, line: `${r.name} released. Penalty $${r.penalty}m.` } : r); location.hash = '#club'; } }, `Cut · Penalty $${v.contract.penalty.toFixed(1)}m`));
    acts.append(el('button', { class: 'btn', disabled: v.actions.ps_ok ? null : '', 'data-tip': v.actions.ps_ok ? (v.actions.vested ? 'A vested veteran: he goes straight to the practice squad' : 'He must clear waivers first; if no club claims him at the Advance he joins your practice squad') : 'The squad has no room for him under its rules', onclick: () => { if (!confirm(`Waive ${v.name} to the practice squad? Penalty $${v.contract.penalty.toFixed(1)}m.${v.actions.vested ? '' : ' Another club may claim him first.'}`)) return; const r = pyJSON(`SESSION.club_act('to_squad', pid=${JSON.stringify(v.pid)})`); notify(r); if (r.ok) location.hash = '#club'; } }, 'Waive to Practice Squad'));
    if (v.actions.hurt && !v.actions.on_ir) acts.append(el('button', { class: 'btn', 'data-tip': 'Injured reserve: off the 53 now, salary counts in full; back after four weeks if a return is left', onclick: () => { const se = confirm(`Place ${v.name} on IR.\n\nOK = designated to return (four weeks minimum, uses one of the club's returns).\nCancel = ask again for season-ending.`); let res; if (se) res = pyJSON(`SESSION.club_act('ir', pid=${JSON.stringify(v.pid)})`); else if (confirm(`Place ${v.name} on IR for the season? He will not return this year.`)) res = pyJSON(`SESSION.club_act('ir', pid=${JSON.stringify(v.pid)}, season_ending=True)`); else return; notify(res); if (res.ok) location.hash = '#club/ir'; } }, 'Place on IR'));
    if (v.actions.on_ir) acts.append(el('button', { class: 'btn', 'data-tip': 'Back to the 53', onclick: () => { const res = pyJSON(`SESSION.club_act('ir_activate', pid=${JSON.stringify(v.pid)})`); notify(res); if (res.ok) location.hash = '#club'; } }, 'Activate from IR'));
  }
  acts.append(el('button', { class: 'btn quiet', onclick: () => history.back() }, 'Back'));
  tabs.append(acts); s.append(tabs);
  const h5 = (t, sub) => el('div', { class: 'h5' }, t, sub ? el('span', {}, sub) : '');
  if (cardTab === 'Overview') {
    const left = el('div', {});
    left.append(h5('Positions'));
    const pm = el('div', { class: 'posmap', style: `grid-template-columns:repeat(${Math.min(5, v.grades.length)},1fr)` }); v.grades.forEach(g => pm.append(el('div', { class: g.mine ? 'nat' : 'fam' }, g.pos))); left.append(pm);
    const gr = el('div', { class: 'grades' }); v.grades.forEach(g => gr.append(el('div', {}, el('span', {}, g.pos), el('div', { class: 'bar' }, el('i', { style: `width:${g.ovr}%` })), el('span', { class: 'g' }, `${g.ovr} Ovr`)))); left.append(gr);
    left.append(h5('Status'));
    left.append(el('div', { class: 'kv' }, el('span', {}, 'Role'), el('span', {}, v.role || '—'), el('span', {}, 'Snaps'), el('span', {}, v.snaps || 'None yet this season'), el('span', {}, 'Health'), el('span', {}, (v.out ? `Out until week ${v.out}` : 'Healthy') + (v.missed ? ` · ${v.missed} game${v.missed === 1 ? '' : 's'} missed` : ' · no games missed')), el('span', {}, 'Condition'), el('span', {}, `${v.cond}%`), el('span', {}, 'Position Change'), el('span', {}, v.pending)));
    const mid = el('div', {});
    mid.append(h5('Attributes'));
    const attrs = el('div', { class: 'attrs' });
    for (const c of v.cols) {
      const box = el('div', {}, el('div', { class: 'h5', style: 'margin-bottom:4px' }, c.title));
      const rowsOf = rows => { for (const r of rows) { const row = el('div', { class: 'arow ' + r.tier }, el('span', {}, r.label)); row.append(r.shift ? el('em', { class: 'fitd ' + (r.shift > 0 ? 'p' : 'm'), 'data-tip': r.shift > 0 ? `${r.scheme} counts this more` : `${r.scheme} counts this less` }, r.scheme || '') : el('em', {})); row.append(el('b', {}, r.v)); box.append(row); } };
      rowsOf(c.rows);
      if (c.extra && c.extra.rows && c.extra.rows.length) { box.append(el('div', { class: 'h5', style: 'margin:12px 0 4px' }, c.extra.title)); rowsOf(c.extra.rows); }
      if (c.title === 'Mental' && v.personality) { box.append(el('div', { class: 'h5', style: 'margin:12px 0 4px' }, 'Traits')); const tr = el('div', { class: 'traits' }); v.personality.split(',').map(x => x.trim()).filter(Boolean).forEach(w => { const m = TRAIT_META[w] || { k: 'even', tip: 'Nothing about him stands out.' }; tr.append(el('span', { class: 'trait ' + m.k, 'data-tip': m.tip }, w.replace(/\b\w/g, ch => ch.toUpperCase()))); }); box.append(tr); }
      attrs.append(box);
    }
    mid.append(attrs);
    const right = el('div', {});
    right.append(h5('Contract', v.contract_caption));
    if (v.contract.by_year.length) { const ct = el('table', { class: 'contract' }); ct.append(el('tr', {}, el('th', {}, 'Year'), el('th', {}, 'Base'), el('th', {}, 'Bonus'), el('th', {}, 'Cap Hit'), el('th', {}, 'Penalty'))); v.contract.by_year.forEach((y, i) => ct.append(el('tr', { class: i === 0 ? 'now' : '' }, el('td', {}, y.year), el('td', {}, y.base != null ? `$${y.base.toFixed(1)}m` : '—'), el('td', {}, y.bonus != null ? `$${y.bonus.toFixed(1)}m` : '—'), el('td', {}, `$${y.hit.toFixed(1)}m`), el('td', {}, y.penalty != null ? `$${y.penalty.toFixed(1)}m` : '—')))); right.append(ct); }
    right.append(el('div', { class: 'kv', style: 'margin-top:8px' }, el('span', {}, 'Market'), el('span', {}, v.market_apy != null ? `About $${v.market_apy}m per year` : '—'), el('span', {}, 'Extension'), el('span', {}, v.ext_eligible ? `Eligible${v.ext_ask != null ? ` · agent's ask ~$${v.ext_ask}m` : ''}` : 'Not yet eligible')));
    right.append(h5('Trade Value', "the scout's read"), el('div', { class: 'kv' }, el('span', {}, 'Market'), el('span', {}, v.market), el('span', {}, 'Interest'), el('span', {}, v.interest_line)));
    s.append(el('div', { class: 'body' }, left, mid, right));
    const tiles = el('div', { class: 'tiles' },
      el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Morale'), el('div', { class: 'word' }, v.morale), el('div', { class: 'sub' }, v.morale_line)),
      el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Condition'), el('div', { class: 'word' }, `${v.cond}%`), el('div', { class: 'sub' }, v.out ? `Out until week ${v.out}` : v.cond >= 85 ? 'Fresh' : v.cond >= 70 ? 'Carrying a load' : 'Worn down'), el('div', { class: 'cond', style: 'width:100%;height:8px;margin-top:8px' }, el('i', { class: v.cond < 60 ? 'low' : v.cond < 80 ? 'mid' : '', style: `width:${v.cond}%` }))),
      el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Development'), el('div', { class: 'word' }, v.dev), el('div', { class: 'sub' }, v.dev_line)),
      el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Ceiling'), el('div', { class: 'word' }, v.ceiling), el('div', { class: 'sub' }, "your scouts' range for where he tops out")));
    s.append(tiles);
  } else if (cardTab === 'Contract') {
    const box = el('div', { class: 'pad' }, h5('Contract', v.contract_caption));
    if (v.contract.by_year.length) { const ct = el('table', { class: 'contract', style: 'max-width:620px' }); ct.append(el('tr', {}, el('th', {}, 'Year'), el('th', {}, 'Base'), el('th', {}, 'Bonus'), el('th', {}, 'Cap Hit'), el('th', {}, 'Penalty'))); v.contract.by_year.forEach((y, i) => ct.append(el('tr', { class: i === 0 ? 'now' : '' }, el('td', {}, y.year), el('td', {}, y.base != null ? `$${y.base.toFixed(1)}m` : '—'), el('td', {}, y.bonus != null ? `$${y.bonus.toFixed(1)}m` : '—'), el('td', {}, `$${y.hit.toFixed(1)}m`), el('td', {}, y.penalty != null ? `$${y.penalty.toFixed(1)}m` : '—')))); box.append(ct); }
    else box.append(el('div', { class: 'empty' }, 'No contract on file.'));
    box.append(el('div', { class: 'kv', style: 'margin-top:12px;max-width:620px' }, el('span', {}, 'Market'), el('span', {}, v.market_apy != null ? `About $${v.market_apy}m per year` : '—'), el('span', {}, 'Extension'), el('span', {}, v.ext_eligible ? `Eligible${v.ext_ask != null ? ` · agent's ask ~$${v.ext_ask}m` : ''}` : 'Not yet eligible'), el('span', {}, 'Penalty if cut now'), el('span', {}, `$${v.contract.penalty.toFixed(1)}m`)));
    s.append(box);
  } else if (cardTab === 'Stats' || cardTab === 'Career') {
    const box = el('div', { class: 'pad' }, h5(cardTab === 'Stats' ? 'Season Stats' : 'Career', cardTab === 'Stats' ? `${v.rail.year} · ${v.games} game${v.games === 1 ? '' : 's'}` : `${v.seasons.length} season${v.seasons.length === 1 ? '' : 's'} on record`));
    const rows = cardTab === 'Stats' ? v.seasons.filter(sn => sn.year === v.rail.year) : v.seasons.slice().reverse();
    if (rows.length) { const t = el('table', { class: 'stab', style: 'max-width:900px' }); t.append(el('tr', {}, el('th', {}, 'Season'), el('th', {}, 'Club'), el('th', {}, 'G'), ...v.season.cols.map(c => el('th', {}, c)))); for (const sn of rows) t.append(el('tr', {}, el('td', {}, sn.year), el('td', {}, sn.team), el('td', {}, sn.games), ...sn.row.map(x => el('td', {}, String(x))))); box.append(t); }
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

// the development sheet: his bank, his ceiling, every attribute with the price of the next point
function developmentPanel(pid, reload) {
  const d = pyJSON(`SESSION.development(${JSON.stringify(pid)})`);
  const box = el('div', { class: 'pad' });
  if (d.error) { box.append(el('div', { class: 'empty' }, d.error)); return box; }
  const act = (name, extra) => { const r = pyJSON(`SESSION.club_act(${JSON.stringify(name)}, pid=${JSON.stringify(pid)}${extra ? ', ' + extra : ''})`); notify(r); reload(); };
  box.append(el('div', { class: 'tiles', style: 'grid-template-columns:repeat(4,1fr);margin-bottom:12px' },
    el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'XP Banked'), el('div', { class: 'word' }, d.bank.toLocaleString()), el('div', { class: 'sub' }, `earning ${d.dev} · ${d.bought} points bought in his career`)),
    el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Ceiling'), el('div', { class: 'word' }, d.ceiling != null ? d.ceiling : '—'), el('div', { class: 'sub' }, d.room != null ? `${d.room} above his ${d.ovr}` : 'uncapped')),
    el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Raise the Ceiling'), el('div', { class: 'word', style: 'font-size:18px' }, d.unlock_cost != null ? `${d.unlock_cost.toLocaleString()} XP` : '—'), el('div', { class: 'sub' }, el('button', { class: 'btn' + (d.unlock_ok ? ' go' : ''), disabled: d.unlock_ok ? null : '', style: 'padding:3px 10px;font-size:13px;margin-top:4px', 'data-tip': 'Raises his ceiling one point', onclick: () => act('unlock_ceiling') }, 'Unlock +1'))),
    el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Auto-Spend'), el('div', { class: 'word', style: 'font-size:18px' }, d.auto ? 'On' : 'Off'), el('div', { class: 'sub' }, el('button', { class: 'btn', style: 'padding:3px 10px;font-size:13px;margin-top:4px', 'data-tip': 'The assistants spend his XP weekly', onclick: () => act('auto_xp', `on=${d.auto ? 'False' : 'True'}`) }, d.auto ? 'Turn Off' : 'Turn On'), ' ', el('button', { class: 'btn quiet', style: 'padding:3px 10px;font-size:13px;margin-top:4px', 'data-tip': 'Spend his bank now, once', onclick: () => act('spend_by_read') }, 'Spend by Read')))));
  const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Attribute'), el('th', { class: 'n' }, 'Now'), el('th', { class: 'n', 'data-tip': 'Share of his overall' }, 'Weight'), el('th', { class: 'n', 'data-tip': 'Overall the next point adds' }, '+Ovr'), el('th', { class: 'n', 'data-tip': 'XP for the next point; rises with every point bought and with age' }, 'Next Point'), el('th', {}, '')));
  for (const r of d.rows) t.append(el('tr', { style: r.blocked ? 'opacity:.55' : '' }, el('td', { style: 'text-align:left' }, r.label, r.phys ? el('small', { class: 'muted' }, ' · physical') : '', r.bought ? el('small', { class: 'muted' }, ` · +${r.bought} bought`) : ''), el('td', { class: 'n' }, r.v), el('td', { class: 'n' }, r.weight ? r.weight.toFixed(2) : '—'), el('td', { class: 'n' }, r.gain ? '+' + r.gain.toFixed(2) : '—'), el('td', { class: 'n', style: r.afford && !r.blocked ? '' : 'color:var(--ink-3)' }, r.cost.toLocaleString()),
    el('td', {}, el('button', { class: 'btn' + (r.afford && !r.blocked ? ' go' : ''), disabled: (r.afford && !r.blocked) ? null : '', style: 'padding:3px 10px;font-size:13px', 'data-tip': r.blocked || (r.afford ? 'Buy one point' : 'Not enough XP'), onclick: () => act('buy_point', `attr=${JSON.stringify(r.key)}`) }, 'Buy +1'))));
  box.append(t);
  return box;
}

// the roster's development at a glance
function renderProgression(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Club'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'club'));
  secondRow([['Roster', '#club'], ['Depth Chart', '#club/depth'], ['Practice Squad', '#club/ps'], ['Injured Reserve', '#club/ir'], ['Progression', '#club/progression']], '#club/progression');
  const reload = () => renderProgression(pyJSON('SESSION.progression()'));
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Progression', el('small', {}, `${v.bank_total.toLocaleString()} XP banked across the roster · ${v.idle} players could buy a point now and are not on auto`)));
  s.append(el('div', { class: 'tools' }, el('button', { class: 'btn' + (v.auto_all ? ' go' : ''), 'data-tip': 'Every player, spent weekly by the assistants', onclick: () => { notify(pyJSON(`SESSION.club_act('auto_xp', on=${v.auto_all ? 'False' : 'True'})`)); reload(); } }, v.auto_all ? 'Auto-Spend: On for All' : 'Turn Auto-Spend On for All'),
    el('button', { class: 'btn', 'data-tip': 'Spend every bank now, once', onclick: () => { notify(pyJSON(`SESSION.club_act('spend_by_read')`)); reload(); } }, 'Spend All by Read'),
    el('span', { class: 'count', style: 'margin-left:auto' }, 'Open a player for his Development tab')));
  const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', { class: 'n' }, 'Ceiling'), el('th', { class: 'n', 'data-tip': 'Overall left under his ceiling' }, 'Room'), el('th', { class: 'n' }, 'XP Banked'), el('th', { class: 'n', 'data-tip': 'The cheapest next point' }, 'Next Point'), el('th', { class: 'n' }, 'Bought This Year'), el('th', {}, 'Auto'), el('th', {}, '')));
  for (const r of v.rows) t.append(el('tr', { style: r.can_buy && !r.auto ? 'background:var(--sheet-2)' : '' }, el('td', {}, el('button', { class: 'who', onclick: () => { cardTab = 'Development'; location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.no ?? r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `earning ${r.dev} · ${r.career} bought in his career`)))), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, r.ceiling ?? '—'), el('td', { class: 'n' }, r.room != null ? r.room : '—'), el('td', { class: 'n' }, r.bank.toLocaleString()), el('td', { class: 'n' }, r.cheapest ? r.cheapest.toLocaleString() : '—'), el('td', { class: 'n' }, r.bought),
    el('td', {}, el('button', { class: 'btn' + (r.auto ? ' go' : ' quiet'), style: 'padding:3px 8px;font-size:13px', onclick: () => { pyJSON(`SESSION.club_act('auto_xp', pid=${JSON.stringify(r.pid)}, on=${r.auto ? 'False' : 'True'})`); reload(); } }, r.auto ? 'On' : 'Off')),
    el('td', {}, el('button', { class: 'btn', style: 'padding:3px 8px;font-size:13px', disabled: r.can_buy ? null : '', 'data-tip': 'Spend his bank now by the read', onclick: () => { notify(pyJSON(`SESSION.club_act('spend_by_read', pid=${JSON.stringify(r.pid)})`)); reload(); } }, 'Spend'))));
  s.append(t); page.append(s);
}

function renderProspectCard(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Draft'; drSecond('board');
  if (v.error) { page.append(el('section', { class: 'sheet c12' }, el('div', { class: 'empty' }, v.error))); return; }
  const reload = () => renderProspectCard(pyJSON(`SESSION.club_card(${JSON.stringify(v.pid)})`));
  const s = el('section', { class: 'sheet c12' });
  s.append(el('div', { class: 'head' },
    el('div', { class: 'jersey', style: 'background:var(--sheet-3);color:var(--ink)' }, v.pos),
    el('div', {}, el('div', { class: 'hname' }, v.name.toUpperCase()),
      el('div', { class: 'hline' }, el('b', {}, v.pos), ` · ${v.cls_year} · ${v.age}${v.size ? ' · ' + v.size : ''} · ${v.college}${v.conference ? ' · ' + v.conference : ''}${v.small ? ' · Small School' : ''}${v.taken ? ' · Drafted' : ''}`),
      el('div', { class: 'hfacts' }, el('div', { 'data-tip': "The league's grade, same scale as yours" }, el('span', {}, 'Consensus'), el('b', {}, v.cons != null ? `${v.cons}${v.cons_rank ? ' · #' + v.cons_rank : ''}` : '—')), el('div', { 'data-tip': "Yours minus the league's. Positive means the league undervalues him" }, el('span', {}, 'Gap'), el('b', { style: v.gap > 0 ? 'color:var(--ok)' : v.gap < 0 ? 'color:var(--danger)' : '' }, v.gap != null ? (v.gap > 0 ? '+' : '') + v.gap : '—')), el('div', { 'data-tip': 'Where the league expects him to go' }, el('span', {}, 'Projected'), el('b', {}, v.proj_range)), el('div', {}, el('span', {}, 'Your Board'), el('b', {}, v.dnd ? 'Do Not Draft' : v.on_board ? `#${v.on_board}` : 'Not placed')), el('div', {}, el('span', {}, 'Read'), el('b', { style: 'color:var(--ink-2)' }, `${v.confidence} · ${v.reads} look${v.reads === 1 ? '' : 's'}`)))),
    el('div', { class: 'ovrbig' }, el('b', { 'data-tip': "Your scouts' read. Carries error; a visit tightens it" }, v.mine), el('span', {}, 'Estimated Overall · your scouts'), el('div', { class: 'pot', 'data-tip': 'Where he can grow to. Wide means your scouts are unsure' }, `Ceiling ${v.ceiling}${v.my_round ? ' · Your Grade ' + v.my_round : ''}`))));
  const acts = el('div', { class: 'ctabs' }, el('span', { style: 'font-family:var(--display);font-weight:700;color:var(--ink-3);padding:8px 0' }, 'Prospect Card'));
  const a = el('div', { class: 'acts' });
  if (!v.taken) {
    a.append(v.on_board ? el('button', { class: 'btn quiet', onclick: () => { pyJSON(`SESSION.draft_act('board', remove=${JSON.stringify(v.pid)})`); reload(); } }, 'Take Off Your Board') : el('button', { class: 'btn go', onclick: () => { pyJSON(`SESSION.draft_act('board', add=${JSON.stringify(v.pid)})`); reload(); } }, 'Add to Your Board'));
    if (!v.spring_done) a.append(el('button', { class: 'btn' + (v.visited ? ' go' : ''), 'data-tip': v.visited ? 'Cancel the visit' : 'Bring him in for the second look', onclick: () => { const r = pyJSON(`SESSION.draft_act('visit', pid=${JSON.stringify(v.pid)})`); if (!r.ok) notify(r); reload(); } }, v.visited ? 'Visiting' : 'Visit'));
    a.append(el('button', { class: 'btn quiet', 'data-tip': 'Keep him off your board on draft day', onclick: () => { pyJSON(`SESSION.draft_act('board', remove=${JSON.stringify(v.pid)})`); const cur = pyJSON(`SESSION.draft_view('board')`).user_board.dnd.map(x => x.pid); pyJSON(`SESSION.draft_act('board', dnd=${JSON.stringify(cur.concat([v.pid]))})`); reload(); } }, 'Do Not Draft'));
  }
  a.append(el('button', { class: 'btn quiet', onclick: () => history.back() }, 'Back'));
  acts.append(a); s.append(acts);
  const h5 = (t, sub) => el('div', { class: 'h5' }, t, sub ? el('span', {}, sub) : '');
  const left = el('div', {});
  left.append(h5('Combine', v.combine.every(c => c.v === '—') ? 'comes in the Spring' : 'from the Spring'));
  left.append(el('div', { class: 'kv' }, ...v.combine.flatMap(c => [el('span', {}, c.label), el('span', {}, c.v)])));
  left.append(h5('Flags'), el('div', { style: 'padding:4px 0 8px' }, ...(v.words.length ? v.words.map(wordTag) : [el('span', { class: 'muted', style: 'font-size:14.5px' }, 'None')])));
  left.append(h5('Medical'), el('div', { style: 'font-size:15px;color:var(--ink-2);padding-bottom:8px' }, v.medical));
  if (v.personality) left.append(h5('Character', 'from your visit'), el('div', { style: 'font-size:15px;color:var(--ink-2)' }, v.personality));
  const mid = el('div', {});
  mid.append(h5('Attributes', "your scouts' read, not the truth"));
  const attrs = el('div', { class: 'attrs' });
  for (const c of v.cols) {
    const box = el('div', {}, el('div', { class: 'h5', style: 'margin-bottom:4px' }, c.title));
    const rowsOf = rows => { for (const r of rows) box.append(el('div', { class: 'arow ' + r.tier }, el('span', {}, r.label), el('em', {}), el('b', {}, r.v))); };
    rowsOf(c.rows); if (c.extra && c.extra.rows && c.extra.rows.length) { box.append(el('div', { class: 'h5', style: 'margin:12px 0 4px' }, c.extra.title)); rowsOf(c.extra.rows); }
    attrs.append(box);
  }
  mid.append(attrs);
  const right = el('div', {});
  right.append(h5('The Scouts', "the room's read"), el('div', { class: 'read' }, el('b', {}, 'Assistants: '), v.read));
  right.append(h5('Where He Goes', 'consensus against your board'), el('div', { class: 'kv' }, el('span', {}, 'Consensus'), el('span', {}, v.cons_rank ? `#${v.cons_rank} · picks ${v.proj_range}` : '—'), el('span', {}, 'Your Read'), el('span', {}, v.my_rank ? `#${v.my_rank}${v.my_round ? ' · ' + v.my_round + ' grade' : ''}` : '—'), el('span', {}, 'Ceiling'), el('span', {}, v.ceiling)));
  s.append(el('div', { class: 'body' }, left, mid, right));
  page.append(s);
}

let depthPkg = 'Nickel', depthSide = 'offense';
function renderDepth(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Club'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'club'));
  const mine = v.mine !== false; const abbr = v.club_abbr || v.rail.club.abbr;
  $('#crumb').textContent = mine ? 'Club' : 'League'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === (mine ? 'club' : 'league')));
  secondRow(clubNav(abbr, mine, null), mine ? '#club/depth' : `#league/team/${abbr}/depth`);
  const reload = () => renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(v.package)}${mine ? '' : ', ' + JSON.stringify(abbr)})`));
  const s = el('section', { class: 'sheet c12' });
  // the side tabs, then the package
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' });
  for (const [k, l] of [['offense', 'Offense'], ['defense', 'Defense'], ['specialists', 'Specialists']]) tabs.append(el('button', { 'aria-pressed': String(depthSide === k), onclick: () => { depthSide = k; renderDepth(v); } }, l));
  tabs.append(el('span', { style: 'margin-left:auto' }), clubSelect(abbr, a => { const m = pyJSON('SESSION.club_list()').find(c => c.abbr === a); location.hash = m && m.mine ? '#club/depth' : `#league/team/${a}/depth`; }));
  s.append(tabs);
  if (depthSide === 'defense') {
    const pk = el('div', { class: 'pkg' }, el('span', {}, 'Package'));
    for (const p of v.packages) pk.append(el('button', { 'aria-pressed': String(p === v.package), onclick: () => { depthPkg = p; renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(p)}${mine ? '' : ', ' + JSON.stringify(abbr)})`)); } }, p));
    pk.append(el('span', { class: 'snaps' }, 'Drag within a column · double-click opens the player'));
    s.append(pk);
  }
  // one column a position, rows aligned across columns, starters lit
  const cols = v.sides[depthSide];
  const chart = el('div', { class: 'chart3', style: `grid-template-columns:repeat(${cols.length},minmax(0,1fr))` });
  for (const c of cols) {
    const men = c.slots; const pinned = v.pins[c.pos] && v.pins[c.pos].length;
    const col = el('div', { class: 'dcol' + (pinned ? ' yours' : '') }, el('div', { class: 'pos' }, c.title));
    const move = (i, dir) => { const order = men.map(m => m.pid); [order[i + dir], order[i]] = [order[i], order[i + dir]]; pyJSON(`SESSION.club_act('set_depth', pos=${JSON.stringify(c.pos)}, pids=${JSON.stringify(order)})`); reload(); };
    men.forEach((x, i) => {
      const fit = x.fit || 0;
      const decide = x.pending && mine ? el('span', { style: 'display:inline-flex;gap:3px;margin-top:4px' }, el('button', { class: 'btn go', style: 'padding:1px 8px;font-size:11px', onclick: e => { e.stopPropagation(); notify(pyJSON(`SESSION.club_act('hurt_decision', pid=${JSON.stringify(x.pid)}, play=True)`)); reload(); } }, 'Play'), el('button', { class: 'btn', style: 'padding:1px 8px;font-size:11px', onclick: e => { e.stopPropagation(); notify(pyJSON(`SESSION.club_act('hurt_decision', pid=${JSON.stringify(x.pid)}, play=False)`)); reload(); } }, 'Sit')) : null;
      const fitEl = x.flag_word ? el('span', { style: 'display:inline-flex;flex-direction:column;align-items:flex-start;gap:0' }, el('span', { class: 'tag ' + (x.flag === 'out' ? 'out' : 'q') }, x.flag_word), decide || '') : x.elevated ? el('span', { class: 'tag q', 'data-tip': 'Elevated from the practice squad for this game' }, 'Elevated') : x.playing_hurt ? el('span', { class: 'tag q' }, `Playing · ${x.playing_hurt}`) : el('span', { class: 'fit' }, 'Fit ', el('b', { class: fit > 0.05 ? 'up' : fit < -0.05 ? 'dn' : '' }, (fit > 0.05 ? '+' : fit < -0.05 ? '−' : '\u00a0') + Math.abs(fit).toFixed(1)));
      const plate = el('div', { class: 'plate3' + (x.start ? ' start' : '') + (x.flag === 'out' ? ' out' : ''), draggable: mine ? 'true' : 'false', title: x.name },
        el('div', { class: 'row1' }, el('span', { class: 'no' }, x.no || ''), el('span', { class: 'nm' }, surname(x.name) || x.name)),
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
    chart.append(col);
  }
  s.append(chart);
  if (mine) s.append(el('div', { class: 'foot' }, el('button', { class: 'btn', 'data-tip': 'Best overall first at every spot', onclick: () => { pyJSON(`SESSION.club_act('reset_depth')`); reload(); } }, 'Auto-Fill by Rating'), el('button', { class: 'btn', 'data-tip': "Best at the spot in your scheme first, the way the coordinators would set it", onclick: () => { notify(pyJSON(`SESSION.club_act('fill_by_fit')`)); reload(); } }, 'Auto-Fill by Fit'),
    v.assistant && depthSide === 'defense' ? el('span', { class: 'read', style: 'margin:0 0 0 10px;padding:6px 10px;flex:1' }, el('b', {}, 'Assistants: '), v.assistant) : el('span', { class: 'count', style: 'margin-left:auto' }, 'Highlighted players are starters')));
  else s.append(el('div', { class: 'foot' }, el('span', { class: 'count' }, 'Highlighted players are starters')));
  page.append(s);
}

// ---------------------------------------------------------------- Personnel
const PERS = { trades: 'Trades', fa: 'Free Agency', wire: 'Waivers', extensions: 'Extensions' };
let tradeState = { other: null, a: [], b: [] };
function persSecond(cur) { secondRow(Object.entries(PERS).map(([k, l]) => [l, '#personnel/' + k]), '#personnel/' + cur); $('#crumb').textContent = 'Personnel'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'personnel')); }
function persPage() { const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)'; return page; }
function crest(c, size) { return el('div', { class: 'cr', style: `background:${c.color}${size ? `;width:${size}px;height:${size}px` : ''}` }, c.abbr); }
function notify(r) { busy(r.why || r.line || (r.ok ? 'Done.' : 'That did not work.')); setTimeout(() => busy(null), 2600); }

function renderTrades(v) {
  renderRail(v.rail); const page = persPage(); persSecond('trades');
  tradeState.other = v.other.abbr;
  const s = el('section', { class: 'sheet c12' });
  s.append(el('h2', {}, 'Trades', el('small', {}, v.can_trade ? `Deadline after Week ${v.deadline_week}` : 'Closed until the season ends')));
  const strip = el('div', { class: 'clubs' });
  for (const c of v.clubs) strip.append(el('button', { class: 'cl', style: `background:${c.color}`, 'aria-pressed': String(c.abbr === v.other.abbr), 'data-tip': c.name, onclick: () => { tradeState = { other: c.abbr, a: [], b: [] }; renderTrades(pyJSON(`SESSION.personnel('trades', other=${JSON.stringify(c.abbr)})`)); } }, c.abbr));
  s.append(strip);
  const reload = () => renderTrades(pyJSON(`SESSION.personnel('trades', other=${JSON.stringify(tradeState.other)}, a_sends=${JSON.stringify(tradeState.a)}, b_sends=${JSON.stringify(tradeState.b)})`));
  const side = (own, list, picks, sel, title) => {
    const box = el('div', {});
    box.append(el('div', { class: 'side-h' }, crest(own.club), el('b', {}, title === 'You Send' ? 'You Send' : `${own.club.nick.charAt(0) + own.club.nick.slice(1).toLowerCase()} Sends`), el('span', {}, title === 'You Send' ? (v.package ? `Cap After: $${v.package.cap_after.me}m` : `Cap $${own.cap.toFixed(1)}m`) : `Their Cap: $${own.cap.toFixed(1)}m`)));
    const sn = el('div', { class: 'read', style: 'display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:8px' });
    sn.append(el('div', {}, el('div', { class: 'h5' }, own === v.me ? 'Your Surplus' : 'Their Surplus'), ...(own.surplus.length ? own.surplus.map(x => { const p = own.roster.find(r => r.pid === x.pid); return p ? el('div', { style: 'font-size:14.5px;cursor:pointer', onclick: () => { if (!sel.includes(p.pid)) { sel.push(p.pid); reload(); } } }, `${p.short} · ${p.pos} · ${p.ovr}`, el('small', { style: 'color:var(--ink-3)' }, ` ${x.why}`)) : ''; }) : [el('div', { style: 'font-size:14.5px;color:var(--ink-3)' }, 'Nothing spare.')])));
    sn.append(el('div', {}, el('div', { class: 'h5' }, own === v.me ? 'Your Needs' : 'Their Needs'), el('div', { style: 'font-size:14.5px' }, own.needs && own.needs.length ? own.needs.join(' · ') : 'None pressing')));
    box.append(sn);
    const pk = el('div', { class: 'pkgbox' });
    if (!sel.length) pk.append(el('div', { class: 'empty' }, 'Drag a plate or a pick here, or pick from the list below'));
    pk.addEventListener('dragover', e => { e.preventDefault(); pk.classList.add('over'); }); pk.addEventListener('dragleave', () => pk.classList.remove('over'));
    pk.addEventListener('drop', e => { e.preventDefault(); pk.classList.remove('over'); let d; try { d = JSON.parse(e.dataTransfer.getData('text/plain')); } catch (_) { return; } if (d && d.side === title && !sel.includes(d.id)) { sel.push(d.id); reload(); } });
    for (const id of sel) {
      const p = own.roster.find(r => r.pid === id), k = own.picks.find(r => r.id === id);
      if (p) pk.append(el('div', { class: 'plate' }, el('div', { class: 'no' }, p.no || p.pos), el('div', { class: 'nm' }, p.short, el('small', {}, `${p.pos} · ${p.yrs} Yr${p.yrs === 1 ? '' : 's'} · $${p.hit}m Hit · $${p.penalty}m Penalty`)), el('div', { class: 'ov' }, p.ovr), el('div', { class: 'x', onclick: () => { sel.splice(sel.indexOf(id), 1); reload(); } }, '✕')));
      else if (k) pk.append(el('div', { class: 'pkcard' }, el('div', { class: 'rd' }, `R${k.round}`), el('div', { class: 'nm' }, k.words, el('small', {}, `${k.own_words}${k.proj ? ' · ' + k.proj : ''}`)), el('div', { class: 'x', onclick: () => { sel.splice(sel.indexOf(id), 1); reload(); } }, '✕')));
    }
    box.append(pk);
    // pickers
    const tabs = el('div', { class: 'tabs', style: 'margin:10px 0 6px' }); const list1 = el('div', { class: 'rows' }); let mode = 'players';
    const drawList = () => {
      list1.innerHTML = '';
      const drag = (elm, id) => { elm.setAttribute('draggable', 'true'); elm.addEventListener('dragstart', e => e.dataTransfer.setData('text/plain', JSON.stringify({ id, side: title }))); };
      if (mode === 'players') for (const p of own.roster) { if (sel.includes(p.pid)) continue; const sur = own.surplus.find(x => x.pid === p.pid); const pl = el('div', { class: 'plate pickable', onclick: () => { sel.push(p.pid); reload(); } }, el('div', { class: 'no' }, p.no || p.pos), el('div', { class: 'nm' }, p.short, el('small', {}, `${p.pos} · ${p.yrs} Yr${p.yrs === 1 ? '' : 's'} · $${p.hit}m Hit` + (sur ? ` · ${sur.why}` : ''))), el('div', { class: 'ov' }, p.ovr)); drag(pl, p.pid); list1.append(pl); }
      else for (const k of own.picks) { if (sel.includes(k.id)) continue; const pc = el('div', { class: 'pkcard pickable', style: 'cursor:pointer', onclick: () => { sel.push(k.id); reload(); } }, el('div', { class: 'rd' }, `R${k.round}`), el('div', { class: 'nm' }, k.words, el('small', {}, `${k.own_words}${k.proj ? ' · ' + k.proj : ''}`)), el('div', {})); drag(pc, k.id); list1.append(pc); }
    };
    for (const [k, l] of [['players', 'Players'], ['picks', title === 'You Send' ? 'Your Picks' : 'Their Picks']]) tabs.append(el('button', { 'aria-pressed': String(mode === k), onclick: e => { mode = k; tabs.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); drawList(); } }, l));
    box.append(tabs, list1); drawList();
    box.append(el('div', { class: 'h5', style: 'margin-top:10px' }, title === 'You Send' ? 'Your Surplus' : 'Their Surplus', el('span', {}, title === 'You Send' ? 'Players the Assistants Would Move' : 'Depth they could spare')));
    for (const sx of own.surplus.slice(0, 4)) { const p = own.roster.find(r => r.pid === sx.pid); if (!p || sel.includes(p.pid)) continue; box.append(el('div', { class: 'plate pickable', style: 'margin-bottom:4px', onclick: () => { sel.push(p.pid); reload(); } }, el('div', { class: 'no' }, p.no || p.pos), el('div', { class: 'nm' }, p.short, el('small', {}, `${p.pos} · ${sx.why}`)), el('div', { class: 'ov' }, p.ovr))); }
    if (title !== 'You Send' && own.needs && own.needs.length) box.append(el('div', { class: 'h5', style: 'margin-top:10px' }, 'Their Needs'), el('div', { class: 'chips' }, ...own.needs.map(n => el('span', { class: 'chip' }, n))));
    return box;
  };
  const two = el('div', { class: 'two' }, side(v.me, v.me.roster, v.me.picks, tradeState.a, 'You Send'), side(v.them, v.them.roster, v.them.picks, tradeState.b, 'You Get'));
  // the read and the buttons sit above the pickers, so the deal is in view without scrolling
  const foot = el('div', { class: 'foot', style: 'flex-wrap:wrap;gap:10px;border-top:0;border-bottom:1px solid var(--rule)' });
  if (v.package) foot.append(el('div', { class: 'read ' + v.package.verdict, style: 'flex:1 1 100%' }, el('b', {}, `${v.them.club.abbr}: ${{ fair: 'Fair.', short: 'A touch short.', far: 'Well short.', overpay: 'An overpay.', blocked: 'Blocked.' }[v.package.verdict] || ''} `), v.package.read, el('br'), el('span', { style: 'color:var(--ink-3)' }, v.package.my_read + ` Roster after: ${v.package.roster_after.me}. Cap after: $${v.package.cap_after.me}m.`)));
  const can = v.can_trade && (tradeState.a.length || tradeState.b.length);
  foot.append(el('button', { class: 'btn go', disabled: can ? null : '', onclick: () => { const r = pyJSON(`SESSION.personnel_act('propose', other=${JSON.stringify(tradeState.other)}, a_sends=${JSON.stringify(tradeState.a)}, b_sends=${JSON.stringify(tradeState.b)})`); notify(r); if (r.done) { tradeState.a = []; tradeState.b = []; } reload(); } }, 'Propose'),
    el('button', { class: 'btn', disabled: v.can_trade && tradeState.b.length ? null : '', 'data-tip': 'Ask what it would take from your picks', onclick: () => { const r = pyJSON(`SESSION.personnel_act('ask', other=${JSON.stringify(tradeState.other)}, a_sends=${JSON.stringify(tradeState.a)}, b_sends=${JSON.stringify(tradeState.b)})`); notify(r); if (r.adds) for (const id of r.adds) if (!tradeState.a.includes(id)) tradeState.a.push(id); reload(); } }, 'Ask What They Want'),
    el('button', { class: 'btn', disabled: v.can_trade && tradeState.a.length === 1 && !tradeState.a[0].includes('-') ? null : '', 'data-tip': 'Shop the one player you send to every club', onclick: () => { const r = pyJSON(`SESSION.personnel_act('gather', pid=${JSON.stringify(tradeState.a[0])})`); const box = $('#gather'); box.innerHTML = ''; box.append(el('b', {}, r.line)); const list = el('div', { style: 'max-height:320px;overflow-y:auto;margin-top:6px;padding-right:6px' }); for (const o of r.offers) list.append(el('div', { style: 'display:flex;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid var(--rule)' }, crest(o.club, 26), el('span', {}, `${o.club.name} offer `, el('b', {}, o.words.join(' and '))), el('button', { class: 'btn', style: 'margin-left:auto;padding:3px 8px;font-size:14px', onclick: () => { tradeState = { other: o.club.abbr, a: [tradeState.a[0]], b: o.ids }; reload(); } }, 'Open'))); box.append(list); } }, 'Gather Offers'),
    el('button', { class: 'btn quiet', onclick: () => { tradeState.a = []; tradeState.b = []; reload(); } }, 'Clear'));
  foot.append(el('span', { class: 'count', style: 'margin-left:auto' }, (v.note || (v.can_trade ? `Deadline after Week ${v.deadline_week}` : '')) + ` · ${v.balance}`));
  s.append(foot, two, el('div', { class: 'read', id: 'gather', style: 'margin:0 14px 14px' }, 'Send one player and Gather Offers to see what the league would give.'));
  page.append(s);
}

function offerForm(t, kind, onDone, preset) {
  const f = el('div', { class: 'msg you' }, el('div', { class: 'from' }, preset ? 'Or Counter' : 'Your Offer'));
  const start = preset || {};
  const apy = el('input', { type: 'number', step: '0.1', min: '0.8', value: start.apy != null ? String(start.apy) : (t.ask ? (t.ask * 0.97).toFixed(1) : '1.0') }), yrs = el('input', { type: 'number', min: '1', max: '5', value: String(start.years || t.years || 3) });
  const bonus = el('input', { type: 'number', step: '0.5', min: '0', value: start.bonus != null ? String(start.bonus) : String(Math.round((t.ask || 1) * (t.years || 3) * 0.3 * 2) / 2) });
  const shapeChips = el('div', { class: 'chips' }); let shape = 0.5;
  for (const [val, label] of [[0.85, 'Pay It Now'], [0.5, 'League Shape'], [0.15, 'Back-Load']]) shapeChips.append(el('button', { class: 'chip', 'aria-pressed': String(val === shape), onclick: e => { shape = val; shapeChips.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); preview(); } }, label));
  const y1 = el('b', {}, '—'), total = el('b', {}, '—'); const hitsRow = el('div', { class: 'hits' });
  const preview = () => {
    const r = pyJSON(`SESSION.personnel_act('offer_preview', pid=${JSON.stringify(t.pid)}, apy=${+apy.value || 0}, years=${+yrs.value || 1}, bonus=${+bonus.value || 0}, front_load=${shape})`);
    if (!r.ok) return; y1.textContent = r.year1 != null ? `$${r.year1.toFixed(1)}m` : '—'; total.textContent = `$${r.total}m`;
    hitsRow.innerHTML = ''; r.hits.forEach((h, i) => hitsRow.append(el('div', { class: 'hit' }, el('div', { class: 'hbar' }, el('i', { style: `height:${Math.min(100, h / Math.max(...r.hits, 0.1) * 100)}%` })), el('span', {}, r.years[i]), el('b', {}, `$${h.toFixed(1)}m`))));
  };
  apy.onchange = yrs.onchange = bonus.onchange = preview;
  const promises = el('div', { class: 'promise' }, el('span', {}, 'Promise:')); const chosen = [];
  for (const [k, l] of [['starting_role', 'Named the Starter'], ['captaincy', 'Captaincy'], ['no_trade', 'No Trade'], ['extension_by', 'Extension by a Set Year'], ['no_tag', 'No Franchise Tag']]) promises.append(el('button', { class: 'btn quiet', style: 'padding:2px 8px;font-size:14px', 'aria-pressed': 'false', onclick: e => { const i = chosen.indexOf(k); if (i < 0) chosen.push(k); else chosen.splice(i, 1); e.currentTarget.setAttribute('aria-pressed', String(i < 0)); } }, l));
  f.append(el('div', { class: 'offer', style: 'grid-template-columns:repeat(5,1fr)' }, el('label', {}, 'New Years', yrs), el('label', {}, 'Per Year ($m)', apy), el('label', {}, 'Bonus ($m)', bonus), el('label', {}, 'Year 1 Hit', y1), el('label', {}, 'Total', total)),
    el('div', { class: 'shape' }, el('span', {}, 'Shape'), shapeChips), hitsRow, promises);
  const acts = el('div', { class: 'acts' });
  acts.append(el('button', { class: 'btn go', onclick: () => { const r = pyJSON(`SESSION.personnel_act('offer', tid=${t.id}, apy=${+apy.value}, years=${+yrs.value}, bonus=${+bonus.value || 0}, front_load=${shape}, promises=${JSON.stringify(chosen)})`); notify(r); onDone(); } }, kind === 'fa_inseason' ? 'Offer (decides at Advance)' : preset ? 'Send Counter' : 'Send Offer'));
  if (kind === 'fa_inseason') acts.append(el('button', { class: 'btn', 'data-tip': 'His full ask, signed now', onclick: () => { const r = pyJSON(`SESSION.personnel_act('offer', tid=${t.id}, apy=${t.ask}, years=${t.years}, sign_today=True)`); notify(r); onDone(); } }, `Sign Today at $${t.ask}m`));
  acts.append(el('button', { class: 'btn quiet', onclick: () => { const r = pyJSON(`SESSION.personnel_act('withdraw', tid=${t.id})`); notify(r); onDone(); } }, 'Let Him Go'));
  f.append(acts); setTimeout(preview, 0); return f;
}

function threadBox(t, onDone) {
  const box = el('div', { class: 'thread' });
  // the conversation as logged: every line with who said it, then the agent's temperament, then the decision
  const log = t.log && t.log.length ? t.log : [];
  if (!log.length) box.append(el('div', { class: 'msg' }, el('div', { class: 'from' }, `Agent · Before Any Offer`), el('div', { class: 'txt' }, t.ask ? el('span', {}, `He is asking `, el('b', {}, `$${t.ask}m × ${t.years}`), '.') : 'He would rather wait.')));
  for (const ln of log) box.append(el('div', { class: 'msg' + (ln.who === 'you' ? ' you' : '') }, el('div', { class: 'from' }, ln.who === 'you' ? 'You' : 'Agent'), el('div', { class: 'txt' }, ln.text)));
  if (t.ask && log.length) box.append(el('div', { class: 'msg note' }, el('b', {}, 'Ask · '), `$${t.ask}m × ${t.years}`));
  box.append(el('div', { class: 'msg note' }, t.agent_line || ''));
  if (t.rival) box.append(el('div', { class: 'msg match' }, el('div', { class: 'from' }, 'To Match'), el('div', { class: 'txt' }, `${t.rival.team} has offered `, el('b', {}, `$${t.rival.apy}m × ${t.rival.years}`), '. Match it and he signs today.'), el('div', { class: 'acts' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.personnel_act('match', tid=${t.id})`)); onDone(); } }, 'Match and Sign'), el('button', { class: 'btn quiet', onclick: () => { notify(pyJSON(`SESSION.personnel_act('withdraw', tid=${t.id})`)); onDone(); } }, 'Let Him Go'))));
  if (t.counter) box.append(el('div', { class: 'msg' }, el('div', { class: 'from' }, 'Counter'), el('div', { class: 'txt' }, el('b', {}, `$${t.counter.apy}m × ${t.counter.years}`)), el('div', { class: 'acts' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.personnel_act('match_counter', tid=${t.id})`)); onDone(); } }, 'Accept Counter'))));
  if (t.state === 'waiting') box.append(el('div', { class: 'msg note' }, `Waiting on his answer${t.due ? ' · due ' + t.due : ''}.`));
  else if (['accepted', 'signed'].includes(t.state)) box.append(el('div', { class: 'msg note' }, 'Signed.'));
  else if (t.state === 'broken_off') box.append(el('div', { class: 'msg note' }, 'He has broken off talks.'));
  else if (t.state === 'declined') box.append(el('div', { class: 'msg note' }, 'He declined.'));
  else box.append(offerForm(t, t.kind, onDone, t.counter ? { apy: t.counter.apy, years: t.counter.years } : null));
  return box;
}

let faPos = '', faCheap = false, faWatch = false, faRole = 'All', faQuery = '';
function renderFA(v) {
  renderRail(v.rail); const page = persPage(); persSecond('fa');
  const reload = () => renderFA(pyJSON(`SESSION.personnel('free_agency')`));
  const GROUP = { QB: ['QB'], OL: ['LT', 'LG', 'C', 'RG', 'RT'], WR: ['WR', 'TE'], DL: ['LEDG', 'DT', 'REDG'], DB: ['CB', 'FS', 'SS'], LB: ['MIKE', 'WILL', 'SAM'] };
  const inSeason = v.in_season;
  const left = el('section', { class: 'sheet c7' }, el('h2', {}, 'Free Agency', el('small', {}, inSeason
    ? `${v.count} Available · Cap Space $${v.cap}m · ${v.weeks_left} week${v.weeks_left === 1 ? '' : 's'} left · Roster ${v.roster} · Practice Squad ${v.ps}`
    : `${v.count} Available · Cap Space $${v.cap}m${v.top51 ? ' · Top 51' : ''} · Next Year $${v.committed_next}m of $${v.limit_next}m committed`)));
  const tools = el('div', { class: 'tools' });
  const posChips = el('div', { class: 'chips' }); for (const g of ['All', 'QB', 'OL', 'WR', 'DL', 'DB', 'LB']) posChips.append(el('button', { class: 'chip', 'aria-pressed': String((faPos || 'All') === g), onclick: () => { faPos = g === 'All' ? '' : g; renderFA(v); } }, g));
  const roleChips = el('div', { class: 'chips' }); for (const g of ['Starters', 'Depth']) roleChips.append(el('button', { class: 'chip', 'aria-pressed': String(faRole === g), onclick: () => { faRole = faRole === g ? 'All' : g; renderFA(v); } }, g));
  const cheap = el('button', { class: 'chip', 'aria-pressed': String(faCheap), 'data-tip': 'Players asking under $5m a year, or with no ask yet', onclick: () => { faCheap = !faCheap; renderFA(v); } }, 'Under $5m');
  const watchB = el('button', { class: 'chip', 'aria-pressed': String(faWatch), onclick: () => { faWatch = !faWatch; renderFA(v); } }, `Watchlist · ${v.rows.filter(r => r.watch).length}`);
  const search = el('input', { type: 'search', class: 'find', placeholder: 'Find a Player', value: faQuery }); search.oninput = () => { faQuery = search.value; drawRows(); };
  tools.append(posChips, roleChips, el('div', { class: 'chips' }, cheap, ...(inSeason ? [] : [watchB])), search);
  left.append(tools);
  const tbl = el('table', { class: 'tbl' });
  const drawRows = () => {
    tbl.innerHTML = '';
    if (inSeason) tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', { class: 'n', 'data-tip': 'How he grades in your scheme' }, 'Fit'), el('th', { 'data-tip': 'His agent\'s number, a year' }, 'Ask'), el('th', { class: 'n', 'data-tip': 'What he costs this year, prorated to the weeks left' }, 'This Year'), el('th', {}, ''), el('th', {}, '')));
    else tbl.append(el('tr', {}, el('th', {}, ''), el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', { class: 'n', 'data-tip': 'How he grades in your scheme' }, 'Fit'), el('th', {}, 'Ask'), el('th', {}, 'Interest'), el('th', {}, 'Your Offer'), el('th', {}, '')));
    const q = faQuery.trim().toLowerCase();
    const rows = v.rows.filter(r => (!faPos || (GROUP[faPos] || []).includes(r.pos)) && (faRole === 'All' || (faRole === 'Starters') === r.starter) && (!faCheap || r.ask == null || r.ask < 5) && (!faWatch || r.watch) && (!q || r.name.toLowerCase().includes(q)));
    for (const r of rows) {
      const who = el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, inSeason ? (r.hole || r.pos) : `${r.pos}${r.last ? ' · from ' + r.last : ''}`))));
      const askBtn = el('div', { style: 'display:flex;gap:4px' }, r.thread ? el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', onclick: () => { document.getElementById('th-' + r.thread)?.scrollIntoView(); } }, inSeason ? 'Talks' : 'Offer') : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', onclick: () => { notify(pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind=${JSON.stringify(inSeason ? 'fa_inseason' : 'fa_offseason')})`)); reload(); } }, 'Ask the Agent'),
        r.ps_ok ? el('button', { class: 'btn quiet', style: 'width:auto;padding:3px 8px;font-size:14px', 'data-tip': 'Sign him to the practice squad at the weekly rate; he can say no', onclick: () => { notify(pyJSON(`SESSION.personnel_act('sign_ps', pid=${JSON.stringify(r.pid)})`)); reload(); } }, 'Practice Squad') : '');
      if (inSeason) tbl.append(el('tr', {}, who, el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, fitCell(r.fit)), el('td', {}, r.ask ? `$${r.ask}m × ${r.years}` : el('span', { style: 'color:var(--ink-3)' }, '—')), el('td', { class: 'n' }, r.ask_now != null ? `$${r.ask_now.toFixed(2)}m` : '—'),
        el('td', {}, r.thread && r.ask ? el('button', { class: 'btn go', style: 'width:auto;padding:3px 8px;font-size:14px', 'data-tip': 'His full ask, signed now', onclick: () => { const t = v.threads.find(x => x.id === r.thread); const res = pyJSON(`SESSION.personnel_act('offer', tid=${r.thread}, apy=${t ? t.ask : r.ask}, years=${t ? t.years : r.years}, sign_today=True)`); notify(res); reload(); } }, 'Sign') : ''), el('td', {}, askBtn)));
      else tbl.append(el('tr', {}, el('td', {}, el('button', { class: 'star' + (r.watch ? ' on' : ''), 'data-tip': r.watch ? 'On your watchlist' : 'Add to your watchlist', onclick: () => { pyJSON(`SESSION.personnel_act('watch', pid=${JSON.stringify(r.pid)})`); reload(); } }, '★')), who, el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, fitCell(r.fit)),
        el('td', {}, r.ask ? `$${r.ask}m × ${r.years}` : el('span', { style: 'color:var(--ink-3)' }, '—')), el('td', {}, r.interest ? el('span', { class: 'pill ' + ({ 'Match Asked': 'unsettled', Agreed: 'happy', Countered: 'content', Mulling: 'content', Walked: 'unhappy' }[r.interest] || 'content') }, r.interest) : ''), el('td', {}, r.my_offer || el('span', { style: 'color:var(--ink-3)' }, '—')), el('td', {}, askBtn)));
    }
    if (!rows.length) tbl.append(el('tr', {}, el('td', { colspan: '10' }, el('div', { class: 'empty' }, v.rows.length ? 'Nobody matches the filter.' : 'Nobody is on the market.'))));
  };
  left.append(tbl); drawRows();
  page.append(left);
  const right = el('section', { class: 'sheet c5' }, el('h2', {}, inSeason ? 'Talks' : 'Negotiation', el('small', {}, `${v.threads.length} open`)));
  for (const t of v.threads) { const w = el('div', { id: 'th-' + t.id }, el('div', { class: 'h5', style: 'padding:10px 12px 0' }, `${t.name} · ${t.pos}`)); w.append(threadBox(t, reload)); right.append(w); }
  if (!v.threads.length) right.append(el('div', { class: 'empty' }, inSeason ? 'Ask an agent to hear his number. Sign at the ask today, or make a one-week offer that decides at the Advance.' : 'Ask an agent to open talks; he weighs offers through each round of the market.'));
  const feedSheet = el('section', { class: 'sheet c5', style: 'order:2' }, el('h2', {}, 'Around the League Today', el('small', {}, 'latest signings')));
  const fd = el('div', { class: 'feed' }); for (const f of v.feed) fd.append(el('div', {}, el('span', {}, stripe(f.team.abbr)), el('span', {}, `${f.team.name} ${f.kind === 'signs' ? 'signed' : 'extended'} `, el('b', {}, f.name), `, ${f.pos}${f.years ? `, ${f.years} year${f.years === 1 ? '' : 's'}` : ''}${f.apy ? ` at $${f.apy}m a year` : ''}`), el('time', {}, f.week ? `Wk ${f.week}` : ''))); if (!v.feed.length) fd.append(el('div', { class: 'empty' }, 'Quiet so far.')); feedSheet.append(fd);
  page.append(right, feedSheet);
}

let wireTab = 'wire';
function renderWire(v) {
  renderRail(v.rail); const page = persPage(); persSecond('wire');
  const reload = () => renderWire(pyJSON(`SESSION.personnel('waivers')`));
  const left = el('section', { class: 'sheet c8' }, el('h2', {}, 'Waiver Wire', el('small', {}, `You Hold ${v.my_priority ?? '—'}${v.my_priority ? ord(v.my_priority) : ''} Priority · Awards ${v.awards}`)));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' });
  for (const [k, label, n] of [['wire', 'On the Wire', v.rows.length], ['claims', 'Your Claims', v.claims.length], ['awarded', 'Awarded This Week', (v.awarded || []).length]]) tabs.append(el('button', { 'aria-pressed': String(wireTab === k), onclick: () => { wireTab = k; renderWire(v); } }, label + ' ', el('em', {}, n)));
  left.append(tabs);
  const rows = wireTab === 'wire' ? v.rows : wireTab === 'claims' ? v.claims : (v.awarded || []);
  const tbl = el('table', { class: 'tbl' });
  if (wireTab === 'awarded') { tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', {}, 'To'), el('th', {}, 'From'))); for (const r of rows) tbl.append(el('tr', { style: r.mine ? 'background:var(--sheet-2)' : '' }, el('td', {}, r.name), el('td', {}, r.pos), el('td', {}, r.team ? stripe(r.team.abbr, r.team.name) : ''), el('td', {}, r.frm || ''))); }
  else {
    tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', { class: 'n', 'data-tip': 'How he grades in your scheme' }, 'Fit'), el('th', {}, 'From'), el('th', { 'data-tip': 'The contract you take on' }, 'Inherited'), el('th', { class: 'n', 'data-tip': 'Dead cap if you cut him after' }, 'Penalty'), el('th', { class: 'n', 'data-tip': 'Accrued seasons' }, 'Accrued'), el('th', {}, '')));
    for (const r of rows) tbl.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos}${r.college ? ' · ' + r.college : ''}`)))), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, fitCell(r.fit)), el('td', {}, r.frm), el('td', {}, r.inherited), el('td', { class: 'n' }, `$${r.penalty.toFixed(1)}m`), el('td', { class: 'n' }, r.accrued),
      el('td', {}, r.claimed ? el('span', { class: 'badge-sm' }, 'Claimed') : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', onclick: () => { wireClaim = r.pid; renderWire(v); } }, 'Claim'))));
  }
  if (!rows.length) tbl.append(el('tr', {}, el('td', { colspan: '10' }, el('div', { class: 'empty' }, wireTab === 'wire' ? 'The wire is clear.' : wireTab === 'claims' ? 'No claims in.' : 'Nothing awarded yet this week.'))));
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
}
let wireClaim = null;

function renderExtensions(v) {
  renderRail(v.rail); const page = persPage(); persSecond('extensions');
  const reload = () => renderExtensions(pyJSON(`SESSION.personnel('extensions')`));
  const left = el('section', { class: 'sheet c7' }, el('h2', {}, 'Extensions', el('small', {}, `Next Year Committed: $${v.committed_next}m of $${v.limit_next}m · Cap $${v.cap}m`)));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' });
  for (const [k, label, list] of [['expiring', 'Expiring', v.expiring], ['two_left', 'Two Years Left', v.two_left], ['done', 'Done This Year', v.done]]) tabs.append(el('button', { 'aria-pressed': String(extTab === k), onclick: () => { extTab = k; renderExtensions(v); } }, label + ' ', el('em', {}, list.length)));
  left.append(tabs);
  const rows = v[extTab] || [];
  const tbl = el('table', { class: 'tbl' }); tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', {}, 'Morale'), el('th', { class: 'n' }, 'Cap Hit'), el('th', {}, 'Ask'), el('th', {}, 'Talks'), el('th', {}, '')));
  for (const r of rows) tbl.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos} · ${r.tag_line || ''}${r.fa_class ? ' · ' + r.fa_class : ''}`)))), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', {}, pill(r.morale)), el('td', { class: 'n' }, `$${r.hit.toFixed(1)}m`), el('td', {}, r.ask_word), el('td', { class: 'talks' }, r.talks_word),
    el('td', {}, r.thread ? el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', onclick: () => { document.getElementById('th-' + r.thread)?.scrollIntoView(); } }, 'Open Talks') : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', disabled: r.eligible ? null : '', onclick: () => { notify(pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind='extension')`)); reload(); } }, 'Ask the Agent'))));
  if (!rows.length) tbl.append(el('tr', {}, el('td', { colspan: '9' }, el('div', { class: 'empty' }, 'Nobody here.'))));
  left.append(tbl);
  const foot = el('div', { class: 'foot' });
  foot.append(el('a', { class: 'btn', href: '#frontoffice/cap' }, 'Restructure Instead'));
  if (v.tag && v.tag.open) {
    const tagSel = el('select', { class: 'btn' }); tagSel.append(el('option', { value: '' }, 'Franchise Tag…')); for (const r of v.expiring.filter(x => x.fa_class === 'UFA')) tagSel.append(el('option', { value: r.pid }, `${r.name} · ${r.pos}` + (r.tag_price ? ` · $${r.tag_price}m` : ''))); tagSel.append(el('option', { value: 'none' }, 'No tag this year'));
    tagSel.onchange = () => { if (!tagSel.value) return; notify(pyJSON(`SESSION.personnel_act('tag', pid=${JSON.stringify(tagSel.value)})`)); reload(); }; foot.append(tagSel);
  } else if (v.tag && v.tag.tagged) foot.append(el('span', { class: 'count' }, `Franchise tag placed on ${v.tag.tagged}`));
  else if (v.tag && v.tag.none) foot.append(el('span', { class: 'count' }, 'No tag this year'));
  left.append(foot);
  left.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Promises', el('small', {}, 'What You Have Told Your Players')));
  const pt = el('table', { class: 'tbl' }); pt.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Promise'), el('th', {}, 'Made'), el('th', {}, 'Checked'), el('th', {}, 'Status')));
  for (const p of v.promises) pt.append(el('tr', {}, el('td', {}, p.name), el('td', {}, (v.promise_kinds && v.promise_kinds[p.kind]) || p.kind.replace(/_/g, ' ')), el('td', {}, p.made), el('td', {}, p.checked || (p.kind === 'starting_role' ? 'Week 4' : p.kind === 'extension_by' ? 'Offseason' : 'Ongoing')), el('td', {}, el('span', { class: 'pill ' + (p.status === 'kept' ? 'happy' : p.status === 'broken' ? 'unhappy' : 'content') }, p.status.charAt(0).toUpperCase() + p.status.slice(1)))));
  if (!v.promises.length) pt.append(el('tr', {}, el('td', { colspan: '5' }, el('div', { class: 'empty' }, 'None made.'))));
  left.append(pt);
  page.append(left);
  const right = el('section', { class: 'sheet c5' }, el('h2', {}, 'Negotiation', el('small', {}, `${v.threads.length} open`)));
  for (const t of v.threads) { const w = el('div', { id: 'th-' + t.id }, el('div', { class: 'h5', style: 'padding:10px 12px 0' }, `${t.name} · ${t.pos}`)); w.append(threadBox(t, reload)); right.append(w); }
  if (!v.threads.length) right.append(el('div', { class: 'empty' }, 'Ask an agent to hear his number. Offers are answered in one to three weeks by situation.'));
  page.append(right);
}
let extTab = 'expiring';

// ---------------------------------------------------------------- Front Office
const FO = { owner: 'Owner', identity: 'Identity', staff: 'Staff', cap: 'Cap' };
function foSecond(cur) { secondRow(Object.entries(FO).map(([k, l]) => [l, '#frontoffice/' + k]), '#frontoffice/' + cur); $('#crumb').textContent = 'Front Office'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'frontoffice')); }

function renderOwner(v) {
  renderRail(v.rail); const page = persPage(); foSecond('owner');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, v.owner ? v.owner.name : 'Owner', el('small', {}, `${v.owner ? `Owner Since ${v.owner.since} · ` : ''}${v.record} · your year ${v.tenure + 1} in the chair`)));
  const g = el('div', { class: 'ownergrid' });
  const l = el('div', {});
  l.append(el('div', { class: 'facts2', style: 'grid-template-columns:repeat(5,1fr);padding:0' },
    el('div', {}, el('span', {}, 'Mood'), el('b', {}, v.mood)),
    el('div', {}, el('span', {}, 'This Year'), el('b', {}, v.expects.charAt(0).toUpperCase() + v.expects.slice(1))),
    el('div', {}, el('span', {}, 'The Draft'), el('b', {}, v.draft_word)),
    el('div', {}, el('span', {}, 'Staff Budget'), el('b', {}, `$${v.staff_budget.total}m`)),
    el('div', {}, el('span', {}, 'Your Job'), el('b', { style: v.job === 'Hot Seat' ? 'color:var(--danger)' : v.job === 'Warming' ? 'color:var(--decide)' : '' }, v.job))));
  l.append(el('div', { class: 'expect', style: 'margin-top:14px' }, el('span', {}, 'Bar'), el('span', {}, `${Math.round(v.expected_pct * 100)}% wins this year`), el('span', {}, 'Last Season'), el('span', {}, v.prev_pct ? `${Math.round(v.prev_pct * 100)}%` : '—'), el('span', {}, 'Playoff Drought'), el('span', {}, v.drought ? `${v.drought} year${v.drought === 1 ? '' : 's'}` : 'None'), el('span', {}, 'Staff Payroll'), el('span', {}, `$${v.staff_budget.payroll}m · $${v.staff_budget.available}m available`)));
  g.append(l);
  const r = el('div', {});
  r.append(el('div', { class: 'h5' }, 'What He Weighs'));
  const w = el('div', { class: 'weights' });
  for (const [k, lab] of [['wins', 'Winning Now'], ['young', 'Building Young'], ['stars', 'Big Names'], ['spend', 'Staff Spending']]) w.append(el('div', { class: 'wrow' }, el('span', {}, lab), el('div', { class: 't' }, el('i', { style: `width:${Math.round(v.weights[k] * 100)}%` }))));
  r.append(w);
  r.append(el('div', { style: 'margin-top:14px' }, el('button', { class: 'btn', onclick: e => { const box = e.currentTarget.nextSibling; box.hidden = !box.hidden; } }, 'Season Reviews'), (() => { const h = el('div', { class: 'histlist', hidden: '', style: 'margin-top:8px' }); for (const x of v.reviews) h.append(el('div', {}, el('time', {}, x.year), el('span', {}, `${x.record || ''} · ${x.line || ''}`))); if (!v.reviews.length) h.append(el('div', {}, el('time', {}, '—'), el('span', {}, 'He reviews you after each season.'))); return h; })()));
  g.append(r); s.append(g); page.append(s);
}

let idPreview = null, restructureFor = null;
function renderIdentity(v) {
  renderRail(v.rail); const page = persPage(); foSecond('identity');
  const reload = () => renderIdentity(pyJSON(`SESSION.frontoffice('identity'${idPreview ? ', preview=' + JSON.stringify(idPreview) : ''})`));
  const pv = v.preview;
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Coaching Identity', el('small', {}, `${v.coach} · ${v.identity.offense} · ${v.identity.defense}`)));
  // the archetypes, one row a side, centered; current marked, preview marked
  for (const side of ['offense', 'defense']) {
    const row = el('div', { class: 'arch center' });
    for (const a of v.archetypes.filter(x => x.side === side)) {
      const cls = (a.current ? 'now' : '') + (pv && pv.key === a.key ? ' preview' : '');
      row.append(el('div', { class: cls, 'data-tip': a.words, onclick: () => { idPreview = a.current ? null : a.key; reload(); } }, a.name, el('small', {}, a.current ? `Your ${side}` : side)));
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
  s.append(el('div', { class: 'foot' }, el('button', { class: 'btn', disabled: mis.length ? null : '', onclick: () => { tradeState = { other: tradeState.other, a: [mis[0].pid], b: [], keep: true }; location.hash = '#personnel/trades'; } }, 'Trade Block a Misfit'), el('button', { class: 'btn quiet', onclick: e => { const h = document.getElementById('idhist'); h.hidden = !h.hidden; } }, 'Identity History')));
  const h = el('div', { class: 'histlist', id: 'idhist', hidden: '', style: 'margin:0 14px 14px' }); for (const x of v.history.slice().reverse()) h.append(el('div', {}, el('time', {}, `${x.year} W${x.week ?? 0}`), el('span', {}, x.change))); if (!v.history.length) h.append(el('div', {}, el('time', {}, '—'), el('span', {}, 'The identity you inherited.')));
  s.append(h); page.append(s);
}

// the staff's trait chips: want traits gold, coaching traits green, a scout's strengths green and blind spots red, unknown gray
function staffTraits(c) {
  const box = el('div', { class: 'traits', style: 'gap:4px' });
  if (!c.traits || !c.traits.length) { box.append(el('span', { class: 'trait even' }, 'None')); return box; }
  for (const t of c.traits) box.append(el('span', { class: 'trait ' + ({ want: 'money', coach: 'work', pos: 'work', neg: 'unhappy-t', unknown: 'unknown' }[t.fam] || 'even'), 'data-tip': t.tip }, t.name));
  return box;
}

let interviewOpen = null;
// the interview thread on a pool card: three questions, then Offer or Pass
function interviewPanel(c, role, reload) {
  const st = pyJSON(`SESSION.frontoffice_act('staff_interview', name=${JSON.stringify(c.name)})`).state;
  const box = el('div', { class: 'thread', style: 'margin-top:10px;padding:0' });
  const log = el('div', { class: 'thread', style: 'padding:0;font-size:13px' });
  for (const m of st.log) log.append(el('div', { class: 'msg' + (m.who === 'gm' ? ' you' : '') + (m.trait ? ' match' : '') }, m.text));
  box.append(log);
  const ask = q => { const r = pyJSON(`SESSION.frontoffice_act('staff_interview', name=${JSON.stringify(c.name)}, question=${JSON.stringify(q)})`); if (!r.ok) notify(r); reload(); };
  const qs = role === 'scout' ? [['hits', 'Ask about his hits', 'One of his strengths, in his words'], ['misses', 'Ask about his misses', 'One of his blind spots'], ['references', 'Ask his references', 'One more trait, at the Advance; a reference can be wrong']]
                             : [['coaching', 'Ask about his coaching', 'One coaching trait, in his words'], ['situation', 'Ask about his situation', 'What he wants from you; a Mercenary hears you are shopping'], ['references', 'Ask his references', 'One more trait, at the Advance; a reference can be wrong']];
  const row = el('div', { class: 'acts', style: 'flex-wrap:wrap' });
  for (const [k, label, tip] of qs) row.append(el('button', { class: 'btn', disabled: st.asked.includes(k) ? '' : null, 'data-tip': tip, onclick: () => ask(k) }, st.asked.includes(k) ? (k === 'references' && st.refs_due ? 'Calls out' : 'Asked') : label));
  box.append(row);
  box.append(el('div', { class: 'read', style: 'margin-top:6px' }, st.all_known ? 'You know everything he is.' : `${st.n_hidden} trait${st.n_hidden === 1 ? '' : 's'} you have not learned. Offer at $${(+st.ask).toFixed(1)}m or keep asking.`));
  return box;
}

function renderStaff(v) {
  renderRail(v.rail); const page = persPage(); foSecond('staff');
  const reload = () => renderStaff(pyJSON(`SESSION.frontoffice('staff')`));
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Staff', el('small', {}, `Budget $${v.budget.total}m · Paid $${v.budget.payroll}m · Available $${v.budget.available}m`)));
  const grid = el('div', { class: 'staffgrid', style: 'grid-template-columns:repeat(4,1fr)' });
  for (const c of v.cards) {
    if (c.empty) { grid.append(el('div', { class: 'scard open' }, `${c.role_name} · open. Hire from the pool below.`)); continue; }
    const card = el('div', { class: 'scard' }, el('div', { class: 'role' }, c.role + (c.hc_candidate ? ' · Head-Coaching Candidate' : '') + (c.disgruntled ? ' · Disgruntled' : '')), el('div', { class: 'nm' }, c.name),
      el('div', { class: 'kv' }, el('span', {}, 'Rating'), el('b', {}, c.rating), el('span', {}, 'Prestige'), el('b', {}, c.prestige), el('span', {}, 'Specialty'), el('span', {}, c.specialty || '—'), el('span', {}, 'Age'), el('span', {}, c.age), el('span', {}, 'Contract'), el('span', {}, `$${(+c.salary).toFixed(1)}m · Expires ${v.rail.year + c.years}`), el('span', {}, 'Asks'), el('span', {}, `$${(+c.extend_ask).toFixed(1)}m`), el('span', {}, `${c.role.replace(' Coordinator', '')} Rank`), el('span', {}, (c.unit_ranks || []).length ? c.unit_ranks.map(r => `${r}${ord(r)}`).join(' · ') : '—'), el('span', {}, 'Traits'), staffTraits(c)));
    const acts = el('div', { class: 'acts' });
    acts.append(el('button', { class: 'btn', 'data-tip': `Three more years at his ask, $${(+c.extend_ask).toFixed(1)}m`, onclick: () => { notify(pyJSON(`SESSION.frontoffice_act('staff_extend', role=${JSON.stringify(c.role_key)}, years=3, salary=${c.extend_ask})`)); reload(); } }, 'Extend'));
    if (v.offseason) acts.append(el('button', { class: 'btn warn', onclick: () => { if (confirm(`Release ${c.name}? You owe what is left on his deal.`)) { notify(pyJSON(`SESSION.frontoffice_act('staff_release', role=${JSON.stringify(c.role_key)})`)); reload(); } } }, 'Release'));
    card.append(acts); grid.append(card);
  }
  s.append(grid);
  // a club wants your coordinator: the conversation
  for (const p of v.poaches) {
    const box = el('div', { class: 'thread', style: 'margin:0 14px 12px;border:1px solid var(--rule)' }, el('div', { class: 'h5', style: 'padding:8px 12px 0' }, 'A Club Wants Your Coordinator', el('span', {}, `${p.to_club.name} · Head Coach`)));
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
  s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'The Pool', el('small', {}, v.offseason ? 'Hire Into an Open Job · Greyed Where He Does Not Fit What You Have Available' : 'hiring reopens after the season')));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); const list = el('div', { class: 'pad' }); let role = 'oc';
  const draw = () => { list.innerHTML = ''; const cur = v.cards.find(x => x.role_key === role); const room = v.budget.available + (cur && !cur.empty ? +cur.salary : 0); const grid2 = el('div', { class: 'staffgrid', style: 'grid-template-columns:repeat(4,1fr);padding:0' });
    for (const c of v.pools[role]) { const fits = +c.ask <= room + 1e-9; const card = el('div', { class: 'scard', style: fits ? '' : 'opacity:.45' }, el('div', { class: 'nm' }, c.name), el('div', { class: 'role', style: 'text-transform:none;letter-spacing:0' }, c.background), el('div', { class: 'kv' }, el('span', {}, 'Rating'), el('b', {}, c.rating), el('span', {}, 'Prestige'), el('b', {}, c.prestige), el('span', {}, 'Age'), el('span', {}, c.age), el('span', {}, 'Asks'), el('span', {}, `$${(+c.ask).toFixed(1)}m`), el('span', {}, 'Traits'), staffTraits(c)),
        el('div', { class: 'acts' }, el('button', { class: 'btn go', 'data-tip': 'Sit down with him: learn his traits before you decide', onclick: () => { interviewOpen = interviewOpen === c.name ? null : c.name; draw(); } }, interviewOpen === c.name ? 'Close' : 'Interview'),
          el('button', { class: 'btn', disabled: v.offseason && fits ? null : '', 'data-tip': v.offseason ? (fits ? 'Three years at his ask; replaces the sitting coach' : 'Over what you have available') : 'Offseason only', onclick: () => { notify(pyJSON(`SESSION.frontoffice_act('staff_hire', name=${JSON.stringify(c.name)})`)); interviewOpen = null; renderStaff(pyJSON(`SESSION.frontoffice('staff')`)); } }, 'Offer')));
      if (interviewOpen === c.name) card.append(interviewPanel(c, role, () => renderStaff(pyJSON(`SESSION.frontoffice('staff')`))));
      grid2.append(card); }
    list.append(grid2); };
  for (const [k, l] of [['oc', 'Offensive Coordinators'], ['dc', 'Defensive Coordinators'], ['st', 'Special Teams'], ['scout', 'Head Scouts']]) tabs.append(el('button', { 'aria-pressed': String(role === k), onclick: e => { role = k; tabs.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); draw(); } }, l));
  s.append(tabs, list); draw(); page.append(s);
}

function renderCap(v) {
  renderRail(v.rail); const page = persPage(); foSecond('cap');
  const reload = () => renderCap(pyJSON(`SESSION.frontoffice('cap')`));
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Cap', el('small', {}, `${v.years[0].year} Limit $${v.years[0].limit}m` + (v.top51 ? ' · Top 51 Applies in the Offseason' : '') + ` · Space $${v.cap_space}m`)));
  const yrs = el('div', { class: 'capyears' });
  const COL = { QB: '#c8102e', RB: '#4cc9f0', WR: '#ffb612', TE: '#3fb37f', OL: '#5aa9d6', DL: '#e5484d', LB: '#a78bfa', DB: '#f59e0b', ST: '#7b8593' };
  v.years.forEach((y, i) => {
    const st = el('div', { class: 'stack' }); for (const [g, val] of Object.entries(y.by)) if (val > 0) st.append(el('i', { style: `width:${(val / y.limit * 100).toFixed(1)}%;background:${COL[g]}`, 'data-tip': `${g} $${val}m` })); if (y.dead > 0) st.append(el('i', { style: `width:${(y.dead / y.limit * 100).toFixed(1)}%;background:#3a424c`, 'data-tip': `Penalty $${y.dead}m` }));
    const kv = el('div', { class: 'kv' }, el('span', {}, 'Committed'), el('span', {}, `$${y.committed}m`), el('span', {}, 'Penalty'), el('span', {}, `$${y.dead}m`));
    if (i === 0) kv.append(el('span', {}, 'Practice Squad'), el('span', {}, `$${y.ps_charge}m`), el('span', {}, 'Rookie Pool'), el('span', {}, '—'));
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
    const drawD = q => { delta.innerHTML = ''; const yr = v.years[0].year; const later = q.added_later || []; delta.append(el('div', {}, el('div', { class: 'l' }, 'Saved Now'), el('div', { class: 'v good' }, `$${q.saves_now}m`)), el('div', {}, el('div', { class: 'l' }, `Added ${yr + 1}`), el('div', { class: 'v bad' }, later.length ? `$${later[0].toFixed(1)}m` : '—')), el('div', {}, el('div', { class: 'l' }, later.length > 1 ? `Added ${yr + 2}–${yr + later.length}` : 'Added later'), el('div', { class: 'v bad' }, later.length > 1 ? `$${later.slice(1).reduce((a, b) => a + b, 0).toFixed(1)}m` : '—')), el('div', {}, el('div', { class: 'l' }, `Penalty if Cut '${String(yr + 1).slice(2)}`), el('div', { class: 'v' }, `$${q.dead_if_cut_next_year}m`))); say.innerHTML = ''; say.append(el('b', {}, 'Assistants: '), q.say || ''); };
    const re = () => { const q = pyJSON(`SESSION.frontoffice_act('restructure_preview', pid=${JSON.stringify(r.pid)}, amount=${+amt.value}, void_years=${+voids.value})`); if (q.ok) drawD(q); };
    amt.onchange = re; voids.onchange = re;
    box.append(el('div', { class: 'offer' }, el('label', {}, 'Base to Convert ($m)', amt), el('label', {}, 'Void Years (0–2)', voids)), delta, say,
      el('div', { style: 'display:flex;gap:6px;margin-top:10px' }, el('button', { class: 'btn go', onclick: () => { const q = pyJSON(`SESSION.frontoffice_act('restructure', pid=${JSON.stringify(r.pid)}, amount=${+amt.value}, void_years=${+voids.value})`); notify({ ok: q.ok, line: q.ok ? `Restructured. Saves $${q.saves_now}m this year.` : q.why }); reload(); } }, 'Restructure'), el('button', { class: 'btn quiet', onclick: () => { box.innerHTML = ''; box.append('Pick a player from the ledger.'); } }, 'Pick Another Contract')));
    drawD(p);
  };
  // tags and tools
  pvBox.append(el('div', { class: 'h5', style: 'margin-top:14px' }, 'Tags and Tools', el('span', {}, `${v.years[0].year + 1} Offseason`)));
  const tt = el('div', { class: 'kv' });
  for (const t of v.tags) tt.append(el('span', {}, `Franchise Tag · ${t.pos}`), el('span', {}, `$${t.price}m · `, el('span', { style: 'cursor:pointer;text-decoration:underline dotted', onclick: () => { location.hash = '#club/player/' + t.pid; } }, surname(t.name))));
  if (!v.tags.length) tt.append(el('span', {}, 'Franchise Tag'), el('span', {}, 'No unrestricted free agent to tag next offseason'));
  tt.append(el('span', {}, 'Void Years Carried'), el('span', {}, v.void_carried ? `$${v.void_carried}m accelerating when the deals void` : 'None'), el('span', {}, 'Cuts and Trades'), el('span', { style: 'color:var(--ink-3)' }, v.june1_rule));
  pvBox.append(tt);
  pvBox.append(el('div', { class: 'h5', style: 'margin-top:14px' }, 'Largest Hits', el('span', {}, String(v.years[0].year))));
  for (const r of v.largest) pvBox.append(el('div', { class: 'fitrow', style: 'grid-template-columns:1fr 1fr 60px' }, el('span', { style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + r.pid; } }, `${r.name} · ${r.pos}`), el('div', { class: 'bar', style: 'height:8px' }, el('i', { style: `width:${Math.min(100, r.share * 4)}%;background:var(--club)` })), el('span', { class: 'v' }, `$${r.hit.toFixed(1)}m`)));
  pvBox.append(el('div', { class: 'h5', style: 'margin-top:14px' }, 'Penalty Detail', el('span', {}, `$${v.dead_total}m this year · $${v.dead_next}m next`)));
  if (v.dead_rows.length) { const dt = el('table', { class: 'stab' }); dt.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'How'), el('th', {}, 'This Year'), el('th', {}, 'Next Year'))); for (const r of v.dead_rows) dt.append(el('tr', {}, el('td', {}, `${r.name} · ${r.pos}`), el('td', {}, r.how + (r.week ? ` wk ${r.week}` : '')), el('td', {}, `$${r.dead.toFixed(1)}m`), el('td', {}, r.dead_next ? `$${r.dead_next.toFixed(1)}m` : '—'))); pvBox.append(dt); }
  else pvBox.append(el('div', { class: 'empty' }, v.dead_total ? 'Charges carried in from before this season.' : 'No penalty on the books.'));
  const ledger = el('div', {}, el('div', { class: 'h5' }, 'Ledger'));
  const tbl = el('table', { class: 'tbl' }); tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), ...v.years.map(y => el('th', { class: 'n' }, String(y.year))), el('th', { class: 'n', 'data-tip': 'Dead cap if cut this year' }, 'Penalty'), el('th', { class: 'n' }, 'Yrs'), el('th', {}, ''), el('th', {}, '')));
  for (const r of v.rows) tbl.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name))), el('td', {}, r.pos), ...r.hits.map(h => el('td', { class: 'n' }, h == null ? '—' : `$${h.toFixed(1)}m`)), el('td', { class: 'n' }, `$${r.penalty.toFixed(1)}m`), el('td', { class: 'n' }, r.yrs), el('td', {}, ...r.tags.map(t => el('span', { class: 'badge-sm', style: 'margin-right:4px' }, t))),
    el('td', {}, r.restructurable > 0.5 ? el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:14px', onclick: () => openPreview(r) }, 'Restructure') : '')));
  ledger.append(tbl, el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#personnel/extensions' }, 'Extensions')));
  two.append(ledger, pvBox); s.append(two); page.append(s);
  if (restructureFor) { const r = v.rows.find(x => x.pid === restructureFor); restructureFor = null; if (r) openPreview(r); }
}

// ---------------------------------------------------------------- Draft
const DR = { board: 'Scouting Board', spring: 'The Spring', day: 'Draft Day', picks: 'Picks' };
let boardPos = 'All', boardFilt = { early: false, late: false, small: false, needs: false }, boardTab = 'class', boardQuery = '', boardSel = null;
function drSecond(cur) { secondRow(Object.entries(DR).map(([k, l]) => [l, '#draft/' + k]), '#draft/' + cur); $('#crumb').textContent = 'Draft'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'draft')); }
function gapCell(g) { if (g == null) return el('span', { class: 'gap' }, '—'); return el('span', { class: 'gap ' + (g > 0 ? 'up' : g < 0 ? 'dn' : '') }, (g > 0 ? '+' : '') + g); }
function flagTags(fl) { const s = el('span', {}); for (const f of fl || []) s.append(el('span', { class: 'flag ' + ({ medical: 'med', character: 'chr', visit: 'vis', riser: 'up', faller: 'dn', 'senior bowl': 'sr' }[String(f).toLowerCase()] || 'ss') }, String(f))); return s; }
const POS_GROUPS = ['All', 'QB', 'HB', 'WR', 'TE', 'OL', 'DL', 'LB', 'DB', 'ST'];
const POS_OF = { QB: ['QB'], HB: ['HB', 'FB'], WR: ['WR'], TE: ['TE'], OL: ['LT', 'LG', 'C', 'RG', 'RT'], DL: ['LEDG', 'DT', 'REDG'], LB: ['MIKE', 'WILL', 'SAM'], DB: ['CB', 'FS', 'SS'], ST: ['K', 'P', 'LS'] };

const NEED_POS = { QB: ['QB'], RB: ['HB', 'FB'], WR: ['WR'], TE: ['TE'], OL: ['LT', 'LG', 'C', 'RG', 'RT'], EDGE: ['LEDG', 'REDG'], DT: ['DT'], LB: ['MIKE', 'WILL', 'SAM'], CB: ['CB'], S: ['FS', 'SS'] };
const wordTag = w => el('span', { class: 'flag ' + ({ Medical: 'med', Character: 'chr', Visited: 'vis', Riser: 'up', Faller: 'dn', 'Sr. Bowl': 'sen', 'Small School': 'small', Underclassman: 'under' }[w] || '') }, w);

function renderBoard(v) {
  renderRail(v.rail); const page = persPage(); drSecond('board');
  const reload = () => renderBoard(pyJSON(`SESSION.draft_view('board')`));
  const onBoard = new Set(v.user_board.order.map(x => x.pid)), dnd = new Set(v.user_board.dnd.map(x => x.pid));
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Scouting Board', el('small', {}, `${v.count} prospects` + (v.scout ? ` · Head Scout ${v.scout.name} (${v.scout.rating})` : ''))));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' });
  for (const [k, l, n] of [['class', `Class of ${v.year}`, v.count], ['board', 'Your Board', onBoard.size], ['visited', 'Visited', v.rows.filter(r => r.visited).length]]) tabs.append(el('button', { 'aria-pressed': String(boardTab === k), onclick: () => { boardTab = k; renderBoard(v); } }, l + ' ', el('em', {}, n)));
  s.append(tabs);
  if (boardTab === 'board') { s.append(yourBoard(v, reload)); page.append(s); return; }
  const filt = el('div', { class: 'filt-pos' });
  for (const g of ['All', 'QB', 'OL', 'WR', 'EDGE', 'CB']) filt.append(el('button', { class: 'btn' + (boardPos === g ? ' go' : ''), onclick: () => { boardPos = g; renderBoard(v); } }, g));
  filt.append(el('span', { style: 'width:1px;background:var(--rule-2);margin:0 6px' }));
  for (const [k, label, tip] of [['needs', 'Needs', `Your needs: ${v.needs.join(', ') || 'none'}`], ['early', 'Rounds 1–3', 'Consensus in the first 96'], ['late', '4–7', 'Consensus after the first 96'], ['small', 'Small School', 'Outside the power conferences: your read is wider on these players']]) filt.append(el('button', { class: 'btn' + (boardFilt[k] ? ' go' : ''), 'data-tip': tip, onclick: () => { boardFilt[k] = !boardFilt[k]; if (k === 'early' && boardFilt.early) boardFilt.late = false; if (k === 'late' && boardFilt.late) boardFilt.early = false; renderBoard(v); } }, label));
  const search = el('input', { type: 'search', class: 'find', placeholder: 'Find a Prospect', value: boardQuery }); search.oninput = () => { boardQuery = search.value; draw(); }; filt.append(search);
  filt.append(el('span', { class: 'count', style: 'margin-left:auto;align-self:center' }, `Visits ${v.visits.length} of ${v.visits_max}` + (v.spring_done ? ' · the spring has run' : ' · name them before the Spring')));
  s.append(filt);
  const tbl = el('table', { class: 'tbl' });
  const draw = () => {
    tbl.innerHTML = '';
    tbl.append(el('tr', {}, el('th', { class: 'n' }, '#'), el('th', {}, 'Prospect'), el('th', {}, 'Pos'), el('th', {}, 'School'), el('th', { class: 'n', 'data-tip': "Your scouts' read. Carries error; a visit tightens it" }, 'Estimated Overall'), el('th', { class: 'n', 'data-tip': 'Where he can grow to. Wide means your scouts are unsure' }, 'Ceiling'), el('th', { class: 'n', 'data-tip': "The league's grade, same scale as yours" }, 'Consensus'), el('th', { class: 'n', 'data-tip': "Yours minus the league's. Positive means the league undervalues him" }, 'Gap'), el('th', { class: 'n', 'data-tip': 'Where the league expects him to go' }, 'Proj.'), el('th', {}, 'Flags'), el('th', {}, '')));
    const q = boardQuery.trim().toLowerCase(); const GROUP = { QB: ['QB'], OL: ['LT', 'LG', 'C', 'RG', 'RT'], WR: ['WR', 'TE'], EDGE: ['LEDG', 'REDG', 'DT'], CB: ['CB', 'FS', 'SS'] };
    const needPos = new Set(v.needs.flatMap(g => NEED_POS[g] || []));
    const rows = v.rows.filter(r => (boardTab !== 'visited' || r.visited) && (boardPos === 'All' || (GROUP[boardPos] || []).includes(r.pos)) && (!boardFilt.needs || needPos.has(r.pos)) && (!boardFilt.early || (r.cons_rank != null && r.cons_rank <= 96)) && (!boardFilt.late || (r.cons_rank != null && r.cons_rank > 96)) && (!boardFilt.small || r.small) && (!q || r.name.toLowerCase().includes(q) || (r.college || '').toLowerCase().includes(q))).slice(0, 200);
    for (const r of rows) tbl.append(el('tr', { class: (r.visited ? 'visited' : '') + (boardSel === r.pid ? ' sel' : ''), style: r.taken ? 'opacity:.4' : '', onclick: e => { if (e.target.closest('button')) return; boardSel = boardSel === r.pid ? null : r.pid; draw(); drawFoot(); } },
      el('td', { class: 'n' }, r.my_rank), el('td', {}, el('button', { class: 'who', onclick: e => { e.stopPropagation(); location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos} · ${r.cls_year}${r.size ? ' · ' + r.size : ''}`)))), el('td', {}, r.pos), el('td', {}, r.college), el('td', { class: 'n' }, ovrCell(r.mine)), el('td', { class: 'n' }, r.ceiling), el('td', { class: 'n' }, r.cons != null ? r.cons : '—'), el('td', { class: 'n' }, gapCell(r.gap)), el('td', { class: 'n' }, r.proj_range), el('td', {}, ...r.words.map(wordTag)),
      el('td', {}, el('div', { style: 'display:flex;gap:4px' }, (v.spring_done || r.visit_locked) ? '' : el('button', { class: 'btn' + (r.visited ? ' go' : ''), style: 'width:auto;padding:2px 8px;font-size:14px', 'data-tip': r.visited ? 'Cancel the visit' : 'Bring him in: the second look is the sharpest read your scouts get', onclick: e => { e.stopPropagation(); const res = pyJSON(`SESSION.draft_act('visit', pid=${JSON.stringify(r.pid)})`); notify(res); reload(); } }, r.visited ? 'Visiting' : 'Visit'),
        onBoard.has(r.pid) ? el('span', { class: 'badge-sm' }, `#${v.user_board.order.findIndex(x => x.pid === r.pid) + 1}`) : el('button', { class: 'btn', style: 'width:auto;padding:2px 8px;font-size:14px', 'data-tip': 'Add him to the bottom of your board', onclick: () => { pyJSON(`SESSION.draft_act('board', add=${JSON.stringify(r.pid)})`); reload(); } }, 'Add')))));
    if (!rows.length) tbl.append(el('tr', {}, el('td', { colspan: '11' }, el('div', { class: 'empty' }, 'Nobody matches the filter.'))));
  };
  const foot = el('div', { class: 'foot' });
  const drawFoot = () => { foot.innerHTML = ''; const r = v.rows.find(x => x.pid === boardSel);
    foot.append(el('button', { class: 'btn', disabled: r ? null : '', onclick: () => { pyJSON(`SESSION.draft_act('board', add=${JSON.stringify(boardSel)})`); reload(); } }, 'Add to Your Board'), el('button', { class: 'btn', disabled: r ? null : '', onclick: () => { location.hash = '#club/player/' + boardSel; } }, 'Prospect Card'), el('span', { class: 'count', style: 'margin-left:auto' }, r ? `${r.name} · ${r.pos} · ${r.college}` : 'Click a row to select a prospect')); };
  s.append(el('div', { class: 'board-wrap' }, tbl), foot); draw(); drawFoot();
  // the spring, inline: stock moves and flags
  const sp = v.spring || null;
  s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'The Spring', el('small', {}, 'Stock Moves and Flags')));
  const spBox = el('div', { class: 'pad' });
  if (v.spring_done) spBox.append(el('a', { class: 'btn', href: '#draft/spring' }, 'Open the Spring'));
  else spBox.append(el('div', { class: 'empty' }, 'The combine, the Senior Bowl, pro days and your visits come in the Spring step. Name your visits now; the second look is the sharpest read your scouts get.'));
  s.append(spBox);
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
    t.append(el('tr', { draggable: 'true', 'data-pid': r.pid }, el('td', { class: 'n' }, i + 1), el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos} · ${r.college}${r.my_round && x.tier > 1 ? ' · Your Grade ' + r.my_round : ''}`)))), el('td', { class: 'n' }, r.proj_range), el('td', { class: 'n' }, ovrCell(r.mine)),
      el('td', {}, el('div', { style: 'display:flex;gap:4px' }, el('button', { class: 'btn', style: 'padding:2px 6px;font-size:14px', disabled: i === 0 ? '' : null, onclick: () => { const o = order.slice(); [o[i - 1], o[i]] = [o[i], o[i - 1]]; pyJSON(`SESSION.draft_act('board', order=${JSON.stringify(o)})`); reload(); } }, '▲'), el('button', { class: 'btn', style: 'padding:2px 6px;font-size:14px', disabled: i === order.length - 1 ? '' : null, onclick: () => { const o = order.slice(); [o[i + 1], o[i]] = [o[i], o[i + 1]]; pyJSON(`SESSION.draft_act('board', order=${JSON.stringify(o)})`); reload(); } }, '▼'),
        el('button', { class: 'btn quiet', style: 'padding:2px 6px;font-size:14px', 'data-tip': 'Do Not Draft', onclick: () => { const d = v.user_board.dnd.map(z => z.pid).concat([r.pid]); pyJSON(`SESSION.draft_act('board', remove=${JSON.stringify(r.pid)})`); pyJSON(`SESSION.draft_act('board', dnd=${JSON.stringify(d)})`); reload(); } }, '✕')))));
  });
  if (!order.length) t.append(el('tr', {}, el('td', { colspan: '5' }, el('div', { class: 'empty' }, "Your board is empty. Add prospects from the class, or Auto-Fill by Read to start from your scouts' order."))));
  if (v.user_board.dnd.length) { t.append(el('tr', { class: 'grp' }, el('td', { colspan: '5' }, 'Do Not Draft'))); for (const x of v.user_board.dnd) { const r = byid[x.pid]; if (!r) continue; t.append(el('tr', { style: 'opacity:.6' }, el('td', { class: 'n' }, '✕'), el('td', {}, el('div', { class: 'who' }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos} · ${r.college} · ${x.why}`)))), el('td', { class: 'n' }, '—'), el('td', { class: 'n' }, ovrCell(r.mine)), el('td', {}, el('button', { class: 'btn quiet', style: 'padding:2px 6px;font-size:14px', onclick: () => { pyJSON(`SESSION.draft_act('board', dnd=${JSON.stringify(v.user_board.dnd.map(z => z.pid).filter(z => z !== r.pid))})`); reload(); } }, 'Restore')))); } }
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
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'The Spring', el('small', {}, v.done ? v.events.map(e => `${e.event} ${e.n} moves`).join(' · ') : 'stock moves and flags')));
  if (!v.done) { s.append(el('div', { class: 'empty' }, v.note)); page.append(s); return; }
  const list = el('div', { class: 'pad' });
  const line = (kind, m) => el('div', { class: 'sprow' }, el('span', { class: 'flag ' + ({ Rises: 'up', Falls: 'dn', Medical: 'med', Character: 'chr' }[kind] || '') }, kind), el('span', {}, el('b', { style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + m.pid; } }, m.name), ` (${m.pos}, ${m.college}) ${m.frm} to ${m.to} after the ${m.event}${m.why ? ' · ' + m.why : ''}`));
  for (const m of v.risers) list.append(line('Rises', m));
  for (const m of v.fallers) list.append(line('Falls', m));
  for (const r of v.flagged) { const med = r.flags.includes('medical'), chr = r.flags.includes('character'); if (med) list.append(el('div', { class: 'sprow' }, el('span', { class: 'flag med' }, 'Medical'), el('span', {}, el('b', {}, r.name), ` (${r.pos}, ${r.college}) flagged out of the combine`))); if (chr) list.append(el('div', { class: 'sprow' }, el('span', { class: 'flag chr' }, 'Character'), el('span', {}, `Your room came away from the ${r.name} visit with a concern about his character.`))); }
  if (!list.children.length) list.append(el('div', { class: 'empty' }, 'No stock moves or flags this spring.'));
  s.append(list);
  s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Your Visits', el('small', {}, `${v.visited.length} players · the second look`)));
  const vt = el('table', { class: 'tbl' }); vt.append(el('tr', {}, el('th', {}, 'Prospect'), el('th', {}, 'Pos'), el('th', { class: 'n', 'data-tip': "Your scouts' read. Carries error; a visit tightens it" }, 'Your Read'), el('th', { class: 'n', 'data-tip': 'Where he can grow to. Wide means your scouts are unsure' }, 'Ceiling'), el('th', { class: 'n', 'data-tip': "The league's grade, same scale as yours" }, 'Consensus'), el('th', { class: 'n', 'data-tip': "Yours minus the league's. Positive means the league undervalues him" }, 'Gap'), el('th', {}, 'Flags')));
  for (const r of v.visited) vt.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, r.college)))), el('td', {}, r.pos), el('td', { class: 'n' }, ovrCell(r.mine)), el('td', { class: 'n' }, r.ceiling), el('td', { class: 'n' }, r.cons_rank != null ? `#${r.cons_rank}` : '—'), el('td', { class: 'n' }, gapCell(r.gap)), el('td', {}, ...(r.words || []).filter(w => w !== 'Visited').map(wordTag))));
  if (!v.visited.length) vt.append(el('tr', {}, el('td', { colspan: '7' }, el('div', { class: 'empty' }, 'You named no visits this year.'))));
  s.append(vt); page.append(s);
}

function renderDraftDay(v) {
  renderRail(v.rail); const page = persPage(); drSecond('day');
  const reload = () => renderDraftDay(pyJSON(`SESSION.draft_view('draft_day')`));
  if (!v.live) {
    const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Draft Day'), el('div', { class: 'empty' }, v.note));
    if (v.last) { s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, `${v.last.year} Draft Results`, el('small', {}, `${v.last.rows.length} picks · ${v.last.trades} trades`))); const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Pick'), el('th', {}, 'Club'), el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Consensus'))); for (const r of v.last.rows) t.append(el('tr', { style: r.mine ? 'background:var(--sheet-2)' : '' }, el('td', {}, r.slot), el('td', {}, stripe(r.team.abbr, r.team.name)), el('td', { style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + r.pid; } }, r.name), el('td', {}, r.pos), el('td', { class: 'n' }, r.cons_rank ?? '—'))); s.append(t); }
    page.append(s); return;
  }
  const act = (name, extra) => { const r = pyJSON(`SESSION.draft_act(${JSON.stringify(name)}${extra ? ', ' + extra : ''})`); notify(r); if (r.done) { location.hash = '#draft/picks'; return; } reload(); };
  const cur = v.current;
  const left = el('section', { class: 'sheet c8' });
  // the clock
  left.append(el('div', { class: 'clockhead' }, crest(cur.team, 44), el('div', {}, el('div', { class: 'big' }, v.on_user ? 'You Are On the Clock' : `${cur.team.name} Is On the Clock`), el('div', { class: 'sub' }, `Round ${cur.round} · Pick ${cur.sel}` + (cur.needs && cur.needs.length ? ` · Needs ${cur.needs.join(', ')}` : ''))),
    el('div', { class: 'yours' }, v.mine_next.length ? el('div', {}, el('div', { class: 'big', style: 'font-size:20.5px' }, `You Pick ${v.mine_next[0].sel}${ord(v.mine_next[0].sel)}`), el('div', { class: 'sub' }, v.on_user ? 'Now' : v.picks_away === 1 ? 'One Pick Away' : v.picks_away != null ? `${['Two', 'Three', 'Four', 'Five', 'Six', 'Seven'][v.picks_away - 2] || v.picks_away} Picks Away` : '')) : el('div', { class: 'sub' }, 'No picks left'))));
  left.append(el('div', { class: 'ctrl2', style: 'padding:0 14px 10px' },
    el('button', { class: 'btn', disabled: v.on_user ? '' : null, onclick: () => act('sim_pick_one') }, 'Next Pick'),
    el('button', { class: 'btn go', disabled: v.on_user ? '' : null, onclick: () => act('sim_to_me') }, 'Sim to Your Pick'),
    el('button', { class: 'btn', disabled: v.on_user ? '' : null, 'data-tip': 'Sim to the end of this round, or to your pick if it comes first', onclick: () => act('sim_round') }, 'Sim Round'),
    el('button', { class: 'btn quiet', onclick: () => { if (confirm('Run the rest of the draft? Your picks go to the top of your board.')) act('sim_draft'); } }, 'Sim Draft'),
    el('span', { class: 'sep' }),
    el('button', { class: 'btn', disabled: v.on_user ? '' : null, 'data-tip': 'Ask a club ahead of you what it wants for its pick', onclick: () => { const q = v.clock.find(x => !x.mine && x.sel < (v.mine_next[0] ? v.mine_next[0].sel : Infinity)); if (!q) { notify({ ok: false, why: 'Nobody picks between now and your pick.' }); return; } const rd = pyJSON(`SESSION.draft_act('read_trade_up', target=${JSON.stringify(q.id)})`); if (!rd.ok) { notify(rd); return; } if (confirm(`${rd.line}\n\nSend ${rd.sends.map(x => x.replace(/^(\d+)-(\d+)-(\w+)$/, '$1 R$2 ($3)')).join(', ')} for pick ${rd.slot}?`)) act('trade_up', `target=${JSON.stringify(q.id)}, sends=${JSON.stringify(rd.sends)}`); } }, 'Trade Up'),
    el('button', { class: 'btn', disabled: v.on_user ? null : '', 'data-tip': 'Gather offers for this pick', onclick: () => { const r = pyJSON(`SESSION.draft_act('offers')`); notify(r); if (r.ok) { offersCache = r.offers; reload(); } } }, 'Trade Down')));
  // the picks around the clock
  const nx = el('div', { class: 'picksmade' });
  const recent = v.results.slice(0, 3).reverse();
  for (const r of recent) nx.append(el('div', { class: 'pk' }, el('span', { class: 'n' }, r.slot), crest(r.team, 30), el('div', { class: 'who' }, el('div', { class: 'nm' }, r.name), el('small', {}, `${r.pos}`)), el('span', {})));
  for (const q of v.clock) {
    const now = q.sel === cur.sel;
    nx.append(el('div', { class: 'pk' + (q.mine ? ' next' : '') + (now ? ' now' : '') }, el('span', { class: 'n' }, q.slot), crest(q.team, 30), el('div', { class: 'who' }, el('div', { class: 'nm' }, now ? 'On the Clock' : q.mine ? 'Your Pick' : '—'), el('small', {}, `${q.team.name}${q.needs && q.needs.length && !q.mine ? ' · Needs ' + q.needs.join(', ') : ''}`)), el('span', {})));
  }
  left.append(nx);
  // offers for your pick
  if (v.on_user && offersCache && offersCache.length) {
    for (const o of offersCache) left.append(el('div', { class: 'card', style: '--k:var(--live);margin:0 14px 10px' }, el('div', { class: 'h' }, el('div', { class: 'k' }, `Trade Offer · ${o.team.name} · Expires When You Pick`), el('div', { class: 's' }, `${o.team.name} offers ${o.summary.join(' and ')} for ${cur.slot}`)), el('div', { class: 'b' }, `They want a ${o.target_pos}. ${o.value >= 0 ? 'The value favors you' : 'You would be giving up value'} by about $${Math.abs(o.value).toFixed(1)}m in draft capital.`),
      el('div', { class: 'a' }, el('button', { class: 'btn go', onclick: () => { offersCache = null; act('accept_offer', `i=${o.i}`); } }, 'Accept'), el('button', { class: 'btn', onclick: () => { location.hash = '#personnel/trades'; } }, 'Counter'), el('button', { class: 'btn quiet', onclick: () => { offersCache = offersCache.filter(x => x.i !== o.i); reload(); } }, 'Decline'))));
  }
  page.append(left);
  const right = el('section', { class: 'sheet c4' }, el('h2', {}, 'Best Available', el('small', {}, 'By Your Board')));
  const bt = el('table', { class: 'tbl' }); bt.append(el('tr', {}, el('th', { class: 'n' }, '#'), el('th', {}, 'Player'), el('th', { class: 'n', 'data-tip': 'Where the league expects him to go' }, 'Proj.'), el('th', { class: 'n', 'data-tip': "Your scouts' read. Carries error; a visit tightens it" }, 'Est. Ovr')));
  for (const r of v.board.slice(0, 12)) bt.append(el('tr', { style: v.on_user ? 'cursor:pointer' : '', 'data-tip': v.on_user ? 'Click the row to draft him; the name opens his card' : null, onclick: e => { if (e.target.closest('.who')) return; if (v.on_user && confirm(`Draft ${r.name}, ${r.pos}, ${r.college} at ${cur.slot}?`)) act('pick', `pid=${JSON.stringify(r.pid)}`); } }, el('td', { class: 'n' }, r.board_no), el('td', {}, el('button', { class: 'who', onclick: e => { e.stopPropagation(); location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, surname(r.name), el('small', {}, `${r.pos} · ${r.college}${r.my_round && r.my_rank > 32 ? ' · Your Grade ' + r.my_round : ''}`)))), el('td', { class: 'n' }, r.proj_range), el('td', { class: 'n' }, ovrCell(r.mine))));
  right.append(bt);
  right.append(el('div', { class: 'read', style: 'margin:10px 12px' }, el('b', {}, 'Assistants: '), v.read || ''));
  if (v.on_user && v.default_pick) right.append(el('div', { class: 'pad', style: 'padding-top:0' }, el('button', { class: 'btn go', style: 'width:100%;justify-content:center', onclick: () => act('pick', `pid=${JSON.stringify(v.default_pick.pid)}`) }, `Draft ${v.default_pick.name}`, el('small', { style: 'margin-left:8px;font-weight:500' }, `${v.default_pick.pos} · ${v.default_pick.college} · Your Board #1`))));
  right.append(el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#draft/board' }, 'Your Board'), el('span', { class: 'count', 'data-tip': v.my_needs.join(', ') }, `Needs · ${v.my_needs.slice(0, 3).join(', ') || 'none'}`), el('button', { class: 'btn quiet', disabled: v.board.length ? null : '', onclick: () => { location.hash = '#club/player/' + v.board[0].pid; } }, 'Prospect Card')));
  page.append(right);
}
let offersCache = null;
const gdReveal = {};      // where each game's reveal stands, so leaving the page and coming back holds the place

let picksClub = 'mine', picksYear = null, picksQuery = '';
function renderPicks(v) {
  renderRail(v.rail); const page = persPage(); drSecond('picks');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Your Picks', el('small', {}, `${v.years.reduce((a, y) => a + y.picks.length, 0)} picks over ${v.years.length} drafts`)));
  const yrs = el('div', { class: 'years' });
  for (const y of v.years) {
    const box = el('div', { class: 'ybox' }, el('h4', {}, y.year === v.rail.year ? `${y.year} This Draft` : String(y.year)));
    for (const p of y.picks) box.append(el('div', { class: 'pkrow' }, el('span', { class: 'rd' }, `R${p.round}`), el('div', { class: 'nm' }, p.slot + (p.frm ? ` (From ${p.frm})` : ''), el('small', {}, p.note || ''))));
    for (const g of v.gone.filter(g => g.year === y.year)) box.append(el('div', { class: 'pkrow gone' }, el('span', { class: 'rd' }, `R${g.round}`), el('div', { class: 'nm' }, `${g.round}${ord(g.round)} · To ${g.holder.name}`, el('small', {}, g.note || ''))));
    yrs.append(box);
  }
  s.append(yrs);
  s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Draft Results', el('small', {}, 'every drafted player on record')));
  const tools = el('div', { class: 'tools' });
  const clubs = el('div', { class: 'chips' }); for (const [k, l] of [['mine', v.rail.club.name], ['all', 'All Clubs'], ['div', v.my_division]]) clubs.append(el('button', { class: 'chip', 'aria-pressed': String(picksClub === k), onclick: () => { picksClub = k; renderPicks(v); } }, l));
  const yrsChips = el('div', { class: 'chips' }); for (const y of v.result_years) yrsChips.append(el('button', { class: 'chip', 'aria-pressed': String(picksYear === y), onclick: () => { picksYear = picksYear === y ? null : y; renderPicks(v); } }, y));
  const search = el('input', { type: 'search', class: 'find', placeholder: 'Find a Player', value: picksQuery }); search.oninput = () => { picksQuery = search.value; drawR(); };
  tools.append(clubs, yrsChips, search); s.append(tools);
  const rt = el('table', { class: 'tbl' });
  const drawR = () => {
    rt.innerHTML = ''; rt.append(el('tr', {}, el('th', {}, 'Player'), el('th', { class: 'n' }, 'Year'), el('th', { class: 'n' }, 'Pick'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Ovr'), el('th', { class: 'n', 'data-tip': 'His rating the day he was drafted' }, 'Drafted At'), el('th', { class: 'n', 'data-tip': 'Where the league had him ranked' }, 'Consensus Was'), el('th', {}, 'Status')));
    const q = picksQuery.trim().toLowerCase();
    const rows = v.results.filter(r => (picksClub === 'all' || (picksClub === 'mine' && r.team && r.team.abbr === v.rail.club.abbr) || (picksClub === 'div' && r.division === v.my_division)) && (!picksYear || r.year === picksYear) && (!q || r.name.toLowerCase().includes(q)));
    for (const r of rows.slice(0, 200)) rt.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos} · ${r.college}${r.team ? ' · ' + r.team.abbr : ''}`)))), el('td', { class: 'n' }, r.year), el('td', { class: 'n' }, r.pick), el('td', {}, r.pos), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, r.drafted_at ?? '—'), el('td', { class: 'n' }, r.cons_was ?? '—'), el('td', {}, r.status)));
    if (!rows.length) rt.append(el('tr', {}, el('td', { colspan: '8' }, el('div', { class: 'empty' }, v.results.length ? 'Nobody matches.' : 'The first class is drafted in the spring.'))));
  };
  s.append(rt); drawR(); page.append(s);
}

// ---------------------------------------------------------------- Team page (another club at a glance)
function renderTeam(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'League'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'league'));
  secondRow(clubNav(v.club.abbr, false, null), `#league/team/${v.club.abbr}`);
  const left = el('section', { class: 'sheet c8' });
  left.append(el('div', { class: 'head', style: 'padding:14px' }, crest(v.club, 56), el('div', {}, el('div', { class: 'hname' }, `${v.club.name.toUpperCase()} ${v.club.nick}`), el('div', { class: 'hline' }, `${v.record} · ${v.place}`),
    el('div', { class: 'hfacts' }, el('div', {}, el('span', {}, 'Offense'), el('b', {}, v.ranks.offense ? `${v.ranks.offense}${ord(v.ranks.offense)}` : '—')), el('div', {}, el('span', {}, 'Defense'), el('b', {}, v.ranks.defense ? `${v.ranks.defense}${ord(v.ranks.defense)}` : '—')), el('div', {}, el('span', {}, 'Cap Space'), el('b', {}, `$${v.cap.space}m`)), el('div', {}, el('span', {}, 'Next Year'), el('b', {}, `$${v.cap.committed_next}m of $${v.cap.limit_next}m`)), el('div', {}, el('span', {}, 'Roster'), el('b', {}, `${v.roster_n} · PS ${v.ps_n}${v.ir_n ? ' · IR ' + v.ir_n : ''}`)))),
    el('div', { style: 'margin-left:auto' }, clubSelect(v.club.abbr, a => { const m = pyJSON('SESSION.club_list()').find(c => c.abbr === a); location.hash = m && m.mine ? '#club' : `#league/team/${a}`; }))));
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
  const right = el('section', { class: 'sheet c4' }, el('h2', {}, 'Trading Block', el('small', {}, v.needs.length ? `needs ${v.needs.join(', ')}` : '')));
  const bt = el('table', { class: 'tbl' }); bt.append(el('tr', {}, el('th', {}, 'Player'), el('th', { class: 'n' }, 'Ovr'), el('th', {}, '')));
  for (const p of v.block) bt.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + p.pid; } }, el('div', { class: 'no' }, p.pos), el('div', { class: 'nm' }, p.name, el('small', {}, `${p.why} · $${p.apy}m`)))), el('td', { class: 'n' }, ovrCell(p.ovr)), el('td', {}, v.mine ? '' : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:13px', 'data-tip': 'Open a trade for him', onclick: () => { tradeState = { other: v.club.abbr, a: [], b: [p.pid] }; location.hash = '#personnel/trades'; } }, 'Ask'))));
  if (!v.block.length) bt.append(el('tr', {}, el('td', { colspan: '3' }, el('div', { class: 'empty' }, 'Nobody they would move right now.'))));
  right.append(bt);
  right.append(el('div', { class: 'foot' }, el('a', { class: 'btn', href: `#league/team/${v.club.abbr}/roster` }, 'Roster'), el('a', { class: 'btn', href: `#league/team/${v.club.abbr}/depth` }, 'Depth Chart'), el('a', { class: 'btn', href: `#league/team/${v.club.abbr}/ps` }, 'Practice Squad'), v.mine ? '' : el('a', { class: 'btn quiet', href: '#personnel/trades', onclick: () => { tradeState = { other: v.club.abbr, a: [], b: [] }; } }, 'Trade')));
  page.append(right);
}

// ---------------------------------------------------------------- League
const LG = { standings: 'Standings', schedule: 'Schedule', transactions: 'Transactions', stats: 'Stats', awards: 'Awards', coaching: 'Coaching', almanac: 'Almanac' };
function lgSecond(cur) { secondRow(Object.entries(LG).map(([k, l]) => [l, '#league/' + k]), '#league/' + cur); $('#crumb').textContent = 'League'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'league')); }
const TAGCLS = { Trade: 'trade', Signing: 'sign', Release: 'cut', Draft: 'draft', Extension: 'contract', Waivers: 'wire', 'Call-Up': 'squad', 'Practice Squad': 'squad', 'Injured Reserve': 'wire', Retirement: 'retire', Fired: 'cut', Hired: 'staff', Staff: 'staff', 'Franchise Tag': 'tagg', Restructure: 'contract', 'Position Change': 'squad', 'Hall of Fame': 'hall', Season: 'season' };

function renderStandings(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('standings');
  const s = el('section', { class: 'sheet c8' }, el('h2', {}, 'Standings', el('small', {}, `Through Week ${v.week ?? '—'} · ${v.games_played} games played`)));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); for (const k of ['Divisions', 'Conference', 'League']) tabs.append(el('button', { 'aria-pressed': String(standingsView === k), onclick: () => { standingsView = k; renderStandings(v); } }, k)); s.append(tabs);
  const arrow = r => r.arrow > 0 ? el('span', { class: 'arr up' }, `▲${r.arrow}`) : r.arrow < 0 ? el('span', { class: 'arr dn' }, `▼${-r.arrow}`) : el('span', { class: 'arr' }, '–');
  const pd = r => el('td', { class: 'n', style: r.pd > 0 ? 'color:var(--ok)' : r.pd < 0 ? 'color:var(--danger)' : '' }, (r.pd > 0 ? '+' : '') + r.pd);
  if (standingsView === 'Conference') {
    for (const conf of ['AFC', 'NFC']) {
      const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, conf), el('th', { class: 'n' }, 'Seed'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', { class: 'n' }, 'T'), el('th', { class: 'n' }, 'Pct'), el('th', { class: 'n', 'data-tip': 'Point differential' }, 'PD'), el('th', { class: 'n', 'data-tip': 'Strength of victory' }, 'SOV'), el('th', { class: 'n', 'data-tip': 'Strength of schedule' }, 'SOS'), el('th', {}, 'Form')));
      for (const r of v.conferences[conf]) t.append(el('tr', { style: r.me ? 'background:var(--sheet-2)' : '' }, el('td', {}, clubLink(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.seed ? el('span', { class: 'seed ' + (r.seed === 1 ? 'bye' : 'in') + (r.me ? ' me' : '') }, r.seed) : ''), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', { class: 'n' }, r.t), el('td', { class: 'n' }, r.pct.toFixed(3).replace(/^0/, '')), pd(r), el('td', { class: 'n' }, r.sov != null ? r.sov.toFixed(3).replace(/^0/, '') : '—'), el('td', { class: 'n' }, r.sos != null ? r.sos.toFixed(3).replace(/^0/, '') : '—'), el('td', {}, formDots(r.form))));
      s.append(t);
    }
  } else if (standingsView === 'League') {
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', { class: 'n' }, '#'), el('th', {}, 'Club'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', { class: 'n' }, 'T'), el('th', { class: 'n' }, 'Pct'), el('th', { class: 'n' }, 'PF'), el('th', { class: 'n' }, 'PA'), el('th', { class: 'n' }, 'PD'), el('th', {}, 'Form')));
    v.league_rows.forEach((r, i) => t.append(el('tr', { style: r.me ? 'background:var(--sheet-2)' : '' }, el('td', { class: 'n' }, i + 1), el('td', {}, clubLink(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', { class: 'n' }, r.t), el('td', { class: 'n' }, r.pct.toFixed(3).replace(/^0/, '')), el('td', { class: 'n' }, r.pf), el('td', { class: 'n' }, r.pa), pd(r), el('td', {}, formDots(r.form)))));
    s.append(t);
  } else {
    const grid = el('div', { class: 'divgrid' });
    for (const d of v.divisions) {
      const box = el('div', { class: 'divbox' }, el('h4', {}, d.name)); const t = el('table', { class: 'tbl' });
      t.append(el('tr', {}, el('th', {}, 'Club'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', {}, 'Form'), el('th', { class: 'n', 'data-tip': 'Points for' }, 'PF'), el('th', { class: 'n', 'data-tip': 'Points against' }, 'PA'), el('th', { class: 'n', 'data-tip': 'Point differential' }, 'PD'), el('th', { class: 'n', 'data-tip': 'Record inside the division' }, 'Div'), el('th', { class: 'n', 'data-tip': 'Moved since last week' }, '')));
      for (const r of d.rows) t.append(el('tr', { style: r.me ? 'background:var(--sheet-2)' : '' }, el('td', {}, clubLink(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', {}, formDots(r.form)), el('td', { class: 'n' }, r.pf), el('td', { class: 'n' }, r.pa), pd(r), el('td', { class: 'n' }, r.div_rec), el('td', { class: 'n' }, arrow(r))));
      box.append(t); grid.append(box);
    }
    s.append(grid);
  }
  if (v.notes.length) s.append(el('div', { class: 'legend-line' }, 'Ties: ' + v.notes.join(' ')));
  page.append(s); page.append(pictureSheet(v));
}
let standingsView = 'Divisions';
function pictureSheet(v) {
  const r = el('section', { class: 'sheet c4' }, el('h2', {}, 'Playoff Picture', el('small', {}, 'seeds as of today')));
  for (const c of v.picture) {
    r.append(el('h4', { style: 'padding:8px 14px 0;font-size:15px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.06em' }, c.conf));
    const t = el('table', { class: 'tbl' });
    for (const x of c.seeds) t.append(el('tr', { style: x.me ? 'background:var(--sheet-2)' : '' }, el('td', { style: 'width:34px' }, el('span', { class: 'seed ' + (x.bye ? 'bye' : 'in') + (x.me ? ' me' : '') }, x.seed)), el('td', {}, clubLink(x.club.abbr, x.club.name)), el('td', { class: 'n' }, x.record), el('td', {}, el('small', { style: 'color:var(--ink-3)' }, x.bye ? 'Bye' : x.div_winner ? 'Div' : 'WC'))));
    for (const x of c.hunt) t.append(el('tr', { style: 'color:var(--ink-3)' + (x.me ? ';background:var(--sheet-2)' : '') }, el('td', {}, el('span', { class: 'seed bub' }, '·')), el('td', {}, clubLink(x.club.abbr, x.club.name)), el('td', { class: 'n' }, x.record), el('td', {}, el('small', {}, 'in the hunt'))));
    r.append(t);
  }
  r.append(el('div', { class: 'legend-line' }, 'Division winners seed one through four; the one seed has the bye. Ties break by the league rules.'));
  return r;
}

function renderSchedule(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('schedule');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Schedule', el('small', {}, `Week ${v.week}`)));
  s.append(el('div', { class: 'tabs', style: 'padding:8px 14px 0' }, el('button', { 'aria-pressed': 'true' }, 'League Schedule'), el('button', { 'aria-pressed': 'false', onclick: () => renderTeamSchedule(pyJSON(`SESSION.league_view('team_schedule')`)) }, 'Team Schedule')));
  const nav = el('div', { class: 'wknav' }, el('span', { class: 'lab' }, 'Week'));
  for (let w = 1; w <= v.weeks; w++) nav.append(el('button', { 'aria-pressed': String(w === v.week), onclick: () => renderSchedule(pyJSON(`SESSION.league_view('schedule', week=${w})`)) }, w));
  s.append(nav);
  const done = v.games.some(g => g.done);
  s.append(el('div', { class: 'h5', style: 'padding:8px 14px 0' }, `Week ${v.week} · ${done ? 'Results' : 'Upcoming'}`, el('span', {}, done ? 'Click your game for the box score' : '')));
  const grid = el('div', { class: 'games' });
  for (const g of v.games) {
    const tm = (c, rec, win, at) => el('div', { class: 'tm' + (g.done ? (win ? ' w' : ' l') : '') }, at ? el('small', {}, 'at') : '', clubLink(c.abbr, c.name), el('small', {}, rec));
    const card = el('div', { class: 'game' + (g.mine ? ' mine' : '') + (g.done ? ' done' : '') },
      tm(g.away, g.away_rec, g.winner === g.away.abbr, false), el('div', { class: 'sc' }, g.done ? String(g.ap) : ''),
      tm(g.home, g.home_rec, g.winner === g.home.abbr, true), el('div', { class: 'sc' }, g.done ? String(g.hp) : ''),
      el('div', { class: 'note' }, (g.note || (g.done ? 'Final' : 'Upcoming')) + (g.box ? ' · Box Score →' : '')));
    if (g.box) { card.onclick = () => { location.hash = `#gameday/${v.week}`; }; card.style.cursor = 'pointer'; card.setAttribute('data-tip', 'Open the box score'); }
    grid.append(card);
  }
  s.append(grid); page.append(s);
}

function renderTeamSchedule(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('schedule');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, `${v.team.name} · ${v.record}`, el('small', {}, `bye week ${v.byes.join(', ') || '—'}`)));
  const sel = el('select', { class: 'btn', style: 'width:auto' }); for (const c of v.clubs) sel.append(el('option', { value: c.abbr, selected: c.abbr === v.team.abbr ? '' : null }, c.name)); sel.onchange = () => renderTeamSchedule(pyJSON(`SESSION.league_view('team_schedule', team=${JSON.stringify(sel.value)})`));
  s.append(el('div', { class: 'tabs', style: 'padding:8px 14px 0;gap:10px;align-items:center' }, el('button', { 'aria-pressed': 'false', onclick: () => renderSchedule(pyJSON(`SESSION.league_view('schedule')`)) }, 'League Schedule'), el('button', { 'aria-pressed': 'true' }, 'Team Schedule'), sel));
  const t = el('table', { class: 'tbl teamsched' }); t.append(el('tr', {}, el('th', { class: 'n' }, 'Wk'), el('th', { class: 'l' }, 'Opponent'), el('th', {}, 'Record'), el('th', {}, 'Result'), el('th', { class: 'n' }, 'Score')));
  const rows = [...v.games.map(g => ({ week: g.week, g })), ...v.byes.map(b => ({ week: b, bye: true }))].sort((a, b) => a.week - b.week);
  for (const r of rows) {
    if (r.bye) { t.append(el('tr', { style: 'color:var(--ink-3)' }, el('td', { class: 'n' }, r.week), el('td', { class: 'l', colspan: '4' }, 'Bye'))); continue; }
    const g = r.g;
    t.append(el('tr', { style: g.done && g.result === 'W' ? '' : g.done ? 'color:var(--ink-2)' : 'color:var(--ink-3)' }, el('td', { class: 'n' }, g.week), el('td', { class: 'l' }, el('span', { style: 'display:inline-block;width:22px;color:var(--ink-3)' }, g.home ? 'vs' : 'at'), clubLink(g.opp.abbr, g.opp.name)), el('td', {}, g.opp_rec), el('td', {}, g.result ? el('span', { style: `font-family:var(--display);font-weight:900;color:${g.result === 'W' ? 'var(--ok)' : g.result === 'L' ? 'var(--danger)' : 'var(--ink-2)'}` }, g.result) : 'Upcoming'),
      el('td', { class: 'n' }, g.done ? (g.box ? el('a', { href: `#gameday/${g.week}`, class: 'score-link', 'data-tip': 'Open the box score' }, `${g.mine}–${g.theirs}`) : `${g.mine}–${g.theirs}`) : '')));
  }
  s.append(t); page.append(s);
}

let txGroup = 'All', txClub = 'all', txQuery = '', txShown = 60;
function renderTransactions(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('transactions');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Transactions', el('small', {}, 'the league record')));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0;flex-wrap:wrap' });
  for (const g of ['All', ...v.groups]) tabs.append(el('button', { 'aria-pressed': String(txGroup === g), onclick: () => { txGroup = g; txShown = 60; renderTransactions(v); } }, g));
  const clubs = el('div', { class: 'chips' }); for (const [k, label] of [['all', 'All Clubs'], ['mine', v.rail.club.name], ['div', v.my_division]]) clubs.append(el('button', { class: 'chip', 'aria-pressed': String(txClub === k), onclick: () => { txClub = k; txShown = 60; renderTransactions(v); } }, label));
  const search = el('input', { type: 'search', class: 'find', placeholder: 'Find a Player or Club', value: txQuery }); search.oninput = () => { txQuery = search.value; txShown = 60; draw(); };
  s.append(tabs, el('div', { class: 'tools' }, clubs, search));
  const list = el('div', {}); s.append(list);
  const draw = () => {
    list.innerHTML = ''; const q = txQuery.trim().toLowerCase();
    const rows = v.rows.filter(r => (txGroup === 'All' || r.group === txGroup) && (txClub === 'all' || (txClub === 'mine' && r.mine) || (txClub === 'div' && r.division === v.my_division)) && (!q || r.line.toLowerCase().includes(q)));
    for (const r of rows.slice(0, txShown)) {
      const when = r.week ? `Wk ${r.week}` : r.phase ? r.phase.charAt(0).toUpperCase() + r.phase.slice(1).replace('_', ' ') : String(r.year);
      const link = r.link === 'card' && r.pid ? el('a', { class: 'more', href: '#club/player/' + r.pid }, 'Card →') : r.link === 'trade' ? el('a', { class: 'more', href: '#personnel/trades' }, 'Trades →') : r.link === 'contract' && r.pid ? el('a', { class: 'more', href: '#club/player/' + r.pid }, 'Contract →') : r.link === 'carousel' ? el('a', { class: 'more', href: '#league/coaching' }, 'Carousel →') : el('span', {});
      list.append(el('div', { class: 'trow' + (r.mine ? ' mine' : '') }, el('time', {}, `${r.year} · ${when}`), el('span', { class: 'tag ' + r.group.toLowerCase() }, r.tag), el('span', { class: 'txt' }, r.team ? el('span', { class: 'stripe bar-only', style: `--c:${COLOR[r.team.abbr] || '#555'}` }, '') : '', ' ', r.line), link));
    }
    if (!rows.length) list.append(el('div', { class: 'empty' }, 'Nothing matches.'));
    if (rows.length > txShown) list.append(el('div', { class: 'foot' }, el('button', { class: 'btn quiet', onclick: () => { txShown += 60; draw(); } }, 'Older'), el('span', { class: 'count' }, `${Math.min(txShown, rows.length)} of ${rows.length}`)));
  };
  draw(); page.append(s);
}

let statsTab = 'Leaders';
function renderStats(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('stats');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Stats', el('small', {}, `Through Week ${v.week ?? '—'}`)));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); for (const k of ['Leaders', 'Passing', 'Rushing', 'Receiving', 'Defense', 'Blocking', 'Advanced', 'Team']) tabs.append(el('button', { 'aria-pressed': String(statsTab === k), onclick: () => { statsTab = k; renderStats(v); } }, k));
  const yrs = el('div', { class: 'chips', style: 'margin-left:auto' }); for (const y of v.years.slice().reverse()) yrs.append(el('button', { class: 'chip', 'aria-pressed': String(y === v.year), onclick: () => renderStats(pyJSON(`SESSION.league_view('stats', year=${y})`)) }, y)); yrs.append(el('a', { class: 'chip', href: '#league/almanac' }, 'Career'));
  tabs.append(yrs); s.append(tabs);
  const nm = r => el('div', { class: 'nm', style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + r.pid; } }, r.name, el('small', {}, `${r.pos} · ${r.team}`));
  if (statsTab === 'Leaders' || statsTab === 'Advanced') {
    const boxes = statsTab === 'Leaders' ? v.boxes : v.advanced;
    const grid = el('div', { class: 'leaders' });
    for (const b of boxes) { const box = el('div', { class: 'lbox' }, el('h4', {}, b.title, el('small', {}, b.unit || ''))); b.rows.slice(0, 5).forEach((r, i) => box.append(el('div', { class: 'lrow', style: r.mine ? 'background:var(--sheet-2)' : '' }, el('span', { class: 'r' }, i + 1), nm(r), el('span', { class: 'v' }, r.v)))); grid.append(box); }
    if (!boxes.length) grid.append(el('div', { class: 'empty' }, 'No games played this season yet.'));
    s.append(grid);
  } else if (statsTab === 'Team') {
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Club'), el('th', { class: 'n' }, 'PF/G'), el('th', { class: 'n' }, 'PA/G'), el('th', { class: 'n' }, 'Yds/G'), el('th', { class: 'n' }, 'Pass/G'), el('th', { class: 'n' }, 'Rush/G'), el('th', { class: 'n' }, 'EPA/Play'), el('th', { class: 'n' }, 'Sacks'), el('th', { class: 'n' }, 'INT')));
    for (const r of v.team) t.append(el('tr', { style: r.mine ? 'background:var(--sheet-2)' : '' }, el('td', {}, clubLink(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.pf), el('td', { class: 'n' }, r.pa), el('td', { class: 'n' }, r.ypg), el('td', { class: 'n' }, r.pyds), el('td', { class: 'n' }, r.ryds), el('td', { class: 'n', style: r.epa > 0 ? 'color:var(--ok)' : r.epa < 0 ? 'color:var(--danger)' : '' }, (r.epa > 0 ? '+' : '') + r.epa.toFixed(2)), el('td', { class: 'n' }, r.sacks), el('td', { class: 'n' }, r.ints)));
    s.append(t);
  } else {
    const tb = v.tables[statsTab.toLowerCase()];
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', { class: 'n' }, '#'), el('th', {}, 'Player'), el('th', {}, 'Club'), ...tb.cols.map(c => el('th', { class: 'n' }, c))));
    tb.rows.forEach((r, i) => t.append(el('tr', { style: r.mine ? 'background:var(--sheet-2)' : '' }, el('td', { class: 'n' }, i + 1), el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name))), el('td', {}, r.team ? stripe(r.team) : ''), ...r.row.map(x => el('td', { class: 'n' }, String(x))))));
    if (!tb.rows.length) t.append(el('tr', {}, el('td', { colspan: String(3 + tb.cols.length) }, el('div', { class: 'empty' }, 'No games played this season yet.'))));
    s.append(t);
  }
  page.append(s);
}

function renderAwards(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('awards');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Awards', el('small', {}, v.pending ? `${v.pending} Awards Are Voted After Week 18` : String(v.year))));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); for (const y of v.years.slice().reverse()) tabs.append(el('button', { 'aria-pressed': String(y === v.year), onclick: () => renderAwards(pyJSON(`SESSION.league_view('awards', year=${y})`)) }, y)); s.append(tabs);
  if (v.note && !v.rows.length) { s.append(el('div', { class: 'empty' }, v.note)); page.append(s); return; }
  const grid = el('div', { class: 'awards' });
  for (const r of v.rows) grid.append(el('div', { class: 'aw' + (r.mine ? ' mine' : ''), style: r.mine ? 'border-color:var(--club)' : '' }, el('div', { class: 'code' }, r.code || ''), el('div', { class: 'a' }, r.award), el('div', { class: 'nm', style: r.pid ? 'cursor:pointer' : '', onclick: () => { if (r.pid) location.hash = '#club/player/' + r.pid; } }, r.name), el('div', { class: 'tm' }, r.team ? clubLink(r.team.abbr, r.team.name) : ''), el('div', { class: 'ln' }, `${r.pos ? r.pos + ' · ' : ''}${r.line || ''}`)));
  s.append(grid);
  for (const [title, list] of [['All-Pro First Team', v.first], ['All-Pro Second Team', v.second]]) {
    if (!list || !list.length) continue;
    s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, title));
    const two = el('div', { class: 'two' });
    for (const side of ['Offense', 'Defense']) {
      const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, side), el('th', {}, 'Player'), el('th', {}, 'Club')));
      const isOff = p => ['QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT', 'K', 'P'].includes(p);
      for (const x of list.filter(x => isOff(x.pos) === (side === 'Offense'))) t.append(el('tr', { style: x.mine ? 'background:var(--sheet-2)' : '' }, el('td', {}, x.pos), el('td', {}, el('span', { style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + x.pid; } }, x.name)), el('td', {}, x.team ? clubLink(x.team.abbr, x.team.name) : '')));
      two.append(t);
    }
    s.append(two);
  }
  page.append(s);
}

let coachTab = 'seats';
function renderCoaching(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('coaching');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Coaching', el('small', {}, v.note || '')));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); for (const [k, l] of [['seats', 'The Seats'], ['pool', 'The Pool'], ['carousel', 'This Offseason']]) tabs.append(el('button', { 'aria-pressed': String(coachTab === k), onclick: () => { coachTab = k; renderCoaching(v); } }, l)); s.append(tabs);
  if (coachTab === 'seats') {
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Club'), el('th', {}, 'Coach'), el('th', {}, 'Seat'), el('th', { class: 'n' }, 'Prestige')));
    for (const r of v.seats) t.append(el('tr', { style: r.mine ? 'background:var(--sheet-2)' : '' }, el('td', {}, clubLink(r.club.abbr, r.club.name)), el('td', {}, el('div', { class: 'nm' }, r.coach, el('small', { style: 'display:block;color:var(--ink-3)' }, `${r.tenure + 1}${ord(r.tenure + 1)} year · ${r.record}${r.note ? ' · ' + r.note : ''}`))), el('td', {}, el('span', { class: 'seat ' + r.seat.toLowerCase().replace(' ', '') }, r.seat)), el('td', { class: 'n' }, r.prestige ?? '—')));
    s.append(t);
  } else if (coachTab === 'pool') {
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Coach'), el('th', {}, 'Background'), el('th', { class: 'n' }, 'Prestige'), el('th', { class: 'n' }, 'Age')));
    for (const c of v.pool) t.append(el('tr', {}, el('td', {}, c.name), el('td', {}, c.background || ''), el('td', { class: 'n' }, c.prestige ?? '—'), el('td', { class: 'n' }, c.age ?? '—')));
    if (!v.pool.length) t.append(el('tr', {}, el('td', { colspan: '4' }, el('div', { class: 'empty' }, 'The pool fills as the season ends.'))));
    s.append(t);
  } else {
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Year'), el('th', {}, 'Club'), el('th', {}, 'Hired'), el('th', {}, 'Background'), el('th', { class: 'n' }, 'After')));
    for (const c of v.carousel) t.append(el('tr', {}, el('td', {}, c.year), el('td', {}, clubLink(c.club.abbr, c.club.name)), el('td', {}, c.hired), el('td', {}, c.background || ''), el('td', { class: 'n' }, c.win_pct != null ? `.${String(Math.round(c.win_pct * 1000)).padStart(3, '0')}` : '')));
    if (!v.carousel.length) t.append(el('tr', {}, el('td', { colspan: '5' }, el('div', { class: 'empty' }, 'No changes this offseason.'))));
    s.append(t);
  }
  page.append(s);
}

let almTab = 'records';
function renderAlmanac(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('almanac');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Almanac', el('small', {}, v.note || `${v.seasons.length} season${v.seasons.length === 1 ? '' : 's'} on record`)));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); for (const [k, l] of [['records', 'Records'], ['careers', 'Career Leaders'], ['hall', 'Hall of Fame'], ['champions', 'Champions'], ['ledger', 'Coaching Ledger']]) tabs.append(el('button', { 'aria-pressed': String(almTab === k), onclick: () => { almTab = k; renderAlmanac(v); } }, l)); s.append(tabs);
  if (almTab === 'records') {
    const two = el('div', { class: 'two' });
    const rs = el('div', {}, el('div', { class: 'h5' }, 'Single Season', el('span', {}, 'Since 2026'))); const rc = el('div', {}, el('div', { class: 'h5' }, 'Career', el('span', {}, 'Active in Gold')));
    for (const r of v.records) {
      if (r.season) rs.append(el('div', { class: 'lrow' }, el('div', { class: 'nm' }, r.stat, el('small', {}, `${r.season.name} · ${r.season.team} · ${r.season.year}`)), el('span', { class: 'v' }, r.season.v)));
      if (r.career) rc.append(el('div', { class: 'lrow' }, el('div', { class: 'nm', style: r.career.active ? 'color:var(--club-2)' : '' }, r.stat, el('small', {}, `${r.career.name} · ${r.career.team}`)), el('span', { class: 'v' }, r.career.v)));
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
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Club'), el('th', {}, 'Coach'), el('th', { class: 'n' }, 'From'), el('th', { class: 'n' }, 'To'), el('th', {}, 'Record')));
    for (const x of v.ledger) t.append(el('tr', {}, el('td', {}, clubLink(x.club.abbr, x.club.name)), el('td', {}, x.name), el('td', { class: 'n' }, x.frm ?? '—'), el('td', { class: 'n' }, x.current ? 'now' : (x.to ?? '—')), el('td', {}, x.record || '')));
    if (!v.ledger.length) t.append(el('tr', {}, el('td', { colspan: '5' }, el('div', { class: 'empty' }, 'The ledger fills as coaches come and go.'))));
    s.append(t);
  }
  page.append(s);
}

// ---------------------------------------------------------------- Game Plan
const GPN = { week: 'This Week', report: 'Opponent Report' };
function gpSecond(cur) { secondRow(Object.entries(GPN).map(([k, l]) => [l, '#gameplan/' + k]), '#gameplan/' + cur); $('#crumb').textContent = 'Game Plan'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'gameplan')); }
const pct = x => Math.round(x * 100);

function renderThisWeek(v) {
  renderRail(v.rail); const page = persPage(); gpSecond('week');
  const reload = () => renderThisWeek(pyJSON(`SESSION.plan_view('this_week')`));
  const s = el('section', { class: 'sheet c12' });
  if (v.off) { s.append(el('h2', {}, 'This Week'), el('div', { class: 'empty' }, v.note)); page.append(s); return; }
  s.append(el('h2', {}, `Week ${v.week} ${v.away ? 'at' : 'vs'} ${v.opp.name}`));
  // suggestions
  const sug = el('div', { class: 'sugs' });
  sug.append(el('div', { class: 'h5' }, "Assistants' Suggestions"));
  for (const x of v.suggestions) sug.append(el('div', { class: 'sug-row' + (x.taken ? ' on' : '') }, el('div', { class: 't' }, x.text, el('small', {}, `${x.target ? x.target + ' · ' : ''}${x.taken ? 'Accepted · ' : ''}${x.why}`)), el('div', { class: 'a', style: 'display:flex;gap:4px' }, x.taken ? el('button', { class: 'btn quiet', onclick: () => { notify(pyJSON(`SESSION.plan_act('untake', i=${x.i})`)); reload(); } }, 'Undo') : el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.plan_act('take', i=${x.i})`)); reload(); } }, 'Accept'), x.taken ? '' : el('button', { class: 'btn quiet', 'data-tip': 'Hide it for now', onclick: e => e.currentTarget.closest('.sug-row').remove() }, 'Skip'))));
  if (!v.suggestions.length) sug.append(el('div', { class: 'empty' }, 'The report has nothing to add this week; the plan is the coordinators\' own.'));
  else sug.append(el('div', { style: 'display:flex;gap:6px;padding:8px 0 0' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON('SESSION.plan_take_all()')); reload(); } }, 'Accept All'), el('span', { class: 'count', style: 'align-self:center' }, '')));
  s.append(sug);
  // leans
  const plan = el('div', { class: 'plan' });
  const side = (title, leans) => {
    const d = el('div', {}, el('div', { class: 'h5' }, title));
    for (const ln of leans) {
      const lo = Math.max(0, ln.min), hi = Math.min(1, ln.max), span = Math.max(0.02, hi - lo);
      const pos = x => `${Math.round((Math.min(hi, Math.max(lo, x)) - lo) / span * 100)}%`;
      const moved = Math.abs(ln.value - ln.base) > 1e-6;
      const track = el('div', { class: 'track' }, el('div', { class: 'range', style: 'left:0;right:0' }), el('div', { class: 'tick', style: `left:${pos(ln.base)}` }));
      if (ln.ghost != null) track.append(el('div', { class: 'knob ghost', style: `left:${pos(ln.ghost)}`, 'data-tip': `The assistants would put it at ${ln.ghost_word}` }));
      track.append(el('div', { class: 'knob' + (moved ? ' sug' : ''), style: `left:${pos(ln.value)}` }));
      const rng = el('input', { type: 'range', min: String(Math.round(lo * 1000)), max: String(Math.round(hi * 1000)), value: String(Math.round(ln.value * 1000)) }); rng.onchange = () => { pyJSON(`SESSION.plan_act('set_lean', key=${JSON.stringify(ln.key)}, value=${+rng.value / 1000})`); reload(); }; track.append(rng);
      d.append(el('div', { class: 'lean' }, el('div', { class: 'l' }, ln.label, el('small', {}, ln.desc)), track, el('div', { class: 'v' + (moved ? ' sug' : ''), 'data-tip': moved ? `${ln.value > ln.base ? '+' : ''}${Math.round((ln.value - ln.base) * 100)} from your identity` : 'At your identity' }, ln.word)));
    }
    return d;
  };
  const off = side('Offense', v.leans.filter(l => l.side === 'offense')), deff = side('Defense', v.leans.filter(l => l.side === 'defense'));
  // depth mix as three numbers
  const dm = el('div', { class: 'lean', style: 'grid-template-columns:130px 1fr' }, el('div', { class: 'l' }, 'Depth of Target', el('small', {}, 'short · medium · deep')));
  const inputs = v.depth.value.map((x, i) => el('input', { type: 'number', min: '5', max: '90', value: String(pct(x)), style: 'width:56px;font-family:var(--mono);font-size:14.5px;background:var(--board);color:var(--ink);border:1px solid var(--rule-2);padding:4px 6px' }));
  const dmrow = el('div', { style: 'display:flex;gap:6px;align-items:center;font-size:13px;color:var(--ink-3)' }); v.depth.labels.forEach((l, i) => dmrow.append(el('span', {}, l), inputs[i], el('span', {}, '%'))); dmrow.append(el('button', { class: 'btn', style: 'padding:3px 8px;font-size:14px', onclick: () => { pyJSON(`SESSION.plan_act('set_depth', short=${+inputs[0].value}, medium=${+inputs[1].value}, deep=${+inputs[2].value})`); reload(); } }, 'Set'), el('span', {}, `base ${v.depth.base.map(pct).join(' · ')}`));
  dm.append(dmrow); off.append(dm);
  plan.append(off, deff); s.append(plan);
  // decisions
  s.append(el('div', { class: 'h5', style: 'padding:10px 14px 6px' }, 'Game-Week Decisions'));
  const dec = el('div', { class: 'decide' });
  const prot = el('div', { class: 'dcard' }, el('div', { class: 'k' }, 'Protection'), el('div', { class: 's' }, v.protection.options.find(o => o.key === v.protection.value)?.word || v.protection.value)); const po = el('div', { class: 'opts' }); for (const o of v.protection.options) po.append(el('button', { class: 'btn chip' + (o.key === v.protection.value ? ' go' : ''), onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='protection', value=${JSON.stringify(o.key === v.protection.base ? '' : o.key)})`); reload(); } }, o.word)); prot.append(po); dec.append(prot);
  const shadowWord = v.travel ? (v.travel_target ? `${v.my_cb1 ? v.my_cb1.name : 'CB1'} on ${v.travel_target.name}` : `${v.my_cb1 ? v.my_cb1.name : 'CB1'} follows their best receiver`) : 'Corners stay by side';
  const tr = el('div', { class: 'dcard' }, el('div', { class: 'k' }, 'Coverage · Shadow Their WR1?'), el('div', { class: 's' }, shadowWord));
  const tro = el('div', { class: 'opts' }, el('button', { class: 'btn chip' + (!v.travel ? ' go' : ''), onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='travel_target', value='')`); pyJSON(`SESSION.plan_act('set_decision', key='travel', value=False)`); reload(); } }, 'No Shadow'));
  for (const w of v.their_wrs) tro.append(el('button', { class: 'btn chip' + (v.travel && v.travel_target && v.travel_target.pid === w.pid ? ' go' : ''), 'data-tip': `${v.my_cb1 ? v.my_cb1.name : 'Your best corner'} follows him all game`, onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='travel_target', value=${JSON.stringify(w.pid)})`); reload(); } }, `${v.my_cb1 ? v.my_cb1.name : 'CB1'} on ${surname(w.name)} · ${w.ovr}`));
  tr.append(tro); dec.append(tr);
  const br = el('div', { class: 'dcard' }, el('div', { class: 'k' }, 'Coverage · Bracket a Star?'), el('div', { class: 's' }, v.bracket ? `Bracket ${surname(v.bracket.name)}` : (v.wr_out && v.wr_out.length ? `${v.wr_out[0]} Is Out · None` : 'None'))); const bo = el('div', { class: 'opts' }, el('button', { class: 'btn chip' + (!v.bracket ? ' go' : ''), onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='bracket', value='')`); reload(); } }, 'None')); for (const w of v.their_wrs) bo.append(el('button', { class: 'btn chip' + (v.bracket && v.bracket.pid === w.pid ? ' go' : ''), onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='bracket', value=${JSON.stringify(w.pid)})`); reload(); } }, `${w.name} · ${w.ovr}`)); br.append(bo); dec.append(br);
  s.append(dec);
  s.append(el('div', { class: 'foot' }, el('button', { class: 'btn go', 'data-tip': 'The plan you leave here is the plan the game reads; this confirms it', onclick: () => { notify({ ok: true, line: 'Saved. Sunday reads this plan.' }); } }, 'Save Plan for Sunday'), el('a', { class: 'btn', href: '#gameplan/report' }, 'Opponent Report'), el('button', { class: 'btn quiet', onclick: () => { notify(pyJSON(`SESSION.plan_act('reset')`)); reload(); } }, 'Reset to Identity'), el('span', { class: 'count', style: 'margin-left:auto' }, v.forecast && v.forecast.text ? v.forecast.text : '')));
  page.append(s);
}

function renderReport(v) {
  renderRail(v.rail); const page = persPage(); gpSecond('report');
  const s = el('section', { class: 'sheet c12' });
  if (v.off) { s.append(el('h2', {}, 'Opponent Report'), el('div', { class: 'empty' }, v.note)); page.append(s); return; }
  s.append(el('h2', {}, `Opponent Report · ${v.opp.name}`, el('small', {}, `Week ${v.week} · ${v.away ? 'Away' : 'Home'} · ${v.record}` + (v.coach && v.coach.name ? ` · ${v.coach.name}, prestige ${v.coach.prestige}` : ''))));
  // their tendencies against the league
  s.append(el('div', { class: 'h5', style: 'padding:10px 14px 6px' }, 'Their Tendencies', el('span', {}, v.tendencies ? `${v.tendencies.games} games in · the tick is the league` : 'nothing on film yet')));
  const tg = el('div', { class: 'tendgrid' });
  const T = [['pass_rate', 'Pass Rate'], ['pa_rate', 'Play Action'], ['deep', 'Deep Shots'], ['two_high', 'Two-High'], ['blitz', 'Blitz'], ['man', 'Man Coverage'], ['fourth_go', 'Fourth-Down Go'], ['motion', 'Motion']];
  for (const [k, lab] of T) { const tv = v.tendencies ? v.tendencies[k] : null; const lg = v.league_tend ? v.league_tend[k] : null; tg.append(el('div', { class: 'tend', 'data-tip': `${v.opp.abbr} ${tv ?? '—'}% · NFL ${lg ?? '—'}%` }, el('div', { class: 'l' }, lab), el('div', { class: 'bar' }, el('i', { style: `width:${tv ?? 0}%` }), lg != null ? el('em', { style: `left:${lg}%` }) : ''), el('div', { class: 'v' }, tv != null ? `${tv}%` : '—'))); }
  s.append(tg);
  // unit rankings, both clubs
  const two = el('div', { class: 'two' });
  const ut = el('div', {}, el('div', { class: 'h5' }, 'Unit Rankings', el('span', {}, `${v.rail.club.abbr} · ${v.opp.abbr}`)));
  const rk = r => el('span', { class: 'rk ' + (r == null ? '' : r <= 8 ? 'good' : r >= 24 ? 'bad' : 'mid-rk'), style: 'font-size:17px' }, r == null ? '—' : `${r}${ord(r)}`);
  for (const r of v.unit_table) ut.append(el('div', { class: 'side-row' }, el('span', { class: 'lab' }, r.label), rk(r.mine), el('span', { class: 'mid' }), rk(r.theirs)));
  const men = el('div', {}, el('div', { class: 'h5' }, 'Players Who Matter')); for (const p of v.stars) men.append(el('div', { class: 'plate', style: 'margin-bottom:4px;cursor:pointer', onclick: () => { location.hash = '#club/player/' + p.pid; } }, el('div', { class: 'no' }, p.pos), el('div', { class: 'nm' }, p.name, el('small', {}, p.pos)), el('div', { class: 'ov' }, p.ovr)));
  if (v.injured && v.injured.length) { men.append(el('div', { class: 'h5', style: 'margin-top:10px' }, 'Their Injuries')); for (const x of v.injured) men.append(el('div', { style: 'font-size:15px;color:var(--ink-2);padding:2px 0' }, typeof x === 'string' ? x : `${x.name} (${x.pos})${x.back ? ' · out to week ' + x.back : ' · out'}`)); }
  two.append(ut, men); s.append(two);
  // when each side has the ball, as on the Portal
  if (v.panels) {
    const P = v.panels; const grid = el('div', { class: 'two' });
    const panel = (title, rows, extra, leftHead, rightHead) => {
      const d = el('div', {}, el('div', { class: 'h5' }, title));
      const box = el('div', { class: 'sides' }, el('div', { class: 'side-row head' }, el('span', {}), el('span', {}, leftHead), el('span', {}), el('span', {}, rightHead)));
      for (const r of rows) box.append(el('div', { class: 'side-row' }, el('span', { class: 'lab' }, r.label), rk(r.mine), el('span', { class: 'mid' }, 'vs'), rk(r.theirs)));
      (extra || []).forEach((t, i) => box.append(el('div', { class: 'side-row' + (i === 0 ? ' sep' : '') }, el('span', { class: 'lab' }, t.label, t.sub ? el('em', {}, t.sub) : ''), el('span', { class: 'rk', style: 'font-size:17px' }, t.left), el('span', { class: 'mid' }, 'vs'), el('span', { class: 'rk', style: 'font-size:17px' }, t.right))));
      d.append(box); return d;
    };
    grid.append(panel(`When ${v.rail.club.name} Has the Ball`, P.ours, P.ours_extra, `${v.rail.club.abbr} Offense`, `${v.opp.abbr} Defense`), panel(`When ${v.opp.name} Has the Ball`, P.theirs, P.theirs_extra, `${v.opp.abbr} Offense`, `${v.rail.club.abbr} Defense`));
    s.append(grid);
  }
  // what we would do
  s.append(el('div', { class: 'h5', style: 'padding:10px 14px 6px' }, 'What We Would Do', el('span', {}, 'act on This Week')));
  const cards = el('div', { class: 'cards' });
  for (const x of v.suggestions) cards.append(el('div', { class: 'card', style: `--k:${x.side === 'offense' ? 'var(--ok)' : 'var(--live)'};opacity:${x.taken ? '.75' : '1'}` }, el('div', { class: 'h' }, el('div', { class: 'k' }, x.side.charAt(0).toUpperCase() + x.side.slice(1) + (x.taken ? ' · accepted' : '')), el('div', { class: 's' }, x.text)), el('div', { class: 'b' }, x.why),
    el('div', { class: 'b', style: 'margin-top:6px' }, el('span', { style: 'font-size:12.5px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.04em' }, 'Plan Change '), el('span', { style: 'font-family:var(--mono);font-size:14px' }, x.change || '—')),
    el('div', { class: 'a' }, x.taken ? el('button', { class: 'btn quiet', onclick: () => { notify(pyJSON(`SESSION.plan_act('untake', i=${x.i})`)); renderReport(pyJSON(`SESSION.plan_view('report')`)); } }, 'Undo') : el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.plan_act('take', i=${x.i})`)); renderReport(pyJSON(`SESSION.plan_view('report')`)); } }, 'Accept'), x.taken ? '' : el('button', { class: 'btn quiet', onclick: e => e.currentTarget.closest('.card').remove() }, 'Skip'))));
  if (!v.suggestions.length) cards.append(el('div', { class: 'empty' }, 'Nothing to add this week.'));
  s.append(cards, el('div', { class: 'foot' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON('SESSION.plan_take_all()')); location.hash = '#gameplan/week'; } }, "Accept All and Open This Week's Plan"), el('a', { class: 'btn', href: '#gameplan/week' }, "Back to This Week's Plan")));
  page.append(s);
}

// ---------------------------------------------------------------- flow
function refresh() { view = pyJSON('SESSION.portal()'); renderRail(view.rail); renderPortal(view); }

async function advance() {
  try { await advanceInner(); }
  catch (e) {
    // whatever failed, the GM sees it and can send it on: the message, and where in the engine it happened
    console.error(e); const msg = String(e && e.message || e); const tail = msg.split('\n').filter(l => l.trim()).slice(-6).join('\n');
    $('#advance').disabled = false; busy('The advance failed; see the notice.'); setTimeout(() => busy(null), 6000);
    notify({ ok: false, why: 'The advance failed. Copy this and send it: ' + tail.slice(0, 600) });
    try { const box = el('div', { class: 'sheet', style: 'position:fixed;left:16px;right:16px;bottom:16px;z-index:999;padding:12px 16px;max-height:40vh;overflow:auto;border-color:var(--danger)' }, el('b', {}, 'The advance failed. Copy this text and send it:'), el('pre', { style: 'white-space:pre-wrap;font-size:12px;margin:8px 0 0' }, msg.slice(-1500)), el('button', { class: 'btn', style: 'margin-top:8px', onclick: e => e.currentTarget.parentNode.remove() }, 'Close')); document.body.append(box); } catch (_) {}
  }
}

async function advanceInner() {
  // a block stops the click: a roster over 53 or under 46 sends you to fix it; a decision opens it
  const blocks = pyJSON('SESSION.blocking()');
  if (blocks.length) { const b = blocks[0]; notify({ ok: false, why: `Blocked: ${b.subject}. ${b.kind === 'roster' ? 'Fix the roster first.' : 'Answer it (or decline) to advance.'}` }); busy(`Blocked: ${b.subject}`); setTimeout(() => busy(null), 4000); renderRail(pyJSON('SESSION.portal()').rail); if (b.go) location.hash = b.go; else if (b.id != null) location.hash = `#portal/inbox/${b.id}`; return; }
  const adv = $('#advance'); adv.disabled = true; const wasSim = /^Sim Week/.test(view.rail.advance.title); busy(view.rail.advance.title + '…');
  await new Promise(r => setTimeout(r, 30));
  let r = null;
  try { r = pyJSON('SESSION.advance()'); busy(`${r.done} done.`); setTimeout(() => busy(null), 1200); }
  catch (e) { adv.disabled = false; throw e; }
  adv.disabled = false;
  if (r && r.done === 'Blocked') { notify({ ok: false, why: r.why }); }
  else if (r && r.done === 'Cutdown') { location.hash = '#personnel/waivers'; renderWire(pyJSON(`SESSION.personnel('waivers')`)); }
  else if (r && r.done === 'Camp') { location.hash = '#portal'; refresh(); }
  else if (r && /^Week \d+ played$/.test(r.done)) { if (location.hash === '#gameday') renderGameDay(pyJSON('SESSION.gameday_view()')); else location.hash = '#gameday'; }
  else if (r && /^Week \d+$/.test(r.done)) { if (location.hash === '' || location.hash.startsWith('#portal')) refresh(); else if (location.hash === '#gameday') renderGameDay(pyJSON('SESSION.gameday_view()')); else location.hash = '#portal'; } else if (r && /on the clock/.test(r.done)) { location.hash = '#draft/day'; renderDraftDay(pyJSON(`SESSION.draft_view('draft_day')`)); } else refresh();
  saveGame();
}

// ---------------------------------------------------------------- start
(async function main() {
  const pick = $('#pick');
  for (const c of CLUBS) pick.append(el('button', { style: `background:${COLOR[c]}${c === 'PIT' || c === 'NO' ? ';color:#111' : ''}`, 'aria-pressed': String(c === team), onclick: e => { team = c; pick.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); } }, c));
  try { await bootEngine(); } catch (e) { say('boot failed: ' + e); return; }
  $('#start').disabled = false;
  const saved = await loadSave(); if (saved) $('#resume').hidden = false;
  $('#start').onclick = async () => { $('#start').disabled = true; await newGame(team); $('#boot').remove(); refresh(); saveGame(); };
  $('#resume').onclick = async () => { $('#resume').disabled = true; say('loading your save…', 90); await new Promise(r => setTimeout(r, 30)); py.globals.set('_SAVE', saved); py.runPython(`SESSION = S.Session.load(_SAVE)`); $('#boot').remove(); refresh(); };
  $('#advance').onclick = advance;
  $('#save').onclick = saveGame;
  $('#back').onclick = () => history.back();
  const fwd = document.querySelector('.hist button[aria-label="Forward"]'); if (fwd) { fwd.disabled = false; fwd.onclick = () => history.forward(); }
  window.addEventListener('hashchange', () => { if (location.hash.startsWith('#portal/inbox/')) openMessage(+location.hash.split('/').pop()); else if (location.hash === '#portal/inbox') { view = pyJSON('SESSION.portal_full()'); renderInbox(view); } else if (location.hash.startsWith('#portal') || location.hash === '') refresh(); else if (location.hash.startsWith('#gameday')) { const wk = location.hash.split('/')[1]; renderGameDay(pyJSON(wk ? `SESSION.gameday_view(week=${+wk})` : 'SESSION.gameday_view()')); } else if (location.hash.startsWith('#club/player/')) renderCard(pyJSON(`SESSION.club_card(${JSON.stringify(location.hash.split('/').pop())})`)); else if (location.hash.startsWith('#club/depth')) renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(depthPkg)})`)); else if (location.hash.startsWith('#club')) { if (location.hash.startsWith('#club/progression')) renderProgression(pyJSON('SESSION.progression()')); else { clubTab = location.hash.startsWith('#club/ps') ? 'ps' : location.hash.startsWith('#club/ir') ? 'ir' : 'active'; renderRoster(pyJSON('SESSION.club_roster()')); } } else if (location.hash.startsWith('#gameplan')) { const sub = location.hash.split('/')[1] || 'week'; if (sub === 'report') renderReport(pyJSON(`SESSION.plan_view('report')`)); else renderThisWeek(pyJSON(`SESSION.plan_view('this_week')`)); } else if (location.hash.startsWith('#league/team/')) { const parts = location.hash.split('/'); const abbr = parts[2]; const sub = parts[3] || ''; if (sub === 'roster' || sub === 'ps') { clubTab = sub === 'ps' ? 'ps' : 'active'; renderRoster(pyJSON(`SESSION.club_roster(${JSON.stringify(abbr)})`)); } else if (sub === 'depth') renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(depthPkg)}, ${JSON.stringify(abbr)})`)); else renderTeam(pyJSON(`SESSION.team_page(${JSON.stringify(abbr)})`)); }
    else if (location.hash.startsWith('#league')) { const sub = location.hash.split('/')[1] || 'standings'; const fn = { standings: renderStandings, schedule: renderSchedule, transactions: renderTransactions, stats: renderStats, awards: renderAwards, coaching: renderCoaching, almanac: renderAlmanac }[sub] || renderStandings; fn(pyJSON(`SESSION.league_view(${JSON.stringify(sub in LG ? sub : 'standings')})`)); } else if (location.hash.startsWith('#draft')) { const sub = location.hash.split('/')[1] || 'board'; if (sub === 'day') renderDraftDay(pyJSON(`SESSION.draft_view('draft_day')`)); else if (sub === 'spring') renderSpring(pyJSON(`SESSION.draft_view('spring')`)); else if (sub === 'picks') renderPicks(pyJSON(`SESSION.draft_view('picks')`)); else renderBoard(pyJSON(`SESSION.draft_view('board')`)); } else if (location.hash.startsWith('#frontoffice')) { const sub = location.hash.split('/')[1] || 'owner'; if (sub === 'identity') { idPreview = null; renderIdentity(pyJSON(`SESSION.frontoffice('identity')`)); } else if (sub === 'staff') renderStaff(pyJSON(`SESSION.frontoffice('staff')`)); else if (sub === 'cap') renderCap(pyJSON(`SESSION.frontoffice('cap')`)); else renderOwner(pyJSON(`SESSION.frontoffice('owner')`)); } else if (location.hash.startsWith('#personnel')) { const sub = location.hash.split('/')[1] || 'trades'; if (sub === 'fa') renderFA(pyJSON(`SESSION.personnel('free_agency')`)); else if (sub === 'wire') renderWire(pyJSON(`SESSION.personnel('waivers')`)); else if (sub === 'extensions') renderExtensions(pyJSON(`SESSION.personnel('extensions')`)); else { if (!tradeState.keep) { tradeState.a = []; tradeState.b = []; } tradeState.keep = false; renderTrades(pyJSON(`SESSION.personnel('trades'${tradeState.other ? ', other=' + JSON.stringify(tradeState.other) : ''})`)); } } else { const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = '1fr'; page.append(el('section', { class: 'sheet' }, el('h2', {}, location.hash.slice(1).split('/')[0].replace(/^\w/, c => c.toUpperCase())), el('div', { class: 'empty' }, 'This page is next to be wired.'), el('div', { class: 'foot' }, el('button', { class: 'btn', onclick: () => { location.hash = '#portal'; } }, 'Back to Portal')))); } });
})();
