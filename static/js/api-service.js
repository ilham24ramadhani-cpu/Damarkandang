/**
 * API Service Layer
 * Menyediakan interface untuk komunikasi dengan backend MongoDB
 * BACKEND-FIRST (MongoDB ONLY) - NO localStorage fallback
 * Semua data WAJIB tersimpan di MongoDB via Flask API
 */

// Badge color helpers untuk jenis kopi & kualitas (selalu tersedia)
window.getJenisKopiBadgeClass = function (jenisKopi) {
  const j = (jenisKopi || "").toLowerCase();
  if (j === "arabica" || j === "arabika") return "bg-primary";
  if (j === "robusta") return "bg-info";
  return "bg-secondary";
};
window.getKualitasBadgeClass = function (kualitas) {
  const k = (kualitas || "").toLowerCase();
  if (k === "premium") return "bg-success";
  if (k === "grade a") return "bg-info";
  if (k === "grade b") return "bg-warning text-dark";
  if (k === "grade c") return "bg-danger";
  return "bg-secondary";
};
/**
 * Warna badge proses pengolahan per idProses master (1–8, mod 8): 1 Anaerob, 2 HSN, 3 Natural,
 * 4 Washed, 5 Carbonic Wethull, 6 Kismis, 7 Komersil, 8 Cherry. Tanpa id: hash nama.
 * @param {string} proses - label / nama proses (tampilan)
 * @param {number|string|null|undefined} idProses - id numerik dari dataProses jika ada
 */
