from flask import Blueprint, request
from app.services import laporan_service
from app.utils.response import error_response, success_response

laporan_bp = Blueprint('laporan_api', __name__)


def _filter_params():
    return {
        'periode': (request.args.get('periode') or 'semua').strip(),
        'nilai': (request.args.get('nilai') or '').strip(),
        'id_jenis': (request.args.get('id_jenis') or '').strip(),
        'bulan': (request.args.get('bulan') or '').strip() or None,
        'tanggal_dari': (request.args.get('tanggal_dari') or '').strip() or None,
        'tanggal_sampai': (request.args.get('tanggal_sampai') or '').strip() or None,
        'id_menu': (request.args.get('id_menu') or request.args.get('produk') or '').strip() or None,
        'petugas_id': (request.args.get('petugas_id') or request.args.get('petugas') or '').strip() or None,
        'id_bahan': (request.args.get('id_bahan') or '').strip() or None,
        'jenis_keuangan': (request.args.get('jenis_keuangan') or '').strip() or None,
        'sumber': (request.args.get('sumber') or '').strip() or None,
        'tipe': (request.args.get('tipe') or '').strip() or None,
        'arus': (request.args.get('arus') or 'semua').strip() or 'semua',
        'page': max(int(request.args.get('page', 1) or 1), 1),
        'per_page': min(max(int(request.args.get('per_page', 500) or 500), 1), 1000),
    }


@laporan_bp.route('/api/laporan/bahan-masuk', methods=['GET'])
def laporan_bahan_masuk():
    try:
        p = _filter_params()
        items, total = laporan_service.get_laporan_bahan_masuk(
            p['periode'], p['nilai'], p['id_jenis'], p['page'], p['per_page']
        )
        ringkasan = laporan_service.ringkasan_bahan_masuk(p['periode'], p['nilai'], p['id_jenis'])
        return success_response('OK', {
            'items': items,
            'total': total,
            'page': p['page'],
            'per_page': p['per_page'],
            'ringkasan': ringkasan,
            'periode': p['periode'],
            'nilai': p['nilai'],
        })
    except Exception as e:
        return error_response('Gagal memuat laporan bahan masuk', str(e), 500)


@laporan_bp.route('/api/laporan/bahan-masuk/<id_bahan>/detail', methods=['GET'])
def detail_bahan_masuk(id_bahan):
    try:
        p = _filter_params()
        data = laporan_service.get_detail_bahan_masuk(id_bahan, p['periode'], p['nilai'])
        if not data:
            return error_response('Bahan tidak ditemukan', 'Not found', 404)
        return success_response('OK', data)
    except Exception as e:
        return error_response('Gagal memuat detail laporan', str(e), 500)


@laporan_bp.route('/api/laporan/opsi', methods=['GET'])
@laporan_bp.route('/api/laporan/penjualan/opsi', methods=['GET'])
def opsi_filter_laporan():
    try:
        return success_response('OK', laporan_service.get_opsi_filter_laporan())
    except Exception as e:
        return error_response('Gagal memuat opsi filter laporan', str(e), 500)


@laporan_bp.route('/api/laporan/ringkasan', methods=['GET'])
def ringkasan_laporan():
    try:
        p = _filter_params()
        data = laporan_service.ringkasan_laporan(p['bulan'], p['tanggal_dari'], p['tanggal_sampai'])
        return success_response('OK', data)
    except Exception as e:
        return error_response('Gagal memuat ringkasan', str(e), 500)


@laporan_bp.route('/api/laporan/<jenis>', methods=['GET'])
def get_laporan(jenis):
    try:
        p = _filter_params()
        items, total, key = laporan_service.get_laporan(
            jenis,
            p['bulan'],
            p['tanggal_dari'],
            p['tanggal_sampai'],
            p['page'],
            p['per_page'],
            p['id_menu'],
            p['petugas_id'],
            p['id_bahan'],
            p['jenis_keuangan'],
            p['sumber'],
            p['tipe'],
            p['arus'],
        )
        payload = {
            'jenis': key,
            'items': items,
            'total': total,
            'page': p['page'],
            'per_page': p['per_page'],
        }
        if key == 'pemesanan':
            payload['ringkasan_penjualan'] = laporan_service.ringkasan_penjualan(
                p['bulan'], p['tanggal_dari'], p['tanggal_sampai'], p['id_menu'], p['petugas_id']
            )
        elif key == 'pembelian':
            payload['ringkasan_pembelian'] = laporan_service.ringkasan_pembelian(
                p['bulan'], p['tanggal_dari'], p['tanggal_sampai'], p['id_bahan']
            )
        elif key in ('keuangan', 'pemasukan', 'pengeluaran'):
            payload['ringkasan_keuangan'] = laporan_service.ringkasan_keuangan(
                p['bulan'], p['tanggal_dari'], p['tanggal_sampai'],
                p['jenis_keuangan'], p['sumber'], p['arus'] if key == 'keuangan' else key,
            )
        elif key in ('stok', 'penyesuaian'):
            payload['ringkasan_stok'] = laporan_service.ringkasan_stok_saat_ini()
            payload['ringkasan_riwayat'] = laporan_service.ringkasan_riwayat_stok(
                p['bulan'], p['tanggal_dari'], p['tanggal_sampai'], p['id_bahan'],
                'PENYESUAIAN' if key == 'penyesuaian' else p['tipe'],
            )
        return success_response('OK', payload)
    except Exception as e:
        return error_response('Gagal memuat laporan', str(e), 500)
