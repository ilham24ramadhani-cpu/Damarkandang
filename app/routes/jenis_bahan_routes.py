from flask import Blueprint, request
from app.config import KATEGORI_BAHAN
from app.services import jenis_bahan_service
from app.utils.response import error_response, success_response

jenis_bahan_bp = Blueprint('jenis_bahan_api', __name__)


def _pagination_params():
    page = max(int(request.args.get('page', 1) or 1), 1)
    per_page = min(max(int(request.args.get('per_page', 10) or 10), 1), 100)
    search = (request.args.get('search') or '').strip()
    status = (request.args.get('status') or '').strip()
    active_only = request.args.get('active_only', '').lower() in ('1', 'true', 'yes')
    kategori = (request.args.get('kategori') or '').strip()
    return search, status, page, per_page, active_only, kategori


@jenis_bahan_bp.route('/api/jenis-bahan', methods=['GET'])
def list_jenis_bahan():
    try:
        search, status, page, per_page, active_only, kategori = _pagination_params()
        items, total = jenis_bahan_service.list_jenis_bahan(
            search, status, page, per_page, active_only, kategori=kategori
        )
        return success_response('OK', {
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'kategori_list': list(KATEGORI_BAHAN),
        })
    except Exception as e:
        return error_response('Gagal memuat jenis bahan', str(e), 500)


@jenis_bahan_bp.route('/api/jenis-bahan', methods=['POST'])
def create_jenis_bahan():
    try:
        doc = jenis_bahan_service.create_jenis_bahan(request.get_json(silent=True) or {})
        return success_response('Jenis bahan berhasil disimpan', doc, 201)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menyimpan jenis bahan', str(e), 500)


@jenis_bahan_bp.route('/api/jenis-bahan/<id_jenis>', methods=['PUT'])
def update_jenis_bahan(id_jenis):
    try:
        doc = jenis_bahan_service.update_jenis_bahan(id_jenis, request.get_json(silent=True) or {})
        return success_response('Jenis bahan berhasil diperbarui', doc)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal memperbarui jenis bahan', str(e), 500)


@jenis_bahan_bp.route('/api/jenis-bahan/<id_jenis>', methods=['DELETE'])
def delete_jenis_bahan(id_jenis):
    try:
        result = jenis_bahan_service.delete_jenis_bahan(id_jenis)
        return success_response(result['message'], result)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menghapus jenis bahan', str(e), 500)
