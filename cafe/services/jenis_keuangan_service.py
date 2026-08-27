"""Master jenis pemasukan & pengeluaran keuangan cafe."""

from cafe.database import get_db
from cafe.utils.id_generator import generate_id_jenis_pemasukan, generate_id_jenis_pengeluaran
from cafe.utils.response import now_iso

DEFAULT_JENIS_PENGELUARAN = [
    {'nama_jenis': 'Bahan Baku', 'tipe': 'otomatis', 'deskripsi': 'Otomatis dari pencatatan bahan masuk & pembelian bahan'},
    {'nama_jenis': 'Operasional', 'tipe': 'manual', 'deskripsi': 'Biaya operasional harian'},
    {'nama_jenis': 'Gaji', 'tipe': 'manual', 'deskripsi': 'Penggajian karyawan'},
    {'nama_jenis': 'Listrik', 'tipe': 'manual', 'deskripsi': 'Tagihan listrik'},
    {'nama_jenis': 'Air', 'tipe': 'manual', 'deskripsi': 'Tagihan air'},
    {'nama_jenis': 'Sewa', 'tipe': 'manual', 'deskripsi': 'Sewa tempat'},
    {'nama_jenis': 'Peralatan', 'tipe': 'manual', 'deskripsi': 'Pembelian/perbaikan peralatan'},
    {'nama_jenis': 'Lainnya', 'tipe': 'manual', 'deskripsi': 'Pengeluaran lainnya'},
]

DEFAULT_JENIS_PEMASUKAN = [
    {'nama_jenis': 'Penjualan', 'tipe': 'otomatis', 'deskripsi': 'Otomatis dari penjualan lunas (pengurangan stok produk)'},
    {'nama_jenis': 'Penjualan Langsung', 'tipe': 'manual', 'deskripsi': 'Pemasukan manual di luar sistem penjualan'},
    {'nama_jenis': 'Lainnya', 'tipe': 'manual', 'deskripsi': 'Pemasukan lainnya'},
]

JENIS_PENGELUARAN_OTOMATIS = 'Bahan Baku'
JENIS_PEMASUKAN_OTOMATIS = 'Penjualan'


def ensure_defaults():
    db = get_db()
    for item in DEFAULT_JENIS_PENGELUARAN:
        if not db.jenis_pengeluaran.find_one({'nama_jenis': item['nama_jenis']}):
            db.jenis_pengeluaran.insert_one({
                'id_jenis': generate_id_jenis_pengeluaran(),
                'nama_jenis': item['nama_jenis'],
                'tipe': item['tipe'],
                'deskripsi': item.get('deskripsi', ''),
                'status': 'aktif',
                'created_at': now_iso(),
            })
    # Rename legacy "Pemesanan" → "Penjualan" for automatic income type
    legacy = db.jenis_pemasukan.find_one({'nama_jenis': 'Pemesanan'})
    if legacy and not db.jenis_pemasukan.find_one({'nama_jenis': 'Penjualan'}):
        db.jenis_pemasukan.update_one(
            {'_id': legacy['_id']},
            {'$set': {
                'nama_jenis': 'Penjualan',
                'deskripsi': 'Otomatis dari penjualan lunas (pengurangan stok produk)',
                'updated_at': now_iso(),
            }},
        )
    for item in DEFAULT_JENIS_PEMASUKAN:
        if not db.jenis_pemasukan.find_one({'nama_jenis': item['nama_jenis']}):
            db.jenis_pemasukan.insert_one({
                'id_jenis': generate_id_jenis_pemasukan(),
                'nama_jenis': item['nama_jenis'],
                'tipe': item['tipe'],
                'deskripsi': item.get('deskripsi', ''),
                'status': 'aktif',
                'created_at': now_iso(),
            })


def list_jenis_pengeluaran(manual_only=False, status=None):
    db = get_db()
    q = {}
    if manual_only:
        q['tipe'] = 'manual'
    if status:
        q['status'] = status
    return list(db.jenis_pengeluaran.find(q).sort('nama_jenis', 1))


def list_jenis_pemasukan(manual_only=False, status=None):
    db = get_db()
    q = {}
    if manual_only:
        q['tipe'] = 'manual'
    if status:
        q['status'] = status
    return list(db.jenis_pemasukan.find(q).sort('nama_jenis', 1))


def get_jenis_pengeluaran(id_jenis):
    return get_db().jenis_pengeluaran.find_one({'id_jenis': id_jenis})


def get_jenis_pemasukan(id_jenis):
    return get_db().jenis_pemasukan.find_one({'id_jenis': id_jenis})


def get_jenis_pengeluaran_by_nama(nama):
    return get_db().jenis_pengeluaran.find_one({'nama_jenis': nama, 'status': 'aktif'})


def get_jenis_pemasukan_by_nama(nama):
    return get_db().jenis_pemasukan.find_one({'nama_jenis': nama, 'status': 'aktif'})


