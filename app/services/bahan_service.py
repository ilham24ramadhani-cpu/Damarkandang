from app.database import get_db
from app.services import jenis_bahan_service, stok_service
from app.services import keuangan_service
from app.services.keuangan_service import run_in_transaction
from app.utils.id_generator import generate_id_bahan
from app.utils.response import now_iso
from app.utils.unit_converter import to_gram, total_harga_dari_gram


def _apply_harga_fields(doc):
    """Normalisasi harga + info satuan dari master jenis (kg/pcs)."""
    if doc is None:
        return doc
    harga_kg = int(doc.get('harga_per_kg') or doc.get('harga_terakhir') or 0)
    doc['harga_per_kg'] = harga_kg
    doc['harga_terakhir'] = harga_kg
    satuan = (doc.get('satuan_berat') or 'kg').strip().lower()
    if satuan == 'pcs':
        doc['satuan_berat'] = 'pcs'
        doc['satuan_berat_label'] = 'Pcs'
        doc['harga_per_pcs'] = int(doc.get('harga_per_pcs') or 0)
        doc['gram_per_pcs'] = int(doc.get('gram_per_pcs') or 0)
        tampil = doc['harga_per_pcs'] or harga_kg
        doc['harga_tampil'] = tampil
        doc['harga_tampil_suffix'] = '/pcs'
    else:
        doc['satuan_berat'] = 'kg'
        doc['satuan_berat_label'] = 'Kg'
        doc['harga_tampil'] = harga_kg
        doc['harga_tampil_suffix'] = '/kg'
    return doc


def _decorate_bahan_satuan_from_jenis(doc, jenis=None):
    """Salin meta satuan/pcs/kategori dari jenis ke dokumen bahan (untuk tampilan)."""
    if not doc:
        return doc
    jenis = jenis or {}
    if jenis.get('kategori'):
        doc['kategori'] = jenis.get('kategori')
    if jenis_bahan_service.is_cairan(jenis):
        doc['bentuk_bahan'] = jenis_bahan_service.BENTUK_CAIRAN
        return _apply_harga_fields(doc)
    doc['bentuk_bahan'] = jenis_bahan_service.BENTUK_NON_CAIRAN
    doc['satuan_berat'] = jenis.get('satuan_berat') or doc.get('satuan_berat') or 'kg'
    if jenis_bahan_service.is_pcs(jenis):
        doc['satuan_berat'] = 'pcs'
        doc['harga_per_pcs'] = int(jenis.get('harga_per_pcs') or doc.get('harga_per_pcs') or 0)
        doc['gram_per_pcs'] = int(jenis.get('gram_per_pcs') or doc.get('gram_per_pcs') or 0)
    return _apply_harga_fields(doc)


def _bahan_filter(extra=None):
    q = {'id_bahan': {'$exists': True}}
    if extra:
        q.update(extra)
    return q


STOK_MENIPIS_BATAS_GRAM = 1000


def stok_status(stok_gram, _stok_minimum_gram=None):
    """Habis = 0 gram, menipis = di bawah 1000 gram, selain itu normal."""
    stok = int(stok_gram or 0)
    if stok <= 0:
        return 'habis', 'Stok Habis'
    if stok < STOK_MENIPIS_BATAS_GRAM:
        return 'menipis', 'Stok Menipis'
    return 'normal', 'Stok Normal'


def _pembelian_ids_for_bahan(db, id_bahan):
    return [
        p['id_pembelian'] for p in db.pembelian.find({'id_bahan': id_bahan}, {'id_pembelian': 1})
        if p.get('id_pembelian')
    ]


def _sum_pengeluaran_bahan(db, id_bahan):
    totals = _sum_pengeluaran_batch(db, [id_bahan])
    return int(totals.get(id_bahan, 0))


