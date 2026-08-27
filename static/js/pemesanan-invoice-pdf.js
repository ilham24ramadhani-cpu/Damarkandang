/**
 * Helper kloter pemesanan + layout PDF invoice lengkap.
 * Load setelah jsPDF, sebelum kelola_pemesanan.js / kelola_laporan.js.
 */
function invoiceFormatDateForPdf(dateString) {
  if (!dateString) return "-";
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString("id-ID", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  } catch (error) {
    return dateString;
  }
}

/** Baca kloter dari dokumen API (kloter → items → satu baris root). */
function getPemesananKloterLinesFromDoc(p) {
  if (!p) return [];
  const rows = p.kloter || p.items;
  if (Array.isArray(rows) && rows.length > 0) {
    const mapped = rows.map((r) => ({
      tipeProduk: r.tipeProduk || "",
      jenisKopi: r.jenisKopi || "",
      prosesPengolahan: r.prosesPengolahan || "",
      beratKg:
        r.beratKg != null && r.beratKg !== ""
          ? r.beratKg
          : r.jumlahPesananKg != null
            ? r.jumlahPesananKg
            : "",
      hargaPerKg: r.hargaPerKg != null ? r.hargaPerKg : "",
      jumlahPembayaranKloter:
        r.jumlahPembayaranKloter != null && r.jumlahPembayaranKloter !== ""
          ? r.jumlahPembayaranKloter
          : "",
      pembayaranKloterLunas: r.pembayaranKloterLunas,
    }));
    // Penyimpanan mengikuti urutan tambah (lama → baru); tampilan: terbaru di atas.
    return mapped.slice().reverse();
  }
  return [
    {
      tipeProduk: p.tipeProduk || "",
      jenisKopi: p.jenisKopi || "",
      prosesPengolahan: p.prosesPengolahan || "",
      beratKg: p.jumlahPesananKg != null ? p.jumlahPesananKg : "",
      hargaPerKg: p.hargaPerKg != null ? p.hargaPerKg : "",
      jumlahPembayaranKloter:
        p.jumlahPembayaranKloter != null && p.jumlahPembayaranKloter !== ""
          ? p.jumlahPembayaranKloter
          : "",
    },
  ];
}

/** True = nominal masuk total terbayar & pemasukan (default untuk dokumen lama). */
function pembayaranBarisLunasTrue(raw) {
  if (raw === undefined || raw === null) return true;
  if (typeof raw === "boolean") return raw;
  const s = String(raw).trim().toLowerCase();
  if (["false", "0", "no", "tidak", "belum lunas", "belum"].includes(s)) return false;
  return true;
}

/** Subtotal Rp satu baris kloter (berat × harga/kg), selaras kolom subtotal di DATA PEMESANAN. */
function pemesananKloterSubtotalRpFromRow(row) {
  if (!row) return 0;
  const j = parseFloat(row.beratKg) || 0;
  const hp = parseFloat(row.hargaPerKg) || 0;
  return Math.round(j * hp * 100) / 100;
}

/** Normalisasi tipe pajak (default penjumlahan untuk dokumen lama). */
function normalizeTipePajak(raw) {
  const t = String(raw || "penjumlahan")
    .trim()
    .toLowerCase();
  if (t === "pengurangan" || t === "kurang" || t === "minus") return "pengurangan";
  return "penjumlahan";
}

/** Label tipe pajak di form & laporan. */
function labelTipePajak(raw) {
  return normalizeTipePajak(raw) === "pengurangan"
    ? 'PPh 22 (-)'
    : 'PPh 22 (+)';
}

/** Keterangan pajak di invoice PDF (tanpa tanda +/-). */
function labelTipePajakInvoice() {
  return "PPh 22";
}

/** Total tagihan: subtotal kloter ± pajak + pengiriman. */
function hitungTotalPemesananDariKomponen(
  subtotalBarang,
  biayaPajak,
  biayaPengiriman,
  tipePajak,
) {
  const sub = Math.max(0, parseFloat(subtotalBarang) || 0);
  const pajak = Math.max(0, parseFloat(biayaPajak) || 0);
  const kirim = Math.max(0, parseFloat(biayaPengiriman) || 0);
  const tipe = normalizeTipePajak(tipePajak);
  const dasar =
    tipe === "pengurangan" ? sub - pajak : sub + pajak;
  return Math.max(0, Math.round((dasar + kirim) * 100) / 100);
}

/** Σ pembayaran yang sudah lunas (per kloter + pembayaranBertahapBaris). Selaras totalPembayaranKloter di API. */
function sumJumlahPembayaranKloterFromDoc(p) {
  if (!p) return 0;
  const agg = parseFloat(p.totalPembayaranKloter);
  if (Number.isFinite(agg) && agg >= 0) return Math.round(agg * 100) / 100;
  const rows = p.kloter || p.items;
  let s = 0;
  if (Array.isArray(rows)) {
    rows.forEach((r) => {
      const v = parseFloat(r.jumlahPembayaranKloter);
      if (!Number.isFinite(v) || v <= 0) return;
      if (!pembayaranBarisLunasTrue(r.pembayaranKloterLunas)) return;
      s += v;
    });
  }
  const extra = p.pembayaranBertahapBaris;
  if (Array.isArray(extra)) {
    extra.forEach((it) => {
      const v = parseFloat(it?.jumlahRp);
      if (!Number.isFinite(v) || v <= 0) return;
      if (!pembayaranBarisLunasTrue(it.terminLunas)) return;
      s += v;
    });
  }
  return Math.round(s * 100) / 100;
}

/**
 * Sisa tagihan = total harga − Σ pembayaran tercatat (selaras field totalPembayaranSaatIni di API).
 */
function totalPembayaranSaatIniFromDoc(p) {
  if (!p) return 0;
  const th = parseFloat(p.totalHarga) || 0;
  const fromApi = parseFloat(p.totalPembayaranSaatIni);
  if (Number.isFinite(fromApi) && fromApi >= 0) return Math.round(fromApi * 100) / 100;
  const sum = sumJumlahPembayaranKloterFromDoc(p);
  return Math.max(0, Math.round((th - sum) * 100) / 100);
}

/** Σ nominal baris pembayaranBertahapBaris (hanya baris yang dipakai invoice) + Σ yang belum lunas. */
function pdfSumPembayaranBertahapFromDoc(p) {
  const rows = pdfPembayaranBertahapBarisOnlyForInvoice(p);
  let sumAll = 0;
  let sumBelum = 0;
  rows.forEach((ex) => {
    const jj = Math.round((parseFloat(ex?.jumlahRp) || 0) * 100) / 100;
    if (jj <= 0) return;
    sumAll += jj;
    if (!pembayaranBarisLunasTrue(ex?.terminLunas)) sumBelum += jj;
  });
  return {
    sumAll: Math.round(sumAll * 100) / 100,
    sumBelum: Math.round(sumBelum * 100) / 100,
  };
}

/**
 * Angka TOTAL TAGIHAN di kotak ringkasan PDF (aturan khusus pembayaran bertahap):
 * - Status "Pembayaran Bertahap" dan masih ada nominal termin belum lunas → total = Σ nominal termin belum lunas.
 * - Status "Pembayaran Bertahap" dan tidak ada nominal termin belum lunas (sudah lunas / tidak ada tunggakan bertahap) → total = total pemesanan (totalHarga) dikurangi Σ nominal semua baris bertahap tercatat.
 * - Selain itu → sisa tagihan (selaras totalPembayaranSaatIniFromDoc / API).
 */
