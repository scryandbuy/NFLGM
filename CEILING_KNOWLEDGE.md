# Ceiling knowledge

Implemented October 2, 2026, from combined base `424dba9`.

## Rules

- Actual potential and the existing XP ceiling lock are unchanged.
- Under 28, each completed professional season and each 500 recorded career
  snaps tighten the estimate by one at each boundary, toward the true ceiling.
- Regular-season history and league totals are the same evidence, counted once.
  Postseason snaps count too. Missing historical snaps are not invented.
- Estimates always contain the true ceiling and retain at least two points of
  width until confirmed. If only one point of tightening is left, the less
  accurate boundary moves first.
- The ceiling is confirmed at the 28th birthday (at the next calendar stop),
  or earlier at the existing developmental cap threshold. Knowledge persists
  through regression and position changes. A paid unlock raises a known ceiling.
- Existing under-28 players without a range receive a deterministic asymmetric
  estimate. Existing ranges, ratings, actual potential, XP, and purchases remain
  intact; knowledge metadata is separate in the saved XP ledger.
- College scouting retains its separate prospect estimates. CPU growth-credit
  reads use established professional ceiling knowledge with unchanged formulas.
- Player card, roster ratings, progression, and development share the same read.
  Development explains temporary position-learning penalties and calculates next
  point gains against underlying ratings, not the temporarily reduced overall.

## Verification

- 68 targeted Python tests passed: ceiling knowledge/visibility/spending,
  development value, package needs, draft planning, and draft redundancy.
- Development panel and ceiling notification JavaScript checks passed; syntax
  and browser engine import registration passed.
- Read-only migration of `nflgm-2028-week-9.json`: all 3,821 players preserved
  ratings, actual potential, existing ranges, XP, purchase ledgers, and RNG.
- Austin screenshot reproduction: underlying 73.06, displayed 70.66 (71),
  true ceiling 73.1; now displays confirmed 73 and explains learning RT.
- Expanded 70-test lifecycle/character/practice run: 67 passed. The three
  failures also reproduce with unchanged base sources: two birthday tests use
  old offseason date assumptions; one prospect-card fixture lacks session.stop.
  These were reported to the main integration chat. No calendar/scouting behavior
  was changed to accommodate those tests.

The main integration chat owns the browser build and release. This source change
does not itself update the published GitHub site.
