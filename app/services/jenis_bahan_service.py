from app.config import KATEGORI_BAHAN, KATEGORI_PCS
from app.database import get_db
from app.utils.id_generator import generate_id_jenis_bahan
from app.utils.response import now_iso

BENTUK_NON_CAIRAN = 'non_cairan'
BENTUK_CAIRAN = 'cairan'
BENTUK_BAHAN_CHOICES = (BENTUK_NON_CAIRAN, BENTUK_CAIRAN)

SATUAN_KG = 'kg'
SATUAN_PCS = 'pcs'
SATUAN_BERAT_CHOICES = (SATUAN_KG, SATUAN_PCS)


def _normalize_kategori(value, default='Minuman'):
    kategori = (value if value is not None else default) or default
    kategori = str(kategori).strip()
    # Normalisasi casing
    for k in KATEGORI_BAHAN:
        if kategori.lower() == k.lower():
            return k
    if kategori.lower() in ('minuman', 'makanan', 'kopral', 'roasted', 'skincare'):
        return kategori.title() if kategori.lower() != 'skincare' else 'Skincare'
    raise ValueError(
        'Kategori harus salah satu: Minuman, Makanan, Kopral, Roasted, Skincare'
    )


def is_kategori_pcs(kategori):
    try:
        return _normalize_kategori(kategori) in KATEGORI_PCS
    except ValueError:
        return False


def _normalize_bentuk(value):
    bentuk = (value or BENTUK_NON_CAIRAN).strip().lower().replace(' ', '_')
    if bentuk in ('cairan', 'liquid'):
        return BENTUK_CAIRAN
    return BENTUK_NON_CAIRAN


def _normalize_satuan_berat(value):
    s = (value or SATUAN_KG).strip().lower()
    if s in ('pcs', 'pc', 'pcs.', 'buah', 'kemasan', 'pack'):
        return SATUAN_PCS
    return SATUAN_KG


def _parse_cairan_fields(data, bentuk):
    harga_per_pack = None
    kg_per_pack = None
    if bentuk == BENTUK_CAIRAN:
        harga_per_pack = int(round(float(data.get('harga_per_pack') or 0)))
        kg_per_pack = float(data.get('kg_per_pack') or 0)
        if harga_per_pack <= 0:
            raise ValueError('Harga per pack wajib diisi untuk bahan cairan')
        if kg_per_pack <= 0:
            raise ValueError('Berat kg per pack wajib diisi untuk bahan cairan')
    return harga_per_pack, kg_per_pack


def _parse_non_cairan_fields(data, bentuk, kategori=None):
    """
    Non cairan: satuan_berat kg atau pcs.
    Kategori Kopral/Roasted/Skincare → wajib pcs.
    """
    if bentuk != BENTUK_NON_CAIRAN:
        return {
            'satuan_berat': SATUAN_KG,
            'harga_per_kg': None,
            'harga_per_pcs': None,
            'gram_per_pcs': None,
        }

    # Paksa pcs untuk kategori kemasan
    if is_kategori_pcs(kategori or data.get('kategori')):
        data = dict(data)
        data['satuan_berat'] = SATUAN_PCS

    satuan = _normalize_satuan_berat(data.get('satuan_berat') or data.get('satuan_harga') or SATUAN_KG)

    if satuan == SATUAN_PCS:
        harga_per_pcs = int(round(float(
            data.get('harga_per_pcs')
            or data.get('harga')
            or data.get('harga_per_kg')
            or 0
        )))
        gram_per_pcs = float(
            data.get('gram_per_pcs')
            or data.get('isi_kemasan_gram')
            or 0
        )
        if gram_per_pcs <= 0 and data.get('kg_per_pcs') is not None:
            gram_per_pcs = float(data.get('kg_per_pcs') or 0) * 1000
        if harga_per_pcs <= 0:
            raise ValueError('Harga per pcs wajib diisi')
        if gram_per_pcs <= 0:
            raise ValueError('Berat isi per pcs (gram) wajib diisi — contoh 250, 500, atau 1000')
        kg = gram_per_pcs / 1000.0
        harga_per_kg = int(round(harga_per_pcs / kg)) if kg > 0 else 0
        return {
            'satuan_berat': SATUAN_PCS,
            'harga_per_kg': harga_per_kg,
            'harga_per_pcs': harga_per_pcs,
            'gram_per_pcs': int(round(gram_per_pcs)),
        }

    harga_per_kg = int(round(float(data.get('harga_per_kg') or data.get('harga') or 0)))
    if harga_per_kg <= 0:
        raise ValueError('Harga per kg wajib diisi')
    return {
        'satuan_berat': SATUAN_KG,
        'harga_per_kg': harga_per_kg,
        'harga_per_pcs': None,
        'gram_per_pcs': None,
    }


