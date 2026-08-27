from flask import Blueprint, request
from app.services import menu_service
from app.utils.response import error_response, success_response

menu_bp = Blueprint('menu_api', __name__)


@menu_bp.route('/api/menu', methods=['GET'])
def list_menu():
    try:
        page = max(int(request.args.get('page', 1) or 1), 1)
        per_page = min(max(int(request.args.get('per_page', 20) or 20), 1), 100)
        search = (request.args.get('search') or '').strip()
        status = (request.args.get('status') or '').strip()
        active_only = request.args.get('active_only', '').lower() in ('1', 'true', 'yes')
        light = request.args.get('light', '').lower() in ('1', 'true', 'yes') or active_only
        items, total = menu_service.list_menu(search, status, page, per_page, active_only, light=light)
        return success_response('OK', {'items': items, 'total': total, 'page': page, 'per_page': per_page})
    except Exception as e:
        return error_response('Gagal memuat produk', str(e), 500)


@menu_bp.route('/api/menu/<id_menu>', methods=['GET'])
def get_menu(id_menu):
    doc = menu_service.get_menu(id_menu)
    if not doc:
        return error_response('Produk tidak ditemukan', 'Not found', 404)
    return success_response('OK', doc)


@menu_bp.route('/api/menu', methods=['POST'])
def create_menu():
    try:
        doc = menu_service.create_menu(request.get_json(silent=True) or {})
        return success_response('Produk berhasil disimpan', doc, 201)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menyimpan produk', str(e), 500)


@menu_bp.route('/api/menu/<id_menu>', methods=['PUT'])
def update_menu(id_menu):
    try:
        doc = menu_service.update_menu(id_menu, request.get_json(silent=True) or {})
        return success_response('Produk berhasil diperbarui', doc)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal memperbarui produk', str(e), 500)


@menu_bp.route('/api/menu/<id_menu>', methods=['DELETE'])
def delete_menu(id_menu):
    try:
        result = menu_service.delete_menu(id_menu)
        return success_response(result['message'], result)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menghapus produk', str(e), 500)
