from datetime import datetime
from cafe.database import get_db
from cafe.services import bahan_service, keuangan_service, pemasukan_service, pembelian_service, kasir_service
from cafe.utils.cache import cached
from cafe.utils.dates import bulan_query


def get_dashboard_stats():
    """Stats dashboard — agregasi ringan + cache singkat."""
    bulan = datetime.now().strftime('%Y-%m')
    return cached(f'dashboard_stats:{bulan}', 20, lambda: _build_dashboard_stats(bulan))


def _build_dashboard_stats(bulan):
    db = get_db()
    total_jenis = db.jenis_bahan.count_documents({'id_jenis': {'$exists': True}})
    total_bahan_aktif = db.bahan.count_documents({'id_bahan': {'$exists': True}, 'status': 'aktif'})
    total_menu_aktif = db.menu.count_documents({'status': 'aktif'})

    # Agregasi stok tanpa load 10k dokumen
    stok_agg = list(db.bahan.aggregate([
        {'$match': {'id_bahan': {'$exists': True}, 'status': 'aktif'}},
        {'$group': {
            '_id': None,
            'total_stok': {'$sum': {'$ifNull': ['$stok_gram', 0]}},
            'menipis': {
                '$sum': {
                    '$cond': [
                        {'$and': [
                            {'$gt': [{'$ifNull': ['$stok_gram', 0]}, 0]},
                            {'$lt': [{'$ifNull': ['$stok_gram', 0]}, 1000]},
                        ]},
                        1, 0,
                    ]
                }
            },
            'habis': {
                '$sum': {
                    '$cond': [{'$lte': [{'$ifNull': ['$stok_gram', 0]}, 0]}, 1, 0]
                }
            },
        }},
    ]))
    stok_row = stok_agg[0] if stok_agg else {}
    total_stok = int(stok_row.get('total_stok') or 0)
    menipis_count = int(stok_row.get('menipis') or 0)
    habis_count = int(stok_row.get('habis') or 0)

    # Hanya 10 bahan menipis (proyeksi ringan)
    menipis_list = list(db.bahan.find(
        {
            'id_bahan': {'$exists': True},
            'status': 'aktif',
            'stok_gram': {'$gt': 0, '$lt': 1000},
        },
        {'id_bahan': 1, 'nama_bahan': 1, 'nama_jenis': 1, 'stok_gram': 1},
    ).sort('stok_gram', 1).limit(10))
    for b in menipis_list:
        code, label = bahan_service.stok_status(b.get('stok_gram'))
        b['stok_status'] = code
        b['stok_status_label'] = label

    total_pembelian = pembelian_service.total_pembelian_bulan(bulan)
    total_pengeluaran_bahan = keuangan_service.total_pengeluaran_bahan_baku_bulan(bulan)
    total_pemasukan = pemasukan_service.total_pemasukan_bulan(bulan)
    total_pengeluaran_all = _total_pengeluaran_bulan(bulan)

    pembelian_terbaru, _ = pembelian_service.list_pembelian(page=1, per_page=5)
    pengeluaran_terbaru, _ = keuangan_service.list_pengeluaran(page=1, per_page=5)
    transaksi_terbaru, _ = kasir_service.list_transaksi(page=1, per_page=5)

    return {
        'total_jenis_bahan': total_jenis,
        'total_bahan_aktif': total_bahan_aktif,
        'total_menu_aktif': total_menu_aktif,
        'total_stok_gram': total_stok,
        'bahan_stok_menipis_count': menipis_count,
        'bahan_stok_habis_count': habis_count,
        'total_pembelian_bulan': total_pembelian,
        'total_pengeluaran_bahan_baku_bulan': total_pengeluaran_bahan,
        'total_pengeluaran_bulan': total_pengeluaran_all,
        'total_pemasukan_bulan': total_pemasukan,
        'laba_kotor_bulan': total_pemasukan - total_pengeluaran_all,
        'bahan_stok_menipis': menipis_list,
        'pembelian_terbaru': pembelian_terbaru,
        'pengeluaran_terbaru': pengeluaran_terbaru,
        'transaksi_terbaru': transaksi_terbaru,
    }


def _total_pengeluaran_bulan(bulan):
    db = get_db()
    pipeline = [
        {'$match': bulan_query(bulan)},
        {'$group': {'_id': None, 'total': {'$sum': '$nominal'}}},
    ]
    result = list(db.pengeluaran.aggregate(pipeline))
    return int(result[0]['total']) if result else 0
