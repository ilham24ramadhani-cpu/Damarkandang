#!/usr/bin/env python3
"""
Bersihkan data uji / nonaktif dari database cafe.
Jalankan: python3 cleanup_test_data.py

Tidak membuat data dummy. Hanya menghapus record test & bahan nonaktif (hard delete + cascade).
ID counter TIDAK direset — gap ID (mis. BHN-002 hilang) tetap terlihat.
"""

import os
import re
from os.path import join, dirname
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(join(dirname(__file__), '.env'))

MONGODB_URI = os.environ.get('MONGODB_URI', '').strip().strip('"').strip("'")
DB_NAME = os.environ.get('DB_NAME', 'DB_DAMARKANDANG').strip().strip('"').strip("'")

TEST_NAMA_PATTERNS = re.compile(
    r'(test|deltest|cascadedel|fresh milk|supdel|supcascade|tdel|susu test|pt supplier susu)',
    re.I,
)


def is_test_name(name):
    return bool(TEST_NAMA_PATTERNS.search(name or ''))

client = MongoClient(MONGODB_URI)
db = client[DB_NAME]

from cafe.database import init_db
from cafe.services.bahan_service import delete_bahan

init_db(db, client)


def is_test_bahan(doc):
    if doc.get('status') == 'nonaktif':
        return True
    nama = doc.get('nama_bahan') or doc.get('nama_jenis') or ''
    return is_test_name(nama)


def cleanup_orphan_pembelian():
    """Hapus pembelian uji yang tersisa (beserta pengeluaran terkait)."""
    removed = 0
    for p in list(db.pembelian.find({})):
        bahan = p.get('nama_bahan') or ''
        sup = p.get('nama_supplier') or ''
        if not (is_test_name(bahan) or is_test_name(sup)):
            continue
        id_pb = p.get('id_pembelian')
        if id_pb:
            db.pengeluaran.delete_many({'id_referensi': id_pb})
        db.pembelian.delete_one({'_id': p['_id']})
        print(f"  Hapus pembelian: {id_pb} — {bahan} / {sup}")
        removed += 1
    return removed


def cleanup():
    bahan_docs = list(db.bahan.find({'id_bahan': {'$exists': True}}))
    deleted = 0
    for doc in bahan_docs:
        if is_test_bahan(doc):
            try:
                delete_bahan(doc['id_bahan'])
                print(f"  Hapus bahan: {doc.get('id_bahan')} — {doc.get('nama_bahan')}")
                deleted += 1
            except Exception as e:
                print(f"  Gagal hapus {doc.get('id_bahan')}: {e}")

    for jenis in list(db.jenis_bahan.find({})):
        nama = jenis.get('nama_jenis') or ''
        if is_test_name(nama):
            used = db.bahan.count_documents({'id_jenis': jenis.get('id_jenis')})
            if used == 0:
                db.jenis_bahan.delete_one({'id_jenis': jenis['id_jenis']})
                print(f"  Hapus jenis: {jenis.get('id_jenis')} — {nama}")

    for sup in list(db.supplier.find({})):
        nama = sup.get('nama_supplier') or ''
        if is_test_name(nama):
            used = db.pembelian.count_documents({'id_supplier': sup.get('id_supplier')})
            if used == 0:
                db.supplier.delete_one({'id_supplier': sup['id_supplier']})
                print(f"  Hapus supplier: {sup.get('id_supplier')} — {nama}")

    orphan_pb = cleanup_orphan_pembelian()

    print(f"\nSelesai. {deleted} bahan + {orphan_pb} pembelian uji dihapus permanen.")
    print("Counter ID tidak di-reset — nomor ID yang sudah dipakai tidak dipakai ulang.")


if __name__ == '__main__':
    print('Membersihkan data test & nonaktif...\n')
    cleanup()
