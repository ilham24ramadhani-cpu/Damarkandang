"""Laporan & rekapan transaksi cafe Damarkandang."""

from datetime import datetime, timedelta

from app.database import get_db
from app.utils.dates import bulan_bounds
from app.utils.unit_converter import total_harga_dari_gram


def _date_filter(bulan, tanggal_dari, tanggal_sampai):
    if tanggal_dari or tanggal_sampai:
        rng = {}
        if tanggal_dari:
            rng['$gte'] = tanggal_dari
        if tanggal_sampai:
            rng['$lte'] = tanggal_sampai
        return {'tanggal': rng}
    if bulan:
        dari, sampai = bulan_bounds(bulan)
        if dari and sampai:
            return {'tanggal': {'$gte': dari, '$lte': sampai}}
    return {}


def _period_bounds(periode, nilai):
    """Kembalikan (tanggal_dari, tanggal_sampai) ISO atau (None, None) untuk semua."""
    periode = (periode or 'semua').strip().lower()
    nilai = (nilai or '').strip()
    if periode == 'semua':
        return None, None
    if not nilai:
        return None, None
    if periode == 'bulanan':
        return bulan_bounds(nilai)
    if periode == 'tahunan':
        try:
            y = int(nilai[:4])
            return f'{y}-01-01', f'{y}-12-31'
        except ValueError:
            return None, None
    if periode == 'mingguan':
        try:
            if '-W' in nilai.upper():
                parts = nilai.upper().split('-W')
                y, w = int(parts[0]), int(parts[1])
            else:
                y, w = int(nilai[:4]), int(nilai[4:6]) if len(nilai) >= 6 else 1
            start = datetime.fromisocalendar(y, w, 1).date()
            end = start + timedelta(days=6)
            return start.isoformat(), end.isoformat()
        except (TypeError, ValueError):
            return None, None
    return None, None


def _riwayat_masuk_q(id_bahan=None, tanggal_dari=None, tanggal_sampai=None, id_bahans=None):
    q = {'tipe': {'$in': ['MASUK', 'PEMBELIAN']}}
    if id_bahans is not None:
        q['id_bahan'] = {'$in': list(id_bahans)}
    elif id_bahan:
        q['id_bahan'] = id_bahan
    if tanggal_dari and tanggal_sampai:
        q['tanggal'] = {'$gte': tanggal_dari, '$lte': tanggal_sampai}
    elif tanggal_dari:
        q['tanggal'] = {'$gte': tanggal_dari}
    elif tanggal_sampai:
        q['tanggal'] = {'$lte': tanggal_sampai}
    return q


def _batch_lookup_maps(db, events):
    """Prefetch pembelian & pengeluaran terkait agar tidak N+1 query."""
    refs_pembelian = []
    refs_masuk = []
    for ev in events:
        tipe = (ev.get('tipe') or '').upper()
        ref = (ev.get('id_referensi') or '').strip()
        if tipe == 'PEMBELIAN' and ref:
            refs_pembelian.append(ref)
        elif tipe == 'MASUK':
            bid = (ev.get('id_bahan') or '').strip()
            if bid:
                refs_masuk.append(bid)

    pembelian_map = {}
    if refs_pembelian:
        for p in db.pembelian.find(
            {'id_pembelian': {'$in': list(set(refs_pembelian))}},
            {'id_pembelian': 1, 'harga_per_kg': 1, 'harga_per_satuan': 1, 'total_harga': 1},
        ):
            pembelian_map[p['id_pembelian']] = p

    peng_map = {}
    or_clauses = []
    if refs_masuk:
        or_clauses.append({'sumber': 'Bahan Masuk', 'id_referensi': {'$in': list(set(refs_masuk))}})
    if refs_pembelian:
        or_clauses.append({'sumber': 'Pembelian Bahan', 'id_referensi': {'$in': list(set(refs_pembelian))}})
    if or_clauses:
        for pg in db.pengeluaran.find(
            {'$or': or_clauses},
            {'sumber': 1, 'id_referensi': 1, 'nominal': 1},
        ):
            key = f"{pg.get('sumber')}|{pg.get('id_referensi')}"
            peng_map[key] = int(pg.get('nominal') or 0)

    return pembelian_map, peng_map


