# NFL GM SIM — COMPLETE HANDOFF

Written at the end of a long build session. 62 commits, 56 Python modules.
Everything below is either verified by running it or explicitly flagged as
unverified. Where a number is quoted, it was measured.

---

## 1. WHAT THIS IS

A solo-play NFL GM franchise simulator. Python engine running in the browser
via Pyodide on GitHub Pages. No server. Calibrated against real 2026 rosters
and real NFL data throughout.

**Stack decision:** the TypeScript port was abandoned. Pyodide runs the Python
engine at 0.216s/game against 0.106s native — a 2x penalty, 59s for a
272-game season in the browser, cached after a 12.6MB first load. Python is
the product. Shelved TS files at `shelved/typescript-port/`.

---

## 2. THE CALENDAR — WHAT RUNS TODAY

`franchise.py` runs a complete year end to end. A 2026 season produces:
champion, first pick, 3-6 front offices changed, ~96 retirements, ~845
contracts expired, ~62 cut, ~27 restructured, 19 tagged, 64 tendered, ~110
signed in free agency, ~57 offer sheets, cut-down to 53, zero clubs over the
cap, rosters at a mean of 50.

    1  REGULAR SEASON      272 real games, real standings, full tiebreakers
    2  PLAYOFFS            wild card, divisional with reseeding, SB
    3  AWARDS              10, each rule fitted to 15 years of real winners
    4  DRAFT ORDER         set from the bracket, all 32 slots
    5  FIRINGS             pressure model, no quota
    6  RETIREMENTS         per-player hazard, measured
    7  REGRESSION          real delta-method aging curves
    8  ROLL THE YEAR       cap projects forward, contracts tick down
    9  CAP COMPLIANCE      cuts and simple restructures
   10  RE-SIGN PHASE       one tag, tenders, exclusive rights
   11  FREE AGENCY         three phases, bids, inbox, offer sheets
   12  CUT-DOWN TO 53      roster_construction wired
   13  THE DRAFT           **NOT BUILT** — the biggest gap
   14  TRAINING CAMP       **NOT BUILT**

---

## 3. THE PLAY ENGINE

### Calibration register (`calibrate.py`)
34 targets measured against real 2026 rosters. **Currently 19/34.** It was
25/34 before the play-calling rework and has fallen as each layer landed —
see §9, this is the single most important open item.

**The register is a bench test, not a league health check.** It runs on a
fresh 2026 league. Once a franchise is a few years deep it cannot distinguish
a broken engine from an evolved league, which is correct and intended.

**Reproducibility:** the engine WAS non-deterministic — `run_drive` rolled a
fresh unseeded generator each drive, so the same seed produced a different
season and the register swung 4 rows between identical runs. Fixed. Two
identical runs now produce identical output. **Any register comparison from
before that fix is unreliable, including several reported during the session.**

Across seeds the count varies ~3 rows, so only metrics off on EVERY seed are
real faults.

### What was fixed in the engine this session
- **Red zone**: `in_space=True` on every catch, so yards after contact never
  compressed near the goal. Real YAC falls 5.64 → 2.68 → 0.94 approaching the
  end zone. Drives reaching the 20 went 41.3% → 36.6% (real 35.5), scoring
  once there 76.4% → 70.4% (real 61.0).
- **The screen game did not exist.** Air yards clamped at zero. Real clubs
  throw 18.4% of attempts behind the line, completing 78.4% for 9.13 YAC.
- **The deep ball barely existed.** Blending depth base with the read modifier
  dragged deep throws to 13-16 air yards. 0.5% of completions travelled 20+
  against a real 6.3%.
- **There was no halftime.** The game ran as one continuous 3600 seconds, so
  only ONE drive a game was killed by a clock. End-of-half drives 4.0% → 7.9%
  (real 7.1).
- **Backed up inside your own 10**, real clubs pass 52.2% not 57.6% and take
  sacks at 3.9% not 7.2%. Neither existed; safeties ran 1.4% of drives against
  a real 0.28%. Now 0.80%.
- **Lineman reps**: `resolve_protection` paired rusher *i* with blocker *i*,
  so against a four-man rush the RIGHT TACKLE never got a pass-block rep.
  Lane Johnson: 1,076 snaps, 67 reps, zero run-block reps. 205 of 365 linemen
  had none.
- **Passes defended** were never recorded at all.

### Win probability (`decisions.py`, `wp_model.json`)
Logistic, 83,408 plays from 570 real games, validated by holding out WHOLE
GAMES. 75.1% accuracy, Brier 0.160, calibrated within 2 points at every
decile. Key transform: score over the SQUARE ROOT of time.

