"""MongoDB helpers for cafe module."""

_db = None
_client = None
_supports_tx = None


def init_db(db, client=None):
    global _db, _client, _supports_tx
    _db = db
    _client = client
    _supports_tx = None


def get_db():
    if _db is None:
        raise RuntimeError('Database belum diinisialisasi. Panggil init_db() terlebih dahulu.')
    return _db


def get_client():
    return _client


def supports_transactions():
    """Cache hasil hello agar tidak round-trip ke MongoDB di setiap write."""
    global _supports_tx
    if _supports_tx is not None:
        return _supports_tx
    client = get_client()
    if client is None:
        _supports_tx = False
        return False
    try:
        info = client.admin.command('hello')
        _supports_tx = bool(info.get('setName') or info.get('msg') == 'isdbgrid')
    except Exception:
        _supports_tx = False
    return _supports_tx
