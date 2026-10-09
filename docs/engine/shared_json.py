"""Decode a franchise with shared immutable values and ordinary mutable containers.

The pools live only for this decode. Never intern into a process-wide registry:
starting another franchise must release the previous franchise's unique values.
Float keys retain their binary representation, including the sign of zero.
"""
import json
import math


class _Values:
    __slots__ = ('strings', 'floats')

    def __init__(self):
        self.strings = {}
        self.floats = {}

    def value(self, value):
        if isinstance(value, str):
            return self.strings.setdefault(value, value)
        if isinstance(value, float) and math.isfinite(value):
            # Finite nonzero floats compare equal exactly when their bits do.
            # Separate signed-zero keys; avoid allocating a bytes key for every
            # rating and statistic decoded from a long-running franchise.
            key = ('-0' if math.copysign(1., value) < 0 else '+0') if value == 0 else value
            return self.floats.setdefault(key, value)
        if isinstance(value, list):
            for index, child in enumerate(value):
                value[index] = self.value(child)
        # Dicts have already passed through object() bottom-up. Do not visit
        # their children again or large nested saves become quadratic work.
        return value

    def object(self, record):
        for key, value in record.items():
            record[key] = self.value(value)
        return record


def loads(text):
    values = _Values()
    return values.value(json.loads(text, object_hook=values.object))


def load(stream):
    values = _Values()
    return values.value(json.load(stream, object_hook=values.object))
