from flask import Blueprint, render_template, request
from cafe.config import CAFE_NAME, PENGELUARAN_KATEGORI
from cafe.services import dashboard_service
from cafe.utils.response import error_response, success_response

pages_bp = Blueprint('cafe_pages', __name__)


@pages_bp.route('/kelola-data')
def kelola_data_legacy_redirect():
    from flask import redirect, url_for
    return redirect(url_for('kelola_data'))


@pages_bp.route('/kelola-data/jenis-bahan')
def jenis_bahan_page():
    return render_template(
        'kelola_data/jenis_bahan.html',
        cafe_name=CAFE_NAME,
        active_menu='kelola-data',
    )


@pages_bp.route('/bahan')
def bahan_page():
    return render_template('bahan/index.html', cafe_name=CAFE_NAME, active_menu='bahan')


@pages_bp.route('/bahan/riwayat-stok')
def riwayat_stok_page():
    return render_template('bahan/riwayat_stok.html', cafe_name=CAFE_NAME, active_menu='riwayat-stok')


@pages_bp.route('/bahan/penyesuaian')
def penyesuaian_page():
    return render_template('bahan/penyesuaian.html', cafe_name=CAFE_NAME, active_menu='penyesuaian')


@pages_bp.route('/pembelian')
def pembelian_page():
    return render_template('pembelian/index.html', cafe_name=CAFE_NAME, active_menu='pembelian')


@pages_bp.route('/keuangan/pengeluaran')
def pengeluaran_page():
    return render_template(
        'keuangan/pengeluaran.html',
        cafe_name=CAFE_NAME,
        active_menu='pengeluaran',
        kategori_list=PENGELUARAN_KATEGORI,
    )


@pages_bp.route('/kelola-bahan/dashboard')
def dashboard_page():
    return render_template('bahan/dashboard.html', cafe_name=CAFE_NAME, active_menu='dashboard')


@pages_bp.route('/api/kelola-bahan/dashboard', methods=['GET'])
def dashboard_api_legacy():
    return dashboard_api()


@pages_bp.route('/api/dashboard/cafe', methods=['GET'])
def dashboard_api():
    try:
        stats = dashboard_service.get_dashboard_stats()
        return success_response('Data dashboard berhasil dimuat', stats)
    except Exception as e:
        return error_response('Gagal memuat dashboard', str(e), 500)
