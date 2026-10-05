# Game log watchlist

## October 5 follow-up: designed runs, rush credit and broader evidence

This section supersedes the earlier open implementation notes below; historical
observations remain for comparison. Evidence is in the shared workspace under
`outputs/franchise-followup-2029`.

- **Designed QB runs are now implemented**, following the user's explicit
  request after the initial audit. Selection uses the actual healthy QB's
  mobility, ball security, condition, supporting personnel, defense, game
  situation and coach aggression. It is part of called rushing plays, with
  normal blocking, fatigue, fumble and injury consequences. In 32 paired games,
  87 designed QB runs gained 425.7 yards, with three losses and one lost fumble.
  Pocket passers did not acquire a mobile starter's opportunities. QB-specific
  opportunity distributions remain a multi-seed watch, not a fixed carry quota.
- **Unblocked rushers now compete on path and closing attributes.** Fixed equal
  arrival times previously favored the first defender in a list. Controlled
  two-free-rusher plays distribute opportunities between the LB and slot rusher;
  a single free rusher no longer effectively reaches every QB in 0.6 seconds.
  Alignment geometry and the 0.12-second shared-finish window are modeling
  assumptions. Blocked rush contests retain their prior calculations.
- **Half sacks are recorded for two distinct near-simultaneous finishers.**
  Each gets 0.5 and the team/QB sack total remains one. Escapes and nullified
  plays do not retain sack credits. Fractional awards, history and narration
  are covered. League positional distribution still needs longer observation;
  this correction does not establish that edge/DT/LB shares are calibrated.
- **A kicking coach clamp error is corrected.** A favorable coach could lower
  an elite short-kick probability from 0.995 to 0.990. Matching the upper bounds
  fixes that reversal without changing the distance curve. The saved 51/51
  under-50 streak includes both clubs across 20 GB games; the full saved 2029
  league made 86.8%. No general kicking accuracy reduction was warranted by
  those observations alone.
- **Two full 272-game fresh-roster registers remain above the scoring target:**
  26.49 and 26.41 points per team. Punt-ending drives are 30.75%/30.55%, sacks
  7.26%/6.89%, FG accuracy 84.59%/85.35%, designed-run losses 8.76%/8.73%, and
  rushing explosives 2.23%/2.22%. Scoring, offensive volume and FG-ending drive
  rates remain open; overtime/ties and margin measures vary by seed. These are
  not all-green registers. Do not lower all rushing/passing to hide a pace or
  opportunity problem. The original 26.16-to-27.45 paired rise used identical
  fresh rosters and therefore cannot be explained by player development.
- **Four-year save evidence does not show uniform offensive talent inflation.**
  Actual points/team rose 20.19 to 24.04, but passing YPA fell 7.14 to 7.00 and
  rushing YPC fell 4.54 to 4.41. Engine revisions and volume changed during this
  playthrough. A 16-game matched current-code comparison of fresh versus 2029
  roster/coaching contexts produced 26.22 versus 24.44 points/team, with wide
  uncertainty. This is not an isolated aging experiment. Specialist accuracy
  growth and full talent distributions still need a longer controlled run.
- **Awards and development remain distinct watches.** Positive production is
  required for major awards, and annual DEV can fall after a first credible poor
  season. Repeated LB defensive awards and RB offensive awards are not proof of
  incorrect winners; opportunity and scoring weights still need monitoring.
  Historical seasons were not replayed or their awards silently reassigned.

## October 5 implementation follow-up

The confirmed gameplay defects from the full-season audit are corrected in the
combined source: settled third/fourth-down conversions, red-zone opportunities,
measured man-coverage denominators, blitz yardage alongside pressure evidence,
and a quarterback's decision to leave the pocket before attempting a throw.
Historic cached Game Day boxes are not silently recomputed from incomplete logs.

Paired fresh-roster comparison: 32 games per version, seeds 71941/71942, each
club twice. Baseline versus final candidate: 24 -> 183 scrambles, 166 -> 136
sacks, 38 -> 47 interceptions, and 26.16 -> 27.45 points per team. Dropbacks
were 2,497 -> 2,533. These are experimental outcomes, not full-season targets.
The final candidate includes the existing coach aggression input. No sack,
scoring, completion or interception constants were adjusted to compensate.

An isolated 400-read paired experiment for each of six quarterbacks preserved
the same sack outcomes while allowing more proactive runs for mobile players.
That rules out a direct sack bypass in those cases; it does not establish that
the full-game sack-rate decrease is harmless or entirely random. Scramble
resolution still handles behind-line failures through the sack path rather
than negative recorded scrambles, and designed quarterback runs remain limited.

**Open balance checks:** scoring is already elevated and increased in this
sample; sack rate fell from 6.65% to 5.37%. Monitor both across additional seeds
and developed rosters before calling the change calibrated. Preserve the
existing rushing-loss, field-goal accuracy, pass-rush distribution, award and
annual-development watches below. No blanket tuning is authorized by these
observations alone. Evidence: outputs/full-season-audit-2029/gameplay-fix-evidence.md
and gameplay-candidate-final.json, with paired baseline and fixed-read outputs.

## Completed 2029 season: audited October 5, 2026

Source: `C:/Users/HP/Downloads/nflgm-2029-offseason-1.json`, frozen audit
baseline `b7667b9`. The original save was not advanced or edited. Historical
games span engine revisions, so current-code probes and saved outcomes must
remain separate. Detailed evidence is in `outputs/full-season-audit-2029` in
the shared workspace.

- **QB rushing requires a wiring correction.** The saved regular season has
  187 inferred scrambles in 20,848 QB dropbacks. The per-dropback probability
  is currently drawn only after a sack result. Lamar has seven scrambles,
  Hurts five, Allen four. Correct when the decision occurs before assessing
  balance; preserve open-read throws, containment, clock and coach differences.
  Do not add a broad designed-QB-run system or compensating sack/scoring changes
  merely to match an aggregate target.
- **Conversion and red-zone summaries require definition fixes.** GB's
  divisional game against TB says 7/16 on Game Day versus 10/16 in the recap;
  settled first downs and goal-to-go touchdowns explain the difference. Long
  touchdowns from outside the 20 are incorrectly counted as red-zone trips.
  These are reporting defects, not missing scoreboard points.
- **Pass rush watch remains.** Parsons finishes with 593 rush reps, 82
  recorded pressures and nine sacks; Barela seven sacks, Biles six. League
  sacks: edges 451, DTs 425, off-ball linebackers 308, DBs 57. Review assignment
  opportunities and protection costs before changing position-wide rates.
  Pressure definitions differ historically: 114 player-games have more sacks
  than pressures, all in weeks 1–8 and none after week 8. Do not use one pooled
  pressure rate as if this whole playthrough used identical accounting.
- **Kicking watch strengthened.** Across 20 GB games, under-40 FGs are 33/33,
  40–49 are 18/18, 50–59 are 21/29 and 60+ are 3/6. Expand distance/kicker/weather
  evidence before changing accuracy; no blanket reduction is authorized here.
- **Losses and explosives still need distribution evidence.** GB logs contain
  31 displayed losses in 576 designed runs, opponents 15 in 421. There are ten
  GB and seven opponent designed runs of 20+, plus 73 and 67 pass gains of 20+.
  Keep failed plays, rounding effects, matchup quality and game situation in
  the analysis rather than lowering all rushing or passing production.
