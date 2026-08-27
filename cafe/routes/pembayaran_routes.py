import os
import uuid
from flask import Blueprint, request, current_app
from werkzeug.utils import secure_filename
from cafe.services import pembayaran_service
from cafe.utils.response import error_response, success_response

pembayaran_bp = Blueprint('pembayaran_api', __name__)

ALLOWED_EXT = {'.jpg', '.jpeg', '.png', '.webp'}
MAX_BYTES = 5 * 1024 * 1024


def _upload_dir():
    root = current_app.root_path
    path = os.path.join(root, 'static', 'uploads', 'pembayaran')
    os.makedirs(path, exist_ok=True)
    return path


@pembayaran_bp.route('/api/data-pembayaran', methods=['GET'])
def list_pembayaran():
    try:
        status = (request.args.get('status') or '').strip() or None
        items = pembayaran_service.list_pembayaran(status)
        return success_response('OK', {'items': items})
    except Exception as e:
        return error_response('Gagal memuat data pembayaran', str(e), 500)


@pembayaran_bp.route('/api/data-pembayaran', methods=['POST'])
def create_pembayaran():
    try:
        doc = pembayaran_service.create_pembayaran(request.get_json(silent=True) or {})
        return success_response('Data pembayaran disimpan', doc, 201)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menyimpan', str(e), 500)


@pembayaran_bp.route('/api/data-pembayaran/<id_pembayaran>', methods=['PUT'])
def update_pembayaran(id_pembayaran):
    try:
        doc = pembayaran_service.update_pembayaran(id_pembayaran, request.get_json(silent=True) or {})
        return success_response('Data pembayaran diperbarui', doc)
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal memperbarui', str(e), 500)


@pembayaran_bp.route('/api/data-pembayaran/<id_pembayaran>', methods=['DELETE'])
def delete_pembayaran(id_pembayaran):
    try:
        pembayaran_service.delete_pembayaran(id_pembayaran)
        return success_response('Data pembayaran dihapus')
    except ValueError as e:
        return error_response('Validasi gagal', str(e), 400)
    except Exception as e:
        return error_response('Gagal menghapus', str(e), 500)


@pembayaran_bp.route('/api/data-pembayaran/upload', methods=['POST'])
def upload_gambar():
    try:
        if 'file' not in request.files:
            return error_response('Validasi gagal', 'Tidak ada berkas', 400)
        f = request.files['file']
        if not f or not f.filename:
            return error_response('Validasi gagal', 'Tidak ada berkas', 400)
        orig = secure_filename(f.filename) or 'gambar'
        ext = os.path.splitext(orig)[1].lower()
        if ext not in ALLOWED_EXT:
            return error_response('Validasi gagal', 'Format gambar tidak didukung', 400)
        new_name = f'{uuid.uuid4().hex}{ext}'
        abs_path = os.path.join(_upload_dir(), new_name)
        f.save(abs_path)
        if os.path.getsize(abs_path) > MAX_BYTES:
            os.remove(abs_path)
            return error_response('Validasi gagal', 'Ukuran maksimal 5 MB', 400)
        url = f'/static/uploads/pembayaran/{new_name}'
        return success_response('Upload berhasil', {'gambar_url': url})
    except Exception as e:
        return error_response('Gagal upload', str(e), 500)
