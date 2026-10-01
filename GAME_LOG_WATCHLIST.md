# Game log watchlist

This records evidence from user-supplied games, fixes made, and questions to revisit as more logs arrive. A poor outcome alone does not establish an engine defect. Add new observations to the existing item before changing league-wide balance.

## Evidence reviewed

- 2027 Week 12, Green Bay 44–31 Los Angeles. User supplied the complete play log and coordinator review. Reviewed October 1, 2026.
- Original log: `C:/Users/HP/.codex/attachments/a017996e-251b-4141-bd0d-bd305b2b21fa/Pasted text.txt`.
- Implementation base: `4b6195b`. Earlier clock fixes in that base must remain intact.

## Fixed and awaiting new game evidence

1. **Late multi-score urgency.** LA trailed by 21 with 2:31 remaining, then spent 23 seconds after a one-yard scramble at 2:00 and 21 after a three-yard completion. Added faster resets for teams needing multiple late scores: two scores within three minutes, three within four and a half, and larger deficits within five. Ordinary pace, one-score situations, and first-half strategy retain existing behavior. Live and batch drive tests verify the new pace.
2. **Fourth-down screens.** LA called a screen on fourth-and-five at 7:05 in Q4 and lost two yards. Reduced screen selection progressively as fourth-down conversion distance increases, retaining short-yardage and occasional medium-distance screens. Pressure concept selection and pressure audibles respect that decision. This changes selection, not the result of a chosen play; failed conversions remain possible.
3. **Punt narration and field position.** Examples: a 33-yard fair-catch punt from midfield followed by a start at the 16; a 35-yard punt from the LA 42 with an eight-yard return followed by a start at the GB 30. Displayed kick and return distances now reconcile with rounded field spots. Raw kick statistics, return outcomes, and possession spots are unchanged. Legacy saved logs remain readable.

## Gameplay observations to monitor

1. **Screen volume and effectiveness.** LA had eight screens in 40 pass attempts, producing 15 yards in this log. Track screens by down, distance, pressure look, coach preference, and audible. Check more games before changing ordinary-down rates; the fourth-down defect above is addressed independently.
2. **Long field goals.** Both teams combined for six makes in six attempts, including LA kicks from 57 and 59 yards. Track attempts and misses by distance, kicker, weather, and venue conditions. One perfect game is insufficient evidence for a probability change.
3. **Leading team before halftime.** GB led by seven, took a sack at 1:06, then next snapped at 0:27 before switching to aggressive passing and timeouts. Track score, field position, available timeouts, and coach decisions to establish whether the shift is sensible or inconsistent. No new first-half strategy change in this patch.
4. **Star pass rush contribution.** Narration alone cannot establish workload or pass-rush effectiveness. Request box scores or a save when needed; track snaps, rush opportunities, pressures, sacks, coverage assignments, fatigue, and opponent protection together.

## Confirmed review issues awaiting implementation

1. **Pregame blitz recommendation graded on the wrong side.** `gameplan_week.py` produces `blitz_rate`, but `game_recap.groups` recognizes only `blitz_lean`. The unknown key falls into offensive Other plan changes. This explains why Bring it cites GB's offensive yardage and turnover. The blitz setting does reach actual defensive play calling through `gameplan.as_def_lean`; this is a reporting mapping error. The saved-plan summary also omits `blitz_rate`.
2. **Success language exceeds the evidence.** `relative_assessment` retains the absolute positive grade when rates barely change or the comparison sample is insufficient. Thus 9.5 to 9.8 net yards per dropback is called Paid off despite the same line saying no meaningful change. Report continued effectiveness separately from improvement attributed to an adjustment.
3. **Summary ignores limited evidence.** `conclusion` treats a positive result alongside a limited result as favorable overall. Keep attacking down the field gets an unqualified favorable summary despite only three second-half deep plays and an insufficient play-action baseline. Carry uncertainty into the recommendation summary.
4. **Accepted recommendations need concern-specific evidence.** The keep throwing into their blitz recommendation is assessed using all passing plays and play-action plays, rather than passing against blitzes. Several recommendations reuse the same numbers, overstating separate support. Use each recommendation's concern, with overlapping evidence identified rather than treated as independent effects. Pressure recommendations should include pressure and sack rates alongside yardage allowed.
5. **Receiver containment threshold is too rigid.** Puka Nacua had seven catches on 12 targets for 58 yards, zero touchdowns, and one 20-yard catch. The positive verdict requires zero explosive catches, so that one catch vetoes an otherwise efficient containment result (4.8 yards per target). Prefer a qualified assessment such as Mostly contained, with one explosive allowed. This is a grading-design adjustment, not proof that the plan caused his output. Fix singular grammar such as one catches at the same time.

