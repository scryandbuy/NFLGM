"""
THE FRANCHISE.

One object that runs a complete year end to end, so the whole thing can be
looked at instead of tested a piece at a time.

THE CALENDAR, and what actually exists behind each step:

    1  REGULAR SEASON      272 real games, real standings, real tiebreakers
    2  PLAYOFFS            wild card, divisional with reseeding, SB
    3  AWARDS              ten of them, each rule fitted to 15 real years
    4  DRAFT ORDER         set from the bracket, all 32 slots
    5  FIRINGS             pressure model, no quota
    6  RETIREMENTS         per-player hazard, measured
    7  REGRESSION          real delta-method aging curves
    8  ROLL THE YEAR       cap projects forward, contracts tick down
    9  CAP COMPLIANCE      cuts and simple restructures
   10  RE-SIGN PHASE       one tag, tenders, exclusive rights
   11  FREE AGENCY         three phases, bids, inbox, offer sheets
   12  DRAFT               NOT BUILT
   13  CAMP AND CUT-DOWN   NOT BUILT

Everything from 1 to 11 runs. 12 and 13 do not exist, and that is why rosters
finish a year at about 47 men instead of 53: a draft class of 224 never
arrives and nobody is ever cut to a limit. The league is playable and it is
not yet whole.

WHAT THE REPORT IS FOR. run(report=True) prints what each step did AND what it
could not do, so a gap shows up as a line rather than as a number that looks
slightly wrong three seasons later.
"""
import numpy as np

import league as LG
import season as SN
import xp as XP
import dev_roll as DR
import schedule as SCH
import trades as TRD
import draft_class as DC
import scouting as SC
import draft as DFT
import newgens as NG
import practice_squad as PSQ
import waivers as WV
import coaching_pool as CP
import position_change as PC
import extensions as EXT
import morale as MO
import almanac as AL
import spring as SP
import postseason as PS
import awards as AW
import retirement as RT
import regression as RG
import contracts as CT
import tags as TG
import market as MK
import cutdown as CD


def prune_pool(league, rng):
    """
    THE POOL EMPTIES. A man unsigned through a whole season retires or
    goes elsewhere: nearly all the old, most in their late twenties, a third
    of the young. Without this the pool held 1,985 men by year six, 1,757 of
    them unsigned for a year, and the cut-down wire had ever more bodies to
    claim (400 cut-down claims against a real ~60).
    """
    gone = 0
    for pid in list(league.free_agents):
        p = league.player(pid)
        if p is None or p.retired: continue
        if p.entry_year is not None and p.entry_year >= league.year - 1: continue   # last year's rookies get a second summer
        # the year has rolled: the season just played is league.year - 1, and a
        # man with no stat line in it, and no club now, sat out the whole year
        if pid in league.stats.get(league.year - 1, {}): continue
        pr = 0.85 if p.age >= 30 else 0.55 if p.age >= 26 else 0.35
        if rng.random() < pr:
            p.retired = True; p.retired_year = league.year; p.team = None
            league.free_agents.remove(pid); gone += 1
    if gone: league.log('pool_pruned', n=gone)
    return gone


