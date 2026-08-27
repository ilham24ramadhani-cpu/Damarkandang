(function () {
  let products = [];
  let editId = new URLSearchParams(window.location.search).get('edit') || '';

  function formatNumber(value) {
    return Math.round(Number(value) || 0).toLocaleString('id-ID');
  }

  async function loadProducts() {
    const res = await CafeAPI.get('/menu?active_only=1&per_page=100');
    products = res.data.items || [];
  }

  async function loadPetugas(selectedId = '') {
    const select = document.getElementById('petugasPenjualan');
    try {
      const response = await fetch('/api/kasir/petugas', { credentials: 'include' });
      const json = await response.json();
      if (!response.ok) throw new Error(json.message || 'Gagal memuat petugas');
      const petugas = json.data || [];
      select.innerHTML = '<option value="">Pilih petugas</option>' + petugas.map((user) =>
        `<option value="${user.id}" ${String(user.id) === String(selectedId) ? 'selected' : ''}>${user.nama_lengkap} — ${user.role}</option>`
      ).join('');
      if (selectedId && !petugas.some((u) => String(u.id) === String(selectedId))) {
        select.insertAdjacentHTML('beforeend', `<option value="${selectedId}" selected>Petugas #${selectedId}</option>`);
      }
    } catch (err) {
      select.innerHTML = '<option value="">Petugas tidak tersedia</option>';
      showToast(err.message, 'danger');
    }
  }

  function productOptions(selected = '') {
    const opts = '<option value="">Pilih produk</option>' + products.map((product) =>
      `<option value="${product.id_menu}" ${product.id_menu === selected ? 'selected' : ''}>${product.nama_menu}</option>`
    ).join('');
    if (selected && !products.some((p) => p.id_menu === selected)) {
      return opts + `<option value="${selected}" selected>${selected}</option>`;
    }
    return opts;
  }

  function addSaleRow(selected = '', qty = 1) {
    const row = document.createElement('tr');
    row.className = 'sale-row';
    row.innerHTML = `
      <td><select class="form-select product-select" required>${productOptions(selected)}</select></td>
      <td class="product-category text-muted">-</td>
      <td><input class="form-control sale-price text-end" readonly value="0" /></td>
      <td><input type="number" class="form-control sale-qty text-end" min="1" step="1" value="${qty || 1}" required /></td>
      <td class="sale-subtotal text-end fw-semibold">Rp0</td>
      <td class="text-center"><button type="button" class="btn btn-outline-danger btn-sm btn-delete-row" title="Hapus"><i class="bi bi-x-lg"></i></button></td>`;
    document.getElementById('barisPenjualan').appendChild(row);
    refreshRow(row);
  }

  function refreshRow(row) {
    const product = products.find((item) => item.id_menu === row.querySelector('.product-select').value);
    const price = Number(product?.harga_jual || 0);
    const qty = Math.max(0, Number(row.querySelector('.sale-qty').value) || 0);
    row.querySelector('.product-category').textContent = product?.kategori || '-';
    row.querySelector('.sale-price').value = formatNumber(price);
    row.querySelector('.sale-subtotal').textContent = formatRupiah(price * qty);
    row.dataset.subtotal = String(price * qty);
    refreshTotal();
  }

  function refreshTotal() {
    const total = [...document.querySelectorAll('.sale-row')].reduce(
      (sum, row) => sum + (Number(row.dataset.subtotal) || 0), 0
    );
    document.getElementById('totalPenjualan').textContent = formatRupiah(total);
  }

  function setEditModeUi(id) {
    const title = document.querySelector('.page-header h1');
    const subtitle = document.querySelector('.page-header p');
    const btn = document.getElementById('btnBayar');
    if (title) title.textContent = 'Edit Penjualan';
    if (subtitle) subtitle.textContent = `Mengubah ${id} — stok dan pemasukan akan disesuaikan otomatis.`;
    if (btn) btn.innerHTML = '<i class="bi bi-check2-circle me-1"></i> Simpan Perubahan';
  }

  async function loadEditData(id) {
    const res = await CafeAPI.get('/kasir/transaksi/' + id);
    const data = res.data || {};
    document.getElementById('tanggalPenjualan').value = data.tanggal || new Date().toISOString().slice(0, 10);
    document.getElementById('catatanPenjualan').value = data.catatan || '';
    await loadPetugas((data.petugas && data.petugas.id) || '');
    document.getElementById('barisPenjualan').innerHTML = '';
    const items = data.items || [];
    if (items.length) {
      items.forEach((item) => addSaleRow(item.id_menu, item.qty));
    } else {
      addSaleRow();
    }
    setEditModeUi(id);
  }

  document.getElementById('btnTambahBaris').addEventListener('click', () => addSaleRow());
  document.getElementById('barisPenjualan').addEventListener('change', (event) => {
    const row = event.target.closest('.sale-row');
    if (row) refreshRow(row);
  });
  document.getElementById('barisPenjualan').addEventListener('input', (event) => {
    const row = event.target.closest('.sale-row');
    if (row && event.target.matches('.sale-qty')) refreshRow(row);
  });
  document.getElementById('barisPenjualan').addEventListener('click', (event) => {
    const button = event.target.closest('.btn-delete-row');
    if (!button) return;
    const rows = document.querySelectorAll('.sale-row');
    if (rows.length === 1) return showToast('Minimal satu baris penjualan diperlukan', 'danger');
    button.closest('.sale-row').remove();
    refreshTotal();
  });

  document.getElementById('btnBayar').addEventListener('click', async () => {
    const items = [...document.querySelectorAll('.sale-row')].map((row) => ({
      id_menu: row.querySelector('.product-select').value,
      qty: Number(row.querySelector('.sale-qty').value),
    }));
    if (items.some((item) => !item.id_menu || item.qty < 1)) {
      return showToast('Pilih produk dan isi jumlah terjual pada setiap baris', 'danger');
    }
    const petugasId = document.getElementById('petugasPenjualan').value;
    if (!petugasId) return showToast('Pilih petugas penginput', 'danger');
    const payload = {
      items,
      tanggal: document.getElementById('tanggalPenjualan').value,
      petugas_id: petugasId,
      catatan: document.getElementById('catatanPenjualan').value.trim(),
    };
    try {
      const res = editId
        ? await CafeAPI.put('/kasir/transaksi/' + editId, payload)
        : await CafeAPI.post('/kasir/transaksi', payload);
      showToast(editId
        ? 'Penjualan diperbarui — stok & pemasukan disesuaikan'
        : 'Penjualan tersimpan — pemasukan tercatat & stok berkurang');
      PemesananUI.renderStruk(res.data);
      if (editId) {
        setTimeout(() => { window.location.href = '/kelola/pemesanan'; }, 700);
      } else {
        document.getElementById('catatanPenjualan').value = '';
        document.getElementById('barisPenjualan').innerHTML = '';
        addSaleRow();
      }
    } catch (err) { showToast(err.message, 'danger'); }
  });

  document.getElementById('btnPrintStruk')?.addEventListener('click', () => PemesananUI.printStruk());

  Promise.all([loadProducts(), loadPetugas()]).then(async () => {
    if (editId) {
      try {
        await loadEditData(editId);
      } catch (err) {
        showToast(err.message, 'danger');
        addSaleRow();
      }
    } else {
      document.getElementById('tanggalPenjualan').value = new Date().toISOString().slice(0, 10);
      addSaleRow();
    }
  });
})();