function invoiceTotalTagihanKotakFromDoc(p) {
  const sisa = totalPembayaranSaatIniFromDoc(p);
  const statusBayar = String(p?.statusPembayaran || "").trim();
  if (statusBayar !== "Pembayaran Bertahap") return sisa;

  const th = Math.max(0, Math.round((parseFloat(p?.totalHarga) || 0) * 100) / 100);
  const { sumAll, sumBelum } = pdfSumPembayaranBertahapFromDoc(p);

  if (sumBelum > 0) return sumBelum;
  if (sumAll > 0) return Math.max(0, Math.round((th - sumAll) * 100) / 100);
  return sisa;
}
/** Warna border netral #e5e5e5 (dipakai header & tabel). */
const INVOICE_BORDER_RGB = [229, 229, 229];
/** Aksen hijau merek (judul bagian, total, nama perusahaan di kop). */
const INV_GREEN_RGB = [28, 115, 68];
/** Latar header tabel / baris ringkasan (hijau lembut). */
const INV_GREEN_LIGHT_RGB = [228, 241, 232];
/** Latar kotak ringkasan dokumen. */
const INV_GRAY_BOX_RGB = [248, 249, 250];
/** Baris total tegas (teks putih di atas hijau tua). */
const INV_GREEN_DARK_RGB = [22, 101, 52];
/** Header tabel order (#e8f2ea). */
const INV_TABLE_HEADER_RGB = [232, 242, 234];
/** Zebra baris genap (#fafafa). */
const INV_ZEBRA_RGB = [250, 250, 250];
/** Label (#262626) — kontras cetak, selaras teks tebal di UI. */
const INV_LABEL_MUTED_RGB = [38, 38, 38];
/** Teks isi (#0f0f0f). */
const INV_TEXT_BODY_RGB = [15, 15, 15];
/**
 * Warna badge selaras Bootstrap 5 + tabel kelola_pemesanan.js
 * (success / warning+text-dark / info+text-dark).
 */
const BS_SUCCESS_RGB = [25, 135, 84];
const BS_WARNING_RGB = [255, 193, 7];
const BS_INFO_RGB = [13, 202, 240];
const BS_SECONDARY_RGB = [108, 117, 125];
const BS_BADGE_TEXT_DARK_RGB = [33, 37, 41];
const BS_WHITE_RGB = [255, 255, 255];

/** Logo + kop surat Damarkandang untuk PDF invoice */
async function fetchArgopuroLogoForPdf() {
  try {
    const url = `${window.location.origin}/brand-assets/logo.png`;
    const res = await fetch(url);
    if (!res.ok) return null;
    const blob = await res.blob();
    return await new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = reject;
      r.readAsDataURL(blob);
    });
  } catch (e) {
    console.warn("Logo tidak dimuat:", e);
    return null;
  }
}

/**
 * Kop invoice (gaya INVOICE PEMESANAN): logo kiri, perusahaan kanan (hijau), judul tengah.
 * ID / tanggal / badge status ada di kotak "Ringkasan dokumen" pada isi halaman.
 * @param {{ singlePage?: boolean }} [opts]
 */
function pdfDrawArgopuroInvoiceHeader(doc, logoDataUrl, p, opts) {
  void p;
  const sp = opts && opts.singlePage ? 0.9 : 1;
  const MARGIN_L = invoicePxToMm(40);
  const MARGIN_R = invoicePxToMm(40);
  const MARGIN_T = invoicePxToMm(30) * sp;
  const PAGE_W = 210;
  const RX = PAGE_W - MARGIN_R;
  const CX = PAGE_W / 2;
  const FT_TITLE = invoiceFontPtFromPx(18 * sp);
  const FT_BODY = invoiceFontPtFromPx(12 * sp);
  const FT_CO = invoiceFontPtFromPx(14 * sp);
  const SECTION_AFTER_TITLE = invoicePxToMm(22) * sp;
  const LINE_ADDR = 3.85 * sp + 0.3;
  const GAP_AFTER_KOP = opts && opts.singlePage ? 2.2 : 2.8;

  const nama = "Damarkandang";
  const kontak = "+62 857-0766-1006";
  const alamat =
    "Ds. Tlogosari Rt 06/Rw 01, Kecamatan Sumbermalang, Kabupaten Situbondo";

  let y = MARGIN_T;
  const logoW = 22;
  const logoH = 22;
  const gapLogo = 5;
  if (logoDataUrl) {
    try {
      doc.addImage(logoDataUrl, "PNG", MARGIN_L, y, logoW, logoH);
    } catch (e) {
      console.warn("addImage logo:", e);
    }
  }

  const blockLeft = logoDataUrl ? MARGIN_L + logoW + gapLogo : MARGIN_L;
  const addrW = Math.max(52, RX - blockLeft - 4);

  doc.setTextColor(...INV_GREEN_RGB);
  doc.setFontSize(FT_CO);
  pdfInvSetFont(doc, "bold");
  doc.text(nama, RX, y + 6.2, { align: "right" });
  doc.setTextColor(42, 42, 42);
  doc.setFontSize(FT_BODY);
  pdfInvSetFont(doc, "bold");
  doc.text(`Kontak: ${kontak}`, RX, y + 10.8, { align: "right" });
  doc.setFontSize(FT_BODY - 0.5);
  pdfInvSetFont(doc, "normal");
  doc.setTextColor(42, 42, 42);
  const addrLines = doc.splitTextToSize(alamat, addrW);
  let ay = y + 15.2;
  addrLines.forEach((ln) => {
    doc.text(ln, RX, ay, { align: "right" });
    ay += LINE_ADDR;
  });

  const yLeftBottom = logoDataUrl ? y + logoH : y;
  const yTextBottom = ay + 1;
  const yRule = Math.max(yLeftBottom, yTextBottom) + GAP_AFTER_KOP;

  doc.setDrawColor(...INVOICE_BORDER_RGB);
  doc.setLineWidth(0.18);
  doc.line(MARGIN_L, yRule, RX, yRule);

  const gapTitle = opts && opts.singlePage ? 4.2 : 5.5;
  let yTitle = yRule + gapTitle;
  doc.setTextColor(22, 22, 22);
  doc.setFontSize(FT_TITLE);
  pdfInvSetFont(doc, "bold");
  doc.text("INVOICE PEMESANAN", CX, yTitle, { align: "center" });
  pdfInvSetFont(doc, "normal");
  doc.setFontSize(FT_BODY - 0.5);
  doc.setTextColor(48, 48, 48);
  const sub = "Dokumen pembelian resmi — mohon periksa rincian berikut.";
  const subLines = doc.splitTextToSize(sub, RX - MARGIN_L - MARGIN_R - 20);
  let ys = yTitle + 5.5;
  subLines.forEach((ln) => {
    doc.text(ln, CX, ys, { align: "center" });
    ys += LINE_ADDR * 0.95;
  });
  doc.setTextColor(0, 0, 0);

  return ys + SECTION_AFTER_TITLE - 2;
}

/**
 * Ringkasan dokumen: grid 2 kolom sama lebar, gap 24px, label 160px + nilai/badge.
 * @param {{ compact?: boolean }} [layoutOpts]
 */