def validate_jenis_pengeluaran_manual(nama_jenis):
    doc = get_jenis_pengeluaran_by_nama(nama_jenis)
    if not doc:
        raise ValueError('Jenis pengeluaran tidak valid')
    if doc.get('tipe') == 'otomatis':
        raise ValueError('Jenis otomatis hanya dari transaksi sistem')
    if doc.get('status') != 'aktif':
        raise ValueError('Jenis pengeluaran tidak aktif')
    return doc


def validate_jenis_pemasukan_manual(nama_jenis):
    doc = get_jenis_pemasukan_by_nama(nama_jenis)
    if not doc:
        raise ValueError('Jenis pemasukan tidak valid')
    if doc.get('tipe') == 'otomatis':
        raise ValueError('Jenis otomatis hanya dari transaksi sistem')
    if doc.get('status') != 'aktif':
        raise ValueError('Jenis pemasukan tidak aktif')
    return doc


def create_jenis_pengeluaran(data):
    db = get_db()
    nama = (data.get('nama_jenis') or '').strip()
    if not nama:
        raise ValueError('Nama jenis wajib diisi')
    if db.jenis_pengeluaran.find_one({'nama_jenis': nama}):
        raise ValueError('Nama jenis sudah ada')
    doc = {
        'id_jenis': generate_id_jenis_pengeluaran(),
        'nama_jenis': nama,
        'tipe': 'manual',
        'deskripsi': (data.get('deskripsi') or '').strip(),
        'status': (data.get('status') or 'aktif').strip(),
        'created_at': now_iso(),
    }
    db.jenis_pengeluaran.insert_one(doc)
    return doc


def create_jenis_pemasukan(data):
    db = get_db()
    nama = (data.get('nama_jenis') or '').strip()
    if not nama:
        raise ValueError('Nama jenis wajib diisi')
    if db.jenis_pemasukan.find_one({'nama_jenis': nama}):
        raise ValueError('Nama jenis sudah ada')
    doc = {
        'id_jenis': generate_id_jenis_pemasukan(),
        'nama_jenis': nama,
        'tipe': 'manual',
        'deskripsi': (data.get('deskripsi') or '').strip(),
        'status': (data.get('status') or 'aktif').strip(),
        'created_at': now_iso(),
    }
    db.jenis_pemasukan.insert_one(doc)
    return doc


def update_jenis_pengeluaran(id_jenis, data):
    db = get_db()
    doc = get_jenis_pengeluaran(id_jenis)
    if not doc:
        raise ValueError('Jenis pengeluaran tidak ditemukan')
    updates = {}
    if doc.get('tipe') != 'otomatis' and 'nama_jenis' in data:
        nama = (data.get('nama_jenis') or '').strip()
        if nama and nama != doc.get('nama_jenis'):
            if db.jenis_pengeluaran.find_one({'nama_jenis': nama}):
                raise ValueError('Nama jenis sudah ada')
            updates['nama_jenis'] = nama
    if 'deskripsi' in data:
        updates['deskripsi'] = (data.get('deskripsi') or '').strip()
    if 'status' in data and doc.get('tipe') != 'otomatis':
        updates['status'] = (data.get('status') or 'aktif').strip()
    if updates:
        db.jenis_pengeluaran.update_one({'id_jenis': id_jenis}, {'$set': updates})
    return get_jenis_pengeluaran(id_jenis)


def update_jenis_pemasukan(id_jenis, data):
    db = get_db()
    doc = get_jenis_pemasukan(id_jenis)
    if not doc:
        raise ValueError('Jenis pemasukan tidak ditemukan')
    updates = {}
    if doc.get('tipe') != 'otomatis' and 'nama_jenis' in data:
        nama = (data.get('nama_jenis') or '').strip()
        if nama and nama != doc.get('nama_jenis'):
            if db.jenis_pemasukan.find_one({'nama_jenis': nama}):
                raise ValueError('Nama jenis sudah ada')
            updates['nama_jenis'] = nama
    if 'deskripsi' in data:
        updates['deskripsi'] = (data.get('deskripsi') or '').strip()
    if 'status' in data and doc.get('tipe') != 'otomatis':
        updates['status'] = (data.get('status') or 'aktif').strip()
    if updates:
        db.jenis_pemasukan.update_one({'id_jenis': id_jenis}, {'$set': updates})
    return get_jenis_pemasukan(id_jenis)


def delete_jenis_pengeluaran(id_jenis):
    doc = get_jenis_pengeluaran(id_jenis)
    if not doc:
        raise ValueError('Jenis pengeluaran tidak ditemukan')
    if doc.get('tipe') == 'otomatis':
        raise ValueError('Jenis otomatis tidak dapat dihapus')
    get_db().jenis_pengeluaran.delete_one({'id_jenis': id_jenis})
    return True


def delete_jenis_pemasukan(id_jenis):
    doc = get_jenis_pemasukan(id_jenis)
    if not doc:
        raise ValueError('Jenis pemasukan tidak ditemukan')
    if doc.get('tipe') == 'otomatis':
        raise ValueError('Jenis otomatis tidak dapat dihapus')
    get_db().jenis_pemasukan.delete_one({'id_jenis': id_jenis})
    return True
