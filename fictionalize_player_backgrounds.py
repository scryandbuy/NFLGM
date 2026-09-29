"""Replace source school bios with stable fictional states; preserve gameplay data."""
import csv
from pathlib import Path
from player_background import state_for

ROOT = Path(__file__).resolve().parent


def read(name):
    with (ROOT / name).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def main():
    _, seed = read('league_seed_2026.csv')
    # Joined roster rows have no pid; use the same stable player as the game.
    by_name = {r['full_name']: r['pid'] for r in seed}
    files = ('league_seed_2026.csv', 'free_agent_pool.csv', 'rosters_2026.csv',
             'player_valuations_2026.csv', 'cfb27_ratings.csv')
    for name in files:
        fields, rows = read(name)
        if 'home_state' not in fields:
            fields.append('home_state')
        for r in rows:
            if name == 'cfb27_ratings.csv':
                pid = f"C{r['id']}"
            elif name == 'free_agent_pool.csv':
                pid = f"FA{int(r['player_id'])}"
            else:
                pid = r.get('pid') or by_name[r['full_name']]
            state = state_for(pid)
            r['home_state'] = state
            if 'college' in r and r['college']:
                r['college'] = state   # legacy column; retain missing-value eligibility
            if name == 'cfb27_ratings.csv':
                r['team'] = state      # source school field, never a pro team
        with (ROOT / name).open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        print(f'{name}: {len(rows)} home states')


if __name__ == '__main__':
    main()
