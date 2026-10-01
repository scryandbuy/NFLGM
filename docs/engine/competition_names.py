"""Competition names and a one-time upgrade of older franchise snapshots."""
import re

VERSION = 1
_LEGACY = re.compile(r'\b(?:AFC|NFC|Super[ -]?Bowl|SB MVP)\b', re.IGNORECASE)
_NAMES = {'afc': 'Continental', 'nfc': 'United',
          'superbowl': 'Championship Game', 'sbmvp': 'Championship Game MVP'}


def rename_text(text):
    return _LEGACY.sub(lambda m: _NAMES[re.sub(r'[ -]', '', m.group().lower())], text)


def migrate_save(data):
    """Rename conference keys, archived labels and inbox prose together.

    Round/award machine codes (SB and sb_mvp) stay stable. The recursive copy
    also covers live brackets and session caches without changing the input.
    """
    if data.get('competition_names_version', 0) >= VERSION:
        return data

    def walk(value):
        if isinstance(value, str):
            return rename_text(value)
        if isinstance(value, dict):
            return {rename_text(k) if isinstance(k, str) else k: walk(v)
                    for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, tuple):
            return tuple(walk(v) for v in value)
        return value

    renamed = walk(data)
    renamed['competition_names_version'] = VERSION
    return renamed
