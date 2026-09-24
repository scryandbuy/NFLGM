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
  $('#second').innerHTML = `<a aria-current="page" href="#portal">Overview</a><a href="#portal/inbox">Inbox <em>${v.inbox.total}</em></a><a href="#league/schedule">Calendar</a><a href="#league/transactions">News</a><a href="#frontoffice/owner">Owner</a>`;

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

  // when we have the ball, when they do; what we would do
  if (m && !m.bye && m.panels) {
    const P = m.panels;
    const rkCell = r => el('span', { class: 'rk ' + (r == null ? '' : r <= 8 ? 'good' : r >= 24 ? 'bad' : 'mid-rk') }, r == null ? '—' : ord(r));
    const panel = (title, rows, tend, leftHead, rightHead) => {
      const s = el('section', { class: 'sheet c6' }, el('h2', {}, title));
      const box = el('div', { class: 'sides' }, el('div', { class: 'side-row head' }, el('span', {}), el('span', {}, leftHead), el('span', {}), el('span', {}, rightHead)));
      for (const r of rows) box.append(el('div', { class: 'side-row' }, el('span', { class: 'lab' }, r.label), rkCell(r.mine), el('span', { class: 'mid' }, 'vs'), rkCell(r.theirs)));
      tend.forEach((t, i) => box.append(el('div', { class: 'side-row' + (i === 0 ? ' sep' : '') }, el('span', { class: 'lab' }, t.label, el('em', {}, t.unit)), el('span', { class: 'rk', style: 'font-size:16px' }, t.v == null ? '—' : `${t.v}%`), el('span', { class: 'mid' }), el('span', {}))));
      s.append(box); return s;
    };
    page.append(panel(`When ${m.me.club.nick} Have the Ball`, P.ours, P.our_tend, `${m.me.club.abbr} Offense`, `${m.them.club.abbr} Defense`));
    page.append(panel(`When ${m.them.club.nick} Have the Ball`, P.theirs, P.their_tend, `${m.them.club.abbr} Offense`, `${m.me.club.abbr} Defense`));
    const wwd = el('section', { class: 'sheet c12' }, el('h2', {}, 'What We Would Do', el('small', {}, P.suggestions.length ? `${P.taken.length} of ${P.suggestions.length} taken` : 'the assistants have nothing to add this week')));
    if (P.suggestions.length) {
      const cards = el('div', { class: 'cards', style: 'grid-template-columns:repeat(3,1fr)' });
      for (const sg of P.suggestions) {
        const on = P.taken.includes(sg.i);
        cards.append(el('div', { class: 'card', style: `--k:${sg.side === 'Offense' ? 'var(--ok)' : 'var(--live)'};opacity:${on ? '.75' : '1'}` },
          el('div', { class: 'h' }, el('div', { class: 'k' }, sg.side + (on ? ' · taken' : '')), el('div', { class: 's' }, sg.text)), el('div', { class: 'b' }, sg.why),
          el('div', { class: 'a' }, on ? el('button', { class: 'btn quiet', onclick: () => { pyJSON(`SESSION.plan_act('untake', i=${sg.i})`); refresh(); } }, 'Put Back') : el('button', { class: 'btn go', onclick: () => { pyJSON(`SESSION.plan_act('take', i=${sg.i})`); refresh(); } }, 'Take'), el('button', { class: 'btn quiet', onclick: e => e.currentTarget.closest('.card').remove() }, 'Skip'))));
      }
      wwd.append(cards, el('div', { class: 'foot' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON('SESSION.plan_take_all()')); location.hash = '#gameplan/week'; } }, 'Accept All and Open Game Plan'), el('a', { class: 'btn', href: '#gameplan/week' }, 'Open Game Plan'), el('a', { class: 'btn quiet', href: '#gameplan/report' }, 'Full Opponent Report')));
    }
    page.append(wwd);
    if (m.series && m.series.length) {
      const sh = el('section', { class: 'sheet c12' }, el('h2', {}, 'Series This Season'));
      for (const g of m.series) sh.append(el('div', { class: 'pad', style: 'font-size:13.5px' }, `Week ${g.week}: ${g.away} ${g.ap} at ${g.home} ${g.hp}`));
      page.append(sh);
    }
  }

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
  const list = el('div', { class: inboxDense ? 'inbox-list dense' : 'inbox-list' });
  const drawInbox = () => {
    list.innerHTML = ''; let lastDay = null, n = 0;
    for (const r of v.inbox.rows) {
      if (inboxFilter === 'decide' && !r.decide) continue;
      if (inboxFilter === 'unread' && !r.unread) continue;
      n++;
      const day = `${r.year} · Week ${r.week}`;
      if (day !== lastDay) { list.append(el('div', { class: 'dayh' }, day)); lastDay = day; }
      list.append(el('button', { class: 'row' + (r.unread ? ' unread' : ''), onclick: () => openMessage(r.id) }, el('div', {}, el('div', { class: 't' }, r.subject), inboxDense ? '' : el('div', { class: 'f' }, r.body)), el('span', { class: 'tag ' + tagClass(r.tag) }, r.tag)));
    }
    if (!n) list.append(el('div', { class: 'empty' }, inboxFilter === 'all' ? 'Nothing yet.' : inboxFilter === 'decide' ? 'Nothing waiting on a decision.' : 'All read.'));
  };
  const filt = el('div', { class: 'filt' });
  for (const [k, label, count] of [['all', 'All', v.inbox.total], ['decide', 'Decide', v.inbox.decide], ['unread', 'Unread', v.inbox.unread]])
    filt.append(el('button', { 'aria-pressed': String(inboxFilter === k), onclick: e => { inboxFilter = k; filt.querySelectorAll('button[data-f]').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); drawInbox(); }, 'data-f': k }, label + ' ', el('em', {}, count)));
  filt.append(el('span', { class: 'sep' }),
    el('button', { onclick: e => { inboxDense = !inboxDense; list.classList.toggle('dense', inboxDense); e.currentTarget.textContent = inboxDense ? 'Detailed' : 'Condensed'; drawInbox(); } }, inboxDense ? 'Detailed' : 'Condensed'),
    el('button', { style: 'margin-left:auto', onclick: () => { pyJSON('SESSION.inbox_mark_all()'); refresh(); } }, 'Mark All Read'));
  inbox.append(filt, list); drawInbox();
  page.append(inbox);

  // cap, room, front office
  const capG = v.cap.by_group; const total = Object.values(capG).reduce((a, b) => a + b, 0) + v.cap.dead;
  const colors = { QB: '#c8102e', OL: '#e0b400', WR: '#4cc9f0', DL: '#3fb37f', DB: '#8791a0', LB: '#b6bec9', TE: '#5a6472', RB: '#a0603a', ST: '#3a3f47' };
  const stack = el('div', { class: 'stack', style: 'margin-top:10px' }, ...Object.entries(capG).filter(([, x]) => x > 0).map(([g, x]) => el('i', { style: `width:${100 * x / v.cap.cap}%;background:${colors[g]}`, 'data-tip': `${g}: $${x.toFixed(1)}m` }, el('span', {}, g))), el('i', { style: `width:${100 * v.cap.dead / v.cap.cap}%;background:#3a1216`, 'data-tip': `Dead Money: $${v.cap.dead.toFixed(1)}m` }));
  const capS = sheet('Cap', `${v.cap.years[0].year} · $${v.cap.cap}m Limit`, el('div', { class: 'pad' }, el('div', { class: 'big' }, v.cap.space, el('span', { class: 'muted', style: 'font-size:14px;font-family:var(--text);font-weight:500' }, ' Space')), stack,
    el('div', { class: 'bars', style: 'padding:10px 0 0;grid-template-columns:96px 1fr 70px' }, ...v.cap.years.flatMap(y => [el('div', { class: 'l' }, y.year), el('div', { class: 't' }, el('i', { style: `width:${Math.min(100, 100 * y.committed / y.cap)}%;background:var(--ink-2)` })), el('div', { class: 'v' }, `$${y.committed}/${y.cap}`)]))),
    el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#frontoffice/cap' }, 'Cap'), el('a', { class: 'btn', href: '#personnel/extensions' }, 'Extensions')));
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
    el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#frontoffice' }, 'Owner'), el('a', { class: 'btn', href: '#frontoffice/staff' }, 'Staff'), el('a', { class: 'btn quiet', href: '#frontoffice/identity' }, 'Identity')));
  foS.classList.add('c4'); page.append(foS);

  // standings and season
  const st = v.standings;
  const table = el('table', {}, el('tr', {}, el('th', {}, ''), el('th', {}, 'Club'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', {}, 'Form'), el('th', { class: 'n' }, 'PF'), el('th', { class: 'n' }, 'PA'), el('th', { class: 'n' }, 'PD')),
    ...st.rows.map(r => el('tr', { class: r.me ? 'me' : '' }, el('td', {}, ''), el('td', {}, stripe(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', {}, formDots(r.form)), el('td', { class: 'n' }, r.pf), el('td', { class: 'n' }, r.pa), el('td', { class: 'n' }, (r.pd > 0 ? '+' : '') + r.pd))));
  const stS = sheet(st.division, '', table, el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#league' }, 'Full Standings')));
  stS.classList.add('c6'); page.append(stS);

  const strip = el('div', { class: 'strip' }, ...v.season.games.map(g => g.bye ? el('div', { class: 'wk bye' }, '—', el('small', {}, 'bye')) : el('div', { class: 'wk' + (g.result ? ' ' + g.result.toLowerCase() : '') + (view.rail.advance.title === `Play Week ${g.week}` ? ' now' : ''), 'data-tip': g.score ? `${g.home ? 'vs' : 'at'} ${g.opp} · ${g.score}` : null }, g.result || g.week, el('small', {}, `${g.home ? '' : '@'}${g.opp}`))));
  const seS = sheet('The Season', view.rail.record, strip, el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#league/schedule' }, 'Schedule'), el('a', { class: 'btn', href: '#league/stats' }, 'Stats')));
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

// ---------------------------------------------------------------- Club: roster, card, depth chart
let clubView = 'Overview', clubTab = 'active';
let inboxFilter = 'all', inboxDense = false;
let faPos = '', faCheap = false, faWatch = false;
function secondRow(items, current) {
  const s = $('#second'); s.innerHTML = '';
  for (const [label, hash] of items) s.append(el('a', { href: hash, 'aria-current': hash === current ? 'page' : null }, label));
}
function pill(word) { return el('span', { class: 'pill ' + word.toLowerCase() }, word); }
function condBar(c) { return el('span', { class: 'cond' }, el('i', { class: c < 60 ? 'low' : c < 80 ? 'mid' : '', style: `width:${c}%` })); }
function ovrCell(o) { return el('span', { class: 'ovr ' + (o >= 88 ? 't1' : o >= 76 ? 't2' : 't3') }, o); }
function fitCell(f) { return el('span', { class: 'fit ' + (f > 0.05 ? 'p' : f < -0.05 ? 'm' : 'z') }, (f > 0 ? '+' : '') + f.toFixed(1)); }
function who(r) { return el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.no || r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, [r.college, r.season_no ? `${r.season_no}${ord(r.season_no)} season` : null].filter(Boolean).join(' · ')))); }

function renderRoster(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Club'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'club'));
  secondRow([['Roster', '#club'], ['Depth Chart', '#club/depth'], ['Practice Squad', '#club/ps']], clubTab === 'ps' ? '#club/ps' : '#club');
  const sheet = el('section', { class: 'sheet c12' });
  const tabs = el('div', { class: 'tabs' });
  for (const [k, label, n] of [['active', 'Active', v.count], ['ps', 'Practice Squad', v.practice.length], ['injured', 'Injured', v.injured.length]])
    tabs.append(el('button', { 'aria-pressed': String(clubTab === k), onclick: () => { clubTab = k; renderRoster(v); } }, label + ' ', el('em', {}, n)));
  const views = el('div', { class: 'tabs', style: 'margin-left:14px' });
  for (const k of ['Overview', 'Ratings', 'Contract', 'Stats']) views.append(el('button', { 'aria-pressed': String(clubView === k), onclick: () => { clubView = k; renderRoster(v); } }, k));
  sheet.append(el('div', { class: 'tools' }, tabs, views, el('span', { class: 'count', style: 'margin-left:auto' }, `${v.count} on the roster · Cap ${'$' + v.cap_total.toFixed(1) + 'm'}` + (v.practice.length ? ` · Practice Squad $${v.ps_charge}m` : ''))));
  const tbl = el('table', { class: 'tbl' });
  const H = (t, tip, n) => { const th = el('th', { 'data-tip': tip || null, class: n ? 'n' : null }, t); return th; };
  const heads = { Overview: [H('Player'), H('Pos', 'Position'), H('Age', null, 1), H('Ovr', 'Overall Rating', 1), H('Fit', "How well the player matches your coach's scheme", 1), H('Dev', 'Rate of XP Growth'), H('Condition', 'Game-day Freshness'), H('Morale', "Player's happiness"), H('Yrs', 'Years left on his contract', 1), H('Cap Hit', "This year's cap hit", 1), H('Penalty', 'Dead cap charged if player is cut/traded', 1), H('Status')],
                  Ratings: [H('Player'), H('Pos', 'Position'), H('Age', null, 1), H('Ovr', 'Overall Rating', 1), H('Ceiling', "The player's estimated potential", 1), H('Dev', 'Rate of XP Growth'), H('Fit', "How well the player matches your coach's scheme", 1), H('Morale', "Player's happiness")],
                  Contract: [H('Player'), H('Pos', 'Position'), H('Age', null, 1), H('Yrs', 'Years left on his contract', 1), H('Cap Hit', "This year's cap hit", 1), H('Penalty', 'Dead cap charged if player is cut/traded', 1), H('Status')],
                  Stats: [H('Player'), H('Pos', 'Position'), H('G', 'Games played', 1), H('This Season'), H('Comp%', 'Completion pct for a quarterback, catch pct for a receiver', 1), H('EPA', 'Expected points added per dropback, rush, target or defensive play by position', 1)] }[clubView];
  if (clubTab === 'ps') heads.push(el('th', {}, ''));
  tbl.append(el('tr', {}, ...heads));
  const rowsFor = () => clubTab === 'ps' ? [{ title: 'Practice Squad', rows: v.practice }] : clubTab === 'injured' ? [{ title: 'Injured', rows: v.injured }] : v.groups;
  for (const g of rowsFor()) {
    tbl.append(el('tr', { class: 'grp' }, el('td', { colspan: String(heads.length) }, `${g.title} · ${g.rows.length}`)));
    for (const r of g.rows) {
      const cells = { Overview: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, fitCell(r.fit)), el('td', {}, el('span', { class: 'dev' + (r.dev === 'Star' || r.dev === 'Superstar' ? ' star' : '') }, r.dev)), el('td', {}, condBar(r.cond)), el('td', {}, pill(r.morale)), el('td', { class: 'n' }, r.yrs), el('td', { class: 'n' }, `$${r.hit.toFixed(1)}m`), el('td', { class: 'n' }, `$${r.penalty.toFixed(1)}m`), el('td', {}, el('span', { class: 'inj' }, r.status))],
                      Ratings: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, r.pot_range ? `${r.pot_range[0]}–${r.pot_range[1]}` : (r.pot ?? '—')), el('td', {}, el('span', { class: 'dev' + (r.dev === 'Star' || r.dev === 'Superstar' ? ' star' : '') }, r.dev)), el('td', { class: 'n' }, fitCell(r.fit)), el('td', {}, pill(r.morale))],
                      Contract: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, r.yrs), el('td', { class: 'n' }, `$${r.hit.toFixed(1)}m`), el('td', { class: 'n' }, `$${r.penalty.toFixed(1)}m`), el('td', {}, el('span', { class: 'inj' }, r.status))],
                      Stats: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.stats.games), el('td', { style: 'text-align:left;font-family:var(--mono);font-size:12px' }, r.stats.line), el('td', { class: 'n' }, r.stats.comp != null ? `${r.stats.comp}%` : '—'), el('td', { class: 'n', style: r.stats.epa != null ? (r.stats.epa > 0 ? 'color:var(--ok)' : 'color:var(--danger)') : '' }, r.stats.epa != null ? (r.stats.epa > 0 ? '+' : '') + r.stats.epa.toFixed(2) : '—')] }[clubView]();
      if (clubTab === 'ps') {
        const act = (name, extra) => { const res = pyJSON(`SESSION.club_act(${JSON.stringify(name)}, ${extra})`); busy(res.ok ? (res.moves ? res.moves.map(m => `${m.name} ${m.how}`).join(', ') : `${res.name}: done.`) : res.why); setTimeout(() => busy(null), 2200); renderRoster(pyJSON('SESSION.club_roster()')); };
        cells.push(el('td', {}, el('div', { class: 'row-act', style: 'opacity:1' },
          el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', 'data-tip': 'Sign him to the 53 at the minimum', onclick: () => act('call_up', `pid=${JSON.stringify(r.pid)}`) }, 'Call Up'),
          el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', disabled: r.elevated_now ? '' : null, 'data-tip': `Dress him Sunday and send him back after · ${r.elevations} of ${v.per_man_max} used`, onclick: () => act('elevate', `pids=[${JSON.stringify(r.pid)}]`) }, r.elevated_now ? 'Elevated' : `Elevate · ${r.elevations}/${v.per_man_max}`),
          el('button', { class: 'btn warn', style: 'width:auto;padding:3px 8px;font-size:12px', onclick: () => { if (confirm(`Release ${r.name} from the practice squad?`)) act('release_ps', `pid=${JSON.stringify(r.pid)}`); } }, 'Release'))));
      }
      tbl.append(el('tr', {}, ...cells));
    }
  }
  sheet.append(tbl);
  if (clubTab === 'ps') sheet.append(el('div', { class: 'foot' }, el('span', { class: 'count' }, `Elevations this week: ${v.elevations_used} of ${v.elevations_max} · a man's ${v.per_man_max + 1}${ord(v.per_man_max + 1)} elevation signs him to the 53`)));
  page.append(sheet);
}

