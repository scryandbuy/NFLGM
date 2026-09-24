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
  await py.loadPackage(['numpy', 'pandas']);
  const manifest = await (await fetch(ENGINE + 'manifest.json')).json();
  const files = [...manifest.modules.map(m => m + '.py'), ...manifest.data];
  let n = 0;
  for (const f of files) {
    const r = await fetch(ENGINE + f);
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
  if (r.blocking.length) { adv.classList.add('blocked'); $('#adv-title').textContent = `${r.blocking.length} Decision${r.blocking.length > 1 ? 's' : ''}`; $('#adv-sub').textContent = `Then ${r.advance.title}`; }
  else { adv.classList.remove('blocked'); $('#adv-title').textContent = r.advance.title; $('#adv-sub').textContent = r.advance.sub || ''; }
}

// ---------------------------------------------------------------- the Portal
function sheet(title, small, ...body) { return el('section', { class: 'sheet' }, el('h2', {}, title, small ? el('small', {}, small) : null), ...body); }
function stripe(abbr, text) { return el('span', { class: 'stripe', style: `--c:${COLOR[abbr] || '#555'}` }, text ?? abbr); }
function formDots(f, big = false) { return el('div', { class: 'form' + (big ? ' big-form' : '') }, ...f.map(x => el('i', { class: x }))); }

