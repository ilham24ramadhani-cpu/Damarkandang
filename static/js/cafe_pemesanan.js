(function () {
  let page = 1;
  const perPage = 15;
  let loading = false;

  function itemSummary(items) {
    return (items || []).slice(0, 2).map((i) => `${i.nama_menu} x${i.qty}`).join(', ')
      + ((items || []).length > 2 ? '...' : '');
  }

  async function loadStats() {
    const bulan = filterBulan.value;
    const q = bulan ? '?bulan=' + bulan : '';
    const res = await CafeAPI.get('/kasir/transaksi/stats' + q, { key: 'kasir-stats' });
    const d = res.data;
    statCards.innerHTML = [
      { t: 'Jumlah Penjualan', v: d.total, c: 'primary' },
      { t: 'Total Pemasukan', v: formatRupiah(d.total_nilai_lunas), c: 'success' },
      { t: 'Belum Lunas (lama)', v: d.ordering, c: 'warning' },
    ].map((x) => `<div class="col-md-4 col-sm-6"><div class="card cafe-card h-100"><div class="card-body py-3">
      <div class="text-muted small">${x.t}</div><div class="fw-bold fs-5 text-${x.c}">${x.v}</div></div></div></div>`).join('');
  }

  async function loadTable(p = 1) {
    page = p;
    const params = new URLSearchParams({ page, per_page: perPage });
    if (filterSearch.value.trim()) params.set('search', filterSearch.value.trim());
    if (filterBulan.value) params.set('bulan', filterBulan.value);

    const res = await CafeAPI.get('/kasir/transaksi?' + params.toString(), { key: 'kasir-list' });
    const items = res.data.items || [];
    const total = res.data.total || 0;

    tableBody.innerHTML = items.length ? items.map((t) => {
      const id = t.id_pemesanan || t.id_transaksi;
      const lunasBtn = t.status_pembayaran === 'ordering'
        ? `<button class="btn btn-sm btn-outline-success" data-lunas="${id}">Lunas</button>` : '';
      return `<tr>
        <td class="fw-semibold">${id}</td>
        <td>${t.petugas?.nama_lengkap || t.nama_pelanggan || '-'}</td>
        <td>${t.tanggal}</td>
        <td><small>${itemSummary(t.items) || '-'}</small></td>
        <td class="text-end fw-semibold">${formatRupiah(t.total)}</td>
        <td class="text-center text-nowrap">
          <button class="btn btn-sm btn-outline-primary" data-struk="${id}" title="Nota">Nota</button>
          <a class="btn btn-sm btn-outline-warning" href="/kelola/pemesanan/tambah?edit=${encodeURIComponent(id)}" title="Edit">Edit</a>
          <button class="btn btn-sm btn-outline-danger" data-hapus="${id}" title="Hapus">Hapus</button>
          ${lunasBtn}
        </td></tr>`;
    }).join('') : '<tr><td colspan="6" class="text-center text-muted py-4">Belum ada penjualan</td></tr>';

    renderPagination(document.getElementById('pagination'), page, total, perPage, (np) => {
      safeLoad(loadTable(np));
    });
  }

  async function refreshAll(p = 1) {
    if (loading) return;
    loading = true;
    try {
      await Promise.all([
        safeLoad(loadStats(), false),
        safeLoad(loadTable(p), false),
      ]);
    } catch (err) {
      if (!isAbortError(err)) showToast(err.message, 'danger');
    } finally {
      loading = false;
    }
  }

  tableBody.addEventListener('click', async (e) => {
    const strukBtn = e.target.closest('[data-struk]');
    const lunasBtn = e.target.closest('[data-lunas]');
    const hapusBtn = e.target.closest('[data-hapus]');
    if (strukBtn) {
      try {
        const res = await CafeAPI.get('/kasir/transaksi/' + strukBtn.dataset.struk, { key: 'kasir-detail' });
        PemesananUI.renderStruk(res.data);
      } catch (err) {
        if (!isAbortError(err)) showToast(err.message, 'danger');
      }
    }
    if (lunasBtn) {
      try {
        const res = await CafeAPI.post('/kasir/transaksi/' + lunasBtn.dataset.lunas + '/lunas', {});
        showToast('Penjualan lunas — pemasukan tercatat & stok berkurang');
        PemesananUI.renderStruk(res.data);
        refreshAll(page);
      } catch (err) { showToast(err.message, 'danger'); }
    }
    if (hapusBtn) {
      const id = hapusBtn.dataset.hapus;
      if (!confirm(`Hapus penjualan ${id}?\nStok bahan akan dikembalikan dan pemasukan dibatalkan.`)) return;
      try {
        await CafeAPI.delete('/kasir/transaksi/' + id);
        showToast('Penjualan dihapus — stok dikembalikan');
        refreshAll(page);
      } catch (err) { showToast(err.message, 'danger'); }
    }
  });

  btnFilter.addEventListener('click', () => refreshAll(1));
  filterSearch.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); refreshAll(1); }
  });
  filterSearch.addEventListener('input', debounce(() => refreshAll(1), 400));
  filterBulan.addEventListener('change', () => refreshAll(1));
  document.getElementById('btnPrintStruk')?.addEventListener('click', () => PemesananUI.printStruk());

  filterBulan.value = new Date().toISOString().slice(0, 7);
  refreshAll(1);
})();