function pdfDrawRingkasanDokumenBox(doc, LX, RX, yTop, p, layoutOpts) {
  const compact = !!(layoutOpts && layoutOpts.compact);
  const sc = compact ? 0.93 : 1;
  const pad = (invoicePxToMm(32) * 0.12 + 3) * sc;
  const gap = invoicePxToMm(24) * sc;
  const lblW = invoicePxToMm(160);
  const titleBarH = compact ? 6.2 : 7;
  const W = RX - LX;
  const innerW = W - pad * 2;
  const colW = (innerW - gap) / 2;
  const c1 = LX + pad;
  const c2 = c1 + colW + gap;
  const FT = invoiceFontPtFromPx(compact ? 11 : 12);
  const FT_TITLE = invoiceFontPtFromPx(compact ? 13 : 14);

  const idDoc = p?.idPembelian || "-";
  const tgl = invoiceFormatDateForPdf(
    p?.tanggalPemesanan || new Date().toISOString(),
  );
  const orderLabel = (p?.statusPemesanan || "—").trim();
  const bayarLabel = (p?.statusPembayaran || "Belum Lunas").trim();

  /** Jarak pusat vertikal antar baris: tinggi badge (22px) + gap 8px — rowH lama < tinggi badge sehingga badge overlap. */
  const badgeH = invoicePxToMm(22) * sc;
  const statusRowGap = invoicePxToMm(8) * sc;
  const rowPitch = badgeH + statusRowGap;
  const lineMm = (FT * 25.4) / 72;
  const innerTop = yTop + titleBarH + pad;
  const cy1 = innerTop + badgeH * 0.5 + 0.25;
  const cy2 = cy1 + rowPitch;
  const y1 = cy1 + lineMm * 0.38;
  const y2 = cy2 + lineMm * 0.38;
  const bodyBottom = cy2 + badgeH * 0.5 + pad * 0.45;
  const bodyH = bodyBottom - innerTop;
  const boxH = titleBarH + bodyH + pad;

  doc.setFillColor(...INV_GRAY_BOX_RGB);
  doc.setDrawColor(...INVOICE_BORDER_RGB);
  doc.setLineWidth(0.15);
  doc.roundedRect(LX, yTop, W, boxH, 0.6, 0.6, "FD");

  doc.setFillColor(240, 242, 244);
  doc.rect(LX + 0.15, yTop + 0.15, W - 0.3, titleBarH - 0.05, "F");
  doc.setDrawColor(...INVOICE_BORDER_RGB);
  doc.setLineWidth(0.1);
  doc.line(LX, yTop + titleBarH, LX + W, yTop + titleBarH);

  doc.setFontSize(FT_TITLE);
  pdfInvSetFont(doc, "bold");
  doc.setTextColor(24, 24, 24);
  doc.text("Ringkasan dokumen", LX + pad, yTop + titleBarH * 0.62);
  pdfInvSetFont(doc, "normal");

  doc.setFontSize(FT);
  pdfInvSetFont(doc, "bold");
  doc.setTextColor(...INV_LABEL_MUTED_RGB);
  doc.text("ID Pembelian", c1, y1);
  doc.text("Tanggal pemesanan", c1, y2);
  doc.text("Status pemesanan", c2, y1);
  doc.text("Status pembayaran", c2, y2);

  const v1 = c1 + lblW;
  const v2 = c2 + lblW;
  pdfInvSetFont(doc, "bold");
  doc.setTextColor(...INV_TEXT_BODY_RGB);
  doc.text(String(idDoc), v1, y1);
  doc.text(tgl, v1, y2);

  const badge1X = v2;
  const badge2X = v2;
  pdfDrawOrderStatusBadge(doc, badge1X, cy1, orderLabel);
  pdfDrawPaymentBadge(doc, badge2X, cy2, bayarLabel);

  const splitX = c1 + colW + gap * 0.5;
  doc.setDrawColor(...INVOICE_BORDER_RGB);
  doc.setLineWidth(0.12);
  doc.line(splitX, yTop + titleBarH + 0.4, splitX, yTop + boxH - pad * 0.45);

  doc.setTextColor(0, 0, 0);
  pdfInvSetFont(doc, "normal");
  return yTop + boxH + 2;
}

/** Angka dengan pemisah ribuan Indonesia, tanpa prefiks Rp/kg */
function pdfFmtIdNumber(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "0";
  return v.toLocaleString("id-ID");
}

/** Nominal pajak di invoice: selalu positif & hitam (tanda ± hanya di form pencatatan). */
function pdfFmtPajakInvoiceValue(amount) {
  return pdfFmtIdNumber(Math.max(0, parseFloat(amount) || 0));
}

/**
 * Tepi kiri kolom tabel order (No 6%, Item 40%, …) dalam rentang [lx,rx].
 * @returns {number[]} edges panjang 8: edges[i]..edges[i+1] = kolom i
 */
function pdfOrderTableEdges(lx, rx) {
  const w = rx - lx;
  const pct = [0.06, 0.4, 0.1, 0.14, 0.14, 0.1, 0.06];
  const out = [lx];
  let acc = lx;
  pct.forEach((p) => {
    acc += w * p;
    out.push(acc);
  });
  return out;
}

/** Konversi px (96dpi) → mm untuk layout A4 di jsPDF. */
function invoicePxToMm(px) {
  return (Number(px) * 25.4) / 96;
}

/** Ukuran font PDF (pt) dari px layar (96dpi): px × 72/96. */
function invoiceFontPtFromPx(px) {
  return (Number(px) * 72) / 96;
}

/** Tinggi halaman A4 jsPDF (mm). */
const PDF_PAGE_HEIGHT_MM = 297;
/** Margin bawah aman (mm). */
const PDF_SAFE_BOTTOM_MM = 10;
/**
 * Margin bawah aman saat memutus baris tabel DATA PEMESANAN (bukan cadangan ringkasan).
 * Cadangan besar (108mm) salah dipakai di sini → halaman baru terlalu awal dengan banyak ruang kosong.
 * Ringkasan + footer punya pengecekan addPage terpisah.
 */
const PDF_INVOICE_TABLE_ROW_SAFE_BOTTOM_MM = 8;
/** Invoice standar: jangan pecah halaman ringkasan/footer jika kloter ≤ batas ini (layout tetap sama). */
const PDF_INVOICE_STANDARD_ONE_PAGE_MAX_KLOTER = 10;

function pdfInvoiceContinuePageTopMm() {
  return invoicePxToMm(24);
}

/** Batas Y aman untuk isi (mm). */
function pdfInvoicePageContentBottomMm() {
  return PDF_PAGE_HEIGHT_MM - PDF_SAFE_BOTTOM_MM;
}

/** Font tunggal untuk invoice PDF (built-in jsPDF). */
const PDF_FONT = "helvetica";

function pdfInvSetFont(doc, style) {
  doc.setFont(PDF_FONT, style || "normal");
}

/** Teks untuk PDF: uraikan entitas HTML bertingkat (mis. &amp;amp; → &). */
function pdfDecodeHtmlEntities(raw) {
  let s = String(raw ?? "");
  for (let i = 0; i < 12; i++) {
    const t = s
      .replace(/&nbsp;/gi, " ")
      .replace(/&#(\d+);/g, (m, n) => {
        const c = parseInt(n, 10);
        return Number.isFinite(c) && c >= 0 && c <= 0x10ffff
          ? String.fromCodePoint(c)
          : m;
      })
      .replace(/&#x([0-9a-fA-F]+);/g, (m, h) => {
        const c = parseInt(h, 16);
        return Number.isFinite(c) && c >= 0 && c <= 0x10ffff
          ? String.fromCodePoint(c)
          : m;
      })
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&apos;/g, "'");
    if (t === s) break;
    s = t;
  }
  return s;
}

/**
 * Tabel catatan pemesanan (bingkai + header + isi).
 * Tanpa forceSinglePage: isi dipecah ke beberapa halaman jika perlu (tidak dipotong "…").
 * @returns {number} y di bawah blok terakhir + marginBottom
 */