function renderCard(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Club'; secondRow([['Roster', '#club'], ['Depth Chart', '#club/depth'], ['Practice Squad', '#club/ps']], '');
  if (v.error) { page.append(el('section', { class: 'sheet c12' }, el('div', { class: 'empty' }, v.error))); return; }
  const s = el('section', { class: 'sheet c12' });
  const col = v.team ? v.team.color : 'var(--rule-hi)';
  s.append(el('div', { class: 'head' },
    el('div', { class: 'jersey', style: `background:${col}` }, v.no || v.pos),
    el('div', {}, el('div', { class: 'hname' }, v.name.toUpperCase()),
      el('div', { class: 'hline' }, el('b', {}, v.pos), ` · ${v.age} · ${v.college || ''}${v.season_no ? ` · ${v.season_no}${ord(v.season_no)} season` : ''} · ${v.draft}` + (v.team ? ` · ${v.team.name}` : ' · Free agent')),
      el('div', { class: 'hfacts' }, el('div', {}, el('span', {}, 'Contract'), el('b', {}, `$${v.contract.per_year.toFixed(1)}m`, el('small', {}, `per year · ${v.contract.years} yrs`))), el('div', {}, el('span', {}, `Cap Hit ${v.rail.year}`), el('b', {}, `$${v.contract.hit.toFixed(1)}m`)), el('div', {}, el('span', {}, 'Penalty'), el('b', {}, `$${v.contract.penalty.toFixed(1)}m`)), el('div', {}, el('span', {}, 'Trade Interest'), el('b', { style: 'color:var(--ink-2)' }, v.interest)), el('div', {}, el('span', {}, 'Morale'), el('b', { style: 'color:var(--ink-2)' }, v.morale)))),
    el('div', { class: 'ovrbig' }, el('b', {}, v.ovr), el('span', {}, `Overall · Scheme Fit ${v.fit >= 0 ? '+' : ''}${v.fit.toFixed(1)}`), el('div', { class: 'pot' }, `Ceiling ${v.ceiling} · ${v.dev}`))));
  const acts = el('div', { class: 'acts' });
  if (v.actions.mine) {
    if (v.actions.extend_eligible) acts.append(el('button', { class: 'btn go', 'data-tip': 'Ask his agent and open the talks', onclick: () => { const r = pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(v.pid)}, kind='extension')`); notify(r); location.hash = '#personnel/extensions'; } }, 'Extend'));
    acts.append(el('button', { class: 'btn', 'data-tip': 'Put him in a trade package and shop him', onclick: () => { tradeState = { other: tradeState.other, a: [v.pid], b: [], keep: true }; location.hash = '#personnel/trades'; } }, 'Trade Block'));
    const alts = v.grades.filter(g => !g.mine);
    if (alts.length) { const sel = el('select', { class: 'btn' }); sel.append(el('option', { value: '' }, 'Position Change…')); alts.forEach(g => sel.append(el('option', { value: g.pos }, `${g.pos} · ${g.ovr} Ovr`))); sel.onchange = () => { if (!sel.value) return; const r = pyJSON(`SESSION.club_act('position_change', pid=${JSON.stringify(v.pid)}, new_pos=${JSON.stringify(sel.value)})`); busy(r.ok ? `${r.name} moves to ${r.to}: ${r.penalty} points for ${r.games} games.` : r.why); setTimeout(() => busy(null), 2200); if (r.ok) renderCard(pyJSON(`SESSION.club_card(${JSON.stringify(v.pid)})`)); }; acts.append(sel); }
    acts.append(el('button', { class: 'btn warn', onclick: () => { if (!confirm(`Cut ${v.name}? Penalty $${v.contract.penalty.toFixed(1)}m against this year's cap.`)) return; const r = pyJSON(`SESSION.club_act('cut', pid=${JSON.stringify(v.pid)})`); busy(r.ok ? `${r.name} released. Penalty $${r.penalty}m.` : r.why); setTimeout(() => busy(null), 2200); location.hash = '#club'; } }, `Cut · Penalty $${v.contract.penalty.toFixed(1)}m`));
  }
  acts.append(el('button', { class: 'btn quiet', onclick: () => history.back() }, 'Back'));
  s.append(el('div', { class: 'ctabs' }, el('button', { 'aria-pressed': 'true' }, 'Overview'), acts));
  // body: positions, attributes, contract
  const left = el('div', {});
  left.append(el('div', { class: 'h5' }, 'Positions'));
  const pm = el('div', { class: 'posmap', style: `grid-template-columns:repeat(${Math.min(5, v.grades.length)},1fr)` }); v.grades.forEach(g => pm.append(el('div', { class: g.mine ? 'nat' : 'fam' }, g.pos))); left.append(pm);
  const gr = el('div', { class: 'grades' }); v.grades.forEach(g => gr.append(el('div', {}, el('span', {}, g.pos), el('div', { class: 'bar' }, el('i', { style: `width:${g.ovr}%` })), el('span', { class: 'g' }, `${g.ovr} Ovr`)))); left.append(gr);
  left.append(el('div', { class: 'h5', style: 'margin-top:14px' }, 'Status'));
  left.append(el('div', { class: 'kv' }, el('span', {}, 'Condition'), el('span', {}, `${v.cond}%`), el('span', {}, 'Health'), el('span', {}, v.out ? `Out until week ${v.out}` : 'Healthy'), el('span', {}, 'Season'), el('span', {}, `${v.games} games · ${v.season.line}`), el('span', {}, 'Notes'), el('span', {}, v.status || '—')));
  const mid = el('div', {});
  mid.append(el('div', { class: 'h5' }, 'Attributes'));
  const attrs = el('div', { class: 'attrs' });
  for (const c of v.cols) {
    const box = el('div', {}, el('div', { class: 'h5', style: 'margin-bottom:4px' }, c.title));
    for (const r of c.rows) { const row = el('div', { class: 'arow ' + r.tier }, el('span', {}, r.label)); row.append(r.shift ? el('em', { class: 'fitd ' + (r.shift > 0 ? 'p' : 'm') }, (r.shift > 0 ? '+' : '') + r.shift) : el('em', {})); row.append(el('b', {}, r.v)); box.append(row); }
    if (c.title === 'Mental' && v.personality) { box.append(el('div', { class: 'h5', style: 'margin:12px 0 4px' }, 'Traits')); const tr = el('div', { class: 'traits' }); v.personality.split(',').map(x => x.trim()).filter(Boolean).forEach(w => tr.append(el('span', {}, w.replace(/\b\w/g, ch => ch.toUpperCase())))); box.append(tr); }
    attrs.append(box);
  }
  mid.append(attrs);
  const right = el('div', {});
  right.append(el('div', { class: 'h5' }, 'Contract', el('span', {}, v.contract.years ? `${v.contract.years} yrs · $${v.contract.per_year.toFixed(1)}m per year` : 'None')));
  if (v.contract.by_year.length) { const ct = el('table', { class: 'contract' }); ct.append(el('tr', {}, el('th', {}, 'Year'), el('th', {}, 'Base'), el('th', {}, 'Bonus'), el('th', {}, 'Cap Hit'), el('th', {}, 'Penalty'))); v.contract.by_year.forEach((y, i) => ct.append(el('tr', { class: i === 0 ? 'now' : '' }, el('td', {}, y.year), el('td', {}, y.base != null ? y.base.toFixed(1) : '—'), el('td', {}, y.bonus != null ? y.bonus.toFixed(1) : '—'), el('td', {}, y.hit.toFixed(1)), el('td', {}, y.penalty != null ? y.penalty.toFixed(1) : '—')))); right.append(ct); }
  right.append(el('div', { class: 'h5', style: 'margin-top:14px' }, 'Trade Value', el('span', {}, "the scout's read")), el('div', { class: 'kv' }, el('span', {}, 'Market'), el('span', {}, v.market), el('span', {}, 'Interest'), el('span', {}, v.interest_line)));
  s.append(el('div', { class: 'body' }, left, mid, right));
  // the tiles: morale, condition, development, season stats
  const tiles = el('div', { class: 'tiles' },
    el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Morale'), el('div', { class: 'word' }, v.morale), el('div', { class: 'sub' }, v.morale_line)),
    el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Condition'), el('div', { class: 'word' }, `${v.cond}%`), el('div', { class: 'sub' }, v.out ? `Out until week ${v.out}` : v.cond >= 85 ? 'Fresh' : v.cond >= 70 ? 'Carrying a load' : 'Worn down'), el('div', { class: 'cond', style: 'width:100%;height:8px;margin-top:8px' }, el('i', { class: v.cond < 60 ? 'low' : v.cond < 80 ? 'mid' : '', style: `width:${v.cond}%` }))),
    el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Development'), el('div', { class: 'word' }, v.dev), el('div', { class: 'sub' }, v.dev_line)),
    el('div', { class: 'tile' }, el('div', { class: 'h5' }, 'Ceiling'), el('div', { class: 'word' }, v.ceiling), el('div', { class: 'sub' }, "your scouts' range for where he tops out")));
  const wide = el('div', { class: 'tile wide' }, el('div', { class: 'h5' }, 'Season Stats', el('span', {}, `${v.rail.year} · ${v.games} game${v.games === 1 ? '' : 's'}`)));
  if (v.seasons && v.seasons.length) { const t = el('table', { class: 'stab' }); t.append(el('tr', {}, el('th', {}, 'Season'), el('th', {}, 'G'), ...v.season.cols.map(c => el('th', {}, c)))); for (const sn of v.seasons.slice().reverse()) t.append(el('tr', {}, el('td', {}, `${sn.year} ${sn.team}`), el('td', {}, sn.games), ...sn.row.map(x => el('td', {}, String(x))))); wide.append(t); }
  else wide.append(el('div', { class: 'sub' }, 'No snaps yet this season.'));
  tiles.append(wide); s.append(tiles);
  s.append(el('div', { class: 'foot' }, el('button', { class: 'btn quiet', onclick: () => { location.hash = '#club'; } }, 'Back to Roster'), el('button', { class: 'btn quiet', onclick: () => { location.hash = '#club/depth'; } }, 'Depth Chart')));
  page.append(s);
}

let depthPkg = 'Nickel';
function renderDepth(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Club'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'club'));
  secondRow([['Roster', '#club'], ['Depth Chart', '#club/depth'], ['Practice Squad', '#club/ps']], '#club/depth');
  const s = el('section', { class: 'sheet c12' });
  const pk = el('div', { class: 'pkg' }, el('span', {}, 'Package'));
  for (const p of v.packages) pk.append(el('button', { 'aria-pressed': String(p === v.package), onclick: () => { depthPkg = p; renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(p)})`)); } }, p));
  pk.append(el('span', { class: 'snaps' }, 'Drag a plate or use the arrows; the game fields the order you set'));
  s.append(pk);
  const chart = el('div', { class: 'chart' });
  for (const c of v.cols) {
    const col = el('div', { class: 'col' }, el('h4', {}, c.title));
    // group by slot position for multi-position columns so arrows move within a position
    const byPos = {}; c.slots.forEach(x => (byPos[x.pos] = byPos[x.pos] || []).push(x));
    for (const [pos, men] of Object.entries(byPos)) {
      men.forEach((x, i) => {
        const plate = el('div', { class: 'plate' + (x.flag === 'out' ? ' out' : ''), draggable: 'true', 'data-pid': x.pid, 'data-pos': pos }, el('div', { class: 'no' }, x.no || pos), el('div', { class: 'nm', onclick: () => { location.hash = '#club/player/' + x.pid; } }, x.short, el('small', {}, x.flag === 'out' ? 'Out' : x.flag === 'questionable' ? 'Questionable' : '')), el('div', { class: 'ov' }, x.ovr));
        plate.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', JSON.stringify({ pid: x.pid, pos })); plate.classList.add('dragging'); });
        plate.addEventListener('dragend', () => plate.classList.remove('dragging'));
        plate.addEventListener('dragover', e => { e.preventDefault(); plate.classList.add('over'); });
        plate.addEventListener('dragleave', () => plate.classList.remove('over'));
        plate.addEventListener('drop', e => {
          e.preventDefault(); plate.classList.remove('over');
          let d; try { d = JSON.parse(e.dataTransfer.getData('text/plain')); } catch (_) { return; }
          if (!d || d.pos !== pos || d.pid === x.pid) return;      // a plate only moves within its own position
          const order = men.map(m => m.pid).filter(p => p !== d.pid); order.splice(order.indexOf(x.pid), 0, d.pid);
          pyJSON(`SESSION.club_act('set_depth', pos=${JSON.stringify(pos)}, pids=${JSON.stringify(order)})`); renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(v.package)})`));
        });
        if (x.flag !== 'out') plate.append(el('div', { class: 'cbar' }, el('i', { class: x.cond < 80 ? 'mid' : '', style: `width:${x.cond}%` })));
        const arrows = el('div', { class: 'arrows' },
          el('button', { disabled: i === 0 ? '' : null, onclick: () => { const order = men.map(m => m.pid); [order[i - 1], order[i]] = [order[i], order[i - 1]]; pyJSON(`SESSION.club_act('set_depth', pos=${JSON.stringify(pos)}, pids=${JSON.stringify(order)})`); renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(v.package)})`)); } }, '▲'),
          el('button', { disabled: i === men.length - 1 ? '' : null, onclick: () => { const order = men.map(m => m.pid); [order[i + 1], order[i]] = [order[i], order[i + 1]]; pyJSON(`SESSION.club_act('set_depth', pos=${JSON.stringify(pos)}, pids=${JSON.stringify(order)})`); renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(v.package)})`)); } }, '▼'));
        col.append(el('div', { class: 'slot' + (x.start ? ' start' : '') }, el('span', { class: 'rk' }, Object.keys(byPos).length > 1 ? pos : String(i + 1)), plate, arrows));
      });
    }
    chart.append(col);
  }
  s.append(chart);
  s.append(el('div', { class: 'foot' }, el('button', { class: 'btn', 'data-tip': 'Best overall first at every spot', onclick: () => { pyJSON(`SESSION.club_act('reset_depth')`); renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(v.package)})`)); } }, 'Auto-Fill by Rating'), el('button', { class: 'btn', 'data-tip': "Best at the spot in your scheme first, the way the coordinators would set it", onclick: () => { notify(pyJSON(`SESSION.club_act('fill_by_fit')`)); renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(v.package)})`)); } }, 'Auto-Fill by Fit'), el('span', { class: 'count', style: 'margin-left:auto' }, Object.keys(v.pins).length ? `Your order set at: ${Object.keys(v.pins).join(', ')}` : 'Ordered by rating')));
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
    box.append(el('div', { class: 'side-h' }, crest(own.club), el('b', {}, own.club.nick), el('span', {}, `Cap ${own.cap >= 0 ? '' : '−'}$${Math.abs(own.cap).toFixed(1)}m`)));
    const sn = el('div', { class: 'read', style: 'display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:8px' });
    sn.append(el('div', {}, el('div', { class: 'h5' }, own === v.me ? 'Your Surplus' : 'Their Surplus'), ...(own.surplus.length ? own.surplus.map(x => { const p = own.roster.find(r => r.pid === x.pid); return p ? el('div', { style: 'font-size:12.5px;cursor:pointer', onclick: () => { if (!sel.includes(p.pid)) { sel.push(p.pid); reload(); } } }, `${p.short} · ${p.pos} · ${p.ovr}`, el('small', { style: 'color:var(--ink-3)' }, ` ${x.why}`)) : ''; }) : [el('div', { style: 'font-size:12.5px;color:var(--ink-3)' }, 'Nothing spare.')])));
    sn.append(el('div', {}, el('div', { class: 'h5' }, own === v.me ? 'Your Needs' : 'Their Needs'), el('div', { style: 'font-size:12.5px' }, own.needs && own.needs.length ? own.needs.join(' · ') : 'None pressing')));
    box.append(sn);
    box.append(el('div', { class: 'h5' }, title));
    const pk = el('div', { class: 'pkgbox' });
    if (!sel.length) pk.append(el('div', { class: 'empty' }, 'Nothing yet. Pick from the list below.'));
    for (const id of sel) {
      const p = own.roster.find(r => r.pid === id), k = own.picks.find(r => r.id === id);
      if (p) pk.append(el('div', { class: 'plate' }, el('div', { class: 'no' }, p.no || p.pos), el('div', { class: 'nm' }, p.short, el('small', {}, `${p.pos} · ${p.age} · $${p.hit}m · ${p.yrs} yrs`)), el('div', { class: 'ov' }, p.ovr), el('div', { class: 'x', onclick: () => { sel.splice(sel.indexOf(id), 1); reload(); } }, '✕')));
      else if (k) pk.append(el('div', { class: 'pkcard' }, el('div', { class: 'rd' }, k.round), el('div', { class: 'nm' }, k.label, el('small', {}, k.slot === `R${k.round}` ? `Round ${k.round}` : `Pick ${k.slot}`)), el('div', { class: 'x', onclick: () => { sel.splice(sel.indexOf(id), 1); reload(); } }, '✕')));
    }
    box.append(pk);
    // pickers
    const tabs = el('div', { class: 'tabs', style: 'margin:10px 0 6px' }); const list1 = el('div', { class: 'rows' }); let mode = 'players';
    const drawList = () => {
      list1.innerHTML = '';
      if (mode === 'players') for (const p of own.roster) { if (sel.includes(p.pid)) continue; const sur = own.surplus.find(x => x.pid === p.pid); list1.append(el('div', { class: 'plate pickable', onclick: () => { sel.push(p.pid); reload(); } }, el('div', { class: 'no' }, p.no || p.pos), el('div', { class: 'nm' }, p.short, el('small', {}, `${p.pos} · ${p.age} · $${p.hit}m · ${p.yrs} yrs` + (sur ? ` · ${sur.why}` : ''))), el('div', { class: 'ov' }, p.ovr))); }
      else for (const k of own.picks) { if (sel.includes(k.id)) continue; list1.append(el('div', { class: 'pkcard pickable', style: 'cursor:pointer', onclick: () => { sel.push(k.id); reload(); } }, el('div', { class: 'rd' }, k.round), el('div', { class: 'nm' }, k.label, el('small', {}, k.slot === `R${k.round}` ? `Round ${k.round}` : `Pick ${k.slot}`)), el('div', {}))); }
    };
    for (const [k, l] of [['players', 'Players'], ['picks', 'Picks']]) tabs.append(el('button', { 'aria-pressed': String(mode === k), onclick: e => { mode = k; tabs.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); drawList(); } }, l));
    box.append(tabs, list1); drawList();
    return box;
  };
  const two = el('div', { class: 'two' }, side(v.me, v.me.roster, v.me.picks, tradeState.a, 'You Send'), side(v.them, v.them.roster, v.them.picks, tradeState.b, 'You Get'));
  s.append(two);
  // the read and the buttons
  const foot = el('div', { class: 'foot', style: 'flex-wrap:wrap;gap:10px' });
  if (v.package) foot.append(el('div', { class: 'read', style: 'flex:1 1 100%' }, el('b', {}, v.them.club.abbr + ': '), v.package.read, el('br'), el('span', { style: 'color:var(--ink-3)' }, v.package.my_read + ` Roster after: ${v.package.roster_after.me}. Cap after: $${v.package.cap_after.me}m.`)));
  const can = v.can_trade && (tradeState.a.length || tradeState.b.length);
  foot.append(el('button', { class: 'btn go', disabled: can ? null : '', onclick: () => { const r = pyJSON(`SESSION.personnel_act('propose', other=${JSON.stringify(tradeState.other)}, a_sends=${JSON.stringify(tradeState.a)}, b_sends=${JSON.stringify(tradeState.b)})`); notify(r); if (r.done) { tradeState.a = []; tradeState.b = []; } reload(); } }, 'Propose'),
    el('button', { class: 'btn', disabled: v.can_trade && tradeState.b.length ? null : '', 'data-tip': 'Ask what it would take from your picks', onclick: () => { const r = pyJSON(`SESSION.personnel_act('ask', other=${JSON.stringify(tradeState.other)}, a_sends=${JSON.stringify(tradeState.a)}, b_sends=${JSON.stringify(tradeState.b)})`); notify(r); if (r.adds) for (const id of r.adds) if (!tradeState.a.includes(id)) tradeState.a.push(id); reload(); } }, 'Ask What They Want'),
    el('button', { class: 'btn', disabled: v.can_trade && tradeState.a.length === 1 && !tradeState.a[0].includes('-') ? null : '', 'data-tip': 'Shop the one player you send to every club', onclick: () => { const r = pyJSON(`SESSION.personnel_act('gather', pid=${JSON.stringify(tradeState.a[0])})`); const box = $('#gather'); box.innerHTML = ''; box.append(el('b', {}, r.line)); for (const o of r.offers) box.append(el('div', { style: 'display:flex;gap:10px;align-items:center;margin-top:6px' }, crest(o.club, 26), el('span', {}, `${o.club.name} offers `, el('b', {}, o.pick.label)), el('button', { class: 'btn', style: 'margin-left:auto;padding:3px 8px;font-size:12px', onclick: () => { tradeState = { other: o.club.abbr, a: [tradeState.a[0]], b: [o.pick.id] }; reload(); } }, 'Open'))); } }, 'Gather Offers'),
    el('button', { class: 'btn quiet', onclick: () => { tradeState.a = []; tradeState.b = []; reload(); } }, 'Clear'));
  if (v.note) foot.append(el('span', { class: 'count' }, v.note));
  s.append(foot, el('div', { class: 'read', id: 'gather', style: 'margin:0 14px 14px;display:none' }));
  s.querySelector('#gather').style.display = ''; s.querySelector('#gather').append('Send one player and Gather Offers to see what the league would give.');
  page.append(s);
}

