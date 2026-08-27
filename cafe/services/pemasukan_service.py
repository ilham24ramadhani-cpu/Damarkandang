from datetime import datetime
from cafe.database import get_db, get_client, supports_transactions
from cafe.services import jenis_keuangan_service
from cafe.utils.id_generator import generate_id_pemasukan
from cafe.utils.response import now_iso


def list_pemasukan(search='', page=1, per_page=10, bulan=None):
    from cafe.utils.dates import bulan_query
    db = get_db()
    query = {}
    if search:
        query['$or'] = [
            {'keterangan': {'$regex': search, '$options': 'i'}},
            {'id_pemasukan': {'$regex': search, '$options': 'i'}},
            {'jenis': {'$regex': search, '$options': 'i'}},
        ]
    if bulan:
        query.update(bulan_query(bulan))

    skip = (page - 1) * per_page
    total = db.pemasukan.count_documents(query)
    items = list(db.pemasukan.find(query).sort('created_at', -1).skip(skip).limit(per_page))
    for item in items:
        if not item.get('jenis'):
            item['jenis'] = 'Penjualan' if (item.get('sumber') or '').lower() in ('kasir', 'pemesanan', 'penjualan') else '-'
    return items, total


def create_pemasukan_kasir(tanggal, id_transaksi, nominal, keterangan, session=None):
    kwargs = {'session': session} if session else {}
    doc = {
        'id_pemasukan': generate_id_pemasukan(tanggal.replace('-', '')),
        'tanggal': tanggal,
        'jenis': jenis_keuangan_service.JENIS_PEMASUKAN_OTOMATIS,
        'sumber': 'Penjualan',
        'id_referensi': id_transaksi,
        'nominal': int(nominal),
        'keterangan': keterangan,
        'created_at': now_iso(),
    }
    get_db().pemasukan.insert_one(doc, **kwargs)
    return doc


def update_pemasukan_kasir(id_pemasukan, tanggal, nominal, keterangan, session=None):
    if not id_pemasukan:
        return None
    kwargs = {'session': session} if session else {}
    result = get_db().pemasukan.update_one(
        {'id_pemasukan': id_pemasukan},
        {'$set': {
            'tanggal': tanggal,
            'nominal': int(nominal),
            'keterangan': keterangan,
            'updated_at': now_iso(),
        }},
        **kwargs,
    )
    if result.matched_count:
        return get_db().pemasukan.find_one({'id_pemasukan': id_pemasukan}, **kwargs)
    return None


def delete_pemasukan_by_referensi(id_referensi, id_pemasukan=None, session=None):
    kwargs = {'session': session} if session else {}
    db = get_db()
    if id_pemasukan:
        db.pemasukan.delete_one({'id_pemasukan': id_pemasukan}, **kwargs)
    if id_referensi:
        db.pemasukan.delete_many({'id_referensi': id_referensi}, **kwargs)


def create_pemasukan_manual(data):
    jenis = (data.get('jenis') or '').strip()
    jenis_keuangan_service.validate_jenis_pemasukan_manual(jenis)

    nominal = int(round(float(data.get('nominal') or 0)))
    if nominal <= 0:
        raise ValueError('Nominal harus lebih dari 0')

    tanggal = (data.get('tanggal') or datetime.now().strftime('%Y-%m-%d')).strip()
    doc = {
        'id_pemasukan': generate_id_pemasukan(tanggal.replace('-', '')),
        'tanggal': tanggal,
        'jenis': jenis,
        'sumber': 'Manual',
        'id_referensi': '',
        'nominal': nominal,
        'keterangan': (data.get('keterangan') or '').strip(),
        'created_at': now_iso(),
    }
    get_db().pemasukan.insert_one(doc)
    return doc


def total_pemasukan_bulan(bulan_yyyy_mm=None):
    from cafe.utils.dates import bulan_query
    bulan = bulan_yyyy_mm or datetime.now().strftime('%Y-%m')
    db = get_db()
    pipeline = [
        {'$match': bulan_query(bulan)},
        {'$group': {'_id': None, 'total': {'$sum': '$nominal'}}},
    ]
    result = list(db.pemasukan.aggregate(pipeline))
    return int(result[0]['total']) if result else 0


def run_in_transaction(callback):
    client = get_client()
    if client and supports_transactions():
        with client.start_session() as session:
            with session.start_transaction():
                return callback(session)

    db = get_db()
    inserts = []

    class RollbackTracker:
        def track_insert(self, collection, field, doc_id):
            inserts.append((collection, field, doc_id))

    tracker = RollbackTracker()
    try:
        return callback(None, tracker)
    except Exception:
        for collection, field, doc_id in reversed(inserts):
            db[collection].delete_one({field: doc_id})
        raise