def _event_financials_cached(bahan, event, pembelian_map, peng_map):
    """Hitung gram/harga/nominal dari map prefetch (tanpa query tambahan)."""
    bid = bahan.get('id_bahan')
    tipe = (event.get('tipe') or '').upper()
    ref = (event.get('id_referensi') or '').strip()
    gram = int(event.get('jumlah_gram') or 0)
    harga_kg = int(bahan.get('harga_per_kg') or bahan.get('harga_terakhir') or 0)
    nominal = 0

    if tipe == 'MASUK':
        nominal = int(peng_map.get(f'Bahan Masuk|{bid}') or 0)
        if not nominal and harga_kg > 0:
            nominal = total_harga_dari_gram(harga_kg, gram)
    elif tipe == 'PEMBELIAN' and ref:
        pem = pembelian_map.get(ref) or {}
        if pem:
            harga_kg = int(pem.get('harga_per_kg') or pem.get('harga_per_satuan') or harga_kg)
        nominal = int(peng_map.get(f'Pembelian Bahan|{ref}') or 0)
        if not nominal and pem:
            nominal = int(pem.get('total_harga') or 0)

    return gram, harga_kg, nominal


def get_laporan_bahan_masuk(periode='semua', nilai='', id_jenis='', page=1, per_page=500):
    """Rekap bahan masuk — batch query (hindari N+1 per bahan/event)."""
    db = get_db()
    tanggal_dari, tanggal_sampai = _period_bounds(periode, nilai)
    bahan_q = {'id_bahan': {'$exists': True}}
    if id_jenis:
        bahan_q['id_jenis'] = id_jenis.strip()

    bahan_list = list(db.bahan.find(
        bahan_q,
        {
            'id_bahan': 1, 'id_jenis': 1, 'nama_jenis': 1, 'nama_bahan': 1,
            'harga_per_kg': 1, 'harga_terakhir': 1, 'stok_gram': 1, 'status': 1,
        },
    ).sort('id_bahan', 1))
    if not bahan_list:
        return [], 0

    bahan_by_id = {b['id_bahan']: b for b in bahan_list if b.get('id_bahan')}
    ids = list(bahan_by_id.keys())

    events = list(db.riwayat_stok.find(
        _riwayat_masuk_q(id_bahans=ids, tanggal_dari=tanggal_dari, tanggal_sampai=tanggal_sampai),
        {
            'id_bahan': 1, 'tipe': 1, 'jumlah_gram': 1, 'tanggal': 1,
            'id_referensi': 1, 'stok_sebelum': 1, 'stok_sesudah': 1, 'keterangan': 1,
            'id_riwayat': 1,
        },
    ).sort([('id_bahan', 1), ('tanggal', 1)]))

    # Fallback: jika filter periode kosong, ambil semua (hanya mode semua)
    if not events and periode == 'semua':
        events = list(db.riwayat_stok.find(
            _riwayat_masuk_q(id_bahans=ids),
            {
                'id_bahan': 1, 'tipe': 1, 'jumlah_gram': 1, 'tanggal': 1,
                'id_referensi': 1, 'stok_sebelum': 1, 'stok_sesudah': 1, 'keterangan': 1,
                'id_riwayat': 1,
            },
        ).sort([('id_bahan', 1), ('tanggal', 1)]))

    events_by_bahan = {}
    for ev in events:
        bid = ev.get('id_bahan')
        if bid:
            events_by_bahan.setdefault(bid, []).append(ev)

    pembelian_map, peng_map = _batch_lookup_maps(db, events)
    rows = []

    for bid, events_b in events_by_bahan.items():
        bahan = bahan_by_id.get(bid)
        if not bahan:
            continue
        total_gram = 0
        total_peng = 0
        harga_weighted_sum = 0
        harga_max = 0
        for ev in events_b:
            gram, harga_kg, nominal = _event_financials_cached(bahan, ev, pembelian_map, peng_map)
            total_gram += gram
            total_peng += nominal
            if gram > 0 and harga_kg > 0:
                harga_weighted_sum += harga_kg * gram
            if harga_kg > harga_max:
                harga_max = harga_kg

        harga_avg = int(round(harga_weighted_sum / total_gram)) if total_gram > 0 else int(
            bahan.get('harga_per_kg') or 0
        )
        rows.append({
            'id_bahan': bid,
            'id_jenis': bahan.get('id_jenis', ''),
            'nama_jenis': bahan.get('nama_jenis') or bahan.get('nama_bahan', ''),
            'jumlah_gram': total_gram,
            'jumlah_kg': round(total_gram / 1000, 3),
            'harga_per_kg': harga_avg,
            'harga_per_kg_max': harga_max or harga_avg,
            'total_pengeluaran': total_peng,
            'tanggal_masuk': events_b[0].get('tanggal', ''),
            'tanggal_terakhir': events_b[-1].get('tanggal', ''),
            'jumlah_transaksi': len(events_b),
            'stok_gram': int(bahan.get('stok_gram') or 0),
            'status': bahan.get('status', 'aktif'),
        })

    rows.sort(key=lambda r: r.get('id_bahan') or '')
    total = len(rows)
    skip = (page - 1) * per_page
    return rows[skip:skip + per_page], total