function pdfDrawCatatanPemesananTable(doc, LX, y, catatanRaw, opts) {
  const optsObj = opts || {};
  const forceSinglePage = !!optsObj.forceSinglePage;
  const pageBottom =
    optsObj && Number.isFinite(optsObj.pageBottom)
      ? optsObj.pageBottom
      : pdfInvoicePageContentBottomMm();
  const W =
    optsObj && Number.isFinite(optsObj.width) ? optsObj.width : 190 - LX;
  const padX = 3.5;
  const innerW = W - padX * 2;
  const marginBottom =
    optsObj && Number.isFinite(optsObj.marginBottom)
      ? optsObj.marginBottom
      : 6;
  const decoded = pdfDecodeHtmlEntities(String(catatanRaw).trim());
  const blocks = decoded
    .split(/\r?\n/)
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
  const lineH = 4;
  const headerH = 8;
  const bodyPadTop = 4.5;
  const bodyPadBottom = 4.5;
  const displayLines = [];
  doc.setFontSize(8);
  pdfInvSetFont(doc, "normal");
  blocks.forEach((blk, idx) => {
    doc.splitTextToSize(blk, innerW).forEach((ln) => displayLines.push(ln));
    if (idx < blocks.length - 1) displayLines.push("");
  });
  if (displayLines.length === 0) {
    displayLines.push("");
  }

  const drawChunk = (yTop, titleText, chunkLines, lhIn, fsBodyIn) => {
    const lhUse = Number.isFinite(lhIn) && lhIn > 0 ? lhIn : lineH;
    const fsB =
      Number.isFinite(fsBodyIn) && fsBodyIn > 0 ? fsBodyIn : 8;
    const bodyH = bodyPadTop + chunkLines.length * lhUse + bodyPadBottom;
    const tableH = headerH + bodyH;
    doc.setDrawColor(38, 120, 55);
    doc.setLineWidth(0.15);
    doc.roundedRect(LX, yTop, W, tableH, 1, 1, "S");

    doc.setFillColor(...INV_GREEN_LIGHT_RGB);
    doc.rect(LX + 0.2, yTop + 0.2, W - 0.4, headerH - 0.05, "F");
    doc.setDrawColor(38, 120, 55);
    doc.setLineWidth(0.12);
    doc.line(LX, yTop + headerH, LX + W, yTop + headerH);

    doc.setTextColor(...INV_GREEN_RGB);
    pdfInvSetFont(doc, "bold");
    doc.setFontSize(Math.min(8.5, fsB + 0.7));
    doc.text(titleText, LX + padX, yTop + 5.7);
    doc.setTextColor(35, 35, 35);
    pdfInvSetFont(doc, "normal");
    doc.setFontSize(fsB);

    let ty = yTop + headerH + bodyPadTop;
    chunkLines.forEach((ln) => {
      if (ln !== "") doc.text(ln, LX + padX, ty);
      ty += lhUse;
    });

    doc.setTextColor(0, 0, 0);
    doc.setDrawColor(0, 0, 0);
    doc.setLineWidth(0.1);
    doc.setFontSize(9);
    pdfInvSetFont(doc, "normal");
    return yTop + tableH;
  };

  if (forceSinglePage) {
    const shrinkToFit = !!optsObj.shrinkToFit;
    let fsB = 8;
    let lhU = lineH;
    const linesWork = [];
    const rebuildLines = () => {
      linesWork.length = 0;
      doc.setFontSize(fsB);
      pdfInvSetFont(doc, "normal");
      blocks.forEach((blk, idx) => {
        doc.splitTextToSize(blk, innerW).forEach((ln) => linesWork.push(ln));
        if (idx < blocks.length - 1) linesWork.push("");
      });
      if (!linesWork.length) linesWork.push("");
    };
    rebuildLines();
    if (shrinkToFit) {
      for (let i = 0; i < 22; i++) {
        const th =
          headerH + bodyPadTop + linesWork.length * lhU + bodyPadBottom;
        if (y + th <= pageBottom || fsB <= 5.05) break;
        fsB -= 0.32;
        lhU = Math.max(2.45, lhU - 0.06);
        rebuildLines();
      }
    }
    let th = headerH + bodyPadTop + linesWork.length * lhU + bodyPadBottom;
    if (y + th > pageBottom) {
      const avail = pageBottom - y - headerH - bodyPadTop - bodyPadBottom;
      const maxLines = Math.max(1, Math.floor(avail / lhU));
      if (linesWork.length > maxLines) {
        const head = linesWork.slice(0, Math.max(0, maxLines - 1));
        head.push("…");
        linesWork.length = 0;
        head.forEach((ln) => linesWork.push(ln));
      }
    }
    const yEnd = drawChunk(y, "CATATAN PEMESANAN", linesWork, lhU, fsB);
    return yEnd + marginBottom;
  }

  let positionY = y;
  let remaining = displayLines.slice();
  let firstChunk = true;
  while (remaining.length > 0) {
    let maxBody =
      pageBottom - positionY - headerH - bodyPadTop - bodyPadBottom;
    if (maxBody < lineH) {
      doc.addPage();
      positionY = pdfInvoiceContinuePageTopMm();
      maxBody =
        pageBottom - positionY - headerH - bodyPadTop - bodyPadBottom;
    }
    const maxLines = Math.max(1, Math.floor(maxBody / lineH));
    const take = Math.min(remaining.length, maxLines);
    const chunk = remaining.splice(0, take);
    const title = firstChunk ? "CATATAN PEMESANAN" : "CATATAN PEMESANAN (lanjutan)";
    firstChunk = false;
    positionY = drawChunk(positionY, title, chunk, lineH, 8);
    positionY += marginBottom;
  }
  return positionY;
}

/**
 * Perkiraan tinggi tabel catatan (mm), selaras perhitungan pdfDrawCatatanPemesananTable.
 */
function pdfEstimateCatatanTableHeight(doc, catatanRaw, W, marginBottom) {
  const mb = Number.isFinite(marginBottom) ? marginBottom : 6;
  const padX = 3.5;
  const innerW = W - padX * 2;
  const decoded = pdfDecodeHtmlEntities(String(catatanRaw || "").trim());
  const blocks = decoded
    .split(/\r?\n/)
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
  const lineH = 4;
  const headerH = 8;
  const bodyPadTop = 4.5;
  const bodyPadBottom = 4.5;
  const displayLines = [];
  doc.setFontSize(8);
  pdfInvSetFont(doc, "normal");
  blocks.forEach((blk, idx) => {
    doc.splitTextToSize(blk, innerW).forEach((ln) => displayLines.push(ln));
    if (idx < blocks.length - 1) displayLines.push("");
  });
  const bodyH = bodyPadTop + displayLines.length * lineH + bodyPadBottom;
  return headerH + bodyH + mb;
}

/** Tinggi kolom tanda tangan (mm), selaras drawTtdSeller di pdfDrawInvoiceBody. */
function pdfEstimateSignatureColumnHeightMm(singlePage) {
  const SIG_BOX_MIN_H = invoicePxToMm(singlePage ? 118 : 160);
  return Math.max(
    singlePage ? 30 : 38,
    SIG_BOX_MIN_H * (singlePage ? 0.44 : 0.54),
  );
}

/** Perkiraan tinggi blok footer (catatan + TTD sejajar), untuk cek muat satu halaman. */
function pdfEstimateInvoiceFooterBlockMm(doc, catatanRaw, catW, singlePage, sigBeforeMm) {
  const sigH = pdfEstimateSignatureColumnHeightMm(singlePage);
  const catH = catatanRaw
    ? pdfEstimateCatatanTableHeight(doc, catatanRaw, catW, 3)
    : 0;
  return (sigBeforeMm || 0) + Math.max(catH, sigH) + 3;
}

/**
 * Warna badge pembayaran — sama logika kelas di kelola_pemesanan.js:
 * Lunas → bg-success putih; Pembayaran Bertahap → bg-info text-dark;
 * lainnya (Belum Lunas) → bg-warning text-dark.
 */
function pdfPaymentBadgeColors(status) {
  const s = (status || "Belum Lunas").trim();
  if (s === "Lunas") {
    return { bg: [...BS_SUCCESS_RGB], fg: [...BS_WHITE_RGB] };
  }
  const low = s.toLowerCase();
  if (s === "Pembayaran Bertahap" || low === "pembayaran bertahap") {
    return { bg: [...BS_INFO_RGB], fg: [...BS_BADGE_TEXT_DARK_RGB] };
  }
  return { bg: [...BS_WARNING_RGB], fg: [...BS_BADGE_TEXT_DARK_RGB] };
}