- **Accounting checks held up.** All checked additive player-season fields
  reconcile with 272 regular-season and 13 postseason books. All 20 GB score
  and scoring-quarter totals reconcile. These checks do not establish that
  football opportunity distributions are calibrated.

## Week 13 SEA at GB, 31-15: reviewed October 2, 2026

Source: C:/Users/HP/.codex/attachments/9e113d3c-d428-4ba3-92c1-e3b30ca4388d/Pasted text.txt.
Season year and build ID absent. Initial review made no engine changes;
the authorized illegal-shift correction below was subsequently implemented.

- Score reconciles: GB four touchdowns/four PATs/one FG; SEA five FGs. Punt
  distances/returns reconcile to all following receiving spots. Final SEA
  timeouts at1:54/1:48/1:42 leave zero; GB kneels1:42/1:00/0:18 and ends game.
- Losing runs: four of44 designed attempts (9.1%, includes a QB sneak, excludes
  three kneels and erased plays). GB25/125 and SEA19/76 in displayed yards.
  Positive counterevidence to earlier zero-loss games; do not close the broader
  distribution watch or reduce overall rushing based on this game.
- Pass rush: seven sacks across85 dropbacks, GB defense five/SEA defense two.
  Parsons two, Biles two, Robinson one. Sack losses1/5 againstGB and3/10/5/6/5
  againstSEA. These do not reproduce the earlier huge-loss/absent-sack concern.
  Text still cannot establish individual snap share or pressure opportunities.
- Passing: GB22/39,295 displayed yards,3TD/1INT; SEA22/39, approximately244,
  0TD/1INT (one completion ends inside the1 and omits an exact gain).
  Pickens9 catches/195 displayed yards/2TD on14 targets, including69-yard TD.
  Third downs excluding closing kneel: GB8/14, SEA4/16. Track GB long-down
  conversions but retain failed plays and opponent differences in the sample.
- Confirmed rules issue: Q3 11:12 Illegal Shift is treated as a before-snap
  no-play foul. events.py categorizes every Illegal Shift as 'pre'. Ordinary
  illegal shifts are live-ball fouls; the specific running-clock/not-all-set
  exception after a half's two-minute warning becomes a false start and does
  not apply here. Fixed October 2: ordinary shifts now use the live-ball path
  on runs and passes, preserving the foul rate and discipline effects.
  Accepted penalties erase the play and repeat the down; interceptions and
  failed fourth downs can stand when the defense declines. Actual play time
  elapses, and false starts remain separate pre-snap fouls. Verified accepted
  and declined outcomes, half-distance enforcement, erased touchdowns, late
  halves, offender narration, and batch/stepped parity. All 93 tests passed
  across illegal-shift, penalty pace/discipline/yardage, game-log, clock, and
  Week 3 engine suites. Source fix awaits integration/browser rebuild.
  Reference: 2026 NFL rules7-4-2 Item6/7-4-7,
  https://static.www.nfl.com/image/upload/fl_attachment/league/tqivdkzt9mu6wdgsh1ku.pdf.
- Narration says 'on the Sundell'/'on the Benefield'. Current source and browser
  ticker already format named offenders without 'the', so verify producing
  build or stored text before claiming a fresh code defect.
- Punting watch:11 punts across25 possessions (two are half/game-ending
  possessions), opposite the earlier low-punt user log. GB's18-yard punt from
  SEA45 nets14 after return; other GB punts37/35 yards from its own territory
  versus one63-yard punt. Investigate punt quality/weather/short-field spread
  across samples before adjusting the distribution. All spots reconcile here.
- Kicking watch:6/6 FGs, five at46 or shorter plus SEA60. Three SEA red-zone
  trips produce3FG; no touchdowns. Q1 fourth-and-goal inside1 settled
  for17-yardFG merits coach/conversion-value review, not an automatic go rule.
- Q4 Seattle down19 takes60-yardFG at2:38, reducing deficit to16, then kicks
  deep with3timeouts. Unlike the earlier futile down34 kick, this reduces the
  required scoring possessions; deep-versus-onside remains a tactical watch.
  Hurry completions/sack at3:40/3:26/3:12/2:58/2:44 use14-second intervals.


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

## Review issues fixed October 1, 2026 (original diagnoses)

The five findings below are fixed in `157c3c6`. Later historical entries saying these review findings are open are superseded by the implementation status and audit at the end of this document.

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


## October 1 implementation and targeted audit

### Completed fixes

- `157c3c6`: nullification now takes precedence over fumble/safety/score presentation. Canceled plays are excluded from the browser's key-play and scoring filters.
- Pregame `blitz_rate` is graded using opposing offense, blitz results, and pressure/sack evidence. Unknown settings are ungraded instead of silently borrowing offensive yardage.
- Specific deep-plan summaries retain limited evidence. Small before/after samples no longer inherit a positive improvement verdict. Unchanged productive results are described as productive, without claiming the adjustment paid off.
- Tempo uses comparable consecutive in-bounds snap intervals, excluding intervening stoppages, quarter changes, possession changes, and touchdowns. It no longer inherits rushing efficiency.
- Accepted clock-control advice gets one intent-specific finding: run share while leading by at least two scores, run productivity, measured timing, turnovers, and final margin. Missing timing or score context yields limited evidence. A win alone does not guarantee success.
- Passing-against-blitz advice uses those dropbacks. Receiver containment can be qualified as mostly contained with one explosive allowed; singular catch/play wording is corrected.
- `d2509fc` combines these fixes and the previous `7a00193` endgame policy with the main branch's `ac45e5d` scheduler in the isolated `nflgm-gameplan-lock` checkout. The main chat was sent the tested commits; its working folder was not modified here.
- Verification: 63 focused recap, choice-evidence, ticker/log, and endgame tests passed. Save/resume adds six passing tests. All seven scheduler tests passed after using the existing local NetworkX dependency (the default runtime lacked it). Total: 76 distinct targeted tests passed. Browser engine rebuilt; no distribution bundle created.

### Week 18 coordinator email

The new email's 519 yards / 76 snaps rounds correctly to 6.8. Its 48 designed runs and 28 dropbacks total 76; the quarterback scramble belongs to dropbacks. Tiny differences from summed narration reflect fractional raw yards.

- **Deep/outside advice:** 9.1 net yards per dropback supports productive passing generally. One deep play for 73.8 yards cannot validate the specific recommendation. The overall recommendation now stays incomplete, and the evidence says one play, not one plays. Outside-route success is not separately established.
- **Run-front advice:** 5.5 yards on 48 designed runs supports productive rushing. It remains observational evidence, not proof that the recommendation caused the result.
- **Clock control:** designed-run share rose from 22/40 (55%) before halftime to 26/36 (72%) afterward. Rushing remained productive at 5.6 versus 5.5, no giveaways were recorded, and the game ended with a 20-point lead. The matching play log shows clock use consistent with protecting the lead. The corrected report evaluates those goals together instead of repeating YPC under Tempo. The old email already stored in a save is not rewritten automatically.
- **13/16 third downs:** worth highlighting, but eleven conversions were on four or fewer yards. This result alone does not demonstrate a broken conversion model.
- **No clear statistical weakness:** defensible as a statement about these recorded scrimmage plays. It is not a claim that every defensive or special-teams decision was optimal.

