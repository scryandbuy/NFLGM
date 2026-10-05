"""
THE AWARDS.

Every rule here was fitted against the last fifteen real winners and their
actual season stat lines, not reasoned from what an award sounds like. What
the data said, in short:

  MVP is a TEAM award wearing a player's name. Fourteen of fifteen winners
  were quarterbacks, and every single one played for a top-10 team - median
  rank 2, and not one MVP in fifteen years came off a sub-.500 club. Passing
  YARDS is a bad predictor: median rank 5 and Lamar Jackson won in 2019
  ranked 22nd. Efficiency and touchdowns are what track.

  OPOY is the opposite shape. Six running backs, five quarterbacks, four
  receivers - it rotates - and thirteen of fifteen LED THE LEAGUE outright in
  a headline counting stat for their position. Team record barely features.

  DPOY is a pass-rush award. Thirteen of fifteen winners rush the passer, and
  the marker is sacks with tackles for loss and quarterback hits alongside.
  The two corners who won did it on a different axis entirely: Gilmore in
  2019 led the league in both interceptions and passes defended.

  THE ROOKIE AWARDS ARE NOT LEAGUE-WIDE. Five of fifteen offensive winners
  and six of fifteen defensive winners ranked nothing in the league top ten.
  It is a within-class competition, so it is scored against the rookie class
  and nothing else.

  COACH OF THE YEAR IS IMPROVEMENT. Median +0.412 win percentage over the
  previous season, roughly seven wins, and not one winner in fifteen years
  had a worse record than the year before. But you cannot win it from 6-11
  either: record rank median 4, worst 10.

  PROTECTOR OF THE YEAR has one season of history, so there is nothing to
  fit. It is built from the line stats plus the team context Omar asked for -
  sacks allowed, rushing, scoring, record - which is the same shape as MVP,
  where the team constraint did most of the work.

Ballots are cast at the end of the regular season and BEFORE the playoffs,
which is why this reads league.stats and never league.post_stats. Championship Game
MVP is the exception and reads a single game.
"""
import numpy as np

import standings_and_seeding as SS

# MVP, OROY, DROY, OPOY and DPOY are each a guaranteed +1 development tier.
DEV_TIER_AWARDS = ('mvp', 'opoy', 'dpoy', 'oroy', 'droy')

PASS_RUSH_POS = ('LEDG', 'REDG', 'DT', 'MIKE', 'WILL', 'SAM', 'DE', 'LB')
COVERAGE_POS = ('CB', 'FS', 'SS')
OL_POS = ('LT', 'LG', 'C', 'RG', 'RT')
# All-Pro takes the best at each spot, and how many the real team names.
ALL_PRO_SLOTS = {'QB': 1, 'HB': 1, 'FB': 1, 'WR': 3, 'TE': 1,
                 'LT': 1, 'LG': 1, 'C': 1, 'RG': 1, 'RT': 1,
                 'LEDG': 1, 'REDG': 1, 'DT': 2, 'MIKE': 1, 'WILL': 1,
                 'SAM': 1, 'CB': 2, 'FS': 1, 'SS': 1, 'K': 1, 'P': 1}


def _g(line, key):
    return float(line.get(key, 0) or 0)


def _rank(value, pool, key):
    """1 = league leader."""
    return 1 + sum(1 for l in pool if _g(l, key) > value)


