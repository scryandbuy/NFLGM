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

// the desk card's second button: where the decision is made
const DESK_GO = { Trade: ['Trades', '#personnel/trades'], Contract: ['Negotiate', '#personnel/extensions'], Staff: ['Staff', '#frontoffice/staff'], Assistants: ['Game Plan', '#gameplan/week'], Wire: ['Waivers', '#personnel/wire'] };
function deskAction(kind) { const g = DESK_GO[kind]; return g ? el('a', { class: 'btn go', href: g[1] }, g[0]) : ''; }

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
      (extra || []).forEach((t, i) => box.append(el('div', { class: 'side-row' + (i === 0 ? ' sep' : '') }, el('span', { class: 'lab' }, t.label, t.sub ? el('em', {}, t.sub) : ''), el('span', { class: 'rk', style: 'font-size:15px' }, t.left), el('span', { class: 'mid' }, 'vs'), el('span', { class: 'rk', style: 'font-size:15px' }, t.right))));
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
          el('div', { class: 'b', style: 'margin-top:6px' }, el('span', { class: 'lbl', style: 'font-size:11px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.04em' }, 'Plan Change '), el('span', { style: 'font-family:var(--mono);font-size:12px' }, sg.change || '—')),
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
    el('div', { class: 'big', style: 'font-size:26px' }, fo.owner_mood), el('div', { class: 'muted', style: 'font-size:13px;margin:2px 0 10px' }, fo.expects || ''),
    el('div', { class: 'kv' }, el('span', {}, 'Your Prestige'), el('b', {}, fo.prestige ?? '—'), el('span', {}, 'Job Security'), el('b', { style: fo.job === 'Hot Seat' ? 'color:var(--danger)' : fo.job === 'Warming' ? 'color:var(--decide)' : '' }, fo.job), el('span', {}, 'Scouting'), el('b', {}, fo.scouting_rank ? `${fo.scouting_rank}${ord(fo.scouting_rank)}` : '—'))),
    el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#frontoffice/identity' }, 'Coaching Identity'), el('a', { class: 'btn', href: '#draft' }, 'Scouting Board'), el('a', { class: 'btn quiet', href: '#league/almanac' }, 'Almanac')));
  foS.classList.add('c4'); page.append(foS);

  // standings and season
  const st = v.standings;
  const table = el('table', {}, el('tr', {}, el('th', {}, ''), el('th', {}, 'Club'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', {}, 'Form'), el('th', { class: 'n' }, 'PF'), el('th', { class: 'n' }, 'PA'), el('th', { class: 'n' }, 'PD')),
    ...st.rows.map(r => el('tr', { class: r.me ? 'me' : '' }, el('td', {}, ''), el('td', {}, stripe(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', {}, formDots(r.form)), el('td', { class: 'n' }, r.pf), el('td', { class: 'n' }, r.pa), el('td', { class: 'n' }, (r.pd > 0 ? '+' : '') + r.pd))));
  const stS = sheet(st.division, '', table, el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#league' }, 'Full Standings')));
  stS.classList.add('c6'); page.append(stS);

  const strip = el('div', { class: 'strip' }, ...v.season.games.map(g => g.bye ? el('div', { class: 'wk bye' }, '—', el('small', {}, 'bye')) : el('div', { class: 'wk' + (g.result ? ' ' + g.result.toLowerCase() : '') + (view.rail.advance.title === `Play Week ${g.week}` ? ' now' : ''), 'data-tip': g.score ? `${g.home ? 'vs' : 'at'} ${g.opp} · ${g.score}` : null }, g.result || g.week, el('small', {}, `${g.home ? '' : '@'}${g.opp}`))));
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
  page.append(el('section', { class: 'sheet' }, el('h2', {}, m.subject, el('small', {}, `${m.sender || ''} · ${m.year} Week ${m.week}`)), el('div', { class: 'pad', style: 'max-width:70ch;line-height:1.5;color:var(--ink-2)' }, m.body), el('div', { class: 'foot' }, el('button', { class: 'btn', onclick: () => refresh() }, 'Back to Portal'))));
}


// ---------------------------------------------------------------- Game Day
function renderGameDay(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Game Day';
  $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'gameday'));
  $('#second').innerHTML = ''; document.body.classList.add('no-second');
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
  let shown = 1, shownPlays = null;      // shownPlays: within the last shown drive, how many plays are revealed (null = all)
  const body = el('div', { class: 'ticker' });
  const filt = { mode: 'all' };
  const draw = () => {
    body.innerHTML = '';
    g.drives.slice(0, shown).forEach((d, di) => {
      const last = di === shown - 1; const plays = (last && shownPlays != null) ? d.plays.slice(0, shownPlays) : d.plays;
      body.append(el('div', { class: 'drive' }, `Drive ${d.n} · ${d.off} · Q${d.quarter}` + ((last && shownPlays != null) ? '' : ` · ${d.plays_n} play${d.plays_n === 1 ? '' : 's'}, ${Math.round(d.yards)} yard${Math.round(d.yards) === 1 ? '' : 's'}` + (d.result ? ` · ${String(d.result).toLowerCase()}` : '') + ` · ${d.score}`)));
      for (const p of plays) {
        if (!p.text) continue;
        if (filt.mode === 'key' && !['score', 'turnover', 'loss'].includes(p.kind) && !(p.type === 'complete' && /for (\d\d) yards/.test(p.text) && +p.text.match(/for (\d\d) yards/)[1] >= 15)) continue;
        if (filt.mode === 'score' && p.kind !== 'score') continue;
        const line = el('div', { class: 'pl ' + p.kind }); if (p.head) line.append(el('span', { class: 'dn' }, p.head), '  '); line.append(p.text); body.append(line);
      }
    });
    tick.querySelector('h2 small').textContent = (shown >= g.drives.length && shownPlays == null) ? 'Final' : `Drive ${shown} of ${g.drives.length}` + (shownPlays != null ? ` · play ${shownPlays}` : '');
    body.scrollTop = body.scrollHeight;
  };
  const nextPlay = () => { const d = g.drives[shown - 1]; if (shownPlays == null) { if (shown >= g.drives.length) return; shown++; shownPlays = 1; } else if (shownPlays < d.plays.length) shownPlays++; else { if (shown >= g.drives.length) { shownPlays = null; } else { shown++; shownPlays = 1; } } draw(); };
  const ctrl = el('div', { class: 'ctrl2' },
    el('button', { class: 'btn', 'data-tip': 'One snap at a time', onclick: nextPlay }, 'Next Play'),
    el('button', { class: 'btn go', onclick: () => { shownPlays = null; shown = Math.min(g.drives.length, shown + 1); draw(); } }, 'Next Drive'),
    el('button', { class: 'btn', onclick: () => { shownPlays = null; const q = g.drives[Math.min(shown, g.drives.length) - 1].quarter; while (shown < g.drives.length && g.drives[shown].quarter === q) shown++; shown = Math.min(g.drives.length, shown + 1); draw(); } }, 'Next Quarter'),
    el('button', { class: 'btn', 'data-tip': 'Run to the break', onclick: () => { shownPlays = null; while (shown < g.drives.length && g.drives[shown].quarter <= 2) shown++; draw(); } }, 'To Halftime'),
    el('button', { class: 'btn', onclick: () => { shownPlays = null; shown = g.drives.length; draw(); } }, 'Finish Game'),
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
  const awayFirst = arr => [...arr.filter(r => r.team === g.away.abbr), ...arr.filter(r => r.team !== g.away.abbr)];
  g.box.passing = awayFirst(g.box.passing); g.box.rushing = awayFirst(g.box.rushing); g.box.receiving = awayFirst(g.box.receiving); g.box.defense = awayFirst(g.box.defense);
  box.append(th('Passing', 'C/A', 'Yds', 'TD', 'INT', 'Lng')); g.box.passing.forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.ca), el('td', {}, r.yds), el('td', {}, r.td), el('td', {}, r.int_), el('td', {}, r.lng ?? ''))));
  box.append(th('Rushing', 'Att', 'Yds', 'TD', '', 'Lng')); g.box.rushing.forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.att), el('td', {}, r.yds), el('td', {}, r.td), el('td', {}, ''), el('td', {}, r.lng ?? ''))));
  box.append(th('Receiving', 'Tgt', 'Rec', 'Yds', 'TD', 'Lng')); g.box.receiving.forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.tgt), el('td', {}, r.rec), el('td', {}, r.yds), el('td', {}, r.td), el('td', {}, r.lng ?? ''))));
  box.append(th('Defense', 'Tkl', 'Sk', 'INT', 'PD', '')); g.box.defense.forEach(r => box.append(el('tr', {}, el('td', {}, stripe(r.team, r.name)), el('td', {}, r.tkl), el('td', {}, r.sk), el('td', {}, r.int_), el('td', {}, r.pd), el('td', {}, ''))));
  right.append(box);
  // team stats side by side, and the assistants' read of what decided it
  if (g.team_stats && g.team_stats[g.home.abbr]) {
    right.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Team Stats'));
    const ts = el('table', { class: 'box' }); const A = g.team_stats[g.away.abbr], H = g.team_stats[g.home.abbr];
    ts.append(el('tr', {}, el('th', {}, ''), el('th', {}, g.away.abbr), el('th', {}, g.home.abbr)));
    for (const [k, label] of [['yards', 'Total Yards'], ['plays', 'Plays'], ['ypp', 'Yards per Play'], ['pass_yds', 'Passing'], ['rush_yds', 'Rushing'], ['first_downs', 'First Downs'], ['third', 'Third Down'], ['fourth', 'Fourth Down'], ['red_zone', 'Red Zone TD'], ['turnovers', 'Turnovers'], ['sacks_allowed', 'Sacks Allowed'], ['penalties', 'Penalties'], ['top', 'Possession']])
      ts.append(el('tr', {}, el('td', {}, label), el('td', {}, String(A[k])), el('td', {}, String(H[k]))));
    right.append(ts);
  }
  if (g.reads && g.reads.length) { right.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, "Assistants' Read")); for (const r of g.reads) right.append(el('div', { class: 'pad', style: 'font-size:13.5px;color:var(--ink-2);padding-top:4px' }, r)); }
  page.append(right);
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
function renderRoster(v) {
  renderRail(v.rail);
  const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = 'repeat(12,1fr)';
  $('#crumb').textContent = 'Club'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'club'));
  secondRow([['Roster', '#club'], ['Depth Chart', '#club/depth'], ['Practice Squad', '#club/ps']], clubTab === 'ps' ? '#club/ps' : '#club');
  const sheet = el('section', { class: 'sheet c12' });
  const tabs = el('div', { class: 'tabs' });
  for (const [k, label, n] of [['active', 'Active', v.count], ['ps', 'Practice Squad', v.practice.length], ['injured', 'Injured', v.injured.length]])
    tabs.append(el('button', { 'aria-pressed': String(clubTab === k), onclick: () => { clubTab = k; const want = k === 'ps' ? '#club/ps' : k === 'active' ? '#club' : null; if (want && location.hash !== want) { location.hash = want; } else renderRoster(v); } }, label + ' ', el('em', {}, n)));
  const views = el('div', { class: 'tabs', style: 'margin-left:14px' });
  for (const k of ['Overview', 'Ratings', 'Contract', 'Stats']) views.append(el('button', { 'aria-pressed': String(clubView === k), onclick: () => { clubView = k; renderRoster(v); } }, k));
  const sides = el('div', { class: 'chips' });
  for (const k of ['All', 'Offense', 'Defense', 'Specialists']) sides.append(el('button', { class: 'chip', 'aria-pressed': String(rosterSide === k), onclick: () => { rosterSide = k; renderRoster(v); } }, k));
  const search = el('input', { type: 'search', class: 'find', placeholder: 'Find a player', value: rosterQuery }); search.oninput = () => { rosterQuery = search.value; drawRows(); };
  const count = el('span', { class: 'count', style: 'margin-left:auto' });
  sheet.append(el('div', { class: 'tools' }, tabs, views, sides, search, count));
  const tbl = el('table', { class: 'tbl' });
  const H = (t, tip, n) => el('th', { 'data-tip': tip || null, class: n ? 'n' : null }, t);
  const heads = { Overview: [H('Player'), H('Pos', 'Position'), H('Age', null, 1), H('Ovr', 'Overall Rating', 1), H('Fit', "How well the player matches your coach's scheme", 1), H('Dev', 'Rate of XP Growth'), H('Condition', 'Game-day Freshness'), H('Morale', "Player's happiness"), H('Yrs', 'Years left on his contract', 1), H('Cap Hit', "This year's cap hit", 1), H('Penalty', 'Dead cap charged if player is cut/traded', 1), H('Status'), H('')],
                  Ratings: [H('Player'), H('Pos', 'Position'), H('Age', null, 1), H('Ovr', 'Overall Rating', 1), H('Ceiling', "The player's estimated potential", 1), H('Dev', 'Rate of XP Growth'), H('Fit', "How well the player matches your coach's scheme", 1), H('Morale', "Player's happiness"), H('')],
                  Contract: [H('Player'), H('Pos', 'Position'), H('Age', null, 1), H('Yrs', 'Years left on his contract', 1), H('Cap Hit', "This year's cap hit", 1), H('Penalty', 'Dead cap charged if player is cut/traded', 1), H('Status'), H('')],
                  Stats: [H('Player'), H('Pos', 'Position'), H('G', 'Games played', 1), H('This Season'), H('Comp%', 'Completion pct for a quarterback, catch pct for a receiver', 1), H('EPA', 'Expected points added per dropback, rush, target or defensive play by position', 1), H('')] }[clubView];
  if (clubTab === 'ps') heads.push(el('th', {}, ''));
  const acts = r => el('td', {}, el('div', { class: 'row-act' },
    el('button', { title: 'Card', 'data-tip': 'Open his card', onclick: e => { e.stopPropagation(); location.hash = '#club/player/' + r.pid; } }, '▣'),
    el('button', { title: 'Extend', 'data-tip': 'Ask his agent and open the talks', onclick: e => { e.stopPropagation(); const res = pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind='extension')`); notify(res); if (res.ok) location.hash = '#personnel/extensions'; } }, '$'),
    el('button', { title: 'Trade Block', 'data-tip': 'Put him in a trade package', onclick: e => { e.stopPropagation(); tradeState = { other: tradeState.other, a: [r.pid], b: [], keep: true }; location.hash = '#personnel/trades'; } }, '⇄')));
  const drawRows = () => {
    tbl.innerHTML = ''; tbl.append(el('tr', {}, ...heads));
    const q = rosterQuery.trim().toLowerCase(); let shown = 0;
    const rowsFor = () => clubTab === 'ps' ? [{ title: 'Practice Squad', rows: v.practice }] : clubTab === 'injured' ? [{ title: 'Injured', rows: v.injured }] : v.groups;
    for (const g of rowsFor()) {
      const rows = g.rows.filter(r => (rosterSide === 'All' || r.side === rosterSide.toLowerCase().replace('specialists', 'special')) && (!q || r.name.toLowerCase().includes(q) || (r.college || '').toLowerCase().includes(q) || r.pos.toLowerCase() === q));
      if (!rows.length) continue;
      tbl.append(el('tr', { class: 'grp' }, el('td', { colspan: String(heads.length) }, `${g.title} · ${rows.length}`)));
      for (const r of rows) {
        shown++;
        const cells = { Overview: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, fitCell(r.fit)), el('td', {}, el('span', { class: 'dev' + (r.dev === 'Star' || r.dev === 'Superstar' || r.dev === 'X-Factor' ? ' star' : '') }, r.dev)), el('td', {}, condBar(r.cond)), el('td', {}, pill(r.morale)), el('td', { class: 'n' }, r.yrs), el('td', { class: 'n' }, `$${r.hit.toFixed(1)}m`), el('td', { class: 'n' }, `$${r.penalty.toFixed(1)}m`), el('td', {}, el('span', { class: 'inj' }, r.status))],
                        Ratings: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, r.pot_range ? `${r.pot_range[0]}–${r.pot_range[1]}` : (r.pot ?? '—')), el('td', {}, el('span', { class: 'dev' + (r.dev === 'Star' || r.dev === 'Superstar' || r.dev === 'X-Factor' ? ' star' : '') }, r.dev)), el('td', { class: 'n' }, fitCell(r.fit)), el('td', {}, pill(r.morale))],
                        Contract: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, r.yrs), el('td', { class: 'n' }, `$${r.hit.toFixed(1)}m`), el('td', { class: 'n' }, `$${r.penalty.toFixed(1)}m`), el('td', {}, el('span', { class: 'inj' }, r.status))],
                        Stats: () => [el('td', {}, who(r)), el('td', {}, r.pos), el('td', { class: 'n' }, r.stats.games), el('td', { style: 'text-align:left;font-family:var(--mono);font-size:12px' }, r.stats.line), el('td', { class: 'n' }, r.stats.comp != null ? `${r.stats.comp}%` : '—'), el('td', { class: 'n', style: r.stats.epa != null ? (r.stats.epa > 0 ? 'color:var(--ok)' : 'color:var(--danger)') : '' }, r.stats.epa != null ? (r.stats.epa > 0 ? '+' : '') + r.stats.epa.toFixed(2) : '—')] }[clubView]();
        cells.push(acts(r));
        if (clubTab === 'ps') {
          const act = (name, extra) => { const res = pyJSON(`SESSION.club_act(${JSON.stringify(name)}, ${extra})`); busy(res.ok ? (res.moves ? res.moves.map(m => `${m.name} ${m.how}`).join(', ') : `${res.name}: done.`) : res.why); setTimeout(() => busy(null), 2200); renderRoster(pyJSON('SESSION.club_roster()')); };
          cells.push(el('td', {}, el('div', { class: 'row-act', style: 'opacity:1' },
            el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', 'data-tip': 'Sign him to the 53 at the minimum', onclick: () => act('call_up', `pid=${JSON.stringify(r.pid)}`) }, 'Call Up'),
            el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', disabled: r.elevated_now ? '' : null, 'data-tip': `Dress him Sunday and send him back after · ${r.elevations} of ${v.per_man_max} used`, onclick: () => act('elevate', `pids=[${JSON.stringify(r.pid)}]`) }, r.elevated_now ? 'Elevated' : `Elevate · ${r.elevations}/${v.per_man_max}`),
            el('button', { class: 'btn warn', style: 'width:auto;padding:3px 8px;font-size:12px', onclick: () => { if (confirm(`Release ${r.name} from the practice squad?`)) act('release_ps', `pid=${JSON.stringify(r.pid)}`); } }, 'Release'))));
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

let cardTab = 'Overview';
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
      el('div', { class: 'hline' }, el('b', {}, v.pos), ` · ${v.age}${v.size ? ' · ' + v.size : ''}${v.college ? ' · ' + v.college : ''}${v.season_no ? ` · ${v.season_no}${ord(v.season_no)} season` : ''} · ${v.draft}` + (v.team ? ` · ${v.team.name}` : ' · Free agent')),
      el('div', { class: 'hfacts' }, el('div', {}, el('span', {}, 'Contract'), el('b', {}, `$${v.contract.per_year.toFixed(1)}m`, el('small', {}, `per year · ${v.contract.years} yrs`))), el('div', {}, el('span', {}, `Cap Hit ${v.rail.year}`), el('b', {}, `$${v.contract.hit.toFixed(1)}m`)), el('div', {}, el('span', {}, 'Penalty'), el('b', {}, `$${v.contract.penalty.toFixed(1)}m`)), el('div', {}, el('span', {}, 'Trade Interest'), el('b', { style: 'color:var(--ink-2)' }, v.interest)), el('div', {}, el('span', {}, 'Morale'), el('b', { style: 'color:var(--ink-2)' }, v.morale)))),
    el('div', { class: 'ovrbig' }, el('b', {}, v.ovr), el('span', {}, `Overall · Scheme Fit ${v.fit >= 0 ? '+' : ''}${v.fit.toFixed(1)}`), el('div', { class: 'pot' }, `Ceiling ${v.ceiling} · ${v.dev}`))));
  // tabs and actions
  const tabs = el('div', { class: 'ctabs' });
  for (const t of ['Overview', 'Contract', 'Stats', 'Career', 'History']) tabs.append(el('button', { 'aria-pressed': String(cardTab === t), onclick: () => { cardTab = t; renderCard(v); } }, t));
  const acts = el('div', { class: 'acts' });
  if (v.actions.mine) {
    acts.append(el('button', { class: 'btn' + (v.ext_eligible ? ' go' : ''), disabled: v.ext_eligible ? null : '', 'data-tip': v.ext_eligible ? `Ask his agent (~$${v.ext_ask ?? '?'}m) and open the talks` : 'Not eligible yet', onclick: () => { const r = pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(v.pid)}, kind='extension')`); notify(r); if (r.ok) location.hash = '#personnel/extensions'; } }, 'Extend'));
    acts.append(el('button', { class: 'btn', 'data-tip': 'Open the restructure preview on his contract', onclick: () => { restructureFor = v.pid; location.hash = '#frontoffice/cap'; } }, 'Restructure'));
    const alts = v.grades.filter(g => !g.mine && g.pos !== 'Nickel');
    if (alts.length) { const sel = el('select', { class: 'btn' }); sel.append(el('option', { value: '' }, 'Position Change…')); alts.forEach(g => sel.append(el('option', { value: g.pos }, `${g.pos} · ${g.ovr} Ovr`))); sel.onchange = () => { if (!sel.value) return; const r = pyJSON(`SESSION.club_act('position_change', pid=${JSON.stringify(v.pid)}, new_pos=${JSON.stringify(sel.value)})`); notify(r.ok ? { ok: true, line: `${r.name} moves to ${r.to}: ${r.penalty} points for ${r.games} games.` } : r); if (r.ok) renderCard(pyJSON(`SESSION.club_card(${JSON.stringify(v.pid)})`)); }; acts.append(sel); }
    acts.append(el('button', { class: 'btn', 'data-tip': 'Put him in a trade package and shop him', onclick: () => { tradeState = { other: tradeState.other, a: [v.pid], b: [], keep: true }; location.hash = '#personnel/trades'; } }, 'Trade Block'));
    acts.append(el('button', { class: 'btn warn', onclick: () => { if (!confirm(`Cut ${v.name}? Penalty $${v.contract.penalty.toFixed(1)}m against this year's cap.`)) return; const r = pyJSON(`SESSION.club_act('cut', pid=${JSON.stringify(v.pid)})`); notify(r.ok ? { ok: true, line: `${r.name} released. Penalty $${r.penalty}m.` } : r); location.hash = '#club'; } }, `Cut · Penalty $${v.contract.penalty.toFixed(1)}m`));
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
      const rowsOf = rows => { for (const r of rows) { const row = el('div', { class: 'arow ' + r.tier }, el('span', {}, r.label)); row.append(r.shift ? el('em', { class: 'fitd ' + (r.shift > 0 ? 'p' : 'm') }, (r.shift > 0 ? '+' : '') + r.shift) : el('em', {})); row.append(el('b', {}, r.v)); box.append(row); } };
      rowsOf(c.rows);
      if (c.extra && c.extra.rows && c.extra.rows.length) { box.append(el('div', { class: 'h5', style: 'margin:12px 0 4px' }, c.extra.title)); rowsOf(c.extra.rows); }
      if (c.title === 'Mental' && v.personality) { box.append(el('div', { class: 'h5', style: 'margin:12px 0 4px' }, 'Traits')); const tr = el('div', { class: 'traits' }); v.personality.split(',').map(x => x.trim()).filter(Boolean).forEach(w => tr.append(el('span', {}, w.replace(/\b\w/g, ch => ch.toUpperCase())))); box.append(tr); }
      attrs.append(box);
    }
    mid.append(attrs);
    const right = el('div', {});
    right.append(h5('Contract', v.contract_caption));
    if (v.contract.by_year.length) { const ct = el('table', { class: 'contract' }); ct.append(el('tr', {}, el('th', {}, 'Year'), el('th', {}, 'Base'), el('th', {}, 'Bonus'), el('th', {}, 'Cap Hit'), el('th', {}, 'Penalty'))); v.contract.by_year.forEach((y, i) => ct.append(el('tr', { class: i === 0 ? 'now' : '' }, el('td', {}, y.year), el('td', {}, y.base != null ? y.base.toFixed(1) : '—'), el('td', {}, y.bonus != null ? y.bonus.toFixed(1) : '—'), el('td', {}, y.hit.toFixed(1)), el('td', {}, y.penalty != null ? y.penalty.toFixed(1) : '—')))); right.append(ct); }
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
    if (v.contract.by_year.length) { const ct = el('table', { class: 'contract', style: 'max-width:620px' }); ct.append(el('tr', {}, el('th', {}, 'Year'), el('th', {}, 'Base'), el('th', {}, 'Bonus'), el('th', {}, 'Cap Hit'), el('th', {}, 'Penalty'))); v.contract.by_year.forEach((y, i) => ct.append(el('tr', { class: i === 0 ? 'now' : '' }, el('td', {}, y.year), el('td', {}, y.base != null ? y.base.toFixed(1) : '—'), el('td', {}, y.bonus != null ? y.bonus.toFixed(1) : '—'), el('td', {}, y.hit.toFixed(1)), el('td', {}, y.penalty != null ? y.penalty.toFixed(1) : '—')))); box.append(ct); }
    else box.append(el('div', { class: 'empty' }, 'No contract on file.'));
    box.append(el('div', { class: 'kv', style: 'margin-top:12px;max-width:620px' }, el('span', {}, 'Market'), el('span', {}, v.market_apy != null ? `About $${v.market_apy}m per year` : '—'), el('span', {}, 'Extension'), el('span', {}, v.ext_eligible ? `Eligible${v.ext_ask != null ? ` · agent's ask ~$${v.ext_ask}m` : ''}` : 'Not yet eligible'), el('span', {}, 'Penalty if cut now'), el('span', {}, `$${v.contract.penalty.toFixed(1)}m`)));
    s.append(box);
  } else if (cardTab === 'Stats' || cardTab === 'Career') {
    const box = el('div', { class: 'pad' }, h5(cardTab === 'Stats' ? 'Season Stats' : 'Career', cardTab === 'Stats' ? `${v.rail.year} · ${v.games} game${v.games === 1 ? '' : 's'}` : `${v.seasons.length} season${v.seasons.length === 1 ? '' : 's'} on record`));
    const rows = cardTab === 'Stats' ? v.seasons.filter(sn => sn.year === v.rail.year) : v.seasons.slice().reverse();
    if (rows.length) { const t = el('table', { class: 'stab', style: 'max-width:900px' }); t.append(el('tr', {}, el('th', {}, 'Season'), el('th', {}, 'Club'), el('th', {}, 'G'), ...v.season.cols.map(c => el('th', {}, c)))); for (const sn of rows) t.append(el('tr', {}, el('td', {}, sn.year), el('td', {}, sn.team), el('td', {}, sn.games), ...sn.row.map(x => el('td', {}, String(x))))); box.append(t); }
    else box.append(el('div', { class: 'empty' }, cardTab === 'Stats' ? 'No snaps yet this season.' : 'No seasons on record yet.'));
    s.append(box);
  } else {
    const box = el('div', { class: 'pad' }, h5('History', 'moves, deals and changes on record'));
    const h = el('div', { class: 'histlist', style: 'max-width:720px' });
    for (const x of (v.history || [])) h.append(el('div', {}, el('time', {}, x.when), el('span', {}, x.line)));
    if (!(v.history || []).length) h.append(el('div', {}, el('time', {}, '—'), el('span', {}, 'Nothing on record yet.')));
    box.append(h); s.append(box);
  }
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
    const byPos = {}; c.slots.forEach(x => (byPos[x.pos] = byPos[x.pos] || []).push(x));
    const pinnedHere = Object.keys(byPos).some(p => v.pins[p] && v.pins[p].length);
    const col = el('div', { class: 'col' }, el('h4', { class: pinnedHere ? 'pinned' : '' }, c.title));
    for (const [pos, men] of Object.entries(byPos)) {
      men.forEach((x, i) => {
        const plate = el('div', { class: 'plate' + (x.flag === 'out' ? ' out' : ''), draggable: 'true', 'data-pid': x.pid, 'data-pos': pos }, el('div', { class: 'no' }, x.no || pos), el('div', { class: 'nm', onclick: () => { location.hash = '#club/player/' + x.pid; } }, x.short, el('small', {}, x.flag_word || '')), el('div', { class: 'ov' }, x.ovr));
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
        col.append(el('div', { class: 'slot' + (x.start ? ' start' : '') }, el('span', { class: 'rk' }, x.slot), plate, arrows));
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
    box.append(el('div', { class: 'side-h' }, crest(own.club), el('b', {}, title === 'You Send' ? 'You Send' : `${own.club.nick.charAt(0) + own.club.nick.slice(1).toLowerCase()} Sends`), el('span', {}, title === 'You Send' ? (v.package ? `Cap After: $${v.package.cap_after.me}m` : `Cap $${own.cap.toFixed(1)}m`) : `Their Cap: $${own.cap.toFixed(1)}m`)));
    const sn = el('div', { class: 'read', style: 'display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:8px' });
    sn.append(el('div', {}, el('div', { class: 'h5' }, own === v.me ? 'Your Surplus' : 'Their Surplus'), ...(own.surplus.length ? own.surplus.map(x => { const p = own.roster.find(r => r.pid === x.pid); return p ? el('div', { style: 'font-size:12.5px;cursor:pointer', onclick: () => { if (!sel.includes(p.pid)) { sel.push(p.pid); reload(); } } }, `${p.short} · ${p.pos} · ${p.ovr}`, el('small', { style: 'color:var(--ink-3)' }, ` ${x.why}`)) : ''; }) : [el('div', { style: 'font-size:12.5px;color:var(--ink-3)' }, 'Nothing spare.')])));
    sn.append(el('div', {}, el('div', { class: 'h5' }, own === v.me ? 'Your Needs' : 'Their Needs'), el('div', { style: 'font-size:12.5px' }, own.needs && own.needs.length ? own.needs.join(' · ') : 'None pressing')));
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
    el('button', { class: 'btn', disabled: v.can_trade && tradeState.a.length === 1 && !tradeState.a[0].includes('-') ? null : '', 'data-tip': 'Shop the one player you send to every club', onclick: () => { const r = pyJSON(`SESSION.personnel_act('gather', pid=${JSON.stringify(tradeState.a[0])})`); const box = $('#gather'); box.innerHTML = ''; box.append(el('b', {}, r.line)); for (const o of r.offers) box.append(el('div', { style: 'display:flex;gap:10px;align-items:center;margin-top:6px' }, crest(o.club, 26), el('span', {}, `${o.club.name} offers `, el('b', {}, o.pick.label)), el('button', { class: 'btn', style: 'margin-left:auto;padding:3px 8px;font-size:12px', onclick: () => { tradeState = { other: o.club.abbr, a: [tradeState.a[0]], b: [o.pick.id] }; reload(); } }, 'Open'))); } }, 'Gather Offers'),
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
  for (const [k, l] of [['starting_role', 'Named the Starter'], ['captaincy', 'Captaincy'], ['no_trade', 'No Trade'], ['extension_by', 'Extension by a Set Year'], ['no_tag', 'No Franchise Tag']]) promises.append(el('button', { class: 'btn quiet', style: 'padding:2px 8px;font-size:12px', 'aria-pressed': 'false', onclick: e => { const i = chosen.indexOf(k); if (i < 0) chosen.push(k); else chosen.splice(i, 1); e.currentTarget.setAttribute('aria-pressed', String(i < 0)); } }, l));
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
  const left = el('section', { class: 'sheet c7' }, el('h2', {}, 'Free Agency', el('small', {}, `${v.count} Available · Cap Space $${v.cap}m${v.top51 ? ' · Top 51' : ''} · Roster ${v.roster}`)));
  if (v.step_i != null) { const ph = el('div', { class: 'phase' }); v.steps.forEach((n, i) => ph.append(el('div', { class: i < v.step_i ? 'done' : i === v.step_i ? 'now' : '' }, n))); left.append(ph); }
  const tools = el('div', { class: 'tools' });
  const posChips = el('div', { class: 'chips' }); for (const g of ['All', 'QB', 'OL', 'WR', 'DL', 'DB', 'LB']) posChips.append(el('button', { class: 'chip', 'aria-pressed': String((faPos || 'All') === g), onclick: () => { faPos = g === 'All' ? '' : g; renderFA(v); } }, g));
  const roleChips = el('div', { class: 'chips' }); for (const g of ['Starters', 'Depth']) roleChips.append(el('button', { class: 'chip', 'aria-pressed': String(faRole === g), onclick: () => { faRole = faRole === g ? 'All' : g; renderFA(v); } }, g));
  const cheap = el('button', { class: 'chip', 'aria-pressed': String(faCheap), 'data-tip': 'Players asking under $5m a year, or with no ask yet', onclick: () => { faCheap = !faCheap; renderFA(v); } }, 'Under $5m');
  const watchB = el('button', { class: 'chip', 'aria-pressed': String(faWatch), onclick: () => { faWatch = !faWatch; renderFA(v); } }, `Watchlist · ${v.rows.filter(r => r.watch).length}`);
  const search = el('input', { type: 'search', class: 'find', placeholder: 'Find a Player', value: faQuery }); search.oninput = () => { faQuery = search.value; drawRows(); };
  tools.append(posChips, roleChips, el('div', { class: 'chips' }, cheap, watchB), search);
  left.append(tools);
  const GROUP = { QB: ['QB'], OL: ['LT', 'LG', 'C', 'RG', 'RT'], WR: ['WR', 'TE'], DL: ['LEDG', 'DT', 'REDG'], DB: ['CB', 'FS', 'SS'], LB: ['MIKE', 'WILL', 'SAM'] };
  const tbl = el('table', { class: 'tbl' });
  const drawRows = () => {
    tbl.innerHTML = ''; tbl.append(el('tr', {}, el('th', {}, ''), el('th', {}, 'Player'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n' }, 'Ovr'), el('th', { class: 'n', 'data-tip': 'How he grades in your scheme' }, 'Fit'), el('th', {}, 'Ask'), el('th', {}, 'Interest'), el('th', {}, 'Your Offer'), el('th', {}, '')));
    const q = faQuery.trim().toLowerCase();
    const rows = v.rows.filter(r => (!faPos || (GROUP[faPos] || []).includes(r.pos)) && (faRole === 'All' || (faRole === 'Starters') === r.starter) && (!faCheap || r.ask == null || r.ask < 5) && (!faWatch || r.watch) && (!q || r.name.toLowerCase().includes(q)));
    for (const r of rows) tbl.append(el('tr', {}, el('td', {}, el('button', { class: 'star' + (r.watch ? ' on' : ''), 'data-tip': r.watch ? 'On your watchlist' : 'Add to your watchlist', onclick: () => { pyJSON(`SESSION.personnel_act('watch', pid=${JSON.stringify(r.pid)})`); reload(); } }, '★')),
      el('td', {}, el('button', { class: 'who', onclick: () => { location.hash = '#club/player/' + r.pid; } }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, `${r.pos}${r.last ? ' · from ' + r.last : ''}`)))), el('td', {}, r.pos), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.ovr)), el('td', { class: 'n' }, fitCell(r.fit)),
      el('td', {}, r.ask ? `$${r.ask}m × ${r.years}` : el('span', { style: 'color:var(--ink-3)' }, '—')), el('td', {}, r.interest ? el('span', { class: 'pill ' + ({ 'Match Asked': 'unsettled', Agreed: 'happy', Countered: 'content', Mulling: 'content', Walked: 'unhappy' }[r.interest] || 'content') }, r.interest) : ''), el('td', {}, r.my_offer || el('span', { style: 'color:var(--ink-3)' }, '—')),
      el('td', {}, r.thread ? el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', onclick: () => { document.getElementById('th-' + r.thread)?.scrollIntoView(); } }, 'Offer') : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', onclick: () => { notify(pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind=${JSON.stringify(v.in_season ? 'fa_inseason' : 'fa_offseason')})`)); reload(); } }, 'Ask the Agent'))));
    if (!rows.length) tbl.append(el('tr', {}, el('td', { colspan: '10' }, el('div', { class: 'empty' }, v.rows.length ? 'Nobody matches the filter.' : 'Nobody worth a call is on the market.'))));
  };
  left.append(tbl); drawRows();
  page.append(left);
  const right = el('section', { class: 'sheet c5' }, el('h2', {}, 'Negotiation', el('small', {}, `${v.threads.length} open`)));
  for (const t of v.threads) { const w = el('div', { id: 'th-' + t.id }, el('div', { class: 'h5', style: 'padding:10px 12px 0' }, `${t.name} · ${t.pos}`)); w.append(threadBox(t, reload)); right.append(w); }
  if (!v.threads.length) right.append(el('div', { class: 'empty' }, v.in_season ? 'Ask an agent; a signing you offer decides at the next Advance, or pay his ask to sign today.' : 'Ask an agent to open talks; he mulls offers through each step of the market.'));
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
      el('td', {}, r.claimed ? el('span', { class: 'badge-sm' }, 'Claimed') : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', onclick: () => { wireClaim = r.pid; renderWire(v); } }, 'Claim'))));
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
    el('td', {}, r.thread ? el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', onclick: () => { document.getElementById('th-' + r.thread)?.scrollIntoView(); } }, 'Open Talks') : el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', disabled: r.eligible ? null : '', onclick: () => { notify(pyJSON(`SESSION.personnel_act('open_talks', pid=${JSON.stringify(r.pid)}, kind='extension')`)); reload(); } }, 'Ask the Agent'))));
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

function renderStaff(v) {
  renderRail(v.rail); const page = persPage(); foSecond('staff');
  const reload = () => renderStaff(pyJSON(`SESSION.frontoffice('staff')`));
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Staff', el('small', {}, `Budget $${v.budget.total}m · Paid $${v.budget.payroll}m · Available $${v.budget.available}m`)));
  const grid = el('div', { class: 'staffgrid', style: 'grid-template-columns:repeat(4,1fr)' });
  for (const c of v.cards) {
    if (c.empty) { grid.append(el('div', { class: 'scard open' }, `${c.role_name} · open. Hire from the pool below.`)); continue; }
    const card = el('div', { class: 'scard' }, el('div', { class: 'role' }, c.role + (c.hc_candidate ? ' · Head-Coaching Candidate' : '') + (c.disgruntled ? ' · Disgruntled' : '')), el('div', { class: 'nm' }, c.name),
      el('div', { class: 'kv' }, el('span', {}, 'Rating'), el('b', {}, c.rating), el('span', {}, 'Prestige'), el('b', {}, c.prestige), el('span', {}, 'Specialty'), el('span', {}, c.specialty || '—'), el('span', {}, 'Age'), el('span', {}, c.age), el('span', {}, 'Contract'), el('span', {}, `$${(+c.salary).toFixed(1)}m · Expires ${v.rail.year + c.years}`), el('span', {}, 'Asks'), el('span', {}, `$${(+c.extend_ask).toFixed(1)}m`), el('span', {}, `${c.role.replace(' Coordinator', '')} Rank`), el('span', {}, (c.unit_ranks || []).length ? c.unit_ranks.map(r => `${r}${ord(r)}`).join(' · ') : '—'), el('span', {}, 'Traits'), el('span', {}, c.personality || '—')));
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
      el('div', { class: 'txt', style: 'color:var(--ink-3);font-size:12px' }, `He is paid $${p.salary.toFixed(1)}m. A head-coaching job would pay him about $${p.hc_pay.toFixed(1)}m. Available without him: $${p.room_without.toFixed(1)}m.`),
      el('div', { class: 'acts' }, el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.frontoffice_act('poach', tid=${p.id}, action='persuade', raise_years=${+yrs.value}, raise_to=${+per.value})`)); reload(); } }, 'Offer and Ask Again'),
        el('button', { class: 'btn', onclick: () => { notify(pyJSON(`SESSION.frontoffice_act('poach', tid=${p.id}, action='let_go')`)); reload(); } }, 'Let Him Go'),
        el('button', { class: 'btn warn', onclick: () => { notify(pyJSON(`SESSION.frontoffice_act('poach', tid=${p.id}, action='block')`)); reload(); } }, 'Block the Move'))));
    box.append(el('div', { class: 'msg note' }, el('b', {}, 'If you block him: '), p.block_read));
    s.append(box);
  }
  s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'The Pool', el('small', {}, v.offseason ? 'Hire Into an Open Job · Greyed Where He Does Not Fit What You Have Available' : 'hiring reopens after the season')));
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); const list = el('div', { class: 'pad' }); let role = 'oc';
  const draw = () => { list.innerHTML = ''; const cur = v.cards.find(x => x.role_key === role); const room = v.budget.available + (cur && !cur.empty ? +cur.salary : 0); const grid2 = el('div', { class: 'staffgrid', style: 'grid-template-columns:repeat(4,1fr);padding:0' });
    for (const c of v.pools[role]) { const fits = +c.ask <= room + 1e-9; grid2.append(el('div', { class: 'scard', style: fits ? '' : 'opacity:.45' }, el('div', { class: 'nm' }, c.name), el('div', { class: 'role', style: 'text-transform:none;letter-spacing:0' }, c.background), el('div', { class: 'kv' }, el('span', {}, 'Rating'), el('b', {}, c.rating), el('span', {}, 'Prestige'), el('b', {}, c.prestige), el('span', {}, 'Age'), el('span', {}, c.age), el('span', {}, 'Asks'), el('span', {}, `$${(+c.ask).toFixed(1)}m`), el('span', {}, 'Traits'), el('span', {}, c.personality || '—')), el('div', { class: 'acts' }, el('button', { class: 'btn', disabled: v.offseason && fits ? null : '', 'data-tip': v.offseason ? (fits ? 'Three years at his ask; replaces the sitting coach' : 'Over what you have available') : 'Offseason only', onclick: () => { notify(pyJSON(`SESSION.frontoffice_act('staff_hire', name=${JSON.stringify(c.name)}, years=3)`)); reload(); } }, 'Hire')))); }
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
    yrs.append(el('div', { class: 'cy' }, el('h4', {}, `${y.year}${i === 0 ? ' Now' : ''}`, el('small', {}, `Limit $${y.limit}m${y.est ? ' est.' : ''}`)), el('div', { class: 'big' + (y.space < 0 ? ' neg' : '') }, `${y.space < 0 ? '−' : ''}$${Math.abs(y.space).toFixed(1)}m`), el('div', { style: 'font-size:11px;color:var(--ink-3)' }, 'space'), st, kv));
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
  for (const t of v.tags) tt.append(el('span', {}, `Franchise Tag · ${t.pos}`), el('span', {}, `$${t.price}m · `, el('span', { style: 'cursor:pointer;text-decoration:underline dotted', onclick: () => { location.hash = '#club/player/' + t.pid; } }, t.name.split(' ').pop())));
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
    el('td', {}, r.restructurable > 0.5 ? el('button', { class: 'btn', style: 'width:auto;padding:3px 8px;font-size:12px', onclick: () => openPreview(r) }, 'Restructure') : '')));
  ledger.append(tbl, el('div', { class: 'foot' }, el('a', { class: 'btn', href: '#personnel/extensions' }, 'Extensions')));
  two.append(ledger, pvBox); s.append(two); page.append(s);
  if (restructureFor) { const r = v.rows.find(x => x.pid === restructureFor); restructureFor = null; if (r) openPreview(r); }
}