## Review findings that are supported

- Play action heavy: safeties stay home is advice about defending the opponent's play action. The title could be clearer, but run-defense and coverage metrics are not on the wrong side.
- Two-high results improved from 6.0 to 3.8 yards per logged shell play, while opposing net passing fell from 9.2 to 5.1 yards per dropback. These support improvement after halftime, with attribution qualified because several adjustments and game circumstances changed together.
- Blitz-play yardage allowed fell from 10.2 to 3.2 across seven first-half and 11 second-half blitz plays. This supports better results on those calls, not by itself more pressure or sacks.
- Drive yards can include penalty movement; scrimmage totals do not. Kneels can count in drive play totals but be excluded from the review's scrimmage analysis. Those differences alone do not establish an accounting error.

## Updating this list

For each future log, record the season, week, teams, score, relevant timestamps, and build if known. Mark observations as fixed, recurring, resolved by context, or requiring save/box-score evidence. Promote an item to a fix when a reproducible code path or repeated comparable evidence supports it. Keep broad statistical tuning separate from confirmed accounting, selection, and clock defects.

## 2027 Week 15: Green Bay 28-20 Kansas City

- Evidence: user play log, attachment e672d1cf-d393-4fa1-8300-cf017a566095. Build unknown.
- Fixed in the integrated branch: Q4 11:33 roughing erased an eight-yard completion from KC47. Completed positive-yardage passes without a possession change now retain the gain and add roughing enforcement (KC24 in this example); interceptions retain previous-spot enforcement. Regression coverage added; 34 penalty tests passed.
- Open, penalty decision valuation: Q2 4:23, holding accepted after two yards on third-and-21. Current evaluator rates fourth-and-19 at opponent55 as -0.4847 offensive EP versus third-and-31 at opponent67 as -0.6870, thus accepts. Reproduce and calibrate fourth-down alternatives/EP before adding a blanket decline rule. Successful subsequent conversion alone is not proof the decision was wrong.
- Recurring timeout ownership: Q2 0:39 timeout credited to KC after GB reaches KC1. Compare raw timeout side and team metadata, actual score state, and game build; do not infer an AI strategy defect from narration alone.
- Recurring conversion watch: GB third-and-31 and third-and-13; KC third-and-nine run. Track called play versus audible, distance, pressure and conversion rates across sample.
- Context: final score reconciles; both long field goals missed; KC late punt preserved a final possession; final GB kneel is consistent with KC having no timeouts.

## Week 17 Chicago at Green Bay

Green Bay won 41–10. User described this as the latest build. The pasted log does not identify the build or season year; code review used the clean integrated state `2401dd9`. Source: attachment `89299c24-ddab-439a-80d7-389b41f8b4ec/Pasted text.txt`. Reviewed October 1, 2026. This entry changes no gameplay code.

### Fixes supported by this log

- **Late urgency works in the observed situation.** Chicago's Q4 drive uses 14-second resets after completions at 3:30, 3:16, and 2:56, and after the draw at 2:42. The accepted holding call costs six seconds and leaves second-and-16. This is consistent with the new multi-score pace.
- **Punt distances reconcile.** GB36 plus a 47-yard punt leads to CHI17. CHI38 plus 44 yards and a 20-yard return leads to GB38. CHI49 plus 36 yards and an eight-yard return leads to GB23. The other punt ends the half, so no subsequent receiving possession is available for comparison.
- **No fourth-down screen recurrence.** The logged fourth-down attempts include Chicago's failed goal-line run, failed fourth-and-six pass and fourth-and-ten sack, plus Green Bay's successful fourth-and-goal pass. One game without a screen is supportive, not a frequency validation.
- **Game ending is coherent.** Once Chicago has no timeouts, Green Bay kneels at 1:42, 1:00, and 0:18. The final score matches five GB touchdowns and two field goals against one CHI touchdown and one field goal.
- **Screens are not excessive here.** Five non-nullified screens in 54 pass attempts: Chicago two for ten displayed yards; Green Bay three for 26. Keep the earlier screen-volume concern open without treating it as present in every game.

### Strategy findings fixed after review