class Franchise:
    """A league, plus the calendar that moves it."""

    def __init__(self, seed=None, user_team=None, rng=None):
        self.rng = rng or np.random.default_rng(seed)
        self.L = LG.build_league(rng=self.rng)
        self.user_team = user_team
        self.L.user_team = user_team          # the season runner reads it at the weekly spend
        self.history = []

    # ---- one year ------------------------------------------------------
    def play_year(self, report=True):
        L, rng = self.L, self.rng
        year = L.year
        log = dict(year=year)

        runner = SN.run_season(L, rng)
        log['standings'] = runner.standings()

        post, order, fired = PS.close_season(L, runner, rng)
        MO.postseason(L, post)
        CP.top_up(L, rng)                    # retirements out of the pool, new men in
        PC.offseason(L)                      # camp: four games of learning for every man mid-move
        log['champion'] = post.champion
        log['top_pick'] = order[0]
        log['fired'] = len(fired)

        votes = AW.vote(L, post)
        CP.season_prestige(L, post, coty_team=votes.get('coty'))
        AL.close_season(L, L.year, post, votes)      # the almanac: leaders, records, the coaching ledger
        log['awards'] = {k: (v.name if hasattr(v, 'name') else v)
                         for k, v in votes.items() if not isinstance(v, list)}
        # season lines, milestones and award XP land once the vote is in
        log['xp_paid'] = len(XP.close_season(L, votes))
        # and the development trait moves: the majors are a guaranteed tier,
        # the rest of the honours and the season itself shift the odds
        moved = DR.run(L, votes, rng)
        log['dev_up'] = sum(1 for m in moved if m[1] == 'up')
        log['dev_down'] = sum(1 for m in moved if m[1] == 'down')

        log['retired'] = len(RT.run(L, rng))
        log['hall'] = [p.name for p, _ in AL.hall_vote(L, L.year)]
        RG.run(L, rng)

        L.roll_year(rng)
        # NEXT YEAR'S SLATE. The real 2026 schedule was loaded once and never
        # replaced, so every later season found all 272 games already scored
        # and played none of them.
        ranks = SCH.division_ranks(L, log['standings'])
        SCH.new_season(L, ranks, rng)
        for t in L.teams.values():
            t.record = [0, 0, 0]
        log['schedule_ok'] = not SCH.validate(L)
        log['expired'] = len(L.advance_contracts())

        cuts, res = CT.run(L, rng)
        CT.enforce(L, rng)
        log['cuts'], log['restructures'] = len(cuts), len(res)
        # the offseason releases go through the wire before free agency opens
        WV.notify_user(L, WV.pending(L), 0, digest=True)
        log['waiver_claims'] = len(WV.process(L, rng, 0))

        # EXTENSIONS. A club keeps who it can before the market opens; the
        # user's expiring men are flagged in the inbox
        MO.check_resolutions(L, week=None)   # a winning season settles the man who wanted a winner
        MO.clear_free_agents(L)              # a man who walked took his grievance with him
        log['pool_pruned'] = prune_pool(L, rng)   # men nobody signed all year move on
        log['trade_requests'] = len(MO.offseason_requests(L, rng))
        MO.offseason_reset(L)                # a new season is a new season (not for the man who asked out)
        MO.offseason_contracts(L, rng)       # the drag of a cheap deal against the market
        log['extensions'] = len(EXT.ai_round(L, rng))
        EXT.notify_user(L)
        t = TG.run(L, rng)
        CT.enforce(L, rng)
        log['tagged'], log['tendered'] = len(t['tagged']), len(t['tendered'])

        signed, left = MK.run(L, rng, user_team=self.user_team)
        # THE OFFSEASON TRADE WINDOW, once the market has settled: clubs know
        # what they could not buy and shop for it
        made = TRD.run(L, rng, rounds=2,
                       exclude=(self.user_team,) if self.user_team else ())
        log['trades'] = len(made)
        # THE DRAFT. The first class is the real College Football 27 seniors
        # and juniors mapped onto a rookie scale; every class after it is
        # generated the offseason before (newgens.build) and scouted then,
        # so it sits on the scouting tab through the year before its draft.
        if getattr(L, 'next_class', None):
            L.draft_pool = L.next_class; L.next_class = []
        else:
            DC.build(L, rng, draft_year=L.year)
            SC.scout(L, rng)
        # the picks carry the SEASON year they were earned in; the year has
        # already rolled by the time the draft is held
        # THE SPRING: the combine, the Senior Bowl, pro days, the thirty
        # visits, medicals and character reads. Nothing changes a prospect;
        # every room's read of him does, differently
        log['spring'] = SP.run_spring(L, rng)
        # when the calendar sims the draft with nobody at the buttons, the
        # user's club picks off the consensus board and its needs
        drafted = DFT.run(L, rng, year=L.year - 1, user_team=self.user_team)
        log['drafted'] = len(drafted)
        # every undrafted man is in the pool; clubs bring a handful to camp
        log['udfa_camp'] = PSQ.udfa_camp(L, rng)
        # and the class for NEXT year's draft is born now
        NG.build(L, rng, draft_year=L.year + 1)
        SC.scout(L, rng)
        log['next_class'] = len(L.next_class)
        log['signed'] = len(signed)
        log['unsigned'] = len(left)
        log['offer_sheets'] = len([m for m in getattr(L, 'inbox', [])
                                   if m.get('kind') == 'offer_sheet'])

        # CUT-DOWN TO 53, which roster_construction could always do and
        # nothing ever asked it to.
        # last year's squads are released back to the pool before cut-down
        for t in L.teams.values():
            for p in list(PSQ.squad(t)):
                PSQ.release_from_squad(L, t.abbr, p.pid)
        PSQ.reset_season(L)
        cut, filled = CD.finalize(L, rng)
        # cut-down men go through the wire before the squads fill
        WV.notify_user(L, WV.pending(L), 0, digest=True)
        log['waiver_claims'] += len(WV.process(L, rng, 0))
        log['practice_squad'] = PSQ.fill_squads(L, rng)
        log['cut_to_53'] = len(cut)
        log['filled'] = filled

        rosters = np.array([len(x.active()) for x in L.teams.values()])
        space = np.array([x.cap_space for x in L.teams.values()])
        log['roster_min'] = int(rosters.min())
        log['roster_mean'] = float(rosters.mean())
        log['over_cap'] = int((space < 0).sum())
        self.history.append(log)
        if report:
            self._report(log)
        return log

    def _report(self, g):
        a = g['awards']
        print(f"\n=== {g['year']} ===")
        print(f"  champion {g['champion']}   first pick {g['top_pick']}"
              f"   {g['fired']} front offices changed")
        print(f"  MVP {a.get('mvp','-')}   OPOY {a.get('opoy','-')}"
              f"   DPOY {a.get('dpoy','-')}")
        print(f"  offseason: {g['retired']} retired, {g['expired']} contracts "
              f"expired, {g['cuts']} cut, {g['restructures']} restructured")
        print(f"  market: {g['tagged']} tagged, {g['tendered']} tendered, "
              f"{g['signed']} signed, {g['offer_sheets']} offer sheets, "
              f"{g['unsigned']} left unsigned")
        print(f"  cut-down: {g.get('cut_to_53',0)} cut, {g.get('filled',0)} signed")
        print(f"  rosters {g['roster_mean']:.0f} mean / {g['roster_min']} min"
              f"   clubs over the cap: {g['over_cap']}")
        if g['roster_mean'] < 50:
            print('    ^ NO DRAFT: 224 rookies never arrive, so the league '
                  'shrinks and clubs cannot always reach 53')

    def run(self, years=1, report=True):
        for _ in range(years):
            self.play_year(report)
        return self.history