// ---------------------------------------------------------------- Draft
const DR = { board: 'Scouting Board', spring: 'The Spring', day: 'Draft Day', picks: 'Picks' };
let boardPos = 'All', boardFilt = { early: false, small: false, visited: false };
function drSecond(cur) { secondRow(Object.entries(DR).map(([k, l]) => [l, '#draft/' + k]), '#draft/' + cur); $('#crumb').textContent = 'Draft'; $('#nav').querySelectorAll('a').forEach(a => a.toggleAttribute('aria-current', a.dataset.page === 'draft')); }
function gapCell(g) { if (g == null) return el('span', { class: 'gap' }, '—'); return el('span', { class: 'gap ' + (g > 0 ? 'up' : g < 0 ? 'dn' : '') }, (g > 0 ? '+' : '') + g); }
function flagTags(fl) { const s = el('span', {}); for (const f of fl || []) s.append(el('span', { class: 'flag ' + ({ medical: 'med', character: 'chr', visit: 'vis', riser: 'up', faller: 'dn', 'senior bowl': 'sr' }[String(f).toLowerCase()] || 'ss') }, String(f))); return s; }
const POS_GROUPS = ['All', 'QB', 'HB', 'WR', 'TE', 'OL', 'DL', 'LB', 'DB', 'ST'];
const POS_OF = { QB: ['QB'], HB: ['HB', 'FB'], WR: ['WR'], TE: ['TE'], OL: ['LT', 'LG', 'C', 'RG', 'RT'], DL: ['LEDG', 'DT', 'REDG'], LB: ['MIKE', 'WILL', 'SAM'], DB: ['CB', 'FS', 'SS'], ST: ['K', 'P', 'LS'] };

