from datetime import datetime
from app.database import get_db


def _next_seq(counter_key):
    db = get_db()
    counter = db.counters.find_one_and_update(
        {'_id': counter_key},
        {'$inc': {'seq': 1}},
        upsert=True,
        return_document=True,
    )
    return counter['seq']


def _preview_seq(counter_key):
    db = get_db()
    counter = db.counters.find_one({'_id': counter_key})
    seq = counter['seq'] if counter else 0
    return seq + 1


def generate_id_jenis_bahan():
    seq = _next_seq('jenis_bahan')
    return f'JB-{str(seq).zfill(3)}'


def preview_id_jenis_bahan():
    seq = _preview_seq('jenis_bahan')
    return f'JB-{str(seq).zfill(3)}'


def generate_id_bahan():
    seq = _next_seq('bahan_baku')
    return f'BHN-{str(seq).zfill(3)}'


def preview_id_bahan():
    seq = _preview_seq('bahan_baku')
    return f'BHN-{str(seq).zfill(3)}'


def generate_id_supplier():
    seq = _next_seq('supplier')
    return f'SUP-{str(seq).zfill(3)}'


def preview_id_supplier():
    seq = _preview_seq('supplier')
    return f'SUP-{str(seq).zfill(3)}'


def _dated_prefix(prefix, date_str=None):
    d = date_str or datetime.now().strftime('%Y%m%d')
    return f'{prefix}-{d}'


def generate_id_pembelian(tanggal=None):
    d = tanggal or datetime.now().strftime('%Y%m%d')
    seq = _next_seq(f'pembelian_{d}')
    return f'PB-{d}-{str(seq).zfill(3)}'


def generate_id_pengeluaran(tanggal=None):
    d = tanggal or datetime.now().strftime('%Y%m%d')
    seq = _next_seq(f'pengeluaran_{d}')
    return f'EXP-{d}-{str(seq).zfill(3)}'


def generate_id_riwayat_stok(tanggal=None):
    d = tanggal or datetime.now().strftime('%Y%m%d')
    seq = _next_seq(f'riwayat_stok_{d}')
    return f'RST-{d}-{str(seq).zfill(3)}'


def generate_id_menu():
    seq = _next_seq('menu')
    return f'MNU-{str(seq).zfill(3)}'


def generate_id_transaksi_kasir(tanggal=None):
    d = tanggal or datetime.now().strftime('%Y%m%d')
    seq = _next_seq(f'kasir_{d}')
    return f'KSR-{d}-{str(seq).zfill(3)}'


def generate_id_pemasukan(tanggal=None):
    d = tanggal or datetime.now().strftime('%Y%m%d')
    seq = _next_seq(f'pemasukan_{d}')
    return f'INC-{d}-{str(seq).zfill(3)}'


def generate_id_pemesanan(tanggal=None):
    d = tanggal or datetime.now().strftime('%Y%m%d')
    seq = _next_seq(f'pemesanan_{d}')
    return f'PM-{d}-{str(seq).zfill(3)}'


def generate_id_pembayaran():
    seq = _next_seq('data_pembayaran')
    return f'PAY-{str(seq).zfill(3)}'


def generate_id_jenis_pengeluaran():
    seq = _next_seq('jenis_pengeluaran')
    return f'JPG-{str(seq).zfill(3)}'


def generate_id_jenis_pemasukan():
    seq = _next_seq('jenis_pemasukan')
    return f'JPM-{str(seq).zfill(3)}'