def get_detail_bahan_masuk(id_bahan, periode='semua', nilai=''):
    db = get_db()
    bahan = db.bahan.find_one({'id_bahan': id_bahan})
    if not bahan:
        return None

    tanggal_dari, tanggal_sampai = _period_bounds(periode, nilai)
    events = list(
        db.riwayat_stok.find(_riwayat_masuk_q(id_bahan, tanggal_dari, tanggal_sampai)).sort('tanggal', 1)
    )
    if not events and periode == 'semua':
        events = list(db.riwayat_stok.find(_riwayat_masuk_q(id_bahan)).sort('tanggal', 1))

    pembelian_map, peng_map = _batch_lookup_maps(db, events)
    detail_rows = []
    total_gram = 0
    total_peng = 0

    for ev in events:
        gram, harga_kg, nominal = _event_financials_cached(bahan, ev, pembelian_map, peng_map)
        total_gram += gram
        total_peng += nominal
        detail_rows.append({
            'id_riwayat': ev.get('id_riwayat'),
            'tanggal': ev.get('tanggal'),
            'tipe': ev.get('tipe'),
            'jumlah_gram': gram,
            'jumlah_kg': round(gram / 1000, 3),
            'harga_per_kg': harga_kg,
            'total_pengeluaran': nominal,
            'stok_sebelum': int(ev.get('stok_sebelum') or 0),
            'stok_sesudah': int(ev.get('stok_sesudah') or 0),
            'keterangan': ev.get('keterangan') or '',
            'id_referensi': ev.get('id_referensi') or '',
        })

    return {
        'bahan': {
            'id_bahan': id_bahan,
            'id_jenis': bahan.get('id_jenis'),
            'nama_jenis': bahan.get('nama_jenis') or bahan.get('nama_bahan'),
            'stok_gram': int(bahan.get('stok_gram') or 0),
            'harga_per_kg': int(bahan.get('harga_per_kg') or 0),
        },
        'periode': {'mode': periode, 'nilai': nilai, 'dari': tanggal_dari, 'sampai': tanggal_sampai},
        'ringkasan': {
            'jumlah_transaksi': len(detail_rows),
            'total_gram': total_gram,
            'total_kg': round(total_gram / 1000, 3),
            'total_pengeluaran': total_peng,
        },
        'items': detail_rows,
    }