function offerForm(t, kind, onDone) {
  const f = el('div', { class: 'msg you' }, el('div', { class: 'from' }, 'Your offer'));
  const apy = el('input', { type: 'number', step: '0.1', min: '0.8', value: t.ask ? (t.ask * 0.97).toFixed(1) : '1.0' }), yrs = el('input', { type: 'number', min: '1', max: '5', value: t.years || 3 });
  const shape = el('input', { type: 'range', min: '0', max: '100', value: '50' });
  const promises = el('div', { class: 'promise' }, el('span', {}, 'Promise:'));
  const chosen = [];
  for (const [k, l] of [['starting_role', 'Named the starter'], ['captaincy', 'Captaincy'], ['no_trade', 'No trade'], ['extension_by', 'Extension by a set year'], ['no_franchise', 'No franchise tag']]) promises.append(el('button', { class: 'btn quiet', style: 'padding:2px 8px;font-size:12px', 'aria-pressed': 'false', onclick: e => { const i = chosen.indexOf(k); if (i < 0) chosen.push(k); else chosen.splice(i, 1); e.currentTarget.setAttribute('aria-pressed', String(i < 0)); } }, l));
  f.append(el('div', { class: 'offer' }, el('label', {}, 'Per Year ($m)', apy), el('label', {}, 'Years', yrs)),
    el('div', { class: 'shape' }, el('span', {}, 'Shape'), shape, el('div', { class: 'shape-lbl' }, el('em', {}, 'Back-loaded'), el('em', {}, 'Even'), el('em', {}, 'Front-loaded'))),
    promises);
  const acts = el('div', { class: 'acts' });
  acts.append(el('button', { class: 'btn go', onclick: () => { const r = pyJSON(`SESSION.personnel_act('offer', tid=${t.id}, apy=${+apy.value}, years=${+yrs.value}, front_load=${(+shape.value / 100).toFixed(2)}, promises=${JSON.stringify(chosen)})`); notify(r); onDone(); } }, kind === 'fa_inseason' ? 'Offer (decides at Advance)' : 'Send Offer'));
  if (kind === 'fa_inseason') acts.append(el('button', { class: 'btn', 'data-tip': 'His full ask, signed now', onclick: () => { const r = pyJSON(`SESSION.personnel_act('offer', tid=${t.id}, apy=${t.ask}, years=${t.years}, sign_today=True)`); notify(r); onDone(); } }, `Sign Today at $${t.ask}m`));
  acts.append(el('button', { class: 'btn quiet', onclick: () => { const r = pyJSON(`SESSION.personnel_act('withdraw', tid=${t.id})`); notify(r); onDone(); } }, 'Walk Away'));
  f.append(acts); return f;
}

function threadBox(t, onDone) {
  const box = el('div', { class: 'thread' });
  box.append(el('div', { class: 'msg' }, el('div', { class: 'from' }, `${t.name}'s agent`), el('div', { class: 'txt' }, t.ask ? el('span', {}, `He is asking `, el('b', {}, `$${t.ask}m per year over ${t.years}`), `. ${t.mood ? 'Mood: ' + t.mood + '.' : ''}`) : 'He would rather wait.')));
  for (const ln of t.log || []) box.append(el('div', { class: 'msg' + (ln.who === 'you' ? ' you' : '') }, el('div', { class: 'from' }, ln.who === 'you' ? 'You' : `${t.name}'s agent`), el('div', { class: 'txt' }, ln.text)));
  if (t.rival) box.append(el('div', { class: 'msg match' }, el('div', { class: 'from' }, 'Rival offer'), el('div', { class: 'txt' }, `${t.rival.team} has offered `, el('b', {}, `$${t.rival.apy}m × ${t.rival.years}`), '.'), el('div', { class: 'acts' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.personnel_act('match', tid=${t.id})`)); onDone(); } }, 'Match'))));
  if (t.counter) box.append(el('div', { class: 'msg' }, el('div', { class: 'from' }, 'Counter'), el('div', { class: 'terms-line' }, el('b', {}, `$${t.counter.apy}m`), ` × ${t.counter.years}`), el('div', { class: 'acts' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.personnel_act('match_counter', tid=${t.id})`)); onDone(); } }, 'Accept Counter'))));
  if (t.state === 'waiting') box.append(el('div', { class: 'msg note' }, `Waiting on his answer${t.due ? ' · due ' + t.due : ''}.`));
  else if (['accepted', 'signed'].includes(t.state)) box.append(el('div', { class: 'msg note' }, 'Signed.'));
  else if (t.state === 'broken_off') box.append(el('div', { class: 'msg note' }, 'He has broken off talks.'));
  else if (t.state === 'declined') box.append(el('div', { class: 'msg note' }, 'He declined.'));
  else box.append(offerForm(t, t.kind, onDone));
  return box;
}