### Audit scope

`audit_game_log_watch.py` ran 64 fresh production-path games, all 32 teams in each of four seeds (100101-100104), using catalog coaches and rosters. The simulator's RNG stream is unchanged by diagnostic wrappers. A repeated 16-game sample added rush alignment traces and exactly matched the original game results and team scrimmage summaries. These are fresh 2026 rosters, not a replay of the user's developed 2027 Green Bay/Chicago roster or accumulated fatigue. This was a targeted audit, not a complete franchise register.

Raw artifacts in the workspace outputs folder:
- `game-log-audit-20261001.json`: 64 games, raw plays, register measurements, modeled field-goal probabilities, and player rush statistics.
- `game-log-rush-trace-20261001.json`: repeated seed 100101, including actual rusher alignments and whether the sack winner was unblocked.

### 1. Rushing losses: league total is plausible; box response needs correction

3,134 designed runs gained 14,366.6 yards (4.58 per carry). There were 254 raw losses (8.10%), near the existing register target of 8.54% +/- 1.50 percentage points. Only 121 (3.86%) round to a visibly negative whole-yard result. Thus narration hides roughly half the actual losses. Fresh Green Bay produced 4.77 YPC with eight raw losses in 88 carries; it did not reproduce the user's dominant developed roster.

**New structural finding:** box strength multiplies signed yards before contact by a positive number. A heavier box compresses positive gains, but also compresses negative losses toward zero; it cannot create a loss from an otherwise positive pre-contact result. Subsequent one-decimal rounding can erase tiny losses entirely. `schemes.BOX_NEG` contains reference loss rates but is not wired into this resolver.

Observed by box count (diagnostic sample, not a controlled causal comparison):

| Box | Carries | YPC | Raw losses | Visible losses |
| --- | ---: | ---: | ---: | ---: |
| 4 | 271 | 6.93 | 9.6% | 7.4% |
| 6 | 871 | 4.63 | 7.9% | 3.2% |
| 8 | 268 | 3.21 | 8.6% | 1.1% |
| 9 | 120 | 2.78 | 1.7% | 0% |
| 10 | 106 | 1.17 | 3.8% | 0% |

**Next action:** separate disruption/loss generation from gain compression, then calibrate by box, blocking matchup, and distance while preserving overall rushing. Do not apply a blanket rushing reduction. This investigation does not implement that new model change.

### 2. Third downs: distance explains much of the apparent dominance

703/1,625 conversions (43.3%) across the sample:

| Distance | Converted / attempts | Rate |
| --- | ---: | ---: |
| 1-2 yards | 192 / 265 | 72.5% |
| 3-4 yards | 152 / 279 | 54.5% |
| 5-7 yards | 170 / 405 | 42.0% |
| 8+ yards | 189 / 676 | 28.0% |

Short runs converted 137/162 (84.6%) on third-and-two or shorter; runs on third-and-eight or longer converted 11/92 (12.0%). The latter does not look like automatic long-distance success. The short-run success rate and heavy-box loss mechanism should be investigated together against the existing research data. No independent third-down probability nerf is justified by the Chicago 13/16 alone.

### 3. Field goals: distance falloff works; retain the accuracy watch

The diagnostic kick rolls include 32/34 makes from 50-54, 24/35 from 55-59, and 9/17 from 60+. The model expected 29.0, 25.4, and 7.9 makes respectively. Four attempts at 64-68 yards all missed, with modeled chances from 7.7% to 32.7%. This contradicts the idea that extreme kicks routinely succeed automatically.

Across all 268 diagnostic kick rolls, modeled expected accuracy was 87.2%. Official recorded field goals were 239/267 (89.5%), above the register's 85% +/- 3-point target in this sample. One diagnostic roll was not counted as an official attempt; distance-bucket numbers above are explicitly diagnostic rolls, not certified official split statistics. Continue watching official accuracy by distance, kicker, weather, and selection; the limited extreme-distance sample does not justify a new curve change yet.

### 4. Pass rush: accounting and workloads pass; allocation remains a watch item

All 64 games matched logged rush reps/wins to the player stat book: zero accounting discrepancies. Sack rate was 7.36% under the register's attempt-plus-sack denominator. Elite nominal edge players (88+ overall) averaged 87.4% of defensive snaps and 21 sacks in 36 player-games. Fresh roster workload does not reproduce the earlier two-thirds-snap concern.

Nominal-position sack totals were 111 edge, 136 interior, and 87 linebacker; another 21 belonged to defensive backs. Interior players also had more recorded rush opportunities (10,168 versus 8,785). A 16-game trace verified that this was not merely mislabeled alignment: 37 sacks came from actual interior alignments, 35 from edges, 27 from off-ball alignments, and six from the slot. Seventeen of the 105 sacks came from unblocked rushers (11 linebackers, six corners).

**Next action:** monitor sacks per rush opportunity, free rushes versus blocked wins, protection help, and individual rush attributes alongside snap share. The current noisy arrival-time race and free-rusher opportunities merit deeper distribution calibration if this pattern persists. Do not reintroduce duplicate pressure counts or boost one named star to force a target stat line. No additional pass-rush tuning in this audit.


## October 1 follow-up: stacked-box correction completed

**Decision: the stacked-box defect is fixed and its targeted calibration passes. No further global rushing or separate third-down adjustment is supported by these tests.** This supersedes the earlier next-action recommendation to implement the contact correction.

### What changed

- `schemes.box_run_contact` uses the existing box-specific negative-run reference rates to shift penetration risk on the same underlying blocking/noise result. Stronger boxes can now turn marginal gains into losses; weak boxes can permit escape from marginal losses. No independent random stuff roll or extra RNG draw was added.
- Positive contact gains are recentered before the existing box gain multiplier, avoiding a second broad yardage boost/penalty. Negative contact depths bypass that gain multiplier, so a stacked box cannot shrink an existing loss toward zero.
- Run scheme, front fit, motion and execution affect signed outcomes in the correct direction: offensive advantages limit losses and help gains; defensive advantages deepen losses and restrict gains. Ratings, blocking assignments, pursuit/YAC, and run-block stat accounting remain active.
- Six-man box contact remains neutral. Controlled tests verify that adding box defenders hurts the runner on identical contact draws, while improved blocking still helps. The reference loss gradient is checked using 10,000 evenly spaced normal quantiles per box, independent of game-sample noise.

### Verification and calibration

56 focused tests passed across contact behavior, defensive front assignments, endgame policy, rush accounting, Game Plan wiring, game-log regressions, and offensive personnel. Browser engine files rebuilt. No bundle created.

Production evaluation: four comparison seeds (100101-100104, 64 games) and four fresh validation seeds (100111-100114, another 64 games), every team once per seed. The first comparison reuses the baseline's league configurations/seeds; changed outcomes naturally change subsequent random consumption, so these are aggregate comparisons, not identical-play causal estimates. No coefficient adjustment was made after inspecting the fresh validation set.

| Metric | Prior 64-game baseline | Corrected comparison, 64 games | Fresh validation, 64 games |
| --- | ---: | ---: | ---: |
| Designed runs | 3,134 | 3,104 | 3,224 |
| Yards per designed run | 4.58 | 4.69 | 4.66 |
| Negative designed runs | 8.10% | 8.02% | 8.37% |
| Third-down conversions | 43.26% | 41.17% | 42.22% |
| Third-and-two-or-shorter runs converted | 84.57% (137/162) | 80.37% (131/163) | 81.14% (142/175) |

