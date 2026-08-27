#!/usr/bin/env python3
"""
Script Migrasi: Update Master Data Tahapan Produksi
- Hapus tahapan "Pengeringan" dari semua dataProses
- Tambahkan "Pengeringan Awal" dan "Pengeringan Akhir" ke semua dataProses yang memiliki "Pengeringan"
- Pastikan Natural Process tidak memiliki Fermentasi
"""

from pymongo import MongoClient
from datetime import datetime
import os
from os.path import join, dirname
from dotenv import load_dotenv

load_dotenv(join(dirname(__file__), ".env"))

MONGO_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = os.environ.get("DB_NAME", "DB_SEMHAS")

# Referensi urutan (dokumentasi; sinkron dengan app.validate_sequential_tahapan)
URUTAN_TAHAPAN = {
    "Sortasi": 1,
    "Fermentasi": 2,
    "Pulping": 3,
    "Pencucian": 4,
    "Pengeringan Awal": 5,
    "Pengeringan Akhir": 6,
    "Hulling": 7,
    "Hand Sortasi": 8,
    "Grinding": 9,
    "Pengemasan": 10,
    "Roasting": 99,  # legacy
}

def migrate_tahapan_pengeringan():
    """Migrasi tahapan Pengeringan menjadi Pengeringan Awal dan Pengeringan Akhir"""
    
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    print("🔄 Memulai migrasi tahapan produksi...")
    print(f"📅 Waktu migrasi: {datetime.now()}")
    
    # Ambil semua dataProses
    data_proses_list = list(db.dataProses.find())
    print(f"📊 Ditemukan {len(data_proses_list)} proses pengolahan")
    
    updated_count = 0
    skipped_count = 0
    
    for proses in data_proses_list:
        tahapan_status = proses.get('tahapanStatus', {})
        
        # Cek apakah ada tahapan "Pengeringan"
        has_pengeringan = tahapan_status.get('Pengeringan', False)
        
        if not has_pengeringan:
            print(f"⏭️  Skip: {proses.get('nama')} - tidak memiliki tahapan Pengeringan")
            skipped_count += 1
            continue
        
        print(f"\n🔄 Memproses: {proses.get('nama')}")
        print(f"   Tahapan status sebelum: {tahapan_status}")
        
        # Hapus "Pengeringan"
        new_tahapan_status = tahapan_status.copy()
        if 'Pengeringan' in new_tahapan_status:
            del new_tahapan_status['Pengeringan']
            print(f"   ✅ Menghapus tahapan 'Pengeringan'")
        
        # Tambahkan "Pengeringan Awal" dan "Pengeringan Akhir"
        # Jika sebelumnya aktif, kedua tahapan baru juga aktif
        if has_pengeringan:
            new_tahapan_status['Pengeringan Awal'] = True
            new_tahapan_status['Pengeringan Akhir'] = True
            print(f"   ✅ Menambahkan 'Pengeringan Awal' dan 'Pengeringan Akhir'")
        
        # Pastikan Natural Process tidak memiliki Fermentasi
        if proses.get('nama') == 'Natural Process':
            if 'Fermentasi' in new_tahapan_status:
                new_tahapan_status['Fermentasi'] = False
                print(f"   ✅ Menonaktifkan Fermentasi untuk Natural Process")
        
        # Update di database
        db.dataProses.update_one(
            {'_id': proses['_id']},
            {'$set': {'tahapanStatus': new_tahapan_status}}
        )
        
        print(f"   ✅ Updated: {proses.get('nama')}")
        print(f"   Tahapan status setelah: {new_tahapan_status}")
        updated_count += 1
    
    print(f"\n✅ Migrasi selesai!")
    print(f"📊 Ringkasan:")
    print(f"   - Proses yang diupdate: {updated_count}")
    print(f"   - Proses yang di-skip: {skipped_count}")
    print(f"   - Total proses: {len(data_proses_list)}")
    
    # Verifikasi: Pastikan tidak ada lagi referensi "Pengeringan"
    print(f"\n🔍 Verifikasi...")
    remaining_pengeringan = list(db.dataProses.find({'tahapanStatus.Pengeringan': {'$exists': True}}))
    if remaining_pengeringan:
        print(f"⚠️  Peringatan: Masih ada {len(remaining_pengeringan)} proses dengan tahapan 'Pengeringan'")
        for p in remaining_pengeringan:
            print(f"   - {p.get('nama')}")
    else:
        print(f"✅ Tidak ada lagi referensi tahapan 'Pengeringan'")
    
    # Verifikasi: Pastikan semua proses memiliki Pengeringan Awal dan Akhir jika diperlukan
    print(f"\n🔍 Verifikasi tahapan baru...")
    proses_dengan_pengeringan_awal = list(db.dataProses.find({'tahapanStatus.Pengeringan Awal': True}))
    proses_dengan_pengeringan_akhir = list(db.dataProses.find({'tahapanStatus.Pengeringan Akhir': True}))
    print(f"   - Proses dengan Pengeringan Awal: {len(proses_dengan_pengeringan_awal)}")
    print(f"   - Proses dengan Pengeringan Akhir: {len(proses_dengan_pengeringan_akhir)}")
    
    client.close()
    print(f"\n✅ Migrasi selesai pada {datetime.now()}")

if __name__ == "__main__":
    try:
        migrate_tahapan_pengeringan()
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
