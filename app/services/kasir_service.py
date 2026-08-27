from datetime import datetime
from collections import defaultdict
from app.database import get_db
from app.services import bahan_service, menu_service, pemasukan_service, pembayaran_service, stok_service
from app.utils.cache import cached, invalidate
from app.utils.dates import bulan_query
from app.utils.id_generator import generate_id_pemesanan
from app.utils.response import now_iso


def _bust_read_caches():
    invalidate('dashboard_stats:')
    invalidate('laporan:opsi')


_LIST_PROJECTION = {
    'id_pemesanan': 1,
    'id_transaksi': 1,
    'tanggal': 1,
    'nama_pelanggan': 1,
    'petugas': 1,
    'items': 1,
    'total': 1,
    'status_pembayaran': 1,
    'metode_bayar': 1,
    'catatan': 1,
    'created_at': 1,
}


def list_petugas():
    """Return active system users eligible to record a sale (cached singkat)."""
    return cached('kasir:petugas', 60, _list_petugas_uncached)


def _list_petugas_uncached():
    db = get_db()
    users = list(db.users.find(
        {'status': {'$regex': '^aktif$', '$options': 'i'}},
        {'id': 1, 'namaLengkap': 1, 'username': 1, 'role': 1},
    ).sort('namaLengkap', 1))
    return [{
        'id': str(user.get('id', '')),
        'nama_lengkap': user.get('namaLengkap') or user.get('username') or '-',
        'username': user.get('username') or '',
        'role': user.get('role') or 'Karyawan',
    } for user in users if user.get('id') is not None]


def _get_petugas(petugas_id):
    if petugas_id is None or str(petugas_id).strip() == '':
        raise ValueError('Petugas penginput wajib dipilih')
    try:
        user_id = int(str(petugas_id).strip())
    except (TypeError, ValueError):
        raise ValueError('Petugas penginput tidak valid')
    user = get_db().users.find_one({'id': user_id})
    if not user:
        raise ValueError('Petugas penginput tidak ditemukan')
    return {
        'id': str(user_id),
        'nama_lengkap': user.get('namaLengkap') or user.get('username') or '-',
        'username': user.get('username') or '',
        'role': user.get('role') or 'Karyawan',
    }


def list_transaksi(page=1, per_page=20, search=None, status=None, bulan=None):
    db = get_db()
    q = {}
    if status == 'lunas':
        q['status_pembayaran'] = {'$ne': 'ordering'}
    elif status == 'ordering':
        q['status_pembayaran'] = 'ordering'
    if bulan:
        q.update(bulan_query(bulan))
    if search:
        s = search.strip()
        q['$or'] = [
            {'id_pemesanan': {'$regex': s, '$options': 'i'}},
            {'id_transaksi': {'$regex': s, '$options': 'i'}},
            {'nama_pelanggan': {'$regex': s, '$options': 'i'}},
            {'petugas.nama_lengkap': {'$regex': s, '$options': 'i'}},
            {'items.nama_menu': {'$regex': s, '$options': 'i'}},
        ]
    skip = (page - 1) * per_page
    total = db.transaksi_kasir.count_documents(q)
    items = list(
        db.transaksi_kasir.find(q, _LIST_PROJECTION)
        .sort([('tanggal', -1), ('created_at', -1)])
        .skip(skip)
        .limit(per_page)
    )
    return items, total