Combined corrected sample: 6,328 carries, 4.67 YPC and 519 losses (8.20%). Both running measures satisfy the existing 4.52 +/- 0.35 YPC and 8.54% +/- 1.50-point negative-run tolerances. Overall thirds: 1,374/3,295 (41.70%); short third-down runs: 273/338 (80.77%). No third-down-specific probability was changed.

Combined loss rates by box: four 4.95%, five 6.23%, six 9.07%, seven 9.23%, eight 11.89%, nine 12.23%, ten 10.00%. Nine/ten combined are 46/409 (11.25%), versus six losses in 226 carries (2.65%) in the baseline. Ten-man boxes alone are only 180 carries and occur in different field-position/personnel situations; do not force every observed bucket to exactly match a reference percentage. Identical-input tests establish the monotonic effect of added box defenders; live buckets retain matchup and sampling differences.

### Remaining watch, with clear action boundaries

- **No immediate additional rushing calibration.** Review future user saves/logs for the corrected heavy-box behavior, particularly goal-line situations. Fractional losses can still legitimately round to no gain in narration.
- **No separate third-down adjustment now.** Continue tracking conversions by distance and play type. The correction already moves short-run conversions downward without a special conversion modifier.
- **Scoring remains an open calibration question.** Points per team were 24.57 in the baseline, 25.02 in the comparison and 25.49 in validation, above the existing 22.90 +/- 1.50 target. This small aggregate difference does not establish causation by the contact change; a scoring/drive/field-goal audit is required before further tuning. These results do not constitute a full register pass.
- **Pass-rush allocation and long-kick accuracy remain their previously documented watch items.** They were not separately tuned here.

Artifacts: workspace outputs `stacked-box-candidate-20261001.json` and `stacked-box-validation-20261001.json`; baseline `game-log-audit-20261001.json`. The isolated checkout is `work/nflgm-gameplan-lock`. The main chat receives the tested commit for integration; other checkout files are not overwritten.

## PHI at GB — Divisional Round review

- Fixed: tied-first-half defensive timeout branch could fund an opponent's continuing drive after first downs. Restrict this possession-buying branch to a failed third/fourth-down conversion. Explicit touchdown/defensive-TD and turnover outcomes cannot spend timeouts.
- Watch: PHI fourth-and-one at GB49, tied with 0:32, passes and is sacked. Revisit fourth-down win-probability estimate including opponent short-field scoring risk and the short-yardage play choice; one outcome alone does not prove the decision wrong. No blanket punt/run override added.
- Cleared: Q3 DPI acceptance on second-and-seven: completion gained three, while penalty grants automatic first down. Earlier review mistakenly treated both as first downs.
- Cleared as direct clock error: GB 54-yard kick with 0:14 followed GB's last timeout, so clock was stopped. Waiting cannot drain game time. Watch whether preceding timeout/clock plan should preserve a later kick opportunity; no unsafe extra-play requirement added.
- Timeout-after-TD appearance: stronger explicit scoring guard added; exact cause in this saved build is unconfirmed without structured play outcomes.

## NY at GB — Conference Championship, pre-latest-fixes build
- Fixed planner mismatch: extra-play and bleed estimates now respect remaining downs. Leading/tied offense does not spend a first-half timeout after a failed third-down conversion beyond the opponent40 simply to enable a punt.
- Fixed lookahead cliff: with no timeouts, a completion leaving 18+ seconds can budget 12 seconds for hurried setup instead of automatically treating an in-bounds catch with fewer than25 seconds as drive-ending. Thirty-second long-kick scenario now has a continuation option; actual choice still depends on kicker.
- Watch: 59-yard kick up3 with1:50. Current fourth-down logic DOES compare punt WP against kick WP including missed-kick spot and timeout edge. Representative42% kicker yields FG .7992 vs punt .7919 (go .8128); small-margin calibration concern, not missing wiring. Need actual saved kicker/weather/coach inputs and broader decision study before overriding.


## Week 3: Green Bay 24-16 Chicago (reviewed October 1, 2026)

Source: user attachment `507e766b-d918-4234-997a-8e0c7ed95a53/Pasted text.txt`. Season year and build are not specified. Read-only gameplay review; displayed yardages are rounded and cannot certify the raw box score.

### Confirmed presentation inconsistencies

- Q1 10:29: punt from CHI17, 54 yards, six-yard return implies GB35, but the receiving drive starts GB34. That drive's five-yard neutral-zone penalty then shows GB40. Check both drive-heading rounding and special-teams display endpoints; earlier fixes do not prove this particular build contains them.
- Q1 6:31: a field goal from displayed CHI20 is labeled 36 yards, rather than the displayed spot plus the engine's 17-yard kick offset (37). Likely inconsistent rounding of continuous field position; do not infer that the actual cap/score/stat ledger is corrupt.

### Recurring items to investigate

- First-half intent/clock consistency: GB leads 10-7, uses timeouts at 0:57 and 0:51, completes 12 yards on third-and-16 at 0:45, then waits until 0:11 for fourth-and-four at CHI46 with one timeout still unused. The current timeout guard deliberately avoids stopping a leading/tied stalled first-half drive outside FG territory. It should be reviewed together with the subsequent fourth-down decision: conceding the half and seeking points are different intents. The text alone does not prove what the saved coach/plan chose.
- Penalties: 17 accepted penalty entries, including four Chicago Delay of Game calls (Q2 9:54, Q3 12:24 and 10:02, Q4 9:22). Inspect presnap frequency, discipline effects, and repeated calls across games before adjusting all penalties.
- Late lead protection: GB goes for fourth-and-goal at CHI2, up seven at 1:48. A short FG would establish a two-score lead. Going can still be rational with a high conversion estimate and the opponent pinned deep; audit modeled alternatives rather than declaring the penalized sack proves a bad decision.
- Pass rush: only one non-nullified sack, against GB. Chicago takes none. Keep the pressure/opportunity/workload watch open; a text log cannot establish whether Parsons or other rushers played too little.
- Negative rushing: one displayed loss across 43 non-nullified designed runs (GB 26 for 88; CHI 17 for 102). Chicago's other negative run was erased by holding. This adds evidence to the watch, but one game does not overturn the prior multi-seed contact calibration.

### Healthy behavior observed

- Final score reconciles: GB three TDs/three PATs/one FG; CHI two TDs/one PAT/one FG with a failed two-point try.
- Chicago's final drive uses 14-second resets after in-bounds short completions, six seconds after incompletions, and a timeout after the 12-yard completion. This is consistent with two-score urgency.
- Chicago attempts fourth-and-nine late rather than punting, scores, tries for two down eight, and attempts an onside kick. Green Bay's recovery and final kneel fit Chicago having no timeouts.
- Six non-nullified screens total: GB one for 13 displayed yards, CHI five for eight. No fourth-down screen recurrence. No new general screen-rate change supported.
- No evidence for a broad passing, rushing, scoring, or fourth-down conversion retune from this game alone. Prioritize display consistency and investigate clock intent and delay-of-game rates.


## Week 3 follow-up: display fix and targeted decision investigation

### Fixed: presentation arithmetic