function renderFA(v) {
  renderRail(v.rail); const page = persPage(); persSecond('fa');
  const reload = () => renderFA(pyJSON(`SESSION.personnel('free_agency')`));
  const left = el('section', { class: 'sheet c7' }, el('h2', {}, 'Free Agency', el('small', {}, `${v.count} available · Cap $${v.cap}m · Roster ${v.roster}`)));
  if (!v.in_season) { const ph = el('div', { class: 'phase' }); ['Legal Tampering', 'Day One', 'Day Two', 'Open Market', 'Camp'].forEach((n, i) => ph.append(el('div', { class: v.step == null ? '' : i + 1 < v.step ? 'done' : i + 1 === v.step ? 'now' : '' }, n))); left.append(ph); }
  const tools = el('div', { class: 'tools' }); const posSel = el('select', { class: 'btn' }, el('option', { value: '' }, 'All positions')); for (const p of v.positions) posSel.append(el('option', { value: p }, p));
  const cheap = el('button', { class: 'btn' + (faCheap ? ' go' : ''), 'data-tip': 'Men asking under $5m a year, or with no ask yet', onclick: () => { faCheap = !faCheap; renderFA(v); } }, 'Under $5m');
  const watchB = el('button', { class: 'btn' + (faWatch ? ' go' : ''), onclick: () => { faWatch = !faWatch; renderFA(v); } }, `Watchlist · ${v.rows.filter(r => r.watch).length}`);
  posSel.value = faPos; posSel.onchange = () => { faPos = posSel.value; renderFA(v); };
  tools.append(posSel, cheap, watchB, el('span', { class: 'count', style: 'margin-left:auto' }, 'Star a man to keep him on your watchlist across the season')); left.append(tools);
  const tbl = el('table', { class: 'tbl' }); tbl.append(el('tr', {}, el('th', {}, ''), el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', {}, 'Last Club'), el('th', {}, 'Talks'), el('th', {}, '')));
  const rows = v.rows.filter(r => (!faPos || r.pos === faPos) && (!faCheap || r.ask == null || r.ask < 5) && (!faWatch || r.watch));
  for (const r of rows) tbl.append(el('tr', {}, el('td', {}, el('button', { class: 'star' + (r.watch ? ' on' : ''), 'data-tip': r.watch ? 'On your watchlist' : 'Add to watchlist', onclick: () => { pyJSON(`SESSION.personnel_act('watch', pid=${JSON.stringify(r.pid)})`); reload(); } }, r.watch ? '★' : '☆')), el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name))), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', {}, r.last || '—'), el('td', {}, r.talks ? `${r.talks}${r.ask ? ` · asks $${r.ask}m × ${r.years}` : ''}` : ''),
    el('td', {}, r.thread ? el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', onclick: () => { document.getElementById('th-' + r.thread)?.scrollIntoView(); } }, 'Open Thread') : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', onclick: () => { notify(pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind=${JSON.stringify(v.in_season ? 'fa_inseason' : 'fa_offseason')})`)); reload(); } }, 'Ask the Agent'))));
  left.append(tbl); if (!rows.length) left.append(el('div', { class: 'empty' }, v.rows.length ? 'Nobody matches the filter.' : 'Nobody worth a call is on the market.'));
  page.append(left);
  const right = el('section', { class: 'sheet c5' }, el('h2', {}, 'Talks', el('small', {}, `${v.threads.length} open`)));
  const feedSheet = el('section', { class: 'sheet c5', style: 'order:2' }, el('h2', {}, 'Around the League', el('small', {}, 'latest signings')));
  const fd = el('div', { class: 'feed' }); for (const f of v.feed) fd.append(el('div', {}, el('span', {}, stripe(f.team.abbr)), el('span', {}, `${f.team.name} ${f.kind} ${f.name} (${f.pos})` + (f.apy ? `, ${f.years} yrs at $${f.apy}m` : '')), el('time', {}, f.week ? `Wk ${f.week}` : String(f.year || '')))); if (!v.feed.length) fd.append(el('div', { class: 'empty' }, 'Quiet.'));
  feedSheet.append(fd);
  for (const t of v.threads) { const w = el('div', { id: 'th-' + t.id }, el('div', { class: 'h5', style: 'padding:10px 12px 0' }, `${t.name} · ${t.pos}`)); w.append(threadBox(t, reload)); right.append(w); }
  if (!v.threads.length) right.append(el('div', { class: 'empty' }, v.in_season ? 'Ask an agent; a signing you offer decides at the next Advance, or pay his ask to sign today.' : 'Ask an agent to open talks; he mulls offers through each market step.'));
  page.append(right, feedSheet);
}

function renderWire(v) {
  renderRail(v.rail); const page = persPage(); persSecond('wire');
  const reload = () => renderWire(pyJSON(`SESSION.personnel('waivers')`));
  const left = el('section', { class: 'sheet c8' }, el('h2', {}, 'Waiver Wire', el('small', {}, `${v.rows.length} on the wire · claims award ${v.awards} · your priority ${v.my_priority ?? '—'}`)));
  const tbl = el('table', { class: 'tbl' }); tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', {}, 'From'), el('th', { class: 'n' }, 'Yrs'), el('th', { class: 'n', 'data-tip': 'Cap hit you take on' }, 'Cap Hit'), el('th', {}, '')));
  for (const r of v.rows) tbl.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name))), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', {}, r.frm), el('td', { class: 'n' }, r.yrs), el('td', { class: 'n' }, `$${r.hit.toFixed(1)}m`),
    el('td', {}, r.claimed ? el('span', { class: 'badge-sm' }, 'Claimed') : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', onclick: () => {
      if (!v.roster_full) { notify(pyJSON(`SESSION.personnel_act('claim', pid=${JSON.stringify(r.pid)})`)); reload(); return; }
      // the roster is full: name the man who goes if the claim is awarded
      const box = $('#claimbox'); box.innerHTML = ''; box.style.display = '';
      const sel = el('select', { class: 'btn' }); for (const c of v.cut_options) sel.append(el('option', { value: c.pid }, `${c.name} (${c.pos}, ${c.ovr}) · penalty $${c.penalty}m`));
      box.append(el('b', {}, `Claim ${r.name}. Your roster is at 53; if the claim is awarded, release:`), el('div', { style: 'display:flex;gap:6px;margin-top:8px;align-items:center' }, sel, el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.personnel_act('claim', pid=${JSON.stringify(r.pid)}, release_pid=${JSON.stringify(sel.value)})`)); reload(); } }, 'Lodge Claim'), el('button', { class: 'btn quiet', onclick: () => { box.style.display = 'none'; } }, 'Cancel')));
    } }, 'Claim'))));
  left.append(tbl); if (!v.rows.length) left.append(el('div', { class: 'empty' }, 'The wire is clear.'));
  left.append(el('div', { class: 'read', id: 'claimbox', style: 'margin:0 14px 14px;display:none' }));
  page.append(left);
  const right = el('section', { class: 'sheet c4' }, el('h2', {}, 'Your Claims', el('small', {}, `${v.claims.length} lodged · awarded ${v.awards}`)));
  for (const c of v.claims) right.append(el('div', { class: 'pad', style: 'display:flex;gap:10px;align-items:center;border-bottom:1px solid var(--rule)' }, el('div', { class: 'nm', style: 'flex:1' }, `${c.name} (${c.pos}, ${c.ovr})`, el('small', { style: 'display:block;color:var(--ink-3)' }, c.release_name ? `if awarded, release ${c.release_name}` : 'room on the roster')), el('button', { class: 'btn quiet', style: 'width:auto;padding:3px 8px;font-size:12px', onclick: () => { notify(pyJSON(`SESSION.personnel_act('withdraw_claim', pid=${JSON.stringify(c.pid)})`)); reload(); } }, 'Withdraw')));
  if (!v.claims.length) right.append(el('div', { class: 'empty' }, 'No claims in.'));
  right.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Awarded This Week', el('small', {}, `${v.awarded.length}`)));
  const aw = el('div', { class: 'feed' }); for (const a of v.awarded) aw.append(el('div', { style: a.mine ? 'background:var(--sheet-2)' : '' }, el('span', {}, stripe(a.team.abbr)), el('span', {}, `${a.team.name} claim ${a.name} (${a.pos})` + (a.frm ? ` from ${a.frm}` : '')), el('time', {}))); if (!v.awarded.length) aw.append(el('div', { class: 'empty' }, 'None yet this week.')); right.append(aw);
  right.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Priority', el('small', {}, 'worst record first')));
  const pr = el('div', { class: 'pad' }); v.priority.forEach((c, i) => pr.append(el('div', { class: 'prio' + (c.abbr === v.rail.club.abbr ? ' me' : '') }, el('span', { class: 'p' }, i + 1), stripe(c.abbr, c.name)))); right.append(pr);
  page.append(right);
}