function renderBoard(v) {
  renderRail(v.rail); const page = persPage(); drSecond('board');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, `Scouting Board · Class of ${v.year}`, el('small', {}, `${v.count} prospects` + (v.scout ? ` · Head Scout ${v.scout.name} (${v.scout.rating})` : ''))));
  if (v.note) { s.append(el('div', { class: 'empty' }, v.note)); page.append(s); return; }
  const filt = el('div', { class: 'filt-pos' }); for (const g of POS_GROUPS) filt.append(el('button', { class: 'btn' + (boardPos === g ? ' go' : ''), onclick: () => { boardPos = g; renderBoard(v); } }, g));
  filt.append(el('span', { style: 'width:1px;background:var(--rule-2);margin:0 6px' }));
  for (const [k, label, tip] of [['early', 'Rounds 1–3', 'Consensus in the first 96'], ['small', 'Small School', 'Outside the power conferences: your read is wider on these players'], ['visited', 'Visited', `Your ${v.visits_max} visits`]]) filt.append(el('button', { class: 'btn' + (boardFilt[k] ? ' go' : ''), 'data-tip': tip, onclick: () => { boardFilt[k] = !boardFilt[k]; renderBoard(v); } }, label));
  filt.append(el('span', { class: 'count', style: 'margin-left:auto;align-self:center' }, `Visits ${v.visits.length} of ${v.visits_max}` + (v.spring_done ? ' · the spring has run' : ' · name them before the Spring')));
  s.append(filt);
  const tbl = el('table', { class: 'tbl' });
  tbl.append(el('tr', {}, el('th', { class: 'n', 'data-tip': 'Where he sits on your board' }, '#'), el('th', {}, 'Prospect'), el('th', {}, 'Pos'), el('th', {}, 'School'), el('th', { class: 'n' }, 'Age'), el('th', { class: 'n', 'data-tip': "Your scouts' grade of him today" }, 'Your Read'), el('th', { class: 'n', 'data-tip': 'The range your scouts see him growing into' }, 'Ceiling'), el('th', { class: 'n', 'data-tip': 'Where the league as a whole has him' }, 'Consensus'), el('th', { class: 'n', 'data-tip': 'The round the consensus puts him in' }, 'Proj.'), el('th', { class: 'n', 'data-tip': 'Your read minus the consensus: plus means you like him more than the room does' }, 'Gap'), el('th', {}, 'Measurables'), el('th', {}, 'Flags'), el('th', {}, '')));
  const rows = v.rows.filter(r => (boardPos === 'All' || POS_OF[boardPos].includes(r.pos)) && (!boardFilt.early || (r.cons_rank != null && r.cons_rank <= 96)) && (!boardFilt.small || r.small) && (!boardFilt.visited || r.visited)).slice(0, 200);
  for (const r of rows) tbl.append(el('tr', { style: r.taken ? 'opacity:.4' : '' }, el('td', { class: 'n' }, r.my_rank), el('td', {}, el('div', { class: 'who' }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name))), el('td', {}, r.pos), el('td', {}, r.college + (r.small ? ' ·' : ''), r.small ? el('small', { style: 'color:var(--ink-3)', 'data-tip': 'small school' }, ' ss') : ''), el('td', { class: 'n' }, r.age), el('td', { class: 'n' }, ovrCell(r.mine)), el('td', { class: 'n' }, r.ceiling), el('td', { class: 'n' }, r.cons != null ? `${r.cons} · #${r.cons_rank}` : '—'), el('td', { class: 'n' }, r.proj), el('td', { class: 'n' }, gapCell(r.gap)), el('td', {}, el('span', { class: 'meas' }, [r.forty ? `${r.forty} forty` : null, r.vert ? `${r.vert}" vert` : null, r.bench ? `${r.bench} bench` : null].filter(Boolean).join(' · ') || '—')), el('td', {}, flagTags(r.flags)),
    el('td', {}, v.spring_done ? '' : el('button', { class: 'btn' + (r.visited ? ' go' : ''), style: 'width:auto;padding:2px 8px;font-size:12px', 'data-tip': r.visited ? 'Cancel the visit' : 'Bring him in: the second look is the sharpest read your scouts get', onclick: () => { const res = pyJSON(`SESSION.draft_act('visit', pid=${JSON.stringify(r.pid)})`); if (!res.ok) notify(res); renderBoard(pyJSON(`SESSION.draft_view('board')`)); } }, r.visited ? 'Visiting' : 'Visit'))));
  s.append(el('div', { class: 'board-wrap' }, tbl)); page.append(s);
}

