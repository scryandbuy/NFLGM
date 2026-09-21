"""
THE SEASON.

This is the seam. The game engine could play one game between two roster
dicts; the League held 32 real teams and the real 272-game schedule; and the
two had never met. Everything downstream - firing, draft order, free agency,
progression, awards - reads a season's results, so none of it could be built
until a season produced them.

THREE THINGS THIS HAS TO GET RIGHT:

1. HEALTH CARRIES. A TeamState is created once per season and reused every
   week, so condition, jadedness and injuries persist. Building a fresh one
   per game would reset every injury at kickoff and the injury system would
   quietly do nothing across a season.

2. THE FIELD REFLECTS THE ROSTER. Units are rebuilt from the live roster each
   week, so a released or injured man actually disappears and his backup
   actually plays. A roster frozen at load would make every transaction
   cosmetic.

3. STATS LAND TWICE. On the player's own career line and in the league's book,
   by decision - the player so his history travels with him through trades and
   retirement, the league so leaderboards and awards can be computed without
   walking 2,114 players.
"""
import numpy as np

import game as G
import plays as P
import schemes as S
import rosters as R
import standings_and_seeding as SS

WEEKS = 18                      # 17 games, one bye apiece


def _deps():
    """The scheme-layer callers the drive loop takes."""
    co = lambda d, di, sd, ytg, r: S.call_offense(d, di, sd, ytg, r)
    cd = lambda oc, d, di, r, ytg=50: S.call_defense(oc, d, di, r,
                                                     yards_to_endzone=ytg)
    return co, cd


def make_coach(gm):
    """
    The coach ratings the drive loop reads. GM and head coach are the same
    actor by decision, so these come off the GM rather than a second person.
    The adjustment engine's hooks are wired here; play styles and scheme
    identity are still tabled.
    """
    if gm is None:
        return dict(adjust_skill=.5, adjust_willingness=.5, man_rate=.35,
                    blitz_rate=.133, travel_willingness=.5, off_script_skill=.5)
    return dict(
        adjust_skill=float(np.clip(0.35 + 0.5 * gm.board_trust, .1, .95)),
        adjust_willingness=float(np.clip(gm.aggression, .1, .95)),
        man_rate=0.35, blitz_rate=0.133,
        travel_willingness=float(np.clip(gm.aggression, .05, .95)),
        off_script_skill=float(np.clip(gm.patience, .1, .9)))


