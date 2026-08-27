"""Date range helpers — pakai $gte/$lte agar index tanggal terpakai."""

import calendar


def bulan_bounds(bulan):
    """Kembalikan (tanggal_dari, tanggal_sampai) untuk YYYY-MM, atau (None, None)."""
    nilai = (bulan or '').strip()
    if not nilai or '-' not in nilai:
        return None, None
    try:
        y, m = nilai.split('-')[:2]
        y, m = int(y), int(m)
        if m < 1 or m > 12:
            return None, None
        last = calendar.monthrange(y, m)[1]
        return f'{y}-{m:02d}-01', f'{y}-{m:02d}-{last:02d}'
    except (TypeError, ValueError):
        return None, None


def bulan_query(bulan, field='tanggal'):
    """Filter Mongo untuk satu bulan tanpa regex."""
    dari, sampai = bulan_bounds(bulan)
    if not dari:
        return {}
    return {field: {'$gte': dari, '$lte': sampai}}
