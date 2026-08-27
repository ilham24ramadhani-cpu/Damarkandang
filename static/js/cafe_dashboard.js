(function () {
  async function loadDashboard() {
    const res = await fetch('/api/dashboard/cafe', { credentials: 'include' });
    const json = await res.json();
    if (!json.success) throw new Error(json.message);
    const d = json.data;

    const cards = [
      { label: 'Total Jenis Bahan', value: d.total_jenis_bahan, cls: '' },
      { label: 'Bahan Aktif', value: d.total_bahan_aktif, cls: 'success' },
      { label: 'Menu Aktif', value: d.total_menu_aktif, cls: 'info' },
      { label: 'Total Stok (gram)', value: d.total_stok_gram.toLocaleString('id-ID'), cls: '' },
      { label: 'Stok Menipis', value: d.bahan_stok_menipis_count, cls: 'warning' },
      { label: 'Pemasukan Bulan Ini', value: formatRupiah(d.total_pemasukan_bulan), cls: 'success' },
      { label: 'Pengeluaran Bulan Ini', value: formatRupiah(d.total_pengeluaran_bulan), cls: 'danger' },
    ];
    document.getElementById('statCards').innerHTML = cards.map((c) => `
      <div class="col-md-3 col-sm-6"><div class="card cafe-card stat-card ${c.cls}"><div class="card-body">
        <div class="text-muted small">${c.label}</div><div class="fs-4 fw-bold">${c.value}</div>
      </div></div></div>`).join('');

    document.getElementById('menipisBody').innerHTML = (d.bahan_stok_menipis || []).map((b) => `
      <tr><td>${b.nama_bahan}</td><td>${b.nama_jenis}</td><td>${formatGram(b.stok_gram)}</td>
      <td><span class="badge ${stokBadgeClass(b.stok_status)}">${b.stok_status_label}</span></td></tr>`).join('') || '<tr><td colspan="4" class="text-muted">Tidak ada</td></tr>';

    document.getElementById('pembelianBody').innerHTML = (d.pembelian_terbaru || []).map((p) => `
      <tr><td>${p.id_pembelian}</td><td>${p.tanggal}</td><td>${p.nama_bahan}</td><td>${formatRupiah(p.total_harga)}</td></tr>`).join('') || '<tr><td colspan="4" class="text-muted">Belum ada</td></tr>';

    document.getElementById('pengeluaranBody').innerHTML = (d.pengeluaran_terbaru || []).map((p) => `
      <tr><td>${p.tanggal}</td><td>${p.kategori}</td><td>${formatRupiah(p.nominal)}</td><td>${p.keterangan || '-'}</td></tr>`).join('') || '<tr><td colspan="4" class="text-muted">Belum ada</td></tr>';
  }

  loadDashboard().catch((e) => showToast(e.message, 'danger'));
})();
