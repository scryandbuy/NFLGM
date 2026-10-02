# Punter-aware fourth downs and defensive game flow

Base: b8c5802. Branch: codex/punt-decisions-20261002.

## Diagnosis

The 816-game register had 35.51% of drives ending in punts (target 29.9–34.9%). `decisions.fourth_down` valued every punt as a fixed 40-yard net. From the opponent's 40 this predicted the receiving team's own 1; from the opponent's 45 it predicted its own 5. The actual punt simulation averages roughly the receiving 16–17 in those situations. This overstated the value of short-field punts.

## Fix

- `punt_strategy.estimate` integrates the existing punt landing/bounce/return model without simulation RNG draws. It uses the selected punter's power/accuracy, long snapper, returner, field position, and weather. It supplies expected receiving position and pin probabilities to fourth-down decisions.
- No blanket increase to punter ratings, distance, pin frequency, passing, rushing, or go-for-it tables. Great pins remain possible, not guaranteed.
- Missing personnel context uses a conservative expected receiving-start floor of 16, instead of an automatic own-1 pin. Live decisions use personnel-aware estimates.
- Defensive confidence comes from completed opposing possessions in this game. It requires at least three meaningful possessions and twelve scrimmage plays, uses yards/play and stop rate, and discounts small samples. One-play turnovers, kneel possessions and half-ending drives do not manufacture confidence.
- Near midfield on fourth-and-four or shorter, confidence modestly increases the go probability of aggressive coaches. Conservative coaches instead prefer field position, proportional to the estimated chance of pinning the opponent inside its 20. A neutral coach receives no preference adjustment. Late-game urgency and halftime protection take priority.
- Observations reset each game and carry through halftime/overtime. Live save/replay reconstructs them.

## Verification

71 tests passed: seven new strategy tests plus existing week-three, clock, endgame, save/resume, and kick-return tests. The estimator was compared with 32,000 actual punts across four power/accuracy combinations and four field positions; mean receiving-start errors were below 1.8 yards in every case. Tests separately verify power, accuracy, weather and returner effects, opposite coach responses, small-sample limits, game resets, live caller context, and must-score/halftime priority.

A bounded comparison used 48 games per engine: every team once on each saved 2027/2028/2029 roster from the existing franchise audit, with matched seeds 4341/4351/4361. This is not a repeat of the full 816-game register.

| Metric | Baseline | Changed |
| --- | ---: | ---: |
| Drives ending in punts | 36.04% | 31.66% |
| Points per team | 23.52 | 23.47 |
| Drive touchdowns | 21.95% | 21.55% |
| Drive field goals | 15.45% | 18.53% |
| Turnovers on downs | 6.05% | 6.71% |
| Drives per game | 23.06 | 22.04 |
| Punt calls inside opponent's 45 | 34 | 9 |
| Punt calls inside opponent's 40 | 9 | 0 |

Punt endings moved within range without a scoring increase in this sample. Field-goal endings rose to 18.53%, marginally above their 18.5% register upper bound; monitor alongside the separate kickoff/field-goal work. Fourth-down failures remained in range. Do not present this sample as proof the entire register is green or that the full-season punt rate is now 31.66%.

An initial fresh-roster exploratory baseline stopped after 21 games because New Orleans could not field a punter on seed 4331. No roster rule was bypassed; the completed comparison instead used the saved, roster-checked franchise checkpoints. Its complete results are in `punt_decision_comparison_20261002.json`. Raw per-decision inputs and logs remain in the worktree's `punt_checkpoint_baseline` and `punt_checkpoint_candidate` JSON/text files.

## Integration

Source files: `game.py` (fourth-down caller/decision and game-flow bookkeeping), `decisions.py`, new `punt_strategy.py`, `build_web.py`, tests and audit driver. No kickoff hunks changed. Merge with the main chat's kickoff changes, then rebuild browser modules with `build_web.py`. Do not copy the entire older checkout over the integration tree.
