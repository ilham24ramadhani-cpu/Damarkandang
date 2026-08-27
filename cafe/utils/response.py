from flask import jsonify
from bson import ObjectId
from datetime import datetime


def json_serialize(data):
    if isinstance(data, ObjectId):
        return str(data)
    if isinstance(data, list):
        return [json_serialize(item) for item in data]
    if isinstance(data, dict):
        # Lewati _id agar respons lebih kecil & serialisasi lebih cepat
        return {
            key: json_serialize(value)
            for key, value in data.items()
            if key != '_id'
        }
    if hasattr(data, 'isoformat'):
        return data.isoformat()
    return data


def success_response(message='Berhasil', data=None, status=200):
    payload = {'success': True, 'message': message}
    if data is not None:
        payload['data'] = json_serialize(data)
    return jsonify(payload), status


def error_response(message='Gagal', error=None, status=400):
    payload = {'success': False, 'message': message}
    if error:
        payload['error'] = str(error)
    return jsonify(payload), status


def now_iso():
    return datetime.now().isoformat()
