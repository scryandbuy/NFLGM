"""Regular-season honors from recorded production and award-specific context.

These are transparent game-design scores, not a fitted model of AP ballots.
MVP emphasizes passing responsibility, efficiency and team record. OPOY and OROY compare
combined offensive production on one scale; they do not target a position mix.
Rookie eligibility limits the OROY/DROY field without changing how production
is scored. Defensive and blocking honors use their respective recorded roles.

Ballots use league.stats, never playoff totals. Championship Game MVP is the
exception and reads one game's book. EPA exists in newer books, but these
scores use counting statistics available in historical saves as well.
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
        # Coach of the Year retains its record-rank context.
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
        Quarterback award score: passing efficiency plus ground production.
        The rushing/receiving terms credit yards and scores actually gained;
        a touchdown has the same weight whether passed, run or caught. This
        is an award heuristic, not EPA or a reconstruction of real voting.
        """
        att = _g(line, 'pass_att')
        if att < 200:
            return 0.0
        ypa = _g(line, 'pass_yds') / att
        td, ints = _g(line, 'pass_td'), _g(line, 'ints')
        comp = _g(line, 'pass_cmp') / att
        return (4.2 * td - 4.0 * ints + 22.0 * (ypa - 6.5)
                + 60.0 * (comp - 0.63)
                + 0.04 * (_g(line, 'rush_yds') + _g(line, 'rec_yds'))
                + 4.2 * (_g(line, 'rush_td') + _g(line, 'rec_td'))
                - 4.0 * self.lost_fumbles(line))

    @staticmethod
    def lost_fumbles(line):
        """Canonical and legacy keys describe the same losses; never add them."""
        return max(_g(line, 'fumbles_lost'), _g(line, 'fum_lost'))

    def skill_score(self, line):
        """Scrimmage production, including the cost of losing possession."""
        # yards and touchdowns carry it; receptions count a little. At 4 a
        # catch a 115-catch receiver out-scored a 1,400-yard back every year
        return (_g(line, 'rush_yds') + _g(line, 'rec_yds')
                + 20.0 * (_g(line, 'rush_td') + _g(line, 'rec_td'))
                + 2.5 * _g(line, 'rec') - 25.0 * self.lost_fumbles(line))

    @staticmethod
    def adjusted_passing_yards(line):
        return (_g(line, 'pass_yds') + 20.0 * _g(line, 'pass_td')
                - 45.0 * _g(line, 'ints'))

    def offensive_score(self, line):
        """One OPOY/OROY scale, combining every recorded offensive role.

        The passing component uses adjusted passing yards (20 per TD, -45
        per INT), discounted to 40% because passing production is shared
        with receivers. That conversion is a game-design judgment, not a
        measured responsibility share or positional quota. Scrimmage yards
        have identical value for a QB, back or receiver. A lost fumble is
        charged once in skill_score, including a quarterback's strip-sack.
        """
        return self.skill_score(line) + 0.4 * self.adjusted_passing_yards(line)

    def mvp_score(self, p, line):
        """Comparable offensive value with bounded efficiency/record context.

        MVP gives more credit to directing the passing game than OPOY does:
        60% of adjusted passing yards versus 40%. Efficient passing adds up
        to 15%; inefficient passing can subtract up to 15%. This affects the
        passing component only, so a trick-pass rate cannot multiply a back's
        entire season. No passing-attempt or rushing-yard eligibility cliff.

        Team success scales the complete case by 0.85 to 1.15, a preference
        that cannot rule out an exceptional player on a weaker team. An
        unattached player's unavailable team record uses neutral context.
        These are explicit design weights, not estimates of real AP voting.
        """
        att = _g(line, 'pass_att')
        efficiency = (max(0.85, min(1.15,
                      1.0 + 0.05 * (_g(line, 'pass_yds') / att - 7.0)))
                      if att > 0 else 1.0)
        passing = 0.6 * self.adjusted_passing_yards(line)
        # A poor efficiency rate must not soften negative passing production.
        passing *= efficiency if passing >= 0 else max(1.0, efficiency)
        production = self.skill_score(line) + passing
        club = self.teams.get(p.team)
        win_pct = max(0.0, min(1.0, club.win_pct)) if club is not None else 0.5
        return production * (0.85 + 0.30 * win_pct)

    def rush_score(self, line):
        """Front-seven production, including their recorded plays in coverage."""
        # Use the existing role-development scale for ball production (3 PD,
        # 8 INT), retaining the award's established rush/tackle/FF weights.
        return (3.0 * _g(line, 'sacks') + 1.0 * _g(line, 'pressures')
                + 0.6 * _g(line, 'tackles') + 4.0 * _g(line, 'ff')
                + 3.0 * _g(line, 'pass_def') + 8.0 * _g(line, 'int_def'))

    def cover_score(self, line):
        """The other axis. Gilmore 2019 led the league in INT and PD."""
        # A slot/safety blitz can create the same recorded rush production
        # as a front-seven rush. Preserve that contribution, including half
        # sacks, without awarding anything for an unproductive assignment.
        return (8.0 * _g(line, 'int_def') + 0.5 * _g(line, 'tackles')
                + 3.0 * _g(line, 'ff') + 3.0 * _g(line, 'pass_def')
                + 3.0 * _g(line, 'sacks') + _g(line, 'pressures'))

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
        """Offensive value with team context, without positional/record gates."""
        best, who = 0.0, None
        for p, line in self.players():
            s = self.mvp_score(p, line)
            if s > best:
                best, who = s, p
        return who

    def opoy(self):
        """
        Combined offensive production, independent of team record.
        No position is scheduled or guaranteed a share of winners.
        """
        best, who = -1e9, None
        for p, line in self.players():
            s = self.offensive_score(line)
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
            s = self.offensive_score(line)
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
