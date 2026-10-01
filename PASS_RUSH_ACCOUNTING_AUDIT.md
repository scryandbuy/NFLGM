# Pass-rush accounting audit

Base: `0badfc6`. This change does not tune rush ratings, sack probabilities,
rotation or fatigue. `StatBook.record` is the single counter owner; EPA booking
no longer duplicates rush opportunities/wins. Sack-to-scramble conversion keeps
the already-resolved protection/rush metadata, without crediting a sack.

## Verification

`python -m unittest test_rush_accounting test_defensive_rush test_counter_contract_shape`

23 tests pass. A paired production-path probe used all 32 teams and seeds
93031/93032, 32 games per configuration, catalog coaches and actual TeamState:

```
python audit_pass_rush.py --baseline-ref 0badfc6 --seeds 93031 93032 --out baseline.json
python audit_pass_rush.py --seeds 93031 93032 --out candidate.json
```

The baseline flag replaces only game.py and advanced_stats.py from that ref.
Use a clean baseline checkout when comparing additional engine changes.

All paired scores, injury counts, defensive snaps and condition match. Both
configurations scored 26.625 points per team-game, with 40 injury events.
Sacks stayed at edge 61, interior 86, off-ball linebacker 27 (not including DBs).
Edge counters changed from 8,868 reps/804 wins/402 pressures to
4,466/408/408. The difference from exactly halving comes from restored scramble
metadata. Interior counters changed from 10,296/838/419 to 5,195/423/423.
Every player's final rush counters matched the non-nullified play log across
all 32 corrected games (zero discrepancies).

The export includes team/front/quality/player detail, defensive snap shares,
condition and injuries. Quality uses OVR bands, not depth rank; the harness
also exports depth rank. These fresh week-one games are a short regression
probe, not proof of season-long balance, fatigue or injury calibration.

## Old-save handling

Repair runs once on load with a persisted accounting version. A game's rush
rows must all match the duplicate signature (even reps, twice as many wins as
pressures), contain a positive-pressure row, and contain an impossible
reps-greater-than-defensive-plays row. Its season totals and regular-season
career copy must reconcile with the sum of saved games before applying deltas.
Correct, mixed, zero-only, ambiguous and incomplete records remain unchanged.
Current-week copies update only when they match a repaired game's old counters.
Postseason and regular-season totals stay separate. The active live book is
replayed by the new engine, not divided again.

On the supplied 2027 Week 9 save, 406 of 408 games met the signature; 9,519
player-game lines were repaired. Parsons' 2027 season and career changed from
348 reps/28 wins to 174/14. Pressures and sacks were untouched. A full Session
load/save/reload retained 174, and the RNG state stayed identical. The original
save file was not changed. Saved caches outside the stats/career/week books
contained no rush counters. Historical lost scramble reps cannot be recovered.

The two unclassified games were deliberately left alone. This is conservative
partial repair, not a claim that all historical counting is reconstructible.