function renderSpring(v) {
  renderRail(v.rail); const page = persPage(); drSecond('spring');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'The Spring', el('small', {}, v.done ? v.events.map(e => `${e.event} ${e.n} moves`).join(' · ') : 'stock moves and flags')));
  if (!v.done) { s.append(el('div', { class: 'empty' }, v.note)); page.append(s); return; }
  const two = el('div', { class: 'two' });
  const mk = (title, list, up) => { const d = el('div', {}, el('div', { class: 'h5' }, title)); for (const m of list) d.append(el('div', { class: 'brow', style: 'grid-template-columns:1fr' }, el('div', { class: 'plate' }, el('div', { class: 'nm', style: 'padding-left:8px' }, m.name, el('small', {}, `${m.pos} · ${m.college} · ${m.event}`)), el('div', { class: 'pj' }, `#${m.frm} → #${m.to}`, el('small', {}, up ? 'up' : 'down')), el('div', { class: 'ov', style: `color:${up ? 'var(--ok)' : 'var(--danger)'}` }, (up ? '+' : '') + m.delta)))); if (!list.length) d.append(el('div', { class: 'empty' }, 'None.')); return d; };
  two.append(mk('Risers', v.risers, true), mk('Fallers', v.fallers, false)); s.append(two);
  s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Your Visits', el('small', {}, `${v.visited.length} players · the second look`)));
  const vt = el('table', { class: 'tbl' }); vt.append(el('tr', {}, el('th', {}, 'Prospect'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Your Read'), el('th', { class: 'n' }, 'Ceiling'), el('th', { class: 'n' }, 'Consensus'), el('th', { class: 'n' }, 'Gap'), el('th', {}, 'Flags')));
  for (const r of v.visited) vt.append(el('tr', {}, el('td', {}, el('div', { class: 'who' }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, r.college)))), el('td', {}, r.pos), el('td', { class: 'n' }, ovrCell(r.mine)), el('td', { class: 'n' }, r.ceiling), el('td', { class: 'n' }, r.cons_rank != null ? `#${r.cons_rank}` : '—'), el('td', { class: 'n' }, gapCell(r.gap)), el('td', {}, flagTags(r.flags.filter(f => f !== 'visited')))));
  if (!v.visited.length) vt.append(el('tr', {}, el('td', { colspan: '7' }, el('div', { class: 'empty' }, 'You named no visits this year.'))));
  s.append(vt);
  s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Flags', el('small', {}, 'medical and character, from the spring')));
  const ft = el('table', { class: 'tbl' }); ft.append(el('tr', {}, el('th', {}, 'Prospect'), el('th', {}, 'Pos'), el('th', { class: 'n' }, 'Consensus'), el('th', {}, 'Flags')));
  for (const r of v.flagged) ft.append(el('tr', {}, el('td', {}, el('div', { class: 'who' }, el('div', { class: 'no' }, r.pos), el('div', { class: 'nm' }, r.name, el('small', {}, r.college)))), el('td', {}, r.pos), el('td', { class: 'n' }, r.cons_rank != null ? `#${r.cons_rank}` : '—'), el('td', {}, flagTags(r.flags.filter(f => f !== 'visited')))));
  s.append(ft); page.append(s);
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
    el('button', { class: 'btn', disabled: v.on_user ? '' : null, 'data-tip': 'Sim to the end of this round, or to your pick if it comes first', onclick: () => act('sim_round') }, 'Sim Round'),
    el('span', { class: 'sep' }), el('button', { class: 'btn quiet', onclick: () => { if (confirm('Run the rest of the draft on auto? Your picks go to the top of your board.')) act('finish_auto'); } }, 'Finish on Auto'));
  left.append(ctrl, el('div', { id: 'offers' }));
  // best available and your board
  const two = el('div', { class: 'two' });
  const ba = el('div', {}, el('div', { class: 'h5' }, 'Best Available · consensus'));
  for (const r of v.best) ba.append(el('div', { class: 'brow' }, el('div', { class: 'r' }, r.cons_rank ?? '—'), el('div', { class: 'plate' }, el('div', { class: 'nm', style: 'padding-left:8px' }, r.name, el('small', {}, `${r.pos} · ${r.college}`)), el('div', { class: 'pj' }, r.ceiling, el('small', {}, 'your ceiling')), el('div', { class: 'ov' }, r.mine))));
  two.append(ba);
  const mb = el('div', {}, el('div', { class: 'h5' }, 'Your Board'), el('div', { class: 'bhead' }, el('span', {}, '#'), el('span', {}, 'Prospect'), el('span', {}, 'Consensus'), el('span', {}, 'Read')));
  const list = el('div', { class: 'board', style: 'max-height:56vh;overflow-y:auto;padding:6px 0' });
  for (const r of v.board) list.append(el('div', { class: 'brow' + (r.cons_rank != null && r.cons_rank - r.my_rank >= 12 ? ' mine-high' : r.cons_rank != null && r.my_rank - r.cons_rank >= 12 ? ' mine-low' : ''), 'data-tip': r.cons_rank != null && Math.abs(r.cons_rank - r.my_rank) >= 12 ? (r.cons_rank > r.my_rank ? 'You have him well above the room' : 'The room has him well above you') : null }, el('div', { class: 'r' }, r.my_rank), el('div', { class: 'plate' + (v.on_user ? ' pickable' : ''), onclick: v.on_user ? () => { if (confirm(`Take ${r.name}, ${r.pos}, at ${cur.slot}?`)) act('pick', `pid=${JSON.stringify(r.pid)}`); } : null }, el('div', { class: 'nm', style: 'padding-left:8px' }, r.name, el('small', {}, `${r.pos} · ${r.college}` + (r.flags.length ? ' · ' + r.flags.join(', ') : ''))), el('div', { class: 'pj' }, r.cons_rank != null ? `#${r.cons_rank}` : '—', el('small', {}, gapCell(r.gap))), el('div', { class: 'ov' }, r.mine))));
  mb.append(list); two.append(mb); left.append(two);
  if (v.on_user && v.board.length) left.append(el('div', { class: 'pad' }, el('button', { class: 'bigpick', onclick: () => { if (confirm(`Take ${v.board[0].name}, ${v.board[0].pos}, at ${cur.slot}?`)) act('pick', `pid=${JSON.stringify(v.board[0].pid)}`); } }, `PICK ${v.board[0].name.toUpperCase()}`, el('small', {}, `${v.board[0].pos} · top of your board · or tap any player on it`))));
  page.append(left);
  const right = el('section', { class: 'sheet c4' }, el('h2', {}, 'The Clock', el('small', {}, `${v.trades} trades`)));
  const myNext = v.mine_next.length ? v.mine_next[0].sel : Infinity;
  const nx = el('div', { class: 'picksmade' });
  for (const q of v.clock) {
    const canUp = !q.mine && q.sel < myNext && !v.on_user;
    nx.append(el('div', { class: 'pk' + (q.mine ? ' next' : '') + (q.sel === cur.sel ? ' now' : '') }, el('span', { class: 'n' }, q.slot), crest(q.team, 30), el('div', { class: 'who' }, el('div', { class: 'nm' }, q.team.nick), el('small', {}, q.sel === cur.sel ? 'on the clock' : '')),
      canUp ? el('button', { class: 'btn', style: 'width:auto;padding:2px 8px;font-size:12px', 'data-tip': 'Ask what they want for this pick', onclick: () => { const rd = pyJSON(`SESSION.draft_act('read_trade_up', target=${JSON.stringify(q.id)})`); if (!rd.ok) { notify(rd); return; } if (confirm(`${rd.line}\n\nSend ${rd.sends.map(x => x.replace(/^(\d+)-(\d+)-(\w+)$/, '$1 R$2 ($3)')).join(', ')} for pick ${rd.slot}?`)) act('trade_up', `target=${JSON.stringify(q.id)}, sends=${JSON.stringify(rd.sends)}`); } }, 'Trade Up') : el('span', {})));
  }
  right.append(nx);
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
  const tabs = el('div', { class: 'tabs', style: 'padding:8px 14px 0' }); for (const k of ['Division', 'Conference']) tabs.append(el('button', { 'aria-pressed': String(standingsView === k), onclick: () => { standingsView = k; renderStandings(v); } }, k)); s.append(tabs);
  if (standingsView === 'Conference') {
    for (const conf of ['AFC', 'NFC']) {
      const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, conf), el('th', { class: 'n' }, 'Seed'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', { class: 'n' }, 'T'), el('th', { class: 'n' }, 'Pct'), el('th', { class: 'n', 'data-tip': 'Point differential' }, '+/−'), el('th', { class: 'n', 'data-tip': 'Strength of victory: the win pct of the clubs beaten' }, 'SOV'), el('th', { class: 'n', 'data-tip': 'Strength of schedule: the win pct of every opponent' }, 'SOS'), el('th', {}, 'Form')));
      for (const r of v.conferences[conf]) t.append(el('tr', { style: r.me ? 'background:var(--sheet-2)' : '' }, el('td', {}, stripe(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.seed ? el('span', { class: 'seed ' + (r.seed === 1 ? 'bye' : 'in') + (r.me ? ' me' : '') }, r.seed) : ''), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', { class: 'n' }, r.t), el('td', { class: 'n' }, r.pct.toFixed(3).replace(/^0/, '')), el('td', { class: 'n', style: r.pd > 0 ? 'color:var(--ok)' : r.pd < 0 ? 'color:var(--danger)' : '' }, (r.pd > 0 ? '+' : '') + r.pd), el('td', { class: 'n' }, r.sov != null ? r.sov.toFixed(3).replace(/^0/, '') : '—'), el('td', { class: 'n' }, r.sos != null ? r.sos.toFixed(3).replace(/^0/, '') : '—'), el('td', {}, formDots(r.form))));
      s.append(t);
    }
    if (v.notes.length) s.append(el('div', { class: 'legend-line' }, 'Ties: ' + v.notes.join(' ')));
    page.append(s); page.append(pictureSheet(v)); return;
  }
  const grid = el('div', { class: 'divgrid' });
  for (const d of v.divisions) {
    const box = el('div', { class: 'divbox' }, el('h4', {}, d.name)); const t = el('table', { class: 'tbl' });
    t.append(el('tr', {}, el('th', {}, 'Club'), el('th', { class: 'n' }, 'W'), el('th', { class: 'n' }, 'L'), el('th', { class: 'n' }, 'T'), el('th', { class: 'n' }, 'Pct'), el('th', { class: 'n', 'data-tip': 'Points for' }, 'PF'), el('th', { class: 'n', 'data-tip': 'Points against' }, 'PA'), el('th', { class: 'n', 'data-tip': 'Point differential' }, '+/−'), el('th', {}, 'Form')));
    for (const r of d.rows) t.append(el('tr', { style: r.me ? 'background:var(--sheet-2)' : '' }, el('td', {}, stripe(r.club.abbr, r.club.name)), el('td', { class: 'n' }, r.w), el('td', { class: 'n' }, r.l), el('td', { class: 'n' }, r.t), el('td', { class: 'n' }, r.pct.toFixed(3).replace(/^0/, '')), el('td', { class: 'n' }, r.pf), el('td', { class: 'n' }, r.pa), el('td', { class: 'n', style: r.pd > 0 ? 'color:var(--ok)' : r.pd < 0 ? 'color:var(--danger)' : '' }, (r.pd > 0 ? '+' : '') + r.pd), el('td', {}, formDots(r.form))));
    box.append(t); grid.append(box);
  }
  s.append(grid);
  if (v.notes.length) s.append(el('div', { class: 'legend-line' }, 'Ties: ' + v.notes.join(' ')));
  page.append(s); page.append(pictureSheet(v));
}
let standingsView = 'Division';
function pictureSheet(v) {
  const r = el('section', { class: 'sheet c4' }, el('h2', {}, 'Playoff Picture', el('small', {}, 'seeds as of today')));
  for (const c of v.picture) {
    r.append(el('div', { class: 'h5', style: 'padding:10px 12px 4px' }, c.conf));
    const t = el('table', { class: 'tbl' });
    for (const x of c.seeds) t.append(el('tr', { style: x.me ? 'background:var(--sheet-2)' : '' }, el('td', { style: 'width:34px' }, el('span', { class: 'seed ' + (x.bye ? 'bye' : 'in') + (x.me ? ' me' : '') }, x.seed)), el('td', {}, stripe(x.club.abbr, x.club.name), x.bye ? el('span', { class: 'clinch' }, 'bye') : ''), el('td', { class: 'n' }, x.record)));
    for (const x of c.hunt) t.append(el('tr', { style: (x.me ? 'background:var(--sheet-2);' : '') + 'opacity:.75' }, el('td', {}, el('span', { class: 'seed bub' }, '·')), el('td', {}, stripe(x.club.abbr, x.club.name), el('span', { class: 'clinch', style: 'color:var(--ink-3)' }, 'in the hunt')), el('td', { class: 'n' }, x.record)));
    r.append(t);
  }
  r.append(el('div', { class: 'legend-line' }, 'Division winners seed one through four; the one seed has the bye. Ties break by the league rules.'));
  return r;
}

function renderSchedule(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('schedule');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, 'Schedule', el('small', {}, `Week ${v.week}`)));
  s.append(el('div', { class: 'tabs', style: 'padding:8px 14px 0' }, el('button', { 'aria-pressed': 'true' }, 'League Schedule'), el('button', { 'aria-pressed': 'false', onclick: () => renderTeamSchedule(pyJSON(`SESSION.league_view('team_schedule')`)) }, 'Team Schedule')));
  const nav = el('div', { class: 'wknav' }, el('span', { class: 'lab' }, 'Week')); for (const w of v.weeks) nav.append(el('button', { 'aria-pressed': String(w === v.week), onclick: () => renderSchedule(pyJSON(`SESSION.league_view('schedule', week=${w})`)) }, w)); s.append(nav);
  const grid = el('div', { class: 'wkgrid' });
  for (const g of v.games) {
    const card = el('div', { class: 'game' + (g.mine ? ' mine' : '') + (g.done ? '' : ' upcoming') },
      el('div', { class: 'tm' + (g.done ? (g.winner === g.away.abbr ? ' w' : ' l') : '') }, stripe(g.away.abbr), el('span', {}, g.away.name), el('small', { style: 'color:var(--ink-3)' }, g.away_rec)), el('div', { class: 'sc' }, g.done ? g.ap : ''),
      el('div', { class: 'tm' + (g.done ? (g.winner === g.home.abbr ? ' w' : ' l') : '') }, stripe(g.home.abbr), el('span', {}, g.home.name), el('small', { style: 'color:var(--ink-3)' }, g.home_rec)), el('div', { class: 'sc' }, g.done ? g.hp : ''),
      el('div', { class: 'meta' }, g.done ? 'Final' + (g.mine ? ' · your game' : '') : (g.mine ? 'Your game' : 'Upcoming')));
    if (g.box) { card.onclick = () => { location.hash = `#gameday/${v.week}`; }; card.style.cursor = 'pointer'; card.setAttribute('data-tip', 'Open the box score'); }
    grid.append(card);
  }
  s.append(grid);
  if (v.byes.length) s.append(el('div', { class: 'legend-line' }, 'Byes: ' + v.byes.map(b => b.abbr).join(', ')));
  page.append(s);
}