class Ballot:
    """
    One season's voting. Built once, then every award reads off it, so a
    player cannot be scored against one league in one award and another in
    the next.
    """

    def __init__(self, league, season=None):
        self.L = league
        self.year = season or league.year
        self.lines = league.stats.get(self.year, {})
        self.teams = league.teams
        # record rank: MVP and Coach of the Year both gate on it
        order = sorted(self.teams, key=lambda t: -self.teams[t].win_pct)
        self.rec_rank = {t: i + 1 for i, t in enumerate(order)}

    def players(self, filt=None):
        for pid, line in self.lines.items():
            p = self.L.player(pid)
            if p is None:
                continue
            if filt and not filt(p, line):
                continue
            yield p, line

    def is_rookie(self, p):
        # Contract-service accrual is not rookie eligibility: a reserve can
        # play in an earlier season without earning an accrued season.
        participation = ('games', 'snaps', 'pass_att', 'rush_att', 'tgt',
                         'tackles', 'sacks', 'def_plays', 'pb_snaps', 'rb_snaps',
                         'fg_att', 'xp_att', 'punts', 'kr', 'pr')
        prior = list((getattr(p, 'career', None) or {}).items())
        prior += [(year, book.get(p.pid, {})) for year, book in self.L.stats.items()]
        for year, line in prior:
            if int(year) < self.year and any(_g(line, key) > 0 for key in participation):
                return False
        entry = getattr(p, 'entry_year', None) or getattr(p, 'draft_year', None)
        if entry is not None:
            return int(entry) == self.year
        # Legacy players without an entry/draft year can still qualify when
        # neither saved participation nor service establishes an earlier year.
        return getattr(p, 'accrued', 0) == 0

    # ---- scoring ------------------------------------------------------
    def passer_score(self, line):
        """
        A stand-in for EPA, which the sim does not compute. Fitted to the
        shape the real winners have: touchdowns carry, interceptions cost,
        efficiency per attempt matters and raw volume barely does.
        """
        att = _g(line, 'pass_att')
        if att < 200:
            return 0.0
        ypa = _g(line, 'pass_yds') / att
        td, ints = _g(line, 'pass_td'), _g(line, 'ints')
        comp = _g(line, 'pass_cmp') / att
        return (4.2 * td - 4.0 * ints + 22.0 * (ypa - 6.5)
                + 60.0 * (comp - 0.63) + 1.8 * _g(line, 'rush_td'))

    def skill_score(self, line):
        """Total offensive production for a non-quarterback."""
        # yards and touchdowns carry it; receptions count a little. At 4 a
        # catch a 115-catch receiver out-scored a 1,400-yard back every year
        return (_g(line, 'rush_yds') + _g(line, 'rec_yds')
                + 20.0 * (_g(line, 'rush_td') + _g(line, 'rec_td'))
                + 2.5 * _g(line, 'rec'))

    def rush_score(self, line):
        """Front-seven production, including their recorded plays in coverage."""
        # Use the existing role-development scale for ball production (3 PD,
        # 8 INT), retaining the award's established rush/tackle/FF weights.
        return (3.0 * _g(line, 'sacks') + 1.0 * _g(line, 'pressures')
                + 0.6 * _g(line, 'tackles') + 4.0 * _g(line, 'ff')
                + 3.0 * _g(line, 'pass_def') + 8.0 * _g(line, 'int_def'))

    def cover_score(self, line):
        """The other axis. Gilmore 2019 led the league in INT and PD."""
        return (8.0 * _g(line, 'int_def') + 0.5 * _g(line, 'tackles')
                + 3.0 * _g(line, 'ff') + 3.0 * _g(line, 'pass_def'))

    def def_score(self, p, line):
        if p.pos in COVERAGE_POS:
            return self.cover_score(line)
        return self.rush_score(line)

    def line_score(self, p, line):
        """Individual execution against the actual assignment's difficulty.

        Missing legacy matchup evidence keeps its original contribution.
        Protector adds the user's team context separately below.
        """
        from blocking_evaluation import line_score
        return line_score(line)

    # ================================================== the awards
    def mvp(self):
        """
        Top-10 record or nothing. That gate is not a preference: every MVP in
        fifteen years played for a top-10 team and none came off a losing one.
        """
        best, who = -1e9, None
        for p, line in self.players():
            if self.rec_rank.get(p.team, 99) > 10:
                continue
            s = self.passer_score(line)
            if s <= 0:
                # THE ADRIAN PETERSON EXCEPTION, and it has to be a genuine
                # exception. He won in 2012 with 2,097 rushing yards, nine
                # short of the all-time record - the only non-quarterback to
                # take it in fifteen years. A loose threshold here handed the
                # award to a receiver with 2,000 combined yards, which is a
                # good season and not an MVP one. So it requires leading the
                # league AND clearing 2,000 rushing yards, and it is scored
                # below any credible quarterback rather than against him.
                if _g(line, 'rush_yds') < 2000:
                    continue
                if _rank(_g(line, 'rush_yds'), self.lines.values(),
                         'rush_yds') > 1:
                    continue
                s = 1.0 + (_g(line, 'rush_yds') - 2000) * 0.02
            if s > best:
                best, who = s, p
        return who

    def opoy(self):
        """
        Position-agnostic and largely record-agnostic: the most dominant
        counting-stat season on offence. Thirteen of fifteen winners led the
        league outright in a headline stat.
        """
        best, who = -1e9, None
        for p, line in self.players():
            # a quarterback wins this about one year in eight, not most years
            s = max(self.skill_score(line), self.passer_score(line) * 11.0)
            if s > 0 and s > best:
                best, who = s, p
        return who

    def dpoy(self):
        best, who = -1e9, None
        for p, line in self.players():
            if p.pos not in PASS_RUSH_POS + COVERAGE_POS:
                continue
            s = self.def_score(p, line)
            if s > 0 and s > best:
                best, who = s, p
        return who

    def oroy(self):
        """Scored against the ROOKIE CLASS, not the league."""
        best, who = -1e9, None
        for p, line in self.players(lambda p, l: self.is_rookie(p)):
            s = max(self.skill_score(line), self.passer_score(line) * 9.0)
            if s > 0 and s > best:
                best, who = s, p
        return who

    def droy(self):
        best, who = -1e9, None
        for p, line in self.players(lambda p, l: self.is_rookie(p)):
            if p.pos not in PASS_RUSH_POS + COVERAGE_POS:
                continue
            s = self.def_score(p, line)
            if s > 0 and s > best:
                best, who = s, p
        return who

    def coty(self):
        """
        Improvement, gated on being good. Median winner improved +0.412 win
        percentage and no winner in fifteen years got worse; but record rank
        was median 4 and never worse than 10, so a 6-11 team cannot win it
        however much it improved.
        """
        best, who = -1e9, None
        for abbr, t in self.teams.items():
            if self.rec_rank.get(abbr, 99) > 10:
                continue
            # Honors can be announced before this year's history is appended.
            # Select the actual previous season in either calendar state.
            prev = next((row['win_pct'] for row in reversed(t.history)
                         if int(row.get('year', -1)) == self.year - 1), 0.5)
            gain = t.win_pct - prev
            if gain < 0:
                continue
            s = gain * 100.0 + t.win_pct * 15.0
            if s > best:
                best, who = s, abbr
        return who

    def protector(self):
        """
        Best offensive lineman. His own win rates and sacks allowed, plus the
        team context Omar asked for: what the whole line gave up, what the
        run game and the offence produced, and the record. One season of real
        history exists, so the weights are reasoned rather than fitted, and
        this is flagged as the one award here that is not data-backed.
        """
        team_ctx = {}
        for abbr in self.teams:
            sacks = rush = pts = 0.0
            for pid, line in self.lines.items():
                p = self.L.player(pid)
                if p is None or p.team != abbr:
                    continue
                sacks += _g(line, 'sacks_allowed')
                rush += _g(line, 'rush_yds')
                # A passing touchdown is already counted for its receiver.
                # Team offensive TD production counts each score once.
                pts += 6.0 * (_g(line, 'rush_td') + _g(line, 'rec_td'))
            team_ctx[abbr] = (sacks, rush, pts)
        if not team_ctx:
            return None
        sk = [v[0] for v in team_ctx.values()]
        ru = [v[1] for v in team_ctx.values()]
        pt = [v[2] for v in team_ctx.values()]
        lo_s, hi_s = min(sk), max(sk)
        lo_r, hi_r = min(ru), max(ru)
        lo_p, hi_p = min(pt), max(pt)

        best, who = -1e9, None
        for p, line in self.players(lambda p, l: p.pos in OL_POS):
            own = self.line_score(p, line)
            if own is None:
                continue
            # a man cut in November has stats and no club; the wire made
            # that a real case
            if p.team not in self.teams:
                continue
            s_, r_, p_ = team_ctx.get(p.team, (0, 0, 0))
            # fewer sacks allowed is better, so this one inverts
            ctx = (25.0 * (1.0 - (s_ - lo_s) / max(1e-9, hi_s - lo_s))
                   + 18.0 * (r_ - lo_r) / max(1e-9, hi_r - lo_r)
                   + 12.0 * (p_ - lo_p) / max(1e-9, hi_p - lo_p)
                   + 15.0 * self.teams[p.team].win_pct)
            s = own + ctx
            if s > best:
                best, who = s, p
        return who

    def all_pro(self):
        """
        First and second team: the best and second best at each spot. No rule
        to fit here - it is structurally a position ranking.
        """
        by_pos = {}
        for p, line in self.players():
            if p.pos in ('K', 'P'):
                # Generic offensive production is zero for kickers/punters;
                # it made honors (and their dev rewards) follow insertion order.
                import dev_evaluation as DE
                assessment = DE.assessment(p, line)
                if assessment is None or not assessment.get('credible', False):
                    continue
                sc = assessment['score']
            elif p.pos in OL_POS:
                sc = self.line_score(p, line)
                if sc is None:
                    continue
            elif p.pos in PASS_RUSH_POS + COVERAGE_POS:
                sc = self.def_score(p, line)
            elif p.pos == 'QB':
                sc = self.passer_score(line)
            else:
                sc = self.skill_score(line)
            by_pos.setdefault(p.pos, []).append((sc, p))
        first, second = [], []
        for pos, n in ALL_PRO_SLOTS.items():
            grp = sorted(by_pos.get(pos, []), key=lambda x: -x[0])
            first += [p for _s, p in grp[:n]]
            second += [p for _s, p in grp[n:2 * n]]
        return first, second


