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