The two findings below now share `comeback_viable` in `game.py`. One- and two-score chases remain available; each additional required score needs a generous 90 seconds beyond that allowance. This is a coaching heuristic, not a measured win-probability estimate. When that budget is exhausted, ordinary field-position choices replace desperation fourth-down choices, consolation kicks require at least a 60% modeled chance, and forced hurry-up, endgame planning, onside attempts, and automatic timeouts stop. Kneel planning uses the same defensive intent without deleting timeout inventory. Close-game and halftime behavior have regression coverage. Awaiting fresh game logs to judge the transition in practice.

1. **Trailing-defense timeouts lack a realistic comeback check.** Chicago spends all three at 1:54, 1:48, and 1:42 while down 31. In the reviewed code, `_timeout_call` automatically spends the trailing defense's timeouts inside three minutes after an in-bounds play; deficit size and attainable remaining possessions are absent from that branch. A direct reproduction with the defense down 31 confirms it spends one. Recommend a consistent endgame intent decision rather than automatic timeouts for every losing team.
2. **Late field-goal value uses theoretical score counts.** At 2:28, down 41–7, Chicago kicks from 63 yards on fourth-and-three. Reducing the deficit from 34 to 31 changes `ceil(deficit / 8)` from five to four, so `fg_matters` accepts the kick despite the time required for that comeback. On 500 seeded calls with otherwise neutral settings and a strong kicker, this state selected 281 conversion attempts and 219 field goals. A garbage-time consolation kick can be intentional; the problem is that the current arithmetic treats it as a comeback benefit and then continues the automatic timeout chase. Align kick, pace, and timeout decisions with one coherent coach intent.

### Recurring observations without enough evidence to tune

- **Few losing runs.** One negative designed run in 66 carries, excluding the QB scramble and three kneels. Green Bay has 46 designed runs; Hall has 25 carries for about 205 displayed yards, including a fractional goal-line gain. This merits tracking against defensive quality, boxes, substitutions, fatigue, and blocking. It does not establish that all teams' rushing is inflated. Brown's 21 carries produce 93 displayed yards, so the backs did not perform identically.
- **Long-kick success remains a watch item.** This game's three field goals are made from 18, 31, and 63 yards. Week 12 had made kicks from 57 and 59; Week 15 had two long misses. Preserve both successes and failures. The current code's 63-yard chance depends strongly on power, accuracy, and environment; the log lacks those inputs, so a single make does not prove a kicking defect.
- **Long-distance conversions.** GB's third-and-goal draw from the 13 scores after an 11-yard sack. Add this to Week 15's conversion watch, while noting that many other long downs fail in this game. Investigate rates and defensive choices rather than prohibiting a successful draw.

### Calls not classified as defects

- Chicago going on fourth-and-six at its own 47, down seven early in Q2, is aggressive rather than automatically invalid. A 500-call neutral-coach reproduction chose it 56 times (11.2%); the actual coach's aggression is unknown.
- Green Bay's run-heavy approach and roughly 40-second second-half intervals fit its large lead. Chicago's 16-play opening drive and Green Bay's subsequent 99-yard touchdown are plausible outcomes, not accounting failures.
- Goal-line text explicitly describes fractional progress without awarding a touchdown. Drive headers identify net field movement including penalties. Do not equate those headers with offensive scrimmage yards.

### Week 17 coordinator email review

The subsequent email identifies the season as 2027. Its 481 yards / 67 snaps is consistent with the displayed 7.2 yards per play; kneels are excluded from these scrimmage results. Per-play integer narration is not an exact source for underlying fractional yard totals.

- **Confirmed clock-control grading defect, still open.** The accepted shorten-the-game recommendation is marked unsuccessful because rushing efficiency fell from 7.0 to 6.1. Its actual goal is clock control while sustaining drives and protecting the lead. Designed runs rose from 16 of 29 scrimmage snaps (55%) to 30 of 38 (79%); the lead grew from 21 to 31. These support effective clock control, not failure. The accepted-review path needs recommendation-specific measures of run share, clock use, continued first downs, giveaways, and lead protection.
- **Duplicate Tempo evidence, still open.** Both Tempo and Run/pass map to the mix metric, and `assess_choice` changes every mix metric to run efficiency when the recommendation contains negative `pass_bias`. Thus Tempo repeats the rushing decline instead of evaluating pace. This is a reproducible code-path defect, not a disputed threshold.
- **Deep-plan summary remains too confident.** Two relevant deep plays cannot establish that the deep/outside plan delivered favorable results. The 8.9 net passing average supports good overall passing, but cannot independently validate the specific depth or outside emphasis. The summary should preserve the limited-evidence verdict.
- **Pressure verdict is appropriately uncertain.** Only two second-half blitz plays were logged versus nine before. The review correctly avoids a firm verdict. Add pressure and sack evidence before judging whether the intended pass-rush payoff occurred. Fewer logged blitz plays alone cannot prove the accepted setting was ignored; compare opponent dropback opportunities and the installed call settings.
- **Run-defense criticism is relevant.** Allowing 5.3 yards per designed run is a useful weakness to identify even in a large win. It should retain sample and explosive-run context.