def get_stats(bulan=None):
    """Satu aggregation pipeline — bukan 3 count terpisah."""
    db = get_db()
    match = bulan_query(bulan) if bulan else {}
    pipeline = [
        {'$match': match} if match else {'$match': {}},
        {'$group': {
            '_id': None,
            'total': {'$sum': 1},
            'ordering': {
                '$sum': {'$cond': [{'$eq': ['$status_pembayaran', 'ordering']}, 1, 0]}
            },
            'total_nilai_lunas': {
                '$sum': {
                    '$cond': [
                        {'$ne': ['$status_pembayaran', 'ordering']},
                        {'$ifNull': ['$total', 0]},
                        0,
                    ]
                }
            },
        }},
    ]
    # $match {} masih valid; hapus stage kosong yang membingungkan
    if not match:
        pipeline[0] = {'$match': {}}
    agg = list(db.transaksi_kasir.aggregate(pipeline))
    if not agg:
        return {'total': 0, 'lunas': 0, 'ordering': 0, 'total_nilai_lunas': 0}
    row = agg[0]
    total = int(row.get('total') or 0)
    ordering = int(row.get('ordering') or 0)
    return {
        'total': total,
        'lunas': total - ordering,
        'ordering': ordering,
        'total_nilai_lunas': int(row.get('total_nilai_lunas') or 0),
    }


def get_transaksi(id_pemesanan):
    db = get_db()
    doc = db.transaksi_kasir.find_one({'id_pemesanan': id_pemesanan})
    if not doc:
        doc = db.transaksi_kasir.find_one({'id_transaksi': id_pemesanan})
    if doc:
        _attach_pembayaran_info(doc)
    return doc


def _normalize_metode(metode):
    m = (metode or 'cash').strip().lower()
    if m in ('tunai', 'cash'):
        return 'cash'
    if m == 'qris':
        return 'qris'
    if m == 'debit':
        return 'debit'
    return m


def _attach_pembayaran_info(doc):
    metode = _normalize_metode(doc.get('metode_bayar'))
    info = pembayaran_service.get_by_metode(metode)
    if info:
        doc['info_pembayaran'] = {
            'label': info.get('label'),
            'nomor_rekening': info.get('nomor_rekening'),
            'nama_rekening': info.get('nama_rekening'),
            'gambar_url': info.get('gambar_url'),
            'keterangan': info.get('keterangan'),
        }


def _resep_gram_for_qty(resep_row, qty):
    """Hitung gram pemakaian dari baris resep × qty penjualan (dukung pcs)."""
    qty = int(qty or 0)
    if qty <= 0:
        return 0
    if (resep_row.get('satuan') or '').lower() == 'pcs' or resep_row.get('jumlah_pcs') is not None:
        pcs = float(resep_row.get('jumlah_pcs') or 0)
        gram_per = int(resep_row.get('gram_per_pcs') or 0)
        if pcs > 0 and gram_per > 0:
            return int(round(pcs * gram_per)) * qty
    return int(resep_row.get('jumlah_gram') or 0) * qty


def _aggregate_bahan_usage(items):
    usage = defaultdict(int)
    line_details = []
    for line in items:
        id_menu = (line.get('id_menu') or '').strip()
        qty = int(line.get('qty') or line.get('jumlah') or 0)
        if not id_menu or qty <= 0:
            raise ValueError('Item transaksi tidak valid')
        menu = menu_service.get_menu(id_menu)
        if not menu:
            raise ValueError(f'Produk {id_menu} tidak ditemukan')
        if menu.get('status') != 'aktif':
            raise ValueError(f'Produk {menu.get("nama_menu")} tidak aktif')

        subtotal = int(menu.get('harga_jual') or 0) * qty
        line_details.append({
            'id_menu': id_menu,
            'nama_menu': menu.get('nama_menu', ''),
            'harga_jual': int(menu.get('harga_jual') or 0),
            'qty': qty,
            'subtotal': subtotal,
        })

        for r in menu.get('bahan_resep') or []:
            bid = r.get('id_bahan')
            gram = _resep_gram_for_qty(r, qty)
            if bid and gram:
                usage[bid] += gram

    return line_details, dict(usage)


def _validate_stok(bahan_usage):
    bahan_map = bahan_service.get_bahan_many(list(bahan_usage.keys()))
    for bid, need in bahan_usage.items():
        bahan = bahan_map.get(bid)
        if not bahan:
            raise ValueError(f'Bahan {bid} tidak ditemukan')
        stok = int(bahan.get('stok_gram') or 0)
        if stok < need:
            raise ValueError(
                f'Stok {bahan.get("nama_bahan")} tidak cukup '
                f'(butuh {need} gram, tersedia {stok} gram)'
            )


