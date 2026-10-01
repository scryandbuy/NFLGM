# Defensive rotation and pass-rush engine audit

Base: `0badfc6`. Combined changes: `4611ab5`, `5fcdafb`, `775fe30`.
All rules are shared across teams and players; there are no name, ID, or team exceptions.

## Changes

- One condition-based defensive rotation decision compares the assigned player
  with healthy, eligible reserves using role ability. Important passing downs
  modestly favor keeping an edge starter in; exhaustion still triggers relief.
- Removed the additional random edge/interior substitution. Edge snap intensity
  is 0.72, with stamina, sideline recovery, injuries and coach policy still active.
- Simulated-pressure exchanges weigh lost rush ability, replacement rush ability,
  coverage and alignment. Explicit assignments and deep coverage remain protected.
- Reachable protection helpers are assigned before the contest and affect its
  outcome, with diminishing returns for stacked help.
- Rush reps/wins have one accounting owner. Sack-to-scramble conversions retain
  rush/protection metadata. Conservative, idempotent old-save repair is described
  in `PASS_RUSH_ACCOUNTING_AUDIT.md`.

## Verification

66 combined tests passed: defensive rotation, protection pressure, defensive rush,
rush accounting, defensive assignments, fourth-down routes, snap-count mail and
live-game save/reload replay. Earlier rotation/personnel/save suite: 37 passed.
`git diff --check` passed. An existing unclosed wp_model.json ResourceWarning is
emitted by decisions.py; it does not fail the suite and was not changed here.

Paired production-path comparison: all 32 teams, four seeds (93031-93034),
64 games per configuration. Baseline uses the exact original source/data;
candidate uses the complete combined changes. Both use catalog coaching and
real TeamState condition/substitution paths. No global sack/scoring retuning.

| Metric | Baseline | Combined |
| --- | ---: | ---: |
| Points per team-game | 25.90 | 26.76 |
| Edge sacks | 126 | 134 |
| Interior sacks | 158 | 128 |
| Off-ball linebacker sacks | 47 | 56 |
| Captured front-seven sacks | 331 | 318 |
| Elite edge defensive snap share | 65.7% | 84.6% |
| Elite edge sacks (36 player-games) | 13 | 26 |
| Elite edge pressures | 87 | 111 |
| Average-rated edge snap share | 44.7% | 47.4% |
| Reserve-rated edge snap share | 9.3% | 3.5% |
| Injury events | 88 | 98 |

All 64 candidate games have zero discrepancies between logged rush opportunities/
wins and player books. Elite edge usage improves across 4-3, 3-4 and multiple
fronts. These are quality bands (elite OVR >=88, average >=75), not depth labels;
depth rank is separately exported. Backup opportunities remain and exhausted or
injured players are handled by focused tests.

Scoring changes by seed: -0.22, +3.25, -1.13, +1.53 points per team-game.
Front-seven sack changes: -22, -4, +25, -12. This variation does not justify
another blanket probability adjustment. Defensive-back sacks are not included
in the harness player-role totals; these are not all-position sack totals.

## Limits and handoff

These are fresh week-one comparisons, not a multi-season health calibration.
The 10-event injury increase and lower starting-DT end-of-game condition deserve
monitoring over longer saves; this sample does not establish a changed injury
rate. Historical missing scramble reps cannot be recreated, and ambiguous legacy
games are intentionally left unchanged. Original user save was not modified.

Raw artifacts in `outputs/`: pass-rush-baseline.json,
pass-rush-baseline-extra.json, pass-rush-combined.json,
pass-rush-combined-extra.json. The accounting-only comparison independently
confirmed unchanged game outcomes. Changes (4) also verified cached gameday boxes
contain no raw rush counters, and two active-game reloads preserve the live book,
season totals and RNG state exactly.

Integration order: rotation, protection/exchanges, accounting, then this report.
No bundle was made as part of this fix.
