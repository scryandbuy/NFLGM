# Goal-line fumble review — October 5, 2026

## Observed source defects

The source skipped every touchdown candidate before fumble resolution. That protected a scoring run even when the pursuit model recorded contact before the goal line. Retained fumbles did not name a recovering player or model loose-ball displacement. Sack safety yardage was capped after the stat-book boundary, permitting inconsistent intermediate evidence.

This is a source audit and controlled reproduction, not a replay of a newly supplied saved game. Changes (3)'s NYJ–DET seed 91310 observation motivated the focused sack-at-own-two reproduction; this change does not attribute that preexisting defect to rotation.

## Football rationale and scope

Possession crossing the plane is a score immediately. A catch made in the end zone cannot become a subsequent live fumble. But a hit before the plane can interrupt a candidate score. We retain the location/defender from existing pursuit contests and the sneak's interior engagement, without inventing a post-plane contact or changing global fumble rates.

The loose-ball model separates the possession-loss spot, recovery/boundary spot, final ball position, original-category yards, and scoring player. Forward OOB fumbles cannot advance the offense; a loose ball through the opponent's end zone is a touchback. Own-end-zone boundary/recovery outcomes can be safeties. Fourth down, late-half and try teammate recoveries cannot advance a forward fumble. Own recoveries retain their original rushing/receiving credit; backward recoveries reduce that credit. Teammate recovery scores have separate `off_fum_rec_td` credit rather than a phantom passing/rushing touchdown. A boundary touchback credits no recovery to a defender.

Fumble OOB restarts on the referee's signal, unlike the late-half runner exception. Fractional short-of-goal retained fumbles use exact adjudicated ball position; they cannot round into touchdowns or receive scoring clock treatment. Ticker/replay/live-box data distinguish original-carrier production and recovery scores. Two-point attempts use the restricted recovery rule and a defensive return is worth two points, not six. Try fumbles remain outside ordinary player statistics.

These are play rules, not GM decisions. No roster, contract, retention, trade or hidden-potential input changes. No mandatory coaching choice or GM personality is imposed.

## Evidence

- 128 focused Python tests passed across goal-line, defensive returns/UI, QB-contact integration, clock decisions, penalty yardage, QB escape workload, defensive rush and personnel.
- The 17 new focused goal-line tests cover action/restraint: candidate score interrupted before plane; terminal scores preserved; own and teammate recovery credit; backward recoveries; boundary turnover without a recoverer; fractional clock/spot; OOB ready clock; safety cap; try restriction and defensive try return.
- Four executable browser replay-scoring checks passed; `node --check docs/app.js` passed. No visual browser session was used.
- `audit_goal_line_fumbles.py` generated `goal_line_opportunities_20261005.json`. Each of four scenarios uses 10,000 seeded opportunities with neutral player ratings. Contact at opponent one: 159 fumbles, 56 possession losses, 14 touchbacks, 12 teammate recovery TDs; 9,875 of 10,000 candidate scores still scored. The same stopped-at-one opportunity produces the same loose-ball counts, with 34 recovered-ball scores. Untouched scores and end-zone catches produce zero fumbles. This is an opportunity test, not a real schedule or estimated league incidence.
- Awards source was reviewed and its 54 focused tests rerun alongside this source; evidence is in `OFFENSIVE_AWARD_REVIEW_20261005.md`.
- Existing unclosed-file ResourceWarnings appeared in data loaders; tests completed successfully.

## Rules and statistical sources

- [2026 NFL playing rules](https://static.www.nfl.com/image/upload/fl_attachment/league/tqivdkzt9mu6wdgsh1ku.pdf): Rule 8, Section 7 for loose-ball recovery/boundaries; Rule 4-3-2(f) for fumble OOB clock; touchdown/dead-ball rules.
- [NFL Guide for Statisticians](https://www.nflgsis.com/gsis/documentation/stadiumguides/guide_for_statisticians.pdf): Fumbles, rushing plays, receptions and recovery credit; forced-fumble tackle attribution.

## Unresolved limits — combined study must retain these

- Bounce displacement (normal SD 1.5 yards, bounded at four yards) and 6% loose-ball boundary share are explicit first-model assumptions, not fitted NFL measurements. Displacement is limited to fumbles within five yards of either goal; ordinary field recoveries keep their existing location. The engine has no lateral/pylon geometry.
- Recovery-player weights favor the carrier but use on-field proximity approximations. Offensive recoveries represent falling on the ball, without a new offensive return-run model or a second fumble.
- Scramble resolution still supplies terminal distance without a pre-goal contact location. Scoring scrambles without recorded contact remain terminal, as do untouched runs. This patch deliberately does not manufacture a pre-plane hit or claim this existing limitation is solved.
- Statistical integer spotting, advanced contact geometry, multiple changes of possession/impetus, and later loose-ball fouls are not newly modeled. Existing general penalty enforcement remains the basis.
- The added recovery TD field is saved in the player book; a dedicated historical recovery-stat column is not introduced.
- No combined register, multi-season balance certification, browser package rebuild or deployment was performed here. Main owns that gate and must preserve Changes (3)'s QB-contact/rotation source.