/**
 * Warna badge status pemesanan — sama tabel kelola_pemesanan.js:
 * Complete → bg-success putih; Ordering → bg-warning text-dark; lainnya → secondary putih.
 */
function pdfOrderStatusBadgeColors(status) {
  const s = (status || "").trim();
  if (s === "Complete") {
    return { bg: [...BS_SUCCESS_RGB], fg: [...BS_WHITE_RGB] };
  }
  if (s === "Ordering") {
    return { bg: [...BS_WARNING_RGB], fg: [...BS_BADGE_TEXT_DARK_RGB] };
  }
  return { bg: [...BS_SECONDARY_RGB], fg: [...BS_WHITE_RGB] };
}

/** Badge status: tinggi 22px, padding 2×10px, font 11px, radius ~BS badge (0.375rem). */
function pdfDrawColoredBadge(doc, x, yCenter, label, colorFn) {
  const text = String(label || "—");
  const fs = invoiceFontPtFromPx(11);
  const h = invoicePxToMm(22);
  const padX = invoicePxToMm(10);
  const rad = Math.min(invoicePxToMm(6), h * 0.32);
  doc.setFontSize(fs);
  pdfInvSetFont(doc, "bold");
  const w = doc.getTextWidth(text);
  const x0 = x;
  const y0 = yCenter - h / 2;
  const { bg, fg } = colorFn(text);
  doc.setFillColor(bg[0], bg[1], bg[2]);
  doc.roundedRect(x0, y0, w + padX * 2, h, rad, rad, "F");
  const yBaseline = yCenter + fs * 0.28;
  doc.setTextColor(fg[0], fg[1], fg[2]);
  doc.text(text, x0 + padX, yBaseline);
  doc.setTextColor(0, 0, 0);
  pdfInvSetFont(doc, "normal");
}

/** Lebar badge (mm) untuk perhitungan grid. */
function pdfEstimateBadgeWidthMm(doc, label) {
  doc.setFontSize(invoiceFontPtFromPx(11));
  pdfInvSetFont(doc, "bold");
  const w = doc.getTextWidth(String(label || "—"));
  pdfInvSetFont(doc, "normal");
  return w + 2 * invoicePxToMm(10);
}

function pdfDrawPaymentBadge(doc, x, yCenter, label) {
  pdfDrawColoredBadge(doc, x, yCenter, label, pdfPaymentBadgeColors);
}

function pdfDrawOrderStatusBadge(doc, x, yCenter, label) {
  pdfDrawColoredBadge(doc, x, yCenter, label, pdfOrderStatusBadgeColors);
}

/** Hanya baris tambahan dari API (DP/termin); pembayaran per kloter tampil di baris kloter, tanpa migrasi ganda. */
function pdfPembayaranBertahapBarisOnlyForInvoice(p) {
  if (!Array.isArray(p?.pembayaranBertahapBaris)) return [];
  return p.pembayaranBertahapBaris.filter((ex) => {
    const jj = parseFloat(ex?.jumlahRp) || 0;
    const ct = String(ex?.catatan || "").trim();
    return jj > 0 || ct.length > 0;
  });
}

/**
 * Untuk laporan HTML & kompatibilitas: baris bertahap dari API, atau migrasi dari jumlahPembayaranKloter (dokumen lama).
 * PDF invoice memakai pdfPembayaranBertahapBarisOnlyForInvoice + kolom di tabel kloter agar tidak dobel.
 */
function pdfPembayaranBertahapRowsForInvoice(p) {
  const fromApi = pdfPembayaranBertahapBarisOnlyForInvoice(p);
  if (fromApi.length > 0) return fromApi;
  const lines = getPemesananKloterLinesFromDoc(p);
  const out = [];
  lines.forEach((row) => {
    const jj = parseFloat(row.jumlahPembayaranKloter) || 0;
    if (jj > 0) {
      const desk = `${row.tipeProduk || "-"} · ${row.jenisKopi || "-"} · ${row.prosesPengolahan || "-"}`;
      out.push({ catatan: desk, jumlahRp: jj, terminLunas: true });
    }
  });
  return out;
}

/** Header tabel order (#e8f2ea), teks 600, border bawah netral. */
function pdfInvoiceGreenTableHeader(doc, lx, rx, yTop, hdrH, cols, hdrFontSize) {
  const w = rx - lx;
  doc.setFillColor(...INV_TABLE_HEADER_RGB);
  doc.rect(lx, yTop, w, hdrH, "F");
  doc.setDrawColor(...INVOICE_BORDER_RGB);
  doc.setLineWidth(0.12);
  doc.line(lx, yTop + hdrH, lx + w, yTop + hdrH);
  const fs =
    Number.isFinite(hdrFontSize) && hdrFontSize > 0 ? hdrFontSize : 8;
  doc.setFontSize(fs);
  const ty = yTop + hdrH * 0.5 + fs * 0.35;
  pdfInvSetFont(doc, "bold");
  doc.setTextColor(12, 72, 40);
  cols.forEach((c) => {
    doc.text(c.label, c.x, ty, c.opt || {});
  });
  doc.setTextColor(0, 0, 0);
  pdfInvSetFont(doc, "normal");
  return yTop + hdrH;
}

/** Header tabel abu-abu lembut + border netral (layout profesional). */
function pdfInvoiceNeutralTableHeader(doc, lx, rx, yTop, hdrH, cols, fontPt) {
  const w = rx - lx;
  doc.setFillColor(242, 244, 246);
  doc.setDrawColor(...INVOICE_BORDER_RGB);
  doc.setLineWidth(0.15);
  doc.rect(lx, yTop, w, hdrH, "FD");
  const ty = yTop + hdrH * 0.7;
  doc.setFontSize(
    Number.isFinite(fontPt) && fontPt > 0 ? fontPt : invoiceFontPtFromPx(12),
  );
  pdfInvSetFont(doc, "bold");
  doc.setTextColor(22, 22, 22);
  cols.forEach((c) => {
    doc.text(c.label, c.x, ty, c.opt || {});
  });
  doc.setTextColor(0, 0, 0);
  pdfInvSetFont(doc, "normal");
  return yTop + hdrH;
}

/** Baris ringkasan di bawah tabel: latar hijau tua, teks putih tebal (kontras cetak). */
function pdfInvoiceTableTotalBand(doc, lx, rx, y, label, valueStr) {
  const h = 7;
  doc.setFillColor(...INV_GREEN_DARK_RGB);
  doc.setDrawColor(18, 90, 48);
  doc.setLineWidth(0.1);
  doc.rect(lx, y, rx - lx, h, "FD");
  doc.setTextColor(255, 255, 255);
  pdfInvSetFont(doc, "bold");
  doc.setFontSize(invoiceFontPtFromPx(11));
  doc.text(label, lx + 3, y + h * 0.7);
  doc.text(valueStr, rx - 3, y + h * 0.7, { align: "right" });
  doc.setTextColor(0, 0, 0);
  pdfInvSetFont(doc, "normal");
  return y + h;
}

/**
 * Label ringkasan untuk satu baris pembayaran bertahap (teks dari input catatan, mis. "DP").
 */
function pdfBertahapRingkasanLabel(ex, lunas) {
  let raw = pdfDecodeHtmlEntities(String(ex?.catatan ?? "").trim()).replace(
    /\s+/g,
    " ",
  );
  if (raw.length > 72) raw = `${raw.slice(0, 69)}…`;
  const judul = raw.length > 0 ? raw : "Pembayaran tahap";
  if (lunas) return `${judul} (sudah lunas)`;
  return `${judul} yang perlu dibayarkan`;
}