class SeasonRunner:
    """
    Runs one regular season on a live League.

    Owns the per-team TeamState for the whole year, which is the reason this
    is a class and not a function: health has to survive between weeks.
    """

    def __init__(self, league, rng=None):
        self.L = league
        self.rng = rng or np.random.default_rng()
        self.co, self.cd = _deps()
        self.states = {}
        self.books = {}
        for abbr, t in league.teams.items():
            coach = make_coach(t.gm)
            self.states[abbr] = G.TeamState(self._units(abbr), coach=coach,
                                            scheme=t.scheme)
        self.week = 0

    # ---- the field ------------------------------------------------------
    def _units(self, abbr):
        """
        Rebuild the roster dicts the engine wants from the LIVE roster, so a
        release or an injury shows up on the field immediately instead of
        being frozen at load.
        """
        t = self.L.teams[abbr]
        rows = [dict(p.ratings, pid=p.pid, pos=p.pos)
                for p in t.active() if p.out_until is None]
        return R.build_roster_rows(rows, t.scheme)

    def refresh(self, abbr):
        self.states[abbr].roster = self._units(abbr)
        return self.states[abbr].roster

    # ---- one game -------------------------------------------------------
    def play(self, home, away, week, playoffs=False):
        hr, ar = self.refresh(home), self.refresh(away)
        if hr is None or ar is None:          # a roster too thin to field
            return None
        book = G.StatBook()
        res = G.play_game(hr, ar, self.rng, P.resolve_play, self.co, self.cd,
                          P.rate, home_state=self.states[home],
                          away_state=self.states[away], week=week, book=book,
                          playoffs=playoffs)

        # ---- record ------------------------------------------------------
        H, A = self.L.teams[home], self.L.teams[away]
        if playoffs:
            pass                      # postseason does not touch the record
        elif res['home'] > res['away']:
            H.record[0] += 1; A.record[1] += 1
        elif res['away'] > res['home']:
            A.record[0] += 1; H.record[1] += 1
        else:
            H.record[2] += 1; A.record[2] += 1

        for pid, line in book.p.items():
            self.L.record_stats(self.L.year, pid, line)

        # Injuries come off the RESULT, not off TeamState. play_game calls
        # end_game() on both states before returning, which clears
        # state.injuries - so reading them there always found an empty list
        # and every injury in the league silently vanished.
        for inj in res['injuries']:
            p = self.L.player(inj['player'])
            if p is None: continue
            weeks = int(inj['weeks_out'])
            p.out_until = week + weeks
            p.injury_history.append(dict(year=self.L.year, week=week,
                                         weeks_out=weeks, kind=inj['kind'],
                                         season_ending=inj['season_ending']))
            self.L.log('injury', pid=p.pid, team=p.team, weeks=weeks,
                       injury=inj['kind'])
        return res

    # ---- one week -------------------------------------------------------
    def play_week(self, week):
        """Play every scheduled game in this week and write the scores back."""
        played = []
        for i, (wk, away, home, ap, hp) in enumerate(self.L.schedule):
            if wk != week or hp is not None:
                continue
            res = self.play(home, away, week)
            if res is None:
                continue
            self.L.schedule[i] = (wk, away, home, res['away'], res['home'])
            played.append((home, away, res['home'], res['away']))

        # anyone whose injury has expired is available again
        for p in self.L.players.values():
            if p.out_until is not None and p.out_until <= week:
                p.out_until = None

        self.week = week
        self.L.week = week
        return played

    def run(self, weeks=WEEKS, verbose=False):
        self.L.set_phase('regular')
        for wk in range(1, weeks + 1):
            got = self.play_week(wk)
            if verbose:
                print(f'  week {wk:2d}: {len(got)} games')
        self.finish()
        return self.standings()

    # ---- standings ------------------------------------------------------
    def completed(self):
        """(home, away, home_pts, away_pts) for every finished game."""
        return [(h, a, hp, ap) for _wk, a, h, ap, hp in self.L.schedule
                if hp is not None]

    def season_state(self):
        """The tiebreaker engine, fed from live results instead of history."""
        div = {a: t.division for a, t in self.L.teams.items()}
        conf = {a: t.conf for a, t in self.L.teams.items()}
        return SS.Season.live(div, conf, self.completed(), self.L.year)

    def standings(self):
        S_ = self.season_state()
        ranks = SS.division_ranks(S_)
        out = {}
        for abbr, t in self.L.teams.items():
            w, l, tie = t.record
            out[abbr] = dict(w=w, l=l, t=tie, pct=round(S_.wpct(abbr), 3),
                             div=t.division, div_rank=ranks.get(abbr),
                             pf=S_.pf[abbr], pa=S_.pa[abbr])
        return out

    def seeds(self):
        S_ = self.season_state()
        return {c: SS.seed_conference(S_, c) for c in sorted(set(
            t.conf for t in self.L.teams.values()))}

    def finish(self):
        """Close the year out: records into history, health rolled forward."""
        S_ = self.season_state()
        seeds = self.seeds()
        made = {t for conf in seeds.values() for t in conf}
        self.L.standings_history[self.L.year] = {
            a: dict(record=list(t.record), pct=round(S_.wpct(a), 3),
                    made_playoffs=a in made)
            for a, t in self.L.teams.items()}
        for abbr, t in self.L.teams.items():
            t.history.append(dict(year=self.L.year, win_pct=t.win_pct,
                                  made_playoffs=abbr in made,
                                  record=list(t.record)))


def run_season(league, rng=None, weeks=WEEKS, verbose=False):
    r = SeasonRunner(league, rng)
    r.run(weeks, verbose)
    return r


if __name__ == '__main__':
    import league as LG, time
    rng = np.random.default_rng(2026)
    L = LG.build_league(rng=rng)
    t0 = time.time()
    r = run_season(L, rng, verbose=True)
    print('\nran in %.0fs' % (time.time() - t0))
    st = r.standings()
    for conf, seeds in r.seeds().items():
        print(f'\n{conf} seeds:')
        for i, t in enumerate(seeds, 1):
            s = st[t]
            rec = f'{s["w"]}-{s["l"]}' + (f'-{s["t"]}' if s["t"] else '')
            print(f'  {i}. {t:<4} {rec:<7} {s["div"]:<10}'
                  f' pf {s["pf"]:4d} pa {s["pa"]:4d}')
    print('\npassing leaders:', L.leaders(L.year, 'pass_yds', 3))
    print('rushing leaders:', L.leaders(L.year, 'rush_yds', 3))
    print('injuries logged:',
          sum(1 for x in L.transactions if x['kind'] == 'injury'))