def ringkasan_bahan_masuk(periode='semua', nilai='', id_jenis=''):
    rows, total = get_laporan_bahan_masuk(periode, nilai, id_jenis, page=1, per_page=10000)
    if not rows:
        return {
            'jumlah_bahan': 0,
            'jumlah_transaksi': 0,
            'total_gram': 0,
            'total_pengeluaran': 0,
            'rata_rata_harga_kg': 0,
            'harga_maksimum_kg': 0,
            'bahan_harga_maksimum': '-',
        }

    total_gram = sum(r['jumlah_gram'] for r in rows)
    total_peng = sum(r['total_pengeluaran'] for r in rows)
    weighted = sum(r['harga_per_kg'] * r['jumlah_gram'] for r in rows if r['jumlah_gram'] > 0)
    rata_harga = int(round(weighted / total_gram)) if total_gram > 0 else 0
    max_row = max(rows, key=lambda r: r.get('harga_per_kg_max') or 0)
    jumlah_transaksi = sum(r['jumlah_transaksi'] for r in rows)

    return {
        'jumlah_bahan': total,
        'jumlah_transaksi': jumlah_transaksi,
        'total_gram': total_gram,
        'total_kg': round(total_gram / 1000, 3),
        'total_pengeluaran': total_peng,
        'rata_rata_harga_kg': rata_harga,
        'harga_maksimum_kg': max_row.get('harga_per_kg_max') or 0,
        'bahan_harga_maksimum': f"{max_row.get('nama_jenis')} ({max_row.get('id_bahan')})",
    }


def _penjualan_query(bulan=None, tanggal_dari=None, tanggal_sampai=None, id_menu=None, petugas_id=None):
    """Filter penjualan selaras data tambah: tanggal, petugas, produk terjual."""
    q = dict(_date_filter(bulan, tanggal_dari, tanggal_sampai))
    petugas = (petugas_id or '').strip()
    if petugas:
        q['petugas.id'] = petugas
    menu = (id_menu or '').strip()
    if menu:
        q['items.id_menu'] = menu
    return q


def get_opsi_filter_penjualan():
    """Dropdown produk & petugas untuk laporan penjualan."""
    from app.services import kasir_service

    db = get_db()
    petugas = kasir_service.list_petugas()
    menus = list(
        db.menu.find({}, {'id_menu': 1, 'nama_menu': 1, 'kategori': 1, 'status': 1, '_id': 0}).sort('nama_menu', 1)
    )
    menu_ids = {m.get('id_menu') for m in menus if m.get('id_menu')}
    sold_ids = set()

    for row in db.transaksi_kasir.aggregate([
        {'$unwind': '$items'},
        {'$group': {
            '_id': '$items.id_menu',
            'nama_menu': {'$first': '$items.nama_menu'},
        }},
    ]):
        mid = str(row.get('_id') or '').strip()
        if not mid:
            continue
        sold_ids.add(mid)
        if mid not in menu_ids:
            menus.append({
                'id_menu': mid,
                'nama_menu': row.get('nama_menu') or mid,
                'kategori': '',
                'status': 'hapus',
            })
            menu_ids.add(mid)

    for m in menus:
        m['pernah_terjual'] = m.get('id_menu') in sold_ids

    menus.sort(key=lambda x: (x.get('nama_menu') or '').lower())
    return {'petugas': petugas, 'produk': menus}


def get_opsi_filter_laporan():
    """Semua opsi filter laporan — di-cache singkat agar tab laporan tidak berat."""
    from app.utils.cache import cached
    return cached('laporan:opsi', 45, _get_opsi_filter_laporan_uncached)


def _get_opsi_filter_laporan_uncached():
    from app.services import jenis_keuangan_service

    db = get_db()
    opsi = get_opsi_filter_penjualan()
    bahan = list(db.bahan.find(
        {'id_bahan': {'$exists': True}},
        {'id_bahan': 1, 'nama_bahan': 1, 'nama_jenis': 1, 'id_jenis': 1, 'status': 1, '_id': 0},
    ).sort('id_bahan', 1))
    opsi['bahan'] = bahan
    opsi['jenis_pemasukan'] = [
        j.get('nama_jenis') for j in jenis_keuangan_service.list_jenis_pemasukan() if j.get('nama_jenis')
    ]
    opsi['jenis_pengeluaran'] = [
        j.get('nama_jenis') for j in jenis_keuangan_service.list_jenis_pengeluaran() if j.get('nama_jenis')
    ]
    opsi['sumber_pemasukan'] = sorted([x for x in db.pemasukan.distinct('sumber') if x])
    opsi['sumber_pengeluaran'] = sorted([x for x in db.pengeluaran.distinct('sumber') if x])
    opsi['tipe_stok'] = ['MASUK', 'PEMBELIAN', 'PEMAKAIAN', 'PENYESUAIAN']
    return opsi