def _sum_pengeluaran_batch(db, id_bahans):
    """Hitung total pengeluaran banyak bahan dalam 2 query (bukan N×query)."""
    ids = [i for i in id_bahans if i]
    if not ids:
        return {}

    totals = {i: 0 for i in ids}

    # 1) Pengeluaran langsung dari bahan masuk
    for row in db.pengeluaran.aggregate([
        {'$match': {'sumber': 'Bahan Masuk', 'id_referensi': {'$in': ids}}},
        {'$group': {'_id': '$id_referensi', 'total': {'$sum': '$nominal'}}},
    ]):
        if row.get('_id') in totals:
            totals[row['_id']] += int(row.get('total') or 0)

    # 2) Pengeluaran dari pembelian bahan
    pembelian_to_bahan = {}
    for p in db.pembelian.find({'id_bahan': {'$in': ids}}, {'id_pembelian': 1, 'id_bahan': 1}):
        pid = p.get('id_pembelian')
        bid = p.get('id_bahan')
        if pid and bid:
            pembelian_to_bahan[pid] = bid

    if pembelian_to_bahan:
        for row in db.pengeluaran.aggregate([
            {
                '$match': {
                    'sumber': 'Pembelian Bahan',
                    'id_referensi': {'$in': list(pembelian_to_bahan.keys())},
                }
            },
            {'$group': {'_id': '$id_referensi', 'total': {'$sum': '$nominal'}}},
        ]):
            bid = pembelian_to_bahan.get(row.get('_id'))
            if bid in totals:
                totals[bid] += int(row.get('total') or 0)

    return totals


def _backfill_pengeluaran_bahan_masuk(doc):
    """Buat pengeluaran untuk data bahan masuk lama yang belum punya entri keuangan."""
    db = get_db()
    id_bahan = doc.get('id_bahan')
    if not id_bahan:
        return
    if db.pengeluaran.find_one({'sumber': 'Bahan Masuk', 'id_referensi': id_bahan}):
        return
    masuk = db.riwayat_stok.find_one({'id_bahan': id_bahan, 'tipe': 'MASUK'})
    if not masuk:
        return
    harga_per_kg = int(doc.get('harga_per_kg') or doc.get('harga_terakhir') or 0)
    jumlah_gram = int(masuk.get('jumlah_gram') or doc.get('stok_gram') or 0)
    total = total_harga_dari_gram(harga_per_kg, jumlah_gram)
    if total <= 0:
        return
    nama = doc.get('nama_jenis') or doc.get('nama_bahan') or id_bahan
    tanggal = (masuk.get('tanggal') or now_iso()[:10]).strip()
    keuangan_service.create_pengeluaran_bahan_masuk(
        tanggal,
        id_bahan,
        total,
        f'Bahan masuk {nama}',
    )


def _attach_pengeluaran_info(item, do_backfill=False):
    db = get_db()
    if do_backfill:
        _backfill_pengeluaran_bahan_masuk(item)
    item['total_pengeluaran'] = _sum_pengeluaran_bahan(db, item.get('id_bahan'))
    return item


def _decorate_bahan(item, include_pengeluaran=False):
    code, label = stok_status(item.get('stok_gram'))
    item['stok_status'] = code
    item['stok_status_label'] = label
    _apply_harga_fields(item)
    if not include_pengeluaran:
        item.setdefault('total_pengeluaran', 0)
    return item


def list_bahan(search='', status='', page=1, per_page=10, active_only=False, include_pengeluaran=True, light=False, kategori=''):
    db = get_db()
    query = _bahan_filter()
    and_parts = []
    if search:
        and_parts.append({'$or': [
            {'nama_bahan': {'$regex': search, '$options': 'i'}},
            {'id_bahan': {'$regex': search, '$options': 'i'}},
            {'nama_jenis': {'$regex': search, '$options': 'i'}},
        ]})
    if status:
        query['status'] = status.lower()
    if active_only:
        query['status'] = 'aktif'
    # Filter kategori lewat master jenis (data lama mungkin belum punya field kategori di bahan)
    if kategori:
        kat = kategori.strip()
        jenis_ids = [
            j['id_jenis']
            for j in db.jenis_bahan.find({'kategori': kat}, {'id_jenis': 1})
            if j.get('id_jenis')
        ]
        and_parts.append(
            {'$or': [{'kategori': kat}, {'id_jenis': {'$in': jenis_ids}}]} if jenis_ids else {'kategori': kat}
        )
    if len(and_parts) == 1:
        query.update(and_parts[0])
    elif and_parts:
        query['$and'] = and_parts

    skip = (page - 1) * per_page
    total = db.bahan.count_documents(query)

    projection = None
    if light:
        include_pengeluaran = False
        projection = {
            'id_bahan': 1,
            'nama_bahan': 1,
            'nama_jenis': 1,
            'id_jenis': 1,
            'stok_gram': 1,
            'harga_per_kg': 1,
            'harga_terakhir': 1,
            'harga_per_pcs': 1,
            'gram_per_pcs': 1,
            'satuan_berat': 1,
            'status': 1,
            'bentuk_bahan': 1,
            'kategori': 1,
        }

    cursor = db.bahan.find(query, projection).sort('id_bahan', 1).skip(skip).limit(per_page)
    items = list(cursor)

    # Enrich satuan dari master jenis (data lama / belum tersalin)
    jenis_ids = list({i.get('id_jenis') for i in items if i.get('id_jenis')})
    jenis_map = {}
    if jenis_ids:
        for j in db.jenis_bahan.find({'id_jenis': {'$in': jenis_ids}}):
            jenis_map[j['id_jenis']] = jenis_bahan_service._apply_bentuk_fields(j)
    for item in items:
        jenis = jenis_map.get(item.get('id_jenis'))
        if jenis:
            _decorate_bahan_satuan_from_jenis(item, jenis)
        _decorate_bahan(item, include_pengeluaran=False)

    if include_pengeluaran and items:
        totals = _sum_pengeluaran_batch(db, [i.get('id_bahan') for i in items])
        for item in items:
            item['total_pengeluaran'] = int(totals.get(item.get('id_bahan'), 0))

    return items, total


