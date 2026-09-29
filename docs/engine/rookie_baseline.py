"""The same corrected seed ratings for the live league and future draft targets."""
import pandas as pd


def load_active_seed(path='league_seed_2026.csv', year=2026):
    seed = pd.read_csv(path, low_memory=False)
    seed = seed[seed.roster == 'active'].copy()
    return correct_rookie_ratings(seed, year)


def correct_rookie_ratings(seed, year):
    """Return a corrected copy; preserve the established roster-loading formula.

    Imputed rookies used veteran comparables in the source file. Match their
    draft-status cohort to measured rookies before using them as a baseline.
    Call once on source data, never on an already corrected live roster.
    """
    seed = seed.copy()
    if 'src_rating' not in seed.columns or 'draft_year' not in seed.columns:
        return seed
    cols = [c for c in seed if c.endswith('_rating') and c != 'src_rating']
    rookies = seed[(seed.draft_year == year) & (~seed.madden_position.isin(['K', 'P', 'LS']))]

    def key_of(value):
        return ('rd', int(value)) if pd.notna(value) else ('ud',)

    references = {}
    measured = rookies[rookies.src_rating == 'madden']
    for key, group in measured.groupby(measured.draft_round.map(key_of)):
        if len(group) >= 5:
            references[key] = group[cols].mean(numeric_only=True)
    imputed = rookies[rookies.src_rating == 'comparables']
    for key, group in imputed.groupby(imputed.draft_round.map(key_of)):
        target = references[key] if key in references else references.get(('ud',))
        if target is None:
            continue
        own = group[cols].mean(numeric_only=True)
        for attr in cols:
            if attr in target.index and pd.notna(own.get(attr)) and pd.notna(target.get(attr)):
                seed.loc[group.index, attr] = (target[attr] + 3.0 + .85 *
                                              (seed.loc[group.index, attr] - own[attr])).clip(30, 95)
    return seed
