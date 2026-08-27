from app.database import get_db
from app.utils.id_generator import generate_id_riwayat_stok
from app.utils.response import now_iso


def list_riwayat(id_bahan='', tipe='', page=1, per_page=20):
    db = get_db()
    query = {}
    if id_bahan:
        query['id_bahan'] = id_bahan
    if tipe:
        query['tipe'] = tipe.upper()

    skip = (page - 1) * per_page
    total = db.riwayat_stok.count_documents(query)
    items = list(db.riwayat_stok.find(query).sort('created_at', -1).skip(skip).limit(per_page))
    return items, total


def create_riwayat(data, session=None):
    kwargs = {'session': session} if session else {}
    doc = {
        'id_riwayat': generate_id_riwayat_stok((data.get('tanggal') or '').replace('-', '')),
        'id_bahan': data['id_bahan'],
        'nama_bahan': data.get('nama_bahan', ''),
        'tanggal': data.get('tanggal') or now_iso()[:10],
        'tipe': data['tipe'].upper(),
        'jumlah_gram': int(data['jumlah_gram']),
        'stok_sebelum': int(data['stok_sebelum']),
        'stok_sesudah': int(data['stok_sesudah']),
        'id_referensi': data.get('id_referensi', ''),
        'keterangan': data.get('keterangan', ''),
        'created_at': now_iso(),
    }
    get_db().riwayat_stok.insert_one(doc, **kwargs)
    return doc