function renderPortal(v) {
  const page = $('#page'); page.hidden = false; page.innerHTML = '';
  page.className = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Portal';
  $('#second').innerHTML = `<a aria-current="page">Overview</a><a href="#portal/inbox">Inbox <em>${v.inbox.total}</em></a><a>Calendar</a><a>News</a><a>Owner</a>`;

  // the matchup
  const m = v.matchup;
  const match = el('section', { class: 'sheet c12' });
  if (!m) match.append(el('h2', {}, 'Offseason'), el('div', { class: 'empty' }, 'The season is over. The Advance button walks the offseason one step at a time.'));
  else if (m.bye) match.append(el('h2', {}, `Week ${m.week}`, el('small', {}, 'Bye Week')), el('div', { class: 'empty' }, 'No game this week.'));
  else {
    match.append(el('h2', {}, `Week ${m.week} ${m.away ? 'at' : 'vs'} ${esc(m.them.club.name)}`, el('small', {}, m.forecast || '')));
    const side = (c, right) => el('div', { class: 'side', style: right ? 'flex-direction:row-reverse;text-align:right' : '' }, el('div', { class: 'cr', style: `background:${c.club.color}` }, c.club.abbr), el('div', {}, el('div', { class: 'nm' }, c.club.nick), el('div', { class: 'rec' }, `${c.record} · ${c.place}`)));
    const bug = el('div', { class: 'bug', style: 'grid-template-columns:auto 1fr auto;padding:12px 12px 4px' },
      side(m.me, false),
      el('div', { class: 'mid' }, el('div', { class: 'lbl' }, 'Win Probability'), el('div', { class: 'wp' }, `${m.wp}%`),
        el('div', { class: 'wpbar' }, el('i', { style: `width:${m.wp}%;background:${m.me.club.color}` }), el('i', { style: `width:${100 - m.wp}%;background:${m.them.club.color}` }))),
      side(m.them, true));
    const facts = el('div', { class: 'facts2' },
      el('div', {}, el('span', {}, 'Their Coach'), el('b', {}, `${esc(m.them.coach)}${m.them.prestige ? ' · Prestige ' + m.them.prestige : ''}`)),
      el('div', {}, el('span', {}, 'Your Injuries'), el('b', {}, m.injuries.me.join(' · ') || 'None')),
      el('div', {}, el('span', {}, 'Their Injuries'), el('b', {}, m.injuries.them.join(' · ') || 'None')));
    const formRow = el('div', { class: 'form-row' }, el('div', {}, el('div', { class: 'lbl' }, `${m.me.club.nick} Last Five`), formDots(m.form.me, true)), el('div', {}, el('div', { class: 'lbl' }, `${m.them.club.nick} Last Five`), formDots(m.form.them, true)));
    const left = el('div', { class: 'm-side' }, bug, facts, formRow);
    const right = el('div', { class: 'm-right' },
      el('div', { class: 'mh' }, 'Assistants Say', el('a', { class: 'more', href: '#gameplan/report' }, 'Full Opponent Report →')),
      el('div', { class: 'say', style: 'padding:0 12px 10px' }, m.say),
      el('div', { class: 'men-row', style: 'border-top:1px solid var(--rule)' }, ...m.watch.map(w => el('div', {}, el('div', { class: 'lbl' }, 'Players to Watch'), el('div', { class: 'man' }, el('div', { class: 'no', style: `background:${m.them.club.color};color:#fff` }, w.pos), el('div', { class: 'nm' }, w.name), el('div', { class: 'ovr' }, w.ovr))))));
    match.append(el('div', { class: 'match', style: 'grid-template-columns:1fr 1.1fr' }, left, right));
    match.append(el('div', { class: 'foot' }, el('a', { class: 'btn go', href: '#gameplan' }, 'Set Game Plan'), el('a', { class: 'btn', href: '#gameplan/report' }, 'Opponent Report'), el('a', { class: 'btn', href: '#club/depth' }, 'Depth Chart')));
  }
  page.append(match);

  // on your desk
  const desk = el('section', { class: 'sheet c12' }, el('h2', {}, 'On Your Desk', el('small', {}, `${v.desk.length} Waiting`)));
  if (!v.desk.length) desk.append(el('div', { class: 'empty' }, 'Nothing needs you before the next advance.'));
  else desk.append(el('div', { class: 'cards' }, ...v.desk.map(c => el('div', { class: 'card', style: `--k:${c.kind === 'Trade' ? 'var(--live)' : 'var(--decide)'}` },
    el('div', { class: 'h' }, el('div', { class: 'k' }, c.kind), el('div', { class: 's' }, c.subject)),
    el('div', { class: 'b' }, c.body),
    el('div', { class: 'a' }, el('button', { class: 'btn', onclick: () => location.hash = `#portal/inbox/${c.id}` }, 'Open'))))));
  page.append(desk);

  // inbox
  const inbox = el('section', { class: 'sheet c12' }, el('h2', {}, 'Inbox', el('small', {}, `${v.inbox.total} Messages · ${v.inbox.decide} Need a Decision`)));
  const filt = el('div', { class: 'filt' }, el('button', { 'aria-pressed': 'true' }, 'All ', el('em', {}, v.inbox.total)), el('button', { 'aria-pressed': 'false' }, 'Decide ', el('em', {}, v.inbox.decide)), el('button', { 'aria-pressed': 'false' }, 'Unread ', el('em', {}, v.inbox.unread)));
  inbox.append(filt);
  let lastDay = null;
  for (const r of v.inbox.rows) {
    const day = `${r.year} · Week ${r.week}`;
    if (day !== lastDay) { inbox.append(el('div', { class: 'dayh' }, day)); lastDay = day; }
    inbox.append(el('button', { class: 'row' + (r.unread ? ' unread' : ''), onclick: () => openMessage(r.id) }, el('div', {}, el('div', { class: 't' }, r.subject), el('div', { class: 'f' }, r.body)), el('span', { class: 'tag ' + tagClass(r.tag) }, r.tag), el('time', {}, r.sender || '')));
  }
  if (!v.inbox.rows.length) inbox.append(el('div', { class: 'empty' }, 'Nothing yet.'));
  page.append(inbox);

  // cap, room, front office
  const capG = v.cap.by_group; const total = Object.values(capG).reduce((a, b) => a + b, 0) + v.cap.dead;
  const colors = { QB: '#c8102e', OL: '#e0b400', WR: '#4cc9f0', DL: '#3fb37f', DB: '#8791a0', LB: '#b6bec9', TE: '#5a6472', RB: '#a0603a', ST: '#3a3f47' };
  const stack = el('div', { class: 'stack', style: 'margin-top:10px' }, ...Object.entries(capG).filter(([, x]) => x > 0).map(([g, x]) => el('i', { style: `width:${100 * x / v.cap.cap}%;background:${colors[g]}`, 'data-tip': `${g}: $${x.toFixed(1)}m` }, el('span', {}, g))), el('i', { style: `width:${100 * v.cap.dead / v.cap.cap}%;background:#3a1216`, 'data-tip': `Dead Money: $${v.cap.dead.toFixed(1)}m` }));
  const capS = sheet('Cap', `${v.cap.years[0].year} · $${v.cap.cap}m Limit`, el('div', { class: 'pad' }, el('div', { class: 'big' }, v.cap.space, el('span', { class: 'muted', style: 'font-size:14px;font-family:var(--text);font-weight:500' }, ' Space')), stack,
    el('div', { class: 'bars', style: 'padding:10px 0 0;grid-template-columns:96px 1fr 70px' }, ...v.cap.years.flatMap(y => [el('div', { class: 'l' }, y.year), el('div', { class: 't' }, el('i', { style: `width:${Math.min(100, 100 * y.committed / y.cap)}%;background:var(--ink-2)` })), el('div', { class: 'v' }, `$${y.committed}/${y.cap}`)]))),
    el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#frontoffice/cap' }, 'Cap'), el('a', { class: 'btn', href: '#personnel/ext' }, 'Extensions')));
  capS.classList.add('c4'); page.append(capS);

  const rc = v.room.counts; const n = Object.values(rc).reduce((a, b) => a + b, 0) || 1;
  const roomS = sheet('The Room', `${n} Players · Morale`, el('div', { class: 'pad' },
    el('div', { class: 'bar' }, el('i', { style: `width:${100 * rc.Unhappy / n}%;background:var(--danger)` }), el('i', { style: `width:${100 * rc.Unsettled / n}%;background:var(--decide)` }), el('i', { style: `width:${100 * rc.Content / n}%;background:var(--rule-hi)` }), el('i', { style: `width:${100 * rc.Happy / n}%;background:var(--ok)` })),
    el('div', { class: 'leg' }, el('span', {}, el('i', { style: 'background:var(--danger)' }), `Unhappy ${rc.Unhappy}`), el('span', {}, el('i', { style: 'background:var(--decide)' }), `Unsettled ${rc.Unsettled}`), el('span', {}, el('i', { style: 'background:var(--rule-hi)' }), `Content ${rc.Content}`), el('span', {}, el('i', { style: 'background:var(--ok)' }), `Happy ${rc.Happy}`))),
    el('div', { class: 'plates', style: 'grid-template-columns:1fr;padding-top:2px' }, ...v.room.watch.map(p => el('button', { class: 'man', onclick: () => location.hash = `#club/player/${p.pid}` }, el('div', { class: 'no' }, p.no || p.pos), el('div', { class: 'nm' }, p.short, el('small', {}, p.note)), el('div', { class: 'ovr' }, p.ovr), el('i', { class: 'pin bad' })))),
    el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#club' }, 'Roster'), el('a', { class: 'btn', href: '#club/depth' }, 'Depth Chart')));
  roomS.classList.add('c4'); page.append(roomS);

  const fo = v.front_office;
  const foS = sheet('Front Office', 'Owner · You', el('div', { class: 'kv', style: 'padding:10px 12px' }, el('span', {}, 'Owner Mood'), el('span', { class: 'big', style: 'font-size:26px' }, fo.owner_mood), el('span', {}, 'Your Job'), el('span', {}, fo.job), el('span', {}, 'Staff Budget'), el('span', {}, fo.staff_budget || '—'), el('span', {}, 'Scouting'), el('span', {}, `${fo.scouting_rank}${ord(fo.scouting_rank)} of 32`)),
    el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#frontoffice' }, 'Owner'), el('a', { class: 'btn', href: '#frontoffice/staff' }, 'Staff'), el('a', { class: 'btn quiet', href: '#frontoffice/ident' }, 'Identity')));
  foS.classList.add('c4'); page.append(foS);

  // standings and season
  const st = v.standings;
  const table = el('table', {}, el('tr', {}, el('th', {}, ''), el('th', {}, 'Club'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', {}, 'Form'), el('th', { class: 'n' }, 'PF'), el('th', { class: 'n' }, 'PA'), el('th', { class: 'n' }, 'PD')),
    ...st.rows.map(r => el('tr', { class: r.me ? 'me' : '' }, el('td', {}, ''), el('td', {}, stripe(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', {}, formDots(r.form)), el('td', { class: 'n' }, r.pf), el('td', { class: 'n' }, r.pa), el('td', { class: 'n' }, (r.pd > 0 ? '+' : '') + r.pd))));
  const stS = sheet(st.division, '', table, el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#league' }, 'Full Standings')));
  stS.classList.add('c6'); page.append(stS);

  const strip = el('div', { class: 'strip' }, ...v.season.games.map(g => g.bye ? el('div', { class: 'wk bye' }, '—', el('small', {}, 'bye')) : el('div', { class: 'wk' + (g.result ? ' ' + g.result.toLowerCase() : '') + (view.rail.advance.title === `Play Week ${g.week}` ? ' now' : ''), 'data-tip': g.score ? `${g.home ? 'vs' : 'at'} ${g.opp} · ${g.score}` : null }, g.result || g.week, el('small', {}, `${g.home ? '' : '@'}${g.opp}`))));
  const seS = sheet('The Season', view.rail.record, strip, el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#league/sched' }, 'Schedule'), el('a', { class: 'btn', href: '#league/stats' }, 'Stats')));
  seS.classList.add('c6'); page.append(seS);
}

function tagClass(t) { return ({ Trade: 'trade', Contract: 'contract', Wire: 'wire', Squad: 'squad', Game: 'game', Scouting: 'scout', 'Locker Room': 'room', Assistants: 'assist', Owner: 'owner', Staff: 'owner' })[t] || ''; }
function ord(n) { return n === 1 ? 'st' : n === 2 ? 'nd' : n === 3 ? 'rd' : 'th'; }

function openMessage(id) {
  py.runPython(`import inbox as IB\nfor _m in IB._box(SESSION.L):\n    if _m['id'] == ${id} and _m['status'] == 'unread': _m['status'] = 'read'`);
  const m = pyJSON(`next(_m for _m in __import__('inbox')._box(SESSION.L) if _m['id'] == ${id})`);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = '1fr';
  page.append(el('section', { class: 'sheet' }, el('h2', {}, m.subject, el('small', {}, `${m.sender || ''} · ${m.year} Week ${m.week}`)), el('div', { class: 'pad', style: 'max-width:70ch;line-height:1.5;color:var(--ink-2)' }, m.body), el('div', { class: 'foot' }, el('button', { class: 'btn', onclick: () => refresh() }, 'Back to Portal'))));
}


// ---------------------------------------------------------------- Game Day
function renderGameDay(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Game Day';
  $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'gameday'));
  $('#second').innerHTML = '';
  if (v.empty) { page.append(el('section', { class: 'sheet c12' }, el('h2', {}, 'Game Day'), el('div', { class: 'empty' }, v.line))); return; }
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
  // the big bug
  const me = g.me_home ? g.home : g.away, them = g.me_home ? g.away : g.home;
  const myScore = g.me_home ? g.hs : g.as_, theirScore = g.me_home ? g.as_ : g.hs;
  const won = myScore > theirScore, tie = myScore === theirScore;
  const rec = r => `${r[0]}–${r[1]}`;
  top.append(el('div', { class: 'bigbug' },
    el('div', { class: 'side' }, el('div', { class: 'cr', style: `background:${g.away.color}` }, g.away.abbr), el('div', {}, el('div', { class: 'nm' }, g.away.nick), el('div', { class: 'rec' }, rec(g.away_rec))), el('div', { class: 'score', style: 'margin-left:auto' }, g.as_)),
    el('div', { class: 'mid' }, el('div', { class: 'q' }, 'Final' + (g.ot ? ' · Overtime' : '')), el('div', { class: 'dd' }, tie ? 'A tie' : (won ? `${me.name} wins` : `${them.name} wins`)), el('div', { class: 'q', style: 'font-size:11px;color:var(--ink-3);margin-top:6px' }, `Week ${v.week}`)),
    el('div', { class: 'side', style: 'flex-direction:row-reverse;text-align:right' }, el('div', { class: 'cr', style: `background:${g.home.color}` }, g.home.abbr), el('div', {}, el('div', { class: 'nm' }, g.home.nick), el('div', { class: 'rec' }, rec(g.home_rec))), el('div', { class: 'score', style: 'margin-right:auto' }, g.hs))));
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
  let shown = 1;
  const body = el('div', { class: 'ticker' });
  const filt = { mode: 'all' };
  const draw = () => {
    body.innerHTML = '';
    g.drives.slice(0, shown).forEach(d => {
      body.append(el('div', { class: 'drive' }, `Drive ${d.n} · ${d.off} · Q${d.quarter} · ${d.plays_n} play${d.plays_n === 1 ? '' : 's'}, ${Math.round(d.yards)} yard${Math.round(d.yards) === 1 ? '' : 's'}` + (d.result ? ` · ${String(d.result).toLowerCase()}` : '') + ` · ${d.score}`));
      for (const p of d.plays) {
        if (!p.text) continue;
        if (filt.mode === 'key' && !['score', 'turnover', 'loss'].includes(p.kind) && !(p.type === 'complete' && /for (\d\d) yards/.test(p.text) && +p.text.match(/for (\d\d) yards/)[1] >= 15)) continue;
        if (filt.mode === 'score' && p.kind !== 'score') continue;
        const line = el('div', { class: 'pl ' + p.kind }); if (p.head) line.append(el('span', { class: 'dn' }, p.head), '  '); line.append(p.text); body.append(line);
      }
    });
    tick.querySelector('h2 small').textContent = shown >= g.drives.length ? 'Final' : `Through Drive ${shown} of ${g.drives.length}`;
    body.scrollTop = body.scrollHeight;
  };
  const ctrl = el('div', { class: 'ctrl2' },
    el('button', { class: 'btn go', onclick: () => { shown = Math.min(g.drives.length, shown + 1); draw(); } }, 'Next Drive'),
    el('button', { class: 'btn', onclick: () => { const q = g.drives[Math.min(shown, g.drives.length) - 1].quarter; while (shown < g.drives.length && g.drives[shown].quarter === q) shown++; shown = Math.min(g.drives.length, shown + 1); draw(); } }, 'Next Quarter'),
    el('button', { class: 'btn', onclick: () => { shown = g.drives.length; draw(); } }, 'Finish Game'),
    el('span', { class: 'sep' }),
    (() => { const t = el('div', { class: 'tabs' }); ['all', 'key', 'score'].forEach(m => t.append(el('button', { 'aria-pressed': String(m === 'all'), onclick: e => { filt.mode = m; t.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); draw(); } }, { all: 'Every Play', key: 'Key Plays', score: 'Scoring' }[m]))); return t; })());
  tick.append(el('h2', {}, 'Play by Play', el('small', {}, '')), ctrl, body);
  page.append(tick);

  // drive chart and box score
  const right = el('section', { class: 'sheet c4' });
  right.append(el('h2', {}, 'Drive Chart'));
  const fh = 14 * g.drives.length + 10; const fsvg = mk('svg', { viewBox: `0 0 720 ${fh}`, class: 'field' });
  fsvg.append(mk('rect', { x: 0, y: 0, width: 720, height: fh, fill: '#1f252c' }), mk('rect', { x: 0, y: 0, width: 60, height: fh, fill: '#3a1216' }), mk('rect', { x: 660, y: 0, width: 60, height: fh, fill: '#3a2a10' }));
  [180, 360, 540].forEach(x => fsvg.append(mk('line', { x1: x, y1: 0, x2: x, y2: fh, stroke: x === 360 ? '#8791a0' : '#3a424c' })));
  g.drives.forEach((d, i) => {
    // the drive's club drives toward the far end zone: home left-to-right, away right-to-left
    const dirHome = d.off === g.home.abbr; const x = v => 60 + 6 * v; const sx = dirHome ? x(d.start) : x(100 - d.start), ex = dirHome ? x(d.end) : x(100 - d.end);
    const y = 8 + 14 * i; const col = d.off === g.home.abbr ? g.home.color : g.away.color;
    fsvg.append(mk('line', { x1: sx, y1: y, x2: ex, y2: y, stroke: col, 'stroke-width': 6, 'stroke-linecap': 'round' }));
    const r = String(d.result || '');
    if (/Touchdown/.test(r)) fsvg.append(mk('circle', { cx: ex, cy: y, r: 5, fill: '#ffb612' }));
    else if (/Field goal/.test(r)) fsvg.append(mk('rect', { x: ex - 5, y: y - 6, width: 10, height: 12, fill: '#4cc9f0' }));
    else if (/Interception|Fumble|Turnover|downs/i.test(r)) fsvg.append(mk('circle', { cx: ex, cy: y, r: 5, fill: '#e5484d' }));
    else fsvg.append(mk('circle', { cx: ex, cy: y, r: 3.5, fill: '#3a424c' }));
  });
  right.append(el('div', { class: 'pad', style: 'padding-top:8px' }, fsvg,
    el('div', { style: 'padding:6px 0 0;display:flex;gap:12px;font-size:11.5px;color:var(--ink-2);flex-wrap:wrap' }, stripe(g.home.abbr), stripe(g.away.abbr), el('span', {}, el('i', { style: 'display:inline-block;width:9px;height:9px;background:#ffb612;border-radius:50%;margin-right:4px' }), 'TD'), el('span', {}, el('i', { style: 'display:inline-block;width:9px;height:9px;background:#4cc9f0;margin-right:4px' }), 'FG'), el('span', {}, el('i', { style: 'display:inline-block;width:9px;height:9px;background:#e5484d;border-radius:50%;margin-right:4px' }), 'Turnover'))));
  right.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Box Score'));
  const box = el('table', { class: 'box' });
  const th = (...c) => el('tr', {}, ...c.map((x, i) => el('th', {}, x)));
  box.append(th('Passing', 'C/A', 'Yds', 'TD', 'INT')); g.box.passing.forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.ca), el('td', {}, r.yds), el('td', {}, r.td), el('td', {}, r.int_))));
  box.append(th('Rushing', 'Att', 'Yds', 'TD', '')); g.box.rushing.forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.att), el('td', {}, r.yds), el('td', {}, r.td), el('td', {}, ''))));
  box.append(th('Receiving', 'Tgt', 'Rec', 'Yds', 'TD')); g.box.receiving.forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.tgt), el('td', {}, r.rec), el('td', {}, r.yds), el('td', {}, r.td))));
  box.append(th('Defense', 'Tkl', 'Sk', 'INT', 'PD')); g.box.defense.forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.tkl), el('td', {}, r.sk), el('td', {}, r.int_), el('td', {}, r.pd))));
  right.append(box);
  page.append(right);
  draw();
}