def get_bahan(id_bahan, include_pengeluaran=False, do_backfill=False):
    db = get_db()
    doc = db.bahan.find_one(_bahan_filter({'id_bahan': id_bahan}))
    if doc:
        jenis = None
        if doc.get('id_jenis'):
            jenis_raw = db.jenis_bahan.find_one({'id_jenis': doc['id_jenis']})
            if jenis_raw:
                jenis = jenis_bahan_service._apply_bentuk_fields(jenis_raw)
                _decorate_bahan_satuan_from_jenis(doc, jenis)
        _decorate_bahan(doc, include_pengeluaran=False)
        if include_pengeluaran:
            _attach_pengeluaran_info(doc, do_backfill=do_backfill)
        else:
            doc.setdefault('total_pengeluaran', 0)
    return doc


def get_bahan_many(id_bahans):
    """Ambil banyak bahan sekaligus (untuk resep menu) tanpa hitung pengeluaran."""
    ids = [i for i in (id_bahans or []) if i]
    if not ids:
        return {}
    db = get_db()
    docs = list(db.bahan.find(_bahan_filter({'id_bahan': {'$in': ids}})))
    jenis_ids = list({d.get('id_jenis') for d in docs if d.get('id_jenis')})
    jenis_map = {}
    if jenis_ids:
        for j in db.jenis_bahan.find({'id_jenis': {'$in': jenis_ids}}):
            jenis_map[j['id_jenis']] = jenis_bahan_service._apply_bentuk_fields(j)
    result = {}
    for doc in docs:
        jenis = jenis_map.get(doc.get('id_jenis'))
        if jenis:
            _decorate_bahan_satuan_from_jenis(doc, jenis)
        _decorate_bahan(doc, include_pengeluaran=False)
        result[doc['id_bahan']] = doc
    return result


def _keterangan_bahan_masuk(payload):
    jumlah_pack = payload.get('jumlah_pack')
    if jumlah_pack:
        pack_label = int(jumlah_pack) if jumlah_pack == int(jumlah_pack) else jumlah_pack
        return f'Pencatatan bahan masuk ({pack_label} pack)'
    jumlah_pcs = payload.get('jumlah_pcs')
    if jumlah_pcs:
        pcs_label = int(jumlah_pcs) if jumlah_pcs == int(jumlah_pcs) else jumlah_pcs
        gram = int(payload.get('gram_per_pcs') or 0)
        isi = f' × {gram}g' if gram else ''
        return f'Pencatatan bahan masuk ({pcs_label} pcs{isi})'
    return 'Pencatatan bahan masuk'


