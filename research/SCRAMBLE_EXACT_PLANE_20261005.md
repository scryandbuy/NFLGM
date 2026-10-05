# Exact scramble goal plane — isolated follow-up

Base: frozen 0b4c49c. This change is not included in the running coordinated study.

## Observed

Seed 93031, 2026 Week 5 NYG at WAS: P2575 scored from 16.1 yards but retained first-contact distance 16.859. Week 7 CIN at BAL: P0210 scored from 3.5 with first contact 3.644. The drive supplies ceil(field distance) to legacy play resolution. Scramble pursuit could therefore continue into the end zone.

The scoring normalizer runs before the fumble handler. A controlled full drive with actual distance 3.5, resolver distance 4, contact at 3.7 and a forced lost-fumble result still scored seven points, credited 3.5 rushing yards and recorded zero fumbles. No erased touchdown or incorrect possession was demonstrated. The confirmed defects are impossible contact/broken-tackle evidence and unnecessary random draws.

## Narrow correction

The drive puts its actual distance in the offensive call as scramble_goal_distance. The voluntary scramble resolver uses that value, falling back to its existing argument for standalone callers. A sack escape receives the actual distance directly. Other play-selection distance inputs retain their existing behavior.

Football motivation: crossing the actual plane ends the carry. Contact before that plane remains eligible to stop the runner, be broken, or cause a fumble. No coaching judgment or GM preferences change. Avoiding extra draws necessarily changes later seeded random sequences; it does not guarantee identical future games.

## Controlled evidence

83 tests passed across exact-plane, scramble-contact, QB-contact integration, escape workload, goal-line fumbles and defensive returns. Four new tests establish:

- Crossings from 3.5, 16.1 and 0.4 yards return touchdowns with no contact/escape random draws or broken-tackle metadata.
- Contact at 3.2 with 3.5 to score remains real and can be broken for a touchdown.
- Actual voluntary pass resolution passes the exact distance, with legacy fallback covered.
- Full-drive sack escape passes the exact distance and preserves touchdown points, rushing credit, and zero post-plane fumbles. The same fixture verifies the drive populates the voluntary-path call field.

Existing goal-line tests retain contact-fumble/recovery/scorebook coverage. Diff whitespace check passed. No source in the frozen study was modified, no new long simulation was run, and no browser rebuild was performed here. Main owns integration after the study.