def _deduct_stok(bahan_usage, tanggal, id_ref, session=None):
    bahan_map = bahan_service.get_bahan_many(list(bahan_usage.keys()))
    for bid, need in bahan_usage.items():
        bahan = bahan_map.get(bid)
        if not bahan:
            raise ValueError(f'Bahan {bid} tidak ditemukan')
        stok_sebelum = int(bahan.get('stok_gram') or 0)
        stok_sesudah = stok_sebelum - need
        bahan_service.update_stok(bid, stok_sesudah, session=session)
        stok_service.create_riwayat(
            {
                'id_bahan': bid,
                'nama_bahan': bahan.get('nama_bahan', ''),
                'tanggal': tanggal,
                'tipe': 'PEMAKAIAN',
                'jumlah_gram': -need,
                'stok_sebelum': stok_sebelum,
                'stok_sesudah': stok_sesudah,
                'id_referensi': id_ref,
                'keterangan': f'Penjualan {id_ref}',
            },
            session=session,
        )


def _usage_from_saved_items(items, require_aktif=False):
    """Hitung pemakaian bahan dari item tersimpan (untuk rollback/edit)."""
    usage = defaultdict(int)
    for line in items or []:
        id_menu = (line.get('id_menu') or '').strip()
        qty = int(line.get('qty') or line.get('jumlah') or 0)
        if not id_menu or qty <= 0:
            continue
        menu = menu_service.get_menu(id_menu)
        if not menu:
            continue
        if require_aktif and menu.get('status') != 'aktif':
            raise ValueError(f'Produk {menu.get("nama_menu")} tidak aktif')
        for r in menu.get('bahan_resep') or []:
            bid = r.get('id_bahan')
            gram = _resep_gram_for_qty(r, qty)
            if bid and gram:
                usage[bid] += gram
    return dict(usage)


def _restore_stok(bahan_usage, tanggal, id_ref, session=None):
    """Kembalikan stok saat penjualan dihapus/diedit."""
    if not bahan_usage:
        return
    bahan_map = bahan_service.get_bahan_many(list(bahan_usage.keys()))
    for bid, amount in bahan_usage.items():
        bahan = bahan_map.get(bid)
        if not bahan:
            continue
        add = int(amount or 0)
        if add <= 0:
            continue
        stok_sebelum = int(bahan.get('stok_gram') or 0)
        stok_sesudah = stok_sebelum + add
        bahan_service.update_stok(bid, stok_sesudah, session=session)
        stok_service.create_riwayat(
            {
                'id_bahan': bid,
                'nama_bahan': bahan.get('nama_bahan', ''),
                'tanggal': tanggal,
                'tipe': 'PENYESUAIAN',
                'jumlah_gram': add,
                'stok_sebelum': stok_sebelum,
                'stok_sesudah': stok_sesudah,
                'id_referensi': id_ref,
                'keterangan': f'Pembatalan/penyesuaian penjualan {id_ref}',
            },
            session=session,
        )


def _was_stock_applied(trans):
    return (trans.get('status_pembayaran') or '').strip().lower() != 'ordering'