def _parse_bahan_masuk_payload(data, jenis):
    nama = (jenis.get('nama_jenis') or '').strip()
    if not nama:
        raise ValueError('Nama jenis bahan tidak valid')

    tanggal = (data.get('tanggal') or now_iso()[:10]).strip()

    if jenis_bahan_service.is_cairan(jenis):
        jumlah_pack = float(data.get('jumlah_pack') or data.get('jumlah') or 0)
        if jumlah_pack <= 0:
            raise ValueError('Jumlah pack harus lebih dari 0')

        harga_per_pack = int(jenis.get('harga_per_pack') or 0)
        kg_per_pack = float(jenis.get('kg_per_pack') or 0)
        if harga_per_pack <= 0 or kg_per_pack <= 0:
            raise ValueError('Master jenis cairan belum lengkap (harga & kg per pack)')

        stok_gram = int(round(jumlah_pack * kg_per_pack * 1000))
        total_harga = int(round(jumlah_pack * harga_per_pack))
        harga_per_kg = int(round(harga_per_pack / kg_per_pack))

        return {
            'nama': nama,
            'stok_gram': stok_gram,
            'harga_per_kg': harga_per_kg,
            'tanggal': tanggal,
            'total_harga': total_harga,
            'bentuk_bahan': jenis_bahan_service.BENTUK_CAIRAN,
            'satuan_berat': 'pack',
            'jumlah_pack': jumlah_pack,
        }

    # Non cairan — pcs (Kopral kemasan) atau kg (roasted beans, dll)
    if jenis_bahan_service.is_pcs(jenis):
        jumlah_pcs = float(
            data.get('jumlah_pcs')
            or data.get('jumlah_pack')
            or data.get('jumlah')
            or 0
        )
        if jumlah_pcs <= 0:
            raise ValueError('Jumlah pcs harus lebih dari 0')

        harga_per_pcs = int(jenis.get('harga_per_pcs') or 0)
        gram_per_pcs = int(jenis.get('gram_per_pcs') or 0)
        harga_per_kg = int(jenis.get('harga_per_kg') or 0)
        if harga_per_pcs <= 0 or gram_per_pcs <= 0:
            raise ValueError('Master jenis pcs belum lengkap (harga & gram per pcs)')
        if harga_per_kg <= 0:
            harga_per_kg = int(round(harga_per_pcs / (gram_per_pcs / 1000.0)))

        stok_gram = int(round(jumlah_pcs * gram_per_pcs))
        total_harga = int(round(jumlah_pcs * harga_per_pcs))

        return {
            'nama': nama,
            'stok_gram': stok_gram,
            'harga_per_kg': harga_per_kg,
            'harga_per_pcs': harga_per_pcs,
            'gram_per_pcs': gram_per_pcs,
            'tanggal': tanggal,
            'total_harga': total_harga,
            'bentuk_bahan': jenis_bahan_service.BENTUK_NON_CAIRAN,
            'satuan_berat': 'pcs',
            'jumlah_pcs': jumlah_pcs,
        }

    if data.get('jumlah') is not None and str(data.get('jumlah')).strip() != '':
        stok_gram = to_gram(data.get('jumlah'), data.get('satuan') or 'kg')
    elif data.get('stok_gram') is not None:
        stok_gram = int(data.get('stok_gram') or 0)
    else:
        raise ValueError('Jumlah bahan masuk wajib diisi')
    if stok_gram <= 0:
        raise ValueError('Jumlah bahan masuk harus lebih dari 0')

    harga_per_kg = int(jenis.get('harga_per_kg') or data.get('harga_per_kg') or data.get('harga_terakhir') or 0)
    if harga_per_kg <= 0:
        raise ValueError('Master jenis non cairan belum lengkap (harga per kg)')

    return {
        'nama': nama,
        'stok_gram': stok_gram,
        'harga_per_kg': harga_per_kg,
        'tanggal': tanggal,
        'total_harga': total_harga_dari_gram(harga_per_kg, stok_gram),
        'bentuk_bahan': jenis_bahan_service.BENTUK_NON_CAIRAN,
        'satuan_berat': 'kg',
    }