/**
 * Blok label (boleh beberapa baris) + nominal rata kanan di kotak ringkasan invoice.
 * @returns {number} y di bawah blok
 */
function pdfDrawInvoiceSummaryKVRow(doc, xBox, yTop, innerW, padX, spec) {
  const {
    label,
    valueStr,
    fontPt = invoiceFontPtFromPx(12),
    labelRgb = INV_LABEL_MUTED_RGB,
    valueRgb = INV_TEXT_BODY_RGB,
    dangerValue = false,
    labelBold = true,
    reserveNumMm = 28,
  } = spec;
  const xL = xBox + padX;
  const labelMax = Math.max(18, innerW - reserveNumMm);
  const lineStep = ((fontPt * 25.4) / 72) * 1.2;
  doc.setFont(PDF_FONT, labelBold ? "bold" : "normal");
  doc.setFontSize(fontPt);
  doc.setTextColor(labelRgb[0], labelRgb[1], labelRgb[2]);
  const lines = doc.splitTextToSize(String(label), labelMax);
  const n = Math.max(lines.length, 1);
  const blockH = n * lineStep;
  const yVal = yTop + blockH * 0.55;

  lines.forEach((ln, i) => {
    doc.text(ln, xL, yTop + lineStep * (i + 0.78));
  });

  const vRgb = dangerValue ? [175, 35, 42] : valueRgb;
  doc.setFont("courier", "bold");
  doc.setFontSize(fontPt);
  doc.setTextColor(vRgb[0], vRgb[1], vRgb[2]);
  doc.text(String(valueStr), xL + innerW, yVal, { align: "right" });

  doc.setFont(PDF_FONT, "normal");
  doc.setTextColor(0, 0, 0);
  pdfInvSetFont(doc, "normal");
  return yTop + blockH + lineStep * 0.15;
}