function renderExtensions(v) {
  renderRail(v.rail); const page = persPage(); persSecond('extensions');
  const reload = () => renderExtensions(pyJSON(`SESSION.personnel('extensions')`));
  const left = el('section', { class: 'sheet c7' }, el('h2', {}, 'Extensions', el('small', {}, `${v.rows.length} men inside two years · Cap $${v.cap}m`)));
  if (v.tag.open) left.append(el('div', { class: 'read', style: 'margin:10px 14px 0' }, el('b', {}, 'Franchise tag: '), v.tag.used ? `used on ${v.tag.tagged}.` : v.tag.none ? 'you told the AI not to place one for you.' : 'one tag, on a man whose deal is up, at the position price; the AI places it for you at Extensions and Tags unless you choose here. ', (!v.tag.used && !v.tag.none) ? el('button', { class: 'btn quiet', style: 'width:auto;padding:2px 8px;font-size:12px;margin-left:6px', onclick: () => { notify(pyJSON(`SESSION.personnel_act('tag', pid='none')`)); reload(); } }, 'No Tag This Year') : ''));
  const tbl = el('table', { class: 'tbl' }); tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', { class: 'n', 'data-tip': 'Years left' }, 'Yrs'), el('th', { class: 'n' }, 'Cap Hit'), el('th', {}, 'Morale'), el('th', {}, 'Talks'), el('th', {}, '')));
  const row = r => el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name))), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, r.yrs === 0 ? (r.fa_class || 'up') : r.yrs), el('td', { class: 'n' }, `$${r.hit.toFixed(1)}m`), el('td', {}, pill(r.morale)), el('td', {}, r.talks ? `${r.talks}${r.ask ? ` · asks $${r.ask}m × ${r.years}` : ''}` : (r.eligible ? '' : 'not yet eligible')),
    el('td', {}, el('div', { style: 'display:flex;gap:4px' },
      r.thread ? el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', onclick: () => { document.getElementById('th-' + r.thread)?.scrollIntoView(); } }, 'Open Thread') : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', disabled: r.eligible ? null : '', onclick: () => { notify(pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind='extension')`)); reload(); } }, 'Ask the Agent'),
      (v.tag.open && !v.tag.used && !v.tag.none && r.tag_price != null && r.fa_class === 'UFA') ? el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', 'data-tip': `One year at the position price, $${r.tag_price}m`, onclick: () => { if (confirm(`Tag ${r.name} at $${r.tag_price}m for one year?`)) { notify(pyJSON(`SESSION.personnel_act('tag', pid=${JSON.stringify(r.pid)})`)); reload(); } } }, `Tag · $${r.tag_price}m`) : '',
      r.restructurable > 0.5 ? el('button', { class: 'btn quiet', style: 'width:auto;padding:3px 8px;font-size:12px', 'data-tip': 'Free cap room by converting base salary to bonus, on the Cap page', onclick: () => { location.hash = '#frontoffice/cap'; } }, 'Restructure Instead') : '')));
  const group = (title, list) => { if (!list.length) return; tbl.append(el('tr', { class: 'grp' }, el('td', { colspan: '9' }, `${title} · ${list.length}`))); for (const r of list) tbl.append(row(r)); };
  group('Expiring', v.expiring); group('Two Years Left', v.two_left);
  if (v.done.length) { tbl.append(el('tr', { class: 'grp' }, el('td', { colspan: '9' }, `Done This Year · ${v.done.length}`))); for (const d of v.done) tbl.append(el('tr', {}, el('td', { colspan: '9', style: 'text-align:left;color:var(--ink-2)' }, `${d.name} (${d.pos}) ${d.kind}` + (d.apy ? ` at $${d.apy}m` + (d.years ? ` over ${d.years}` : '') : '')))); }
  left.append(tbl);
  page.append(left);
  const right = el('section', { class: 'sheet c5' }, el('h2', {}, 'Talks', el('small', {}, `${v.threads.length} open`)));
  for (const t of v.threads) { const w = el('div', { id: 'th-' + t.id }, el('div', { class: 'h5', style: 'padding:10px 12px 0' }, `${t.name} · ${t.pos}`)); w.append(threadBox(t, reload)); right.append(w); }
  if (!v.threads.length) right.append(el('div', { class: 'empty' }, 'Ask an agent to hear his number. Offers are answered in one to three weeks by situation.'));
  right.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Promises', el('small', {}, `${v.promises.length}`)));
  const pl = el('div', { class: 'feed' }); for (const p of v.promises) pl.append(el('div', {}, el('span', {}, p.name), el('span', {}, p.kind.replace(/_/g, ' ')), el('time', {}, `${p.made} · ${p.status}`))); if (!v.promises.length) pl.append(el('div', { class: 'empty' }, 'None made.'));
  right.append(pl); page.append(right);
}

// ---------------------------------------------------------------- Front Office
const FO = { owner: 'Owner', identity: 'Identity', staff: 'Staff', cap: 'Cap' };
function foSecond(cur) { secondRow(Object.entries(FO).map(([k, l]) => [l, '#frontoffice/' + k]), '#frontoffice/' + cur); $('#crumb').textContent = 'Front Office'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'frontoffice')); }

function renderOwner(v) {
  renderRail(v.rail); const page = persPage(); foSecond('owner');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Owner', el('small', {}, `${v.record} · Year ${v.tenure + 1} in the chair`)));
  const g = el('div', { class: 'ownergrid' });
  const l = el('div', {});
  l.append(el('div', { class: 'h5' }, 'Mood'), el('div', { class: 'word-big' }, v.mood), el('div', { class: 'h5', style: 'margin-top:14px' }, 'Your Job'), el('div', { class: 'word-big', style: v.job === 'Hot Seat' ? 'color:var(--danger)' : v.job === 'Warming' ? 'color:var(--decide)' : '' }, v.job),
    el('div', { class: 'expect' }, el('span', {}, 'Expects'), el('span', {}, v.expects), el('span', {}, 'Bar'), el('span', {}, `${Math.round(v.expected_pct * 100)}% wins this year`), el('span', {}, 'Last Season'), el('span', {}, v.prev_pct ? `${Math.round(v.prev_pct * 100)}%` : '—'), el('span', {}, 'Playoff Drought'), el('span', {}, v.drought ? `${v.drought} year${v.drought === 1 ? '' : 's'}` : 'None')));
  g.append(l);
  const r = el('div', {});
  r.append(el('div', { class: 'h5' }, 'What He Weighs'));
  const w = el('div', { class: 'weights' });
  for (const [k, lab, word] of [['wins', 'Winning now', v.patience_word], ['stars', 'Star power', v.stars_word], ['spend', 'Spending on staff', v.spend_word], ['acumen', 'Football acumen', null]]) w.append(el('div', { class: 'wrow' }, el('span', {}, lab + (word ? ` · ${word}` : '')), el('div', { class: 't' }, el('i', { style: `width:${Math.round(v.weights[k] * 100)}%` }))));
  r.append(w, el('div', { class: 'h5', style: 'margin-top:14px' }, 'Staff Budget'), el('div', { class: 'expect' }, el('span', {}, 'Total'), el('span', {}, `$${v.staff_budget.total}m`), el('span', {}, 'Payroll'), el('span', {}, `$${v.staff_budget.payroll}m`), el('span', {}, 'Available'), el('span', {}, `$${v.staff_budget.available}m`)));
  r.append(el('div', { class: 'h5', style: 'margin-top:14px' }, 'Season Reviews'));
  const h = el('div', { class: 'histlist' }); for (const x of v.reviews) h.append(el('div', {}, el('time', {}, x.year), el('span', {}, `${x.record || ''} · ${x.line || ''}`))); if (!v.reviews.length) h.append(el('div', {}, el('time', {}, '—'), el('span', {}, 'He reviews you after each season.')));
  r.append(h); g.append(r); s.append(g); page.append(s);
}

let idDraft = {};
function renderIdentity(v) {
  renderRail(v.rail); const page = persPage(); foSecond('identity');
  const reload = () => renderIdentity(pyJSON(`SESSION.frontoffice('identity'${Object.keys(idDraft).length ? ', preview=' + JSON.stringify(idDraft) : ''})`));
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Identity', el('small', {}, `${v.coach} · Prestige ${v.prestige} · ${v.rigidity >= 0.65 ? 'holds hard to his scheme' : v.rigidity <= 0.4 ? 'bends to his roster' : 'balanced'}`)));
  const arch = el('div', { class: 'arch' });
  for (const a of v.archetypes) arch.append(el('div', { 'data-tip': a.words, onclick: () => { idDraft = {}; for (const [k, val] of Object.entries(a.leans)) idDraft[{ blocking: 'off_blocking', personnel: 'off_personnel', front: 'def_front' }[k] || k] = val; reload(); } }, a.name, el('small', {}, a.side)));
  s.append(arch);
  const grid = el('div', { class: 'fitgrid' });
  const side = (title, leans) => {
    const d = el('div', {}, el('div', { class: 'h5' }, title));
    for (const ln of leans) {
      const cur = v.leans[ln.key], aft = v.after ? v.after[ln.key] : null, val = idDraft[ln.key] != null ? +idDraft[ln.key] : cur;
      const track = el('div', { class: 'tr' }, el('div', { class: 'all' }, el('em', {}, ln.lo), el('em', {}, ln.hi)), el('div', { class: 'band', style: `left:${Math.round(cur * 100)}%;width:2px;background:var(--ink-3)` }), el('div', { class: 'dot', style: `left:${Math.round(val * 100)}%` }));
      const rng = el('input', { type: 'range', min: '0', max: '100', value: String(Math.round(val * 100)) }); rng.onchange = () => { idDraft[ln.key] = +rng.value / 100; reload(); }; track.append(rng);
      d.append(el('div', { class: 'srow' }, el('span', { class: 'l' }, ln.label), track, el('span', { class: 'v' }, aft != null && aft !== cur ? `${cur} → ${aft}` : String(cur))));
    }
    return d;
  };
  grid.append(side('Offense', v.off), side('Defense', v.deff));
  s.append(grid);
  const ch = el('div', { class: 'fitgrid' });
  const cd = el('div', {}, el('div', { class: 'h5' }, 'Structure'));
  for (const c of v.choices) { const row = el('div', { class: 'srow', style: 'grid-template-columns:110px 1fr' }, el('span', { class: 'l' }, c.label)); const b = el('div', { class: 'choice' }); for (const o of c.options) b.append(el('button', { class: 'btn' + ((idDraft[c.key] ?? v.leans[c.key]) === o ? ' go' : ''), onclick: () => { idDraft[c.key] = o; reload(); } }, o)); row.append(b); cd.append(row); }
  ch.append(cd);
  const kd = el('div', {}, el('div', { class: 'h5' }, 'What the Scheme Asks For'), el('div', { class: 'read' }, v.keys.length ? v.keys.join(' · ') : 'No lean strong enough to change how players are graded.'));
  if (v.after) {
    kd.append(el('div', { class: 'h5', style: 'margin-top:12px' }, 'Who Moves'));
    const mk = (list, cls) => { for (const m of list) kd.append(el('div', { class: 'fitrow' }, el('span', {}, m.pos), el('span', {}, m.name), el('span', { class: 'v', style: `color:var(--${cls})` }, (m.delta > 0 ? '+' : '') + m.delta))); };
    mk(v.gainers, 'ok'); mk(v.losers, 'danger'); if (!v.gainers.length && !v.losers.length) kd.append(el('div', { class: 'empty' }, 'Nobody moves more than a point.'));
  }
  ch.append(kd); s.append(ch);
  if (Object.keys(idDraft).length) s.append(el('div', { class: 'confirm' }, el('span', {}, 'Preview. Nothing changes until you confirm; assistants regrade the roster under the new identity.'), el('div', { style: 'display:flex;gap:6px' }, el('button', { class: 'btn go', onclick: () => { const r = pyJSON(`SESSION.frontoffice_act('set_identity', changes=${JSON.stringify(idDraft)})`); notify({ ok: r.ok, line: r.ok ? 'Identity set.' : r.why }); idDraft = {}; reload(); } }, 'Confirm'), el('button', { class: 'btn quiet', onclick: () => { idDraft = {}; reload(); } }, 'Discard'))));
  s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'History', el('small', {}, `${v.history.length} changes`)));
  const h = el('div', { class: 'histlist', style: 'margin:0 14px 14px' }); for (const x of v.history.slice().reverse()) h.append(el('div', {}, el('time', {}, `${x.year} W${x.week ?? 0}`), el('span', {}, x.change))); if (!v.history.length) h.append(el('div', {}, el('time', {}, '—'), el('span', {}, 'The identity you inherited.')));
  s.append(h); page.append(s);
}

function renderStaff(v) {
  renderRail(v.rail); const page = persPage(); foSecond('staff');
  const reload = () => renderStaff(pyJSON(`SESSION.frontoffice('staff')`));
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Staff', el('small', {}, `Budget $${v.budget.total}m · Payroll $${v.budget.payroll}m · Available $${v.budget.available}m`)));
  const grid = el('div', { class: 'staffgrid', style: 'grid-template-columns:repeat(4,1fr)' });
  for (const c of v.cards) {
    if (c.empty) { grid.append(el('div', { class: 'scard open' }, `${c.role_name} · open. Hire from the pool below.`)); continue; }
    const card = el('div', { class: 'scard' }, el('div', { class: 'role' }, c.role + (c.hc_candidate ? ' · head-coach candidate' : '') + (c.disgruntled ? ' · disgruntled' : '')), el('div', { class: 'nm' }, c.name),
      el('div', { class: 'kv' }, el('span', {}, 'Rating'), el('b', {}, c.rating), el('span', {}, 'Prestige'), el('b', {}, c.prestige), el('span', {}, 'Specialty'), el('span', {}, c.specialty || '—'), el('span', {}, 'Age'), el('span', {}, c.age), el('span', {}, 'Contract'), el('span', {}, `${c.years} yr${c.years === 1 ? '' : 's'} · $${(+c.salary).toFixed(2)}m`), el('span', {}, 'Asks'), el('span', {}, `$${(+c.extend_ask).toFixed(2)}m`), el('span', {}, 'Units'), el('span', {}, (c.unit_ranks || []).length ? c.unit_ranks.map(r => `#${r}`).join(' · ') : '—'), el('span', {}, 'Traits'), el('span', {}, c.personality || '—')));
    const acts = el('div', { class: 'acts' });
    acts.append(el('button', { class: 'btn', 'data-tip': `Three more years at his ask, $${(+c.extend_ask).toFixed(2)}m`, onclick: () => { notify(pyJSON(`SESSION.frontoffice_act('staff_extend', role=${JSON.stringify(c.role_key)}, years=3, salary=${c.extend_ask})`)); reload(); } }, 'Extend'));
    if (v.offseason) acts.append(el('button', { class: 'btn warn', onclick: () => { if (confirm(`Release ${c.name}? You owe what is left on his deal.`)) { notify(pyJSON(`SESSION.frontoffice_act('staff_release', role=${JSON.stringify(c.role_key)})`)); reload(); } } }, 'Release'));
    card.append(acts); grid.append(card);
  }
  s.append(grid);
  for (const p of v.poaches) {
    s.append(el('div', { class: 'confirm' }, el('span', {}, `${p.coach} has been offered the ${p.to} head-coaching job. ${p.lean === 'wants' ? 'He wants to go.' : 'He is torn.'}`), el('div', { style: 'display:flex;gap:6px' },
      el('button', { class: 'btn', onclick: () => { notify(pyJSON(`SESSION.frontoffice_act('poach', tid=${p.id}, action='let_go')`)); reload(); } }, 'Let Him Go'),
      el('button', { class: 'btn go', 'data-tip': 'A raise toward what a head job pays, if the budget holds', onclick: () => { const to = prompt('Raise him to ($m a year):'); if (to) { notify(pyJSON(`SESSION.frontoffice_act('poach', tid=${p.id}, action='persuade', raise_years=2, raise_to=${+to})`)); reload(); } } }, 'Persuade'),
      el('button', { class: 'btn warn', 'data-tip': 'He stays, disgruntled, and walks when his deal ends', onclick: () => { notify(pyJSON(`SESSION.frontoffice_act('poach', tid=${p.id}, action='block')`)); reload(); } }, 'Block'))));
  }
  s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'The Pool', el('small', {}, v.offseason ? 'hiring is open' : 'hiring reopens after the season')));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); const list = el('div', { class: 'pad' }); let role = 'oc';
  const draw = () => { list.innerHTML = ''; const tbl = el('table', { class: 'tbl' }); tbl.append(el('tr', {}, el('th', {}, 'Coach'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Rating'), el('th', { class: 'n' }, 'Prestige'), el('th', {}, 'Specialty'), el('th', { class: 'n' }, 'Asks'), el('th', {}, 'Traits'), el('th', {}, ''))); for (const c of v.pools[role]) tbl.append(el('tr', {}, el('td', {}, c.name + (c.hc_candidate ? ' · HC candidate' : '')), el('td', { class: 'n' }, c.age), el('td', { class: 'n' }, ovrCell(c.rating)), el('td', { class: 'n' }, c.prestige), el('td', {}, c.specialty || '—'), el('td', { class: 'n' }, `$${(+c.ask).toFixed(2)}m`), el('td', {}, c.personality || ''), el('td', {}, el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', disabled: v.offseason && +c.ask <= v.budget.available + (v.cards.find(x => x.role_key === role) ? +v.cards.find(x => x.role_key === role).salary : 0) ? null : '', 'data-tip': v.offseason ? 'Three years at his ask; replaces the sitting man' : 'Offseason only', onclick: () => { notify(pyJSON(`SESSION.frontoffice_act('staff_hire', name=${JSON.stringify(c.name)}, years=3)`)); reload(); } }, 'Hire')))); list.append(tbl); };
  for (const [k, l] of [['oc', 'Offensive'], ['dc', 'Defensive'], ['st', 'Special Teams'], ['scout', 'Scouts']]) tabs.append(el('button', { 'aria-pressed': String(role === k), onclick: e => { role = k; tabs.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); draw(); } }, l));
  s.append(tabs, list); draw(); page.append(s);
}

function renderCap(v) {
  renderRail(v.rail); const page = persPage(); foSecond('cap');
  const reload = () => renderCap(pyJSON(`SESSION.frontoffice('cap')`));
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Cap', el('small', {}, `Space $${v.cap_space}m`)));
  const yrs = el('div', { class: 'capyears' });
  const COL = { QB: '#c8102e', RB: '#4cc9f0', WR: '#ffb612', TE: '#3fb37f', OL: '#5aa9d6', DL: '#e5484d', LB: '#a78bfa', DB: '#f59e0b', ST: '#7b8593' };
  for (const y of v.years) {
    const st = el('div', { class: 'stack' }); for (const [g, val] of Object.entries(y.by)) if (val > 0) st.append(el('i', { style: `width:${(val / y.limit * 100).toFixed(1)}%;background:${COL[g]}`, 'data-tip': `${g} $${val}m` })); if (y.dead > 0) st.append(el('i', { style: `width:${(y.dead / y.limit * 100).toFixed(1)}%;background:#3a424c`, 'data-tip': `Penalty $${y.dead}m` }));
    yrs.append(el('div', { class: 'cy' }, el('h4', {}, String(y.year), el('small', {}, `Cap $${y.limit}m · ${y.under_contract} under contract`)), el('div', { class: 'big' + (y.space < 0 ? ' neg' : '') }, `${y.space < 0 ? '−' : ''}$${Math.abs(y.space).toFixed(1)}m`), el('div', { style: 'font-size:11px;color:var(--ink-3)' }, 'space'), st,
      el('div', { class: 'kv' }, ...Object.entries(y.by).filter(([, val]) => val > 0).sort((a, b) => b[1] - a[1]).flatMap(([g, val]) => [el('span', {}, g), el('span', {}, `$${val}m`)]), el('span', {}, 'Penalty'), el('span', {}, `$${y.dead}m`))));
  }
  s.append(yrs);
  const two = el('div', { class: 'restr' });
  const ledger = el('div', {}, el('div', { class: 'h5' }, 'Ledger'));
  const tbl = el('table', { class: 'tbl' }); tbl.append(el('tr', {}, el('th', {}, 'Player'), el('th', {}, 'Pos'), ...v.years.map(y => el('th', { class: 'n' }, String(y.year))), el('th', { class: 'n', 'data-tip': 'Dead cap if cut this year' }, 'Penalty'), el('th', {}, ''), el('th', {}, '')));
  const pv = el('div', {}, el('div', { class: 'h5' }, 'Restructure'), el('div', { class: 'read', id: 'pv' }, 'Pick a man from the ledger to see what converting base salary into signing bonus does to the books.'));
  for (const r of v.rows) tbl.append(el('tr', {}, el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name))), el('td', {}, r.pos), ...r.hits.map(h => el('td', { class: 'n' }, h == null ? '—' : `$${h.toFixed(1)}m`)), el('td', { class: 'n' }, `$${r.penalty.toFixed(1)}m`), el('td', {}, ...r.tags.map(t => el('span', { class: 'badge-sm', style: 'margin-right:4px' }, t))),
    el('td', {}, r.restructurable > 0.5 ? el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', onclick: () => {
      const p = pyJSON(`SESSION.frontoffice_act('restructure_preview', pid=${JSON.stringify(r.pid)})`); const box = $('#pv'); box.innerHTML = '';
      if (!p.ok) { box.append(p.why); return; }
      const amt = el('input', { type: 'number', step: '0.5', min: '0.5', max: String(p.max_convert), value: String(p.convert) }), voids = el('input', { type: 'number', min: '0', max: '2', value: String(p.void_years || 0) });
      const delta = el('div', { class: 'delta' }); const drawD = q => { delta.innerHTML = ''; delta.append(el('div', {}, el('div', { class: 'l' }, 'Saves now'), el('div', { class: 'v good' }, `$${q.saves_now}m`)), el('div', {}, el('div', { class: 'l' }, 'Added later, per year'), el('div', { class: 'v bad' }, q.added_later.length ? `+$${(q.added_later.reduce((a, b) => a + b, 0) / q.added_later.length).toFixed(1)}m` : '—')), el('div', {}, el('div', { class: 'l' }, 'Penalty next year'), el('div', { class: 'v' }, `$${q.dead_if_cut_next_year}m`)), el('div', {}, el('div', { class: 'l' }, 'At void'), el('div', { class: 'v' }, `$${q.dead_at_void}m`))); };
      const re = () => { const q = pyJSON(`SESSION.frontoffice_act('restructure_preview', pid=${JSON.stringify(r.pid)}, amount=${+amt.value}, void_years=${+voids.value})`); if (q.ok) drawD(q); };
      amt.onchange = re; voids.onchange = re;
      box.append(el('b', {}, r.name), ` · up to $${p.max_convert}m of base can convert this year.`, el('div', { class: 'offer' }, el('label', {}, 'Convert ($m)', amt), el('label', {}, 'Void years (0–2)', voids)), delta,
        el('div', { style: 'display:flex;gap:6px;margin-top:10px' }, el('button', { class: 'btn go', onclick: () => { const q = pyJSON(`SESSION.frontoffice_act('restructure', pid=${JSON.stringify(r.pid)}, amount=${+amt.value}, void_years=${+voids.value})`); notify({ ok: q.ok, line: q.ok ? `Restructured. Saves $${q.saves_now}m this year.` : q.why }); reload(); } }, 'Restructure'), el('button', { class: 'btn quiet', onclick: () => { box.innerHTML = ''; box.append('Pick a man from the ledger.'); } }, 'Cancel')));
      drawD(p);
    } }, 'Restructure') : '')));
  ledger.append(tbl); two.append(ledger, pv); s.append(two); page.append(s);
}

