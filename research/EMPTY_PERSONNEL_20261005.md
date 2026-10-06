# Empty personnel preference

Isolated on 0b4c49c; no changes to the running six-season study.

## Football decision

An empty set defaults to four receivers and the best available receiving tight end. A fifth WR replaces that TE only with a substantial advantage on the same receiving-grade scale: catching25%, short routes20%, intermediate routes20%, deep routes10%, catch in traffic10%, speed10%, release5%. Blocking-based overall differences and hidden potential are not used.

Default threshold12 points, varying10–14 with coach aggression. This is a transparent design threshold, not an empirically fitted NFL cutoff. The reason to keep the TE is that a marginal fifth receiver does not warrant removing a comparable receiving option; the reason to replace him is a genuinely stronger route/catching matchup. No cap, contract or transaction decisions are performed by this selector.

Controlled player comparisons: TE80/WR570 retains TE; equal75 retains TE; TE75/WR582 retains TE; TE60/WR585 uses fiveWR. At TE70/WR581 the aggressive coach uses fiveWR while the conservative coach keeps TE. A low-overall TE with90 receiving attributes remains preferred to WR580. Unavailable players cannot justify the selection.

## Wiring

- Added actual01 personnel (0RB,1TE,4WR), retaining00 for fiveWR.
- Empty package calls and empty formations resolve the comparison. Defense receives actual composition; live and two-point paths refresh for unavailable players before defensive calls.
- The receiving TE is selected for this role; normal rest/rotation remains available.
- Both empty packages use five-man protection, preserving five eligible receiving options.
- Projected roster package weights use the same empty choice and formation probabilities. Existing explicit depth-chart package previews still show their literal selected personnel.
- Browser personnel label recognizes01 as Empty. Main owns browser engine packaging/integration.

## Verification and limits

57 targeted tests passed across empty composition, depth-chart/field consistency, personnel planning, TE roles, designed QB runs and scramble workload. The new tests cover ordinary/marginal/large gaps, coach differences, receiving versus overall grades, injuries, eleven unique players, actual call selection, planning weights and protection limits. JavaScript syntax and diff checks passed.

No new full-season run or league frequency calibration performed. Empty formation frequency inputs are preserved; the personnel in those formations changes, which can affect production and roster demand. The12-point threshold is an initial implementation of the requested large-gap exception and should remain visible in later balance review.