window.getProsesPengolahanBadgeClass = function (proses, idProses) {
  /* Selaras kelas .process-1 … .process-8 di kelola_produksi.css / kelola_laporan.css */
  const palette = [
    "process-1",
    "process-2",
    "process-3",
    "process-4",
    "process-5",
    "process-6",
    "process-7",
    "process-8",
  ];
  const n =
    idProses != null && String(idProses).trim() !== ""
      ? Number(idProses)
      : NaN;
  let idx;
  if (!Number.isNaN(n) && n >= 1) {
    idx = (Math.floor(n) - 1) % palette.length;
  } else {
    // Fallback konsisten untuk data legacy tanpa idProses: map via nama proses.
    // Ini mencegah warna berubah karena perbedaan kecil teks (spasi/kasus).
    const s = String(proses || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();

    if (s.includes("anaerob")) return "process-1";
    if (s.includes("hsn")) return "process-2";
    if (s.includes("natural")) return "process-3";
    if (s.includes("washed") || s.includes("full wash")) return "process-4";
    if (s.includes("carbonic") && s.includes("wethull")) return "process-5";
    if (s.includes("kismis")) return "process-6";
    if (s.includes("komersil") || s.includes("komersial")) return "process-7";
    if (s.includes("cherry")) return "process-8";

    let h = 0;
    for (let i = 0; i < s.length; i++) {
      h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
    }
    idx = Math.abs(h) % palette.length;
  }
  return palette[idx];
};
window.getStatusTahapanBadgeClass = function (tahapan) {
  const t = (tahapan || "").toLowerCase();
  if (t.includes("sortasi") && !t.includes("hand")) return "bg-info";
  if (t.includes("fermentasi")) return "bg-secondary";
  if (t.includes("pulping")) return "text-bg-dark";
  if (t.includes("pencucian")) return "bg-primary";
  if (t.includes("pengeringan")) return "bg-warning text-dark";
  if (t.includes("hulling") || t.includes("pengupasan")) return "bg-dark";
  if (t.includes("hand") && t.includes("sortasi")) return "bg-info text-dark";
  if (t.includes("roasting")) return "bg-danger";
  if (t.includes("grinding")) return "bg-light text-dark";
  if (t.includes("pengemasan")) return "bg-success";
  return "bg-secondary";
};

/** Urutan kanonik tahapan (sinkron dengan backend `get_produksi`). Roasting legacy sebelum Pengemasan. */
window.URUTAN_TAHAPAN_PRODUKSI_KANON = [
  "Sortasi",
  "Pengeringan Awal Pertama",
  "Fermentasi",
  "Pulping",
  "Pencucian",
  "Pengeringan Awal",
  "Fermentasi 2",
  "Pulping 2",
  "Pengeringan Akhir",
  "Hulling",
  "Hand Sortasi",
  "Grinding",
  "Roasting",
  "Pengemasan",
];

const _TAHAPAN_LABEL_KE_KUNCI_SORT = {
  "Sortasi Cherry atau Buah Kopi": "Sortasi",
  "Sortasi Buah": "Sortasi",
  "Pengeringan Awal Pertama (Para - Para)": "Pengeringan Awal Pertama",
  "Pengeringan Awal (Para - Para)": "Pengeringan Awal",
  "Pengeringan Awal kedua (Para - Para)": "Pengeringan Awal",
  "Pengeringan Akhir (Pengeringan Lantai)": "Pengeringan Akhir",
  "Pengupasan Kulit Tanduk (Hulling) Pertama": "Pulping 2",
  "Pengupasan Kulit Tanduk (Hulling) Kedua": "Hulling",
  "Pengupasan Kulit Tanduk (Hulling)": "Hulling",
  "Hand Sortasi atau Sortasi Biji Kopi": "Hand Sortasi",
  Fermentasi: "Fermentasi",
  Pulping: "Pulping",
  Pencucian: "Pencucian",
  "Pengeringan Awal Pertama": "Pengeringan Awal Pertama",
  "Pengeringan Awal": "Pengeringan Awal",
  "Fermentasi 2": "Fermentasi 2",
  "Pulping 2": "Pulping 2",
  "Pengeringan Akhir": "Pengeringan Akhir",
  Grinding: "Grinding",
  Pengemasan: "Pengemasan",
  Roasting: "Roasting",
  Hulling: "Hulling",
  Sortasi: "Sortasi",
  "Hand Sortasi": "Hand Sortasi",
};
for (let _ti = 0; _ti < window.URUTAN_TAHAPAN_PRODUKSI_KANON.length; _ti++) {
  const _tn = window.URUTAN_TAHAPAN_PRODUKSI_KANON[_ti];
  if (!Object.prototype.hasOwnProperty.call(_TAHAPAN_LABEL_KE_KUNCI_SORT, _tn)) {
    _TAHAPAN_LABEL_KE_KUNCI_SORT[_tn] = _tn;
  }
}
const _TAHAPAN_SORT_KEYS_BY_LEN = Object.keys(_TAHAPAN_LABEL_KE_KUNCI_SORT).sort(
  (a, b) => b.length - a.length,
);

/**
 * Urutkan array dokumen produksi: indeks tahapan naik, lalu idProduksi.
 * Memakai substring terpanjang dulu agar "Pulping 2" tidak tertangkap sebagai "Pulping".
 */
window.sortProduksiDocumentsByTahapanThenId = function (arr) {
  if (!Array.isArray(arr)) return arr;
  const urutan = window.URUTAN_TAHAPAN_PRODUKSI_KANON;
  const mapCanon = _TAHAPAN_LABEL_KE_KUNCI_SORT;
  const keysByLen = _TAHAPAN_SORT_KEYS_BY_LEN;
  function keKunci(st) {
    const s = String(st || "").trim();
    if (!s) return "";
    if (Object.prototype.hasOwnProperty.call(mapCanon, s)) return mapCanon[s];
    for (let i = 0; i < keysByLen.length; i++) {
      const k = keysByLen[i];
      if (s.includes(k)) return mapCanon[k];
    }
    return urutan.includes(s) ? s : "";
  }
  function indeks(st) {
    const k = keKunci(st);
    const ix = urutan.indexOf(k);
    return ix === -1 ? 999 : ix;
  }
  return [...arr].sort((a, b) => {
    const c = indeks(a && a.statusTahapan) - indeks(b && b.statusTahapan);
    if (c !== 0) return c;
    return String(a && a.idProduksi ? a.idProduksi : "").localeCompare(
      String(b && b.idProduksi ? b.idProduksi : ""),
      "id",
      { numeric: true },
    );
  });
};

// Prevent duplicate execution - jika sudah dieksekusi, langsung return
// Pemesanan & Ordering wajib dicek untuk halaman kelola pemesanan
if (window.API && window.API.Bahan && window.API.Produksi && window.API.Users && window.API.Pemesanan && window.API.Ordering) {
  console.log("⚠️ api-service.js already loaded, skipping re-execution");
  // Dispatch event anyway in case modules are waiting
  window.dispatchEvent(
    new CustomEvent("APIReady", { detail: { API: window.API } }),
  );
} else {
  // Initialize window.API early to prevent race conditions
  window.API = window.API || {};

  // Use same origin as current page to ensure cookies are sent correctly
  // Check if already declared to avoid duplicate declaration errors
  if (typeof window.API_BASE_URL === "undefined") {
    window.API_BASE_URL = window.location.origin
      ? `${window.location.origin}/api`
      : "http://localhost:5002/api";
  }

  // Use window property directly - no const/let to avoid redeclaration errors
  var API_BASE_URL = (function () {
    if (typeof window.API_BASE_URL !== "undefined") {
      return window.API_BASE_URL;
    }
    // Fallback (should not reach here)
    return window.location.origin
      ? `${window.location.origin}/api`
      : "http://localhost:5002/api";
  })();

  /**
   * URL untuk membuka PDF hasil POST /api/laporan/upload di tab browser.
   * Mengutamakan field `url` (path absolut dari root) + origin halaman saat ini,
   * supaya host/port sama dengan yang dipakai pengguna (menghindari fullUrl server
   * yang salah, misalnya 127.0.0.1 saat akses lewat IP LAN).
   */
  window.resolveUploadedLaporanPdfUrl = function (result) {
    if (!result || typeof result !== "object") return "";
    const origin =
      typeof window.location.origin === "string" && window.location.origin
        ? window.location.origin
        : "";
    const relRaw = result.url != null ? String(result.url).trim() : "";
    if (relRaw.startsWith("/") && origin) {
      return `${origin}${relRaw}`;
    }
    if (relRaw && !/^https?:\/\//i.test(relRaw) && origin) {
      const path = relRaw.startsWith("/") ? relRaw : `/${relRaw}`;
      return `${origin}${path}`;
    }
    const fn = result.filename != null ? String(result.filename).trim() : "";
    if (fn && !/[\\/]/.test(fn) && fn.toLowerCase().endsWith(".pdf") && origin) {
      return `${origin}/static/laporan/${encodeURIComponent(fn)}`;
    }
    const full = result.fullUrl != null ? String(result.fullUrl).trim() : "";
    if (/^https?:\/\//i.test(full)) return full;
    return "";
  };

  /**
   * Isi tab yang sudah dibuka (mis. about:blank dari klik) dengan PDF.
   * Fetch + blob lebih andal daripada location.replace ke PDF di beberapa browser.
   */
  window.openPdfInTabFromUrl = async function (tab, absoluteUrl) {
    if (!tab || tab.closed || !absoluteUrl) return false;
    try {
      const res = await fetch(absoluteUrl, {
        credentials: "include",
        redirect: "follow",
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      tab.location.href = blobUrl;
      setTimeout(function () {
        try {
          URL.revokeObjectURL(blobUrl);
        } catch (e) {
          /* ignore */
        }
      }, 300000);
      return true;
    } catch (e) {
      console.warn("openPdfInTabFromUrl:", e);
      try {
        tab.location.href = absoluteUrl;
        return true;
      } catch (e2) {
        return false;
      }
    }
  };

  let backendAvailable = false;

  // Check backend availability on load
  (async function checkBackend() {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      if (response.ok) {
        backendAvailable = true;
        console.log("✅ Backend MongoDB tersedia");
      } else {
        console.warn("⚠️ Backend tidak merespon dengan baik");
      }
    } catch (error) {
      console.warn(
        "⚠️ Backend tidak tersedia saat ini. Pastikan backend Flask aktif untuk menggunakan sistem.",
      );
      console.warn("Error:", error.message);
    }
  })();

  // Generic API call function
  // Default timeout 25 detik supaya request tidak hang tanpa feedback (mis.
  // Railway cold start). Bisa dinaikkan via opsi 4: `apiCall(endpoint, method,
  // data, { timeoutMs })`.
  async function apiCall(endpoint, method = "GET", data = null, opts = {}) {
    // Always try API first, even if backendAvailable is false
    // This allows recovery if backend comes online later

    const timeoutMs = Number.isFinite(opts && opts.timeoutMs)
      ? Math.max(1000, opts.timeoutMs)
      : 25000;
    const controller =
      typeof AbortController !== "undefined" ? new AbortController() : null;
    const timeoutId = controller
      ? setTimeout(() => {
          try {
            controller.abort();
          } catch (_) {
            /* ignore */
          }
        }, timeoutMs)
      : null;

    const options = {
      method: method,
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include", // Important for cookies
      signal: controller ? controller.signal : undefined,
    };

    if (data && (method === "POST" || method === "PUT")) {
      options.body = JSON.stringify(data);
    }

    const tStart =
      typeof performance !== "undefined" && performance.now
        ? performance.now()
        : Date.now();
    try {
      console.log(
        `🔵 API Call: ${method} ${API_BASE_URL}${endpoint}`,
        data ? "(with data)" : "",
      );
      const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
      if (timeoutId) clearTimeout(timeoutId);

      if (response.ok) {
        // Mark backend as available on successful response
        backendAvailable = true;
        const result = await response.json();
        const dt = (
          (typeof performance !== "undefined" && performance.now
            ? performance.now()
            : Date.now()) - tStart
        ).toFixed(0);
        if (dt > 1500) {
          console.warn(
            `⏱️ API Slow: ${method} ${endpoint} (${dt} ms) — kemungkinan server cold-start / koneksi lambat`,
          );
        } else {
          console.log(`✅ API Success: ${method} ${endpoint} (${dt} ms)`);
        }
        return result;
      } else {
        // Try to parse error as JSON first
        let errorData = null;
        let errorText = "";
        try {
          errorText = await response.text();
          errorData = JSON.parse(errorText);
        } catch (e) {
          // If not JSON, use text as is
          errorData = { error: errorText || response.statusText };
        }

        console.error(
          `❌ API Error: ${method} ${endpoint} - Status ${response.status}`,
          errorData,
        );

        // Create error object with response data
        const error = new Error(
          errorData.error || errorText || response.statusText,
        );
        error.status = response.status;
        error.data = errorData;
        throw error;
      }
    } catch (error) {
      if (timeoutId) clearTimeout(timeoutId);
      // Aborted karena timeout → kasih pesan yang jelas
      if (error && (error.name === "AbortError" || error.code === 20)) {
        const dt = (
          (typeof performance !== "undefined" && performance.now
            ? performance.now()
            : Date.now()) - tStart
        ).toFixed(0);
        console.error(
          `⏱️ API Timeout: ${method} ${endpoint} (>${timeoutMs} ms, real ${dt} ms) — server tidak merespons.`,
        );
        const tErr = new Error(
          `Server lambat / tidak merespons dalam ${(timeoutMs / 1000).toFixed(0)} detik. Cek koneksi atau coba lagi.`,
        );
        tErr.code = "TIMEOUT";
        backendAvailable = false;
        throw tErr;
      }
      console.error(`❌ API Call Failed: ${method} ${endpoint}`, error);
      // Mark backend as unavailable on network error
      if (
        error.message &&
        (error.message.includes("Failed to fetch") ||
          error.message.includes("NetworkError"))
      ) {
        backendAvailable = false;
        console.warn("⚠️ Backend marked as unavailable");
      }
      throw error;
    }
  }

  // ==================== PRODUKSI API ====================
  // ==================== PRODUKSI API (MONGODB ONLY - NO localStorage fallback) ====================
  const ProduksiAPI = {
    async getAll() {
      // MONGODB ONLY - NO FALLBACK
      const data = await apiCall("/produksi");
      if (!Array.isArray(data)) return data;
      return typeof window.sortProduksiDocumentsByTahapanThenId === "function"
        ? window.sortProduksiDocumentsByTahapanThenId(data)
        : data;
    },

    async getNextId() {
      // Get next auto-generated idProduksi (PRD-YYYYMM-XXXX) for preview
      const res = await apiCall("/produksi/next-id");
      return res?.idProduksi || null;
    },

    async getById(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/produksi/${id}`);
    },

    async create(data) {
      // MONGODB ONLY - NO FALLBACK
      // Backend will generate id and idProduksi automatically
      // Frontend should NOT send 'id' or 'idProduksi' (backend generates idProduksi)
      const dataWithoutId = { ...data };
      delete dataWithoutId.id;
      delete dataWithoutId.idProduksi; // Backend auto-generates idProduksi
      return await apiCall("/produksi", "POST", dataWithoutId);
    },

    async update(id, data) {
      // MONGODB ONLY - NO FALLBACK
      const dataWithoutId = { ...data };
      delete dataWithoutId.id; // Remove id from update data
      return await apiCall(`/produksi/${id}`, "PUT", dataWithoutId);
    },

    async uploadFotoTahapan(file) {
      const fd = new FormData();
      fd.append("file", file);
      const response = await fetch(`${API_BASE_URL}/produksi/upload-foto-tahapan`, {
        method: "POST",
        body: fd,
        credentials: "include",
      });
      let data = null;
      try {
        data = await response.json();
      } catch (e) {
        data = {};
      }
      if (!response.ok) {
        const err = new Error((data && data.error) || "Upload foto gagal");
        err.data = data;
        err.status = response.status;
        throw err;
      }
      return data;
    },

    async delete(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/produksi/${id}`, "DELETE");
    },

    async getPengemasan() {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall("/produksi/pengemasan");
    },

    async getSisa(idProduksi) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/produksi/${idProduksi}/sisa`);
    },
  };

  // ==================== HASIL PRODUKSI API ====================
  // ==================== HASIL PRODUKSI API (MONGODB ONLY - NO localStorage fallback) ====================
  const HasilProduksiAPI = {
    async getAll() {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall("/hasil-produksi");
    },

    async getById(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/hasil-produksi/${id}`);
    },

    async create(data) {
      // MONGODB ONLY - NO FALLBACK
      // Backend will generate ID automatically via get_next_id('hasilProduksi')
      // Frontend should NOT send 'id' field
      const dataWithoutId = { ...data };
      delete dataWithoutId.id; // Remove id if present (backend will generate)
      return await apiCall("/hasil-produksi", "POST", dataWithoutId);
    },

    async update(id, data) {
      // MONGODB ONLY - NO FALLBACK
      const dataWithoutId = { ...data };
      delete dataWithoutId.id; // Remove id from update data
      return await apiCall(`/hasil-produksi/${id}`, "PUT", dataWithoutId);
    },

    async delete(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/hasil-produksi/${id}`, "DELETE");
    },

    async getByProduksi(idProduksi) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/hasil-produksi/produksi/${idProduksi}`);
    },
  };

  // ==================== BAHAN API ====================
  // ==================== BAHAN API (MONGODB ONLY - NO localStorage fallback) ====================
  const BahanAPI = {
    async getAll() {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall("/bahan-produksi");
    },

    async getById(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/bahan-produksi/${id}`);
    },

    async create(data) {
      // MONGODB ONLY - NO FALLBACK
      // Backend will generate ID automatically via get_next_id('bahan')
      // Frontend should NOT send 'id' field
      const dataWithoutId = { ...data };
      delete dataWithoutId.id; // Remove id if present (backend will generate)
      return await apiCall("/bahan-produksi", "POST", dataWithoutId);
    },

    async update(id, data) {
      // MONGODB ONLY - NO FALLBACK
      const dataWithoutId = { ...data };
      delete dataWithoutId.id; // Remove id from update data
      return await apiCall(`/bahan-produksi/${id}`, "PUT", dataWithoutId);
    },

    async delete(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/bahan-produksi/${id}`, "DELETE");
    },

    async getSisa(idBahan, prosesPengolahan) {
      // MONGODB ONLY — untuk bahan dengan prosesBahan, query ?proses= wajib
      let path = `/bahan-produksi/sisa/${encodeURIComponent(idBahan)}`;
      if (prosesPengolahan != null && String(prosesPengolahan).trim() !== "") {
        path += `?proses=${encodeURIComponent(String(prosesPengolahan).trim())}`;
      }
      return await apiCall(path);
    },

    /** Bahan yang boleh dipilih untuk produksi: sesuai proses, belum dipakai produksi lain, sisa > 0 */
    async getUntukProduksi(prosesPengolahan, idProduksi) {
      const q = new URLSearchParams();
      q.set("proses", String(prosesPengolahan || "").trim());
      if (idProduksi) q.set("idProduksi", String(idProduksi).trim());
      return await apiCall(`/bahan-produksi/untuk-produksi?${q.toString()}`);
    },

    async getNextId() {
      // Get next auto-generated idBahan (BHN001, BHN002, ...)
      const res = await apiCall("/bahan-produksi/next-id");
      return res?.idBahan || null;
    },

    /**
     * Legacy: backend tidak lagi mengubah prosesPengolahan pada produksi dari master bahan.
     * Tetap ada agar kode lama tidak error; respons biasanya { skipped: true }.
     */
    async syncProduksiProses(bahanDocId) {
      return await apiCall(
        `/bahan-produksi/${encodeURIComponent(bahanDocId)}/sync-produksi-proses`,
        "POST",
        {},
      );
    },
  };

  // ==================== PEMASOK API (MONGODB ONLY - NO localStorage fallback) ====================
  const PemasokAPI = {
    async getAll() {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall("/pemasok");
    },

    async getById(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/pemasok/${id}`);
    },

    async create(data) {
      // MONGODB ONLY - NO FALLBACK
      // NOTE: Backend will generate ID automatically via get_next_id('pemasok')
      // Frontend should NOT send 'id' field
      const dataWithoutId = { ...data };
      delete dataWithoutId.id; // Remove id if present (backend will generate)
      return await apiCall("/pemasok", "POST", dataWithoutId);
    },

    async update(id, data) {
      // MONGODB ONLY - NO FALLBACK
      const dataWithoutId = { ...data };
      delete dataWithoutId.id; // Remove id from update data
      return await apiCall(`/pemasok/${id}`, "PUT", dataWithoutId);
    },

    async delete(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/pemasok/${id}`, "DELETE");
    },
  };

  // ==================== PEMBELI API (MASTER PEMBELI — MONGODB ONLY) ====================
  const PembeliAPI = {
    async getAll() {
      return await apiCall("/pembeli");
    },

    async getById(id) {
      return await apiCall(`/pembeli/${encodeURIComponent(id)}`);
    },

    async create(data) {
      const payload = { ...data };
      delete payload.id;
      return await apiCall("/pembeli", "POST", payload);
    },

    async update(id, data) {
      const payload = { ...data };
      delete payload.id;
      return await apiCall(`/pembeli/${encodeURIComponent(id)}`, "PUT", payload);
    },

    async delete(id) {
      return await apiCall(`/pembeli/${encodeURIComponent(id)}`, "DELETE");
    },
  };

  // ==================== STOK API (MONGODB ONLY - NO localStorage fallback) ====================
  const StokAPI = {
    async getAll(params = {}) {
      const q = new URLSearchParams();
      if (params.tipeProduk) q.set("tipeProduk", params.tipeProduk);
      if (params.tanggalPengemasan) q.set("tanggalPengemasan", params.tanggalPengemasan);
      const query = q.toString();
      const endpoint = query ? `/stok?${query}` : "/stok";
      const data = await apiCall(endpoint);
      if (Array.isArray(data)) {
        return { rows: data, ringkasan: null };
      }
      if (data && Array.isArray(data.rows)) {
        return { rows: data.rows, ringkasan: data.ringkasan || null };
      }
      return { rows: [], ringkasan: null };
    },
    async getFilterOptions() {
      return await apiCall("/stok/filter-options");
    },
    async getBahan() {
      return await apiCall("/stok/bahan");
    },
  };

  // ==================== MASTER DATA API (MONGODB ONLY - NO localStorage fallback) ====================
  function createMasterDataAPI(collectionName) {
    return {
      async getAll() {
        // MONGODB ONLY - NO FALLBACK
        return await apiCall(`/${collectionName}`);
      },

      async getById(id) {
        // MONGODB ONLY - NO FALLBACK
        return await apiCall(`/${collectionName}/${id}`);
      },

      async create(data) {
        // MONGODB ONLY - NO FALLBACK
        // NOTE: Backend will generate ID automatically via get_next_id()
        // Frontend should NOT send 'id' field
        const dataWithoutId = { ...data };
        delete dataWithoutId.id; // Remove id if present (backend will generate)
        return await apiCall(`/${collectionName}`, "POST", dataWithoutId);
      },

      async update(id, data) {
        // MONGODB ONLY - NO FALLBACK
        const dataWithoutId = { ...data };
        delete dataWithoutId.id; // Remove id from update data
        return await apiCall(`/${collectionName}/${id}`, "PUT", dataWithoutId);
      },

      async delete(id) {
        // MONGODB ONLY - NO FALLBACK
        return await apiCall(`/${collectionName}/${id}`, "DELETE");
      },
    };
  }

  const MasterDataAPI = {
    jenisKopi: createMasterDataAPI("dataJenisKopi"),
    varietas: createMasterDataAPI("dataVarietas"),
    proses: createMasterDataAPI("dataProses"),
    roasting: createMasterDataAPI("dataRoasting"),
    kemasan: createMasterDataAPI("dataKemasan"),
    produk: createMasterDataAPI("dataProduk"),
  };

  // ==================== USERS API ====================
  // ==================== USERS API (MONGODB ONLY - NO localStorage fallback) ====================
  const UsersAPI = {
    async getAll() {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall("/users");
    },

    async getById(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/users/${id}`);
    },

    async create(data) {
      // MONGODB ONLY - NO FALLBACK
      // NOTE: Backend will generate ID automatically via get_next_id('users')
      // Frontend should NOT send 'id' field
      const dataWithoutId = { ...data };
      delete dataWithoutId.id; // Remove id if present (backend will generate)
      return await apiCall("/users", "POST", dataWithoutId);
    },

    async update(id, data) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/users/${id}`, "PUT", data);
    },

    async delete(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/users/${id}`, "DELETE");
    },
  };

  // ==================== SANITASI API ====================
  // ==================== SANITASI API (MONGODB ONLY - NO localStorage fallback) ====================
  const SanitasiAPI = {
    async getAll(excludeFotos = false) {
      // MONGODB ONLY - NO FALLBACK
      // excludeFotos: set to true to exclude large foto data for list view
      const url = excludeFotos ? "/sanitasi?exclude_fotos=true" : "/sanitasi";
      return await apiCall(url);
    },

    async getById(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/sanitasi/${id}`);
    },

    async create(data) {
      // MONGODB ONLY - NO FALLBACK
      // Backend will generate ID automatically via get_next_id('sanitasi')
      // Frontend should NOT send 'id' field
      const dataWithoutId = { ...data };
      delete dataWithoutId.id; // Remove id if present (backend will generate)
      return await apiCall("/sanitasi", "POST", dataWithoutId);
    },

    async update(id, data) {
      // MONGODB ONLY - NO FALLBACK
      const dataWithoutId = { ...data };
      delete dataWithoutId.id; // Remove id from update data
      return await apiCall(`/sanitasi/${id}`, "PUT", dataWithoutId);
    },

    async delete(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/sanitasi/${id}`, "DELETE");
    },
  };

  // ==================== KEUANGAN API (MONGODB ONLY - NO localStorage fallback) ====================
  const KeuanganAPI = {
    async getAll() {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall("/keuangan");
    },

    async getById(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/keuangan/${id}`);
    },

    async create(data) {
      // MONGODB ONLY - NO FALLBACK
      // NOTE: Backend will generate ID automatically via get_next_id('keuangan')
      // Frontend should NOT send 'id' field
      const dataWithoutId = { ...data };
      delete dataWithoutId.id; // Remove id if present (backend will generate)
      return await apiCall("/keuangan", "POST", dataWithoutId);
    },

    async update(id, data) {
      // MONGODB ONLY - NO FALLBACK
      const dataWithoutId = { ...data };
      delete dataWithoutId.id; // Remove id from update data
      return await apiCall(`/keuangan/${id}`, "PUT", dataWithoutId);
    },

    async delete(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/keuangan/${id}`, "DELETE");
    },
  };

  // ==================== SETTINGS API (MONGODB ONLY - NO localStorage fallback) ====================
  const SettingsAPI = {
    async get(userId) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/settings?userId=${userId}`);
    },

    async save(data) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall("/settings", "POST", data);
    },
  };

  // ==================== AUTH API ====================
  const AuthAPI = {
    async login(username, password, role) {
      try {
        return await apiCall("/auth/login", "POST", {
          username: username,
          password: password,
          role: role,
        });
      } catch (error) {
        throw error;
      }
    },
  };

  // ==================== LAPORAN PDF API (MONGODB ONLY - NO localStorage fallback) ====================
  const LaporanAPI = {
    /**
     * Upload PDF laporan ke backend
     * @param {string} pdfData - Base64 encoded PDF data (dengan atau tanpa data: prefix)
     * @param {string} type - Tipe laporan ('hasil-produksi', 'produksi', 'data-kemasan', dll)
     * @param {string|number} id - ID item (hasil produksi, produksi, dll)
     * @returns {Promise<{success: boolean, url: string, filename: string}>}
     */
    async uploadPdf(pdfData, type, id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall("/laporan/upload", "POST", {
        pdfData: pdfData,
        type: type,
        id: String(id), // Convert to string for consistency
      });
    },

    /**
     * List semua PDF laporan
     * @param {string} type - Filter by type (optional)
     * @param {string|number} id - Filter by item ID (optional)
     * @returns {Promise<Array>}
     */
    async list(type = null, id = null) {
      // MONGODB ONLY - NO FALLBACK
      let endpoint = "/laporan/list";
      const params = [];
      if (type) params.push(`type=${encodeURIComponent(type)}`);
      if (id) params.push(`id=${encodeURIComponent(String(id))}`);
      if (params.length > 0) endpoint += "?" + params.join("&");
      return await apiCall(endpoint);
    },
  };

  // ==================== PEMESANAN API (MONGODB ONLY - NO localStorage fallback) ====================
  const PemesananAPI = {
    async getAll() {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall("/pemesanan");
    },

    async getById(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/pemesanan/${id}`);
    },

    async create(data) {
      // MONGODB ONLY - NO FALLBACK
      // Backend will generate ID automatically via get_next_id('pemesanan')
      const dataWithoutId = { ...data };
      delete dataWithoutId.id;
      return await apiCall("/pemesanan", "POST", dataWithoutId);
    },

    async update(id, data) {
      // MONGODB ONLY - NO FALLBACK
      const dataWithoutId = { ...data };
      delete dataWithoutId.id;
      return await apiCall(`/pemesanan/${id}`, "PUT", dataWithoutId);
    },

    async delete(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/pemesanan/${id}`, "DELETE");
    },

    async getStok() {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall("/pemesanan/stok");
    },
  };

  // ==================== ORDERING API (MONGODB ONLY - NO localStorage fallback) ====================
  const OrderingAPI = {
    async getAll() {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall("/ordering");
    },

    async getById(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/ordering/${id}`);
    },

    async create(data) {
      // DEPRECATED: Gunakan proses() untuk mengurangi stok
      // MONGODB ONLY - NO FALLBACK
      // Backend will generate ID automatically via get_next_id('ordering')
      const dataWithoutId = { ...data };
      delete dataWithoutId.id;
      return await apiCall("/ordering", "POST", dataWithoutId);
    },

    async proses(data) {
      // PROSES ORDERING - SATU-SATUNYA METHOD YANG MENGURANGI STOK
      // MONGODB ONLY - NO FALLBACK
      // Endpoint ini adalah titik eksekusi gudang yang mengurangi stok secara nyata
      const dataWithoutId = { ...data };
      delete dataWithoutId.id;
      return await apiCall("/ordering/proses", "POST", dataWithoutId);
    },

    async update(id, data) {
      // MONGODB ONLY - NO FALLBACK
      const dataWithoutId = { ...data };
      delete dataWithoutId.id;
      return await apiCall(`/ordering/${id}`, "PUT", dataWithoutId);
    },

    async delete(id) {
      // MONGODB ONLY - NO FALLBACK
      return await apiCall(`/ordering/${id}`, "DELETE");
    },
  };

  // Export for use in other scripts
  // Initialize window.API if not exists (prevent overwrite)
  if (!window.API) {
    window.API = {};
  }

  // Register all API modules
  window.API.Produksi = ProduksiAPI;
  window.API.HasilProduksi = HasilProduksiAPI;
  window.API.Bahan = BahanAPI;
  window.API.Pemasok = PemasokAPI;
  window.API.Pembeli = PembeliAPI;
  window.API.Stok = StokAPI;
  window.API.MasterData = MasterDataAPI;
  window.API.Users = UsersAPI;
  window.API.Keuangan = KeuanganAPI;
  window.API.Sanitasi = SanitasiAPI;
  window.API.Settings = SettingsAPI;
  window.API.Auth = AuthAPI;
  window.API.Laporan = LaporanAPI;
  window.API.Pemesanan = PemesananAPI;
  window.API.Ordering = OrderingAPI;
  
  // ==================== NOTIFICATION SYSTEM ====================
  /**
   * Menampilkan notifikasi untuk aktivitas CRUD
   * @param {string} type - Jenis operasi: 'create', 'update', 'delete'
   * @param {string} module - Nama modul: 'Pengguna', 'Bahan', 'Produksi', 'Pemesanan', 'Sanitasi'
   * @param {string} status - Status: 'success' atau 'error'
   * @param {string} customMessage - Pesan custom (opsional)
   */
  window.showNotification = function(type, module, status = 'success', customMessage = null) {
    // Hapus notifikasi sebelumnya jika ada
    const existingNotifications = document.querySelectorAll('.crud-notification');
    existingNotifications.forEach(n => {
      n.classList.remove('show');
      setTimeout(() => n.remove(), 300);
    });

    // Mapping pesan berdasarkan type dan module
    const messages = {
      create: {
        Pengguna: 'Pengguna berhasil ditambahkan',
        Bahan: 'Bahan berhasil ditambahkan',
        Produksi: 'Produksi berhasil ditambahkan',
        Pemesanan: 'Pemesanan berhasil ditambahkan',
        Sanitasi: 'Data sanitasi berhasil ditambahkan'
      },
      update: {
        Pengguna: 'Pengguna berhasil diperbarui',
        Bahan: 'Bahan berhasil diperbarui',
        Produksi: 'Produksi berhasil diperbarui',
        Pemesanan: 'Pemesanan berhasil diperbarui',
        Sanitasi: 'Data sanitasi berhasil diperbarui'
      },
      delete: {
        Pengguna: 'Pengguna berhasil dihapus',
        Bahan: 'Bahan berhasil dihapus',
        Produksi: 'Produksi berhasil dihapus',
        Pemesanan: 'Pemesanan berhasil dihapus',
        Sanitasi: 'Data sanitasi berhasil dihapus'
      }
    };

    const message = customMessage || (messages[type] && messages[type][module]) || 'Operasi berhasil';
    const alertClass = status === 'success' ? 'alert-success' : 'alert-danger';
    const icon = status === 'success' ? 'bi-check-circle' : 'bi-exclamation-triangle';

    // Buat elemen notifikasi
    const notification = document.createElement('div');
    notification.className = `alert ${alertClass} alert-dismissible fade show position-fixed crud-notification`;
    notification.style.cssText = 'top: 100px; right: 20px; z-index: 9999; min-width: 300px; max-width: 400px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);';
    notification.innerHTML = `
      <i class="bi ${icon} me-2"></i>${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;

    document.body.appendChild(notification);

    // Auto-hide setelah 4 detik
    setTimeout(() => {
      if (notification.parentNode) {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
      }
    }, 4000);
  };

  window.API.isBackendAvailable = () => backendAvailable;

  // Make backendAvailable accessible globally
  window.backendAvailable = () => backendAvailable;

  // Log API registration for debugging
  console.log("✅ window.API registered:", {
    Bahan: !!window.API.Bahan,
    Produksi: !!window.API.Produksi,
    HasilProduksi: !!window.API.HasilProduksi,
    Pemasok: !!window.API.Pemasok,
    Sanitasi: !!window.API.Sanitasi,
    Keuangan: !!window.API.Keuangan,
    Users: !!window.API.Users,
    MasterData: !!window.API.MasterData,
    Settings: !!window.API.Settings,
    Auth: !!window.API.Auth,
    Laporan: !!window.API.Laporan,
    Pemesanan: !!window.API.Pemesanan,
    Ordering: !!window.API.Ordering,
  });

  // VERIFY API is properly registered
  if (window.API.Bahan) {
    console.log("✅ API.Bahan loaded:", {
      getAll: typeof window.API.Bahan.getAll === "function",
      getById: typeof window.API.Bahan.getById === "function",
      create: typeof window.API.Bahan.create === "function",
      update: typeof window.API.Bahan.update === "function",
      delete: typeof window.API.Bahan.delete === "function",
      getSisa: typeof window.API.Bahan.getSisa === "function",
    });
    console.log("✅ API.Bahan methods:", Object.keys(window.API.Bahan));
  } else {
    console.error("❌ API.Bahan is NOT registered in window.API!");
  }

  if (window.API.Sanitasi) {
    console.log("✅ API.Sanitasi loaded:", {
      getAll: typeof window.API.Sanitasi.getAll === "function",
      getById: typeof window.API.Sanitasi.getById === "function",
      create: typeof window.API.Sanitasi.create === "function",
      update: typeof window.API.Sanitasi.update === "function",
      delete: typeof window.API.Sanitasi.delete === "function",
    });
    console.log("✅ API.Sanitasi methods:", Object.keys(window.API.Sanitasi));
  } else {
    console.error("❌ API.Sanitasi is NOT registered in window.API!");
  }

  // VERIFY Users API is properly registered
  if (window.API.Users) {
    console.log("✅ API.Users loaded:", {
      getAll: typeof window.API.Users.getAll === "function",
      getById: typeof window.API.Users.getById === "function",
      create: typeof window.API.Users.create === "function",
      update: typeof window.API.Users.update === "function",
      delete: typeof window.API.Users.delete === "function",
    });
    console.log("✅ API.Users methods:", Object.keys(window.API.Users));
  } else {
    console.error("❌ API.Users is NOT registered in window.API!");
    console.error("Available APIs:", Object.keys(window.API || {}));
  }

  // VERIFY MasterData API is properly registered
  if (window.API.MasterData) {
    console.log("✅ API.MasterData loaded:", {
      produk: !!window.API.MasterData.produk,
      proses: !!window.API.MasterData.proses,
      jenisKopi: !!window.API.MasterData.jenisKopi,
      varietas: !!window.API.MasterData.varietas,
      roasting: !!window.API.MasterData.roasting,
      kemasan: !!window.API.MasterData.kemasan,
    });
    if (window.API.MasterData.produk) {
      console.log(
        "✅ API.MasterData.produk methods:",
        Object.keys(window.API.MasterData.produk),
      );
      console.log(
        "✅ API.MasterData.produk.getAll:",
        typeof window.API.MasterData.produk.getAll === "function",
      );
    }
  } else {
    console.error("❌ API.MasterData is NOT registered in window.API!");
    console.error("Available APIs:", Object.keys(window.API || {}));
  }

  // Dispatch custom event to notify that API is ready
  window.dispatchEvent(
    new CustomEvent("APIReady", { detail: { API: window.API } }),
  );
  console.log("🚀 API Ready event dispatched - window.API is now available");
}

// End of api-service.js execution guard
