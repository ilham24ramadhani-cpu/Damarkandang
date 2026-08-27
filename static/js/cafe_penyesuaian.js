(function () {
  let bahanMap = {};

  async function loadBahan() {
    const res = await CafeAPI.get('/bahan?active_only=1&per_page=100');
    const sel = document.getElementById('idBahan');
    sel.innerHTML = '<option value="">Pilih bahan...</option>';
    bahanMap = {};
    (res.data.items || []).forEach((b) => {
      bahanMap[b.id_bahan] = b;
      sel.innerHTML += `<option value="${b.id_bahan}">${b.nama_bahan}</option>`;
    });
  }

  function updateSelisih() {
    const id = document.getElementById('idBahan').value;
    const b = bahanMap[id];
    const sistem = b ? b.stok_gram : 0;
    document.getElementById('stokSistem').value = formatGram(sistem);
    const fisik = parseInt(document.getElementById('stokFisik').value || 0, 10);
    const selisih = fisik - sistem;
    document.getElementById('selisih').value = (selisih >= 0 ? '+' : '') + selisih.toLocaleString('id-ID') + ' gram';
  }

  document.getElementById('idBahan').addEventListener('change', updateSelisih);
  document.getElementById('stokFisik').addEventListener('input', updateSelisih);

  document.getElementById('formPenyesuaian').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await CafeAPI.post('/penyesuaian-stok', {
        id_bahan: document.getElementById('idBahan').value,
        stok_fisik: parseInt(document.getElementById('stokFisik').value, 10),
        alasan: document.getElementById('alasan').value.trim(),
        catatan: document.getElementById('catatan').value.trim(),
      });
      showToast('Penyesuaian stok berhasil disimpan');
      await loadBahan();
      document.getElementById('formPenyesuaian').reset();
    } catch (err) { showToast(err.message, 'danger'); }
  });

  loadBahan();
})();
