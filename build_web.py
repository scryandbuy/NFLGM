import re
"""Assemble docs/engine from the repo: the modules a session imports and the data they read."""
import json, os, shutil, sys, importlib
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'docs', 'engine')
MODULES = ['halftime', 'staff_traits', 'club_notes', 'league_notes', 'adjust', 'advanced_stats', 'almanac', 'awards', 'cap_engine', 'cap_accounting', 'coaching_pool', 'contract_structure', 'contracts', 'coverage', 'coverage_call', 'cutdown', 'decisions',
           'dev_roll', 'defense_roles', 'offense_roles', 'draft', 'draft_plan', 'draft_class', 'draft_balance', 'events', 'extensions', 'firing_model', 'formations', 'franchise', 'free_agency', 'game', 'gameplan', 'gameplan_week', 'gm_engine',
           'health', 'identity', 'identity_catalog', 'inbox', 'inbox_events', 'injury_status', 'ir_and_hiring', 'league', 'market', 'matchups', 'min_salary', 'morale', 'morale_system',
           'negotiation_engine', 'negotiations', 'newgens', 'otc_2026', 'personality', 'player_background', 'playcall', 'plays', 'position_change', 'postseason', 'practice_squad', 'progression_engine',
           'regression', 'retirement', 'rookie_baseline', 'roster_construction', 'roster_needs', 'rosters', 'schedule', 'schemes', 'scouting', 'season', 'session', 'spring', 'staff', 'standings_and_seeding', 'tags',
           'targets', 'field_fit', 'stable', 'ticker', 'gameday', 'gm_surfaces', 'draft_day', 'views_club', 'views_personnel', 'views_frontoffice', 'views_draft', 'views_league', 'views_gameplan', 'trade_engine', 'trades', 'valuation', 'views', 'waivers', 'weather', 'xp', 'xp_spend', 'zones']
DATA = ['newgen_shape.json', 'league_seed_2026.csv', 'schedule_2026.csv', 'cfb27_ratings.csv', 'aging_curves.json', 'pick_values.json', 'wp_model.json', 'production_scores.json', 'free_agent_pool.csv', 'original_player_name_hashes.json']
os.makedirs(OUT, exist_ok=True)
def _check_imports():
    """Every local module any shipped module imports must itself be shipped; a module left off the list fails
    silently in the browser (the halftime read did for weeks)."""
    local = {f[:-3] for f in os.listdir(HERE) if f.endswith('.py')}
    missing = set()
    for m in MODULES:
        src = open(os.path.join(HERE, m + '.py')).read()
        for name in re.findall(r'^\s*(?:from|import)\s+([a-zA-Z_][\w]*)', src, re.M) + re.findall(r'import\s+([a-zA-Z_][\w]*)\s+as\s+', src):
            if name in local and name not in MODULES and name not in ('build_web', 'calibrate', 'xp_cost_solve'): missing.add(name)
    if missing: raise SystemExit(f"build_web: modules imported but not shipped: {sorted(missing)}")
_check_imports()
for m in MODULES: shutil.copy(os.path.join(HERE, m + '.py'), OUT)
for d in DATA: shutil.copy(os.path.join(HERE, d), OUT)
import hashlib
# Git may check out text with CRLF on Windows. Hash normalized bytes so running
# the build on either platform gives the same cache stamp for the same content.
def _stamp_bytes(path):
    return open(path, 'rb').read().replace(b'\r\n', b'\n')
# the stamp covers the engine AND the shell, so a change to app.js or style.css alone shows in the header too
build = hashlib.sha1(b''.join(_stamp_bytes(os.path.join(OUT, f)) for f in sorted(os.listdir(OUT)) if f != 'manifest.json' and os.path.isfile(os.path.join(OUT, f))) + _stamp_bytes('docs/app.js') + _stamp_bytes('docs/style.css')).hexdigest()[:10]
json.dump(dict(modules=MODULES, data=DATA, build=build), open(os.path.join(OUT, 'manifest.json'), 'w'))
# the page's own script and stylesheet carry a stamp too, so a new push is never served from a stale cache: the
# stamp is the hash of app.js and style.css together
import re as _re
_ui = hashlib.sha1(_stamp_bytes('docs/app.js') + _stamp_bytes('docs/style.css')).hexdigest()[:10]
_html = open('docs/index.html').read()
_html = _re.sub(r'app\.js\?v=[0-9a-f]+', f'app.js?v={_ui}', _html)
_html = _re.sub(r'style\.css\?v=[0-9a-f]+', f'style.css?v={_ui}', _html)
open('docs/index.html', 'w').write(_html)
print(f"docs/engine: {len(MODULES)} modules, {len(DATA)} data files, {sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT)) // 1024} KB")