// ---------------------------------------------------------------- flow
function refresh() { view = pyJSON('SESSION.portal()'); renderRail(view.rail); renderPortal(view); }

async function advance() {
  const adv = $('#advance'); adv.disabled = true; busy(view.rail.advance.title + '…');
  await new Promise(r => setTimeout(r, 30));
  let r = null;
  try { r = pyJSON('SESSION.advance()'); busy(`${r.done} done.`); setTimeout(() => busy(null), 1200); }
  catch (e) { console.error(e); busy('Something broke: ' + String(e).slice(0, 120)); }
  adv.disabled = false;
  if (r && /^Week \d+$/.test(r.done)) { location.hash = '#gameday'; renderGameDay(pyJSON('SESSION.gameday_view()')); } else refresh();
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
  $('#back').onclick = () => refresh();
  window.addEventListener('hashchange', () => { if (location.hash.startsWith('#portal/inbox/')) openMessage(+location.hash.split('/').pop()); else if (location.hash.startsWith('#portal') || location.hash === '') refresh(); else if (location.hash.startsWith('#gameday')) renderGameDay(pyJSON('SESSION.gameday_view()')); else { const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = '1fr'; page.append(el('section', { class: 'sheet' }, el('h2', {}, location.hash.slice(1).split('/')[0].replace(/^\w/, c => c.toUpperCase())), el('div', { class: 'empty' }, 'This page is next to be wired.'), el('div', { class: 'foot' }, el('button', { class: 'btn', onclick: () => { location.hash = '#portal'; } }, 'Back to Portal')))); } });
})();
