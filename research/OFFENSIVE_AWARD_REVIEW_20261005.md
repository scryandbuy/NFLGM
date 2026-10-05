# Offensive award production review — 2026-10-05

Base: `ff33f07`. Scope: `awards.py`, focused tests, and this evidence. No game simulation, roster decision, or saved ballot is changed by this code until a new ballot is cast.

## Observed implementation

- `passer_score` ignored rushing yards and receiving production. Rushing touchdowns counted 1.8 versus 4.2 for passing touchdowns.
- OPOY/OROY selected the larger of a player's scrimmage score and a scaled passing score. They therefore discarded one side of a dual-threat season. The passing conversion differed between veterans (11) and rookies (9).
- Skill production did not charge recorded lost fumbles. The canonical and legacy loss keys can coexist in the same book.
- The module header claimed statistical fitting and a positional rotation without an accompanying fit or dataset. It also said EPA did not exist, although current game books record it.
- This review did not inspect an end-of-season saved league. There is no new observed league-wide winner distribution.

## Football rationale and counterarguments

A runner's actual yardage and scores matter whether his position label is QB or HB. A quarterback who passes and runs should receive credit for both in an offensive-production award. A possession lost should reduce his case, while a recovered fumble should not be treated as a turnover. Rookie status should determine the field rather than change the relative value of the same performance.

Passing yards represent shared work with receivers and blockers, and their typical totals are much larger than individual rushing/receiving totals. OPOY/OROY now combine existing scrimmage production with 40% of adjusted passing yards (passing yards + 20 per passing touchdown - 45 per interception). The 40% conversion is an explicit design judgment. It is not a measured responsibility share or a prescribed proportion of winners. MVP/All-Pro retain the existing passing-efficiency emphasis, with added rushing/receiving yards and the same touchdown weight across the quarterback's scoring roles.

Counterarguments: a counting-stat award score can favor volume over efficiency; catch bonuses can reward short passing; and shared credit is not directly measurable from a box score. Voters can reasonably prefer record, play difficulty, opportunity, or efficiency to raw production. These changes do not claim to reconstruct those judgments. GM personalities, roster retention, displacement, contracts, age, development potential, and trade alternatives are not inputs to award voting and are untouched.

The adjustment uses existing lost-fumble keys once, with the development production model's 25-point scrimmage penalty. Historical books missing that evidence keep the previous zero-loss fallback; no unseen fumbles or sack yardage are inferred.

## Controlled player-level evidence

`offensive_award_comparisons_20261005.json` contains complete synthetic player lines and before/after OPOY scores, evaluated against the base commit and this change.

| Controlled field | Before winner | New winner | New leading comparison |
| --- | --- | --- | --- |
| Exceptional pocket passer, good back/receiver | QB | QB | QB 2486; HB 2017.5; WR 1990 |
| Add exceptional receiver | QB | WR | WR 2585; QB 2486 |
| Add exceptional all-purpose back | HB | HB | HB 3000; WR 2585; QB 2486 |
| Dual-threat QB and exceptional receiver | WR | QB | QB 2742; WR 2585 |
| Same QB with modest rushing | WR | WR | WR 2585; QB 1762 |

These are controlled examples, not evidence that their ordering is uniquely correct. The close exceptional receiver/passer result is particularly sensitive to the conversion weight.

Focused test run: 44 passing tests across `test_offensive_award_production`, `test_award_evidence`, `test_blocking_awards`, and `test_defensive_back_award_rush`. Coverage includes QB/HB/WR winners, dual-threat action and restraint, turnovers, recovered versus lost fumbles, canonical/legacy alias parity, the previous 200-attempt OPOY cliff, rookie eligibility, absence of record/rating/order boosts in OPOY, and quarterback MVP/All-Pro rushing comparisons. Existing award and defensive/blocking tests passed. An existing unclosed-file ResourceWarning in `draft_class.py` was emitted.

## Research and remaining uncertainty

The [Pro Football Reference glossary](https://www.pro-football-reference.com/about/glossary.htm) documents the 20-yard touchdown and 45-yard interception adjustments. This patch uses its adjusted-yard numerator, not ANY/A: individual sack-yard loss is not recorded in the game's current player book.

[NFL.com's Allen MVP report](https://www.nfl.com/news/bills-qb-josh-allen-wins-2024-ap-nfl-most-valuable-player-award) credits all three scoring roles. [Barkley's OPOY announcement](https://www.nfl.com/news/eagles-rb-saquon-barkley-named-2024-ap-nfl-offensive-player-of-the-year) and [Thomas's OPOY announcement](https://www.nfl.com/news/saints-wr-michael-thomas-named-2019-nfl-opoy-0ap3000001100165) support keeping backs and receivers competitive without forcing a rotation.

Historical ballot replication is not established. For example, using 2024 headline production, the new score still prefers Jackson to actual OPOY winner Barkley. That is a calibration uncertainty, not a reason to add a player exception. The MVP non-QB 2,000-rushing-yard eligibility rule and the top-ten team-record gate remain existing limitations; they are not solved by correcting QB ground credit. No multiseason simulation or browser rebuild was performed here. Parent integration owns combined verification and browser packaging.
