(function () {
  let bmItems = [];
  let bmDetailData = null;
  let opsi = { produk: [], petugas: [], bahan: [], jenis_pemasukan: [], jenis_pengeluaran: [], sumber_pemasukan: [], sumber_pengeluaran: [] };
  const store = {
    penjualan: { items: [], rekap: [], heads: ['ID Penjualan', 'Petugas', 'Tanggal', 'Produk Terjual', 'Jumlah', 'Total Pemasukan', 'Catatan'] },
    pembelian: { items: [], heads: ['ID', 'Tanggal', 'Bahan', 'Jumlah', 'Satuan', 'Gram', 'Harga/Kg', 'Total', 'Catatan'] },
    keuangan: { items: [], rekap: [], heads: ['ID', 'Tanggal', 'Arus', 'Jenis', 'Sumber', 'Nominal', 'Referensi', 'Keterangan'] },
    stok: { items: [], snapshot: [], heads: ['ID', 'Tanggal', 'Bahan', 'Tipe', 'Jumlah (gram)', 'Stok Sebelum', 'Stok Sesudah', 'Referensi', 'Keterangan'] },
  };

  const BM_HEADERS = [
    'No', 'ID Bahan', 'Jenis Bahan', 'Jumlah (kg)', 'Harga/Kg (Rp)',
    'Total Pengeluaran (Rp)', 'Tanggal Masuk', 'Jumlah Transaksi',
  ];

  function fmtRp(n) {
    return 'Rp' + Math.round(Number(n) || 0).toLocaleString('id-ID');
  }

  function fmtKgFromGram(gram) {
    const kg = (Number(gram) || 0) / 1000;
    return (Number.isInteger(kg) ? kg : kg.toFixed(3).replace(/\.?0+$/, '')).toLocaleString('id-ID');
  }

  function fmtDateId(iso) {
    if (!iso) return '-';
    try {
      return new Date(iso + 'T00:00:00').toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' });
    } catch {
      return iso;
    }
  }

  function val(id) {
    return (document.getElementById(id)?.value || '').trim();
  }

  function buildQuery(params) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) q.set(k, v); });
    return q.toString() ? '?' + q.toString() : '';
  }

  function periodParams(prefix) {
    return {
      bulan: val(prefix + 'Bulan'),
      tanggal_dari: val(prefix + 'Dari'),
      tanggal_sampai: val(prefix + 'Sampai'),
    };
  }

  function setMonthDefault(prefix) {
    const el = document.getElementById(prefix + 'Bulan');
    if (el && !el.value) el.value = new Date().toISOString().slice(0, 7);
  }

  function resetPeriod(prefix) {
    const el = document.getElementById(prefix + 'Bulan');
    if (el) el.value = new Date().toISOString().slice(0, 7);
    const dari = document.getElementById(prefix + 'Dari');
    const sampai = document.getElementById(prefix + 'Sampai');
    if (dari) dari.value = '';
    if (sampai) sampai.value = '';
  }

  function fillSelect(select, items, valueFn, labelFn, placeholder) {
    if (!select) return;
    const current = select.value;
    const opts = (items || []).map((item) => {
      const value = typeof valueFn === 'function' ? valueFn(item) : item[valueFn];
      const label = typeof labelFn === 'function' ? labelFn(item) : item[labelFn];
      return `<option value="${value}">${label}</option>`;
    }).join('');
    select.innerHTML = `<option value="">${placeholder}</option>` + opts;
    if (current && [...select.options].some((o) => o.value === current)) select.value = current;
  }

  function renderCards(id, cards) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = cards.map((x) => `<div class="col-md-4 col-lg"><div class="card cafe-card h-100"><div class="card-body py-3">
      <div class="text-muted small">${x.t}</div><div class="fw-bold text-${x.c || 'dark'}">${x.v}</div>
      ${x.s ? `<div class="small text-muted">${x.s}</div>` : ''}</div></div></div>`).join('');
  }

  function emptyRow(colspan, text) {
    return `<tr><td colspan="${colspan}" class="text-muted text-center py-4">${text}</td></tr>`;
  }

  function downloadCsv(filename, heads, rows) {
    const csv = [heads, ...rows].map((row) => row.map((cell) => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    showToast('Excel (CSV) berhasil diunduh');
  }

  function downloadPdf(title, caption, heads, rows, extraTables) {
    if (!window.jspdf) return showToast('Library PDF belum dimuat', 'danger');
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ orientation: 'landscape' });
    doc.setFontSize(14);
    doc.text(title, 14, 15);
    doc.setFontSize(9);
    doc.text(caption || `Dicetak: ${new Date().toLocaleString('id-ID')}`, 14, 22);
    doc.autoTable({
      head: [heads],
      body: rows,
      startY: 28,
      styles: { fontSize: 8 },
      headStyles: { fillColor: [13, 110, 96] },
    });
    (extraTables || []).forEach((tbl) => {
      doc.autoTable({
        head: [tbl.heads],
        body: tbl.rows,
        startY: (doc.lastAutoTable?.finalY || 28) + 10,
        styles: { fontSize: 8 },
        headStyles: { fillColor: [13, 110, 96] },
      });
    });
    doc.save(title.toLowerCase().replace(/\s+/g, '-') + '-' + new Date().toISOString().slice(0, 10) + '.pdf');
    showToast('PDF berhasil diunduh');
  }

  function periodCaption(prefix, extra) {
    const p = periodParams(prefix);
    const bits = extra ? extra.slice() : [];
    if (p.tanggal_dari || p.tanggal_sampai) bits.push(`Tanggal: ${p.tanggal_dari || '...'} s/d ${p.tanggal_sampai || '...'}`);
    else if (p.bulan) bits.push('Bulan: ' + p.bulan);
    else bits.push('Periode: semua');
    return bits.join(' · ');
  }

  /* --- Bahan masuk (existing) --- */
  function getBmFilters() {
    const periode = document.getElementById('bmPeriode').value;
    let nilai = '';
    if (periode === 'bulanan') nilai = document.getElementById('bmNilaiBulan').value;
    else if (periode === 'mingguan') nilai = document.getElementById('bmNilaiMinggu').value;
    else if (periode === 'tahunan') nilai = document.getElementById('bmNilaiTahun').value;
    return { periode, nilai, id_jenis: document.getElementById('bmJenis').value };
  }

  function toggleBmNilaiInputs() {
    const periode = document.getElementById('bmPeriode').value;
    document.querySelectorAll('.bm-nilai').forEach((el) => el.classList.add('d-none'));
    if (periode === 'bulanan') document.getElementById('bmNilaiBulan').classList.remove('d-none');
    else if (periode === 'mingguan') document.getElementById('bmNilaiMinggu').classList.remove('d-none');
    else if (periode === 'tahunan') document.getElementById('bmNilaiTahun').classList.remove('d-none');
  }

  async function loadJenisOptions() {
    const res = await CafeAPI.get('/jenis-bahan?per_page=200');
    fillSelect(document.getElementById('bmJenis'), res.data.items || [], 'id_jenis', 'nama_jenis', 'Semua jenis bahan');
  }

  function renderBmSummary(ringkasan) {
    const r = ringkasan || {};
    renderCards('bmSummaryCards', [
      { t: 'Rata-rata Harga/Kg', v: fmtRp(r.rata_rata_harga_kg), s: `${r.jumlah_transaksi || 0} transaksi`, c: 'primary' },
      { t: 'Harga Maksimum/Kg', v: fmtRp(r.harga_maksimum_kg), s: r.bahan_harga_maksimum || '-', c: 'warning' },
      { t: 'Total Pengeluaran', v: fmtRp(r.total_pengeluaran), s: `${r.jumlah_bahan || 0} ID bahan`, c: 'danger' },
      { t: 'Total Bahan Masuk', v: `${fmtKgFromGram(r.total_gram)} kg`, s: `${(r.total_gram || 0).toLocaleString('id-ID')} gram`, c: 'success' },
    ]);
  }

  function bmRowCells(r, idx) {
    return [idx + 1, r.id_bahan, r.nama_jenis, r.jumlah_kg, r.harga_per_kg, r.total_pengeluaran, r.tanggal_masuk, r.jumlah_transaksi];
  }

  function renderBmTable(items, total) {
    bmItems = items || [];
    const tbody = document.getElementById('bmTableBody');
    tbody.innerHTML = bmItems.length
      ? bmItems.map((r, i) => `
        <tr>
          <td>${i + 1}</td>
          <td><code>${r.id_bahan}</code></td>
          <td><strong>${r.nama_jenis}</strong></td>
          <td>${fmtKgFromGram(r.jumlah_gram)}</td>
          <td>${fmtRp(r.harga_per_kg)}</td>
          <td>${fmtRp(r.total_pengeluaran)}</td>
          <td>${fmtDateId(r.tanggal_masuk)}</td>
          <td><span class="badge bg-secondary">${r.jumlah_transaksi}</span></td>
          <td><button class="btn btn-sm btn-primary btn-bm-detail" data-id="${r.id_bahan}"><i class="bi bi-eye"></i> Lihat Detail</button></td>
        </tr>`).join('')
      : emptyRow(9, 'Tidak ada data bahan masuk untuk filter ini');
    document.getElementById('bmInfo').textContent = `${bmItems.length} dari ${total || 0} ID bahan`;
  }

  async function loadBahanMasuk() {
    const f = getBmFilters();
    const res = await CafeAPI.get('/laporan/bahan-masuk' + buildQuery({ ...f, per_page: 500 }), { key: 'lap-bm' });
    renderBmSummary(res.data.ringkasan);
    renderBmTable(res.data.items || [], res.data.total);
  }

  async function showBmDetail(idBahan) {
    const f = getBmFilters();
    const res = await CafeAPI.get(`/laporan/bahan-masuk/${idBahan}/detail` + buildQuery({ periode: f.periode, nilai: f.nilai }));
    bmDetailData = res.data;
    const b = res.data.bahan;
    const ring = res.data.ringkasan;
    document.getElementById('bmDetailTitle').textContent = `Laporan ${b.id_bahan} — ${b.nama_jenis}`;
    document.getElementById('bmDetailSubtitle').textContent =
      `Periode: ${f.periode}${f.nilai ? ' · ' + f.nilai : ''} · Stok saat ini: ${formatGram(b.stok_gram)}`;
    document.getElementById('bmDetailSummary').innerHTML = [
      { t: 'Total Masuk', v: `${ring.total_kg} kg` },
      { t: 'Total Pengeluaran', v: fmtRp(ring.total_pengeluaran) },
      { t: 'Jumlah Transaksi', v: ring.jumlah_transaksi },
      { t: 'Harga/Kg Saat Ini', v: fmtRp(b.harga_per_kg) },
    ].map((x) => `<div class="col-md-3"><div class="border rounded p-2"><div class="small text-muted">${x.t}</div><strong>${x.v}</strong></div></div>`).join('');
    document.getElementById('bmDetailBody').innerHTML = (res.data.items || []).map((row) => `
      <tr>
        <td>${fmtDateId(row.tanggal)}</td>
        <td><span class="badge ${row.tipe === 'MASUK' ? 'bg-success' : 'bg-info text-dark'}">${row.tipe}</span></td>
        <td>${row.jumlah_kg}</td>
        <td>${fmtRp(row.harga_per_kg)}</td>
        <td>${fmtRp(row.total_pengeluaran)}</td>
        <td>${formatGram(row.stok_sebelum)}</td>
        <td>${formatGram(row.stok_sesudah)}</td>
        <td>${row.keterangan || '-'}</td>
      </tr>`).join('') || emptyRow(8, 'Tidak ada riwayat');
    bootstrap.Modal.getOrCreateInstance(document.getElementById('modalBmDetail')).show();
  }

  function exportBmCsv() {
    downloadCsv(`laporan-bahan-masuk-${new Date().toISOString().slice(0, 10)}.csv`, BM_HEADERS, bmItems.map((r, i) => bmRowCells(r, i)));
  }

  function exportBmPdfAll() {
    const f = getBmFilters();
    downloadPdf(
      'Laporan Bahan Masuk — Damarkandang',
      `Periode: ${f.periode}${f.nilai ? ' · ' + f.nilai : ''} · Jenis: ${document.getElementById('bmJenis').selectedOptions[0]?.text || 'Semua'}`,
      BM_HEADERS,
      bmItems.map((r, i) => bmRowCells(r, i))
    );
  }

  function exportBmDetailPdf() {
    if (!bmDetailData || !window.jspdf) return;
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ orientation: 'landscape' });
    const b = bmDetailData.bahan;
    doc.setFontSize(14);
    doc.text(`Detail Laporan ${b.id_bahan} — ${b.nama_jenis}`, 14, 15);
    doc.setFontSize(9);
    doc.text(`Total pengeluaran: ${fmtRp(bmDetailData.ringkasan.total_pengeluaran)} · Total masuk: ${bmDetailData.ringkasan.total_kg} kg`, 14, 22);
    doc.autoTable({
      head: [['Tanggal', 'Tipe', 'Kg', 'Harga/Kg', 'Total', 'Stok Sebelum', 'Stok Sesudah', 'Keterangan']],
      body: (bmDetailData.items || []).map((r) => [
        r.tanggal, r.tipe, r.jumlah_kg, r.harga_per_kg, r.total_pengeluaran, r.stok_sebelum, r.stok_sesudah, r.keterangan || '',
      ]),
      startY: 28,
      styles: { fontSize: 8 },
      headStyles: { fillColor: [13, 110, 96] },
    });
    doc.save(`detail-${b.id_bahan}-${new Date().toISOString().slice(0, 10)}.pdf`);
    showToast('PDF detail berhasil diunduh');
  }

  /* --- Opsi filter --- */
  function bahanLabel(b) {
    return `${b.id_bahan} — ${b.nama_jenis || b.nama_bahan || '-'}`;
  }

  function refreshKeuanganJenisSumber() {
    const arus = val('keuArus');
    const jenis = arus === 'pengeluaran' ? opsi.jenis_pengeluaran : arus === 'pemasukan' ? opsi.jenis_pemasukan
      : [...new Set([...(opsi.jenis_pemasukan || []), ...(opsi.jenis_pengeluaran || [])])];
    const sumber = arus === 'pengeluaran' ? opsi.sumber_pengeluaran : arus === 'pemasukan' ? opsi.sumber_pemasukan
      : [...new Set([...(opsi.sumber_pemasukan || []), ...(opsi.sumber_pengeluaran || [])])];
    fillSelect(document.getElementById('keuJenis'), jenis.map((n) => ({ n })), 'n', 'n', 'Semua jenis');
    fillSelect(document.getElementById('keuSumber'), sumber.map((n) => ({ n })), 'n', 'n', 'Semua sumber');
  }

  async function loadOpsi() {
    const res = await CafeAPI.get('/laporan/opsi', { key: 'lap-opsi' });
    opsi = res.data || opsi;
    fillSelect(document.getElementById('pjProduk'), opsi.produk, 'id_menu', (p) => `${p.nama_menu}${p.kategori ? ' · ' + p.kategori : ''}`, 'Semua produk');
    fillSelect(document.getElementById('pjPetugas'), opsi.petugas, 'id', (u) => `${u.nama_lengkap}${u.role ? ' — ' + u.role : ''}`, 'Semua petugas');
    fillSelect(document.getElementById('pbBahan'), opsi.bahan, 'id_bahan', bahanLabel, 'Semua bahan');
    fillSelect(document.getElementById('stBahan'), opsi.bahan, 'id_bahan', bahanLabel, 'Semua bahan');
    refreshKeuanganJenisSumber();
  }

  /* --- Penjualan --- */
  function pjSelectedMenu() { return val('pjProduk'); }

  function pjLines(r) {
    const menuId = pjSelectedMenu();
    const items = r.items || [];
    return menuId ? items.filter((i) => i.id_menu === menuId) : items;
  }

  function pjRow(r) {
    const lines = pjLines(r);
    const produk = lines.map((i) => `${i.nama_menu} x${i.qty || i.jumlah || 0}`).join(', ') || '-';
    const qty = lines.reduce((s, i) => s + (Number(i.qty || i.jumlah) || 0), 0);
    const total = pjSelectedMenu()
      ? lines.reduce((s, i) => s + (Number(i.subtotal) || (Number(i.harga_jual) || 0) * (Number(i.qty || i.jumlah) || 0)), 0)
      : r.total;
    return [
      r.id_pemesanan || r.id_transaksi,
      (r.petugas && r.petugas.nama_lengkap) || r.nama_pelanggan || '-',
      fmtDateId(r.tanggal),
      produk,
      qty,
      fmtRp(total),
      r.catatan || '-',
    ];
  }

  async function loadPenjualan() {
    const q = buildQuery({ ...periodParams('pj'), id_menu: val('pjProduk'), petugas_id: val('pjPetugas'), per_page: 500 });
    const res = await CafeAPI.get('/laporan/pemesanan' + q, { key: 'lap-pj' });
    const ring = res.data.ringkasan_penjualan || {};
    store.penjualan.items = res.data.items || [];
    store.penjualan.rekap = ring.rekap_produk || [];
    renderCards('pjSummary', [
      { t: 'Jumlah Penjualan', v: ring.jumlah_transaksi || 0, c: 'primary' },
      { t: 'Total Pemasukan', v: fmtRp(ring.total_pemasukan), c: 'success' },
      { t: 'Produk Terjual', v: `${(ring.jumlah_qty || 0).toLocaleString('id-ID')} pcs`, c: 'info' },
      { t: 'Jenis Produk', v: ring.jumlah_jenis_produk || 0, c: 'secondary' },
      { t: 'Petugas', v: ring.jumlah_petugas || 0, c: 'warning' },
    ]);
    const rekap = store.penjualan.rekap;
    const totalQty = rekap.reduce((s, x) => s + (Number(x.qty) || 0), 0);
    const totalRp = rekap.reduce((s, x) => s + (Number(x.total) || 0), 0);
    document.getElementById('pjRekapBody').innerHTML = rekap.length
      ? rekap.map((r, i) => `<tr><td>${i + 1}</td><td><strong>${r.nama_menu || '-'}</strong></td><td class="text-end">${(r.qty || 0).toLocaleString('id-ID')}</td><td class="text-end">${fmtRp(r.total)}</td></tr>`).join('')
        + `<tr class="table-light fw-semibold"><td colspan="2">Total</td><td class="text-end">${totalQty.toLocaleString('id-ID')}</td><td class="text-end">${fmtRp(totalRp)}</td></tr>`
      : emptyRow(4, 'Belum ada produk terjual pada filter ini');
    document.getElementById('pjRekapInfo').textContent = `${rekap.length} jenis produk`;
    document.getElementById('pjBody').innerHTML = store.penjualan.items.length
      ? store.penjualan.items.map((r) => {
        const cells = pjRow(r);
        return `<tr>${cells.map((c, i) => `<td class="${i === 4 || i === 5 ? 'text-end' : ''}">${c}</td>`).join('')}</tr>`;
      }).join('')
      : emptyRow(7, 'Tidak ada data penjualan');
    document.getElementById('pjInfo').textContent = `${store.penjualan.items.length} baris — Penjualan`;
  }

  /* --- Pembelian --- */
  function pbRow(r) {
    return [
      r.id_pembelian, fmtDateId(r.tanggal), r.nama_bahan || r.nama_jenis || '-',
      r.jumlah, r.satuan || 'kg', r.jumlah_gram || 0, fmtRp(r.harga_per_kg || r.harga_per_satuan),
      fmtRp(r.total_harga), r.catatan || '-',
    ];
  }

  async function loadPembelian() {
    const q = buildQuery({ ...periodParams('pb'), id_bahan: val('pbBahan'), per_page: 500 });
    const res = await CafeAPI.get('/laporan/pembelian' + q, { key: 'lap-pb' });
    const ring = res.data.ringkasan_pembelian || {};
    store.pembelian.items = res.data.items || [];
    renderCards('pbSummary', [
      { t: 'Jumlah Transaksi', v: ring.jumlah_transaksi || 0, c: 'primary' },
      { t: 'Jenis Bahan', v: ring.jumlah_bahan || 0, c: 'secondary' },
      { t: 'Total Masuk', v: `${fmtKgFromGram(ring.total_gram)} kg`, c: 'info' },
      { t: 'Total Pengeluaran', v: fmtRp(ring.total_harga), c: 'danger' },
    ]);
    document.getElementById('pbBody').innerHTML = store.pembelian.items.length
      ? store.pembelian.items.map((r) => {
        const cells = pbRow(r);
        return `<tr>${cells.map((c, i) => `<td class="${[5, 6, 7].includes(i) ? 'text-end' : ''}">${c}</td>`).join('')}</tr>`;
      }).join('')
      : emptyRow(9, 'Tidak ada data pembelian');
    document.getElementById('pbInfo').textContent = `${store.pembelian.items.length} baris — Pembelian`;
  }

  /* --- Keuangan --- */
  function keuRow(r) {
    return [
      r.id_dokumen || r.id_pemasukan || r.id_pengeluaran,
      fmtDateId(r.tanggal),
      r.arus || '-',
      r.jenis || r.kategori || '-',
      r.sumber || '-',
      fmtRp(r.nominal),
      r.id_referensi || '-',
      r.keterangan || '-',
    ];
  }

  async function loadKeuangan() {
    const q = buildQuery({
      ...periodParams('keu'),
      arus: val('keuArus') || 'semua',
      jenis_keuangan: val('keuJenis'),
      sumber: val('keuSumber'),
      per_page: 500,
    });
    const res = await CafeAPI.get('/laporan/keuangan' + q, { key: 'lap-keu' });
    const ring = res.data.ringkasan_keuangan || {};
    store.keuangan.items = res.data.items || [];
    store.keuangan.rekap = ring.rekap_jenis || [];
    renderCards('keuSummary', [
      { t: 'Pemasukan', v: fmtRp(ring.total_pemasukan), s: `${ring.jumlah_pemasukan || 0} transaksi`, c: 'success' },
      { t: 'Pengeluaran', v: fmtRp(ring.total_pengeluaran), s: `${ring.jumlah_pengeluaran || 0} transaksi`, c: 'danger' },
      { t: 'Selisih', v: fmtRp(ring.selisih), c: (ring.selisih || 0) >= 0 ? 'primary' : 'warning' },
    ]);
    document.getElementById('keuRekapBody').innerHTML = store.keuangan.rekap.length
      ? store.keuangan.rekap.map((r) => `<tr>
          <td><span class="badge ${r.arus === 'Pemasukan' ? 'bg-success' : 'bg-danger'}">${r.arus}</span></td>
          <td>${r.jenis}</td><td class="text-end">${r.jumlah}</td><td class="text-end">${fmtRp(r.total)}</td>
        </tr>`).join('')
      : emptyRow(4, 'Tidak ada rekap jenis');
    document.getElementById('keuBody').innerHTML = store.keuangan.items.length
      ? store.keuangan.items.map((r) => {
        const cells = keuRow(r);
        const badge = r.arus === 'Pemasukan' ? 'bg-success' : 'bg-danger';
        return `<tr>
          <td>${cells[0]}</td><td>${cells[1]}</td>
          <td><span class="badge ${badge}">${cells[2]}</span></td>
          <td>${cells[3]}</td><td>${cells[4]}</td>
          <td class="text-end">${cells[5]}</td><td>${cells[6]}</td><td>${cells[7]}</td>
        </tr>`;
      }).join('')
      : emptyRow(8, 'Tidak ada data keuangan');
    document.getElementById('keuInfo').textContent = `${store.keuangan.items.length} baris — Keuangan`;
  }

  /* --- Stok --- */
  function stRow(r) {
    return [
      r.id_riwayat, fmtDateId(r.tanggal), r.nama_bahan || r.id_bahan || '-', r.tipe || '-',
      r.jumlah_gram, r.stok_sebelum, r.stok_sesudah, r.id_referensi || '-', r.keterangan || '-',
    ];
  }

  function tipeBadge(tipe) {
    const t = (tipe || '').toUpperCase();
    if (t === 'MASUK' || t === 'PEMBELIAN') return 'bg-success';
    if (t === 'PEMAKAIAN') return 'bg-danger';
    if (t === 'PENYESUAIAN') return 'bg-warning text-dark';
    return 'bg-secondary';
  }

  async function loadStok() {
    const q = buildQuery({ ...periodParams('st'), id_bahan: val('stBahan'), tipe: val('stTipe'), per_page: 500 });
    const res = await CafeAPI.get('/laporan/stok' + q, { key: 'lap-stok' });
    const snap = res.data.ringkasan_stok || {};
    const hist = res.data.ringkasan_riwayat || {};
    store.stok.items = res.data.items || [];
    store.stok.snapshot = snap.snapshot || [];
    renderCards('stSummary', [
      { t: 'Jenis Bahan', v: snap.jumlah_jenis || 0, c: 'primary' },
      { t: 'Stok Normal', v: snap.stok_normal || 0, c: 'success' },
      { t: 'Menipis / Habis', v: `${snap.stok_menipis || 0} / ${snap.stok_habis || 0}`, c: 'warning' },
      { t: 'Total Stok', v: `${fmtKgFromGram(snap.total_gram)} kg`, c: 'info' },
      { t: 'Riwayat (filter)', v: hist.jumlah_transaksi || 0, s: `Masuk ${fmtKgFromGram(hist.total_masuk_gram)} kg · Pakai ${fmtKgFromGram(hist.total_keluar_gram)} kg`, c: 'secondary' },
    ]);
    document.getElementById('stSnapshotBody').innerHTML = store.stok.snapshot.length
      ? store.stok.snapshot.map((r) => `<tr>
          <td><strong>${r.nama_jenis || '-'}</strong></td>
          <td class="text-end">${formatGram(r.stok_gram)}</td>
          <td class="text-end">${fmtKgFromGram(r.stok_gram)}</td>
          <td><span class="badge ${stokBadgeClass(r.stok_status)}">${r.stok_status_label || r.stok_status}</span></td>
        </tr>`).join('')
      : emptyRow(4, 'Belum ada stok bahan');
    document.getElementById('stBody').innerHTML = store.stok.items.length
      ? store.stok.items.map((r) => {
        const cells = stRow(r);
        return `<tr>
          <td>${cells[0]}</td><td>${cells[1]}</td><td>${cells[2]}</td>
          <td><span class="badge ${tipeBadge(r.tipe)}">${r.tipe}</span></td>
          <td class="text-end">${cells[4]}</td><td class="text-end">${cells[5]}</td>
          <td class="text-end">${cells[6]}</td><td>${cells[7]}</td><td>${cells[8]}</td>
        </tr>`;
      }).join('')
      : emptyRow(9, 'Tidak ada riwayat stok pada filter ini');
    document.getElementById('stInfo').textContent = `${store.stok.items.length} baris riwayat`;
  }

  /* --- Bind --- */
  const now = new Date();
  document.getElementById('bmNilaiBulan').value = now.toISOString().slice(0, 7);
  document.getElementById('bmNilaiTahun').value = now.getFullYear();
  ['pj', 'pb', 'keu', 'st'].forEach(setMonthDefault);

  document.getElementById('bmPeriode').addEventListener('change', toggleBmNilaiInputs);
  document.getElementById('btnBmLoad').addEventListener('click', () => loadBahanMasuk().catch((e) => showToast(e.message, 'danger')));
  document.getElementById('btnBmReset').addEventListener('click', () => {
    document.getElementById('bmPeriode').value = 'bulanan';
    document.getElementById('bmNilaiBulan').value = now.toISOString().slice(0, 7);
    document.getElementById('bmJenis').value = '';
    toggleBmNilaiInputs();
    loadBahanMasuk().catch((e) => showToast(e.message, 'danger'));
  });
  document.getElementById('btnBmExportExcel').addEventListener('click', (e) => { e.preventDefault(); exportBmCsv(); });
  document.getElementById('btnBmExportPdf').addEventListener('click', (e) => { e.preventDefault(); exportBmPdfAll(); });
  document.getElementById('btnBmDetailPdf').addEventListener('click', exportBmDetailPdf);
  document.getElementById('bmTableBody').addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-bm-detail');
    if (btn) showBmDetail(btn.dataset.id).catch((err) => showToast(err.message, 'danger'));
  });

  document.getElementById('btnPjLoad').addEventListener('click', () => loadPenjualan().catch((e) => showToast(e.message, 'danger')));
  document.getElementById('btnPjReset').addEventListener('click', () => {
    document.getElementById('pjProduk').value = '';
    document.getElementById('pjPetugas').value = '';
    resetPeriod('pj');
    loadPenjualan().catch((e) => showToast(e.message, 'danger'));
  });
  document.getElementById('btnPjExcel').addEventListener('click', () => {
    const extra = store.penjualan.rekap.map((r, i) => [i + 1, r.nama_menu, r.qty, r.total]);
    downloadCsv(`laporan-penjualan-${now.toISOString().slice(0, 10)}.csv`, store.penjualan.heads, [
      ...store.penjualan.items.map(pjRow), [], ['Rekap Produk Terjual'], ['No', 'Produk', 'Jumlah', 'Total'], ...extra,
    ]);
  });
  document.getElementById('btnPjPdf').addEventListener('click', () => downloadPdf(
    'Laporan Penjualan — Damarkandang', periodCaption('pj', [
      document.getElementById('pjProduk').selectedOptions[0]?.text,
      document.getElementById('pjPetugas').selectedOptions[0]?.text,
    ]),
    store.penjualan.heads, store.penjualan.items.map(pjRow),
    store.penjualan.rekap.length ? [{ heads: ['No', 'Produk', 'Jumlah', 'Total'], rows: store.penjualan.rekap.map((r, i) => [i + 1, r.nama_menu, r.qty, fmtRp(r.total)]) }] : []
  ));

  document.getElementById('btnPbLoad').addEventListener('click', () => loadPembelian().catch((e) => showToast(e.message, 'danger')));
  document.getElementById('btnPbReset').addEventListener('click', () => {
    document.getElementById('pbBahan').value = '';
    resetPeriod('pb');
    loadPembelian().catch((e) => showToast(e.message, 'danger'));
  });
  document.getElementById('btnPbExcel').addEventListener('click', () => downloadCsv(`laporan-pembelian-${now.toISOString().slice(0, 10)}.csv`, store.pembelian.heads, store.pembelian.items.map(pbRow)));
  document.getElementById('btnPbPdf').addEventListener('click', () => downloadPdf('Laporan Pembelian — Damarkandang', periodCaption('pb'), store.pembelian.heads, store.pembelian.items.map(pbRow)));

  document.getElementById('keuArus').addEventListener('change', refreshKeuanganJenisSumber);
  document.getElementById('btnKeuLoad').addEventListener('click', () => loadKeuangan().catch((e) => showToast(e.message, 'danger')));
  document.getElementById('btnKeuReset').addEventListener('click', () => {
    document.getElementById('keuArus').value = 'semua';
    refreshKeuanganJenisSumber();
    document.getElementById('keuJenis').value = '';
    document.getElementById('keuSumber').value = '';
    resetPeriod('keu');
    loadKeuangan().catch((e) => showToast(e.message, 'danger'));
  });
  document.getElementById('btnKeuExcel').addEventListener('click', () => downloadCsv(`laporan-keuangan-${now.toISOString().slice(0, 10)}.csv`, store.keuangan.heads, store.keuangan.items.map(keuRow)));
  document.getElementById('btnKeuPdf').addEventListener('click', () => downloadPdf(
    'Laporan Keuangan — Damarkandang', periodCaption('keu'), store.keuangan.heads, store.keuangan.items.map(keuRow),
    store.keuangan.rekap.length ? [{ heads: ['Arus', 'Jenis', 'Jumlah', 'Nominal'], rows: store.keuangan.rekap.map((r) => [r.arus, r.jenis, r.jumlah, fmtRp(r.total)]) }] : []
  ));

  document.getElementById('btnStLoad').addEventListener('click', () => loadStok().catch((e) => showToast(e.message, 'danger')));
  document.getElementById('btnStReset').addEventListener('click', () => {
    document.getElementById('stBahan').value = '';
    document.getElementById('stTipe').value = '';
    resetPeriod('st');
    loadStok().catch((e) => showToast(e.message, 'danger'));
  });
  document.getElementById('btnStExcel').addEventListener('click', () => {
    const snapHeads = ['Jenis Bahan', 'Stok (gram)', 'Status'];
    const snapRows = store.stok.snapshot.map((r) => [r.nama_jenis, r.stok_gram, r.stok_status_label || r.stok_status]);
    downloadCsv(`laporan-stok-${now.toISOString().slice(0, 10)}.csv`, store.stok.heads, [
      ...store.stok.items.map(stRow), [], ['Stok Saat Ini'], snapHeads, ...snapRows,
    ]);
  });
  document.getElementById('btnStPdf').addEventListener('click', () => downloadPdf(
    'Laporan Stok — Damarkandang', periodCaption('st'), store.stok.heads, store.stok.items.map(stRow),
    [{ heads: ['Jenis Bahan', 'Stok (gram)', 'Status'], rows: store.stok.snapshot.map((r) => [r.nama_jenis, r.stok_gram, r.stok_status_label || r.stok_status]) }]
  ));

  document.querySelector('[data-bs-target="#tabPenjualan"]')?.addEventListener('shown.bs.tab', () => loadPenjualan().catch((e) => { if (!isAbortError(e)) showToast(e.message, 'danger'); }));
  document.querySelector('[data-bs-target="#tabPembelian"]')?.addEventListener('shown.bs.tab', () => loadPembelian().catch((e) => { if (!isAbortError(e)) showToast(e.message, 'danger'); }));
  document.querySelector('[data-bs-target="#tabKeuangan"]')?.addEventListener('shown.bs.tab', () => loadKeuangan().catch((e) => { if (!isAbortError(e)) showToast(e.message, 'danger'); }));
  document.querySelector('[data-bs-target="#tabStok"]')?.addEventListener('shown.bs.tab', () => loadStok().catch((e) => { if (!isAbortError(e)) showToast(e.message, 'danger'); }));

  const debouncedPj = debounce(() => loadPenjualan().catch(() => {}), 350);
  const debouncedPb = debounce(() => loadPembelian().catch(() => {}), 350);
  const debouncedKeu = debounce(() => {
    refreshKeuanganJenisSumber();
    loadKeuangan().catch(() => {});
  }, 350);
  const debouncedSt = debounce(() => loadStok().catch(() => {}), 350);

  ['pjProduk', 'pjPetugas', 'pjBulan', 'pjDari', 'pjSampai'].forEach((id) => {
    document.getElementById(id)?.addEventListener('change', debouncedPj);
  });
  ['pbBahan', 'pbBulan', 'pbDari', 'pbSampai'].forEach((id) => {
    document.getElementById(id)?.addEventListener('change', debouncedPb);
  });
  ['keuArus', 'keuJenis', 'keuSumber', 'keuBulan', 'keuDari', 'keuSampai'].forEach((id) => {
    document.getElementById(id)?.addEventListener('change', () => {
      if (id === 'keuArus') refreshKeuanganJenisSumber();
      debouncedKeu();
    });
  });
  ['stBahan', 'stTipe', 'stBulan', 'stDari', 'stSampai'].forEach((id) => {
    document.getElementById(id)?.addEventListener('change', debouncedSt);
  });

  toggleBmNilaiInputs();
  loadJenisOptions().then(() => loadBahanMasuk()).catch((e) => showToast(e.message, 'danger'));
  loadOpsi().catch((e) => showToast(e.message, 'danger'));
})();
