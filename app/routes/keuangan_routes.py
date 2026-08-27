from flask import Blueprint, request
from app.services import keuangan_service, pemasukan_service
from app.utils.response import error_response, success_response

keuangan_bp = Blueprint('keuangan_api', __name__)


@keuangan_bp.route('/api/pengeluaran', methods=['GET'])
def list_pengeluaran():
    try:
        page = max(int(request.args.get('page', 1) or 1), 1)
        per_page = min(max(int(request.args.get('per_page', 10) or 10), 1), 100)
        search = (request.args.get('search') or '').strip()
        jenis = (request.args.get('jenis') or request.args.get('kategori') or '').strip()
        bulan = (request.args.get('bulan') or '').strip()
        items, total = keuangan_service.list_pengeluaran(search, jenis, page, per_page, bulan or None)
        return success_response('OK', {'items': items, 'total': total, 'page': page, 'per_page': per_page})
    except Exception as e:
        return error_response('Gagal memuat pengeluaran', str(e), 500)


@keuangan_bp.route('/api/pengeluaran', methods=['POST'])
def create_pengeluaran():
    try:
        doc = keuangan_service.create_pengeluaran_manual(request.get_json(silent=True) or {})
        return success_response('Pengeluaran berhasil disimpan', doc, 201)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menyimpan pengeluaran', str(e), 500)


@keuangan_bp.route('/api/pemasukan', methods=['POST'])
def create_pemasukan():
    try:
        doc = pemasukan_service.create_pemasukan_manual(request.get_json(silent=True) or {})
        return success_response('Pemasukan berhasil disimpan', doc, 201)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menyimpan pemasukan', str(e), 500)
