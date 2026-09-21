import { loadLeague, RATING_COLS } from '../src/rosters.js';
const L = loadLeague('/home/claude/data/league_seed_2026.csv');
const teams = Object.keys(L).sort();
console.log('teams:', teams.length, '| rating cols:', RATING_COLS.length);
const t = L[teams[0]];
console.log(teams[0], 'qb', t.qb.pid, '| ol', t.ol.length, '| db', t.db.length,
            '| wr', t.wr.map(p => `${p.pid}:${p.pos}`).join(','),
            '| k', t.k?.pid, '| depth groups', Object.keys(t.depth ?? {}).length);
