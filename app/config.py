import os
from dotenv import load_dotenv
from os.path import join, dirname

load_dotenv(join(dirname(dirname(__file__)), '.env'))

MONGODB_URI = os.environ.get('MONGODB_URI', '')
DB_NAME = os.environ.get('DB_NAME', 'DB_DAMARKANDANG')
SECRET_KEY = os.environ.get('SECRET_KEY', 'SPARTA')

CAFE_NAME = 'Damarkandang'
CAFE_TAGLINE = 'Cafe Management System'

PENGELUARAN_KATEGORI = [
    'Bahan Baku',
    'Operasional',
    'Gaji',
    'Listrik',
    'Air',
    'Sewa',
    'Peralatan',
    'Lainnya',
]

SATUAN_PEMBELIAN = ('gram', 'kg')
GRAM_PER_KG = 1000

# Kategori bahan & produk cafe
KATEGORI_BAHAN = ('Minuman', 'Makanan', 'Kopral', 'Roasted', 'Skincare')
# Konsep per pcs / kemasan
KATEGORI_PCS = frozenset({'Kopral', 'Roasted', 'Skincare'})
# Konsep normal (kg/gram atau cairan)
KATEGORI_NORMAL = frozenset({'Minuman', 'Makanan'})

