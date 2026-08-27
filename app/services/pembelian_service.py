from datetime import datetime
from app.database import get_db
from app.services import bahan_service, keuangan_service, stok_service
from app.utils.id_generator import generate_id_pembelian
from app.utils.unit_converter import normalize_satuan, to_gram, total_harga_dari_gram
from app.utils.response import now_iso


def list_pembelian(search='', page=1, per_page=10):
    db = get_db()
    query = {}
    if search:
        query['$or'] = [
            {'id_pembelian': {'$regex': search, '$options': 'i'}},
            {'nama_bahan': {'$regex': search, '$options': 'i'}},
        ]
    skip = (page - 1) * per_page
    total = db.pembelian.count_documents(query)
    items = list(db.pembelian.find(query).sort('created_at', -1).skip(skip).limit(per_page))
    return items, total


def get_pembelian(id_pembelian):
    return get_db().pembelian.find_one({'id_pembelian': id_pembelian})


def _validate_pembelian_payload(data):
    id_bahan = (data.get('id_bahan') or '').strip()
    if not id_bahan:
        raise ValueError('Bahan wajib dipilih')

    bahan = bahan_service.get_bahan(id_bahan)
    if not bahan:
        raise ValueError('Bahan tidak ditemukan')
    if bahan.get('status') != 'aktif':
        raise ValueError('Bahan tidak aktif')

    jumlah = float(data.get('jumlah') or 0)
    if jumlah <= 0:
        raise ValueError('Jumlah harus lebih dari 0')

    satuan = normalize_satuan(data.get('satuan'))
    jumlah_gram = to_gram(jumlah, satuan)

    harga_per_kg = float(data.get('harga_per_kg') or data.get('harga_per_satuan') or 0)
    if harga_per_kg < 0:
        raise ValueError('Harga per kg tidak boleh negatif')

    harga_per_kg_int = int(round(harga_per_kg))
    total_harga = total_harga_dari_gram(harga_per_kg_int, jumlah_gram)
    tanggal = (data.get('tanggal') or datetime.now().strftime('%Y-%m-%d')).strip()

    return {
        'bahan': bahan,
        'jumlah': jumlah,
        'satuan': satuan,
        'jumlah_gram': jumlah_gram,
        'harga_per_kg': harga_per_kg_int,
        'harga_per_satuan': harga_per_kg_int,
        'total_harga': total_harga,
        'tanggal': tanggal,
        'catatan': (data.get('catatan') or '').strip(),
    }


def create_pembelian(data):
    validated = _validate_pembelian_payload(data)
    bahan = validated['bahan']
    stok_sebelum = int(bahan.get('stok_gram') or 0)
    stok_sesudah = stok_sebelum + validated['jumlah_gram']

    def _execute(session=None, tracker=None):
        kwargs = {'session': session} if session else {}
        db = get_db()

        id_pembelian = generate_id_pembelian(validated['tanggal'].replace('-', ''))
        pembelian_doc = {
            'id_pembelian': id_pembelian,
            'tanggal': validated['tanggal'],
            'id_bahan': bahan['id_bahan'],
            'nama_bahan': bahan.get('nama_bahan', ''),
            'jumlah': validated['jumlah'],
            'satuan': validated['satuan'],
            'jumlah_gram': validated['jumlah_gram'],
            'harga_per_kg': validated['harga_per_kg'],
            'harga_per_satuan': validated['harga_per_kg'],
            'total_harga': validated['total_harga'],
            'catatan': validated['catatan'],
            'created_at': now_iso(),
        }
        db.pembelian.insert_one(pembelian_doc, **kwargs)
        if tracker:
            tracker.track_insert('pembelian', 'id_pembelian', id_pembelian)

        bahan_service.update_stok(bahan['id_bahan'], stok_sesudah, session=session)
        bahan_service.update_harga_terakhir(
            bahan['id_bahan'], validated['harga_per_kg'], session=session
        )

        riwayat = stok_service.create_riwayat(
            {
                'id_bahan': bahan['id_bahan'],
                'nama_bahan': bahan.get('nama_bahan', ''),
                'tanggal': validated['tanggal'],
                'tipe': 'PEMBELIAN',
                'jumlah_gram': validated['jumlah_gram'],
                'stok_sebelum': stok_sebelum,
                'stok_sesudah': stok_sesudah,
                'id_referensi': id_pembelian,
                'keterangan': f"Pembelian {validated['jumlah']} {validated['satuan']}",
            },
            session=session,
        )
        if tracker:
            tracker.track_insert('riwayat_stok', 'id_riwayat', riwayat['id_riwayat'])

        pengeluaran = keuangan_service.create_pengeluaran_pembelian(
            validated['tanggal'],
            id_pembelian,
            validated['total_harga'],
            f"Pembelian {bahan.get('nama_bahan', '')}",
            session=session,
        )
        if tracker:
            tracker.track_insert('pengeluaran', 'id_pengeluaran', pengeluaran['id_pengeluaran'])

        return pembelian_doc

    return keuangan_service.run_in_transaction(_execute)


def total_pembelian_bulan(bulan_yyyy_mm=None):
    from app.utils.dates import bulan_query
    bulan = bulan_yyyy_mm or datetime.now().strftime('%Y-%m')
    db = get_db()
    pipeline = [
        {'$match': bulan_query(bulan)},
        {'$group': {'_id': None, 'total': {'$sum': '$total_harga'}}},
    ]
    result = list(db.pembelian.aggregate(pipeline))
    return int(result[0]['total']) if result else 0


def penyesuaian_stok(data):
    id_bahan = (data.get('id_bahan') or '').strip()
    if not id_bahan:
        raise ValueError('Bahan wajib dipilih')

    bahan = bahan_service.get_bahan(id_bahan)
    if not bahan:
        raise ValueError('Bahan tidak ditemukan')
    if bahan.get('status') != 'aktif':
        raise ValueError('Bahan tidak aktif')

    stok_sistem = int(bahan.get('stok_gram') or 0)
    stok_fisik = int(data.get('stok_fisik') or 0)
    if stok_fisik < 0:
        raise ValueError('Stok fisik tidak boleh negatif')

    selisih = stok_fisik - stok_sistem
    alasan = (data.get('alasan') or '').strip()
    if not alasan:
        raise ValueError('Alasan penyesuaian wajib diisi')
    catatan = (data.get('catatan') or '').strip()
    tanggal = (data.get('tanggal') or datetime.now().strftime('%Y-%m-%d')).strip()

    def _execute(session=None, tracker=None):
        bahan_service.update_stok(id_bahan, stok_fisik, session=session)
        riwayat = stok_service.create_riwayat(
            {
                'id_bahan': id_bahan,
                'nama_bahan': bahan.get('nama_bahan', ''),
                'tanggal': tanggal,
                'tipe': 'PENYESUAIAN',
                'jumlah_gram': selisih,
                'stok_sebelum': stok_sistem,
                'stok_sesudah': stok_fisik,
                'id_referensi': '',
                'keterangan': f'{alasan}. {catatan}'.strip(),
            },
            session=session,
        )
        return {
            'id_bahan': id_bahan,
            'stok_sebelum': stok_sistem,
            'stok_sesudah': stok_fisik,
            'selisih': selisih,
            'riwayat': riwayat,
        }

    return keuangan_service.run_in_transaction(_execute)
