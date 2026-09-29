"""Replace NFL player names consistently across source and shipped roster data.

Run once after the input CSVs are assembled. The saved map contains fictional
names only, keyed by stable IDs, so applying it again is idempotent. Pass a
newline-delimited list of already assigned college names with --exclude.
"""
import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAP = ROOT / 'nfl_fictional_name_map.csv'
SEED = 0x4E464C474D2026
FILES = ('league_seed_2026.csv', 'rosters_2026.csv',
         'free_agent_pool.csv', 'player_valuations_2026.csv')


def read_csv(path):
    with path.open(newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def write_csv(path, fields, rows):
    # Match the repository's CRLF CSVs regardless of host line-ending settings.
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\r\n')
        writer.writeheader()
        writer.writerows(rows)


def normalize(value):
    value = unicodedata.normalize('NFKD', str(value or '')).casefold()
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return ''.join(c for c in value if c.isalnum())


def match_key(value):
    # The source preparation uses this spelling in its "key" column.
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode()
    value = value.lower().replace('.', '').replace("'", '').replace('-', ' ')
    value = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', ' ', value)
    return ' '.join(re.sub(r'[^a-z ]', '', value).split())


def component_ok(value):
    value = str(value or '').strip()
    if len(value) < 2 or re.search(r'\d|\bESPN\b', value, re.I):
        return False
    if normalize(value) in {'jr', 'sr', 'ii', 'iii', 'iv', 'v'}:
        return False
    return all(c.isalpha() or c in " .'-" for c in value)


def original_names(seed, free, college):
    names = {normalize(row['full_name']) for row in seed + free}
    names.update(normalize(f"{row['first_name']} {row['last_name']}") for row in college)
    return names


def entities(seed, free):
    out = []
    for row in seed:
        out.append(('seed', row['pid'], row))
    for row in free:
        out.append(('free_agent', row['player_id'], row))
    assert len({(kind, key) for kind, key, _ in out}) == len(out)
    return sorted(out, key=lambda e: (e[0], e[1]))


def generate(seed, free, college, reserved):
    all_players = entities(seed, free)
    first_pool = [row['first_name'].strip() for _, _, row in all_players]
    last_pool = [row['last_name'].strip() for _, _, row in all_players]
    first_pool += [row['first_name'].strip() for row in college]
    last_pool += [row['last_name'].strip() for row in college]
    first_pool = [v for v in first_pool if component_ok(v)]
    last_pool = [v for v in last_pool if component_ok(v)]
    assert len(first_pool) > 1000 and len(last_pool) > 1000
    blocked = original_names(seed, free, college) | reserved
    used = set()
    rows = []
    rng = random.Random(SEED)
    for kind, key, old in all_players:
        for _ in range(100000):
            first = rng.choice(first_pool)
            last = rng.choice(last_pool)
            name = f'{first} {last}'
            norm = normalize(name)
            if (normalize(first) == normalize(old['first_name']) or
                    normalize(last) == normalize(old['last_name']) or
                    norm in blocked or norm in used):
                continue
            used.add(norm)
            rows.append(dict(kind=kind, stable_id=key, first_name=first,
                             last_name=last, full_name=name))
            break
        else:
            raise RuntimeError(f'Could not find unique name for {kind}:{key}')
    return rows


def apply(row, replacement):
    row['first_name'] = replacement['first_name']
    row['last_name'] = replacement['last_name']
    row['full_name'] = replacement['full_name']
    key = match_key(replacement['full_name'])
    if 'key' in row:
        row['key'] = key
    if 'first' in row:
        row['first'] = key.split()[0]
    if 'last' in row:
        row['last'] = key.split()[-1]
    if 'football_name' in row:
        row['football_name'] = replacement['first_name']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exclude', type=Path,
                        help='JSON list or newline-delimited fictional college names to reserve')
    args = parser.parse_args()
    data = {file: read_csv(ROOT / file) for file in FILES}
    seed = data['league_seed_2026.csv'][1]
    roster = data['rosters_2026.csv'][1]
    free = data['free_agent_pool.csv'][1]
    values = data['player_valuations_2026.csv'][1]
    college = read_csv(ROOT / 'cfb27_ratings.csv')[1]
    reserved = set()
    if args.exclude:
        content = args.exclude.read_text(encoding='utf-8')
        names = json.loads(content) if args.exclude.suffix.lower() == '.json' else content.splitlines()
        reserved = {normalize(name) for name in names if str(name).strip()}

    if MAP.exists():
        mapping = read_csv(MAP)[1]
    else:
        mapping = generate(seed, free, college, reserved)
        write_csv(MAP, ['kind', 'stable_id', 'first_name', 'last_name', 'full_name'], mapping)
    index = {(r['kind'], r['stable_id']): r for r in mapping}
    assert len(index) == len(seed) + len(free)
    assert len({normalize(r['full_name']) for r in mapping}) == len(mapping)
    assert not ({normalize(r['full_name']) for r in mapping} & reserved)

    roster_index = {}
    for row in seed:
        replacement = index[('seed', row['pid'])]
        roster_index[(row['full_name'], row['team'])] = replacement
        roster_index[(replacement['full_name'], row['team'])] = replacement
        apply(row, replacement)
    for row in roster:
        apply(row, roster_index[(row['full_name'], row['team'])])
    for row in free:
        apply(row, index[('free_agent', row['player_id'])])
    for row in values:
        apply(row, index[('seed', row['pid'])])

    for file, (fields, rows) in data.items():
        write_csv(ROOT / file, fields, rows)
    for file in ('league_seed_2026.csv', 'free_agent_pool.csv'):
        shutil.copyfile(ROOT / file, ROOT / 'docs' / 'engine' / file)

    print(f"Assigned {len(seed)} starting-roster and {len(free)} free-agent names; "
          f"{len({normalize(r['full_name']) for r in mapping})} distinct full names.")
    for file in FILES:
        print(file, hashlib.sha256((ROOT / file).read_bytes()).hexdigest()[:12])


if __name__ == '__main__':
    main()
