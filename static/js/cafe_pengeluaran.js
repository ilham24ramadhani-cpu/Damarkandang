(function () {
  let page = 1;
  const perPage = 10;
  const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('modalForm'));

  async function loadData() {
    const search = document.getElementById('searchInput').value.trim();
    const q = new URLSearchParams({ page, per_page: perPage, search });
    const res = await CafeAPI.get('/pengeluaran?' + q);
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';
    (res.data.items || []).forEach((row) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.id_pengeluaran}</td>
        <td>${row.tanggal}</td>
        <td>${row.kategori}</td>
        <td>${row.sumber || '-'}</td>
        <td>${formatRupiah(row.nominal)}</td>
        <td>${row.keterangan || '-'}</td>`;
      tbody.appendChild(tr);
    });
    renderPagination(document.getElementById('pagination'), page, res.data.total, perPage, (p) => { page = p; loadData(); });
  }

  document.getElementById('searchInput').addEventListener('input', () => { page = 1; loadData(); });
  document.getElementById('tanggal').value = new Date().toISOString().slice(0, 10);

  document.getElementById('formData').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await CafeAPI.post('/pengeluaran', {
        tanggal: document.getElementById('tanggal').value,
        kategori: document.getElementById('kategori').value,
        nominal: parseNumberInput(document.getElementById('nominal').value),
        keterangan: document.getElementById('keterangan').value.trim(),
      });
      showToast('Pengeluaran berhasil disimpan');
      modal.hide();
      loadData();
    } catch (err) { showToast(err.message, 'danger'); }
  });

  loadData();
})();
