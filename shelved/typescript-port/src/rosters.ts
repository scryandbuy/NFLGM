/**
 * Real rosters from the league seed.
 *
 * Every test to this point used synthetic teams: clones with a linear strength
 * spread, three receivers, one quarterback who never left the field, and no
 * positional depth. That is a harness, not a league - it removes mismatch,
 * removes the tail of every distribution, and makes any calibration suspect.
 *
 * This builds the 32 real 2026 rosters from league_seed_2026.csv: 2,114 active
 * players with all 54 Madden attributes, ordered by POSITION-SPECIFIC rating.
 *
 * Ported from rosters.py. Node only - the browser build loads a prepared JSON
 * seed rather than parsing a CSV at runtime.
 */
import { readFileSync } from 'fs';
import { Player } from './core/math.js';
import * as TG from './targets.js';
import { Roster } from './game.js';

/**
 * RFC 4180 CSV. The seed has quoted fields containing commas (college names,
 * and so on), so a naive split on ',' silently shifts every column after the
 * first quoted one - which would scramble the rating columns without erroring.
 */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; } else { quoted = false; }
      } else { field += c; }
    } else if (c === '"') {
      quoted = true;
    } else if (c === ',') {
      row.push(field); field = '';
    } else if (c === '\n') {
      row.push(field); field = '';
      rows.push(row); row = [];
    } else if (c !== '\r') {
      field += c;
    }
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  return rows;
}

export let RATING_COLS: string[] = [];

function toPlayer(row: string[], idx: Record<string, number>): Player {
  const p: any = { pid: String(row[idx['pid']]), pos: row[idx['madden_position']] };
  for (const c of RATING_COLS) {
    const v = row[idx[c]];
    if (v !== undefined && v !== '') {
      const n = Number(v);
      if (!Number.isNaN(n)) p[c] = n;
    }
  }
  return p as Player;
}

/**
 * A real team. Position groups ordered by position-specific rating, so the
 * depth chart reflects who is actually best AT THAT SPOT rather than a blended
 * overall.
 */
export function buildRoster(grp: Player[], scheme?: string): Roster | null {
  const byPos: Record<string, Player[]> = {};
  for (const p of grp) {
    (byPos[p.pos] ??= []).push(p);
  }
  for (const pos of Object.keys(byPos)) {
    byPos[pos] = TG.orderDepth(byPos[pos], pos, scheme);
  }
  const take = (pos: string, n?: number): Player[] => {
    const v = byPos[pos] ?? [];
    return n === undefined ? v : v.slice(0, n);
  };

  const qbs = take('QB');
  const hbs = [...take('HB'), ...take('FB')];
  const wrs = take('WR');
  const tes = take('TE');
  // the line in real order: LT LG C RG RT, then everyone else as depth
  const ol = [...take('LT', 1), ...take('LG', 1), ...take('C', 1),
              ...take('RG', 1), ...take('RT', 1)];
  for (const pos of ['LT', 'LG', 'C', 'RG', 'RT']) ol.push(...take(pos).slice(1));
  const dl = [...take('LEDG', 1), ...take('DT', 2), ...take('REDG', 1)];
  for (const pos of ['LEDG', 'DT', 'REDG']) dl.push(...take(pos).slice(1));
  const lb = [...take('MIKE'), ...take('WILL'), ...take('SAM')];
  const db = [...take('CB'), ...take('FS'), ...take('SS')];

  if (!qbs.length || !ol.length || !db.length) return null;
  return {
    qb: qbs[0], qbs: qbs.slice(1),
    rb: hbs.length ? hbs[0] : null, backs: hbs,
    // the pattern: three receivers, the tight end and the back
    wr: [...wrs.slice(0, 3), ...tes.slice(0, 1), ...hbs.slice(0, 1)],
    extra_blockers: [...tes.slice(1, 2), ...hbs.slice(1, 2)],
    ol, dl, lb, db,
    k: take('K', 1)[0] ?? null,
    p: take('P', 1)[0] ?? null,
    kr: wrs.length > 3 ? wrs[wrs.length - 1] : (wrs[0] ?? null),
    depth: byPos,
  };
}

/** Return {team: roster} ready for the game loop. */
export function loadLeague(path: string, scheme?: string): Record<string, Roster> {
  const rows = parseCsv(readFileSync(path, 'utf8'));
  const header = rows[0];
  const idx: Record<string, number> = {};
  header.forEach((h, i) => { idx[h] = i; });
  RATING_COLS = header.filter(c => c.endsWith('_rating') && c !== 'src_rating');

  const byTeam: Record<string, Player[]> = {};
  for (let r = 1; r < rows.length; r++) {
    const row = rows[r];
    if (row.length < header.length) continue;
    if (row[idx['roster']] !== 'active') continue;
    const team = row[idx['team']];
    (byTeam[team] ??= []).push(toPlayer(row, idx));
  }
  const league: Record<string, Roster> = {};
  // Python groups by team in SORTED key order; match it so any downstream
  // iteration over the league sees the same sequence.
  for (const team of Object.keys(byTeam).sort()) {
    const r = buildRoster(byTeam[team], scheme);
    if (r) league[team] = r;
  }
  return league;
}
