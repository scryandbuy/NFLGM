# Scramble contact follow-up — 2026-10-05

## Observed gap and football motivation

The resolver supplied a terminal scramble distance. A scoring scramble had no evidence of a defender meeting the QB before the plane, so the shared goal-line fumble resolver correctly treated it as terminal. This was a code-path gap, not proof of an incorrect fumble in a saved game.

The new sequence records an on-field pursuer and first contact short of the goal. The QB may break the tackle and continue; the existing fumble handler can interrupt that candidate result at the earlier contact. An untouched crossing remains terminal. A lineman can be the pursuer, especially near the pocket. Safe slides/exits must precede first contact and cannot retain the subsequent broken-tackle burst.

The reason against this particular model is that the original distance distribution represented a completed scramble. Reinterpreting it as first contact and adding a burst increases total production. This is an explicit additive model, not a fitted reconstruction of tracking data. Coaching differences in risk and safe endings remain in qb_contact; no roster or GM decision changes.

## Implementation

- events.py: on-field role/pursuit-weighted defender; break-tackle/strength/elusiveness versus tackle/pursuit contest; bounded continuation distance; actual contact metadata.
- game.py: sack escapes retain resolver defender attribution instead of replacing it.
- qb_contact.py: avoid-contact decisions stop before first contact and clear the canceled contact/broken-tackle evidence.
- No changes to global fumble rates, scramble frequency, roster logic, awards or scoring balance knobs.
- Based on combined source 42e597c. Main owns browser packaging and subsequent integration.

## Controlled evidence

92 focused tests passed: new scramble contact tests plus QB contact, contact integration, escape workload, goal-line fumbles and defensive returns.

The eight new tests cover broken and unbroken contact; untouched scores without contact/fumble draws; stronger versus weaker individual QB attributes; on-field defender selection and stable ordering; full-drive touchback, defensive recovery and own recovery; rushing/TD/forced-fumble statistics and narration; and safe endings before contact.

Paired audit: 5,000 identical initial seeds per QB/field-position cell, 30,000 opportunities total. Neutral defenders and either neutral QB attributes or a strong runner (90 speed/acceleration/agility/break tackle, 85 strength). This isolates the resolver before safe-ending choices, fumbles, penalties and play selection.

| QB | Yards to goal | Mean yards before → after | TD opportunities before → after |
|---|---:|---:|---:|
| Neutral | 3 | 2.591 → 2.628 | 3,557 → 3,661 |
| Neutral | 10 | 5.651 → 5.836 | 1,166 → 1,234 |
| Neutral | 50 | 6.972 → 7.238 | 1 → 1 |
| Strong runner | 3 | 2.658 → 2.738 | 3,765 → 4,001 |
| Strong runner | 10 | 6.160 → 6.595 | 1,502 → 1,690 |
| Strong runner | 50 | 8.156 → 8.869 | 2 → 3 |

All baseline untouched scoring outcomes retained their distance and touchdown result. In midfield, 618/4,999 neutral contact opportunities and 1,453/4,998 strong-runner contacts broke a tackle. The front supplied 1,288 and 1,168 first-contact defenders respectively, showing that linemen remain involved. Raw results: scramble_contact_opportunities_20261005.json; reproducible with audit_scramble_contact.py.

## Unresolved balance and modeling limits

- Break probability and burst distribution are stated model assumptions, not NFL-calibrated parameters. The strong runner's roughly 0.71 extra midfield yards per opportunity and increased goal-line scoring chance require the combined study. No separate season study or compensating rate tuning was performed.
- Contact location derives from a distance distribution, not defender coordinates. The second pursuer also uses role/proximity weights; there is no full pursuit path or repeated tackle-break chain.
- Existing loose-ball bounce/recovery assumptions remain unchanged and unresolved as documented in GOAL_LINE_FUMBLE_REVIEW_20261005.md. This follow-up supersedes only that report's missing scramble-contact caveat.
- Tests establish sequencing and accounting, not league-level realism or browser deployment. Main should retain both action/restraint scenarios and these production deltas in its single combined study.
