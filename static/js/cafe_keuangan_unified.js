(function () {
  const pengeluaranBody = document.getElementById('pengeluaranBody');
  const pemasukanBody = document.getElementById('pemasukanBody');
  const pgTanggal = document.getElementById('pgTanggal');
  const pgJenis = document.getElementById('pgJenis');
  const pgNominal = document.getElementById('pgNominal');
  const pgKeterangan = document.getElementById('pgKeterangan');
  const pmTanggal = document.getElementById('pmTanggal');
  const pmJenis = document.getElementById('pmJenis');
  const pmNominal = document.getElementById('pmNominal');
  const pmKeterangan = document.getElementById('pmKeterangan');
  const modalPg = () => bootstrap.Modal.getOrCreateInstance(document.getElementById('modalPengeluaran'));
  const modalPm = () => bootstrap.Modal.getOrCreateInstance(document.getElementById('modalPemasukan'));
  const today = () => new Date().toISOString().slice(0, 10);
  const AUTO_SUMBER = ['Pembelian Bahan', 'Bahan Masuk', 'Penjualan', 'Pemesanan', 'Kasir'];

  function readJenis(row) {
    return row.jenis || row.kategori || '-';
  }

  function badgeOtomatis(sumber) {
    return AUTO_SUMBER.includes(sumber)
      ? ' <span class="badge bg-info text-dark">Otomatis</span>' : '';
  }

  async function loadJenisOptions() {
    const [pg, pm] = await Promise.all([
      CafeAPI.get('/jenis-pengeluaran?manual_only=1'),
      CafeAPI.get('/jenis-pemasukan?manual_only=1'),
    ]);
    pgJenis.innerHTML = (pg.data.items || []).map((j) =>
      `<option value="${j.nama_jenis}">${j.nama_jenis}</option>`).join('')
      || '<option value="">Belum ada jenis manual — tambah di Kelola Data</option>';
    pmJenis.innerHTML = (pm.data.items || []).map((j) =>
      `<option value="${j.nama_jenis}">${j.nama_jenis}</option>`).join('')
      || '<option value="">Belum ada jenis manual — tambah di Kelola Data</option>';
  }

  async function loadPengeluaran() {
    const res = await CafeAPI.get('/pengeluaran?per_page=100');
    const items = res.data.items || [];
    pengeluaranBody.innerHTML = items.length
      ? items.map((r) => `
      <tr><td>${r.tanggal}</td><td>${readJenis(r)}</td><td>${r.sumber || '-'}${badgeOtomatis(r.sumber)}</td>
      <td>${formatRupiah(r.nominal)}</td><td>${r.keterangan || '-'}</td></tr>`).join('')
      : '<tr><td colspan="5" class="text-muted text-center">Belum ada pengeluaran</td></tr>';
  }

  async function loadPemasukan() {
    const res = await CafeAPI.get('/pemasukan?per_page=100');
    const items = res.data.items || [];
    pemasukanBody.innerHTML = items.length
      ? items.map((r) => `
      <tr><td>${r.tanggal}</td><td>${readJenis(r)}</td><td>${r.sumber || '-'}${badgeOtomatis(r.sumber)}</td>
      <td>${r.id_referensi || '-'}</td><td>${formatRupiah(r.nominal)}</td><td>${r.keterangan || '-'}</td></tr>`).join('')
      : '<tr><td colspan="6" class="text-muted text-center">Belum ada pemasukan</td></tr>';
  }

  document.getElementById('btnTambahPengeluaran').addEventListener('click', () => {
    pgTanggal.value = today();
    loadJenisOptions().catch((err) => showToast(err.message, 'danger'));
  });

  document.getElementById('btnTambahPemasukan').addEventListener('click', () => {
    pmTanggal.value = today();
    loadJenisOptions().catch((err) => showToast(err.message, 'danger'));
  });

  document.querySelector('[data-bs-target="#tabPemasukan"]')?.addEventListener('shown.bs.tab', () => {
    loadPemasukan().catch((err) => showToast(err.message, 'danger'));
  });

  document.getElementById('formPengeluaran').addEventListener('submit', async (e) => {
    e.preventDefault();
    const nominal = parseNumberInput(pgNominal.value);
    if (!pgTanggal.value || !pgJenis.value || nominal <= 0) {
      showToast('Lengkapi tanggal, jenis, dan nominal pengeluaran', 'danger');
      return;
    }
    try {
      await CafeAPI.post('/pengeluaran', {
        tanggal: pgTanggal.value,
        jenis: pgJenis.value,
        nominal,
        keterangan: pgKeterangan.value.trim(),
      });
      showToast('Pengeluaran disimpan');
      modalPg().hide();
      await loadPengeluaran();
    } catch (err) { showToast(err.message, 'danger'); }
  });

  document.getElementById('formPemasukan').addEventListener('submit', async (e) => {
    e.preventDefault();
    const nominal = parseNumberInput(pmNominal.value);
    if (!pmTanggal.value || !pmJenis.value || nominal <= 0) {
      showToast('Lengkapi tanggal, jenis, dan nominal pemasukan', 'danger');
      return;
    }
    try {
      await CafeAPI.post('/pemasukan', {
        tanggal: pmTanggal.value,
        jenis: pmJenis.value,
        nominal,
        keterangan: pmKeterangan.value.trim(),
      });
      showToast('Pemasukan disimpan');
      modalPm().hide();
      await loadPemasukan();
    } catch (err) { showToast(err.message, 'danger'); }
  });

  Promise.all([loadJenisOptions(), loadPengeluaran(), loadPemasukan()]).catch((err) => {
    showToast(err.message || 'Gagal memuat data keuangan', 'danger');
  });
})();