// ---------------------------------------------------------------- Draft
const DR = { board: 'Scouting Board', day: 'Draft Day', picks: 'Picks' };
let boardPos = 'All';
function drSecond(cur) { secondRow(Object.entries(DR).map(([k, l]) => [l, '#draft/' + k]), '#draft/' + cur); $('#crumb').textContent = 'Draft'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'draft')); }
function gapCell(g) { if (g == null) return el('span', { class: 'gap' }, '—'); return el('span', { class: 'gap ' + (g > 0 ? 'up' : g < 0 ? 'dn' : '') }, (g > 0 ? '+' : '') + g); }
function flagTags(fl) { const s = el('span', {}); for (const f of fl || []) s.append(el('span', { class: 'flag ' + ({ medical: 'med', character: 'chr', visit: 'vis', riser: 'up', faller: 'dn', 'senior bowl': 'sr' }[String(f).toLowerCase()] || 'ss') }, String(f))); return s; }
const POS_GROUPS = ['All', 'QB', 'HB', 'WR', 'TE', 'OL', 'DL', 'LB', 'DB', 'ST'];
const POS_OF = { QB: ['QB'], HB: ['HB', 'FB'], WR: ['WR'], TE: ['TE'], OL: ['LT', 'LG', 'C', 'RG', 'RT'], DL: ['LEDG', 'DT', 'REDG'], LB: ['MIKE', 'WILL', 'SAM'], DB: ['CB', 'FS', 'SS'], ST: ['K', 'P', 'LS'] };

function renderBoard(v) {
  renderRail(v.rail); const page = persPage(); drSecond('board');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, `Scouting Board · Class of ${v.year}`, el('small', {}, `${v.count} prospects` + (v.scout ? ` · Head Scout ${v.scout.name} (${v.scout.rating})` : ''))));
  if (v.note) { s.append(el('div', { class: 'empty' }, v.note)); page.append(s); return; }
  const filt = el('div', { class: 'filt-pos' }); for (const g of POS_GROUPS) filt.append(el('button', { class: 'btn' + (boardPos === g ? ' go' : ''), onclick: () => { boardPos = g; renderBoard(v); } }, g)); s.append(filt);
  const tbl = el('table', { class: 'tbl' });
  tbl.append(el('tr', {}, el('th', { class: 'n', 'data-tip': 'Where he sits on your board' }, '#'), el('th', {}, 'Prospect'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n', 'data-tip': "Your scouts' grade of him today" }, 'Your Read'), el('th', { class: 'n', 'data-tip': 'The range your scouts see him growing into' }, 'Ceiling'), el('th', { class: 'n', 'data-tip': 'Where the league as a whole has him' }, 'Consensus'), el('th', { class: 'n', 'data-tip': 'Your read minus the consensus: plus means you like him more than the room does' }, 'Gap'), el('th', {}, 'Measurables'), el('th', {}, 'Flags')));
  const rows = v.rows.filter(r => boardPos === 'All' || POS_OF[boardPos].includes(r.pos)).slice(0, 200);
  for (const r of rows) tbl.append(el('tr', { style: r.taken ? 'opacity:.4' : '' }, el('td', { class: 'n' }, r.my_rank), el('td', {}, el('div', { class: 'who' }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, r.college)))), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.mine)), el('td', { class: 'n' }, r.ceiling), el('td', { class: 'n' }, r.cons != null ? `${r.cons} · #${r.cons_rank}` : '—'), el('td', { class: 'n' }, gapCell(r.gap)), el('td', {}, el('span', { class: 'meas' }, [r.forty ? `${r.forty} forty` : null, r.vert ? `${r.vert}" vert` : null, r.bench ? `${r.bench} bench` : null].filter(Boolean).join(' · ') || '—')), el('td', {}, flagTags(r.flags))));
  s.append(tbl); page.append(s);
}

function renderDraftDay(v) {
  renderRail(v.rail); const page = persPage(); drSecond('day');
  const reload = () => renderDraftDay(pyJSON(`SESSION.draft_view('draft_day')`));
  if (!v.live) {
    const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Draft Day'), el('div', { class: 'empty' }, v.note));
    if (v.last) { s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, `${v.last.year} Draft Results`, el('small', {}, `${v.last.rows.length} picks · ${v.last.trades} trades`))); const pm = el('div', { class: 'picksmade' }); for (const r of v.last.rows) pm.append(el('div', { class: 'pk' + (r.mine ? ' next' : '') }, el('span', { class: 'n' }, r.slot), crest(r.team, 30), el('div', { class: 'who' }, el('div', { class: 'nm' }, r.name), el('small', {}, r.pos)), el('span', {}))); s.append(pm); }
    page.append(s); return;
  }
  const left = el('section', { class: 'sheet c8' });
  const cur = v.current;
  left.append(el('div', { class: 'clockbar' }, el('div', { class: 'onclock' }, crest(cur.team, 44), el('div', {}, el('b', {}, `${cur.team.name} ${v.on_user ? 'are on the clock' : 'on the clock'}`), el('span', {}, `Pick ${cur.slot} · Round ${cur.round}` + (cur.original !== cur.team.abbr ? ` · via ${cur.original}` : '')))), el('div', {}),
    el('div', { class: 'timer' }, el('b', {}, `${v.total - v.picks_left} of ${v.total}`), el('span', {}, 'picks made')), el('div', { class: 'timer' }, el('b', {}, v.mine_next.length ? v.mine_next[0].slot : '—'), el('span', {}, v.on_user ? 'your pick now' : 'your next pick'))));
  const ctrl = el('div', { class: 'ctrl' });
  const act = (name, extra) => { const r = pyJSON(`SESSION.draft_act(${JSON.stringify(name)}${extra ? ', ' + extra : ''})`); notify(r); if (r.done) { refresh(); location.hash = '#draft/picks'; } else reload(); };
  ctrl.append(el('button', { class: 'btn go', disabled: v.on_user ? '' : null, onclick: () => act('sim_to_me') }, 'Sim to My Pick'),
    el('button', { class: 'btn', disabled: v.on_user ? null : '', 'data-tip': 'Take the top of your own board', onclick: () => act('auto_pick') }, 'Auto Pick'),
    el('button', { class: 'btn', disabled: v.on_user ? null : '', 'data-tip': 'See which clubs would come up for this pick', onclick: () => { const r = pyJSON(`SESSION.draft_act('offers')`); const box = $('#offers'); box.innerHTML = ''; if (!r.ok) { box.append(el('div', { class: 'empty' }, r.why)); return; } if (!r.offers.length) box.append(el('div', { class: 'empty' }, r.line)); for (const o of r.offers) box.append(el('div', { class: 'offercard' }, el('div', { class: 'from' }, `${o.team.name} · ${o.gm} · wants a ${o.target_pos}`), el('div', { class: 's' }, o.summary.join(' + ')), el('div', { class: 'acts' }, el('button', { class: 'btn go', onclick: () => act('accept_offer', `i=${o.i}`) }, 'Accept'), el('button', { class: 'btn quiet', onclick: () => box.removeChild(box.children[Array.from(box.children).findIndex(c => c.contains(event.target))]) }, 'Pass')))); } }, 'Trade the Pick'),
    el('span', { class: 'sep' }), el('button', { class: 'btn quiet', onclick: () => { if (confirm('Run the rest of the draft on auto? Your picks go to the top of your board.')) act('finish_auto'); } }, 'Finish on Auto'));
  left.append(ctrl, el('div', { id: 'offers' }));
  // best available and your board
  const two = el('div', { class: 'two' });
  const ba = el('div', {}, el('div', { class: 'h5' }, 'Best Available · consensus'));
  for (const r of v.best) ba.append(el('div', { class: 'brow' }, el('div', { class: 'r' }, r.cons_rank ?? '—'), el('div', { class: 'plate' }, el('div', { class: 'nm', style: 'padding-left:8px' }, r.name, el('small', {}, `${r.pos} · ${r.college}`)), el('div', { class: 'pj' }, r.ceiling, el('small', {}, 'your ceiling')), el('div', { class: 'ov' }, r.mine))));
  two.append(ba);
  const mb = el('div', {}, el('div', { class: 'h5' }, 'Your Board'), el('div', { class: 'bhead' }, el('span', {}, '#'), el('span', {}, 'Prospect'), el('span', {}, 'Consensus'), el('span', {}, 'Read')));
  const list = el('div', { class: 'board', style: 'max-height:56vh;overflow-y:auto;padding:6px 0' });
  for (const r of v.board) list.append(el('div', { class: 'brow' }, el('div', { class: 'r' }, r.my_rank), el('div', { class: 'plate' + (v.on_user ? ' pickable' : ''), onclick: v.on_user ? () => { if (confirm(`Take ${r.name}, ${r.pos}, at ${cur.slot}?`)) act('pick', `pid=${JSON.stringify(r.pid)}`); } : null }, el('div', { class: 'nm', style: 'padding-left:8px' }, r.name, el('small', {}, `${r.pos} · ${r.college}` + (r.flags.length ? ' · ' + r.flags.join(', ') : ''))), el('div', { class: 'pj' }, r.cons_rank != null ? `#${r.cons_rank}` : '—', el('small', {}, gapCell(r.gap))), el('div', { class: 'ov' }, r.mine))));
  mb.append(list); two.append(mb); left.append(two);
  if (v.on_user && v.board.length) left.append(el('div', { class: 'pad' }, el('button', { class: 'bigpick', onclick: () => { if (confirm(`Take ${v.board[0].name}, ${v.board[0].pos}, at ${cur.slot}?`)) act('pick', `pid=${JSON.stringify(v.board[0].pid)}`); } }, `PICK ${v.board[0].name.toUpperCase()}`, el('small', {}, `${v.board[0].pos} · top of your board · or tap any man on it`))));
  page.append(left);
  const right = el('section', { class: 'sheet c4' }, el('h2', {}, 'The Clock', el('small', {}, `${v.trades} trades`)));
  const nx = el('div', { class: 'picksmade' }); for (const q of v.clock) nx.append(el('div', { class: 'pk' + (q.mine ? ' next' : '') + (q.sel === cur.sel ? ' now' : '') }, el('span', { class: 'n' }, q.slot), crest(q.team, 30), el('div', { class: 'who' }, el('div', { class: 'nm' }, q.team.nick), el('small', {}, q.sel === cur.sel ? 'on the clock' : '')), el('span', {}))); right.append(nx);
  right.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Picks Made', el('small', {}, 'latest first')));
  const pm = el('div', { class: 'picksmade' }); for (const r of v.results) { const d = r.cons_rank != null ? r.sel - r.cons_rank : null; pm.append(el('div', { class: 'pk' }, el('span', { class: 'n' }, r.slot), crest(r.team, 30), el('div', { class: 'who' }, el('div', { class: 'nm' }, r.name), el('small', {}, r.pos)), el('span', { class: 'cons' + (d != null && d >= 12 ? ' steal' : d != null && d <= -12 ? ' reach' : ''), 'data-tip': 'Consensus rank' }, r.cons_rank != null ? `#${r.cons_rank}` : ''))); }
  if (!v.results.length) pm.append(el('div', { class: 'empty' }, 'No picks yet.'));
  right.append(pm); page.append(right);
}

function renderPicks(v) {
  renderRail(v.rail); const page = persPage(); drSecond('picks');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Picks', el('small', {}, `${v.years.reduce((a, y) => a + y.picks.length, 0)} held` + (v.gone.length ? ` · ${v.gone.length} of yours held elsewhere` : ''))));
  const yrs = el('div', { class: 'years' });
  for (const y of v.years) { const box = el('div', { class: 'yr' }, el('h4', {}, String(y.year), el('small', {}, `${y.picks.length} picks`))); for (const p of y.picks) box.append(el('div', { class: 'pkcard' }, el('div', { class: 'rd' }, p.round), el('div', { class: 'nm' }, p.slot === `R${p.round}` ? `Round ${p.round}` : `Pick ${p.slot}`, el('small', {}, p.own ? 'own' : `via ${p.via.abbr}`)), el('div', {}))); for (const g of v.gone.filter(g => g.year === y.year)) box.append(el('div', { class: 'pkcard gone' }, el('div', { class: 'rd' }, g.round), el('div', { class: 'nm' }, `Round ${g.round}`, el('small', {}, `held by ${g.holder.abbr}`)), el('div', {}))); yrs.append(box); }
  s.append(yrs);
  if (v.last) { s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, `${v.last.year} Draft Results`, el('small', {}, `${v.last.rows.length} picks · ${v.last.trades} trades`))); const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); const pm = el('div', { class: 'picksmade' }); let mine = false; const draw = () => { pm.innerHTML = ''; for (const r of v.last.rows.filter(r => !mine || r.mine)) pm.append(el('div', { class: 'pk' + (r.mine ? ' next' : '') }, el('span', { class: 'n' }, r.slot), crest(r.team, 30), el('div', { class: 'who' }, el('div', { class: 'nm', style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + r.pid; } }, r.name), el('small', {}, r.pos)), el('span', {}))); }; for (const [k, l] of [[false, 'All'], [true, 'Your Picks']]) tabs.append(el('button', { 'aria-pressed': String(mine === k), onclick: e => { mine = k; tabs.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); draw(); } }, l)); s.append(tabs, pm); draw(); }
  page.append(s);
}