def _apply_bentuk_fields(doc):
    bentuk = _normalize_bentuk(doc.get('bentuk_bahan'))
    doc['bentuk_bahan'] = bentuk
    doc['bentuk_bahan_label'] = bentuk_bahan_label(bentuk)
    try:
        doc['kategori'] = _normalize_kategori(doc.get('kategori') or 'Minuman')
    except ValueError:
        doc['kategori'] = 'Minuman'
    doc['kategori_pcs'] = doc['kategori'] in KATEGORI_PCS
    if bentuk == BENTUK_CAIRAN:
        doc['harga_per_pack'] = int(doc.get('harga_per_pack') or 0)
        doc['kg_per_pack'] = float(doc.get('kg_per_pack') or 0)
        doc.pop('harga_per_kg', None)
        doc.pop('satuan_berat', None)
        doc.pop('harga_per_pcs', None)
        doc.pop('gram_per_pcs', None)
        doc.pop('satuan_harga', None)
    else:
        # Kategori kemasan → pcs
        if doc['kategori'] in KATEGORI_PCS:
            satuan = SATUAN_PCS
        else:
            satuan = _normalize_satuan_berat(doc.get('satuan_berat') or doc.get('satuan_harga') or SATUAN_KG)
            if doc.get('harga_per_pcs') and doc.get('gram_per_pcs') and not doc.get('satuan_berat'):
                satuan = SATUAN_PCS
        doc['satuan_berat'] = satuan
        doc['satuan_berat_label'] = 'Pcs' if satuan == SATUAN_PCS else 'Kg'
        harga_kg = int(doc.get('harga_per_kg') or 0)
        if satuan == SATUAN_PCS:
            harga_pcs = int(doc.get('harga_per_pcs') or 0)
            gram_pcs = int(doc.get('gram_per_pcs') or 0)
            if harga_pcs > 0 and gram_pcs > 0 and harga_kg <= 0:
                harga_kg = int(round(harga_pcs / (gram_pcs / 1000.0)))
            doc['harga_per_pcs'] = harga_pcs
            doc['gram_per_pcs'] = gram_pcs
            doc['harga_per_kg'] = harga_kg
            doc['harga_tampil'] = harga_pcs
            doc['harga_tampil_label'] = f'{harga_pcs}/pcs' if harga_pcs else '-'
        else:
            doc['harga_per_kg'] = harga_kg
            doc.pop('harga_per_pcs', None)
            doc.pop('gram_per_pcs', None)
            doc['harga_tampil'] = harga_kg
            doc['harga_tampil_label'] = f'{harga_kg}/kg' if harga_kg else '-'
        doc.pop('harga_per_pack', None)
        doc.pop('kg_per_pack', None)
        doc.pop('satuan_harga', None)
    return doc


def bentuk_bahan_label(bentuk):
    return 'Cairan' if _normalize_bentuk(bentuk) == BENTUK_CAIRAN else 'Non Cairan'


def is_cairan(jenis):
    return _normalize_bentuk((jenis or {}).get('bentuk_bahan')) == BENTUK_CAIRAN


def is_pcs(jenis):
    if is_cairan(jenis):
        return False
    if is_kategori_pcs((jenis or {}).get('kategori')):
        return True
    return _normalize_satuan_berat((jenis or {}).get('satuan_berat')) == SATUAN_PCS


