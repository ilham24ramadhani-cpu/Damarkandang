from app.database import get_db
from app.utils.id_generator import generate_id_pembayaran
from app.utils.response import now_iso


def list_pembayaran(status=None):
    db = get_db()
    q = {}
    if status:
        q['status'] = status
    return list(db.data_pembayaran.find(q).sort('metode', 1))


def get_by_metode(metode):
    db = get_db()
    m = (metode or '').strip().lower()
    return db.data_pembayaran.find_one({'metode': m, 'status': 'aktif'})


def get_pembayaran(id_pembayaran):
    db = get_db()
    return db.data_pembayaran.find_one({'id_pembayaran': id_pembayaran})


def create_pembayaran(data):
    db = get_db()
    metode = (data.get('metode') or '').strip().lower()
    if metode not in ('cash', 'qris', 'debit'):
        raise ValueError('Metode harus cash, qris, atau debit')
    existing = db.data_pembayaran.find_one({'metode': metode})
    if existing:
        raise ValueError(f'Data pembayaran untuk {metode} sudah ada')

    doc = {
        'id_pembayaran': generate_id_pembayaran(),
        'metode': metode,
        'label': (data.get('label') or metode.upper()).strip(),
        'nomor_rekening': (data.get('nomor_rekening') or '').strip(),
        'nama_rekening': (data.get('nama_rekening') or '').strip(),
        'gambar_url': (data.get('gambar_url') or '').strip(),
        'keterangan': (data.get('keterangan') or '').strip(),
        'status': (data.get('status') or 'aktif').strip(),
        'created_at': now_iso(),
        'updated_at': now_iso(),
    }
    db.data_pembayaran.insert_one(doc)
    return doc


def update_pembayaran(id_pembayaran, data):
    db = get_db()
    doc = get_pembayaran(id_pembayaran)
    if not doc:
        raise ValueError('Data pembayaran tidak ditemukan')

    updates = {'updated_at': now_iso()}
    for key in ('label', 'nomor_rekening', 'nama_rekening', 'gambar_url', 'keterangan', 'status'):
        if key in data:
            updates[key] = (data.get(key) or '').strip()

    db.data_pembayaran.update_one({'id_pembayaran': id_pembayaran}, {'$set': updates})
    return get_pembayaran(id_pembayaran)


def delete_pembayaran(id_pembayaran):
    db = get_db()
    res = db.data_pembayaran.delete_one({'id_pembayaran': id_pembayaran})
    if res.deleted_count == 0:
        raise ValueError('Data pembayaran tidak ditemukan')
    return True
