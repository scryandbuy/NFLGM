"""Assemble web/engine from the repo: the modules a session imports and the data they read."""
import json, os, shutil, sys, importlib
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'web', 'engine')
MODULES = ['adjust', 'advanced_stats', 'almanac', 'awards', 'cap_engine', 'coaching_pool', 'contract_structure', 'contracts', 'coverage', 'coverage_call', 'cutdown', 'decisions',
           'dev_roll', 'draft', 'draft_class', 'events', 'extensions', 'firing_model', 'formations', 'franchise', 'free_agency', 'game', 'gameplan', 'gameplan_week', 'gm_engine',
           'health', 'identity', 'identity_catalog', 'inbox', 'injury_status', 'ir_and_hiring', 'league', 'market', 'matchups', 'min_salary', 'morale', 'morale_system',
           'negotiation_engine', 'negotiations', 'newgens', 'otc_2026', 'personality', 'playcall', 'plays', 'position_change', 'postseason', 'practice_squad', 'progression_engine',
           'regression', 'retirement', 'roster_construction', 'rosters', 'schedule', 'schemes', 'scouting', 'season', 'session', 'spring', 'staff', 'standings_and_seeding', 'tags',
           'targets', 'ticker', 'gameday', 'views_club', 'views_personnel', 'views_frontoffice', 'trade_engine', 'trades', 'valuation', 'views', 'waivers', 'weather', 'xp', 'xp_spend', 'zones']
DATA = ['league_seed_2026.csv', 'schedule_2026.csv', 'cfb27_ratings.csv', 'aging_curves.json', 'pick_values.json', 'wp_model.json', 'production_scores.json']
os.makedirs(OUT, exist_ok=True)
for m in MODULES: shutil.copy(os.path.join(HERE, m + '.py'), OUT)
for d in DATA: shutil.copy(os.path.join(HERE, d), OUT)
json.dump(dict(modules=MODULES, data=DATA), open(os.path.join(OUT, 'manifest.json'), 'w'))
print(f"web/engine: {len(MODULES)} modules, {len(DATA)} data files, {sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT)) // 1024} KB")