def proses_transaksi(data):
    items = data.get('items') or []
    if not items:
        raise ValueError('Keranjang kosong')

    metode = _normalize_metode(data.get('metode_bayar'))
    status_pembayaran = (data.get('status_pembayaran') or 'lunas').strip().lower()
    if status_pembayaran not in ('lunas', 'ordering'):
        raise ValueError('Status pembayaran harus lunas atau ordering')

    catatan = (data.get('catatan') or '').strip()
    nama_pelanggan = (data.get('nama_pelanggan') or data.get('nama') or '').strip()
    tanggal = (data.get('tanggal') or datetime.now().strftime('%Y-%m-%d')).strip()
    petugas = _get_petugas(data.get('petugas_id'))

    line_details, bahan_usage = _aggregate_bahan_usage(items)
    total = sum(x['subtotal'] for x in line_details)
    if total <= 0:
        raise ValueError('Total transaksi harus lebih dari 0')

    if status_pembayaran == 'lunas':
        _validate_stok(bahan_usage)

    metode_label = {'cash': 'Cash', 'qris': 'QRIS', 'debit': 'Debit'}.get(metode, metode.upper())
    pay_info = pembayaran_service.get_by_metode(metode)

    def _execute(session=None, tracker=None):
        kwargs = {'session': session} if session else {}
        db = get_db()

        id_pemesanan = generate_id_pemesanan(tanggal.replace('-', ''))
        transaksi_doc = {
            'id_pemesanan': id_pemesanan,
            'id_transaksi': id_pemesanan,
            'tanggal': tanggal,
            'nama_pelanggan': nama_pelanggan,
            'petugas': petugas,
            'items': line_details,
            'total': total,
            'metode_bayar': metode_label,
            'metode_bayar_key': metode,
            'status_pembayaran': status_pembayaran,
            'catatan': catatan,
            'created_at': now_iso(),
        }
        if pay_info:
            transaksi_doc['info_pembayaran'] = {
                'label': pay_info.get('label'),
                'nomor_rekening': pay_info.get('nomor_rekening'),
                'nama_rekening': pay_info.get('nama_rekening'),
                'gambar_url': pay_info.get('gambar_url'),
            }

        if status_pembayaran == 'lunas':
            _deduct_stok(bahan_usage, tanggal, id_pemesanan, session=session)
            keterangan = ', '.join(f'{x["nama_menu"]} x{x["qty"]}' for x in line_details)
            pemasukan = pemasukan_service.create_pemasukan_kasir(
                tanggal,
                id_pemesanan,
                total,
                keterangan,
                session=session,
            )
            transaksi_doc['id_pemasukan'] = pemasukan['id_pemasukan']
            if tracker:
                tracker.track_insert('pemasukan', 'id_pemasukan', pemasukan['id_pemasukan'])

        db.transaksi_kasir.insert_one(transaksi_doc, **kwargs)
        if tracker:
            tracker.track_insert('transaksi_kasir', 'id_pemesanan', id_pemesanan)

        return transaksi_doc

    if status_pembayaran == 'lunas':
        result = pemasukan_service.run_in_transaction(_execute)
        _bust_read_caches()
        return result

    db = get_db()
    result = _execute()
    _bust_read_caches()
    return result


def lunasi_pemesanan(id_pemesanan):
    db = get_db()
    trans = get_transaksi(id_pemesanan)
    if not trans:
        raise ValueError('Penjualan tidak ditemukan')
    if trans.get('status_pembayaran') == 'lunas':
        raise ValueError('Penjualan sudah lunas')

    items = trans.get('items') or []
    bahan_usage = defaultdict(int)
    for line in items:
        menu = menu_service.get_menu(line.get('id_menu'))
        if not menu:
            continue
        qty = int(line.get('qty') or 0)
        for r in menu.get('bahan_resep') or []:
            bid = r.get('id_bahan')
            gram = _resep_gram_for_qty(r, qty)
            if bid and gram:
                bahan_usage[bid] += gram

    bahan_usage = dict(bahan_usage)
    _validate_stok(bahan_usage)

    tanggal = trans.get('tanggal') or datetime.now().strftime('%Y-%m-%d')
    total = int(trans.get('total') or 0)

    def _execute(session=None, tracker=None):
        _deduct_stok(bahan_usage, tanggal, id_pemesanan, session=session)
        keterangan = ', '.join(
            f'{x.get("nama_menu")} x{x.get("qty")}' for x in items
        )
        pemasukan = pemasukan_service.create_pemasukan_kasir(
            tanggal,
            id_pemesanan,
            total,
            keterangan,
            session=session,
        )
        db.transaksi_kasir.update_one(
            {'id_pemesanan': id_pemesanan},
            {'$set': {
                'status_pembayaran': 'lunas',
                'id_pemasukan': pemasukan['id_pemasukan'],
                'lunas_at': now_iso(),
            }},
            session=session,
        )
        if tracker:
            tracker.track_insert('pemasukan', 'id_pemasukan', pemasukan['id_pemasukan'])
        return get_transaksi(id_pemesanan)

    result = pemasukan_service.run_in_transaction(_execute)
    _bust_read_caches()
    return result