- `ticker._spot_yards` now rounds half-yard field positions consistently. The former ties-to-even rounding made translated five-yard moves display as four or six yards. Drive headings and snap locations share this formatter.
- Punt narration now derives gross and returned distances from recorded origin, catch and final spots when available. `kick_returns.resolve` had overwritten the earlier corrected `display_ret` with independently rounded return yardage. Rendering repairs saved raw logs with endpoint metadata too. Return-penalty movement is excluded from the reported return distance.
- Field-goal text uses the displayed line of scrimmage plus 17, avoiding 36-yard text beside a displayed 20-yard line. Old records without spot metadata retain a distance fallback.
- Raw yards, possession spots, kick probabilities, outcomes and RNG are unchanged. Already-generated saved text must be recaptured to reflect new formatting; this does not rewrite historical rendered strings on load.
- Verification: 18 focused tests passed (`test_week3_display`, `test_week12_game_log`, `test_game_log_regressions`), including 500 real return-pipeline trials, flags, saved-field reconstruction, legacy records and no input mutation. The older punt test assumed integer raw receiving spots; updated it to verify the actual displayed arithmetic with fractional return results.

### Investigation conclusions (not implemented in this display patch)

1. **First-half clock intent needs a targeted fix.** Reproduced third-and-16, own 42, up 3, 45 seconds before half, one own timeout. `_timeout_call` refuses the timeout both with no plan and with explicit hurry. Neutral completion time is 34.6 seconds. At the resulting fourth-and-four on opponent 46 with 11 seconds, independent fourth-down logic still goes in 29.8% of uniformly swept random draws with neutral aggression (18.5%-42.3% across aggression 0-1). This confirms inconsistent decision branches, not proof of the exact user coach. Make preserving clock and fourth-down intent share the same half-aware assessment; do not restore indiscriminate timeouts for every stalled leading drive.

2. **Penalty ownership needs a targeted fix; no general rate reduction supported.** `game.drive_steps` supplies defensive awareness as the single discipline input to `events.penalty_check`, so even offensive Delay of Game/False Start odds respond to opposing defensive awareness. Staff offense/defense penalty multipliers are averaged into the crowd-noise parameter, which only changes two offensive presnap foul types. Select discipline/staff effects by the offending side. In three controlled samples of 40,000 checks, delays numbered 212/178/152 as defensive awareness increased 0.60/0.787/0.90; expected 232.4/187.5/160.4. Neutral expectation is 0.31 delays in 66 checks. Four delays is unusual, but these tests do not reproduce league-wide excess or the user's saved team. Avoid a blanket penalty nerf.

3. **Fourth-down evaluation has structural defects; fix before tuning aggression.** `decisions.fourth_down` evaluates a goal-line conversion as first-and-goal at the 1 with unchanged score, rather than a touchdown and ensuing possession. The field-goal success branch also assumes the opponent starts at its 25; the game has varied returns and 35-yard touchbacks. At up 7, opponent 2, 108 seconds, neutral aggression and timeout edge +2, current model prices FG 0.9861 vs go 0.9778 win probability; stochastic caller still goes 15.7% (9.8%-22.2% across aggression 0-1). The logged go decision is possible coach variation, not by itself a bug. Correct scoring/possession branches and verify the valuations before changing go frequency.

Reproducible probes and outputs: `audit_week3_decisions.py` / `.json`. These are isolated context tests, not replay of the user's save. Pass-rush and negative-run observations remain on watch; no fresh broad simulation or tuning was undertaken.


## Week 3 targeted engine fixes completed

The three findings in the preceding investigation are now implemented.

1. **First-half clock intent:** an explicit hurry plan can spend the remaining timeout after a failed third down. With no timeout left, the same intent uses hurry pace. When a leading/tied club instead lets a stalled drive's clock run, that protect intent carries to fourth down and chooses a viable kick or punt rather than independently gambling on a conversion. Trailing clubs and second-half comeback decisions retain their prior paths. The drive stores this short-lived intent; no new league/save counter is needed.
2. **Penalty ownership:** offensive awareness now comes from the offense's projected personnel group. Defensive awareness remains defensive. Each foul's rate uses the offending side's awareness and staff multiplier; either-side fouls weight their original 18/82 side split by those two factors before selecting the offender. Crowd noise independently affects only false starts and delays. Existing base rates, neutral calibration and hurry suppression are unchanged; legacy callers can still provide a shared discipline value.
3. **Goal-line fourth downs:** converting goal-to-go evaluates six points plus the selected PAT/two-point outcome, followed by opposing possession. Ordinary conversions retain possession. Made field goals and touchdown/try branches share a representative kickoff spot (receiving own 35, matching the current touchback rule), including reversed timeout advantage and home/away ownership. Terminal-clock scoring uses win/tie/loss outcomes. This is a decision estimate, not a new actual kickoff rule or simulated return.

Verification: 86 focused tests passed across new regressions, clock behavior, endgame intent, penalty enforcement/pace and prior game-log fixes. Four fresh-roster games completed with 538 penalty checks; every check supplied separate unit discipline/staff inputs, with no runtime errors. Results are in `week3_engine_smoke.json`. These games are runtime verification, not proof of long-run calibration. No global penalty/scoring/rushing rate adjustment, no change to coach aggression coefficients, and no user-save replay. Browser engine rebuilt for integration.

Continue monitoring first-half play selection after a stalled hurry drive, penalties by offending team/foul type, and goal-line choices by score/timeouts. Previous low-sack and negative-run items remain observational watches.

## Week 4 GB at NY: clock intent and copied labels

- Fixed fourth-and-four at own24, down26, 3:01: all1000 seeded trials now retain possession rather than the prior467 punts. The late possession override shares the comeback-viability check, preserves useful kicks, and does not force comeback behavior in decided blowouts.
- Added gradual second-half catch-up pace based on remaining game time and required scores. It applies to normal in-bounds play intervals and penalty ready-for-play runoff, preserves timeout/incomplete timing, and has no discontinuity at the Q3/Q4 boundary. Full hurry remains separate from this gradual acceleration.
- Copied play-by-play now applies the existing NYG->NY, NYJ->NJ, LAC->CA presentation formatter to the complete exported text. Saved canonical team IDs are unchanged.
- Verification:37 clock/fourth-down checks,14 save/resume/log checks, and a Node execution of the actual copy callback passed. Browser engine rebuilt. Four interceptions and two11-yard sacks remain observational watches; no broad turnover or sack-loss tuning from this game.

## Week 5 DET at GB: safety and onside fixes

- Safety outcomes are identified before clock/timeout processing. Only live action runs off; no post-safety huddle or timeout is charged. Sack and run safety endpoints are the goal line, fixing net field-yardage summaries.
- Reproduced safety at4:59 from own7: finishes4:53 with both teams' timeouts unchanged in ordinary and stepped drive paths. Original own13 drive endpoint gives minus13 net field yards including the earlier penalty.
- Onside evaluation reserves45 seconds plus6 seconds for each additional required scoring possession. It no longer values one usable possession as a complete comeback. The deep-kick alternative also cannot reuse timeouts spent forcing the stop.
- Down23 at2:14 with three timeouts now selects onside across cautious/neutral/aggressive settings. One-score deep-kick and decided-blowout cases remain available. This is a bounded clock-feasibility heuristic, not a newly calibrated full comeback probability model.
-55 focused checks including safety ordinary/stepped paths, previous clock/log regressions and save/resume passed. Browser rebuilt. Repeated18-yard sacks remain on the watch list; no sack-distribution change.