Drives three decisions:
- **Fourth down.** Replayed against every real 4th down, the model says clubs
  should go 35% where they actually go 20% — 0.58x, against Baldwin's
  published "about half as often". That gap IS the behaviour and it is where
  the coach dial lives. Aggression is a THRESHOLD, not a multiplier (scaling
  an edge cannot change its sign). The bar shrinks as win probability
  compresses at the extremes.
- **Two-point try.** 0.957 points vs 0.950 — an active choice every time.
  Information value for taking a needed try EARLY, gated to late game.
  Produces 12.8% against a real 10.2% with the right quarter profile.
- **Late-game tempo.** Measured pass rate by score and clock. Nearly binary in
  the last four minutes: 90% throwing down 9-16, 13% running it out up 9-16.

**Timeouts**: 3 a half each, reset at halftime. The defence burns them when
behind, the offence when driving. Nobody spends one in the first quarter.

### Offensive play calling (built this session)
Four layers, mirroring the defence:
1. **Identity** (`identity.py`) — read from the roster: run blocking, pass
   blocking, QB, backs, tight ends, receivers. Pass rate now runs 39% at Las
   Vegas to 80% at Jacksonville, from rosters alone. League share still 57.8.
2. **Situational personnel** — goal line pulls heavy, two-minute pulls light,
   protecting a lead brings tight ends back. Identity survives it.
3. **Formation** (`formations.py`) — 14 formations. **A package is who is on
   the field, a formation is where they stand.** The X receiver aligned LEFT
   on 600 of 600 snaps; now 443/357. Filling is BY FIT, so a tight end takes
   the X spot on 86 of 800 snaps.
4. **Play call** (`playcall.py`) — job from the situation, play from the
   personnel. Identity play per club. San Francisco runs outside zone 48%,
   Cincinnati counter 33%.
5. **Audible** — he MODIFIES, never re-calls. Reads the look they are SHOWING,
   so a disguised coverage checks him into something worse: 21% of audibles
   are made off a lie. Latitude is a property of the MAN — 0.00 to 0.40.

### Defensive play calling (built this session)
- **Coverage is what is left after the rush.** It used to be assigned from the
  whole depth chart regardless, so a linebacker could blitz and cover on the
  same snap. Safeties went 19.0% → 24.2% of coverage snaps (real 25).
- **Coverage is a call with a JOB, not a boolean** (`coverage_call.py`). 11
  calls with a deep count and a per-side underneath principle — 2-man under,
  mable, cover 6, fire zone are all sayable now. Job from the situation, call
  from the PERSONNEL: swap a secondary for replacement-level men and man-under
  falls 64% → 46%, collapsing into fire zone.
- **The defence remembers** what has been working, decaying, reset at the
  whistle.
- Man-under lands at 33% against a real 35% as an OUTCOME.

---

## 4. THE OFFSEASON

### Retirement (`retirement.py`)
Derived from 15 seasons of real careers, 2025 excluded as censored.
**The obvious approach was wrong**: `aging_curves.json` carried a "retention"
curve that is an EXIT rate, not a retirement rate — it would have retired
35-50% a year.

**Two deliberate departures from the data, by decision:** snaps do NOT count
(they predict getting CUT, a different event here), and almost nobody under 27
retires. 97 retirements a year, mean age 31.3. Year one retires Folk at 42,
Campbell at 40, Von Miller at 38.

### Regression (`regression.py`)
Real delta-method aging curves that had never been called. Two traps:
the curve measures PRODUCTION not ability (damping is the correction), and a
binary physical/mental split does not survive contact with real positions —
every rating carries a physical WEIGHT 0-1. No decline through 25, -0.5 at 28,
-1.1 at 30, -1.6 at 33. A QB stays flat, which is what the curve says.

### Cap and contracts (`contracts.py`, `cap_engine.py`, `min_salary.py`)
- Day-one cap positions match Over the Cap to $0.001M.
- **Simple restructures only** — no void years, no maximum restructures.
- **No GM stat gates it.** Need drives it; dead money is the consequence.
- Order matters: rework the deals of men worth keeping, THEN release the ones
  you can replace. Cutting first released an 88-overall receiver.
- **Compliance at zero is not enough** — Baltimore finished with 20 players,
  $1.2M space and a $1.29M minimum. `enforce` takes a roster target.
- **Guaranteed money is CUT from the game.** Dead money comes from signing
  bonus proration, untouched.

