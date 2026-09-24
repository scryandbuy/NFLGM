"""
Minimum salary scale, frozen.

WHY THIS FILE EXISTS: rookie_and_minimum_scales.py derives these numbers from
a contracts parquet AT IMPORT TIME, which means the module cannot be imported
at all unless that file is sitting in the working directory. That is the same
pattern that kept standings_and_seeding uncallable for months, and it is why
several of the engines that were "built" had never once been run.

The derivation is still the source of truth and still lives in the original
module. What is copied here is its OUTPUT, so the runtime never depends on a
research artefact being present.

Minimums are stored as a SHARE OF THE CAP rather than as dollars, which is how
the league actually sets them - so they project forward on their own as the
cap grows instead of needing a new table every year.

Cross-checked against the published 2024 minimums:
    tier      derived    published
    rookie      0.799        0.795
    1 year      0.888        0.915
    2 years     0.956        0.985
    3 years     1.032        1.055
    4-6         1.138        1.125
    7+          1.284        1.210
"""

# share of the salary cap, median 2020-2026
MIN_PCT = {
    '0':   0.003224531611846047,
    '1':   0.0035826155050900548,
    '2':   0.0038566953797963977,
    '3':   0.0041624621594349145,
    '4-6': 0.004591321897073663,
    '7+':  0.00518238434163701,
}

TIERS = ['0', '1', '2', '3', '4-6', '7+']


def tier(credited_seasons):
    e = credited_seasons
    if e < 1: return '0'
    if e < 2: return '1'
    if e < 3: return '2'
    if e < 4: return '3'
    if e < 7: return '4-6'
    return '7+'


def minimum_salary(credited_seasons, cap):
    """The least a club may pay this man, in $M."""
    return round(MIN_PCT[tier(credited_seasons)] * cap, 3)


if __name__ == '__main__':
    print('2026 cap of 301.2:')
    for t, e in (('rookie', 0), ('1 yr', 1), ('2 yr', 2), ('3 yr', 3),
                 ('4-6', 5), ('7+', 9)):
        print(f'  {t:8s} ${minimum_salary(e, 301.2):.3f}M')
