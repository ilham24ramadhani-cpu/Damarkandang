(function () {
  function fmtRp(n) {
    return 'Rp' + Math.round(Number(n) || 0).toLocaleString('id-ID');
  }

  async function loadCafeDashboardHome() {
    try {
      const res = await fetch('/api/dashboard/cafe', { credentials: 'include' });
      const json = await res.json();
      if (!json.success) return;
      const d = json.data;

      const cards = document.getElementById('statisticsCards');
      if (cards) {
        cards.innerHTML = [
          { t: 'Bahan Aktif', v: d.total_bahan_aktif, c: 'primary' },
          { t: 'Menu Aktif', v: d.total_menu_aktif, c: 'info' },
          { t: 'Stok Menipis', v: d.bahan_stok_menipis_count, c: 'warning' },
          { t: 'Stok Habis', v: d.bahan_stok_habis_count, c: 'danger' },
          { t: 'Pemasukan Bulan Ini', v: fmtRp(d.total_pemasukan_bulan), c: 'success' },
          { t: 'Pengeluaran Bulan Ini', v: fmtRp(d.total_pengeluaran_bulan), c: 'secondary' },
          { t: 'Pembelian Bahan', v: fmtRp(d.total_pembelian_bulan), c: 'dark' },
          { t: 'Selisih (Pemasukan-Pengeluaran)', v: fmtRp(d.laba_kotor_bulan), c: 'primary' },
        ].map((x) => `
          <div class="col-md-3 col-sm-6"><div class="card shadow-sm border-0 h-100">
            <div class="card-body"><div class="text-muted small">${x.t}</div><div class="fs-4 fw-bold text-${x.c}">${x.v}</div></div>
          </div></div>`).join('');
      }

      const summary = document.getElementById('quickSummary');
      if (summary) {
        summary.innerHTML = `
          <p class="mb-2"><strong>Total stok bahan:</strong> ${(d.total_stok_gram || 0).toLocaleString('id-ID')} gram</p>
          <p class="mb-0"><strong>Jenis bahan:</strong> ${d.total_jenis_bahan}</p>`;
      }

      const activity = document.getElementById('recentActivity');
      if (activity) {
        const tx = (d.transaksi_terbaru || []).map((t) =>
          `<div class="d-flex justify-content-between border-bottom py-2"><span>Penjualan ${t.id_pemesanan || t.id_transaksi}</span><strong>${fmtRp(t.total)}</strong></div>`).join('');
        const pb = (d.pembelian_terbaru || []).map((p) =>
          `<div class="d-flex justify-content-between border-bottom py-2"><span>Pembelian ${p.nama_bahan}</span><strong>${fmtRp(p.total_harga)}</strong></div>`).join('');
        activity.innerHTML = tx + pb || '<p class="text-muted mb-0">Belum ada aktivitas</p>';
      }

    } catch (e) {
      console.warn('Cafe dashboard load failed', e);
    }
  }

  window.loadCafeDashboardHome = loadCafeDashboardHome;
  document.addEventListener('DOMContentLoaded', loadCafeDashboardHome);
})();