def championship_game_mvp(league, post, season=None):
    """
    One game, not one season - so this is the only award that reads the
    per-game book rather than the season totals.
    """
    sb = [g for g in post.games if g[0] == 'SB']
    if not sb:
        return None
    _r, _c, home, away, _hp, _ap = sb[0]
    year = season or league.year
    key = next((k for k in (f'{year}-22-{home}-{away}', f'{year}-22-{away}-{home}')
                if k in league.game_stats), None)
    if key is None:
        return None
    winner = post.champion
    best, who = -1e9, None
    for pid, line in league.game_stats[key].items():
        p = league.player(pid)
        if p is None:
            continue
        s = (_g(line, 'pass_yds') * 0.25 + _g(line, 'pass_td') * 12
             - _g(line, 'ints') * 10 + _g(line, 'rush_yds') * 0.5
             + _g(line, 'rec_yds') * 0.5
             + (_g(line, 'rush_td') + _g(line, 'rec_td')) * 14
             + _g(line, 'sacks') * 10 + _g(line, 'int_def') * 16
             + _g(line, 'tackles') * 1.5)
        # it is nearly always someone from the winning side
        if p.team == winner:
            s *= 1.35
        if s > best:
            best, who = s, p
    return who


def vote(league, post=None, season=None):
    """Every award for one season. Returns {award: pid or team}."""
    b = Ballot(league, season)
    year = season or league.year
    first, second = b.all_pro()
    out = {
        'mvp': b.mvp(), 'opoy': b.opoy(), 'dpoy': b.dpoy(),
        'oroy': b.oroy(), 'droy': b.droy(),
        'protector': b.protector(),
        'coty': b.coty(),                       # a team, not a player
        'all_pro_1': first, 'all_pro_2': second,
    }
    if post is not None:
        out['sb_mvp'] = championship_game_mvp(league, post, year)
    league.awards[year] = {
        k: ([p.pid for p in v] if isinstance(v, list)
            else (v.pid if hasattr(v, 'pid') else v))
        for k, v in out.items() if v}
    return out