def _keuangan_q(date_q, jenis_keu=None, sumber=None):
    q = dict(date_q or {})
    if sumber:
        q['sumber'] = sumber
    if jenis_keu:
        q['$or'] = [{'jenis': jenis_keu}, {'kategori': jenis_keu}]
    return q


def _sum_match(collection, q, field):
    pipeline = [
        {'$match': q or {}},
        {'$group': {'_id': None, 'total': {'$sum': {'$ifNull': [f'${field}', 0]}}, 'count': {'$sum': 1}}},
    ]
    rows = list(collection.aggregate(pipeline))
    if not rows:
        return 0, 0
    return int(rows[0].get('total') or 0), int(rows[0].get('count') or 0)


def _rekap_jenis_keuangan(collection, q):
    pipeline = [
        {'$match': q or {}},
        {'$group': {
            '_id': {'$ifNull': ['$jenis', {'$ifNull': ['$kategori', '-']}]},
            'total': {'$sum': {'$ifNull': ['$nominal', 0]}},
            'jumlah': {'$sum': 1},
        }},
        {'$sort': {'total': -1, '_id': 1}},
    ]
    return [
        {'jenis': r.get('_id') or '-', 'jumlah': int(r.get('jumlah') or 0), 'total': int(r.get('total') or 0)}
        for r in collection.aggregate(pipeline)
    ]


def ringkasan_pembelian(bulan=None, tanggal_dari=None, tanggal_sampai=None, id_bahan=None):
    db = get_db()
    q = dict(_date_filter(bulan, tanggal_dari, tanggal_sampai))
    if id_bahan:
        q['id_bahan'] = id_bahan
    total_harga, jumlah = _sum_match(db.pembelian, q, 'total_harga')
    total_gram, _ = _sum_match(db.pembelian, q, 'jumlah_gram')
    bahan_ids = db.pembelian.distinct('id_bahan', q)
    return {
        'jumlah_transaksi': jumlah,
        'jumlah_bahan': len([x for x in bahan_ids if x]),
        'total_gram': int(total_gram),
        'total_kg': round(int(total_gram) / 1000, 3),
        'total_harga': int(total_harga),
    }


def ringkasan_keuangan(bulan=None, tanggal_dari=None, tanggal_sampai=None, jenis_keu=None, sumber=None, arus=None):
    db = get_db()
    date_q = _date_filter(bulan, tanggal_dari, tanggal_sampai)
    arus = (arus or 'semua').strip().lower()
    q = _keuangan_q(date_q, jenis_keu, sumber)

    pemasukan_total, pemasukan_n = (0, 0) if arus == 'pengeluaran' else _sum_match(db.pemasukan, q, 'nominal')
    pengeluaran_total, pengeluaran_n = (0, 0) if arus == 'pemasukan' else _sum_match(db.pengeluaran, q, 'nominal')

    rekap = []
    if arus != 'pengeluaran':
        for r in _rekap_jenis_keuangan(db.pemasukan, q):
            rekap.append({**r, 'arus': 'Pemasukan'})
    if arus != 'pemasukan':
        for r in _rekap_jenis_keuangan(db.pengeluaran, q):
            rekap.append({**r, 'arus': 'Pengeluaran'})

    return {
        'jumlah_pemasukan': pemasukan_n,
        'jumlah_pengeluaran': pengeluaran_n,
        'total_pemasukan': pemasukan_total,
        'total_pengeluaran': pengeluaran_total,
        'selisih': pemasukan_total - pengeluaran_total,
        'rekap_jenis': rekap,
    }