### Re-sign phase and tags (`tags.py`)
One franchise tag, priced non-exclusive. Three-tag escalator 120%/144%. RFA
tenders are RIGHT OF FIRST REFUSAL ONLY — no compensation tiers, by decision.
A tender keeps a player BIDDABLE; the club gets the last word, not exclusivity.
Five-day match window (the real rule; longer than the three discussed).

**Two bugs that made the market impossible:** nothing ever decremented a
contract (27 men reached free agency league-wide against a real 400-600), and
the cap never grew (contracts are backloaded, so clubs finished 90M over).

### Free agency (`market.py`)
Three phases where PRICE falls between them. One editable bid per player,
resolved at the advance. Five-bar meter reads UTILITY, not money, and does not
always win. Inbox: match requests and offer sheets. Contender discount small
and occasional. Pool stays open, reopens at camp.

**The bug that mattered:** the comp set fell back to the WHOLE LEAGUE when a
position group had under 25 men — there are only 32 kickers, so a kicker was
priced against quarterbacks and signed for $31.9M.

### Valuation (`valuation.py`)
Recovered mid-session — it was never in the tarball, only its output survived.
Comps weighted on position, overall, age AND production. Outliers widen on AGE
but NEVER on rating (widening rating took Myles Garrett from $44.8M to $24M).
Comp window is ROLLED between the agent's two years and the club's five.
Linemen have real production now (PBWR/RBWR). Comps come from your own league.
Median error $0.78M against real 2026 contracts.

**Contracts keep `orig_years`** — the comp pool read REMAINING years, so a man
three years into a five-year deal taught the market that long deals do not
exist, and nothing longer than two years could ever be signed.

### Spending power
**Every AI decision prices against spending power, not cap space.** Space minus
the floor cost of the bodies still owed. A club with $20M and twenty holes
cannot spend $15M on anybody. Plus forward obligation: a multi-year deal is
paid from the same room that re-signs your own expiring men, so it only clears
if the man beats whoever walks. A one-year rental always passes.

### Cut-down (`cutdown.py`)
`roster_construction` finally called. Produces a real shape: 2 QB, 3 HB, 7 WR,
4 TE, 9 OL, 11 DL, 4 LB, 10 DB, 3 specialists. **One pass cannot work** — a
club cannot sign its 52nd man until it has cut somebody, cannot know who to cut
until it has seen who it can sign, and cutting accelerates dead money. Three
passes: 45 cut, 224 signed.

### Trades (`trades.py`, `trade_engine.py`)
Grounded in 1,077 real deals: only 34% are one-for-one, 55% are players PLUS
picks, 82% of player acquisitions headline a DAY-THREE pick, package size
scales with the prize.

The builder ADDS to an offer rather than swapping. The seller is harder to move
than the buyer. Valuations differ by club via a **placeholder** perception
offset. Need is QUALITY not headcount, measured against the league's own median
starter, and accounts for WHO IS AVAILABLE (a starter on IR creates a hole).

**Not wired into the franchise calendar.**

### Injuries (`health.py`, `injury_status.py`)
**The rate was never the problem** — `TeamState.out` was never cleared between
games, so once a player was hurt he could never be hurt again, and neither
could anyone else. 0.96 per team per game; the untouched formula then gave
3.10. **Tuned DOWN to 2.65 by decision** — injuries make depth matter, not
take your players away.

Designations from the real rules: Out, Doubtful (plays 20-25%), Questionable
(50-70%, deliberately the widest). Playing hurt costs CONDITION scaled to how
hurt he actually is, which also raises re-injury risk. IR: four games minimum,
eight returns a club, two designations a player.

### Awards (`awards.py`)
Ten, each fitted to 15 years of real winners. MVP gates on a top-10 record
(every winner had one) and scores efficiency not yards (Jackson won at 22nd in
yards). Rookie awards score against the ROOKIE CLASS. Coach of the Year is
improvement gated on record. Protector is flagged as NOT data-backed — one
season of history.

**Playoff stats were being folded into season totals.** Ballots are cast before
the playoffs. Regular, postseason and per-game lines now kept apart.

---

## 5. XP AND PROGRESSION (partially built)

**Design:** progression is continuous — XP earned every game, a weekly
practice, minicamp drills, spent whenever. Regression stays in the offseason.

`xp.py` — the ledger. All 27 recorded stats, plus weekly, season, career
milestone and award tiers. Values solved backwards so positions land level: a
full season is 39k for a 4,500-yard QB, 32k for a 1,200-yard back, 28k for a
twelve-sack edge, 21k for a tackle, 21k for a corner.

