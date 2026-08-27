(function () {
  let page = 1;
  const perPage = 20;

  async function loadBahanFilter() {
    const res = await CafeAPI.get('/bahan?per_page=100');
    const sel = document.getElementById('filterBahan');
    (res.data.items || []).forEach((b) => {
      sel.innerHTML += `<option value="${b.id_bahan}">${b.nama_bahan}</option>`;
    });
  }

  async function loadData() {
    const idBahan = document.getElementById('filterBahan').value;
    const tipe = document.getElementById('filterTipe').value;
    const q = new URLSearchParams({ page, per_page: perPage, id_bahan: idBahan, tipe });
    const res = await CafeAPI.get('/riwayat-stok?' + q);
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';
    (res.data.items || []).forEach((row) => {
      const tr = document.createElement('tr');
      const sign = row.jumlah_gram >= 0 ? '+' : '';
      tr.innerHTML = `
        <td>${row.id_riwayat}</td>
        <td>${row.tanggal}</td>
        <td>${row.nama_bahan}</td>
        <td><span class="badge bg-info">${row.tipe}</span></td>
        <td>${sign}${formatGram(row.jumlah_gram)}</td>
        <td>${formatGram(row.stok_sebelum)}</td>
        <td>${formatGram(row.stok_sesudah)}</td>
        <td>${row.keterangan || '-'}</td>`;
      tbody.appendChild(tr);
    });
    renderPagination(document.getElementById('pagination'), page, res.data.total, perPage, (p) => { page = p; loadData(); });
  }

  document.getElementById('filterBahan').addEventListener('change', () => { page = 1; loadData(); });
  document.getElementById('filterTipe').addEventListener('change', () => { page = 1; loadData(); });

  loadBahanFilter().then(loadData);
})();
