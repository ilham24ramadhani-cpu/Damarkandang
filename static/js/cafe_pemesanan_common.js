(function () {
  let paymentMaster = {};

  async function loadPaymentMaster() {
    try {
      const res = await CafeAPI.get('/data-pembayaran');
      paymentMaster = {};
      (res.data.items || []).forEach((p) => { paymentMaster[p.metode] = p; });
    } catch (e) { /* optional */ }
  }

  function statusBadge(s) {
    return s === 'ordering'
      ? '<span class="badge bg-warning text-dark">Ordering</span>'
      : '<span class="badge bg-success">Lunas</span>';
  }

  function renderStruk(order) {
    const info = order.info_pembayaran || paymentMaster[order.metode_bayar_key] || {};
    const lines = (order.items || []).map((i) =>
      `<div class="d-flex justify-content-between"><span>${i.nama_menu} x${i.qty}</span><span>${formatRupiah(i.subtotal)}</span></div>`
    ).join('');
    let payBlock = '<p class="mb-1"><strong>Status:</strong> Pemasukan tercatat</p>';
    if (order.metode_bayar) payBlock = `<p class="mb-1"><strong>Metode:</strong> ${order.metode_bayar}</p>` + payBlock;
    if (order.metode_bayar_key === 'cash' || (order.metode_bayar || '').toLowerCase() === 'cash') {
      payBlock += '<p class="mb-0 text-success"><strong>Pembayaran: CASH</strong></p>';
    } else {
      if (info.gambar_url) payBlock += `<img src="${info.gambar_url}" alt="QR/Rekening" class="my-2 d-block" />`;
      if (info.nomor_rekening) {
        payBlock += `<p class="mb-0"><strong>Rek:</strong> ${info.nomor_rekening}${info.nama_rekening ? ' a/n ' + info.nama_rekening : ''}</p>`;
      }
    }
    const el = document.getElementById('strukContent');
    if (!el) return;
    const namaLine = order.nama_pelanggan
      ? `<p class="mb-1"><strong>Nama:</strong> ${order.nama_pelanggan}</p>`
      : '';
    const petugasLine = order.petugas?.nama_lengkap
      ? `<p class="mb-1"><strong>Petugas:</strong> ${order.petugas.nama_lengkap}</p>`
      : '';
    el.innerHTML = `
      <div class="text-center mb-2"><strong>DAMARKANDANG</strong><br/><small>Nota Penjualan</small></div>
      <p class="mb-1"><strong>ID:</strong> ${order.id_pemesanan || order.id_transaksi}</p>
      ${namaLine}
      ${petugasLine}
      <p class="mb-1"><strong>Tanggal:</strong> ${order.tanggal}</p><hr class="my-2"/>${lines}
      <hr class="my-2"/><div class="d-flex justify-content-between fw-bold"><span>TOTAL</span><span>${formatRupiah(order.total)}</span></div>
      <hr class="my-2"/>${payBlock}<p class="text-center mt-2 mb-0"><small>Terima kasih</small></p>`;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('modalStruk')).show();
  }

  function printStruk() {
    const el = document.getElementById('strukContent');
    if (!el) return;
    const w = window.open('', '_blank');
    w.document.write('<html><head><title>Nota</title></head><body>' + el.innerHTML + '</body></html>');
    w.document.close();
    w.print();
  }

  window.PemesananUI = {
    loadPaymentMaster,
    statusBadge,
    renderStruk,
    printStruk,
    getPaymentMaster: () => paymentMaster,
  };

  loadPaymentMaster();
})();