def list_jenis_bahan(search='', status='', page=1, per_page=10, active_only=False, kategori=''):
    db = get_db()
    query = {}
    if search:
        query['$or'] = [
            {'nama_jenis': {'$regex': search, '$options': 'i'}},
            {'id_jenis': {'$regex': search, '$options': 'i'}},
        ]
    if status:
        query['status'] = status.lower()
    if active_only:
        query['status'] = 'aktif'
    if kategori:
        try:
            query['kategori'] = _normalize_kategori(kategori)
        except ValueError:
            pass

    skip = (page - 1) * per_page
    total = db.jenis_bahan.count_documents(query)
    items = list(db.jenis_bahan.find(query).sort('id_jenis', 1).skip(skip).limit(per_page))
    return [_apply_bentuk_fields(item) for item in items], total


def get_jenis_bahan(id_jenis):
    doc = get_db().jenis_bahan.find_one({'id_jenis': id_jenis})
    return _apply_bentuk_fields(doc) if doc else None


def create_jenis_bahan(data):
    db = get_db()
    nama = (data.get('nama_jenis') or '').strip()
    if not nama:
        raise ValueError('Nama jenis wajib diisi')

    bentuk = _normalize_bentuk(data.get('bentuk_bahan'))
    kategori = _normalize_kategori(data.get('kategori') or 'Minuman')
    # Kategori pcs tidak boleh cairan
    if kategori in KATEGORI_PCS and bentuk == BENTUK_CAIRAN:
        raise ValueError(f'Kategori {kategori} memakai konsep pcs, bukan cairan')

    id_jenis = generate_id_jenis_bahan()
    doc = {
        'id_jenis': id_jenis,
        'nama_jenis': nama,
        'kategori': kategori,
        'deskripsi': (data.get('deskripsi') or '').strip(),
        'bentuk_bahan': bentuk,
        'status': (data.get('status') or 'aktif').lower(),
        'created_at': now_iso(),
        'updated_at': now_iso(),
    }
    if bentuk == BENTUK_CAIRAN:
        harga_per_pack, kg_per_pack = _parse_cairan_fields(data, bentuk)
        doc['harga_per_pack'] = harga_per_pack
        doc['kg_per_pack'] = kg_per_pack
    else:
        fields = _parse_non_cairan_fields(data, bentuk, kategori=kategori)
        doc['satuan_berat'] = fields['satuan_berat']
        doc['harga_per_kg'] = fields['harga_per_kg']
        if fields['satuan_berat'] == SATUAN_PCS:
            doc['harga_per_pcs'] = fields['harga_per_pcs']
            doc['gram_per_pcs'] = fields['gram_per_pcs']
    db.jenis_bahan.insert_one(doc)
    return _apply_bentuk_fields(doc)


