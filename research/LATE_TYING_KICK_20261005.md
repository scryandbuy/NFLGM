# Late tying kick and halftime exchange

## Observed and reproduced
Chicago declined a 35-yard tying kick on fourth-and-7 with 60 seconds left. The decision model favored kicking (.358 win probability versus .201 going), but an urgency floor overrode that advantage. Before the change, 328 of 1,000 seeded decisions went for it at each tested coach aggression level.

Green Bay completed a short third-down pass from the Chicago 22 with 18 seconds before halftime and no timeouts. The execution charged a regular huddle. The fourth-down planner also incorrectly credited a failed passing attempt with a subsequent kick.

## Changes
Remove the urgency floor when a viable kick ties or takes the lead. When the model favors kicking in the final two minutes, scale conversion appetite by that advantage; coaches retain different preferences and rare aggressive choices. A kick cannot solve a four-point deficit, and poor kicking ability still affects the comparison.

Do not credit a failed fourth-down shot with a subsequent field goal. Allow a hurried ten-second kicking-unit exchange after a third-down in-bounds play when the halftime planner selects a kick and sufficient actual time remains. Preserve actual live-play duration. Completed kicks cannot move the clock beyond the period boundary; their outcomes still count.

## Controlled evidence
40 targeted tests pass. At normal kicker quality, the Chicago scenario now goes for it 2, 3, and 6 times per 1,000 seeds for conservative, average, and aggressive coaches. At average aggression, weaker kicker quality produces 6 attempts, stronger quality 2. Needing a touchdown remains aggressive.

The halftime completion reaches a field-goal snap with two seconds remaining in both live and batch paths. A twelve-second live play leaves insufficient exchange time and does not create a kick. Existing quick-play, timeout, halftime risk, and clock regressions pass.

## Limits
The ten-second exchange and .06 decision sensitivity are modeling choices, not empirically fitted league rates. These controlled scenarios establish the identified fixes, not full-season coaching balance. No production browser build was made here. Depends on 303e649; main owns integration.
