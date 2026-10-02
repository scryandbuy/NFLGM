# Week 3 targeted engine audit — 2026-10-01

Engine revision: `cf70245`. Measurement only; no tuning or engine edits in this audit.

## Production slice

`audit_week3_register.py`: seeds 100141 and 100142; runner RNG seed is league seed +1000. Fresh catalog teams, all 32 clubs play once per seed, 32 total games. This does not model a progressed franchise season or reproduce the user's saved game.

- 706 offensive drives; 4,022 official offensive plays.
- Zero runtime failures, drive-log clock increases/out-of-range clocks, or drive-points/final-score mismatches.
- 31/33 register targets within their existing tolerances.
- Points/team 24.00; plays/game 125.69; drives/game 22.06; sacks 7.12%; run YPC 4.71; negative runs 7.64%: all within tolerance.
- Miss: field goals 122/136, 89.706%, target 85±3%.
- Miss: overtime 0/32, target 6.2±2%.
- 322 standalone penalty log rows, including special teams; 16 Delay of Game rows (0.50/game). This count is not all generated/declined flags and is not compared with a new external benchmark.

Field-goal and overtime misses are small-sample observations, not established tuning defects. Main chat is running the larger fixed-roster and multi-season register.

## Controlled checks

`audit_week3_fixed_probes.py` enumerates 1,000 equally spaced decision thresholds per scenario and coach aggression setting.

- Protect-the-half intent at fourth-and-four on the opponent 46: punt in all 3,000 cases. Explicit attack intent retains coach-dependent choices (18.5%, 29.8%, 42.3% go).
- Fourth-and-goal at the 2, up seven with 1:48: model correctly prices a touchdown/try and subsequent opponent possession. Neutral win values: go .9806, FG .9849. FG remains preferred; the policy retains occasional aggressive attempts (16.1% at neutral aggression). This fix does not force a single decision in all situations.
- Changing only defensive discipline leaves offensive delay/false-start/holding probabilities unchanged. Delay probability stays .00468737 per check.
- Changing offensive discipline .5→.9 changes delay probability .00618733→.00318741, while defensive-holding probability stays .00530859.
- Hurry-up delay probability is zero, as designed.

## Tests and save/replay

Original combined Python run: 175 tests, 172 passed, three fixture errors. Modules: test_week3_engine, test_game_clock_decisions, test_endgame_intent, test_penalty_yardage, test_penalty_pace, test_game_log_regressions, test_week12_game_log, test_save_resume, test_save_encoding, test_overtime_adjustments, test_gameday_timeout_metadata, test_seattle_game_fixes, test_reported_game_fixes, test_game_ai_choices, test_kickoff_clock, test_kick_return_outcomes, test_defensive_returns, test_defensive_return_register, test_register_diagnostics.

The three errors are in `test_seattle_game_fixes.SeattleGameFixes.fake_game`, which passes `rate_fn=None` into game_steps. Kickoff coverage-unit sorting requires that function. They are:

- test_defensive_touchdown_kicks_back_to_original_offense
- test_no_phantom_kickoff_after_game_clock_expired
- test_terminal_kickoff_survives_without_empty_drive_in_both_reports

All three errors were reproduced using the parent revision's game.py (c9ec63d). All 15 Seattle tests pass when an in-memory test wrapper supplies the missing neutral rating function. No permanent fixture or engine change was made. The fixture should be updated by integration before treating that suite as a clean gate.

Save/load checks passed, including identical resumed live game view, actions, final score, player stats, recap, and journal restoration. Both Node browser replay tests passed (defensive blocked-punt touchdown/try ownership and ordinary/nullified scoring). This is deterministic engine replay plus browser scoring-helper coverage, not a manual full-browser save workflow.

## Artifacts

- week3_register_audit.json: per-game results, penalty counts, all target results, raw collector denominators.
- week3_register_audit.txt: human-readable register output.
- week3_fixed_probes.json: full decision and ownership probes.

No new engine defect was established in this audit. Report the two statistical misses alongside the larger register; repair the stale test fixture separately.
