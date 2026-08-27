#!/usr/bin/env python3
"""
Seed data untuk testing modul Kelola Bahan Cafe Damarkandang.
Jalankan: python seed.py
Pastikan .env sudah berisi MONGODB_URI dan DB_NAME.
"""

import os
from os.path import join, dirname
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(join(dirname(__file__), '.env'))

MONGODB_URI = os.environ.get('MONGODB_URI', '').strip().strip('"').strip("'")
DB_NAME = os.environ.get('DB_NAME', 'DB_DAMARKANDANG')

client = MongoClient(MONGODB_URI)
db = client[DB_NAME]

SEED_PREFIX = 'SEED_TEST_'


def cleanup_seed():
    db.jenis_bahan.delete_many({'nama_jenis': {'$regex': f'^{SEED_PREFIX}'}})
    db.bahan.delete_many({'nama_bahan': {'$regex': f'^{SEED_PREFIX}'}})
    db.supplier.delete_many({'nama_supplier': {'$regex': f'^{SEED_PREFIX}'}})


def main():
    print('Membersihkan data seed lama...')
    cleanup_seed()
    print('Seed selesai dibersihkan. Gunakan UI atau test script untuk skenario lengkap.')
    print('Contoh alur testing ada di dokumentasi README modul.')


if __name__ == '__main__':
    main()
