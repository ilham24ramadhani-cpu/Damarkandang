from flask import Blueprint, request
from app.services import kasir_service, pemasukan_service
from app.utils.response import error_response, success_response

kasir_bp = Blueprint('kasir_api', __name__)


@kasir_bp.route('/api/kasir/petugas', methods=['GET'])
def list_petugas():
    try:
        return success_response('OK', kasir_service.list_petugas())
    except Exception as e:
        return error_response('Gagal memuat petugas', str(e), 500)


@kasir_bp.route('/api/kasir/transaksi/stats', methods=['GET'])
def transaksi_stats():
    try:
        bulan = (request.args.get('bulan') or '').strip() or None
        data = kasir_service.get_stats(bulan)
        return success_response('OK', data)
    except Exception as e:
        return error_response('Gagal memuat statistik', str(e), 500)


@kasir_bp.route('/api/kasir/transaksi', methods=['GET'])
def list_transaksi():
    try:
        page = max(int(request.args.get('page', 1) or 1), 1)
        per_page = min(max(int(request.args.get('per_page', 20) or 20), 1), 100)
        search = (request.args.get('search') or '').strip() or None
        status = (request.args.get('status') or '').strip() or None
        bulan = (request.args.get('bulan') or '').strip() or None
        items, total = kasir_service.list_transaksi(page, per_page, search, status, bulan)
        return success_response('OK', {'items': items, 'total': total, 'page': page, 'per_page': per_page})
    except Exception as e:
        return error_response('Gagal memuat transaksi', str(e), 500)


@kasir_bp.route('/api/kasir/transaksi/<id_pemesanan>', methods=['GET'])
def get_transaksi(id_pemesanan):
    try:
        doc = kasir_service.get_transaksi(id_pemesanan)
        if not doc:
            return error_response('Tidak ditemukan', 'Penjualan tidak ditemukan', 404)
        return success_response('OK', doc)
    except Exception as e:
        return error_response('Gagal memuat penjualan', str(e), 500)


@kasir_bp.route('/api/kasir/transaksi', methods=['POST'])
def create_transaksi():
    try:
        doc = kasir_service.proses_transaksi(request.get_json(silent=True) or {})
        return success_response('Penjualan berhasil', doc, 201)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal memproses transaksi', str(e), 500)


@kasir_bp.route('/api/kasir/transaksi/<id_pemesanan>/lunas', methods=['POST'])
def lunasi_pemesanan(id_pemesanan):
    try:
        doc = kasir_service.lunasi_pemesanan(id_pemesanan)
        return success_response('Penjualan dilunasi — pemasukan tercatat & stok berkurang', doc)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal melunasi penjualan', str(e), 500)


@kasir_bp.route('/api/kasir/transaksi/<id_pemesanan>', methods=['PUT'])
def update_transaksi(id_pemesanan):
    try:
        doc = kasir_service.update_transaksi(id_pemesanan, request.get_json(silent=True) or {})
        return success_response('Penjualan diperbarui — stok & pemasukan disesuaikan', doc)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal memperbarui penjualan', str(e), 500)


@kasir_bp.route('/api/kasir/transaksi/<id_pemesanan>', methods=['DELETE'])
def delete_transaksi(id_pemesanan):
    try:
        result = kasir_service.delete_transaksi(id_pemesanan)
        return success_response('Penjualan dihapus — stok dikembalikan & pemasukan dibatalkan', result)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menghapus penjualan', str(e), 500)


@kasir_bp.route('/api/pemasukan', methods=['GET'])
def list_pemasukan():
    try:
        page = max(int(request.args.get('page', 1) or 1), 1)
        per_page = min(max(int(request.args.get('per_page', 10) or 10), 1), 100)
        search = (request.args.get('search') or '').strip()
        bulan = (request.args.get('bulan') or '').strip()
        items, total = pemasukan_service.list_pemasukan(search, page, per_page, bulan or None)
        return success_response('OK', {'items': items, 'total': total, 'page': page, 'per_page': per_page})
    except Exception as e:
        return error_response('Gagal memuat pemasukan', str(e), 500)
