(function () {
  let pollTimer = null;
  let loading = false;

  async function loadStok() {
    if (loading || document.hidden) return;
    loading = true;
    try {
      const search = document.getElementById('searchInput').value.trim();
      const q = search ? '?search=' + encodeURIComponent(search) : '';
      const res = await CafeAPI.get('/stok/jenis-bahan' + q, { key: 'stok-jenis' });
      const items = res.data.items || [];

      let normal = 0, menipis = 0, habis = 0;
      items.forEach((b) => {
        if (b.stok_status === 'menipis') menipis++;
        else if (b.stok_status === 'habis') habis++;
        else normal++;
      });

      document.getElementById('stokSummary').innerHTML = `
      <div class="col-md-3"><div class="card cafe-card stat-card"><div class="card-body"><div class="text-muted small">Jenis Bahan</div><div class="fs-4 fw-bold">${items.length}</div></div></div></div>
      <div class="col-md-3"><div class="card cafe-card stat-card success"><div class="card-body"><div class="text-muted small">Stok Normal</div><div class="fs-4 fw-bold">${normal}</div></div></div></div>
      <div class="col-md-3"><div class="card cafe-card stat-card warning"><div class="card-body"><div class="text-muted small">Stok Menipis</div><div class="fs-4 fw-bold">${menipis}</div></div></div></div>
      <div class="col-md-3"><div class="card cafe-card stat-card danger"><div class="card-body"><div class="text-muted small">Stok Habis</div><div class="fs-4 fw-bold">${habis}</div></div></div></div>`;

      document.getElementById('tableBody').innerHTML = items.length
        ? items.map((r) => `
        <tr>
          <td><strong>${r.nama_jenis}</strong></td>
          <td>${formatGram(r.stok_gram)}</td>
          <td><span class="badge ${stokBadgeClass(r.stok_status)}">${r.stok_status_label}</span></td>
        </tr>`).join('')
        : '<tr><td colspan="3" class="text-muted text-center">Belum ada stok bahan terdaftar</td></tr>';

      const ts = res.data.updated_at ? new Date(res.data.updated_at) : new Date();
      document.getElementById('lastUpdate').textContent = 'Update: ' + ts.toLocaleTimeString('id-ID');
    } catch (err) {
      console.error(err);
    } finally {
      loading = false;
    }
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(() => {
      if (!document.hidden) loadStok();
    }, 60000);
  }

  document.getElementById('searchInput').addEventListener('input', debounce(loadStok, 400));
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) loadStok();
  });

  loadStok();
  startPolling();
})();
