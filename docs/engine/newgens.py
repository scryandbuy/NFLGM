"""
NEWGENS: the draft class after the real one.

Built onto the same template the College Football 27 class was mapped to:
your position counts, the real rookie curve at each position for the pro
overall, the seed's headroom rule for the ceiling, dev drawn 65/22/10/3
tilted to the top of the class.

WHAT VARIES. Class strength. Position and class rolls are drawn at standard
deviations 1.5 and 0.8, then their combined effect is capped and tapered by
position rank. There can still be strong quarterback years and thin tackle
years without moving an entire receiver or corner room above starter grade.

WHERE A MAN'S SHAPE COMES FROM. A real attribute profile. The college file
holds 10,931 real profiles by position; a newgen takes one at his position
as his template and is scaled to his pro overall the way the class builder
does it, physicals moving at the square root of the scale. Nothing is
invented about how a corner's ratings hang together. Height and weight ride
along.

NAMES. First names and surnames are drawn independently from the renamed
seeds. Current players and a draft class cannot share a full name. A generated
name can return after fifteen years, at most twice in a forty-year window.
The history travels with the save; original source full names stay excluded.

WHEN. The class for NEXT year's draft is generated in the offseason right
after this year's draft, and scouted then, so it is on the scouting tab
through the preseason and the season that follows.
"""
import numpy as np, pandas as pd, collections
import csv, hashlib, json, math, unicodedata
from functools import lru_cache
import targets as TG
import draft_class as DC
import draft_balance as DB

STRENGTH_SD_POS, STRENGTH_SD_CLASS = 1.5, 0.8


def _name_pools(cfb_path='cfb27_ratings.csv', seed_path='league_seed_2026.csv'):
    c = pd.read_csv(cfb_path, low_memory=False, usecols=['first_name', 'last_name'])
    m = pd.read_csv(seed_path, low_memory=False)
    col = next((c for c in ('name', 'player_name', 'full_name', 'display_name') if c in m.columns), None)
    first = list(c.first_name.dropna()); last = list(c.last_name.dropna())
    if col:
        for n in m[col].dropna():
            parts = str(n).split()
            if len(parts) >= 2:
                first.append(parts[0]); last.append(' '.join(parts[1:]))
    # keep the frequency of the real pools so common names stay common and
    # the rare ones stay rare, then dedupe the suffix junk
    first = [f for f in first if len(f) > 1 and not f.endswith('.')]
    last = [l for l in last if len(l) > 1 and l not in ('Jr.', 'Sr.', 'II', 'III', 'IV')]
    return first, last


NAME_REUSE_GAP = 15
NAME_REUSE_WINDOW = 40
NAME_REUSE_LIMIT = 2


def normalize_name(value):
    """Treat case, accents, punctuation and spacing variants as one name."""
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)).casefold() if c.isalnum())


def name_history(league):
    """Merge saved reservations with known players; also upgrades older saves.

    Player IDs distinguish legitimate repeats without counting a player again
    whenever a new class is created or a save is loaded. Removed players remain
    in the saved history, so deletion cannot bypass the reuse limits.
    """
    history = {normalize_name(key): {str(pid): int(year) for pid, year in people.items()}
               for key, people in getattr(league, 'player_name_history', {}).items()}
    for p in league.players.values():
        key = normalize_name(p.name)
        year = getattr(p, 'draft_year', None) or getattr(p, 'entry_year', None) or league.year
        history.setdefault(key, {}).setdefault(str(p.pid), int(year))
    return history


@lru_cache(maxsize=8)
def _name_catalog(cfb_path='cfb27_ratings.csv'):
    first, last = _name_pools(cfb_path=cfb_path)
    # Hashes retain the original-source exclusion after source names are replaced.
    with open('original_player_name_hashes.json', encoding='utf-8') as handle:
        blocked = set(json.load(handle))
    for path in (cfb_path, 'league_seed_2026.csv', 'free_agent_pool.csv'):
        with open(path, encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle):
                full = row.get('full_name') or (row.get('first_name', '') + ' ' + row.get('last_name', ''))
                blocked.add(hashlib.sha256(normalize_name(full).encode()).hexdigest())
    return first, last, blocked