function renderTeamSchedule(v) {
  renderRail(v.rail); const page = persPage(); lgSecond('schedule');
  const s = el('section', { class: 'sheet c12' }, el('h2', {}, `${v.team.name} · ${v.record}`, el('small', {}, `bye week ${v.byes.join(', ') || '—'}`)));
  const sel = el('select', { class: 'btn', style: 'width:auto' }); for (const c of v.clubs) sel.append(el('option', { value: c.abbr, selected: c.abbr === v.team.abbr ? '' : null }, c.name)); sel.onchange = () => renderTeamSchedule(pyJSON(`SESSION.league_view('team_schedule', team=${JSON.stringify(sel.value)})`));
  s.append(el('div', { class: 'tabs', style: 'padding:8px 14px 0;gap:10px;align-items:center' }, el('button', { 'aria-pressed': 'false', onclick: () => renderSchedule(pyJSON(`SESSION.league_view('schedule')`)) }, 'League Schedule'), el('button', { 'aria-pressed': 'true' }, 'Team Schedule'), sel));
  const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', { class: 'n' }, 'Wk'), el('th', { class: 'l' }, 'Opponent'), el('th', {}, 'Record'), el('th', {}, 'Result'), el('th', { class: 'n' }, 'Score')));
  for (const g of v.games) t.append(el('tr', { style: g.done && g.result === 'W' ? '' : g.done ? 'color:var(--ink-2)' : 'color:var(--ink-3)' }, el('td', { class: 'n' }, g.week), el('td', { class: 'l' }, el('span', { style: 'display:inline-block;width:22px;color:var(--ink-3)' }, g.home ? 'vs' : 'at'), stripe(g.opp.abbr, g.opp.name)), el('td', {}, g.opp_rec), el('td', {}, g.result ? el('span', { style: `font-family:var(--display);font-weight:900;color:${g.result === 'W' ? 'var(--ok)' : g.result === 'L' ? 'var(--danger)' : 'var(--ink-2)'}` }, g.result) : 'Upcoming'),
    el('td', { class: 'n' }, g.done ? (g.box ? el('a', { href: `#gameday/${g.week}`, class: 'score-link', 'data-tip': 'Open the box score' }, `${g.mine}–${g.theirs}`) : `${g.mine}–${g.theirs}`) : '')));
  for (const b of v.byes) { const row = el('tr', { style: 'color:var(--ink-3)' }, el('td', { class: 'n' }, b), el('td', { colspan: '4' }, 'Bye')); const rows = Array.from(t.children); const idx = rows.findIndex(r => r.children && r.children[0] && +r.children[0].textContent > b); if (idx > 0) t.insertBefore(row, rows[idx]); else t.append(row); }
  s.append(t); page.append(s);
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
  s.append(grid);
  if (v.advanced && v.advanced.length) {
    s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Advanced', el('small', {}, 'minimums scale with the games played')));
    const ag = el('div', { class: 'leaders' });
    for (const b of v.advanced) { const box = el('div', { class: 'lbox' }, el('h4', {}, b.title, el('small', {}, b.unit))); b.rows.forEach((r, i) => box.append(el('div', { class: 'lrow', style: r.mine ? 'background:var(--sheet-2)' : '' }, el('span', { class: 'r' }, i + 1), el('div', { class: 'nm', style: 'cursor:pointer', onclick: () => { location.hash = '#club/player/' + r.pid; } }, r.name, el('small', {}, `${r.pos} · ${r.team} · n ${r.n}`)), el('span', { class: 'v' }, r.v)))); ag.append(box); }
    s.append(ag);
  }
  page.append(s);
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
  if (v.careers && v.careers.some(c => c.rows.length)) {
    s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Career Leaders', el('small', {}, 'active players in gold')));
    const cg = el('div', { class: 'leaders' });
    for (const c of v.careers) { if (!c.rows.length) continue; const box = el('div', { class: 'lbox' }, el('h4', {}, c.title)); c.rows.forEach((r, i) => box.append(el('div', { class: 'lrow', style: r.mine ? 'background:var(--sheet-2)' : '' }, el('span', { class: 'r' }, i + 1), el('div', { class: 'nm', style: `cursor:pointer;${r.active ? 'color:var(--club-2)' : ''}`, onclick: () => { location.hash = '#club/player/' + r.pid; } }, r.name, el('small', {}, r.pos)), el('span', { class: 'v' }, r.v)))); cg.append(box); }
    s.append(cg);
  }
  if (v.ledger && v.ledger.length) {
    s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Coaching Ledger', el('small', {}, `${v.ledger.length} stints on record`)));
    const t = el('table', { class: 'tbl' }); t.append(el('tr', {}, el('th', {}, 'Club'), el('th', {}, 'Coach'), el('th', { class: 'n' }, 'From'), el('th', { class: 'n' }, 'To'), el('th', {}, 'Record')));
    for (const x of v.ledger) t.append(el('tr', {}, el('td', {}, stripe(x.club.abbr, x.club.name)), el('td', {}, x.name), el('td', { class: 'n' }, x.frm ?? '—'), el('td', { class: 'n' }, x.current ? 'now' : (x.to ?? '—')), el('td', {}, x.record || '')));
    s.append(t);
  }
  s.append(el('h2', { style: 'border-top:1px solid var(--rule-2)' }, 'Hall of Fame', el('small', {}, `${v.hall.length} inducted`)));
  const hall = el('div', { class: 'hall' }); for (const h of v.hall) hall.append(el('div', { class: 'bust' }, el('div', { class: 'nm' }, h.name), el('div', { class: 'pos' }, `${h.pos} · ${h.seasons || '?'} seasons`), el('div', { class: 'why' }, h.why), el('div', { class: 'yr' }, `Class of ${h.inducted}`))); if (!v.hall.length) hall.append(el('div', { class: 'empty' }, 'A retired player is eligible five offseasons after he stops.'));
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
  for (const x of v.suggestions) sug.append(el('div', { class: 'sug-row' + (x.taken ? ' on' : '') }, el('div', { class: 't' }, x.text, el('small', {}, `${x.side} · ${x.why}`)), el('div', { class: 'a', style: 'display:flex;gap:4px' }, x.taken ? el('button', { class: 'btn quiet', onclick: () => { notify(pyJSON(`SESSION.plan_act('untake', i=${x.i})`)); reload(); } }, 'Undo') : el('button', { class: 'btn go', onclick: () => { notify(pyJSON(`SESSION.plan_act('take', i=${x.i})`)); reload(); } }, 'Take'), x.taken ? '' : el('button', { class: 'btn quiet', 'data-tip': 'Hide it for now', onclick: e => e.currentTarget.closest('.sug-row').remove() }, 'Skip'))));
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
  const shadowWord = v.travel ? (v.travel_target ? `${v.my_cb1 ? v.my_cb1.name : 'CB1'} on ${v.travel_target.name}` : `${v.my_cb1 ? v.my_cb1.name : 'CB1'} follows their best receiver`) : 'Corners stay by side';
  const tr = el('div', { class: 'dcard' }, el('div', { class: 'k' }, 'Shadow'), el('div', { class: 's' }, shadowWord));
  const tro = el('div', { class: 'opts' }, el('button', { class: 'btn chip' + (!v.travel ? ' go' : ''), onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='travel_target', value='')`); pyJSON(`SESSION.plan_act('set_decision', key='travel', value=False)`); reload(); } }, 'No Shadow'));
  for (const w of v.their_wrs) tro.append(el('button', { class: 'btn chip' + (v.travel && v.travel_target && v.travel_target.pid === w.pid ? ' go' : ''), 'data-tip': `${v.my_cb1 ? v.my_cb1.name : 'Your best corner'} follows him all game`, onclick: () => { pyJSON(`SESSION.plan_act('set_decision', key='travel_target', value=${JSON.stringify(w.pid)})`); reload(); } }, `${v.my_cb1 ? v.my_cb1.name : 'CB1'} on ${w.name.split(' ').pop()} · ${w.ovr}`));
  tr.append(tro); dec.append(tr);
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
  const men = el('div', {}, el('div', { class: 'h5' }, 'Players Who Matter')); for (const p of v.stars) men.append(el('div', { class: 'plate', style: 'margin-bottom:4px;cursor:pointer', onclick: () => { location.hash = '#club/player/' + p.pid; } }, el('div', { class: 'no' }, p.pos), el('div', { class: 'nm' }, p.name), el('div', { class: 'ov' }, p.ovr))); if (v.injured.length) { men.append(el('div', { class: 'h5', style: 'margin-top:10px' }, 'Their Injured Starters')); for (const p of v.injured) men.append(el('div', { style: 'font-size:13px;color:var(--ink-2);padding:3px 0' }, `${p.name} (${p.pos}) · back week ${p.back}`)); }
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
  window.addEventListener('hashchange', () => { if (location.hash.startsWith('#portal/inbox/')) openMessage(+location.hash.split('/').pop()); else if (location.hash.startsWith('#portal') || location.hash === '') refresh(); else if (location.hash.startsWith('#gameday')) { const wk = location.hash.split('/')[1]; renderGameDay(pyJSON(wk ? `SESSION.gameday_view(week=${+wk})` : 'SESSION.gameday_view()')); } else if (location.hash.startsWith('#club/player/')) renderCard(pyJSON(`SESSION.club_card(${JSON.stringify(location.hash.split('/').pop())})`)); else if (location.hash.startsWith('#club/depth')) renderDepth(pyJSON(`SESSION.club_depth(${JSON.stringify(depthPkg)})`)); else if (location.hash.startsWith('#club')) { clubTab = location.hash.startsWith('#club/ps') ? 'ps' : 'active'; renderRoster(pyJSON('SESSION.club_roster()')); } else if (location.hash.startsWith('#gameplan')) { const sub = location.hash.split('/')[1] || 'week'; if (sub === 'report') renderReport(pyJSON(`SESSION.plan_view('report')`)); else renderThisWeek(pyJSON(`SESSION.plan_view('this_week')`)); } else if (location.hash.startsWith('#league')) { const sub = location.hash.split('/')[1] || 'standings'; const fn = { standings: renderStandings, schedule: renderSchedule, transactions: renderTransactions, stats: renderStats, awards: renderAwards, coaching: renderCoaching, almanac: renderAlmanac }[sub] || renderStandings; fn(pyJSON(`SESSION.league_view(${JSON.stringify(sub in LG ? sub : 'standings')})`)); } else if (location.hash.startsWith('#draft')) { const sub = location.hash.split('/')[1] || 'board'; if (sub === 'day') renderDraftDay(pyJSON(`SESSION.draft_view('draft_day')`)); else if (sub === 'spring') renderSpring(pyJSON(`SESSION.draft_view('spring')`)); else if (sub === 'picks') renderPicks(pyJSON(`SESSION.draft_view('picks')`)); else renderBoard(pyJSON(`SESSION.draft_view('board')`)); } else if (location.hash.startsWith('#frontoffice')) { const sub = location.hash.split('/')[1] || 'owner'; if (sub === 'identity') { idPreview = null; renderIdentity(pyJSON(`SESSION.frontoffice('identity')`)); } else if (sub === 'staff') renderStaff(pyJSON(`SESSION.frontoffice('staff')`)); else if (sub === 'cap') renderCap(pyJSON(`SESSION.frontoffice('cap')`)); else renderOwner(pyJSON(`SESSION.frontoffice('owner')`)); } else if (location.hash.startsWith('#personnel')) { const sub = location.hash.split('/')[1] || 'trades'; if (sub === 'fa') renderFA(pyJSON(`SESSION.personnel('free_agency')`)); else if (sub === 'wire') renderWire(pyJSON(`SESSION.personnel('waivers')`)); else if (sub === 'extensions') renderExtensions(pyJSON(`SESSION.personnel('extensions')`)); else { if (!tradeState.keep) { tradeState.a = []; tradeState.b = []; } tradeState.keep = false; renderTrades(pyJSON(`SESSION.personnel('trades'${tradeState.other ? ', other=' + JSON.stringify(tradeState.other) : ''})`)); } } else { const page = $('#page'); page.innerHTML = ''; page.style.gridTemplateColumns = '1fr'; page.append(el('section', { class: 'sheet' }, el('h2', {}, location.hash.slice(1).split('/')[0].replace(/^\w/, c => c.toUpperCase())), el('div', { class: 'empty' }, 'This page is next to be wired.'), el('div', { class: 'foot' }, el('button', { class: 'btn', onclick: () => { location.hash = '#portal'; } }, 'Back to Portal')))); } });
})();