def ringkasan_stok_saat_ini():
    from app.services import bahan_service

    rows = bahan_service.list_stok_by_jenis()
    normal = sum(1 for r in rows if r.get('stok_status') not in ('menipis', 'habis'))
    menipis = sum(1 for r in rows if r.get('stok_status') == 'menipis')
    habis = sum(1 for r in rows if r.get('stok_status') == 'habis')
    total_gram = sum(int(r.get('stok_gram') or 0) for r in rows)
    return {
        'snapshot': rows,
        'jumlah_jenis': len(rows),
        'stok_normal': normal,
        'stok_menipis': menipis,
        'stok_habis': habis,
        'total_gram': total_gram,
        'total_kg': round(total_gram / 1000, 3),
    }


def ringkasan_riwayat_stok(bulan=None, tanggal_dari=None, tanggal_sampai=None, id_bahan=None, tipe=None):
    db = get_db()
    q = dict(_date_filter(bulan, tanggal_dari, tanggal_sampai))
    if id_bahan:
        q['id_bahan'] = id_bahan
    if tipe:
        q['tipe'] = tipe.upper()
    total = db.riwayat_stok.count_documents(q)
    pipeline = [
        {'$match': q},
        {'$group': {
            '_id': '$tipe',
            'jumlah': {'$sum': 1},
            'total_gram': {'$sum': {'$ifNull': ['$jumlah_gram', 0]}},
        }},
        {'$sort': {'_id': 1}},
    ]
    per_tipe = [
        {'tipe': r.get('_id') or '-', 'jumlah': int(r.get('jumlah') or 0), 'total_gram': int(r.get('total_gram') or 0)}
        for r in db.riwayat_stok.aggregate(pipeline)
    ]
    masuk = sum(r['total_gram'] for r in per_tipe if r['tipe'] in ('MASUK', 'PEMBELIAN'))
    keluar = sum(abs(r['total_gram']) for r in per_tipe if r['tipe'] == 'PEMAKAIAN')
    return {
        'jumlah_transaksi': total,
        'total_masuk_gram': int(masuk),
        'total_keluar_gram': int(keluar),
        'per_tipe': per_tipe,
    }


def get_laporan_keuangan(bulan=None, tanggal_dari=None, tanggal_sampai=None, jenis_keu=None, sumber=None, arus=None, page=1, per_page=500):
    db = get_db()
    date_q = _date_filter(bulan, tanggal_dari, tanggal_sampai)
    arus = (arus or 'semua').strip().lower()
    skip = (page - 1) * per_page
    sort_spec = [('tanggal', -1), ('created_at', -1)]
    proj = {
        'id_pemasukan': 1, 'id_pengeluaran': 1, 'tanggal': 1, 'jenis': 1, 'kategori': 1,
        'sumber': 1, 'nominal': 1, 'id_referensi': 1, 'keterangan': 1, 'created_at': 1,
    }

    if arus == 'pemasukan':
        q = _keuangan_q(date_q, jenis_keu, sumber)
        total = db.pemasukan.count_documents(q)
        items = list(db.pemasukan.find(q, proj).sort(sort_spec).skip(skip).limit(per_page))
        for doc in items:
            doc['arus'] = 'Pemasukan'
            doc['id_dokumen'] = doc.get('id_pemasukan')
            if not doc.get('jenis'):
                doc['jenis'] = 'Penjualan' if (doc.get('sumber') or '').lower() in ('kasir', 'pemesanan', 'penjualan') else '-'
        return items, total, 'keuangan'

    if arus == 'pengeluaran':
        q = _keuangan_q(date_q, jenis_keu, sumber)
        total = db.pengeluaran.count_documents(q)
        items = list(db.pengeluaran.find(q, proj).sort(sort_spec).skip(skip).limit(per_page))
        for doc in items:
            doc['arus'] = 'Pengeluaran'
            doc['id_dokumen'] = doc.get('id_pengeluaran')
            if not doc.get('jenis'):
                doc['jenis'] = doc.get('kategori') or '-'
        return items, total, 'keuangan'

    # Gabungan: ambil cukup baris dari tiap koleksi lalu merge (hindari load full table)
    q = _keuangan_q(date_q, jenis_keu, sumber)
    take = skip + per_page
    items = []
    for doc in db.pemasukan.find(q, proj).sort(sort_spec).limit(take):
        doc['arus'] = 'Pemasukan'
        doc['id_dokumen'] = doc.get('id_pemasukan')
        if not doc.get('jenis'):
            doc['jenis'] = 'Penjualan' if (doc.get('sumber') or '').lower() in ('kasir', 'pemesanan', 'penjualan') else '-'
        items.append(doc)
    for doc in db.pengeluaran.find(q, proj).sort(sort_spec).limit(take):
        doc['arus'] = 'Pengeluaran'
        doc['id_dokumen'] = doc.get('id_pengeluaran')
        if not doc.get('jenis'):
            doc['jenis'] = doc.get('kategori') or '-'
        items.append(doc)

    items.sort(key=lambda x: (x.get('tanggal') or '', x.get('created_at') or ''), reverse=True)
    total = db.pemasukan.count_documents(q) + db.pengeluaran.count_documents(q)
    return items[skip:skip + per_page], total, 'keuangan'