**Cost is tied to regression, PARTLY.** Two terms: a position-specific part off
the real aging curve, and a flat age term — because a quarterback's curve is
flat until 36 and pricing off it alone let a 31-year-old add nearly 5 overall.
Production and LEARNING are different things.

**Measured: one overall point costs 4-6 attribute points**, depending on how
well you spend. Concentrating on the highest-weighted attribute is ~2x more
efficient than spreading.

Growth from a big season, against the budget (21-24 up to 5, 25-28 up to 3,
29+ about 1):

           22    25    28    31    34
    WR    4.9   4.3   2.6   1.8   0.7
    QB    5.2   4.3   3.2   2.5   2.0
    HB    4.2   3.7   2.3   1.4   1.1
    EDGE  3.8   3.3   1.8   1.2   1.0

**NOT BUILT:** what a skill point buys, earning wired into the game and season
loops, how the AI spends it, XP for awards feeding the dev tier.

---

## 6. DESIGN DECISIONS MADE (do not relitigate)

- Compensatory picks: DELETED
- Transition tag: DELETED. Franchise tag only, priced non-exclusive, no offer
  sheets on tagged players
- RFA tender compensation tiers: DELETED. Right of first refusal only
- Owner mandates: DELETED
- GM and head coach are ONE actor
- Guaranteed money: CUT entirely
- Void years and maximum restructures: NOT in the game
- Restructures available to EVERY GM, not gated on a stat
- FM-style CA/PA ability budget: REJECTED. Gaining one attribute never costs
  another
- Scheme-based archetype progression: REJECTED
- Awards kept: MVP, OPOY, DPOY, OROY, DROY, Coach of the Year, Protector,
  All-Pro 1st and 2nd, Super Bowl MVP. Everything else removed
- MVP/OPOY/DPOY/OROY/DROY carry a guaranteed +1 dev tier
- Career stats live on the player AND at league level
- Retirement is per-player, not a percentage
- Trades: don't force real-world percentages. Use real data for AI REASONING,
  not to hit outcome targets
- Injuries: below real is fine

---

## 7. TABLED — ENGINE

- **Drives per game 23.7 vs 21.0.** Plays per drive and first downs per drive
  are the SAME FACT — total snaps are right (124.6 vs 124.0), so it is two
  extra possession changes a game. Not yet diagnosed.
- **Blowouts of 10+ at 56.4% vs 44.7%.** Mean margin and variance are BOTH
  correct (margin sd 14.60 vs real 14.61), so the shape is wrong in a way not
  yet understood — too few games in the 1-9 band.
- **Overtime 2.0% vs 6.2%**, ties 0.92% vs 0.29% — same fact as blowouts.
- **Passes defended concentration.** League total is right (8.25/game vs 8.2)
  but the projected season leader is ~79 against a real 24. THREE attempts
  failed: coverage assignment, the rush split, and X alignment. **Next step is
  instrumentation, not another change** — log every break-up with who covered,
  who was targeted, and the call.
- Pass block win rate ~86% vs 91%; run block win rate ~65% vs 71% with NO
  per-snap variance (a lineman wins every rep or loses every rep).
- Third corner snap share ~81% vs 57% — no nickel/dime package rotation.
- Corner travel 8.5% vs a real 15-25%, and unhooked from the coverage call.
- `shell` and `coverage` are now two parallel truths that can disagree.
- Man/zone is per-side but not per-DEFENDER — no pattern-matching, no palms.

## 8. TABLED — FEATURES

- **THE DRAFT.** Scouting with fog of war, board, AI behaviour, rookie
  contracts on the slotted scale. The league loses ~97 players a year and
  gains none.
- Practice squad: 16 men, elevations, poaching
- Newgens — no player is ever created
- Progression: XP spend rules, earning wired in, AI spending
- XP and a dev-tier chance for every award
- Restructuring from a salaries screen at any time
- Kicker and punter stats — All-Pro slots sit empty
- Special teams returner depth
- GM hiring pool: 60 candidates, visible vs hidden attributes
- **Team schemes are never set.** Six exist in `SCHEME_SHIFT`,
  `position_score` applies them, no team has one. Trade valuations use a
  placeholder perception offset instead
- Coach play styles and scheme identity
- Three promise types: scheme fit, bringing in help, snap share floor
- Trades not wired into the franchise calendar
- Conditional picks (13% of real deals)
- **Future picks priced too cheaply** against marginal players — a 2029 first
  for a 74-overall linebacker
- Morale is DEAD: `morale_system` is imported only to deserialise. No player
  is ever given one
