from flask import Blueprint, request
from app.services import pembelian_service, stok_service
from app.utils.response import error_response, success_response, now_iso

stok_bp = Blueprint('stok_api', __name__)


@stok_bp.route('/api/stok/jenis-bahan', methods=['GET'])
def list_stok_jenis_bahan():
    try:
        from app.services import bahan_service
        search = (request.args.get('search') or '').strip()
        items = bahan_service.list_stok_by_jenis(search)
        return success_response('OK', {'items': items, 'total': len(items), 'updated_at': now_iso()})
    except Exception as e:
        return error_response('Gagal memuat stok per jenis', str(e), 500)


@stok_bp.route('/api/riwayat-stok', methods=['GET'])
def list_riwayat_stok():
    try:
        page = max(int(request.args.get('page', 1) or 1), 1)
        per_page = min(max(int(request.args.get('per_page', 20) or 20), 1), 100)
        id_bahan = (request.args.get('id_bahan') or '').strip()
        tipe = (request.args.get('tipe') or '').strip()
        items, total = stok_service.list_riwayat(id_bahan, tipe, page, per_page)
        return success_response('OK', {'items': items, 'total': total, 'page': page, 'per_page': per_page})
    except Exception as e:
        return error_response('Gagal memuat riwayat stok', str(e), 500)


@stok_bp.route('/api/penyesuaian-stok', methods=['POST'])
def penyesuaian_stok():
    try:
        result = pembelian_service.penyesuaian_stok(request.get_json(silent=True) or {})
        return success_response('Penyesuaian stok berhasil disimpan', result, 201)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menyimpan penyesuaian stok', str(e), 500)
