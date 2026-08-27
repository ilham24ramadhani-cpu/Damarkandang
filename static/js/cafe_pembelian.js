(function () {
  let page = 1;
  const perPage = 10;

  function formatKg(kg) {
    const n = Number(kg) || 0;
    return (Number.isInteger(n) ? n : n.toFixed(3).replace(/\.?0+$/, '')) + ' kg';
  }

  function updatePreview() {
    const jumlah = parseNumberInput(document.getElementById('jumlah').value);
    const satuan = document.getElementById('satuan').value;
    const hargaKg = parseNumberInput(document.getElementById('hargaPerSatuan').value);
    const gram = satuan === 'kg' ? Math.round(jumlah * 1000) : Math.round(jumlah);
    const kg = gram / 1000;
    const total = Math.round(kg * hargaKg);
    document.getElementById('previewKg').textContent = formatKg(kg);
    document.getElementById('previewGram').textContent = formatGram(gram);
    document.getElementById('previewTotal').textContent = formatRupiah(total);
  }

  async function loadDropdowns() {
    const bahan = await CafeAPI.get('/bahan?active_only=1&per_page=100');
    const bahSel = document.getElementById('idBahan');
    bahSel.innerHTML = '<option value="">Pilih bahan...</option>';
    (bahan.data.items || []).forEach((b) => {
      const harga = b.harga_per_kg || b.harga_terakhir || 0;
      bahSel.innerHTML += `<option value="${b.id_bahan}" data-harga="${harga}">${b.nama_jenis || b.nama_bahan}</option>`;
    });
  }

  document.getElementById('idBahan').addEventListener('change', (e) => {
    const opt = e.target.selectedOptions[0];
    if (opt && opt.dataset.harga && opt.dataset.harga !== '0') {
      document.getElementById('hargaPerSatuan').value = opt.dataset.harga;
      updatePreview();
    }
  });

  async function loadTable() {
    const q = new URLSearchParams({ page, per_page: perPage });
    const res = await CafeAPI.get('/pembelian?' + q);
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';
    (res.data.items || []).forEach((row) => {
      const hargaKg = row.harga_per_kg || row.harga_per_satuan || 0;
      const kg = (row.jumlah_gram || 0) / 1000;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.id_pembelian}</td>
        <td>${row.tanggal}</td>
        <td>${row.nama_bahan}</td>
        <td>${formatKg(kg)} (${formatGram(row.jumlah_gram)})</td>
        <td>${formatRupiah(hargaKg)}/kg</td>
        <td>${formatRupiah(row.total_harga)}</td>`;
      tbody.appendChild(tr);
    });
    renderPagination(document.getElementById('pagination'), page, res.data.total, perPage, (p) => { page = p; loadTable(); });
  }

  ['jumlah', 'satuan', 'hargaPerSatuan'].forEach((id) => {
    document.getElementById(id).addEventListener('input', updatePreview);
    document.getElementById(id).addEventListener('change', updatePreview);
  });

  document.getElementById('tanggal').value = new Date().toISOString().slice(0, 10);

  document.getElementById('formPembelian').addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      tanggal: document.getElementById('tanggal').value,
      id_bahan: document.getElementById('idBahan').value,
      jumlah: parseNumberInput(document.getElementById('jumlah').value),
      satuan: document.getElementById('satuan').value,
      harga_per_kg: parseNumberInput(document.getElementById('hargaPerSatuan').value),
      catatan: document.getElementById('catatan').value.trim(),
    };
    try {
      await CafeAPI.post('/pembelian', payload);
      showToast('Pembelian berhasil disimpan');
      document.getElementById('formPembelian').reset();
      document.getElementById('tanggal').value = new Date().toISOString().slice(0, 10);
      updatePreview();
      loadTable();
      loadDropdowns();
    } catch (err) { showToast(err.message, 'danger'); }
  });

  loadDropdowns();
  loadTable();
  updatePreview();
})();