class NameAllocator:
    """One class's allocator: reserve immediately, persist history, never return a collision."""
    def __init__(self, league, draft_year, cfb_path='cfb27_ratings.csv'):
        self.league, self.year = league, int(draft_year)
        self.first, self.last, self.blocked = _name_catalog(cfb_path)
        if not self.first or not self.last:
            raise ValueError('Newgen name pools are empty')
        self.history = league.player_name_history = name_history(league)
        self.current = {normalize_name(p.name) for p in league.players.values() if not p.retired}
        # A coprime stride visits every unique pair once. This is a bounded
        # fallback when repeated random draws collide, not an unchecked last try.
        self.unique_first = sorted({normalize_name(n): n for n in self.first}.values())
        self.unique_last = sorted({normalize_name(n): n for n in self.last}.values())
        self.capacity = len(self.unique_first) * len(self.unique_last)
        self.stride = max(1, int(self.capacity * .61803398875))
        while math.gcd(self.stride, self.capacity) != 1:
            self.stride += 1

    def available(self, value):
        key = normalize_name(value)
        if key in self.current or hashlib.sha256(key.encode()).hexdigest() in self.blocked:
            return False
        years = list(self.history.get(key, {}).values())
        return (not years or (self.year - max(years) >= NAME_REUSE_GAP
                and sum(y > self.year - NAME_REUSE_WINDOW for y in years) < NAME_REUSE_LIMIT))

    def reserve(self, value, pid):
        key = normalize_name(value)
        self.current.add(key)
        self.history.setdefault(key, {})[str(pid)] = self.year
        return value

    def draw(self, rng, pid):
        # Exactly two simulation RNG draws per name, including collisions.
        value = f'{self.first[int(rng.integers(len(self.first)))]} {self.last[int(rng.integers(len(self.last)))]}'
        if self.available(value):
            return self.reserve(value, pid)
        cursor = int(getattr(self.league, 'newgen_name_cursor', 0))
        for _ in range(self.capacity):
            index = (cursor * self.stride) % self.capacity
            cursor += 1
            self.league.newgen_name_cursor = cursor
            first, last = divmod(index, len(self.unique_last))
            value = f'{self.unique_first[first]} {self.unique_last[last]}'
            if self.available(value):
                return self.reserve(value, pid)
        raise RuntimeError('No eligible newgen names remain; expand the name pools')


def name(rng, league, draft_year, pid, allocator=None):
    return (allocator or NameAllocator(league, draft_year)).draw(rng, pid)


def build(league, rng, draft_year, cfb_path='cfb27_ratings.csv', verbose=False):
    """The class for draft_year, on league.next_class and in league.players."""
    import league as LG
    college = DC.load_college(cfb_path)
    college = college[college.school_year.isin(DC.CLASS_AGE)]
    rookies = DC.rookie_targets()
    names = NameAllocator(league, draft_year, cfb_path)
    class_shift = float(rng.normal(0.0, STRENGTH_SD_CLASS))
    out = []; strength = {}
    for pos, n in DC.COUNTS.items():
        # The college data has no LS position; centers provide the snapping,
        # awareness and blocking profile for new long snappers.
        templates = college[college.pos == ('C' if pos == 'LS' else pos)]
        if templates.empty:
            continue
        n = min(n, len(templates))
        src = DC.PROXY.get(pos, pos)
        rk = rookies.get(src, []) if src else []
        if pos in DC.FALLBACK_MEAN: rk = [DC.FALLBACK_MEAN[pos]] * 2
        pos_shift = float(rng.normal(0.0, STRENGTH_SD_POS))
        base_curve = DC.target_curve(rk, n)
        curve = DB.variation_targets(pos, base_curve, class_shift, pos_shift)
        strength[pos] = round(curve[0] - base_curve[0], 1)
        # a random real profile at the spot for each slot; the top of the class
        # leans on the better college profiles so shapes stay plausible
        ranked = templates.sort_values('overall_rating', ascending=False)
        for i in range(n):
            lo = int(len(ranked) * max(0.0, i / n - 0.25)); hi = int(len(ranked) * min(1.0, i / n + 0.35))
            row = ranked.iloc[int(rng.integers(lo, max(lo + 1, hi)))]
            ratings, _ = DC.convert(row, pos, curve[i])
            age = (22.0 if rng.random() < 0.68 else 21.0) + float(rng.uniform(0.1, 0.9))
            pid = f"N{draft_year}{pos}{i:03d}"
            p = LG.Player(pid, name(rng, league, draft_year, pid, names), pos, age, ratings,
                          dev=DC.draw_dev(i / max(n - 1, 1), rng, pos=pos),
                          draft_year=draft_year, entry_year=draft_year)
            headroom = rng.uniform(2.0, 4.5) + max(0.0, 28.0 - age) * rng.uniform(0.35, 1.15)
            pot = float(np.clip(p.ovr + headroom, p.ovr, 99.0)); spread = rng.uniform(3.0, 11.0)
            p.potential = None
            p.potential_range = (round(max(p.ovr, pot - spread), 1), round(min(99.0, pot + spread), 1))
            p.college = str(row.team); p.college_ovr = None; p.conference = str(row.get('conference', '') or '')
            p.height, p.weight = float(row.height), float(row.weight)
            out.append(p)
    out.sort(key=lambda p: -p.ovr)
    DC.shape_class(out, rng=rng)
    import xp as XP
    for p in out:
        XP.resolve_potential(p, rng)
    league.next_class = out
    league.class_strength = strength
    for p in out:
        league.players[p.pid] = p
    if verbose:
        strong = sorted(strength.items(), key=lambda kv: -kv[1])
        print(f'{len(out)} newgens for {draft_year}; class shift {class_shift:+.1f}; strongest {strong[:3]}, weakest {strong[-3:]}')
    import personality as PT
    for _p in out:
        PT.ensure(_p, rng)
    return out