if __name__ == '__main__':
    import league as LG, season as SN, postseason as PS
    rng = np.random.default_rng(2026)
    L = LG.build_league(rng=rng)
    r = SN.run_season(L, rng)
    post, order, fired = PS.close_season(L, r, rng)
    res = vote(L, post)
    for k in ('mvp', 'opoy', 'dpoy', 'oroy', 'droy', 'protector', 'sb_mvp'):
        v = res.get(k)
        if v is None:
            print(f'{k:10s} -'); continue
        line = L.stats.get(L.year, {}).get(v.pid, {})
        print(f'{k:10s} {v.name:22s} {v.pos:5s} {v.team:4s} '
              f'({L.teams[v.team].record[0]}-{L.teams[v.team].record[1]})')
    print(f'{"coty":10s} {res["coty"]}')
    print('\nAll-Pro 1st team:')
    for p in res['all_pro_1']:
        print(f'   {p.pos:5s} {p.name:24s} {p.team}')


def announce_championship(league, post):
    """Publish the final and its MVP once, after the game book is recorded."""
    if post is None or not post.champion:
        return None
    year = int(getattr(post, 'year', None) or league.year)
    if year != int(league.year):
        # A retained bracket is historical after rollover. Loading it must not
        # create current-year metadata, repay honors or announce an old final.
        return league.player((league.awards.get(year) or {}).get('sb_mvp'))
    history = league.__dict__.setdefault('history', {}).setdefault(str(year), {})
    if history.get('championship_announced'):
        return league.player((league.awards.get(year) or {}).get('sb_mvp'))
    winner = championship_game_mvp(league, post, year)
    if winner is None:
        return None  # Missing historical game evidence is not an award.
    import xp as XP, morale as MO, inbox as IB
    ballot = league.awards.setdefault(year, {})
    already_paid = 'sb_mvp' in (getattr(league, 'awards_paid', {}) or {}).get(str(year), [])
    ballot['sb_mvp'] = winner.pid
    XP.pay_awards(league, {'sb_mvp': winner}, year=year)
    if not already_paid:
        mood = MO.ensure(winner)
        if mood is not None: mood.apply('major_award')
    game = next(g for g in post.games if g[0] == 'SB')
    _, _, home, away, hp, ap = game
    loser = away if post.champion == home else home
    from views import CLUB_NAME
    name = lambda abbr: CLUB_NAME.get(abbr, abbr)
    IB.post(league, 'league', f"{name(post.champion)} win the Championship Game",
            f"{name(post.champion)} beat {name(loser)} {max(hp, ap)}–{min(hp, ap)}.\n\nChampionship Game MVP: {IB.player_name(winner)} ({winner.pos}).",
            sender='league', payload=dict(link='league:awards'))
    history['championship_announced'] = True
    return winner
