from flask import Blueprint, request
from cafe.services import jenis_keuangan_service
from cafe.utils.response import error_response, success_response

jenis_keuangan_bp = Blueprint('jenis_keuangan_api', __name__)


@jenis_keuangan_bp.route('/api/jenis-pengeluaran', methods=['GET'])
def list_jenis_pengeluaran():
    try:
        manual_only = request.args.get('manual_only') == '1'
        status = (request.args.get('status') or '').strip() or None
        items = jenis_keuangan_service.list_jenis_pengeluaran(manual_only, status)
        return success_response('OK', {'items': items})
    except Exception as e:
        return error_response('Gagal memuat jenis pengeluaran', str(e), 500)


@jenis_keuangan_bp.route('/api/jenis-pengeluaran', methods=['POST'])
def create_jenis_pengeluaran():
    try:
        doc = jenis_keuangan_service.create_jenis_pengeluaran(request.get_json(silent=True) or {})
        return success_response('Jenis pengeluaran disimpan', doc, 201)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menyimpan', str(e), 500)


@jenis_keuangan_bp.route('/api/jenis-pengeluaran/<id_jenis>', methods=['PUT'])
def update_jenis_pengeluaran(id_jenis):
    try:
        doc = jenis_keuangan_service.update_jenis_pengeluaran(id_jenis, request.get_json(silent=True) or {})
        return success_response('Jenis pengeluaran diperbarui', doc)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal memperbarui', str(e), 500)


@jenis_keuangan_bp.route('/api/jenis-pengeluaran/<id_jenis>', methods=['DELETE'])
def delete_jenis_pengeluaran(id_jenis):
    try:
        jenis_keuangan_service.delete_jenis_pengeluaran(id_jenis)
        return success_response('Jenis pengeluaran dihapus')
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menghapus', str(e), 500)


@jenis_keuangan_bp.route('/api/jenis-pemasukan', methods=['GET'])
def list_jenis_pemasukan():
    try:
        manual_only = request.args.get('manual_only') == '1'
        status = (request.args.get('status') or '').strip() or None
        items = jenis_keuangan_service.list_jenis_pemasukan(manual_only, status)
        return success_response('OK', {'items': items})
    except Exception as e:
        return error_response('Gagal memuat jenis pemasukan', str(e), 500)


@jenis_keuangan_bp.route('/api/jenis-pemasukan', methods=['POST'])
def create_jenis_pemasukan():
    try:
        doc = jenis_keuangan_service.create_jenis_pemasukan(request.get_json(silent=True) or {})
        return success_response('Jenis pemasukan disimpan', doc, 201)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menyimpan', str(e), 500)


@jenis_keuangan_bp.route('/api/jenis-pemasukan/<id_jenis>', methods=['PUT'])
def update_jenis_pemasukan(id_jenis):
    try:
        doc = jenis_keuangan_service.update_jenis_pemasukan(id_jenis, request.get_json(silent=True) or {})
        return success_response('Jenis pemasukan diperbarui', doc)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal memperbarui', str(e), 500)


@jenis_keuangan_bp.route('/api/jenis-pemasukan/<id_jenis>', methods=['DELETE'])
def delete_jenis_pemasukan(id_jenis):
    try:
        jenis_keuangan_service.delete_jenis_pemasukan(id_jenis)
        return success_response('Jenis pemasukan dihapus')
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menghapus', str(e), 500)