def rekap_produk_terjual(bulan=None, tanggal_dari=None, tanggal_sampai=None, id_menu=None, petugas_id=None):
    db = get_db()
    q = _penjualan_query(bulan, tanggal_dari, tanggal_sampai, None, petugas_id)
    pipeline = [
        {'$match': q},
        {'$unwind': '$items'},
    ]
    menu = (id_menu or '').strip()
    if menu:
        pipeline.append({'$match': {'items.id_menu': menu}})
    pipeline.extend([
        {'$group': {
            '_id': '$items.id_menu',
            'nama_menu': {'$first': '$items.nama_menu'},
            'qty': {'$sum': {'$ifNull': ['$items.qty', {'$ifNull': ['$items.jumlah', 0]}]}},
            'total': {'$sum': {'$ifNull': [
                '$items.subtotal',
                {'$multiply': [
                    {'$ifNull': ['$items.harga_jual', 0]},
                    {'$ifNull': ['$items.qty', {'$ifNull': ['$items.jumlah', 0]}]},
                ]},
            ]}},
        }},
        {'$sort': {'total': -1, 'nama_menu': 1}},
    ])
    rows = []
    for r in db.transaksi_kasir.aggregate(pipeline):
        rows.append({
            'id_menu': r.get('_id') or '',
            'nama_menu': r.get('nama_menu') or (r.get('_id') or '-'),
            'qty': int(r.get('qty') or 0),
            'total': int(r.get('total') or 0),
        })
    return rows


def ringkasan_penjualan(bulan=None, tanggal_dari=None, tanggal_sampai=None, id_menu=None, petugas_id=None):
    db = get_db()
    q = _penjualan_query(bulan, tanggal_dari, tanggal_sampai, id_menu, petugas_id)
    jumlah_transaksi = db.transaksi_kasir.count_documents(q)
    rekap = rekap_produk_terjual(bulan, tanggal_dari, tanggal_sampai, id_menu, petugas_id)
    jumlah_qty = sum(r['qty'] for r in rekap)
    total_item = sum(r['total'] for r in rekap)

    if (id_menu or '').strip():
        total_pemasukan = total_item
    else:
        pipeline = [
            {'$match': q},
            {'$group': {'_id': None, 'total': {'$sum': {'$ifNull': ['$total', 0]}}}},
        ]
        agg = list(db.transaksi_kasir.aggregate(pipeline))
        total_pemasukan = int(agg[0]['total']) if agg else 0

    petugas_ids = db.transaksi_kasir.distinct('petugas.id', q)

    return {
        'jumlah_transaksi': jumlah_transaksi,
        'total_pemasukan': int(total_pemasukan),
        'jumlah_qty': int(jumlah_qty),
        'jumlah_jenis_produk': len(rekap),
        'jumlah_petugas': len([x for x in petugas_ids if x]),
        'rekap_produk': rekap,
    }


