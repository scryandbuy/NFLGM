"""Generic venue labels, shared by every page and championship host.

Legacy names exist only as input aliases for old-save migration.
"""
import re

TEAM_NAMES = {'ARI': 'Arizona',
 'ATL': 'Atlanta',
 'BAL': 'Baltimore',
 'BUF': 'Buffalo',
 'CAR': 'Carolina',
 'CHI': 'Chicago',
 'CIN': 'Cincinnati',
 'CLE': 'Cleveland',
 'DAL': 'Dallas',
 'DEN': 'Denver',
 'DET': 'Detroit',
 'GB': 'Green Bay',
 'HOU': 'Houston',
 'IND': 'Indianapolis',
 'JAX': 'Jacksonville',
 'KC': 'Kansas City',
 'LV': 'Las Vegas',
 'LAC': 'California',
 'LA': 'Los Angeles',
 'MIA': 'Miami',
 'MIN': 'Minnesota',
 'NE': 'New England',
 'NO': 'New Orleans',
 'NYG': 'New York',
 'NYJ': 'New Jersey',
 'PHI': 'Philadelphia',
 'PIT': 'Pittsburgh',
 'SF': 'San Francisco',
 'SEA': 'Seattle',
 'TB': 'Tampa Bay',
 'TEN': 'Tennessee',
 'WAS': 'Washington'}
STADIUM = {abbr: name + " Stadium" for abbr, name in TEAM_NAMES.items()}

LEGACY_VENUES = {'State Farm Stadium': 'ARI',
 'Mercedes-Benz Stadium': 'ATL',
 'M&T Bank Stadium': 'BAL',
 'Highmark Stadium': 'BUF',
 'Bank of America Stadium': 'CAR',
 'Soldier Field': 'CHI',
 'Paycor Stadium': 'CIN',
 'Huntington Bank Field': 'CLE',
 'AT&T Stadium': 'DAL',
 'Empower Field': 'DEN',
 'Ford Field': 'DET',
 'Lambeau Field': 'GB',
 'NRG Stadium': 'HOU',
 'Lucas Oil Stadium': 'IND',
 'EverBank Stadium': 'JAX',
 'Arrowhead Stadium': 'KC',
 'Allegiant Stadium': 'LV',
 'SoFi Stadium': 'LA',
 'Hard Rock Stadium': 'MIA',
 'U.S. Bank Stadium': 'MIN',
 'Gillette Stadium': 'NE',
 'Caesars Superdome': 'NO',
 'MetLife Stadium': 'NYG',
 'Lincoln Financial Field': 'PHI',
 'Acrisure Stadium': 'PIT',
 "Levi's Stadium": 'SF',
 'Lumen Field': 'SEA',
 'Raymond James Stadium': 'TB',
 'Nissan Stadium': 'TEN',
 'Northwest Stadium': 'WAS',
 'Empower Field at Mile High': 'DEN',
 'GEHA Field at Arrowhead Stadium': 'KC',
 'Levi’s Stadium': 'SF',
 'US Bank Stadium': 'MIN',
 'M&amp;T Bank Stadium': 'BAL',
 'AT&amp;T Stadium': 'DAL'}
_PATTERN = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(x) for x in sorted(LEGACY_VENUES, key=len, reverse=True)) + r")(?!\w)", re.IGNORECASE)
_LOOKUP = {name.casefold(): team for name, team in LEGACY_VENUES.items()}


def rename_venues(text, home=None):
    """Shared legacy venues use the recorded home club when available."""
    def replace(match):
        team = _LOOKUP[match.group().casefold()]
        shared = ('LA', 'LAC') if team == 'LA' else ('NYG', 'NYJ') if team == 'NYG' else ()
        if home in shared:
            team = home
        elif shared:
            # Older prose may have no structured home field. Honor explicit
            # host wording; otherwise retain the venue's generic city label.
            for candidate in shared:
                if re.search(r'\bat\s+(?:' + re.escape(TEAM_NAMES[candidate]) + '|' + candidate + r')\b', text, re.I):
                    team = candidate
                    break
        return STADIUM[team]
    return _PATTERN.sub(replace, text)