def update_jenis_bahan(id_jenis, data):
    db = get_db()
    doc = get_jenis_bahan(id_jenis)
    if not doc:
        raise ValueError('Jenis bahan tidak ditemukan')

    update = {'updated_at': now_iso()}
    unset = {}
    if 'nama_jenis' in data:
        nama = (data.get('nama_jenis') or '').strip()
        if not nama:
            raise ValueError('Nama jenis wajib diisi')
        update['nama_jenis'] = nama
    if 'deskripsi' in data:
        update['deskripsi'] = (data.get('deskripsi') or '').strip()
    if 'status' in data:
        update['status'] = (data.get('status') or 'aktif').lower()

    kategori = _normalize_kategori(data.get('kategori', doc.get('kategori') or 'Minuman'))
    if 'kategori' in data:
        update['kategori'] = kategori

    bentuk = _normalize_bentuk(data.get('bentuk_bahan', doc.get('bentuk_bahan')))
    old_bentuk = _normalize_bentuk(doc.get('bentuk_bahan'))
    if kategori in KATEGORI_PCS and bentuk == BENTUK_CAIRAN:
        raise ValueError(f'Kategori {kategori} memakai konsep pcs, bukan cairan')
    if 'bentuk_bahan' in data:
        if bentuk != old_bentuk:
            used = db.bahan.count_documents({'id_jenis': id_jenis, 'id_bahan': {'$exists': True}})
            if used > 0:
                raise ValueError('Bentuk bahan tidak dapat diubah karena sudah digunakan di Kelola Bahan')
        update['bentuk_bahan'] = bentuk

    harga_changed = False
    if bentuk == BENTUK_CAIRAN:
        if any(k in data for k in ('harga_per_pack', 'kg_per_pack')) or (
            'bentuk_bahan' in data and old_bentuk != BENTUK_CAIRAN
        ):
            harga_per_pack, kg_per_pack = _parse_cairan_fields(data, bentuk)
            update['harga_per_pack'] = harga_per_pack
            update['kg_per_pack'] = kg_per_pack
        if 'bentuk_bahan' in data and old_bentuk != BENTUK_CAIRAN:
            unset.update({
                'harga_per_kg': '',
                'satuan_berat': '',
                'harga_per_pcs': '',
                'gram_per_pcs': '',
                'satuan_harga': '',
            })
    else:
        price_keys = (
            'harga_per_kg', 'harga', 'satuan_berat', 'satuan_harga',
            'harga_per_pcs', 'gram_per_pcs', 'kg_per_pcs', 'isi_kemasan_gram', 'kategori',
        )
        if any(k in data for k in price_keys) or (
            'bentuk_bahan' in data and old_bentuk != BENTUK_NON_CAIRAN
        ) or kategori in KATEGORI_PCS:
            merged = {
                'satuan_berat': data.get('satuan_berat', doc.get('satuan_berat')),
                'harga_per_kg': data.get('harga_per_kg', doc.get('harga_per_kg')),
                'harga_per_pcs': data.get('harga_per_pcs', doc.get('harga_per_pcs')),
                'gram_per_pcs': data.get('gram_per_pcs', doc.get('gram_per_pcs')),
                'kg_per_pcs': data.get('kg_per_pcs'),
                'harga': data.get('harga'),
                'kategori': kategori,
            }
            for k in price_keys:
                if k in data:
                    merged[k] = data[k]
            fields = _parse_non_cairan_fields(merged, bentuk, kategori=kategori)
            update['satuan_berat'] = fields['satuan_berat']
            update['harga_per_kg'] = fields['harga_per_kg']
            if fields['satuan_berat'] == SATUAN_PCS:
                update['harga_per_pcs'] = fields['harga_per_pcs']
                update['gram_per_pcs'] = fields['gram_per_pcs']
            else:
                unset.update({'harga_per_pcs': '', 'gram_per_pcs': ''})
            harga_changed = True
        if 'bentuk_bahan' in data and old_bentuk != BENTUK_NON_CAIRAN:
            unset.update({'harga_per_pack': '', 'kg_per_pack': ''})

    ops = {'$set': update}
    if unset:
        ops['$unset'] = unset
    db.jenis_bahan.update_one({'id_jenis': id_jenis}, ops)

    if 'nama_jenis' in update or 'kategori' in update:
        from app.services.bahan_service import sync_nama_from_jenis_master
        nama = update.get('nama_jenis') or doc.get('nama_jenis')
        sync_nama_from_jenis_master(id_jenis, nama, kategori=update.get('kategori') or kategori)
    if harga_changed and 'harga_per_kg' in update:
        from app.services.bahan_service import sync_harga_from_jenis_master
        sync_payload = dict(update)
        sync_payload['kategori'] = kategori
        sync_harga_from_jenis_master(id_jenis, sync_payload)

    return get_jenis_bahan(id_jenis)


def delete_jenis_bahan(id_jenis):
    db = get_db()
    doc = get_jenis_bahan(id_jenis)
    if not doc:
        raise ValueError('Jenis bahan tidak ditemukan')

    used = db.bahan.count_documents({'id_jenis': id_jenis, 'id_bahan': {'$exists': True}})
    if used > 0:
        db.jenis_bahan.update_one(
            {'id_jenis': id_jenis},
            {'$set': {'status': 'nonaktif', 'updated_at': now_iso()}},
        )
        return {'soft_deleted': True, 'message': 'Jenis bahan dinonaktifkan karena masih digunakan'}

    db.jenis_bahan.delete_one({'id_jenis': id_jenis})
    return {'soft_deleted': False, 'message': 'Jenis bahan berhasil dihapus'}
