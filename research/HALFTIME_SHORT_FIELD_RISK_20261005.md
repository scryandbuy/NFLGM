# Halftime short-field risk

User's GB–SF log: GB leads17–0, starts own12 with31seconds, later calls timeout at19seconds at own17 and throws an interception. No save/replay seed supplied. Controlled old-code scenario at own17,25seconds,+17, modest passing advantage and existing hurry mode reproduces attacking+offensive timeout. This is evidence of a planning weakness, not an exact replay.

## Correction

- End-zone scoring probability decays beyond a quarterback's estimated throwing reach instead of retaining a2–3% floor at any distance. Reach is48+20×normalized throw-power yards; the tail decays over12yards. These are disclosed planning approximations, not measured throw-distance calibration.
- Before halftime, evaluate the opponent's short field after a possible turnover, using resulting field position, remaining time and opponent kicker. Ordinary-play turnover planning share is min(PLAY_BAD,.025); the existing shot interception estimate is retained. These change decision estimates, not actual interception/fumble probabilities.
- Charge both hurry and bleed plans for that exposure. Retain separate existing possession costs after scoring/punting. Final minimum-value decision uses net value, not the unadjusted scoring estimate.
- A rejected attack explicitly clears hurry mode. Subsequent timeout choice follows protective intent.

Football motivation: tiny scoring chances from deep territory should not outweigh giving the opponent an immediate kick. Reasons to attack remain: reachable field position, enough time, favorable personnel and aggressive coaching. No universal kneel mandate; live ball-protection runs remain available when opponent timeouts prevent ending the half. No roster/contract/GM transaction changes.

## Evidence

35 targeted tests passed, including five new tests.27 deep-territory cases (three spots/times × three coach aggression settings × three matchup advantages) now protect and retain offensive timeouts. Near scoring range the offense still attacks and takes timeout. Stronger arms retain better distant-shot prospects. Live and batch paths protect the ball with opposing timeouts remaining. Existing aggressive-final-shot versus conservative-restraint cases still pass, as do quick-play/field-goal, sack timing and late timeout tests.

No new season simulation, browser rebuild or deployment. Isolated atop0b4c49c for main integration. Planning constants and aggregate scoring impact remain balance questions; the observed interception itself is not treated as proof of a bad random outcome.
