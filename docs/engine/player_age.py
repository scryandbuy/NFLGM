"""Birthdays, football calendar dates, and fixed seasonal development ages.

The simulation advances in weeks/stops, so birthdays crossed between stops are
reflected at the next stop. No birthday consumes RNG or changes ratings.
"""
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
import csv
import hashlib

VERSION = 1
# Dates are simulation calendar anchors, not a claim about a real schedule.
OFFSEASON_DATES = ((2, 15), (2, 20), (2, 25), (3, 10), (3, 11),
                   (3, 12), (3, 20), (3, 27), (4, 3), (4, 10),
                   (4, 17), (4, 22), (4, 27), (7, 25), (8, 25))


def anniversary(born, year):
    # February 29 birthdays are observed on February 28 in non-leap years.
    try:
        return born.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def age_on(birth_date, when):
    born = date.fromisoformat(str(birth_date))
    when = date.fromisoformat(when) if isinstance(when, str) else when
    years = when.year - born.year - (when < anniversary(born, when.year))
    last = anniversary(born, born.year + years)
    following = anniversary(born, born.year + years + 1)
    return years + (when - last).days / (following - last).days


def development_age(player):
    value = getattr(player, 'development_age', None)
    return float(player.age if value is None else value)


def review_age(player):
    """Season just played; retain compatibility with standalone legacy models."""
    born = getattr(player, 'birth_date', None)
    year = getattr(player, 'development_year', None)
    if born and year is not None:
        return age_on(born, date(int(year), 9, 1))
    value = getattr(player, 'development_age', None)
    return float(player.age) - 1.0 if value is None else float(value)


def week_date(year, week):
    start = date(int(year), 9, 7)
    start += timedelta(days=(6 - start.weekday()) % 7)
    return start + timedelta(weeks=max(1, int(week)) - 1)


def stop_date(year, stop, *, week=0, phase='preseason', calendar_version=0):
    if stop:
        kind = stop[0]
        if kind == 'offseason':
            index = int(stop[1])
            if calendar_version:
                from offseason_calendar import AGE_INDICES
                index = AGE_INDICES[index]
            # League.year changes while step 3 executes, not on January 1.
            return date(int(year) + (index <= 3), *OFFSEASON_DATES[index])
        if kind == 'week':
            return week_date(year, stop[1])
        if kind == 'playoffs':
            return week_date(year, 19 + min(3, int(stop[1]) if len(stop) > 1 else 0))
        if kind in ('cutdown', 'wire'):
            return date(int(year), 8, 25 if kind == 'cutdown' else 28)
    if phase in ('regular', 'playoffs'):
        return week_date(year, max(1, week))
    if phase == 'offseason':
        return date(int(year) + 1, 2, 15)
    if phase == 'free_agency':
        return date(int(year), 3, 20)
    return date(int(year), 8, 25)


@lru_cache(maxsize=1)
def seed_birthdays():
    """IDs survive name changes. Read the shipped source, never live websites."""
    out = {}
    root = Path(__file__).parent
    for filename in ('league_seed_2026.csv', 'free_agent_pool.csv'):
        path = root / filename
        if not path.exists():
            continue
        with path.open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                try:
                    if filename.startswith('league_seed'):
                        pid = row['pid']; born = date.fromisoformat(row['birth_date'])
                    else:
                        # Synthetic reserve templates are reused in future years.
                        if row.get('iteration') == 'LS Reserve 2026 v1':
                            continue
                        pid = 'FA' + str(int(float(row['player_id'])))
                        born = date(*(int(float(row[k])) for k in ('birth_year', 'birth_month', 'birth_day')))
                    out[pid] = born.isoformat()
                except (ValueError, KeyError, TypeError):
                    continue
    return out


