"""A stable seed from names and ids. Python randomizes string hashes per process, so a generator seeded from
hash() gave a different read on every load: a prospect's tape, a coach's traits, a player's extension ask and the
noise on a trade value all reshuffled between sessions. crc32 of the text is the same everywhere."""
import zlib


def stable_seed(*parts):
    return zlib.crc32('|'.join(str(x) for x in parts).encode('utf-8'))
