#!/usr/bin/env python3
"""Test skenario modul Kelola Bahan Damarkandang."""

import json
import os
import sys
import urllib.request
from datetime import datetime
from urllib.parse import quote

BASE = os.environ.get('TEST_BASE_URL', 'http://127.0.0.1:5003')


def api(method, path, data=None):
    url = BASE + path.replace(' ', '%20') if ' ' in path else BASE + path
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def assert_eq(label, actual, expected):
    if actual != expected:
        raise AssertionError(f'{label}: expected {expected}, got {actual}')
    print(f'  OK {label} = {actual}')


def run_tests():
    ts = datetime.now().strftime('%H%M%S')
    print('=== Skenario 1: Jenis Bahan Susu ===')
    jenis = api('POST', '/api/jenis-bahan', {'nama_jenis': f'Susu Test {ts}', 'deskripsi': 'Test', 'status': 'aktif'})
    id_jenis = jenis['data']['id_jenis']

    print('=== Skenario 2: Bahan Fresh Milk ===')
    bahan = api('POST', '/api/bahan', {
        'id_jenis': id_jenis,
        'jumlah': 1,
        'satuan': 'gram',
        'harga_per_kg': 12000,
        'status': 'aktif',
    })
    id_bahan = bahan['data']['id_bahan']

    print('=== Skenario 3: Pembelian 6 Kg @ 12000 ===')
    api('POST', '/api/pembelian', {
        'tanggal': '2026-08-09',
        'id_bahan': id_bahan,
        'jumlah': 6,
        'satuan': 'kg',
        'harga_per_satuan': 12000,
    })
    b1 = api('GET', f'/api/bahan/{id_bahan}')['data']
    assert_eq('stok setelah pembelian 1', b1['stok_gram'], 6000)

    peng = api('GET', f'/api/pengeluaran?per_page=100&jenis={quote("Bahan Baku")}')['data']['items']
    pembelian_ids = [p['id_pembelian'] for p in api('GET', '/api/pembelian?per_page=10')['data']['items'] if p.get('id_bahan') == id_bahan]
    total_bb = sum(p['nominal'] for p in peng if p.get('id_referensi') in pembelian_ids[:1])
    assert_eq('pengeluaran pembelian 1', total_bb, 72000)

    print('=== Skenario 4: Pembelian 2 Kg @ 13000 ===')
    api('POST', '/api/pembelian', {
        'tanggal': '2026-08-09',
        'id_bahan': id_bahan,
        'jumlah': 2,
        'satuan': 'kg',
        'harga_per_satuan': 13000,
    })
    b2 = api('GET', f'/api/bahan/{id_bahan}')['data']
    assert_eq('stok setelah pembelian 2', b2['stok_gram'], 8000)
    assert_eq('harga terakhir', b2.get('harga_per_kg') or b2['harga_terakhir'], 13000)

    pembelian_all = api('GET', '/api/pembelian?per_page=10')['data']['items']
    pembelian_ids = [p['id_pembelian'] for p in pembelian_all if p.get('id_bahan') == id_bahan]
    peng2 = api('GET', f'/api/pengeluaran?per_page=100&jenis={quote("Bahan Baku")}')['data']['items']
    total_bb2 = sum(p['nominal'] for p in peng2 if p.get('id_referensi') in pembelian_ids)
    assert_eq('total pengeluaran bahan baku', total_bb2, 98000)

    print('=== Skenario 5: Penyesuaian 8000 -> 7500 ===')
    api('POST', '/api/penyesuaian-stok', {
        'id_bahan': id_bahan,
        'stok_fisik': 7500,
        'alasan': 'Stok fisik opname',
        'catatan': 'Test',
    })
    b3 = api('GET', f'/api/bahan/{id_bahan}')['data']
    assert_eq('stok setelah penyesuaian', b3['stok_gram'], 7500)

    riwayat = api('GET', f'/api/riwayat-stok?id_bahan={id_bahan}&tipe=PENYESUAIAN')['data']['items']
    if not riwayat:
        raise AssertionError('riwayat penyesuaian tidak ditemukan')
    assert_eq('selisih penyesuaian', riwayat[0]['jumlah_gram'], -500)

    print('\n=== SEMUA SKENARIO LULUS ===')


if __name__ == '__main__':
    try:
        run_tests()
    except Exception as e:
        print('GAGAL:', e)
        sys.exit(1)