// ---------------------------------------------------------------- League
const LG = { standings: 'Standings', schedule: 'Schedule', transactions: 'Transactions', stats: 'Stats', awards: 'Awards', coaching: 'Coaching', almanac: 'Almanac' };
function lgSecond(cur) { secondRow(Object.entries(LG).map(([k, l]) => [l, '#league/' + k]), '#league/' + cur); $('#crumb').textContent = 'League'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'league')); }
const TAGCLS = { Trade: 'trade', Signing: 'sign', Release: 'cut', Draft: 'draft', Extension: 'contract', Waivers: 'wire', 'Call-Up': 'squad', 'Practice Squad': 'squad', 'Injured Reserve': 'wire', Retirement: 'retire', Fired: 'cut', Hired: 'staff', Staff: 'staff', 'Franchise Tag': 'tagg', Restructure: 'contract', 'Position Change': 'squad', 'Hall of Fame': 'hall', Season: 'season' };

function renderStandings(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('standings');
  const s = el('section', { class: 'sheet c8' }, el('h2', {}, 'Standings', el('small', {}, `Week ${v.week ?? '—'} · ${v.games_played} games played`)));
  const grid = el('div', { class: 'divgrid' });
  for (const d of v.divisions) {
    const box = el('div', { class: 'divbox' }, el('h4', {}, d.name)); const t = el('table', { class: 'tbl' });
    t.append(el('tr', {}, el('th', {}, 'Club'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', { class: 'n' }, 'T'), el('th', { class: 'n' }, 'Pct'), el('th', { class: 'n', 'data-tip': 'Points for' }, 'PF'), el('th', { class: 'n', 'data-tip': 'Points against' }, 'PA'), el('th', { class: 'n', 'data-tip': 'Point differential' }, '+/−'), el('th', {}, 'Form')));
    for (const r of d.rows) t.append(el('tr', { style: r.me ? 'background:var(--sheet-2)' : '' }, el('td', {}, stripe(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', { class: 'n' }, r.t), el('td', { class: 'n' }, r.pct.toFixed(3).replace(/^0/, '')), el('td', { class: 'n' }, r.pf), el('td', { class: 'n' }, r.pa), el('td', { class: 'n', style: r.pd > 0 ? 'color:var(--ok)' : r.pd < 0 ? 'color:var(--danger)' : '' }, (r.pd > 0 ? '+' : '') + r.pd), el('td', {}, formDots(r.form))));
    box.append(t); grid.append(box);
  }
  s.append(grid); page.append(s);
  const r = el('section', { class: 'sheet c4' }, el('h2', {}, 'Playoff Picture', el('small', {}, 'seeds as of today')));
  for (const c of v.picture) {
    r.append(el('div', { class: 'h5', style: 'padding:10px 12px 4px' }, c.conf));
    const t = el('table', { class: 'tbl' });
    for (const x of c.seeds) t.append(el('tr', { style: x.me ? 'background:var(--sheet-2)' : '' }, el('td', { style: 'width:34px' }, el('span', { class: 'seed ' + (x.bye ? 'bye' : 'in') }, x.seed)), el('td', {}, stripe(x.club.abbr, x.club.name), x.bye ? el('span', { class: 'clinch' }, 'bye') : ''), el('td', { class: 'n' }, x.record)));
    for (const x of c.hunt) t.append(el('tr', { style: (x.me ? 'background:var(--sheet-2);' : '') + 'opacity:.75' }, el('td', {}, el('span', { class: 'seed bub' }, '·')), el('td', {}, stripe(x.club.abbr, x.club.name), el('span', { class: 'clinch', style: 'color:var(--ink-3)' }, 'in the hunt')), el('td', { class: 'n' }, x.record)));
    r.append(t);
  }
  r.append(el('div', { class: 'legend-line' }, 'Division winners seed one through four; the one seed has the bye. Ties break by the league rules.'));
  page.append(r);
}

function renderSchedule(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('schedule');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Schedule', el('small', {}, `Week ${v.week}`)));
  const nav = el('div', { class: 'wknav' }, el('span', { class: 'lab' }, 'Week')); for (const w of v.weeks) nav.append(el('button', { 'aria-pressed': String(w === v.week), onclick: () => renderSchedule(pyJSON(`SESSION.league_view('schedule', week=${w})`)) }, w)); s.append(nav);
  const grid = el('div', { class: 'wkgrid' });
  for (const g of v.games) {
    const card = el('div', { class: 'game' + (g.mine ? ' mine' : '') + (g.done ? '' : ' upcoming') },
      el('div', { class: 'tm' + (g.done ? (g.winner === g.away.abbr ? ' w' : ' l') : '') }, stripe(g.away.abbr), el('span', {}, g.away.name), el('small', { style: 'color:var(--ink-3)' }, g.away_rec)), el('div', { class: 'sc' }, g.done ? g.ap : ''),
      el('div', { class: 'tm' + (g.done ? (g.winner === g.home.abbr ? ' w' : ' l') : '') }, stripe(g.home.abbr), el('span', {}, g.home.name), el('small', { style: 'color:var(--ink-3)' }, g.home_rec)), el('div', { class: 'sc' }, g.done ? g.hp : ''),
      el('div', { class: 'meta' }, g.done ? 'Final' + (g.mine ? ' · your game' : '') : (g.mine ? 'Your game' : 'Upcoming')));
    if (g.mine && g.done) card.onclick = () => { location.hash = '#gameday'; };
    grid.append(card);
  }
  s.append(grid);
  if (v.byes.length) s.append(el('div', { class: 'legend-line' }, 'Byes: ' + v.byes.map(b => b.abbr).join(', ')));
  page.append(s);
}

let txFilter = 'All', txMine = false;
function renderTransactions(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('transactions');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Transactions', el('small', {}, `${v.rows.length} most recent`)));
  const tabs = el('div', { class: 'tools' }); const tb = el('div', { class: 'tabs' });
  for (const t of ['All', ...v.tags]) tb.append(el('button', { 'aria-pressed': String(txFilter === t), onclick: () => { txFilter = t; renderTransactions(v); } }, t));
  tabs.append(tb, el('button', { class: 'btn' + (txMine ? ' go' : ''), style: 'margin-left:auto', onclick: () => { txMine = !txMine; renderTransactions(v); } }, 'Your Club'));
  s.append(tabs);
  const feed = el('div', {});
  let n = 0;
  for (const r of v.rows) { if (txFilter !== 'All' && r.tag !== txFilter) continue; if (txMine && !r.mine) continue; n++; feed.append(el('div', { class: 'trow' + (r.mine ? ' mine' : '') }, el('time', {}, `${r.year} · ${r.week ? 'Wk ' + r.week : (r.phase || '')}`), el('span', { class: 'tag ' + (TAGCLS[r.tag] || '') }, r.tag), el('span', { class: 'txt' }, r.line), r.pid ? el('span', { class: 'go', onclick: () => { location.hash = '#club/player/' + r.pid; } }, 'Card') : el('span', {}))); }
  if (!n) feed.append(el('div', { class: 'empty' }, 'Nothing here yet.'));
  s.append(feed); page.append(s);
}

function renderStats(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('stats');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'League Leaders', el('small', {}, String(v.year))));
  if (v.years.length > 1) { const nav = el('div', { class: 'wknav' }, el('span', { class: 'lab' }, 'Season')); for (const y of v.years) nav.append(el('button', { style: 'width:auto;padding:0 8px', 'aria-pressed': String(y === v.year), onclick: () => renderStats(pyJSON(`SESSION.league_view('stats', year=${y})`)) }, y)); s.append(nav); }
  const grid = el('div', { class: 'leaders' });
  for (const b of v.boxes) { const box = el('div', { class: 'lbox' }, el('h4', {}, b.title, el('small', {}, b.unit))); b.rows.forEach((r, i) => box.append(el('div', { class: 'lrow', style: r.mine ? 'background:var(--sheet-2)' : '' }, el('span', { class: 'r' }, i + 1), el('div', { class: 'nm', style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + r.pid; } }, r.name, el('small', {}, `${r.pos} · ${r.team}`)), el('span', { class: 'v' }, r.v)))); grid.append(box); }
  if (!v.boxes.length) grid.append(el('div', { class: 'empty' }, 'No games played this season yet.'));
  s.append(grid); page.append(s);
}

function renderAwards(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('awards');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Awards', el('small', {}, String(v.year))));
  if (v.years.length > 1) { const nav = el('div', { class: 'wknav' }, el('span', { class: 'lab' }, 'Season')); for (const y of v.years) nav.append(el('button', { style: 'width:auto;padding:0 8px', 'aria-pressed': String(y === v.year), onclick: () => renderAwards(pyJSON(`SESSION.league_view('awards', year=${y})`)) }, y)); s.append(nav); }
  if (v.note) { s.append(el('div', { class: 'empty' }, v.note)); page.append(s); return; }
  const grid = el('div', { class: 'awgrid' });
  for (const r of v.rows) grid.append(el('div', { class: 'aw' + (r.mine ? ' mine' : ''), style: r.mine ? 'border-color:var(--club)' : '' }, el('div', { class: 'trophy' }, r.award.split(' ').map(w => w[0]).join('').slice(0, 4)), el('div', {}, el('div', { class: 'lbl' }, r.award), el('div', { class: 'who', style: r.pid ? 'cursor:pointer' : '', onclick: r.pid ? () => { location.hash = '#club/player/' + r.pid; } : null }, r.name), el('div', { class: 'why' }, `${r.pos}${r.team ? ' · ' + r.team.name : ''}`))));
  s.append(grid);
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); const ap = el('div', { class: 'allpro' }); let team = 'first';
  const draw = () => { ap.innerHTML = ''; const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Pos'), el('th', {}, 'Player'), el('th', {}, 'Club'))); for (const r of v[team]) t.append(el('tr', { style: r.mine ? 'background:var(--sheet-2)' : '' }, el('td', {}, r.pos), el('td', {}, el('span', { style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + r.pid; } }, r.name)), el('td', {}, r.team))); ap.append(t); };
  for (const [k, l] of [['first', 'All-Pro First Team'], ['second', 'All-Pro Second Team']]) tabs.append(el('button', { 'aria-pressed': String(team === k), onclick: e => { team = k; tabs.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); e.currentTarget.setAttribute('aria-pressed', 'true'); draw(); } }, l));
  s.append(tabs, ap); draw(); page.append(s);
}

function renderCoaching(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('coaching');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Coaching', el('small', {}, v.carousel_open ? 'the carousel is turning' : 'seats, hottest first')));
  const g = el('div', { class: 'coachgrid' });
  const seats = el('div', {}, el('div', { class: 'h5' }, 'The Seats'));
  for (const x of v.seats) seats.append(el('div', { class: 'crow', style: x.me ? 'background:var(--sheet-2)' : '' }, crest(x.club, 30), el('div', { class: 'nm' }, x.coach, el('small', {}, `${x.club.name} · ${x.record} · year ${x.tenure + 1}` + (x.history.length ? ` · before: ${x.history.map(h => h.name).filter(n => n !== x.coach).slice(-2).join(', ')}` : ''))), el('span', { style: 'font-size:12.5px;color:' + (x.seat === 'Hot Seat' ? 'var(--danger)' : x.seat === 'Warming' ? 'var(--decide)' : 'var(--ink-2)') }, x.seat), el('div', { class: 'pr' }, x.prestige ?? '—', el('small', {}, 'prestige'))));
  g.append(seats);
  const pool = el('div', {}, el('div', { class: 'h5' }, 'Head-Coaching Candidates'));
  for (const c of v.pool) pool.append(el('div', { class: 'crow', style: 'grid-template-columns:1fr 64px' }, el('div', { class: 'nm' }, c.name, el('small', {}, `${c.background || 'coordinator'}` + (c.seasons ? ` · ${c.seasons} seasons as a head coach, ${Math.round((c.win_pct || 0) * 100)}% wins, ${c.playoffs} playoff trips` : ' · first head job'))), el('div', { class: 'pr' }, c.prestige, el('small', {}, 'prestige'))));
  if (!v.pool.length) pool.append(el('div', { class: 'empty' }, 'The pool fills in the offseason.'));
  g.append(pool); s.append(g); page.append(s);
}

function renderAlmanac(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('almanac');
  const s = el('section', { class: 'sheet c12', id: 'alm' }, el('h2', {}, 'Almanac', el('small', {}, `${v.seasons.length} seasons on record`)));
  if (v.note) { s.append(el('div', { class: 'empty' }, v.note)); page.append(s); return; }
  const grid = el('div', { class: 'recgrid' });
  const ch = el('div', { class: 'lbox' }, el('h4', {}, 'Champions')); for (const x of v.seasons) ch.append(el('div', { class: 'lrow champ', style: x.mine ? 'background:var(--sheet-2)' : '' }, el('span', { class: 'r' }, x.year), el('div', { class: 'nm' }, x.champion ? stripe(x.champion.abbr, x.champion.name) : '—', el('small', {}, (x.runner_up ? `over ${x.runner_up.name}` : '') + (x.mvp ? ` · MVP ${x.mvp}` : ''))), el('span', {}))); if (!v.seasons.length) ch.append(el('div', { class: 'empty' }, 'None yet.')); grid.append(ch);
  const rs = el('div', { class: 'lbox' }, el('h4', {}, 'Single-Season Records')); for (const r of v.records) if (r.season) rs.append(el('div', { class: 'lrow norank' }, el('div', { class: 'nm' }, r.stat, el('small', {}, `${r.season.name} · ${r.season.year}`)), el('span', { class: 'v' }, r.season.v))); grid.append(rs);
  const rc = el('div', { class: 'lbox' }, el('h4', {}, 'Career Records')); for (const r of v.records) if (r.career) rc.append(el('div', { class: 'lrow norank' }, el('div', { class: 'nm' }, r.stat, el('small', {}, r.career.name)), el('span', { class: 'v' }, r.career.v))); grid.append(rc);
  s.append(grid);
  s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Hall of Fame', el('small', {}, `${v.hall.length} inducted`)));
  const hall = el('div', { class: 'hall' }); for (const h of v.hall) hall.append(el('div', { class: 'bust' }, el('div', { class: 'nm' }, h.name), el('div', { class: 'pos' }, `${h.pos} · ${h.seasons || '?'} seasons`), el('div', { class: 'why' }, h.why), el('div', { class: 'yr' }, `Class of ${h.inducted}`))); if (!v.hall.length) hall.append(el('div', { class: 'empty' }, 'A retired man is eligible five offseasons after he stops.'));
  s.append(hall); page.append(s);
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
  s.append(el('h2', {}, `Week ${v.week} · ${v.away ? 'at' : 'vs'} ${v.opp.name}`, el('small', {}, `${v.coordinators.oc ? `OC ${v.coordinators.oc.name} (${v.coordinators.oc.rating})` : ''}${v.coordinators.dc ? ` · DC ${v.coordinators.dc.name} (${v.coordinators.dc.rating})` : ''} · leans move inside the coordinators' range`)));
  // suggestions
  const sug = el('div', { class: 'sugs' });
  sug.append(el('div', { class: 'h5' }, 'The Report Suggests', el('span', {}, `${v.suggestions.filter(x => x.taken).length} of ${v.suggestions.length} taken`)));
  for (const x of v.suggestions) sug.append(el('div', { class: 'sug-row' + (x.taken ? ' on' : '') }, el('div', { class: 't' }, x.text, el('small', {}, `${x.side} · ${x.why}`)), el('div', { class: 'a' }, x.taken ? el('button', { class: 'btn quiet', onclick: () => { notify(pyJSON(`SESSION.plan_act('untake', i=${x.i})`)); reload(); } }, 'Put Back') : el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.plan_act('take', i=${x.i})`)); reload(); } }, 'Take'))));
  if (!v.suggestions.length) sug.append(el('div', { class: 'empty' }, 'The report has nothing to add this week; the plan is the coordinators\' own.'));
  else sug.append(el('div', { style: 'display:flex;gap:6px;padding:8px 0 0' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON('SESSION.plan_take_all()')); reload(); } }, 'Accept All'), el('span', { class: 'count', style: 'align-self:center' }, 'or take them one at a time')));
  s.append(sug);
  // leans
  const plan = el('div', { class: 'plan' });
  const side = (title, leans) => {
    const d = el('div', {}, el('div', { class: 'h5' }, title));
    for (const ln of leans) {
      const lo = Math.max(0, ln.min), hi = Math.min(1, ln.max), span = Math.max(0.02, hi - lo);
      const pos = x => `${Math.round((Math.min(hi, Math.max(lo, x)) - lo) / span * 100)}%`;
      const moved = Math.abs(ln.value - ln.base) > 1e-6;
      const track = el('div', { class: 'track' }, el('div', { class: 'range', style: 'left:0;right:0' }), el('div', { class: 'tick', style: `left:${pos(ln.base)}` }), el('div', { class: 'knob' + (moved ? ' sug' : ''), style: `left:${pos(ln.value)}` }));
      const rng = el('input', { type: 'range', min: String(Math.round(lo * 1000)), max: String(Math.round(hi * 1000)), value: String(Math.round(ln.value * 1000)) }); rng.onchange = () => { pyJSON(`SESSION.plan_act('set_lean', key=${JSON.stringify(ln.key)}, value=${+rng.value / 1000})`); reload(); }; track.append(rng);
      d.append(el('div', { class: 'lean' }, el('div', { class: 'l' }, ln.label, el('small', {}, `${ln.lo} ← → ${ln.hi}`)), track, el('div', { class: 'v' + (moved ? ' sug' : '') }, moved ? `${ln.value > ln.base ? '+' : ''}${Math.round((ln.value - ln.base) * 100)}` : 'base')));
    }
    return d;
  };
  const off = side('Offense', v.leans.filter(l => l.side === 'offense')), deff = side('Defense', v.leans.filter(l => l.side === 'defense'));
  // depth mix as three numbers
  const dm = el('div', { class: 'lean', style: 'grid-template-columns:130px 1fr' }, el('div', { class: 'l' }, 'Depth of Target', el('small', {}, 'short · medium · deep')));
  const inputs = v.depth.value.map((x, i) => el('input', { type: 'number', min: '5', max: '90', value: String(pct(x)), style: 'width:56px;font-family:var(--mono);font-size:12.5px;background:var(--board);color:var(--ink);border:1px solid var(--rule-2);padding:4px 6px' }));
  const dmrow = el('div', { style: 'display:flex;gap:6px;align-items:center;font-size:11.5px;color:var(--ink-3)' }); v.depth.labels.forEach((l, i) => dmrow.append(el('span', {}, l), inputs[i], el('span', {}, '%'))); dmrow.append(el('button', { class: 'btn', style: 'padding:3px 8px;font-size:12px', onclick: () => { pyJSON(`SESSION.plan_act('set_depth', short=${+inputs[0].value}, medium=${+inputs[1].value}, deep=${+inputs[2].value})`); reload(); } }, 'Set'), el('span', {}, `base ${v.depth.base.map(pct).join(' · ')}`));
  dm.append(dmrow); off.append(dm);
  plan.append(off, deff); s.append(plan);
  // decisions
  s.append(el('div', { class: 'h5', style: 'padding:10px 14px 6px' }, 'Game-Week Decisions'));
  const dec = el('div', { class: 'decide' });
  const prot = el('div', { class: 'dcard' }, el('div', { class: 'k' }, 'Protection'), el('div', { class: 's' }, v.protection.options.find(o => o.key === v.protection.value)?.word || v.protection.value)); const po = el('div', { class: 'opts' }); for (const o of v.protection.options) po.append(el('button', { class: 'btn chip' + (o.key === v.protection.value ? ' go' : ''), onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='protection', value=${JSON.stringify(o.key === v.protection.base ? '' : o.key)})`); reload(); } }, o.word)); prot.append(po); dec.append(prot);
  const tr = el('div', { class: 'dcard' }, el('div', { class: 'k' }, 'Corner Travel'), el('div', { class: 's' }, v.travel ? 'CB1 follows their best receiver' : 'Corners stay by side')); tr.append(el('div', { class: 'opts' }, el('button', { class: 'btn chip' + (v.travel ? ' go' : ''), onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='travel', value=${v.travel ? 'False' : 'True'})`); reload(); } }, v.travel ? 'Travel on' : 'Travel off'))); dec.append(tr);
  const br = el('div', { class: 'dcard' }, el('div', { class: 'k' }, 'Bracket'), el('div', { class: 's' }, v.bracket ? `Double ${v.bracket.name} on the shots` : 'Nobody doubled')); const bo = el('div', { class: 'opts' }, el('button', { class: 'btn chip' + (!v.bracket ? ' go' : ''), onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='bracket', value='')`); reload(); } }, 'None')); for (const w of v.their_wrs) bo.append(el('button', { class: 'btn chip' + (v.bracket && v.bracket.pid === w.pid ? ' go' : ''), onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='bracket', value=${JSON.stringify(w.pid)})`); reload(); } }, `${w.name} · ${w.ovr}`)); br.append(bo); dec.append(br);
  s.append(dec);
  s.append(el('div', { class: 'foot' }, el('button', { class: 'btn quiet', onclick: () => { notify(pyJSON(`SESSION.plan_act('reset')`)); reload(); } }, "Back to the Coordinators' Plan"), el('span', { class: 'count', style: 'margin-left:auto' }, v.forecast && v.forecast.text ? v.forecast.text : 'The plan you leave here is what the game runs on Sunday.')));
  page.append(s);
}

function renderReport(v) {
  renderRail(v.rail); const page = persPage(); gpSecond('report');
  const s = el('section', { class: 'sheet c12' });
  if (v.off) { s.append(el('h2', {}, 'Opponent Report'), el('div', { class: 'empty' }, v.note)); page.append(s); return; }
  s.append(el('h2', {}, `${v.opp.name} · ${v.record}`, el('small', {}, `Week ${v.week} · ${v.away ? 'away' : 'home'}` + (v.coach && v.coach.name ? ` · ${v.coach.name}, prestige ${v.coach.prestige}${v.coach.tree ? ' · ' + v.coach.tree : ''}` : ''))));
  s.append(el('div', { class: 'h5', style: 'padding:10px 14px 6px' }, 'Tendencies', el('span', {}, v.tendencies ? `${v.tendencies.games} games in` : 'nothing on film yet')));
  const tg = el('div', { class: 'tendgrid' });
  const T = [['pass_rate', 'Pass rate', 'of plays'], ['pa_rate', 'Play action', 'of dropbacks'], ['deep', 'Deep shots', 'of throws'], ['motion', 'Motion', 'of plays'], ['fourth_go', 'Goes on fourth', 'of chances'], ['blitz', 'Blitz', 'of snaps'], ['man', 'Man coverage', 'of pass snaps'], ['two_high', 'Two-high', 'of snaps'], ['box8', 'Eight in the box', 'of snaps']];
  for (const [k, lab, unit] of T) { const tv = v.tendencies ? v.tendencies[k] : null; tg.append(el('div', { class: 'tend', 'data-tip': `${v.opp.abbr} ${tv ?? '—'}% · NFL ${v.league_tend ? v.league_tend[k] : '—'}%` }, el('div', { class: 'k' }, lab), el('div', { class: 'v' }, tv != null ? `${tv}%` : '—'), el('div', { class: 'cmp' }, unit, v.league_tend ? el('span', {}, ' · NFL ', el('b', {}, `${v.league_tend[k]}%`)) : ''))); }
  s.append(tg);
  const two = el('div', { class: 'two' });
  const units = (title, list, color) => { const d = el('div', {}, el('div', { class: 'h5' }, title)); for (const u of list) { const q = u.rank <= 8 ? 'var(--ok)' : u.rank >= 24 ? 'var(--danger)' : 'var(--rule-hi)'; d.append(el('div', { class: 'unitrow' }, el('span', {}, u.unit), el('div', { class: 't' }, el('i', { style: `width:${Math.round((1 - (u.rank - 1) / Math.max(1, u.of - 1)) * 100)}%;background:${q}` })), el('span', { class: 'v' }, `${u.rank} of ${u.of}`))); } return d; };
  two.append(units(`${v.opp.abbr} Units`, v.units), units('Your Units', v.my_units)); s.append(two);
  const three = el('div', { class: 'two' });
  const men = el('div', {}, el('div', { class: 'h5' }, 'The Men Who Matter')); for (const p of v.stars) men.append(el('div', { class: 'plate', style: 'margin-bottom:4px;cursor:pointer', onclick: () => { location.hash = '#club/player/' + p.pid; } }, el('div', { class: 'no' }, p.pos), el('div', { class: 'nm' }, p.name), el('div', { class: 'ov' }, p.ovr))); if (v.injured.length) { men.append(el('div', { class: 'h5', style: 'margin-top:10px' }, 'Their Injured Starters')); for (const p of v.injured) men.append(el('div', { style: 'font-size:13px;color:var(--ink-2);padding:3px 0' }, `${p.name} (${p.pos}) · back week ${p.back}`)); }
  const sw = el('div', {}, el('div', { class: 'h5' }, 'Strengths')); for (const x of v.strengths) sw.append(el('div', { style: 'font-size:13px;color:var(--ok);padding:3px 0' }, x)); if (!v.strengths.length) sw.append(el('div', { style: 'font-size:13px;color:var(--ink-3)' }, 'No unit in the top eight.')); sw.append(el('div', { class: 'h5', style: 'margin-top:10px' }, 'Weaknesses')); for (const x of v.weaknesses) sw.append(el('div', { style: 'font-size:13px;color:var(--danger);padding:3px 0' }, x)); if (!v.weaknesses.length) sw.append(el('div', { style: 'font-size:13px;color:var(--ink-3)' }, 'No unit in the bottom nine.'));
  three.append(men, sw); s.append(three);
  s.append(el('div', { class: 'h5', style: 'padding:10px 14px 6px' }, "What We'd Do", el('span', {}, 'act on This Week')));
  const sug = el('div', { class: 'sugs' }); for (const x of v.suggestions) sug.append(el('div', { class: 'sug-row' + (x.taken ? ' on' : '') }, el('div', { class: 't' }, x.text, el('small', {}, `${x.side} · ${x.why}`)), el('div', { class: 'a' }, el('span', { class: 'count' }, x.taken ? 'taken' : '')))); if (!v.suggestions.length) sug.append(el('div', { class: 'empty' }, 'Nothing to add this week.'));
  s.append(sug, el('div', { class: 'foot' }, el('button', { class: 'btn go', onclick: () => { location.hash = '#gameplan/week'; } }, 'Go to This Week'), el('span', { class: 'count', style: 'margin-left:auto' }, v.forecast && v.forecast.text ? v.forecast.text : '')));
  page.append(s);
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
  if (r && /^Week \d+$/.test(r.done)) { location.hash = '#gameday'; renderGameDay(pyJSON('SESSION.gameday_view()')); } else if (r && /on the clock/.test(r.done)) { location.hash = '#draft/day'; renderDraftDay(pyJSON(`SESSION.draft_view('draft_day')`)); } else refresh();
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
  window.addEventListener('hashchange', () => { if (location.hash.startsWith('#portal/inbox/')) openMessage(+location.hash.split('/').pop()); else if (location.hash.startsWith('#portal') || location.hash === '') refresh(); else if (location.hash.startsWith('#gameday')) renderGameDay(pyJSON('SESSION.gameday_view()')); else if (location.hash.startsWith('#club/player/')) renderCard(pyJSON(`SESSION.club_card(${JSON.stringify(location.hash.split('/').pop())})`)); else if (location.hash.startsWith('#club/depth')) renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(depthPkg)})`)); else if (location.hash.startsWith('#club')) { clubTab = location.hash.startsWith('#club/ps') ? 'ps' : 'active'; renderRoster(pyJSON('SESSION.club_roster()')); } else if (location.hash.startsWith('#gameplan')) { const sub = location.hash.split('/')[1] || 'week'; if (sub === 'report') renderReport(pyJSON(`SESSION.plan_view('report')`)); else renderThisWeek(pyJSON(`SESSION.plan_view('this_week')`)); } else if (location.hash.startsWith('#league')) { const sub = location.hash.split('/')[1] || 'standings'; const fn = { standings: renderStandings, schedule: renderSchedule, transactions: renderTransactions, stats: renderStats, awards: renderAwards, coaching: renderCoaching, almanac: renderAlmanac }[sub] || renderStandings; fn(pyJSON(`SESSION.league_view(${JSON.stringify(sub in LG ? sub : 'standings')})`)); } else if (location.hash.startsWith('#draft')) { const sub = location.hash.split('/')[1] || 'board'; if (sub === 'day') renderDraftDay(pyJSON(`SESSION.draft_view('draft_day')`)); else if (sub === 'picks') renderPicks(pyJSON(`SESSION.draft_view('picks')`)); else renderBoard(pyJSON(`SESSION.draft_view('board')`)); } else if (location.hash.startsWith('#frontoffice')) { const sub = location.hash.split('/')[1] || 'owner'; if (sub === 'identity') { idDraft = {}; renderIdentity(pyJSON(`SESSION.frontoffice('identity')`)); } else if (sub === 'staff') renderStaff(pyJSON(`SESSION.frontoffice('staff')`)); else if (sub === 'cap') renderCap(pyJSON(`SESSION.frontoffice('cap')`)); else renderOwner(pyJSON(`SESSION.frontoffice('owner')`)); } else if (location.hash.startsWith('#personnel')) { const sub = location.hash.split('/')[1] || 'trades'; if (sub === 'fa') renderFA(pyJSON(`SESSION.personnel('free_agency')`)); else if (sub === 'wire') renderWire(pyJSON(`SESSION.personnel('waivers')`)); else if (sub === 'extensions') renderExtensions(pyJSON(`SESSION.personnel('extensions')`)); else { if (!tradeState.keep) { tradeState.a = []; tradeState.b = []; } tradeState.keep = false; renderTrades(pyJSON(`SESSION.personnel('trades'${tradeState.other ? ', other=' + JSON.stringify(tradeState.other) : ''})`)); } } else { const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = '1fr'; page.append(el('section', { class: 'sheet' }, el('h2', {}, location.hash.slice(1).split('/')[0].replace(/^\w/, c => c.toUpperCase())), el('div', { class: 'empty' }, 'This page is next to be wired.'), el('div', { class: 'foot' }, el('button', { class: 'btn', onclick: () => { location.hash = '#portal'; } }, 'Back to Portal')))); } });
})();