def _add_bahan_masuk(existing, payload):
    """Tambah stok pada bahan yang sudah terdaftar (transaksi bahan masuk berikutnya)."""
    id_bahan = existing['id_bahan']
    stok_sebelum = int(existing.get('stok_gram') or 0)
    stok_sesudah = stok_sebelum + payload['stok_gram']
    nama = payload['nama'] or existing.get('nama_jenis') or existing.get('nama_bahan') or id_bahan

    def _execute(session=None, tracker=None):
        update_stok(id_bahan, stok_sesudah, session=session)
        fields = {
            'harga_per_kg': payload['harga_per_kg'],
            'harga_terakhir': payload['harga_per_kg'],
            'satuan_berat': payload.get('satuan_berat') or existing.get('satuan_berat') or 'kg',
            'updated_at': now_iso(),
        }
        if payload.get('satuan_berat') == 'pcs':
            fields['harga_per_pcs'] = int(payload.get('harga_per_pcs') or 0)
            fields['gram_per_pcs'] = int(payload.get('gram_per_pcs') or 0)
        kwargs = {'session': session} if session else {}
        get_db().bahan.update_one({'id_bahan': id_bahan}, {'$set': fields}, **kwargs)
        keterangan = _keterangan_bahan_masuk(payload)
        stok_service.create_riwayat({
            'id_bahan': id_bahan,
            'nama_bahan': nama,
            'tanggal': payload['tanggal'],
            'tipe': 'MASUK',
            'jumlah_gram': payload['stok_gram'],
            'stok_sebelum': stok_sebelum,
            'stok_sesudah': stok_sesudah,
            'id_referensi': id_bahan,
            'keterangan': keterangan,
        }, session=session)
        keuangan_service.create_pengeluaran_bahan_masuk(
            payload['tanggal'],
            id_bahan,
            payload['total_harga'],
            f'Bahan masuk {nama}',
            session=session,
        )

    run_in_transaction(_execute)
    return get_bahan(id_bahan)


def create_bahan(data):
    db = get_db()
    id_jenis = (data.get('id_jenis') or '').strip()
    if not id_jenis:
        raise ValueError('Jenis bahan wajib dipilih')

    jenis = jenis_bahan_service.get_jenis_bahan(id_jenis)
    if not jenis:
        raise ValueError('Jenis bahan tidak ditemukan')
    if jenis.get('status') != 'aktif':
        raise ValueError('Jenis bahan tidak aktif')

    payload = _parse_bahan_masuk_payload(data, jenis)

    existing = db.bahan.find_one({'id_jenis': id_jenis, 'id_bahan': {'$exists': True}, 'status': 'aktif'})
    if existing:
        return _add_bahan_masuk(existing, payload)

    nama = payload['nama']
    stok_gram = payload['stok_gram']
    harga_per_kg = payload['harga_per_kg']
    tanggal = payload['tanggal']
    total_harga = payload['total_harga']

    id_bahan = generate_id_bahan()
    doc = {
        'id_bahan': id_bahan,
        'nama_bahan': nama,
        'id_jenis': id_jenis,
        'nama_jenis': nama,
        'bentuk_bahan': payload.get('bentuk_bahan') or jenis_bahan_service.BENTUK_NON_CAIRAN,
        'satuan_berat': payload.get('satuan_berat') or jenis.get('satuan_berat') or 'kg',
        'kategori': jenis.get('kategori') or 'Minuman',
        'stok_gram': stok_gram,
        'stok_minimum_gram': 0,
        'harga_per_kg': harga_per_kg,
        'harga_terakhir': harga_per_kg,
        'status': (data.get('status') or 'aktif').lower(),
        'created_at': now_iso(),
        'updated_at': now_iso(),
    }
    if payload.get('satuan_berat') == 'pcs':
        doc['harga_per_pcs'] = int(payload.get('harga_per_pcs') or 0)
        doc['gram_per_pcs'] = int(payload.get('gram_per_pcs') or 0)

    def _execute(session=None, tracker=None):
        kwargs = {'session': session} if session else {}
        db.bahan.insert_one(doc, **kwargs)
        stok_service.create_riwayat({
            'id_bahan': id_bahan,
            'nama_bahan': nama,
            'tanggal': tanggal,
            'tipe': 'MASUK',
            'jumlah_gram': stok_gram,
            'stok_sebelum': 0,
            'stok_sesudah': stok_gram,
            'id_referensi': id_bahan,
            'keterangan': _keterangan_bahan_masuk(payload),
        }, session=session)
        keuangan_service.create_pengeluaran_bahan_masuk(
            tanggal,
            id_bahan,
            total_harga,
            f'Bahan masuk {nama}',
            session=session,
        )
        return doc

    run_in_transaction(_execute)
    code, label = stok_status(stok_gram)
    doc['stok_status'] = code
    doc['stok_status_label'] = label
    doc['total_pengeluaran'] = total_harga
    return _apply_harga_fields(doc)