def inferred_birthday(player, when):
    """Preserve unknown players' current age; assign once, without live RNG."""
    age = max(0., float(player.age))
    years = int(age)
    fraction = age - years
    if fraction:
        born = when - timedelta(days=round(age * 365.2425))
        # Rounding near midnight/a leap year must not add or remove a whole
        # year when the only evidence we have is the saved age.
        while int(age_on(born.isoformat(), when)) > years:
            born += timedelta(days=1)
        while int(age_on(born.isoformat(), when)) < years:
            born -= timedelta(days=1)
        return born.isoformat()
    # Integer-only legacy ages do not imply every player shares a birthday.
    offset = int.from_bytes(hashlib.sha256(str(player.pid).encode()).digest()[:4], 'big') % 365
    last = when - timedelta(days=offset)
    return anniversary(last, last.year - years).isoformat()


def initialize_player(player, league, *, use_seed=False):
    when = date.fromisoformat(getattr(league, 'game_date', f'{int(league.year)}-08-25'))
    if not getattr(player, 'birth_date', None):
        reference = date(int(player.retired_year) + 1, 2, 25) if player.retired and getattr(player, 'retired_year', None) else when
        player.birth_date = (seed_birthdays().get(player.pid) if use_seed else None) or inferred_birthday(player, reference)
    if not player.retired:
        player.age = age_on(player.birth_date, when)
    if getattr(player, 'development_year', None) != int(league.year):
        player.development_age = age_on(player.birth_date, date(int(league.year), 9, 1))
        player.development_year = int(league.year)


def set_date(league, when):
    """Monotonic, idempotent calendar; repeat calls never add age twice."""
    when = date.fromisoformat(when) if isinstance(when, str) else when
    previous = getattr(league, 'game_date', None)
    if previous:
        when = max(when, date.fromisoformat(previous))
    league.game_date = when.isoformat()
    for player in league.players.values():
        initialize_player(player, league)
    import ceiling_knowledge as CK
    CK.sync(league)


def sync_session(session):
    L = session.L
    stop = session.stop
    progress = getattr(session, 'offseason_progress', None) or {}
    if stop == ('offseason', 1) and progress.get('year_rolled') and progress.get('year') == L.year - 1:
        stop = ('offseason', 2)  # a saved retry after rollover is already in March of this year
    set_date(L, stop_date(L.year, stop, week=L.week, phase=L.phase, calendar_version=1))


def game_week(league, week):
    set_date(league, week_date(league.year, week))


def offseason(league, index, *, calendar_year=None):
    year = int(calendar_year) if calendar_year is not None else int(league.year) + (index <= 3)
    set_date(league, date(year, *OFFSEASON_DATES[index]))


def migrate(league, saved):
    league.game_date = saved.get('game_date') or stop_date(
        league.year, saved.get('_stop'), week=league.week, phase=league.phase,
        calendar_version=saved.get('_offseason_calendar_version', 0)).isoformat()
    repaired = 0
    stop = saved.get('_stop') or ()
    in_season = stop[0] in ('week', 'playoffs') if stop else league.phase in ('regular', 'playoffs')
    for p in league.players.values():
        before = int(p.age)
        legacy_age = float(p.age)
        missing_development_age = getattr(p, 'development_age', None) is None
        initialize_player(p, league, use_seed=True)
        if not saved.get('age_calendar_version') and in_season and missing_development_age:
            # A migration must not reprice XP midway through an existing season.
            # Correct the displayed birthday age now; normalize learning age at
            # the next league-year rollover. Reviews still use the DOB reference.
            p.development_age = legacy_age
        repaired += int(p.age) != before
    league.age_calendar_version = VERSION
    league.age_migration = saved.get('age_migration') or dict(version=VERSION, corrected_display_ages=repaired)
    league.regression_applied_years = list(saved.get('regression_applied_years', []))
    # A save already past this season's regression must not run it again.
    if not saved.get('age_calendar_version') and stop and stop[0] == 'offseason' and int(stop[1]) >= 3:
        closed = int(league.year) - (int(stop[1]) >= 4)
        if closed not in league.regression_applied_years:
            league.regression_applied_years.append(closed)
