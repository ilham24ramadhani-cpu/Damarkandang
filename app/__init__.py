"""Modul Kelola Bahan & Keuangan — Cafe Damarkandang."""

from app.database import init_db
from app.routes.pages import pages_bp
from app.routes.jenis_bahan_routes import jenis_bahan_bp
from app.routes.bahan_routes import bahan_bp
from app.routes.pembelian_routes import pembelian_bp
from app.routes.keuangan_routes import keuangan_bp
from app.routes.penyesuaian_routes import stok_bp


from app.routes.menu_routes import menu_bp
from app.routes.kasir_routes import kasir_bp
from app.routes.laporan_routes import laporan_bp
from app.routes.pembayaran_routes import pembayaran_bp
from app.routes.jenis_keuangan_routes import jenis_keuangan_bp
from app.services import jenis_keuangan_service


def init_cafe_module(app, db, client=None):
    """Daftarkan blueprint modul cafe ke aplikasi Flask existing."""
    init_db(db, client)
    jenis_keuangan_service.ensure_defaults()
    _ensure_cafe_indexes(db)

    blueprints = [
        pages_bp,
        jenis_bahan_bp,
        bahan_bp,
        pembelian_bp,
        keuangan_bp,
        stok_bp,
        menu_bp,
        kasir_bp,
        laporan_bp,
        pembayaran_bp,
        jenis_keuangan_bp,
    ]
    for bp in blueprints:
        app.register_blueprint(bp)


def _ensure_cafe_indexes(db):
    """Pastikan index penting ada (no-op jika sudah ada dengan nama default)."""
    specs = [
        (db.bahan, 'id_bahan'),
        (db.bahan, [('status', 1), ('id_jenis', 1)]),
        (db.bahan, 'id_jenis'),
        (db.pengeluaran, [('sumber', 1), ('id_referensi', 1)]),
        (db.pengeluaran, 'tanggal'),
        (db.pengeluaran, [('tanggal', -1), ('created_at', -1)]),
        (db.pemasukan, 'tanggal'),
        (db.pemasukan, [('tanggal', -1), ('created_at', -1)]),
        (db.pemasukan, 'id_referensi'),
        (db.pembelian, 'id_bahan'),
        (db.pembelian, 'id_pembelian'),
        (db.pembelian, 'tanggal'),
        (db.pembelian, [('tanggal', -1), ('created_at', -1)]),
        (db.menu, 'id_menu'),
        (db.menu, [('status', 1), ('nama_menu', 1)]),
        (db.jenis_bahan, 'id_jenis'),
        (db.riwayat_stok, [('id_bahan', 1), ('tipe', 1), ('tanggal', 1)]),
        (db.riwayat_stok, [('tanggal', -1), ('created_at', -1)]),
        (db.riwayat_stok, 'id_riwayat'),
        (db.transaksi_kasir, 'id_pemesanan'),
        (db.transaksi_kasir, 'tanggal'),
        (db.transaksi_kasir, [('tanggal', -1), ('created_at', -1)]),
        (db.transaksi_kasir, 'petugas.id'),
        (db.transaksi_kasir, 'items.id_menu'),
        (db.users, 'id'),
        (db.users, 'status'),
    ]
    for coll, keys in specs:
        try:
            coll.create_index(keys, background=True)
        except Exception:
            pass