def get_laporan(
    jenis,
    bulan=None,
    tanggal_dari=None,
    tanggal_sampai=None,
    page=1,
    per_page=500,
    id_menu=None,
    petugas_id=None,
    id_bahan=None,
    jenis_keuangan=None,
    sumber=None,
    tipe=None,
    arus=None,
):
    db = get_db()
    jenis = (jenis or 'pemesanan').strip().lower()
    date_q = _date_filter(bulan, tanggal_dari, tanggal_sampai)
    skip = (page - 1) * per_page
    id_bahan = (id_bahan or '').strip() or None
    jenis_keuangan = (jenis_keuangan or '').strip() or None
    sumber = (sumber or '').strip() or None
    tipe = (tipe or '').strip() or None

    if jenis == 'pembelian':
        q = {**date_q}
        if id_bahan:
            q['id_bahan'] = id_bahan
        total = db.pembelian.count_documents(q)
        items = list(db.pembelian.find(q).sort([('tanggal', -1), ('created_at', -1)]).skip(skip).limit(per_page))
        return items, total, 'pembelian'

    if jenis == 'keuangan':
        return get_laporan_keuangan(
            bulan, tanggal_dari, tanggal_sampai, jenis_keuangan, sumber, arus, page, per_page
        )

    if jenis == 'pemasukan':
        q = _keuangan_q(date_q, jenis_keuangan, sumber)
        total = db.pemasukan.count_documents(q)
        items = list(db.pemasukan.find(q).sort([('tanggal', -1), ('created_at', -1)]).skip(skip).limit(per_page))
        for item in items:
            item['arus'] = 'Pemasukan'
            if not item.get('jenis'):
                item['jenis'] = 'Penjualan' if (item.get('sumber') or '').lower() in ('kasir', 'pemesanan', 'penjualan') else '-'
        return items, total, 'pemasukan'

    if jenis == 'pengeluaran':
        q = _keuangan_q(date_q, jenis_keuangan, sumber)
        total = db.pengeluaran.count_documents(q)
        items = list(db.pengeluaran.find(q).sort([('tanggal', -1), ('created_at', -1)]).skip(skip).limit(per_page))
        for item in items:
            item['arus'] = 'Pengeluaran'
            if not item.get('jenis'):
                item['jenis'] = item.get('kategori') or '-'
        return items, total, 'pengeluaran'

    if jenis in ('stok', 'penyesuaian'):
        q = {**date_q}
        if id_bahan:
            q['id_bahan'] = id_bahan
        if jenis == 'penyesuaian':
            q['tipe'] = 'PENYESUAIAN'
        elif tipe:
            q['tipe'] = tipe.upper()
        total = db.riwayat_stok.count_documents(q)
        items = list(db.riwayat_stok.find(q).sort([('tanggal', -1), ('created_at', -1)]).skip(skip).limit(per_page))
        return items, total, jenis

    q = _penjualan_query(bulan, tanggal_dari, tanggal_sampai, id_menu, petugas_id)
    total = db.transaksi_kasir.count_documents(q)
    items = list(db.transaksi_kasir.find(q).sort([('tanggal', -1), ('created_at', -1)]).skip(skip).limit(per_page))
    return items, total, 'pemesanan'


def ringkasan_laporan(bulan=None, tanggal_dari=None, tanggal_sampai=None):
    db = get_db()
    date_q = _date_filter(bulan, tanggal_dari, tanggal_sampai)

    def _sum(col, field='nominal'):
        pipeline = [
            {'$match': date_q},
            {'$group': {'_id': None, 'total': {'$sum': f'${field}'}}},
        ]
        r = list(db[col].aggregate(pipeline))
        return int(r[0]['total']) if r else 0

    pembelian_total = _sum('pembelian', 'total_harga')
    pemasukan_total = _sum('pemasukan', 'nominal')
    pengeluaran_total = _sum('pengeluaran', 'nominal')
    jumlah_pemesanan = db.transaksi_kasir.count_documents(date_q)
    jumlah_ordering = db.transaksi_kasir.count_documents({**date_q, 'status_pembayaran': 'ordering'})

    return {
        'total_pembelian': pembelian_total,
        'total_pemasukan': pemasukan_total,
        'total_pengeluaran': pengeluaran_total,
        'jumlah_pemesanan': jumlah_pemesanan,
        'jumlah_ordering': jumlah_ordering,
        'selisih': pemasukan_total - pengeluaran_total,
    }
