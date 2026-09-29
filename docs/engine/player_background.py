"""Fictional, cosmetic home states. Never draw from the simulation RNG."""
import hashlib
import re

# Design weights, not a claim about real player birthplaces or census totals.
# Keep this version stable: existing saves also store the assigned value.
STATE_WEIGHTS = (
    ('Alabama', 30), ('Alaska', 1), ('Arizona', 14), ('Arkansas', 12),
    ('California', 90), ('Colorado', 10), ('Connecticut', 5), ('Delaware', 2),
    ('Florida', 100), ('Georgia', 65), ('Hawaii', 6), ('Idaho', 3),
    ('Illinois', 22), ('Indiana', 14), ('Iowa', 10), ('Kansas', 8),
    ('Kentucky', 12), ('Louisiana', 35), ('Maine', 1), ('Maryland', 18),
    ('Massachusetts', 6), ('Michigan', 25), ('Minnesota', 10), ('Mississippi', 24),
    ('Missouri', 18), ('Montana', 2), ('Nebraska', 7), ('Nevada', 6),
    ('New Hampshire', 1), ('New Jersey', 20), ('New Mexico', 3), ('New York', 14),
    ('North Carolina', 30), ('North Dakota', 2), ('Ohio', 40), ('Oklahoma', 15),
    ('Oregon', 8), ('Pennsylvania', 28), ('Rhode Island', 1), ('South Carolina', 23),
    ('South Dakota', 2), ('Tennessee', 23), ('Texas', 110), ('Utah', 10),
    ('Vermont', 1), ('Virginia', 22), ('Washington', 14), ('West Virginia', 4),
    ('Wisconsin', 12), ('Wyoming', 1),
)
STATES = frozenset(state for state, _ in STATE_WEIGHTS)
TOTAL_WEIGHT = sum(weight for _, weight in STATE_WEIGHTS)


def state_for(pid):
    """Stable weighted draw from an immutable player ID, independent of save seed."""
    digest = hashlib.sha256(f'home-state-v1|{pid}'.encode('utf-8')).digest()
    ticket = int.from_bytes(digest[:8], 'big') % TOTAL_WEIGHT
    for state, weight in STATE_WEIGHTS:
        if ticket < weight:
            return state
        ticket -= weight


def home_state(player):
    """Read without mutating the player, including older fixtures and save records."""
    current = getattr(player, 'home_state', None)
    if current in STATES:
        return current
    return state_for(player.pid)


def restore_background(player):
    """Migrate old players, preserving the old college-presence eligibility flag."""
    previous = getattr(player, 'college', None)
    if getattr(player, 'home_state', None) not in STATES:
        player.home_state = state_for(player.pid)
    # Kept for older UDFA eligibility code; never retain a school name here.
    player.college = player.home_state if previous else None


def migrate_saved_backgrounds(data):
    """Update archived scouting bios and messages when loading an older save.

    Only known bio fields and exact player bio phrases are replaced; football
    team names, IDs, scouting tiers, and other historical facts are untouched.
    """
    players = data.get('players') or {}
    states = {}
    phrases = {}
    for pid, p in players.items():
        state = p.get('home_state')
        if state not in STATES:
            state = state_for(pid)
        states[str(pid)] = state
        school = p.get('college')
        if school and school != state:
            old = f"{p.get('name')} ({p.get('pos')}, {school})"
            phrases[old] = f"{p.get('name')} ({p.get('pos')}, {state})"
    pattern = re.compile('|'.join(re.escape(x) for x in phrases)) if phrases else None

    def migrate(value):
        if isinstance(value, list):
            return [migrate(x) for x in value]
        if isinstance(value, dict):
            out = {k: migrate(v) for k, v in value.items() if k != 'college'}
            if 'college' in value:
                pid = str(value.get('pid') or '')
                current = value.get('home_state')
                out['home_state'] = (current if current in STATES else
                                     states.get(pid) or state_for(pid or value.get('name', 'unknown')))
            return out
        if isinstance(value, str) and pattern and ' (' in value:
            return pattern.sub(lambda m: phrases[m.group()], value)
        return value

    out = dict(data)
    for key in ('spring_news', 'inbox', 'history', 'transactions', 'last_draft', 'almanac'):
        if key in out:
            out[key] = migrate(out[key])
    return out