def update_bahan(id_bahan, data):
    db = get_db()
    doc = get_bahan(id_bahan)
    if not doc:
        raise ValueError('Bahan tidak ditemukan')

    update = {'updated_at': now_iso()}
    if 'id_jenis' in data:
        raise ValueError('Jenis bahan tidak dapat diubah. Hapus lalu buat ulang jika perlu.')
    if 'nama_bahan' in data:
        raise ValueError('Nama bahan mengikuti master jenis bahan di Kelola Data')
    if 'status' in data:
        update['status'] = (data.get('status') or 'aktif').lower()
    if 'harga_per_kg' in data or 'harga_terakhir' in data:
        harga_per_kg = int(round(float(data.get('harga_per_kg') or data.get('harga_terakhir') or 0)))
        if harga_per_kg < 0:
            raise ValueError('Harga per kg tidak boleh negatif')
        update['harga_per_kg'] = harga_per_kg
        update['harga_terakhir'] = harga_per_kg
    if 'stok_gram' in data and 'from_penyesuaian' not in data:
        stok = int(data.get('stok_gram') or 0)
        if stok < 0:
            raise ValueError('Stok tidak boleh negatif')
        update['stok_gram'] = stok

    db.bahan.update_one({'id_bahan': id_bahan}, {'$set': update})
    if 'harga_per_kg' in update:
        nama = doc.get('nama_jenis') or doc.get('nama_bahan') or id_bahan
        _sync_pengeluaran_bahan_masuk_harga(db, id_bahan, update['harga_per_kg'], nama)
    return get_bahan(id_bahan)


def _sync_pengeluaran_bahan_masuk_harga(db, id_bahan, harga_per_kg, nama):
    masuk = db.riwayat_stok.find_one({'id_bahan': id_bahan, 'tipe': 'MASUK'})
    if not masuk:
        return
    total = total_harga_dari_gram(harga_per_kg, int(masuk.get('jumlah_gram') or 0))
    if total <= 0:
        return
    db.pengeluaran.update_one(
        {'sumber': 'Bahan Masuk', 'id_referensi': id_bahan},
        {'$set': {'nominal': total, 'keterangan': f'Bahan masuk {nama}'}},
    )


def delete_bahan(id_bahan):
    """
    Hapus bahan permanen beserta data terkait:
    pembelian, pengeluaran dari pembelian, dan riwayat stok bahan tersebut.
    """
    db = get_db()
    doc = get_bahan(id_bahan)
    if not doc:
        raise ValueError('Bahan tidak ditemukan')

    pembelian_list = list(db.pembelian.find({'id_bahan': id_bahan}))
    id_pembelian_list = [p['id_pembelian'] for p in pembelian_list if p.get('id_pembelian')]

    def _execute(session=None, tracker=None):
        kwargs = {'session': session} if session else {}

        if id_pembelian_list:
            db.pengeluaran.delete_many(
                {
                    'sumber': 'Pembelian Bahan',
                    'id_referensi': {'$in': id_pembelian_list},
                },
                **kwargs,
            )
            db.pembelian.delete_many({'id_bahan': id_bahan}, **kwargs)

        db.pengeluaran.delete_many(
            {'sumber': 'Bahan Masuk', 'id_referensi': id_bahan},
            **kwargs,
        )

        db.riwayat_stok.delete_many({'id_bahan': id_bahan}, **kwargs)

        # Lepas bahan dari resep menu (tanpa menghapus menu)
        for menu_doc in db.menu.find({'bahan_resep.id_bahan': id_bahan}):
            new_resep = [
                r for r in (menu_doc.get('bahan_resep') or [])
                if r.get('id_bahan') != id_bahan
            ]
            db.menu.update_one(
                {'id_menu': menu_doc['id_menu']},
                {'$set': {'bahan_resep': new_resep, 'updated_at': now_iso()}},
                **kwargs,
            )

        db.bahan.delete_one({'id_bahan': id_bahan}, **kwargs)

        return {
            'deleted': True,
            'id_bahan': id_bahan,
            'pembelian_dihapus': len(id_pembelian_list),
            'pengeluaran_dihapus': len(id_pembelian_list),
            'message': (
                f'Bahan {doc.get("nama_bahan", id_bahan)} berhasil dihapus. '
                f'{len(id_pembelian_list)} pembelian & pengeluaran terkait ikut dihapus.'
            ),
        }

    return run_in_transaction(_execute)


