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

Passing yards represent shared work with receivers and blockers, and their typical totals are much larger than individual rushing/receiving totals. OPOY/OROY now combine existing scrimmage production with 40% of adjusted passing yards (passing yards + 20 per passing touchdown - 45 per interception). The 40% conversion is an explicit design judgment. It is not a measured responsibility share or a prescribed proportion of winners. QB All-Pro retains the existing passing-efficiency emphasis, with added rushing/receiving yards and the same touchdown weight across the quarterback's scoring roles. MVP uses the common production units described below.

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

Focused test run: 54 passing tests across `test_offensive_award_production`, `test_award_evidence`, `test_blocking_awards`, and `test_defensive_back_award_rush`. Coverage includes QB/HB/WR winners, dual-threat action and restraint, turnovers, recovered versus lost fumbles, canonical/legacy alias parity, the previous 200-attempt OPOY cliff, rookie eligibility, absence of record/rating/order boosts in OPOY, and quarterback MVP/All-Pro rushing comparisons. Existing award and defensive/blocking tests passed. An existing unclosed-file ResourceWarning in `draft_class.py` was emitted.

## Research and remaining uncertainty

The [Pro Football Reference glossary](https://www.pro-football-reference.com/about/glossary.htm) documents the 20-yard touchdown and 45-yard interception adjustments. This patch uses its adjusted-yard numerator, not ANY/A: individual sack-yard loss is not recorded in the game's current player book.

[NFL.com's Allen MVP report](https://www.nfl.com/news/bills-qb-josh-allen-wins-2024-ap-nfl-most-valuable-player-award) credits all three scoring roles. [Barkley's OPOY announcement](https://www.nfl.com/news/eagles-rb-saquon-barkley-named-2024-ap-nfl-offensive-player-of-the-year) and [Thomas's OPOY announcement](https://www.nfl.com/news/saints-wr-michael-thomas-named-2019-nfl-opoy-0ap3000001100165) support keeping backs and receivers competitive without forcing a rotation.

Historical ballot replication is not established. For example, using 2024 headline production, the new score still prefers Jackson to actual OPOY winner Barkley. That is a calibration uncertainty, not a reason to add a player exception. No multiseason simulation or browser rebuild was performed here. Parent integration owns combined verification and browser packaging.


## Completed MVP comparison

The old MVP logic required a non-passing candidate to lead the league with at least 2,000 rushing yards, then gave that player a score near 1 while a credible quarterback typically scored over 100. Receiving production could never establish an MVP case. The top-ten record gate could exclude a player based on unrelated teams' records or tie ordering. These were structural exclusions, not just strong quarterback preferences.

MVP now compares total scrimmage production plus 60% of adjusted passing yards. Passing efficiency scales only the passing component between 0.85 and 1.15, centered on 7 yards per attempt; team winning percentage scales the entire case from 0.85 to 1.15, centered on .500. The efficiency formula has no minimum-attempt cliff, and a trick pass cannot multiply the rest of a back's season. Negative passing production cannot become less costly because of poor efficiency. An unavailable team record is neutral. The same formula applies regardless of offensive position or player name.

The football motivation is to preserve the quarterback's responsibility for directing the passing game while allowing an exceptional receiver or all-purpose back to beat a credible quarterback. Reasons for restraint: quarterbacks affect more offensive plays; a strong record is relevant to MVP; and impressive skill production alone should not automatically beat an excellent passing season. The passing share, efficiency bounds, and team-success range are explicit judgments that allow reasonable voter disagreement. No award-frequency target is encoded.

Additional controlled results, with complete lines in `mvp_comparisons_20261005.json`:

| Field | MVP outcome | Scores |
| --- | --- | --- |
| 1,650-yard rusher with substantial receiving production; credible 4,000-yard QB | Back | 2899.779 vs 2705.676 |
| Ordinary good back against same QB | QB | 2705.676 vs 2070.904 |
| Exceptional receiver with zero rushing yards | Receiver | 3053.750 vs QB 2705.676 |
| Same exceptional receiver on a 4-win team | Receiver | 2738.750 vs QB 2705.676 |

The passing candidate wins when given the exceptional passing fixture from the OPOY tests. Identical production favors the stronger team. Other tests prove that adding eleven better-record teams cannot exclude the candidate; 1,999 to 2,000 rushing yards has only a one-yard effect; a non-leading rusher remains eligible; and empty production yields no MVP.

### Historical comparison, not fitted ballot targets

Two selected historical candidate fields were evaluated after choosing the formula. The comparison uses headline passing/rushing/receiving lines and verified team records, without unvalidated fumble-loss entries. It is not a complete recreation of either ballot field or player-value context.

| Season | Model MVP | Actual MVP | Model OPOY | Actual OPOY |
| --- | --- | --- | --- | --- |
| 2012 Peterson/Manning field | Manning | Peterson | Peterson | Peterson |
| 2024 Allen/Jackson/Barkley field | Jackson | Allen | Jackson | Barkley |

The 2012 MVP scores are Manning 3384.345 and Peterson 2774.275. The 2024 MVP scores are Jackson 4398.139, Allen 3559.914 and Barkley 2924.210. The formula makes all these offensive candidates comparable, but still prefers different winners in these historical MVP debates. No name exception or weight retuning was used to force the real results. This disagreement and the limited historical sample remain calibration uncertainty; the formulas are not fully validated as a model of real voting.

Historical inputs: [Peterson statistics](https://www.nfl.com/players/adrian-peterson/stats/career), [Manning statistics](https://amp.nfl.com/players/peyton-manning/stats/), [2012 MVP announcement](https://www.nfl.com/news/adrian-peterson-mvp-after-dominant-season-on-vikings-0ap1000000134519), [2024 quarterback comparison](https://apnews.com/article/338922ca0d7a2deb8dc8d514284040c7), [2024 passing statistics](https://www.nfl.com/stats/player-stats/category/passing/2024/REG/all/passingtouchdowns/ASC), [Barkley statistics](https://www.nfl.com/players/saquon-barkley/stats/), [2012 standings](https://www.nfl.com/standings/division/2012/reg), and [2024 standings](https://www.nfl.com/standings/division/2024/reg).

Scope boundary: this is the requested comparison across offensive positions. Defensive production, blocking and special-teams production are still not mapped onto the offensive MVP scale. DPOY, Protector and specialist All-Pro scoring are untouched. Current-team record attribution for a player who changed clubs remains an existing limitation. Saved-season outcomes and combined browser integration remain untested here.