Only the endgame gameplay policy was changed with this follow-up. The email findings are documented for a separate recap fix.

## Week 18 Green Bay at Chicago

Green Bay won 44–24. Source: user attachment `47c6647b-69cc-4af1-b121-0f0059f5f23c/Pasted text.txt`. Reviewed October 1, 2026. The log contains no build stamp. The integration checkout remains at `2401dd9`, without the completed endgame fix `7a00193`; observed late-game behavior matches the earlier policy. Do not classify this as a regression in the new policy before testing an integrated build containing it.

### Findings requiring attention

- **Confirmed nullified-fumble presentation defect.** Q4 10:32: an Odunze completion and lost fumble are wiped out by defensive pass interference. Chicago correctly keeps possession at its 42. In `ticker.play_line`, nullification first sets the event to neutral, but the subsequent fumble block changes its kind back to turnover and appends the fumble after the nullification notice. A direct reproduction returns `kind=turnover` with `nullified=True`; the ticker key-play filter/styles use kind without excluding nullified plays. Correct the presentation and category; this log does not establish a turnover-bookkeeping error.
- **Completed endgame fix still needs integration and live validation.** Chicago uses timeouts at 2:52, 2:46 and 2:40 down 25, then uses 14-second urgent intervals down 28 and attempts an onside kick at 0:30 down 20. These are the old behaviors addressed by `7a00193`. Verify the installed build before changing the policy again.

### Recurring gameplay evidence

- **Losing runs warrant a targeted raw-data audit.** GB has 48 designed runs for 265 displayed yards; CHI eight for 28. Only one is visibly negative. Together with Week 17, two visibly negative runs appear in 122 designed carries. These are rounded narration counts, not the engine's exact negative-run statistic: sub-yard losses can display as no gain. Reconcile raw play outcomes, blocking/tackling matchups, and actual ratings before tuning. Both games involve the same teams, so this is not a league-wide sample.
- **Third-down dominance needs distance context.** GB converts 13 of 16, following six of ten in Week 17. Eleven of this game's 13 conversions are on four or fewer yards to go; the other two are third-and-12 and third-and-six. Strong early-down gains repeatedly create easier conversion opportunities. Investigate the run-loss/short-yardage distributions before assuming the third-down conversion model itself is inflated.
- **Screens remain restrained.** Three screens in 62 non-nullified pass attempts: GB one for seven displayed yards, CHI two for seven. No fourth-down screen recurrence.
- **Field-goal evidence is mixed.** Six makes in seven attempts. Chicago makes 41, 43 and 49, then misses another 49; GB makes 18, 21 and 23. No 55-plus attempt here. Keep this distinct from the earlier long-kick watch.

### Supported behavior and accounting

- GB's five touchdowns, five extra points, and three field goals total 44; CHI's two touchdowns, one extra point, one two-point conversion, and three field goals total 24.
- The lone punt from CHI43 travels 49 yards to GB8. The missed 49-yard field goal from GB32 gives GB the ball at its 40. Both spots reconcile.
- The kickoff at 0:04 is explicitly recorded as ending the first half; the third-quarter opening is present. The final single kneel at 0:30 correctly ends the game with Chicago out of timeouts.
- Nullified interceptions, sacks, catches, and runs do not count as official outcomes. Headers explicitly report field movement including penalties. The roughness call at Q4 15:00 retains Hall's 12-yard catch, then adds 15 yards to CHI24.
- Reconstructed passing from rounded narration: Love 23/27 for about 230 yards, two touchdowns, no interceptions; Williams 21/35 for about 258 yards, one touchdown, one valid interception. GB also has a 25-yard QB scramble. Treat these yard totals as approximate until compared with the box score.
- Cook exits injured in Q3 and Hill takes the subsequent carries. No later Cook participation is visible in this log.

This review updates documentation only. Recommended next actions are integration of the existing endgame patch, the small ticker fix, and a focused rushing-outcome audit; no blanket offense or kicking adjustment is supported yet.
