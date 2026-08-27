"""Cache memori berumur pendek untuk query baca yang sering diulang."""

import time

_STORE = {}


def cached(key, ttl_seconds, factory):
    now = time.monotonic()
    hit = _STORE.get(key)
    if hit and hit[0] > now:
        return hit[1]
    value = factory()
    _STORE[key] = (now + max(1, int(ttl_seconds)), value)
    return value


def invalidate(prefix=''):
    if not prefix:
        _STORE.clear()
        return
    for key in [k for k in _STORE if str(k).startswith(prefix)]:
        _STORE.pop(key, None)