def list_stok_by_jenis(search=''):
    """
    Agregasi stok per jenis bahan (realtime dari collection bahan).
    Satu baris = satu jenis bahan, bukan per id_bahan.
    """
    db = get_db()
    match = {
        'id_bahan': {'$exists': True},
        'status': 'aktif',
    }
    if search:
        match['$or'] = [
            {'nama_jenis': {'$regex': search, '$options': 'i'}},
            {'id_jenis': {'$regex': search, '$options': 'i'}},
            {'nama_bahan': {'$regex': search, '$options': 'i'}},
        ]

    pipeline = [
        {'$match': match},
        {
            '$group': {
                '_id': '$id_jenis',
                'nama_jenis': {'$first': '$nama_jenis'},
                'stok_gram': {'$sum': {'$ifNull': ['$stok_gram', 0]}},
                'harga_per_kg': {
                    '$max': {
                        '$ifNull': ['$harga_per_kg', {'$ifNull': ['$harga_terakhir', 0]}],
                    }
                },
                'jumlah_item_bahan': {'$sum': 1},
            }
        },
        {'$sort': {'nama_jenis': 1}},
    ]

    rows = []
    for row in db.bahan.aggregate(pipeline):
        id_jenis = row.get('_id')
        if not id_jenis:
            continue
        stok_total = int(row.get('stok_gram') or 0)
        harga_terakhir = int(row.get('harga_per_kg') or 0)
        code, label = stok_status(stok_total)
        rows.append({
            'id_jenis': id_jenis,
            'nama_jenis': row.get('nama_jenis') or '',
            'stok_gram': stok_total,
            'harga_per_kg': harga_terakhir,
            'harga_terakhir': harga_terakhir,
            'stok_status': code,
            'stok_status_label': label,
            'jumlah_item_bahan': int(row.get('jumlah_item_bahan') or 0),
        })

    return rows


def sync_nama_from_jenis_master(id_jenis, nama_jenis, kategori=None):
    """Sinkronkan nama/kategori bahan ketika master jenis diubah."""
    update = {
        'nama_bahan': nama_jenis,
        'nama_jenis': nama_jenis,
        'updated_at': now_iso(),
    }
    if kategori:
        update['kategori'] = kategori
    get_db().bahan.update_many(
        {'id_jenis': id_jenis, 'id_bahan': {'$exists': True}},
        {'$set': update},
    )


def sync_harga_from_jenis_master(id_jenis, jenis_fields):
    """Sinkronkan harga/satuan/kategori bahan ketika master jenis diubah."""
    fields = jenis_fields if isinstance(jenis_fields, dict) else {'harga_per_kg': jenis_fields}
    harga_kg = int(fields.get('harga_per_kg') or 0)
    if harga_kg < 0:
        return
    update = {
        'harga_per_kg': harga_kg,
        'harga_terakhir': harga_kg,
        'updated_at': now_iso(),
    }
    if fields.get('kategori'):
        update['kategori'] = fields['kategori']
    satuan = (fields.get('satuan_berat') or 'kg').strip().lower()
    update['satuan_berat'] = satuan
    if satuan == 'pcs':
        update['harga_per_pcs'] = int(fields.get('harga_per_pcs') or 0)
        update['gram_per_pcs'] = int(fields.get('gram_per_pcs') or 0)
    else:
        get_db().bahan.update_many(
            {'id_jenis': id_jenis, 'id_bahan': {'$exists': True}},
            {'$set': update, '$unset': {'harga_per_pcs': '', 'gram_per_pcs': ''}},
        )
        return
    get_db().bahan.update_many(
        {'id_jenis': id_jenis, 'id_bahan': {'$exists': True}},
        {'$set': update},
    )


def update_stok(id_bahan, stok_baru, session=None):
    stok_baru = int(stok_baru)
    if stok_baru < 0:
        raise ValueError('Stok tidak boleh negatif')
    kwargs = {'session': session} if session else {}
    get_db().bahan.update_one(
        {'id_bahan': id_bahan},
        {'$set': {'stok_gram': stok_baru, 'updated_at': now_iso()}},
        **kwargs,
    )


def update_harga_terakhir(id_bahan, harga_per_kg, session=None):
    harga_per_kg = int(round(float(harga_per_kg)))
    if harga_per_kg < 0:
        raise ValueError('Harga tidak boleh negatif')
    kwargs = {'session': session} if session else {}
    get_db().bahan.update_one(
        {'id_bahan': id_bahan},
        {'$set': {
            'harga_per_kg': harga_per_kg,
            'harga_terakhir': harga_per_kg,
            'updated_at': now_iso(),
        }},
        **kwargs,
    )
