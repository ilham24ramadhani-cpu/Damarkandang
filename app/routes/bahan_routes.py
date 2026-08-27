from flask import Blueprint, request
from app.services import bahan_service
from app.utils.id_generator import preview_id_bahan
from app.utils.response import error_response, success_response

bahan_bp = Blueprint('bahan_api', __name__)


def _pagination_params():
    page = max(int(request.args.get('page', 1) or 1), 1)
    per_page = min(max(int(request.args.get('per_page', 10) or 10), 1), 500)
    search = (request.args.get('search') or '').strip()
    status = (request.args.get('status') or '').strip()
    active_only = request.args.get('active_only', '').lower() in ('1', 'true', 'yes')
    light = request.args.get('light', '').lower() in ('1', 'true', 'yes')
    kategori = (request.args.get('kategori') or '').strip()
    include_raw = (request.args.get('include_pengeluaran') or '').strip().lower()
    if include_raw in ('0', 'false', 'no'):
        include_pengeluaran = False
    elif include_raw in ('1', 'true', 'yes'):
        include_pengeluaran = True
    else:
        # Default: full list butuh pengeluaran; light/options tidak
        include_pengeluaran = not light
    return search, status, page, per_page, active_only, light, include_pengeluaran, kategori


@bahan_bp.route('/api/bahan/next-id', methods=['GET'])
def preview_bahan_id():
    return success_response('OK', {'id_bahan': preview_id_bahan()})


@bahan_bp.route('/api/bahan', methods=['GET'])
def list_bahan():
    try:
        search, status, page, per_page, active_only, light, include_pengeluaran, kategori = _pagination_params()
        items, total = bahan_service.list_bahan(
            search,
            status,
            page,
            per_page,
            active_only,
            include_pengeluaran=include_pengeluaran,
            light=light,
            kategori=kategori,
        )
        return success_response('OK', {'items': items, 'total': total, 'page': page, 'per_page': per_page})
    except Exception as e:
        return error_response('Gagal memuat bahan', str(e), 500)


@bahan_bp.route('/api/bahan/<id_bahan>', methods=['GET'])
def get_bahan(id_bahan):
    include_pengeluaran = request.args.get('include_pengeluaran', '').lower() in ('1', 'true', 'yes')
    doc = bahan_service.get_bahan(id_bahan, include_pengeluaran=include_pengeluaran)
    if not doc:
        return error_response('Bahan tidak ditemukan', 'Not found', 404)
    return success_response('OK', doc)


@bahan_bp.route('/api/bahan', methods=['POST'])
def create_bahan():
    try:
        doc = bahan_service.create_bahan(request.get_json(silent=True) or {})
        return success_response('Bahan berhasil disimpan', doc, 201)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menyimpan bahan', str(e), 500)


@bahan_bp.route('/api/bahan/<id_bahan>', methods=['PUT'])
def update_bahan(id_bahan):
    try:
        doc = bahan_service.update_bahan(id_bahan, request.get_json(silent=True) or {})
        return success_response('Bahan berhasil diperbarui', doc)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal memperbarui bahan', str(e), 500)


@bahan_bp.route('/api/bahan/<id_bahan>', methods=['DELETE'])
def delete_bahan(id_bahan):
    try:
        result = bahan_service.delete_bahan(id_bahan)
        return success_response(result['message'], result)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menghapus bahan', str(e), 500)