## Week 6 CHI at GB: punt roll, kickoff warning, onside caller

- Fixed a confirmed onside wiring bug: game_steps passed the number of required scores to _onside_call, which expects points. The caller now supplies the actual deficit. An integration test drives the scoring/halftime/kickoff loop and verifies 15 points, rather than 2, reaches the policy. Down15 at2:03 with three timeouts still chooses deep under the existing policy; retain as a decision watch, not a forced onside change. The earlier down23 at2:14 regression retains its onside choice.
- The opening42-yard touchback from the opponent44 was a punt landing short and rolling into the end zone. The touchback branch omitted the roll from gross yardage. Touchback gross now ends at the goal line (44 in this case); net remains24 and possession starts at own20. Rendering also repairs legacy text from origin metadata without mutating stored records. Previously recorded historical gross statistics are not migrated.
- A kickoff return crossing2:00 had no warning entry. Receiving drives now record the warning at the return's actual ending clock and mark it delivered, in both halves and ordinary/stepped modes. The return is not truncated at2:00; no extra timeout is consumed.
- Watch: six GB sacks for48 displayed yards including13 and15, no CHI sacks; zero negative designed runs across45 attempts; passing TDs77/78/49; opening fourth-and-three at own41. No broad rates or aggression retuned.
- Score37-22 reconciles. Improved GB comeback pace, late fourth-down attempts, nullified-TD scoring, and final kneel remain healthy observations.

## Week 7 GB at MIN: halftime risk, sack severity, live-foul context

- Halftime shot valuation now includes bounded protection-versus-rush sack risk, play duration, and whether a timeout or sufficient clock remains for the kick. The reported third down at opponent17 with10 seconds and no timeouts chooses kick across all three aggression settings. A touchdown-required endgame still avoids a useless field goal.
- Sack severity now depends on drop depth and pressure arrival time, with a narrow ordinary distribution and rare additional escape loss. Sack probability and the existing scramble escape path are unchanged. In100,000 medium-drop samples at2.7 seconds, mean loss6.862 yards,14+ losses0.412%,18-yard losses0.005%. This is a component experiment, not full-game calibration.
- Existing live flags are checked after the resolved play and scramble conversion. Incompatible roughing/pass-interference/facemask outcomes are reassigned to an eligible live foul on the same offending side. No extra flag draw or consecutive-flag cooldown. Illegal contact can still precede a sack. Pressure is the current proxy for passer-contact opportunity; individual hit evidence remains a potential refinement. Total flag occurrence and offending side are preserved, but individual foul frequencies can change and need monitoring.
-77 focused tests passed, including the reproduced halftime choice, touchdown-required case, timeout value, depth/tail checks, same-side flag preservation and legitimate consecutive roughing. Browser engine rebuilt.
- Watch full-game sack loss by depth and named-foul mix/yardage. GB's increased second-half passing was the user's selected adjustment and is not treated as a bug. Historical saved logs are unchanged.

## TE overall and assignment roles

- Headline TE overall transfers11 percentage points from blocking to receiving: receiving60%, blocking10%, awareness17%, speed/acceleration9%, strength4%. Balanced retains the old weights; blocking-role grade weights blocking50%. All grades derive from existing attributes, with no permanent archetype or attribute grant.
- Additional12/13/22 personnel TE slots use the blocking role; lead TE remains receiving;21 personnel TE uses balanced. Manual lead depth order remains respected. CPU/assistant XP weights follow the role, including pinned lead order. Existing ceiling checks still use headline overall.
- Legacy heavy_te/spread_te scheme tags no longer stack a second role adjustment through fit or on-field attribute modifiers. Other offensive scheme adjustments remain.
- Player serialization carries te_rating_version1. Legacy TE loads shift fixed potential and potential ranges by new minus old effective overall, bounded0..99. Subsequent save/reload does not repeat it. New-player creation and draft shaping already use position_score and therefore use the revised scale automatically.
-65 focused tests passed, then8 role tests passed after adding a non-TE preservation check (66 distinct checks across those runs). Coverage includes migration, limits, role-sensitive upgrade mix, pinned lead, personnel, draft generation, ceiling enforcement and trade windows.
-Read-only2028 Week7 save experiment migrated/reloaded247 TEs. Bowers88.99 overall,89.95 potential, unchanged attributes/XP. Formula-only valuation comparison with rebuilt live comp pools: Bowers team APY20.26m->21.11m, seller trade value17.63->29.45, buyer39.52->51.34. Rostered TE median APY4.06m->3.85m; maximum20.27m->23.67m. These are targeted estimates, not executed trades or full-season balance proof. Monitor elite TE trade returns and contract distribution. User save file was not modified.


## GB 31-HOU 28, Week 8: user log reviewed October 2, 2026

Source: C:/Users/HP/.codex/attachments/08ae5f6a-d052-41dc-b36a-ff021687a75d/Pasted text.txt. The copied log contains no build ID or season year. Counts below use displayed yards, exclude nullified plays, and separate kneels/scrambles from designed runs; they are not a replacement for the saved box score.

- Confirmed display arithmetic: both punt spots reconcile (GB41, 59-yard touchback -> HOU20; HOU6, 59-yard punt and 13-yard return -> GB48). The missed57-yard FG from GB40 leaves GB at48, the kick spot. Scoring reaches HOU28-GB31, including Houston's tying two-point conversion. Goal-line holding erases the TD and the replayed fourth down produces a FG. Timeouts reset at halftime, neither side exceeds three, and Houston uses its final timeout between the two closing GB kneels. No confirmed new clock/field-position/accounting defect from this text.
- Priority investigation: zero negative designed runs in49 attempts (GB15/121, HOU34/145). HOU has three no-gain runs, so short-yardage stops do occur. GB averages8.1 yards per designed run; this adds to prior negative-run/rushing-efficiency evidence. Inspect raw versus displayed losses, contact outcomes, blocking matchup and box before any broad tuning.
- Priority investigation: one sack across76 dropbacks (74 pass attempts, one sack, one scramble), all on Houston. GB has no sacks allowed in33 attempts. Text cannot establish rush opportunities, pressure rates, protection help, or Parsons' snap share; use save/box-score instrumentation before attributing cause.
- Offensive distribution: GB20/33 for328 passing yards, three passing TDs, one INT; HOU31/41 for321, three TDs, one INT. GB's53- and84-yard TDs account for137/328 passing yards. Third downs: GB5/8, HOU8/16, treating the third-down lost fumble as a failed conversion. These totals are reconstructed from rounded narration.
- Low-priority watches: two punts across19 possessions (two are half/game-ending kneel possessions); one kickoff touchback in12 kickoffs; both teams attempt57-yard FGs, one made and one missed. Evaluate punts alongside fourth-down attempts, giveaways and explosive TDs rather than tuning punt frequency from this game.
- Fourth-down/clock decisions: Houston's Q3 fourth-and-four from its47 while down8 and GB's Q4 fourth-and-three from HOU4 while tied are situational gambles, not proven decision bugs. Houston's tying FG attempt on fourth-and-six at0:33 is coherent. The late short kickoff giving Houston its42 merits tactical monitoring, not a forced fix based on the return outcome.
- Status: review/watchlist update only. No engine changes or claims of reproducing this saved game's outcomes.


