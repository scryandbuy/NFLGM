# Attribute wiring integration — 2026-10-02

Base: `f6b7eb9`. Branch: `codex/attribute-wiring-20261002`.

## Changes

- `405e4dd`: run blocking. Actual selected FB/TE/WR and free offensive linemen receive unique support-block contests. Lead Block, Impact Block, and skill-position Run Block affect contact yards and recorded block reps. Carrier and already engaged blockers are excluded; neutral opposing grades add zero yards.
- `d69088f`: changes (2)'s Hit Power and defender Catching. Actual tackler/sacker/return-contact player influences fumbles. Selected interceptor's catching influences whether the original interception opportunity is caught; failed opportunities become incompletions. No global turnover base-rate change.
- `d93cca5`: changes (4)'s Throw on Run and consistent Play Action. Actual boot calls invoke moving-throw ability. Audibles/hot/screen/swing changes are checked before applying it. Both man and zone paths use the same situational ability multiplier, neutral at 70.
- Browser copies rebuilt, including the new `run_blocking.py` module in `build_web.py`.

## Verification

194 tests passed, including the three new suites, personnel selection, injuries/rotation, turnovers, return outcomes, coverage recording, game clock, penalties, and save/resume. See `attribute_tests.txt`.

Two fixed-seed samples ran on both baseline and changed engines: 32 exploratory games and 64 confirmation games. Each seed uses every team once with fresh rosters. These are game-level checks, not a multi-season franchise audit. Score reconstruction and unique blocker assertions passed throughout.

Confirmation (64 games per engine, identical seeds/matchups):

| Metric | Before | After |
| --- | ---: | ---: |
| Points per team | 25.49 | 25.20 |
| Completion percentage | 64.19 | 63.96 |
| Sack percentage | 7.07 | 6.55 |
| Interception percentage | 2.35 | 2.45 |
| Net yards per dropback | 6.62 | 6.27 |
| Rushing yards per carry | 4.74 | 4.76 |
| Negative run percentage | 7.69 | 7.98 |

Changed engine confirmation: 27/33 register targets within tolerance. Misses: points per team/total scoring, margins of 10+/17+, overtime, field-goal accuracy. The baseline also missed scoring (25.49 points/team). The initial 32-game changed sample was 28/33; its margin/OT/FG pattern was different. Do not describe this as a fully passing register or infer causal balance effects from individual changed game outcomes: new block/contact decisions change RNG consumption.

## Watch list

1. Scoring: high in both baseline and changed confirmation samples; no evidence this patch increased it in that comparison.
2. Victory margins and overtime: changed confirmation produced fewer blowouts and more overtime; needs broader evidence before tuning.
3. Field-goal accuracy: 89.55% in changed confirmation versus 87.13% baseline; no kicking formula changed.
4. Moving-throw coverage: 29 executed boots in 64 changed confirmation games; it is intentionally limited to called movement, not every pressured pass. Directional tests separately exercise both coverage paths.

## Integration precautions

Cherry-pick these scoped gameplay commits and the following handoff/browser commit. Then run `build_web.py` in the integration checkout to regenerate the manifest for the complete current tree.

This checkout preserves seven copied market/XP files from the integration branch's previously uncommitted state. They were not changed for this task and are excluded from our commits. The locally rebuilt manifest remains uncommitted because it includes those preserved snapshots. Do not copy market.py, xp.py, their browser copies, test_market_close_bonus.py, or test_kicker_xp_balance.py from this checkout. Main's newer market/XP work remains authoritative.

Evidence: `attribute_register_baseline.json`, `attribute_register_combined.json`, `attribute_register_confirmation_baseline.json`, `attribute_register_confirmation.json`. The latter pair uses seeds 100151–100154; the former pair uses 100141–100142. `audit_attribute_register.py` reproduces the changed-engine checks. Baseline confirmation loaded the five changed existing modules from `git show f6b7eb9:<module>.py` in a temporary import directory before importing the audit, leaving worktree sources intact.
