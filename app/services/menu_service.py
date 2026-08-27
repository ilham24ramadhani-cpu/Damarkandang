from app.config import KATEGORI_BAHAN, KATEGORI_PCS
from app.database import get_db
from app.services import bahan_service
from app.utils.id_generator import generate_id_menu
from app.utils.response import now_iso
from app.utils.unit_converter import total_harga_dari_gram

KATEGORI_PRODUK = KATEGORI_BAHAN


def _normalize_kategori(value, default='Minuman'):
    kategori = (value if value is not None else default) or default
    kategori = str(kategori).strip()
    for k in KATEGORI_PRODUK:
        if kategori.lower() == k.lower():
            return k
    raise ValueError(
        'Kategori produk harus Minuman, Makanan, Kopral, Roasted, atau Skincare'
    )


def is_kategori_pcs(kategori):
    try:
        return _normalize_kategori(kategori) in KATEGORI_PCS
    except ValueError:
        return False


def list_menu(search='', status='', page=1, per_page=20, active_only=False, light=False):
    db = get_db()
    query = {}
    if search:
        query['$or'] = [
            {'nama_menu': {'$regex': search, '$options': 'i'}},
            {'id_menu': {'$regex': search, '$options': 'i'}},
        ]
    if status:
        query['status'] = status.lower()
    if active_only:
        query['status'] = 'aktif'

    skip = (page - 1) * per_page
    total = db.menu.count_documents(query)
    projection = None
    if light:
        projection = {
            'id_menu': 1,
            'nama_menu': 1,
            'kategori': 1,
            'harga_jual': 1,
            'status': 1,
        }
    items = list(db.menu.find(query, projection).sort('nama_menu', 1).skip(skip).limit(per_page))
    return items, total


def get_menu(id_menu):
    return get_db().menu.find_one({'id_menu': id_menu})


def _harga_bahan_per_kg(bahan):
    return int(bahan.get('harga_per_kg') or bahan.get('harga_terakhir') or 0)


def _is_bahan_pcs(bahan):
    if (bahan.get('satuan_berat') or '').strip().lower() == 'pcs':
        return True
    return is_kategori_pcs(bahan.get('kategori'))


def _normalize_resep(resep_raw):
    if not resep_raw or not isinstance(resep_raw, list):
        raise ValueError('Resep bahan wajib diisi minimal 1 baris')

    prepared = []
    id_bahans = []
    for row in resep_raw:
        id_bahan = (row.get('id_bahan') or '').strip()
        if not id_bahan:
            continue
        prepared.append(row)
        id_bahans.append(id_bahan)

    if not prepared:
        raise ValueError('Resep bahan wajib diisi')

    bahan_map = bahan_service.get_bahan_many(id_bahans)
    resep = []
    for row in prepared:
        id_bahan = (row.get('id_bahan') or '').strip()
        bahan = bahan_map.get(id_bahan)
        if not bahan:
            raise ValueError(f'Bahan {id_bahan} tidak ditemukan')

        harga_per_kg = _harga_bahan_per_kg(bahan)
        if _is_bahan_pcs(bahan):
            harga_per_pcs = int(bahan.get('harga_per_pcs') or 0)
            gram_per_pcs = int(bahan.get('gram_per_pcs') or 0)
            if harga_per_pcs <= 0 or gram_per_pcs <= 0:
                raise ValueError(
                    f'Bahan {bahan.get("nama_bahan") or id_bahan} satuan pcs belum lengkap (harga & isi gram)'
                )
            # Terima jumlah_pcs; fallback jumlah_gram / gram_per_pcs (edit data lama)
            if row.get('jumlah_pcs') is not None and str(row.get('jumlah_pcs')).strip() != '':
                jumlah_pcs = float(row.get('jumlah_pcs') or 0)
            elif row.get('jumlah') is not None and (row.get('satuan') or '').lower() == 'pcs':
                jumlah_pcs = float(row.get('jumlah') or 0)
            elif row.get('jumlah_gram'):
                jumlah_pcs = float(row.get('jumlah_gram') or 0) / gram_per_pcs
            else:
                jumlah_pcs = float(row.get('jumlah') or 0)
            if jumlah_pcs <= 0:
                raise ValueError('Jumlah bahan resep pcs harus lebih dari 0')
            # Izinkan pecahan kecil (0.5 pcs) tapi stok tetap integer gram
            jumlah_gram = int(round(jumlah_pcs * gram_per_pcs))
            if jumlah_gram <= 0:
                raise ValueError('Jumlah bahan resep menghasilkan stok 0 gram')
            biaya_modal = int(round(jumlah_pcs * harga_per_pcs))
            resep.append({
                'id_bahan': id_bahan,
                'nama_bahan': bahan.get('nama_bahan', ''),
                'satuan': 'pcs',
                'jumlah_pcs': jumlah_pcs if jumlah_pcs != int(jumlah_pcs) else int(jumlah_pcs),
                'jumlah_gram': jumlah_gram,
                'gram_per_pcs': gram_per_pcs,
                'harga_per_pcs': harga_per_pcs,
                'harga_per_kg': harga_per_kg,
                'biaya_modal': biaya_modal,
            })
        else:
            jumlah = int(row.get('jumlah_gram') or row.get('jumlah') or 0)
            if jumlah <= 0:
                raise ValueError('Jumlah bahan resep harus lebih dari 0 gram')
            biaya_modal = total_harga_dari_gram(harga_per_kg, jumlah)
            resep.append({
                'id_bahan': id_bahan,
                'nama_bahan': bahan.get('nama_bahan', ''),
                'satuan': 'gram',
                'jumlah_gram': jumlah,
                'harga_per_kg': harga_per_kg,
                'biaya_modal': biaya_modal,
            })
    return resep