## October 2: recent-log investigation, rushing losses, sacks and explosives

**Decision: fix post-catch pursuit selection before tuning explosive frequency. No blanket rushing reduction or sack increase is supported. The low visible-loss rate in the historical logs remains unresolved rather than declared fixed. No production engine changes in this investigation.**

### Evidence reviewed

Re-read the six supplied Weeks3-8 logs against the saved 2028 Weeks3-7 summaries; also reviewed the earlier 2027 Week12 LA and Weeks17/18 Chicago logs. Counts exclude nullified plays and kneels, retain designed QB runs/sneaks, and separate scrambles from designed runs. Copied logs do not identify the engine build. Week7 has eleven GB designed runs, including Love's sneak, and46 MIN runs including Fletcher's carry; HB-only box rows omit those additional runners.

| Recent game | Visible run losses / designed attempts, both teams | Sacks / dropbacks, both teams |
| --- | ---: | ---: |
| Week3 GB at CHI | 1 /43 | 1 /80 |
| Week4 GB at NY | 1 /58 | 5 /58 |
| Week5 DET at GB | 2 /52 | 5 /82 |
| Week6 CHI at GB | 0 /45 | 6 /90 |
| Week7 GB at MIN | 2 /57 | 3 /68 |
| Week8 GB at HOU | 0 /49 | 1 /76 |
| Total | 6 /304 (1.97%) | 21 /454 (4.63%) |

GB allowed14 sacks in240 dropbacks; opponents allowed7 in214. Houston's sack-free GB game is therefore not representative of the whole sequence. Recent completed passes of40+ yards: GB4/224 attempts, opponents4/205. The older three logs also show few visible rushing losses (three in159 attempts), but their historical builds cannot establish a current regression.

### Current-engine experiments

Source checkout `nflgm-gm-financial-plan` at7f20cb2; relevant gameplay source matched integration10b547b at inspection. Non-mutating diagnostic wrappers refresh the previous audit's contact calculation to include support blocking, record actual rush assignments and post-catch tacklers, and consume no extra RNG draws. Source save `Downloads/nflgm-2028-week-7.json` was read only.

32 fresh-roster games and32 developed-save games, seeds102021/102022, each team once perseed. Developed-save runs independently reload the save perseed and restore runner state, then play randomized pairings atWeek8. Eight additional HOU-home/GB-away games independently reload that save with seeds102031-102038. They are current-engine experiments, NOT exact replays of historical RNG, builds, Week8 acquisitions or user halftime choices. The saved Week7 user plan is not applied as a Week8 plan. These samples are not a full register certification.

| Sample | Designed carries | YPC | Raw losses | Whole-yard visible losses | Sack rate* |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fresh rosters,32 games | 1,699 | 4.57 | 140 (8.24%) | 81 (4.77%) | 6.96% |
| Developed save,32 games | 1,621 | 4.56 | 164 (10.12%) | 89 (5.49%) | 7.08% |
| GB-HOU,8 games | 333 | 4.67 | 29 (8.71%) | 17 (5.11%) | 7.06% |

*Sack rate uses the existing register's attempts-plus-sacks denominator; the historical table uses all dropbacks including scrambles. Do not compare them as identical denominators.

Rounding hides roughly half of raw backfield losses, but does not fully explain why the supplied historical sequence has only1.97% visible losses. Current tests do not reproduce that shortage; developed-save raw losses are already slightly above the register's10.04% upper tolerance (10.12%, a small-sample miss). Increasing loss frequency globally would be unjustified. Heavy boxes continue to increase loss risk: saved sample six-man46/487 versus eight-man29/151, although live buckets differ in matchup/context. Support blocking's average contact contribution was only+0.008 yards in this sample, not evidence of a universal support-block bonus overwhelming penetration.

Current pass rush also does not reproduce a global failure: zero rush-rep/win accounting mismatches across64 mixed-matchup games. Elite edge snap shares were86.2% fresh and84.7% developed. In eight GB-HOU trials Parsons logged459/583 defensive snaps (78.7%),284 blocked rush reps,27 wins and7 sacks. That supports retaining meaningful rotation and individual ability rather than adding a named-player boost. Existing box 'pressures' match credited rush wins, so do not treat their sum as unique pressured dropbacks.

GB-HOU trials: GB23 sacks in378 dropbacks, HOU29 in362; GB4.69YPC and HOU4.64. GB had six40+ completions and HOU seven across all eight games. Fresh versus developed passing:6.46 versus6.12 net yards perdropback;40+ completions28/2259 versus23/2323 attempts. These do not support a broad passing nerf. Scoring remains on the prior watch (25.11 and24.89 points/team in the mixed samples, above the existing target), but requires its own drive/field-position analysis.

### Confirmed structural issue: pursuit after the catch

`plays._pass_play` draws nearby tacklers with replacement from all DBs/LBs, instead of deriving unique pursuers from the actual coverage assignments. The same defender can appear more than once. In the targeted GB-HOU trace,201/412 accepted completion pursuit lists contained duplicates. Those are lists, not claims that every duplicated defender was actually encountered before the play ended.

For a deep completion with separation>=0.5, the code reduces the list to one random defender. All ten such lists in the targeted sample selected a non-safety, including a WILL; the rule does not inspect whether two-high safety help remains. A reproduced81.6-yard completion against two_man had21.5 air yards and60.5 YAC, and faced only one CB despite two safeties in the coverage assignments. A cover_2 completion with a recorded safety helper similarly used a random CB alone for pursuit. Once the sampled list is beaten, the final chase is evaluated against that same list, so omitted safety help cannot intervene.

**Recommended fix:** build a unique pursuit group from the actual primary defender, coverage helper and remaining eligible defenders; preserve safety help according to shell/assignment, depth and separation. Exclude already beaten/ineligible defenders appropriately, and let relevant pursuit/speed/tackling ratings decide the remaining chase. Verify repeated-defender prevention and deep catches versus one-high/two-high, then compare YAC/explosive/scoring outcomes across seeds before changing any global coefficients. This is a structural recommendation, not proof that each historical long TD was invalid or that all deep catches must face two safeties.

### Remaining evidence needed / watch disposition

- **Rushing losses:** open discrepancy. Capture raw yards/contact/box in a future game from the exact played build, then compare to the copied log; current save reconstruction is not exact replay. No global loss-frequency change now.
- **Sacks:** no current global fix justified; retain team/role distribution and pressure-to-sack monitoring. Single-game no-sack outcomes remain possible.
- **Explosives:** concrete pursuit-selection correction recommended; global explosive frequency unproven. Preserve legitimate long touchdowns.
- Artifacts: `outputs/game-watch-investigation-20261002/` contains `fresh.json`, `saved.json`, `matchup.json`, diagnostic runners and `log-comparison.json`. Detailed raw outcomes and coverage/pursuit evidence are retained for a targeted follow-up.


## October 2: coverage-aware post-catch pursuit implemented

User approved the preceding pursuit recommendation. Source changes are isolated to `pass_pursuit.py`, the receiving pursuit integration/optional tackler attribution in `plays.py`, the browser module list, and focused tests. No global completion, sack, rushing, or break-tackle coefficients were adjusted.

