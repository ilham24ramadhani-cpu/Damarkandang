from app.config import GRAM_PER_KG, SATUAN_PEMBELIAN


def normalize_satuan(satuan):
    s = (satuan or '').strip().lower()
    if s in ('kg', 'kilogram', 'kilogram'):
        return 'kg'
    if s in ('gram', 'g', 'gr'):
        return 'gram'
    return s


def to_gram(jumlah, satuan):
    satuan = normalize_satuan(satuan)
    if satuan not in SATUAN_PEMBELIAN:
        raise ValueError(f'Satuan tidak valid: {satuan}. Gunakan gram atau kg.')
    qty = float(jumlah)
    if qty <= 0:
        raise ValueError('Jumlah harus lebih dari 0')
    if satuan == 'kg':
        return int(round(qty * GRAM_PER_KG))
    return int(round(qty))


def to_kg(jumlah_gram):
    return float(jumlah_gram or 0) / GRAM_PER_KG


def total_harga_dari_gram(harga_per_kg, jumlah_gram):
    """Total harga pembelian: jumlah kg × harga per kg."""
    kg = to_kg(jumlah_gram)
    return int(round(kg * float(harga_per_kg or 0)))


def format_gram(gram_val):
    try:
        val = int(round(float(gram_val or 0)))
    except (TypeError, ValueError):
        val = 0
    return f'{val:,}'.replace(',', '.') + ' gram'


def format_rupiah(amount):
    try:
        val = int(round(float(amount or 0)))
    except (TypeError, ValueError):
        val = 0
    return 'Rp' + f'{val:,}'.replace(',', '.')