def update_transaksi(id_pemesanan, data):
    db = get_db()
    trans = get_transaksi(id_pemesanan)
    if not trans:
        raise ValueError('Penjualan tidak ditemukan')

    items = data.get('items') or []
    if not items:
        raise ValueError('Minimal satu produk terjual wajib diisi')

    catatan = (data.get('catatan') or '').strip()
    tanggal = (data.get('tanggal') or trans.get('tanggal') or datetime.now().strftime('%Y-%m-%d')).strip()
    petugas = _get_petugas(data.get('petugas_id') or (trans.get('petugas') or {}).get('id'))
    line_details, new_usage = _aggregate_bahan_usage(items)
    total = sum(x['subtotal'] for x in line_details)
    if total <= 0:
        raise ValueError('Total transaksi harus lebih dari 0')

    old_usage = _usage_from_saved_items(trans.get('items') or []) if _was_stock_applied(trans) else {}
    net_need = defaultdict(int)
    for bid, gram in new_usage.items():
        net_need[bid] += gram
    for bid, gram in old_usage.items():
        net_need[bid] -= gram
    need_validate = {bid: gram for bid, gram in net_need.items() if gram > 0}
    if need_validate:
        _validate_stok(need_validate)

    keterangan = ', '.join(f'{x["nama_menu"]} x{x["qty"]}' for x in line_details)

    def _execute(session=None, tracker=None):
        kwargs = {'session': session} if session else {}
        if old_usage:
            _restore_stok(old_usage, tanggal, id_pemesanan, session=session)
        if new_usage:
            _deduct_stok(new_usage, tanggal, id_pemesanan, session=session)

        update_fields = {
            'tanggal': tanggal,
            'petugas': petugas,
            'items': line_details,
            'total': total,
            'catatan': catatan,
            'status_pembayaran': 'lunas',
            'updated_at': now_iso(),
        }

        id_pemasukan = trans.get('id_pemasukan')
        if id_pemasukan:
            pemasukan_service.update_pemasukan_kasir(
                id_pemasukan, tanggal, total, keterangan, session=session
            )
        else:
            pemasukan = pemasukan_service.create_pemasukan_kasir(
                tanggal, id_pemesanan, total, keterangan, session=session
            )
            update_fields['id_pemasukan'] = pemasukan['id_pemasukan']
            if tracker:
                tracker.track_insert('pemasukan', 'id_pemasukan', pemasukan['id_pemasukan'])

        db.transaksi_kasir.update_one(
            {'id_pemesanan': id_pemesanan},
            {'$set': update_fields},
            **kwargs,
        )
        return get_transaksi(id_pemesanan)

    result = pemasukan_service.run_in_transaction(_execute)
    _bust_read_caches()
    return result


def delete_transaksi(id_pemesanan):
    db = get_db()
    trans = get_transaksi(id_pemesanan)
    if not trans:
        raise ValueError('Penjualan tidak ditemukan')

    tanggal = trans.get('tanggal') or datetime.now().strftime('%Y-%m-%d')
    old_usage = _usage_from_saved_items(trans.get('items') or []) if _was_stock_applied(trans) else {}

    def _execute(session=None, tracker=None):
        kwargs = {'session': session} if session else {}
        if old_usage:
            _restore_stok(old_usage, tanggal, id_pemesanan, session=session)
        pemasukan_service.delete_pemasukan_by_referensi(
            id_pemesanan, trans.get('id_pemasukan'), session=session
        )
        db.transaksi_kasir.delete_one({'id_pemesanan': id_pemesanan}, **kwargs)
        return {'id_pemesanan': id_pemesanan, 'deleted': True}

    result = pemasukan_service.run_in_transaction(_execute)
    _bust_read_caches()
    return result