- Pursuers are unique live player IDs from the actual rush/coverage complement. Blitzing/absent players cannot reappear. Actual primary/helper coverage is retained, and zone catch areas come from the existing zone model.
- Two-man sideline catches use the safety responsible for that half; seam catches use the middle landing area and can involve both halves. An opposite-half safety is not automatically added to a sideline catch. One-high and Cover0 remain distinct. Safeties already assigned to other man receivers are not treated as free help.
- A separated man defender trails the relevant deep support rather than being erased from recovery pursuit. Underneath catches retain a deeper support opportunity. This remains an assignment/side approximation, not coordinate-level tracking.
- Actual selected defenders' existing tackle/pursuit/speed/awareness grades resolve the chase. Completed passes retain pursuit IDs and the actual stopping defender, so tackle/forced-fumble credit and contact Hit Power no longer use an unrelated randomly chosen defender. Rushing attribution is unchanged. No available pursuer means no invented tackler or phantom stop.
- Verification:69 tests passed (12 new pursuit checks, coverage recording/rush selection, receiving touchdowns, modifier ordering, hit power, fourth-down routes, save/resume). Browser build passed with121 shipped modules, including the new helper. Integration should rebuild generated browser files from source.

Development comparisons identified two structural omissions in an early candidate: deeper support could be absent from short-catch pursuit, and separated primaries were deleted from recovery. Both were corrected before final validation; their earlier output files are development artifacts, not the shipped result. No coefficient search was performed.

Final validation used fresh seeds102041/102042 after the final seam-area correction,32 games with fresh rosters and32 independently loaded from the user's2028 Week7 save. Final artifacts: `pursuit-validation-fresh.json` and `pursuit-validation-saved.json` in `outputs/game-watch-investigation-20261002/`. The saved league was played atWeek8 with restored runner state, not replayed with historical user decisions. Other `pursuit-*` files in this folder document prior candidates.

| Final validation | Fresh rosters,32 games | Developed save,32 games |
| --- | ---: | ---: |
| Points/team | 26.56 | 25.00 |
| Yards after catch/completion | 5.94 | 5.25 |
| Net yards/dropback | 6.70 | 6.03 |
|40+ yard completions/attempts | 38/2311 (1.64%) | 27/2345 (1.15%) |
| Designed-run YPC | 4.61 | 4.58 |
| Sack rate, attempts+sacks denominator | 7.11% | 6.91% |

**Balance status: structural tests/build pass; full register NOT certified.** Earlier baseline32-game samples were25.11/24.89 points perteam and1.24%/0.99%40+ pass rates; final validation uses different seeds, so these differences are not clean causal estimates. Fresh-roster YAC/scoring remain elevated and warrant a dedicated calibration follow-up; the developed-save sample stays close to its prior yardage/scoring level. Long gains remain possible. Do not claim this fix alone has reduced league-wide explosive frequency or solved scoring. Preserve this concern in the running watchlist instead of applying an untested broad offense reduction.


## October 2: four-chat character, discipline and work-ethic balance audit

**Decision: retain the current character/work-ethic/discipline coefficients. No broad balance adjustment is justified by this comparison. Full-register certification is still not claimed.** One confirmed performance issue was corrected: deferred snap preparation no longer copies unselected reserve players' rating dictionaries. Sixteen paired full games preserved exact scores, logs, stat books and final RNG state; the isolated benchmark improved from 6.022s to 4.979s (17.3%).

### Gameplay and persistence

Changes (4) compared baseline c14c945 game/events/return enforcement with the completed character implementation, holding current practice/coaching preparation equal. Four fresh-league rounds cover all32teams once perround in each mode:64 baseline +64 new games. These are independent fresh-roster slices, not a continuous full season. Normal SeasonRunner preparation, availability and stat recording were exercised.

| Metric | Before | After |
| --- | ---: | ---: |
| Total points/game |54.016|53.516|
| Accepted flags/game |11.375|11.766|
| Designed-run YPC |4.678|4.669|
| Net yards/dropback |6.611|6.630|
| Completion percentage |64.065|64.121|
| Sack percentage |6.326|6.703|
| Interception percentage |2.344|2.028|

Paired total-scoring delta -0.5 has approximate95% margin4.90; accepted-flags delta+0.391 has margin1.059. This sample does not establish a broad gameplay shift. Zero invalid eleven-player selections, inactive offenders or penalty log/stat count/yard mismatches were found. Actual batch/live full logs and stat books matched; single-session midgame JSON save/replay/finish also matched. A2300-player legacy migration preserved input data, previous traits, XP, development and potential, with identical generated/migrated discipline and stable reload.

Before the copy optimization, production game-call time was23.652s/32.943s over64games (about+0.145s/game). The separate raw-game optimization benchmark is not directly subtractable from those timings. Browser responsiveness and longer-season runtime remain worth monitoring.

### Development and CPU decisions

This chat compared standard/balanced practice forecasts on three seeded32-team rosters,2114players each. League-wide XP changed -0.111%,+0.014%,-0.114%; team changes across96 observations ranged -2.142%..+2.085%.360 paired practice-only18week cohorts covered ten positions, four development tiers, three experience levels and work ethic15/50/85, spending every third week. Neutral work ethic preserved exact XP/growth/purchases/unspent balances. Low/high work ethic changed XP to0.86x/1.14x; average OVR growth was0.605/0.701/0.811 for low/neutral/high. Random upgrade choices mean higher XP is not a guarantee of higher OVR in every individual sample. Ceilings held. A66-player18week resolved-practice comparison preserved health, injuries and RNG state.31 additional cadence/practice/identity/development tests passed.

Changes (2) compared288 CPU draft boards:three classes of482prospects, all32teams and draft slots20/100/200, identical football reads and availability. Top choice changed7times(2.43%), each toward lower observed character cost and a previously second/third-ranked prospect. Average top-ten overlap9.861/10;24 paired actual CPU picks matched boards. Visits/boards preserved talent, potential, XP, traits and scouting RNG; save/load retained assessments.48 character/draft checks passed. These are decision snapshots, not full-draft or longitudinal calibration. Largest OVR difference7.2 was a cross-position QB versus edge comparison where roster/positional value had already placed the QB third; do not describe it as character overriding7.2 points between otherwise equivalent players.

### Follow-up watches — investigate, not automatic tuning

- Scoring and touchdown/field-goal drive rates exceeded targets in both versions. Wide win margins and low overtime also persist. They remain broader existing calibration questions.
- New sample additionally missed punt-drive percentage(29.576 versus29.9 minimum), negative-run percentage(6.809 versus7.04 minimum) and FG accuracy(89.058 versus88 maximum). Baseline missed other nearby thresholds, including drives, plays, injuries and kickoff touchbacks. Check more continuous-season evidence before attributing a threshold crossing to discipline or changing global coefficients.
- Monitor penalty mix and offender roles, net drive effects, simulation speed, long-term character-driven draft behavior, and whether club observations refine at a believable pace.
- Reproduction: audit_discipline_production.py, audit_work_ethic_balance.py, audit_character_draft.py. Evidence in parent rev/outputs: discipline-production-audit.json, discipline-copy-optimization.json, work-ethic-balance-20261002.json, character-draft-balance.json. Combined gameplay/practice suite passed144 checks before optimization; changes (4)'s198 checks and this chat's32 integration checks passed after optimization. Counts overlap and must not be summed as unique tests.