function pdfDrawInvoiceBody(doc, p, y, opts) {
  pdfInvSetFont(doc, "normal");
  const layout = opts && typeof opts === "object" ? opts : {};
  const singlePage = !!layout.singlePage;
  const sp = singlePage ? 0.82 : 1;

  const MARGIN_L = invoicePxToMm(40);
  const MARGIN_R = invoicePxToMm(40);
  const LX = MARGIN_L;
  const RX = 210 - MARGIN_R;

  const FT_SEC = invoiceFontPtFromPx(singlePage ? 11.5 : 14);
  const FT_BODY = invoiceFontPtFromPx(singlePage ? 9 : 12);
  const LH = invoicePxToMm(singlePage ? 13 : 18);
  const SECTION_MB = invoicePxToMm(singlePage ? 17 : 28) * (singlePage ? 0.92 : 1);
  const BAR_H = singlePage ? 5.2 : 6.8;
  const CELL_PAD_H = invoicePxToMm(8) * sp;
  const CELL_PAD_V = invoicePxToMm(10) * sp;
  const HDR_H =
    CELL_PAD_V * 2 +
    invoiceFontPtFromPx(singlePage ? 9 : 11) * 0.45 +
    (singlePage ? 0.55 : 1.2);
  const BUYER_LBL_W = invoicePxToMm(160) * (singlePage ? 0.92 : 1);
  const BUYER_ROW_GAP = invoicePxToMm(singlePage ? 6 : 8);
  const LX_LABEL = LX + CELL_PAD_H;
  const VX_VALUE = LX_LABEL + BUYER_LBL_W;
  const SUMMARY_BOX_W = invoicePxToMm(singlePage ? 300 : 320);
  const SIG_BEFORE = invoicePxToMm(singlePage ? 22 : 36);
  const FOOT_GRID_GAP = invoicePxToMm(24) * sp;
  const SIG_BOX_MIN_H = invoicePxToMm(singlePage ? 118 : 160);

  const edges = pdfOrderTableEdges(LX, RX);
  const xNoC = (edges[0] + edges[1]) / 2;
  const xItemL = edges[1] + CELL_PAD_H;
  const W_ITEM = Math.max(12, edges[2] - edges[1] - 2 * CELL_PAD_H);
  const xKgR = edges[3] - CELL_PAD_H;
  const xHpR = edges[4] - CELL_PAD_H;
  const xSubR = edges[5] - CELL_PAD_H;
  const xPayR = edges[6] - CELL_PAD_H;
  const xStatC = (edges[6] + edges[7]) / 2;

  const totalTagihanKotakInv = invoiceTotalTagihanKotakFromDoc(p);
  const pajakInv = Math.max(0, parseFloat(p.biayaPajak) || 0);
  const kirimInv = Math.max(0, parseFloat(p.biayaPengiriman) || 0);
  const pajakInvStr = pdfFmtPajakInvoiceValue(pajakInv);
  const invLines = getPemesananKloterLinesFromDoc(p);
  const barisPembayaranTambahan = pdfPembayaranBertahapBarisOnlyForInvoice(p);

  const orderTableCols = () => [
    { label: "No", x: xNoC, opt: { align: "center" } },
    { label: "Item", x: xItemL },
    { label: "Kg", x: xKgR, opt: { align: "right" } },
    { label: "Harga/Kg", x: xHpR, opt: { align: "right" } },
    { label: "Subtotal", x: xSubR, opt: { align: "right" } },
    { label: "Bayar", x: xPayR, opt: { align: "right" } },
    { label: "Status", x: xStatC, opt: { align: "center" } },
  ];

  const drawH = (yy) => {
    doc.setDrawColor(...INVOICE_BORDER_RGB);
    doc.setLineWidth(0.12);
    doc.line(LX, yy, RX, yy);
  };

  y += SECTION_MB * 0.2;
  y = pdfDrawRingkasanDokumenBox(doc, LX, RX, y, p, {
    compact: singlePage,
  });
  y += SECTION_MB * 0.85;

  const yPembeliBar = y;
  doc.setFillColor(...INV_GREEN_LIGHT_RGB);
  doc.setDrawColor(...INVOICE_BORDER_RGB);
  doc.setLineWidth(0.1);
  doc.rect(LX, yPembeliBar, RX - LX, BAR_H, "FD");
  doc.setFontSize(FT_SEC);
  pdfInvSetFont(doc, "bold");
  doc.setTextColor(...INV_GREEN_RGB);
  doc.text("PEMBELI", LX + CELL_PAD_H, yPembeliBar + BAR_H * 0.62);
  pdfInvSetFont(doc, "normal");
  doc.setTextColor(0, 0, 0);
  y = yPembeliBar + BAR_H + 2;
  drawH(y);
  y += CELL_PAD_V * 0.85;

  const drawBuyerRow = (label, valueRaw) => {
    doc.setFontSize(FT_BODY);
    pdfInvSetFont(doc, "bold");
    doc.setTextColor(...INV_LABEL_MUTED_RGB);
    doc.text(label, LX_LABEL, y);
    pdfInvSetFont(doc, "bold");
    doc.setTextColor(...INV_TEXT_BODY_RGB);
    const val = pdfDecodeHtmlEntities(String(valueRaw ?? "—").trim()) || "—";
    const lines = doc.splitTextToSize(val, RX - VX_VALUE - CELL_PAD_H);
    lines.forEach((ln, idx) => {
      doc.text(ln, VX_VALUE, y + idx * LH);
    });
    y += Math.max(lines.length, 1) * LH + BUYER_ROW_GAP;
  };

  drawBuyerRow("Nama", String(p.namaPembeli || "-").trim() || "-");
  drawBuyerRow("Kontak", p.kontakPembeli || "-");
  drawBuyerRow("Alamat", p.alamatPembeli || "-");
  if (p.idMasterPembeli) {
    drawBuyerRow("ID master", String(p.idMasterPembeli));
  }
  drawBuyerRow("Tipe", p.tipePemesanan || "-");
  if (p.tipePemesanan === "International" && p.negara) {
    drawBuyerRow("Negara", p.negara || "-");
  }

  y += CELL_PAD_V * 0.2;
  drawH(y);
  y += SECTION_MB * 0.85;

  const yDataBar = y;
  doc.setFillColor(...INV_GREEN_LIGHT_RGB);
  doc.setDrawColor(...INVOICE_BORDER_RGB);
  doc.setLineWidth(0.1);
  doc.rect(LX, yDataBar, RX - LX, BAR_H, "FD");
  doc.setFontSize(FT_SEC);
  pdfInvSetFont(doc, "bold");
  doc.setTextColor(...INV_GREEN_RGB);
  doc.text("DATA PEMESANAN", LX + CELL_PAD_H, yDataBar + BAR_H * 0.62);
  pdfInvSetFont(doc, "normal");
  doc.setTextColor(0, 0, 0);
  y = yDataBar + BAR_H + 2;

  y = pdfInvoiceGreenTableHeader(
    doc,
    LX,
    RX,
    y,
    HDR_H,
    orderTableCols(),
    singlePage ? 6.5 : 8,
  );

  doc.setFont(PDF_FONT, "normal");
  doc.setFontSize(FT_BODY);
  let rowIdx = 0;

  const orderTableBreakLimitY = singlePage
    ? 1e9
    : PDF_PAGE_HEIGHT_MM -
      PDF_SAFE_BOTTOM_MM -
      PDF_INVOICE_TABLE_ROW_SAFE_BOTTOM_MM;

  const continueDataPemesananTableOnNewPage = () => {
    if (singlePage) return;
    doc.addPage();
    let yy = pdfInvoiceContinuePageTopMm();
    doc.setFillColor(...INV_GREEN_LIGHT_RGB);
    doc.setDrawColor(...INVOICE_BORDER_RGB);
    doc.setLineWidth(0.1);
    const yBar = yy;
    doc.rect(LX, yBar, RX - LX, BAR_H, "FD");
    doc.setFontSize(FT_SEC);
    pdfInvSetFont(doc, "bold");
    doc.setTextColor(...INV_GREEN_RGB);
    doc.text(
      "DATA PEMESANAN (lanjutan)",
      LX + CELL_PAD_H,
      yBar + BAR_H * 0.62,
    );
    pdfInvSetFont(doc, "normal");
    doc.setTextColor(0, 0, 0);
    yy = yBar + BAR_H + 2;
    yy = pdfInvoiceGreenTableHeader(doc, LX, RX, yy, HDR_H, orderTableCols(), 8);
    doc.setFont(PDF_FONT, "normal");
    doc.setFontSize(FT_BODY);
    y = yy;
  };

  const drawPemesananRow = ({
    itemLines,
    kgStr,
    hpStr,
    subStr,
    payStr,
    statusStr,
    emphasizeUnpaid,
  }) => {
    rowIdx += 1;
    const yRowTop = y;
    const yStart = y + CELL_PAD_V;
    const nLines = Math.max(itemLines.length, 1);
    const hBlock = nLines * LH;
    const yEnd = yRowTop + CELL_PAD_V + hBlock + CELL_PAD_V;
    const yMid = yStart + hBlock * 0.5 - LH * 0.12;

    if (rowIdx % 2 === 0) {
      doc.setFillColor(...INV_ZEBRA_RGB);
      doc.rect(LX, yRowTop, RX - LX, yEnd - yRowTop, "F");
    }

    doc.setFont(PDF_FONT, "normal");
    doc.setFontSize(FT_BODY);
    if (emphasizeUnpaid) {
      doc.setTextColor(195, 40, 40);
      pdfInvSetFont(doc, "bold");
    } else {
      doc.setTextColor(...INV_TEXT_BODY_RGB);
      pdfInvSetFont(doc, "bold");
    }
    itemLines.forEach((ln, i) => {
      doc.text(ln, xItemL, yStart + i * LH);
    });

    doc.setFont("courier", emphasizeUnpaid ? "bold" : "normal");
    doc.setFontSize(FT_BODY);
    doc.text(String(rowIdx), xNoC, yMid, { align: "center" });
    doc.text(kgStr, xKgR, yMid, { align: "right" });
    doc.text(hpStr, xHpR, yMid, { align: "right" });
    doc.text(subStr, xSubR, yMid, { align: "right" });
    doc.text(payStr, xPayR, yMid, { align: "right" });

    doc.setFont(PDF_FONT, "bold");
    doc.setFontSize(FT_BODY - 0.5);
    doc.setTextColor(...INV_TEXT_BODY_RGB);
    doc.text(String(statusStr || "—"), xStatC, yMid, { align: "center" });
    doc.setFontSize(FT_BODY);

    y = yEnd;
    drawH(y);
    y += 0.5;
    doc.setTextColor(0, 0, 0);
    pdfInvSetFont(doc, "normal");
    doc.setFont(PDF_FONT, "normal");
  };

  invLines.forEach((row) => {
    const desk = `${row.tipeProduk || "-"} - ${row.jenisKopi || "-"} - ${row.prosesPengolahan || "-"}`;
    const itemLines = doc.splitTextToSize(desk, W_ITEM);
    const nLines = Math.max(itemLines.length, 1);
    const rowHApprox = CELL_PAD_V * 2 + nLines * LH + 2;
    if (y + rowHApprox > orderTableBreakLimitY) {
      continueDataPemesananTableOnNewPage();
    }
    const jumlahKg = parseFloat(row.beratKg) || 0;
    const hargaKg = parseFloat(row.hargaPerKg) || 0;
    const subtotalBaris = jumlahKg * hargaKg;
    const payK = parseFloat(row.jumlahPembayaranKloter) || 0;
    const adaPayK = Number.isFinite(payK) && payK > 0;
    const lunasK = pembayaranBarisLunasTrue(row.pembayaranKloterLunas);
    drawPemesananRow({
      itemLines,
      kgStr: pdfFmtIdNumber(jumlahKg),
      hpStr: pdfFmtIdNumber(hargaKg),
      subStr: pdfFmtIdNumber(subtotalBaris),
      payStr: adaPayK ? pdfFmtIdNumber(payK) : "—",
      statusStr: adaPayK ? (lunasK ? "Lunas" : "Belum") : "—",
      emphasizeUnpaid: adaPayK && !lunasK,
    });
  });

  /** Baris DP/termin `pembayaranBertahapBaris` tidak ditampil di tabel order — hanya di kotak «Rincian pembayaran bertahap» di bawah. */

  const statusBayar = String(p?.statusPembayaran || "").trim();
  const showBertahapRingkasan =
    statusBayar === "Pembayaran Bertahap" ||
    barisPembayaranTambahan.length > 0;
  const estimatedSummaryBlockMm =
    12 +
    LH * 3.2 +
    (showBertahapRingkasan
      ? LH * (4.5 + barisPembayaranTambahan.length * 0.92)
      : 0) +
    22;
  const pageBottom = pdfInvoicePageContentBottomMm();
  const standardOnePageInvoice =
    !singlePage && invLines.length <= PDF_INVOICE_STANDARD_ONE_PAGE_MAX_KLOTER;
  if (
    !standardOnePageInvoice &&
    y + estimatedSummaryBlockMm > pageBottom
  ) {
    doc.addPage();
    y = pdfInvoiceContinuePageTopMm();
  }

  y += 2;
  const boxL = RX - SUMMARY_BOX_W;
  const boxTop = y;
  const boxPad = CELL_PAD_H;
  let yy = boxTop + boxPad + 4;
  const innerW = SUMMARY_BOX_W - 2 * boxPad;

  yy = pdfDrawInvoiceSummaryKVRow(doc, boxL, yy, innerW, boxPad, {
    label: labelTipePajakInvoice(),
    valueStr: pajakInvStr,
    fontPt: FT_BODY,
    labelRgb: INV_LABEL_MUTED_RGB,
    valueRgb: INV_TEXT_BODY_RGB,
    dangerValue: false,
    labelBold: true,
    reserveNumMm: 34,
  });
  yy = pdfDrawInvoiceSummaryKVRow(doc, boxL, yy, innerW, boxPad, {
    label: "Pengiriman (Rp)",
    valueStr: pdfFmtIdNumber(kirimInv),
    fontPt: FT_BODY,
    labelRgb: INV_LABEL_MUTED_RGB,
    valueRgb: INV_TEXT_BODY_RGB,
    dangerValue: false,
    labelBold: true,
  });

  if (showBertahapRingkasan) {
    yy += LH * 0.08;
    doc.setDrawColor(...INVOICE_BORDER_RGB);
    doc.setLineWidth(0.1);
    doc.line(boxL + boxPad, yy, boxL + boxPad + innerW, yy);
    yy += LH * 0.38;

    const subHdrPt = FT_BODY - 0.35;
    doc.setFontSize(subHdrPt);
    pdfInvSetFont(doc, "bold");
    doc.setTextColor(...INV_GREEN_RGB);
    doc.text("Rincian pembayaran bertahap", boxL + boxPad, yy + (subHdrPt * 25.4) / 72 * 0.72);
    yy += LH * 0.58;
    pdfInvSetFont(doc, "normal");
    doc.setTextColor(0, 0, 0);

    if (barisPembayaranTambahan.length > 0) {
      const rowsSorted = barisPembayaranTambahan.slice().sort((a, b) => {
        const la = pembayaranBarisLunasTrue(a?.terminLunas) ? 1 : 0;
        const lb = pembayaranBarisLunasTrue(b?.terminLunas) ? 1 : 0;
        return la - lb;
      });
      rowsSorted.forEach((ex) => {
        const lunas = pembayaranBarisLunasTrue(ex.terminLunas);
        const jj = parseFloat(ex?.jumlahRp) || 0;
        const label = pdfBertahapRingkasanLabel(ex, lunas);
        const valStr = jj > 0 ? pdfFmtIdNumber(jj) : "—";
        const unpaidNeedPay = !lunas && jj > 0;
        yy = pdfDrawInvoiceSummaryKVRow(doc, boxL, yy, innerW, boxPad, {
          label,
          valueStr: valStr,
          fontPt: FT_BODY - 0.15,
          labelRgb: lunas ? [105, 105, 105] : INV_LABEL_MUTED_RGB,
          valueRgb: lunas ? [105, 105, 105] : INV_TEXT_BODY_RGB,
          dangerValue: unpaidNeedPay,
          labelBold: true,
        });
      });
    } else {
      yy = pdfDrawInvoiceSummaryKVRow(doc, boxL, yy, innerW, boxPad, {
        label:
          "Belum ada baris termin / nominal pada dokumen (periksa di Kelola Pemesanan)",
        valueStr: "—",
        fontPt: FT_BODY - 0.35,
        labelRgb: [115, 115, 115],
        valueRgb: [115, 115, 115],
        dangerValue: false,
        labelBold: false,
      });
    }
    yy += LH * 0.2;
  }

  const totalBandH = singlePage ? 7.2 : 8.5;
  doc.setFillColor(14, 78, 44);
  doc.setDrawColor(12, 70, 40);
  doc.setLineWidth(0.1);
  doc.rect(boxL + boxPad, yy, innerW, totalBandH, "FD");
  doc.setTextColor(255, 255, 255);
  pdfInvSetFont(doc, "bold");
  doc.setFontSize(invoiceFontPtFromPx(singlePage ? 12 : 14));
  doc.text("TOTAL TAGIHAN (Rp)", boxL + boxPad + 2, yy + totalBandH * 0.68);
  doc.setFont("courier", "bold");
  doc.text(
    pdfFmtIdNumber(totalTagihanKotakInv),
    boxL + boxPad + innerW - 2,
    yy + totalBandH * 0.68,
    { align: "right" },
  );
  doc.setFont(PDF_FONT, "normal");
  doc.setTextColor(0, 0, 0);
  pdfInvSetFont(doc, "normal");
  yy += totalBandH + boxPad;

  doc.setDrawColor(...INVOICE_BORDER_RGB);
  doc.setLineWidth(0.15);
  doc.rect(boxL, boxTop, SUMMARY_BOX_W, yy - boxTop, "S");

  const catatan = (p.catatanPemesanan && String(p.catatanPemesanan).trim()) || "";
  /** Catatan hanya di kiri; kolom kanan (≥ boxL) untuk ringkasan di atas + TTD di bawah. */
  const footColGap = FOOT_GRID_GAP;
  const catW = Math.max(52, boxL - LX - footColGap);
  const sigL = boxL + 1.2;
  const sigR = RX - CELL_PAD_H;

  /** yy = bawah kotak ringkasan; y lama masih di boxTop — wajib pakai yy agar TTD tidak menimpa PPh/pengiriman. */
  y = yy + SECTION_MB * 0.45;

  const estFootBlockMm = pdfEstimateInvoiceFooterBlockMm(
    doc,
    catatan,
    catW,
    singlePage,
    SIG_BEFORE,
  );
  if (
    !standardOnePageInvoice &&
    y + estFootBlockMm > pageBottom
  ) {
    doc.addPage();
    y = pdfInvoiceContinuePageTopMm();
  }

  y += SIG_BEFORE;
  let yFooter = y;

  const drawTtdSeller = (yTop, sigL, sigR) => {
    const xC = (sigL + sigR) / 2;
    const padIn = singlePage ? 3.5 : 5;
    const boxW = Math.max(28, sigR - sigL);
    const boxH = Math.max(
      singlePage ? 30 : 38,
      SIG_BOX_MIN_H * (singlePage ? 0.44 : 0.54),
    );
    const bTop = yTop;

    doc.setDrawColor(...INVOICE_BORDER_RGB);
    doc.setLineWidth(0.12);
    doc.roundedRect(sigL, bTop, boxW, boxH, 0.8, 0.8, "S");

    const yHormat = bTop + padIn + (singlePage ? 3.2 : 4);
    const yLine = bTop + boxH * 0.56;
    const yNama = bTop + boxH * 0.76;
    const lineInset = padIn + 2;

    doc.setFontSize(FT_BODY);
    pdfInvSetFont(doc, "normal");
    doc.setTextColor(75, 75, 75);
    doc.text("Hormat Kami,", xC, yHormat, { align: "center" });
    doc.setDrawColor(110, 110, 110);
    doc.setLineWidth(0.18);
    doc.line(sigL + lineInset, yLine, sigR - lineInset, yLine);
    doc.setDrawColor(0, 0, 0);
    doc.setLineWidth(0.1);
    pdfInvSetFont(doc, "bold");
    doc.setTextColor(...INV_GREEN_RGB);
    doc.text("Damarkandang", xC, yNama, { align: "center" });
    doc.setTextColor(0, 0, 0);
    pdfInvSetFont(doc, "normal");
    return bTop + boxH;
  };

  let yBottom = yFooter;

  if (catatan) {
    const ySigEnd = drawTtdSeller(yFooter, sigL, sigR);
    const yCatEnd = pdfDrawCatatanPemesananTable(doc, LX, yFooter, catatan, {
      width: catW,
      marginBottom: singlePage ? 2 : 3,
      forceSinglePage: singlePage,
      shrinkToFit: singlePage,
      pageBottom: pdfInvoicePageContentBottomMm(),
    });
    yBottom = Math.max(yCatEnd, ySigEnd + 4);
  } else {
    const ySigEnd = drawTtdSeller(yFooter, sigL, sigR);
    yBottom = ySigEnd + 6;
  }

  return yBottom;
}

