"""Pressure credit shared by statistics and coaching evidence.

A rush must consume at least 12.5% of the planned throwing window. This is
an explicit reporting threshold, not a change to pass resolution. Actual
sacks and pressure-forced throwaways/escapes retain their causal credit.
"""
VERSION = 3
MIN_SEVERITY = .125


def credited_rushers(out, release, arrivals, cutoff):
    release = max(float(release), .001)
    forced = out.get('throwaway') or out.get('scramble_kind') == 'escape'
    first = min((float(t) for pid, t in arrivals if pid), default=float('inf'))
    return {pid for pid, arrival in arrivals if pid and arrival <= cutoff and
            ((release - arrival) / release >= MIN_SEVERITY or
             (forced and arrival == first))}


def disrupted(play):
    if play.get('type') == 'sack':
        return True
    if play.get('pressure_version') == VERSION:
        return bool(play.get('pressured'))
    # Old logs with timing can be reclassified. A legacy boolean alone cannot
    # distinguish a marginal arrival from disruption; do not invent evidence.
    if 'pressure_arrivals' in play and 'pressure_release' in play:
        return bool(credited_rushers(play, play['pressure_release'],
            play['pressure_arrivals'], play.get('pressure_credit_end', play['pressure_release'])))
    return False
