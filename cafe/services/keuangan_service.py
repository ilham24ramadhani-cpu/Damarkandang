from datetime import datetime
from cafe.database import get_db, get_client, supports_transactions
from cafe.services import jenis_keuangan_service
from cafe.utils.id_generator import generate_id_pengeluaran
from cafe.utils.response import now_iso


def _read_jenis(doc):
    return doc.get('jenis') or doc.get('kategori') or '-'


def list_pengeluaran(search='', jenis='', page=1, per_page=10, bulan=None):
    from cafe.utils.dates import bulan_query
    db = get_db()
    query = {}
    clauses = []
    if search:
        clauses.append({'$or': [
            {'keterangan': {'$regex': search, '$options': 'i'}},
            {'id_pengeluaran': {'$regex': search, '$options': 'i'}},
            {'jenis': {'$regex': search, '$options': 'i'}},
            {'kategori': {'$regex': search, '$options': 'i'}},
        ]})
    if jenis:
        clauses.append({'$or': [{'jenis': jenis}, {'kategori': jenis}]})
    if clauses:
        query = clauses[0] if len(clauses) == 1 else {'$and': clauses}
    if bulan:
        bq = bulan_query(bulan)
        if bq:
            if not query:
                query = bq
            elif '$and' in query:
                query['$and'].append(bq)
            else:
                query = {'$and': [query, bq]}

    skip = (page - 1) * per_page
    total = db.pengeluaran.count_documents(query)
    items = list(db.pengeluaran.find(query).sort('created_at', -1).skip(skip).limit(per_page))
    for item in items:
        if not item.get('jenis'):
            item['jenis'] = item.get('kategori')
    return items, total


def get_pengeluaran(id_pengeluaran):
    doc = get_db().pengeluaran.find_one({'id_pengeluaran': id_pengeluaran})
    if doc and not doc.get('jenis'):
        doc['jenis'] = doc.get('kategori')
    return doc


def create_pengeluaran_manual(data):
    jenis = (data.get('jenis') or data.get('kategori') or '').strip()
    jenis_keuangan_service.validate_jenis_pengeluaran_manual(jenis)

    nominal = int(round(float(data.get('nominal') or 0)))
    if nominal < 0:
        raise ValueError('Nominal tidak boleh negatif')
    if nominal == 0:
        raise ValueError('Nominal harus lebih dari 0')

    tanggal = (data.get('tanggal') or datetime.now().strftime('%Y-%m-%d')).strip()
    doc = {
        'id_pengeluaran': generate_id_pengeluaran(tanggal.replace('-', '')),
        'tanggal': tanggal,
        'jenis': jenis,
        'sumber': 'Manual',
        'id_referensi': '',
        'nominal': nominal,
        'keterangan': (data.get('keterangan') or '').strip(),
        'created_at': now_iso(),
    }
    get_db().pengeluaran.insert_one(doc)
    return doc


def create_pengeluaran_pembelian(tanggal, id_pembelian, nominal, keterangan, session=None):
    kwargs = {'session': session} if session else {}
    jenis = jenis_keuangan_service.JENIS_PENGELUARAN_OTOMATIS
    doc = {
        'id_pengeluaran': generate_id_pengeluaran(tanggal.replace('-', '')),
        'tanggal': tanggal,
        'jenis': jenis,
        'sumber': 'Pembelian Bahan',
        'id_referensi': id_pembelian,
        'nominal': int(nominal),
        'keterangan': keterangan,
        'created_at': now_iso(),
    }
    get_db().pengeluaran.insert_one(doc, **kwargs)
    return doc


def create_pengeluaran_bahan_masuk(tanggal, id_bahan, nominal, keterangan, session=None):
    """Pengeluaran otomatis saat pencatatan bahan masuk di Kelola Bahan."""
    kwargs = {'session': session} if session else {}
    jenis = jenis_keuangan_service.JENIS_PENGELUARAN_OTOMATIS
    doc = {
        'id_pengeluaran': generate_id_pengeluaran(tanggal.replace('-', '')),
        'tanggal': tanggal,
        'jenis': jenis,
        'sumber': 'Bahan Masuk',
        'id_referensi': id_bahan,
        'nominal': int(nominal),
        'keterangan': keterangan,
        'created_at': now_iso(),
    }
    get_db().pengeluaran.insert_one(doc, **kwargs)
    return doc


def total_pengeluaran_bahan_baku_bulan(bulan_yyyy_mm=None):
    from cafe.utils.dates import bulan_query
    bulan = bulan_yyyy_mm or datetime.now().strftime('%Y-%m')
    jenis = jenis_keuangan_service.JENIS_PENGELUARAN_OTOMATIS
    db = get_db()
    match = {
        '$or': [{'jenis': jenis}, {'kategori': jenis}],
    }
    match.update(bulan_query(bulan))
    pipeline = [
        {'$match': match},
        {'$group': {'_id': None, 'total': {'$sum': '$nominal'}}},
    ]
    result = list(db.pengeluaran.aggregate(pipeline))
    return int(result[0]['total']) if result else 0


def run_in_transaction(callback):
    """Jalankan callback(session) dalam transaksi MongoDB jika didukung."""
    client = get_client()
    if client and supports_transactions():
        with client.start_session() as session:
            with session.start_transaction():
                result = callback(session)
                return result

    db = get_db()
    inserts = []

    class RollbackTracker:
        def track_insert(self, collection, doc_id_field, doc_id):
            inserts.append((collection, doc_id_field, doc_id))

    tracker = RollbackTracker()
    try:
        result = callback(None, tracker)
        return result
    except Exception:
        for collection, field, doc_id in reversed(inserts):
            db[collection].delete_one({field: doc_id})
        raise
