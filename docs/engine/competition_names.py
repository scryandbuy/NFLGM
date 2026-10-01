"""Competition names and a one-time upgrade of older franchise snapshots."""
import re
from stadium_names import rename_venues, TEAM_NAMES

VERSION = 2
_LEGACY = re.compile(r'\b(?:AFC|NFC|Super[ -]?Bowl|SB MVP)\b', re.IGNORECASE)
_NAMES = {'afc': 'Continental', 'nfc': 'United',
          'superbowl': 'Championship Game', 'sbmvp': 'Championship Game MVP'}


def rename_text(text, home=None):
    text = _LEGACY.sub(lambda m: _NAMES[re.sub(r'[ -]', '', m.group().lower())], text)
    return rename_venues(text, home)


def migrate_save(data):
    """Rename conference keys, archived labels and inbox prose together.

    Round/award machine codes (SB and sb_mvp) stay stable. The recursive copy
    also covers live brackets and session caches without changing the input.
    """
    if data.get('competition_names_version', 0) >= VERSION:
        return data

    def walk(value, home=None):
        if isinstance(value, str):
            return rename_text(value, home)
        if isinstance(value, dict):
            home = next((value[k] for k in ('home_abbr', 'home', 'host', 'abbr')
                         if isinstance(value.get(k), str) and value[k] in TEAM_NAMES), home)
            return {rename_text(k, home) if isinstance(k, str) else k: walk(v, home)
                    for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v, home) for v in value]
        if isinstance(value, tuple):
            return tuple(walk(v, home) for v in value)
        return value

    renamed = walk(data)
    renamed['competition_names_version'] = VERSION
    return renamed