def whats_left():
    """An honest inventory. Printed rather than remembered."""
    built = [
        ('play engine', '25/34 calibration targets, real 2026 rosters'),
        ('season', '272-game real schedule, standings, full tiebreakers'),
        ('playoffs', 'reseeding, no ties, draft order'),
        ('awards', '10, each fitted to 15 years of real winners'),
        ('firings', 'pressure model, no quota'),
        ('retirement', 'per-player hazard from 15 seasons of careers'),
        ('regression', 'real delta-method aging curves'),
        ('cap', 'real 2026 positions, dead money, carryover, rollforward'),
        ('contracts', 'cuts, simple restructures, compliance backstop'),
        ('re-sign phase', 'franchise tag with escalator, tenders'),
        ('free agency', '3 phases, bids, interest meter, inbox, offer sheets'),
        ('valuation', 'weighted comps, two-sided, own-league pool'),
        ('decisions', 'win probability model, 4th down, 2pt, late tempo'),
        ('timeouts', '3 a half, spent by the side that needs the clock'),
        ('cut-down to 53', 'roster_construction wired: minimums, group floors, '
                           'marginal slot value'),
    ]
    missing = [
        ('THE DRAFT', 'scouting with fog of war, board, AI behaviour, '
                      'rookie contracts on the slotted scale'),
        ('practice squad', '16 men, elevations, poaching - nowhere for a cut '
                           'player to land'),
        ('decisions not wired', 'decisions.py is built and game.py still uses '
                                'the old GO_RATE table'),
        ('progression', 'XP earned per game, weekly practice, minicamp'),
        ('newgens', 'no players are ever created, so the league shrinks'),
        ('trades', 'trade_engine imports now but nothing calls it'),
        ('UI', 'everything above is a python API with no screens'),
    ]
    print('BUILT AND RUNNING')
    for n, d in built:
        print(f'  {n:<18} {d}')
    print('\nNOT BUILT')
    for n, d in missing:
        print(f'  {n:<20} {d}')


if __name__ == '__main__':
    import sys
    yrs = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    f = Franchise(seed=2026)
    f.run(yrs)
    print()
    whats_left()