def _total_modal(resep):
    return int(sum(int(r.get('biaya_modal') or 0) for r in resep))


def _parse_margin(data, default=0):
    raw = data.get('margin_persen', data.get('keuntungan_persen', default))
    try:
        margin = float(raw if raw is not None else default)
    except (TypeError, ValueError):
        raise ValueError('Persentase keuntungan tidak valid')
    if margin < 0:
        raise ValueError('Persentase keuntungan tidak boleh negatif')
    return margin


def _harga_jual_dari_modal(modal, margin_persen):
    """Harga jual = modal + (modal × margin%). Contoh modal 2000, 30% → 2600."""
    return int(round(float(modal) * (1 + float(margin_persen) / 100.0)))


def _margin_dari_harga(modal, harga):
    """Keuntungan % = ((harga jual − modal) / modal) × 100. Modal 0 → 0%."""
    if modal <= 0:
        return 0.0
    return round(((float(harga) - float(modal)) / float(modal)) * 100, 2)


def _parse_harga_jual(data):
    try:
        harga = int(round(float(data.get('harga_jual') or 0)))
    except (TypeError, ValueError):
        raise ValueError('Harga jual tidak valid')
    if harga < 0:
        raise ValueError('Harga jual tidak boleh negatif')
    return harga


def _resolve_harga_dan_margin(data, modal):
    """
    Prioritas:
    1. Jika harga_jual dikirim → simpan harga itu, keuntungan % dihitung dari modal.
    2. Jika hanya margin_persen / keuntungan_persen dikirim → hitung harga jual dari modal.
    3. Default → harga jual = modal, keuntungan 0%.
    """
    has_margin = 'margin_persen' in data or 'keuntungan_persen' in data
    has_harga = 'harga_jual' in data

    if has_harga:
        harga = _parse_harga_jual(data)
        return harga, _margin_dari_harga(modal, harga)

    if has_margin:
        margin = _parse_margin(data)
        harga = _harga_jual_dari_modal(modal, margin)
        return harga, margin

    return int(modal), 0.0


def create_menu(data):
    db = get_db()
    nama = (data.get('nama_menu') or '').strip()
    if not nama:
        raise ValueError('Nama produk wajib diisi')

    resep = _normalize_resep(data.get('bahan_resep') or data.get('resep'))
    modal = _total_modal(resep)
    harga, margin = _resolve_harga_dan_margin(data, modal)

    doc = {
        'id_menu': generate_id_menu(),
        'nama_menu': nama,
        'kategori': _normalize_kategori(data.get('kategori')),
        'biaya_modal': modal,
        'margin_persen': margin,
        'harga_jual': harga,
        'bahan_resep': resep,
        'status': (data.get('status') or 'aktif').lower(),
        'created_at': now_iso(),
        'updated_at': now_iso(),
    }
    db.menu.insert_one(doc)
    return doc


def update_menu(id_menu, data):
    db = get_db()
    doc = get_menu(id_menu)
    if not doc:
        raise ValueError('Produk tidak ditemukan')

    update = {'updated_at': now_iso()}
    if 'nama_menu' in data:
        nama = (data.get('nama_menu') or '').strip()
        if not nama:
            raise ValueError('Nama produk wajib diisi')
        update['nama_menu'] = nama
    if 'kategori' in data:
        update['kategori'] = _normalize_kategori(data.get('kategori'))
    if 'status' in data:
        update['status'] = (data.get('status') or 'aktif').lower()

    resep = doc.get('bahan_resep') or []
    if 'bahan_resep' in data or 'resep' in data:
        resep = _normalize_resep(data.get('bahan_resep') or data.get('resep'))
        update['bahan_resep'] = resep

    need_pricing = (
        'bahan_resep' in data
        or 'resep' in data
        or 'margin_persen' in data
        or 'keuntungan_persen' in data
        or 'harga_jual' in data
    )
    if need_pricing:
        modal = _total_modal(resep)
        # Saat resep berubah tapi harga jual tidak dikirim, pertahankan harga jual lama
        pricing_data = dict(data)
        if (
            ('bahan_resep' in data or 'resep' in data)
            and 'harga_jual' not in data
            and 'margin_persen' not in data
            and 'keuntungan_persen' not in data
        ):
            pricing_data['harga_jual'] = doc.get('harga_jual', 0)
        harga, margin = _resolve_harga_dan_margin(pricing_data, modal)
        update['biaya_modal'] = modal
        update['margin_persen'] = margin
        update['harga_jual'] = harga

    db.menu.update_one({'id_menu': id_menu}, {'$set': update})
    return get_menu(id_menu)


def delete_menu(id_menu):
    db = get_db()
    doc = get_menu(id_menu)
    if not doc:
        raise ValueError('Produk tidak ditemukan')

    used = db.transaksi_kasir.count_documents({'items.id_menu': id_menu})
    if used > 0:
        db.menu.update_one(
            {'id_menu': id_menu},
            {'$set': {'status': 'nonaktif', 'updated_at': now_iso()}},
        )
        return {'soft_deleted': True, 'message': 'Produk dinonaktifkan karena sudah pernah ditransaksikan'}

    db.menu.delete_one({'id_menu': id_menu})
    return {'soft_deleted': False, 'message': 'Produk berhasil dihapus'}