- `gm_surfaces.claim_value` fails with a KeyError — 1 of 12 functions
- OPOY picks a receiver every time, OROY a running back — blocked on the
  engine
- UI: everything is a Python API with no screens
- Morale display: own column plus per-attribute breakout

## 8a. TABLED — UI (current, as of the browser-app wiring)

The list in §8 predates the draft, practice squad, newgens, schemes, morale
and staff builds; several of its lines are done. These are the items tabled
during the page wiring, in the order they came up:

- Playoff odds as percentages on the Standings picture. Needs a season
  simulation from the current standings (an engine piece); the picture shows
  seeds and in-the-hunt instead.
- Box Score as its own page from a Schedule click-through (finished games
  open Game Day for now).
- Cap ledger as its own full page (the ledger sits inside the Cap tab).
- Identity: the five roster-philosophy archetypes (draft and develop, win-now
  trader, analytics room, scouts' gut, owner meddler) as a third row that
  sets the GM's roster traits. Only the nine on-field archetypes are on the page.
- Prospect Card (a board row opens nothing yet).
- Trade Tree link from a transaction.
- Season Reviews written by the owner (the Owner tab lists them; nothing
  writes one yet).
- Halftime Adjustments on Game Day.
- Named Saved Plans on Game Plan (needs a small engine addition).
- Personnel: an Add-to-Trade picker from a player card (Trade Block links to
  the Trades page for now).

## 9. THE ONE THING TO DO FIRST

**Finish the register refit.** It sits at 19/34, down from 25 before the
play-calling rework. Two genuine bugs were found and fixed (the intermediate
throw had nowhere to live; the concept was scored against the shell rather
than the coverage actually played). The remainder is NOT a bug:

    completions 0-9   65.1%  vs real 54.1%
    completions 10-19 12.2%  vs real 17.3%
    completions 20+    4.3%  vs real  6.3%

Throws are CALLED at roughly the right depths (66/23/11 vs 62/24/14). The
intermediate and deep ones are being defended better than they were when the
passing game was fitted, because the defence now calls coverage that fits the
situation instead of flipping a coin.

**So the completion model needs re-deriving against a defence that covers
properly.** That single curve drives completion percentage, interceptions,
sacks, yards per dropback and scoring together — move it wrong and five rows
shift at once. Do it carefully.

Until that is done the register cannot distinguish a regression from an
improvement.

---

## 10. HOW I GOT THINGS WRONG THIS SESSION

Recorded because the pattern is more useful than the individual errors.

- **Three times I reported a bug that was my own test harness.** Measuring a
  tuple's length and calling `allocate` broken. Testing coverage with 3
  receivers when the engine uses 5. Building a league with every club 0-0 so
  every team read as "retooling" and concluding the rebuild logic wasn't
  firing. **Test against what the engine actually does, inside a real game.**
- **I nearly built a feature to fix a non-problem.** Read the SD of the
  ABSOLUTE margin as the SD of the margin, concluded real games share a pace
  factor, and was about to add one. Real margin sd 14.61, ours 14.60.
- **The relative-vs-absolute trap, three times.** Identity centred on a fixed
  0.70 (every NFL roster is above it). Run schemes scored on their own scale
  (power asks for 2 attributes, zone for 3, so power always won). Coverage
  weighted by grade picked the best free safety rather than the strong safety
  whose JOB it is. **The question is never which option scores highest — it is
  which one this roster is better at than rosters generally are.**
- **I chased percentages that were outputs, not targets.** Pushed trade package
  size toward 66% multi-asset and produced two firsts for an 80-overall guard.
- **Several register comparisons before the reproducibility fix were
  meaningless** — the count swung 3-4 rows between identical runs.

**Ask before building: is this a TARGET (a number to hit, test numerically) or
AI LOGIC (decision quality, test the decisions)?**

---

## 11. FILES

All in `/home/claude/data/`. 56 modules, all importing cleanly — 13 could not
be imported at the start of the session (stale names after renames, derivation
at import time, analysis scripts running on import, a hard ortools dependency).
That was why so much was "built" and had never run.

Data: `league_seed_2026.csv` (2,114 players, 54 attrs), `rosters_2026.csv`,
`schedule_2026.csv`, `player_valuations_2026.csv`, `free_agent_pool.csv`,
`advanced_stats_by_season.csv`, `aging_curves.json`, `wp_model.json`,
`pick_values.json`, `otc_2026.py`.

Entry points: `franchise.py` (a full year), `calibrate.py` (the register),
and every engine module has a `__main__` demo.
