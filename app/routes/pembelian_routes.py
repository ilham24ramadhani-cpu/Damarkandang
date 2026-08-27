from flask import Blueprint, request
from app.services import pembelian_service
from app.utils.response import error_response, success_response

pembelian_bp = Blueprint('pembelian_api', __name__)


@pembelian_bp.route('/api/pembelian', methods=['GET'])
def list_pembelian():
    try:
        page = max(int(request.args.get('page', 1) or 1), 1)
        per_page = min(max(int(request.args.get('per_page', 10) or 10), 1), 100)
        search = (request.args.get('search') or '').strip()
        items, total = pembelian_service.list_pembelian(search, page, per_page)
        return success_response('OK', {'items': items, 'total': total, 'page': page, 'per_page': per_page})
    except Exception as e:
        return error_response('Gagal memuat pembelian', str(e), 500)


@pembelian_bp.route('/api/pembelian', methods=['POST'])
def create_pembelian():
    try:
        doc = pembelian_service.create_pembelian(request.get_json(silent=True) or {})
        return success_response('Pembelian berhasil disimpan', doc, 201)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menyimpan pembelian', str(e), 500)
