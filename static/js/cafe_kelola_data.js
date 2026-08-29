/* Cafe Damarkandang — kelola data master, stok, keuangan, kasir */
(function () {
  let bahanOptions = [];
  const KATEGORI_PCS = new Set(["Kopral", "Roasted", "Skincare"]);

  function el(id) {
    return document.getElementById(id);
  }

  function on(id, event, handler) {
    const node = el(id);
    if (node) node.addEventListener(event, handler);
  }

  const modalJenis = () =>
    bootstrap.Modal.getOrCreateInstance(document.getElementById("modalJenis"));
  const modalMenu = () =>
    bootstrap.Modal.getOrCreateInstance(document.getElementById("modalMenu"));

  function isJenisCairanSelected() {
    const bentuk = el("jenisBentuk");
    return !!(bentuk && bentuk.value === "cairan");
  }

  function isJenisKategoriPcs() {
    return KATEGORI_PCS.has(el("jenisKategori")?.value);
  }

  function isJenisPcsSelected() {
    if (isJenisKategoriPcs()) return true;
    return !isJenisCairanSelected() && el("jenisSatuanBerat")?.value === "pcs";
  }

  function isMenuKategoriPcs() {
    return KATEGORI_PCS.has(el("menuKategori")?.value);
  }

  function syncGramPerPcsCustom() {
    const sel = el("jenisGramPerPcs");
    const custom = el("jenisGramPerPcsCustom");
    if (!sel || !custom) return;
    const isCustom = sel.value === "custom";
    custom.classList.toggle("d-none", !isCustom);
    if (!isCustom) custom.value = "";
  }

  function getGramPerPcsValue() {
    const sel = el("jenisGramPerPcs");
    if (!sel) return 0;
    if (sel.value === "custom") {
      return parseNumberInput(el("jenisGramPerPcsCustom")?.value);
    }
    return parseNumberInput(sel.value);
  }

  function setGramPerPcsValue(gram) {
    const sel = el("jenisGramPerPcs");
    const custom = el("jenisGramPerPcsCustom");
    if (!sel) return;
    const g = String(parseInt(gram, 10) || "");
    if (["250", "500", "1000"].includes(g)) {
      sel.value = g;
      if (custom) {
        custom.classList.add("d-none");
        custom.value = "";
      }
    } else if (g) {
      sel.value = "custom";
      if (custom) {
        custom.classList.remove("d-none");
        custom.value = g;
      }
    } else {
      sel.value = "250";
      if (custom) {
        custom.classList.add("d-none");
        custom.value = "";
      }
    }
  }

  function applyJenisKategoriDefaults() {
    const kat = el("jenisKategori")?.value || "Minuman";
    const bentuk = el("jenisBentuk");
    const satuan = el("jenisSatuanBerat");
    if (KATEGORI_PCS.has(kat)) {
      if (bentuk) {
        bentuk.value = "non_cairan";
        bentuk.disabled = true;
      }
      if (satuan) {
        satuan.value = "pcs";
        satuan.disabled = true;
      }
    } else {
      if (bentuk) bentuk.disabled = false;
      if (satuan) satuan.disabled = false;
    }
  }

  function toggleJenisBentukFields() {
    if (!el("jenisBentuk")) return;
    applyJenisKategoriDefaults();
    const cairan = isJenisCairanSelected();
    const pcs = !cairan && isJenisPcsSelected();
    setBlocksVisible({
      wrapJenisCairanFields: cairan,
      wrapJenisNonCairanFields: !cairan,
      wrapJenisHargaKg: !cairan && !pcs,
      wrapJenisHargaPcs: !cairan && pcs,
    });
    setFieldsRequired(["jenisHargaPerPack", "jenisKgPerPack"], cairan);
    setFieldsRequired(["jenisHargaPerKg"], !cairan && !pcs);
    setFieldsRequired(["jenisHargaPerPcs"], !cairan && pcs);
    syncGramPerPcsCustom();
  }

  function hargaInfoJenis(row) {
    if (row.bentuk_bahan === "cairan") {
      const kg = row.kg_per_pack != null ? `${row.kg_per_pack} kg` : "-";
      const harga = row.harga_per_pack ? formatRupiah(row.harga_per_pack) : "-";
      return `${kg}/pack · ${harga}`;
    }
    if (row.satuan_berat === "pcs" || KATEGORI_PCS.has(row.kategori)) {
      const isi = row.gram_per_pcs ? `${row.gram_per_pcs}g` : "-";
      const harga = row.harga_per_pcs
        ? formatRupiah(row.harga_per_pcs)
        : "-";
      return `${isi}/pcs · ${harga}`;
    }
    return row.harga_per_kg ? `${formatRupiah(row.harga_per_kg)}/kg` : "-";
  }

  async function loadJenis() {
    const tbody = el("jenisBody");
    if (!tbody) return;
    const res = await CafeAPI.get("/jenis-bahan?per_page=100");
    tbody.innerHTML = (res.data.items || [])
      .map(
        (r) => `
      <tr><td>${r.id_jenis}</td><td>${r.nama_jenis}</td>
      <td><span class="badge bg-secondary">${r.kategori || "Minuman"}</span></td>
      <td><span class="badge ${r.bentuk_bahan === "cairan" ? "bg-info text-dark" : "bg-light text-dark border"}">${r.bentuk_bahan_label || "Non Cairan"}${r.satuan_berat === "pcs" || KATEGORI_PCS.has(r.kategori) ? " · Pcs" : r.bentuk_bahan !== "cairan" ? " · Kg" : ""}</span></td>
      <td>${hargaInfoJenis(r)}</td>
      <td>${r.deskripsi || "-"}</td>
      <td><span class="badge ${r.status === "aktif" ? "bg-success" : "bg-secondary"}">${r.status}</span></td>
      <td><button class="btn btn-sm btn-outline-primary" data-edit-jenis='${JSON.stringify(r).replace(/'/g, "&#39;")}'>Edit</button>
      <button class="btn btn-sm btn-outline-danger" data-del-jenis="${r.id_jenis}">Hapus</button></td></tr>`,
      )
      .join("");
  }

  async function loadMenu() {
    const res = await CafeAPI.get("/menu?per_page=100");
    document.getElementById("menuBody").innerHTML = (res.data.items || [])
      .map((r) => {
        const resep = (r.bahan_resep || [])
          .map((x) => {
            if (x.satuan === "pcs" || x.jumlah_pcs != null) {
              return `${x.nama_bahan} ${x.jumlah_pcs ?? x.jumlah_gram}pcs`;
            }
            return `${x.nama_bahan} ${x.jumlah_gram}g`;
          })
          .join(", ");
        const margin = formatMarginDisplay(r.biaya_modal || 0, r.harga_jual);
        return `<tr><td>${r.id_menu}</td><td>${r.nama_menu}</td><td>${r.kategori || "-"}</td>
      <td>${formatRupiah(r.biaya_modal || 0)}</td><td>${margin}</td><td>${formatRupiah(r.harga_jual)}</td>
      <td><small>${resep || "-"}</small></td><td><span class="badge ${r.status === "aktif" ? "bg-success" : "bg-secondary"}">${r.status}</span></td>
      <td><button class="btn btn-sm btn-outline-primary" data-edit-menu='${JSON.stringify(r).replace(/'/g, "&#39;")}'>Edit</button>
      <button class="btn btn-sm btn-outline-danger" data-del-menu="${r.id_menu}">Hapus</button></td></tr>`;
      })
      .join("");
  }

  async function loadBahanOptions() {
    const res = await CafeAPI.get("/bahan?active_only=1&per_page=200&light=1");
    bahanOptions = res.data.items || [];
  }

  function getBahanById(id) {
    return bahanOptions.find((b) => b.id_bahan === id) || null;
  }

  function isBahanPcs(bahan) {
    return !!(
      bahan &&
      (bahan.satuan_berat === "pcs" || KATEGORI_PCS.has(bahan.kategori))
    );
  }

  function bahanOptionsForMenu() {
    const kat = el("menuKategori")?.value || "";
    if (KATEGORI_PCS.has(kat)) {
      const exact = bahanOptions.filter((b) => b.kategori === kat);
      if (exact.length) return exact;
      // Fallback data lama: pcs tanpa kategori tersimpan
      return bahanOptions.filter((b) => isBahanPcs(b) && !b.kategori);
    }
    return bahanOptions.filter((b) => !KATEGORI_PCS.has(b.kategori));
  }

  function biayaModalDariGram(hargaPerKg, gram) {
    const kg = (Number(gram) || 0) / 1000;
    return Math.round(kg * (Number(hargaPerKg) || 0));
  }

  function biayaModalDariPcs(hargaPerPcs, pcs) {
    return Math.round((Number(pcs) || 0) * (Number(hargaPerPcs) || 0));
  }

  function hitungMarginPersen(modal, hargaJual) {
    const m = Number(modal) || 0;
    const h = Number(hargaJual) || 0;
    if (h <= 0) return 0;
    return Math.round(((h - m) / h) * 10000) / 100;
  }

  function formatMarginDisplay(modal, hargaJual) {
    const m = Number(modal) || 0;
    const h = Number(hargaJual) || 0;
    if (h <= 0) return "-";
    const margin = hitungMarginPersen(m, h);
    const text = Number.isInteger(margin) ? String(margin) : margin.toFixed(2);
    return `${text}%`;
  }

  function syncResepRowSatuan(row) {
    if (!row) return;
    const bahan = getBahanById(row.querySelector(".resep-bahan")?.value);
    const qtyInput = row.querySelector(".resep-qty");
    const satuanLabel = row.querySelector(".resep-satuan-label");
    const pcs = isBahanPcs(bahan);
    if (satuanLabel) satuanLabel.textContent = pcs ? "pcs" : "gram";
    if (qtyInput) {
      qtyInput.placeholder = pcs ? "pcs" : "gram";
      qtyInput.step = pcs ? "any" : "1";
      qtyInput.min = pcs ? "0.001" : "1";
      qtyInput.dataset.satuan = pcs ? "pcs" : "gram";
    }
  }

  function refreshResepBiaya(row) {
    if (!row) return;
    const bahan = getBahanById(row.querySelector(".resep-bahan")?.value);
    const qty = parseFloat(row.querySelector(".resep-qty")?.value) || 0;
    const elBiaya = row.querySelector(".resep-biaya");
    let biaya = 0;
    let title = "Harga bahan belum tersedia";
    if (isBahanPcs(bahan)) {
      const hargaPcs = bahan.harga_per_pcs || 0;
      biaya = biayaModalDariPcs(hargaPcs, qty);
      title = hargaPcs
        ? `${formatRupiah(hargaPcs)}/pcs × ${qty || 0} pcs`
        : title;
    } else if (bahan) {
      const hargaKg = bahan.harga_per_kg || bahan.harga_terakhir || 0;
      biaya = biayaModalDariGram(hargaKg, qty);
      title = hargaKg
        ? `${formatRupiah(hargaKg)}/kg × ${qty || 0}g`
        : title;
    }
    if (elBiaya) {
      elBiaya.value = formatRupiah(biaya);
      elBiaya.dataset.biaya = String(biaya);
      elBiaya.title = title;
    }
  }

  function recalculateMenuPricing() {
    const rows = [...document.querySelectorAll(".resep-row")];
    let totalModal = 0;
    rows.forEach((row) => {
      syncResepRowSatuan(row);
      refreshResepBiaya(row);
      totalModal +=
        parseInt(row.querySelector(".resep-biaya")?.dataset.biaya || "0", 10) ||
        0;
    });
    const harga = parseNumberInput(el("menuHarga")?.value) || 0;
    const margin = hitungMarginPersen(totalModal, harga);
    if (el("menuModal")) el("menuModal").value = formatRupiah(totalModal);
    const marginEl = el("menuMargin");
    if (marginEl) {
      marginEl.value = formatMarginDisplay(totalModal, harga);
      marginEl.classList.toggle("text-danger", totalModal > 0 && harga < totalModal);
      marginEl.classList.toggle("text-success", totalModal > 0 && harga > totalModal);
    }
    return { totalModal, margin, harga };
  }

  function qtyFromResepData(data = {}) {
    const bahan = getBahanById(data.id_bahan);
    if (isBahanPcs(bahan)) {
      if (data.jumlah_pcs != null && data.jumlah_pcs !== "") return data.jumlah_pcs;
      const gramPcs = Number(bahan.gram_per_pcs) || 0;
      if (data.jumlah_gram && gramPcs > 0) {
        return Number(data.jumlah_gram) / gramPcs;
      }
      return "";
    }
    return data.jumlah_gram || "";
  }

  function addResepRow(data = {}) {
    const wrap = document.getElementById("resepRows");
    const row = document.createElement("div");
    row.className = "row g-2 mb-2 resep-row align-items-center";
    const qtyVal = qtyFromResepData(data);
    const opts = bahanOptionsForMenu();
    const optionsHtml = opts.length
      ? opts
          .map(
            (b) =>
              `<option value="${b.id_bahan}" ${b.id_bahan === data.id_bahan ? "selected" : ""}>${b.nama_bahan} (${formatRupiah(b.harga_tampil || b.harga_per_pcs || b.harga_per_kg || b.harga_terakhir || 0)}${b.harga_tampil_suffix || (isBahanPcs(b) ? "/pcs" : "/kg")})</option>`,
          )
          .join("")
      : '<option value="">Belum ada bahan untuk kategori ini</option>';
    row.innerHTML = `<div class="col-12 col-md-5">
        <label class="form-label d-md-none small mb-1">Bahan</label>
        <select class="form-select resep-bahan" required>${optionsHtml}</select>
      </div>
      <div class="col-6 col-md-2">
        <label class="form-label d-md-none small mb-1">Jumlah</label>
        <div class="input-group input-group-sm">
          <input type="number" class="form-control resep-qty" min="1" step="1" placeholder="gram" value="${qtyVal}" required />
          <span class="input-group-text resep-satuan-label">gram</span>
        </div>
      </div>
      <div class="col-5 col-md-4">
        <label class="form-label d-md-none small mb-1">Biaya Modal</label>
        <input type="text" class="form-control resep-biaya" readonly value="Rp0" />
      </div>
      <div class="col-1 col-md-1 d-flex align-items-end align-items-md-center">
        <button type="button" class="btn btn-outline-danger btn-sm w-100 btn-del-resep" aria-label="Hapus bahan">&times;</button>
      </div>`;
    wrap.appendChild(row);
    syncResepRowSatuan(row);
    refreshResepBiaya(row);
    recalculateMenuPricing();
  }

  async function fillMenuNamaSelect(selectedId = "", selectedName = "") {
    const kat = el("menuKategori")?.value || "";
    const sel = el("menuNamaSelect");
    if (!sel) return;
    const q = new URLSearchParams({
      active_only: "1",
      per_page: "200",
      light: "1",
      kategori: kat,
    });
    const res = await CafeAPI.get("/bahan?" + q.toString());
    const items = res.data.items || [];
    // Fallback: jika belum ada kategori tersimpan di bahan, filter dari options pcs
    const list = items.length ? items : bahanOptionsForMenu();
    sel.innerHTML =
      '<option value="">Pilih kemasan dari Kelola Bahan...</option>' +
      (list.length
        ? list
            .map((b) => {
              const label = `${b.nama_bahan || b.nama_jenis}${b.gram_per_pcs ? " · " + b.gram_per_pcs + "g" : ""} (${formatRupiah(b.harga_per_pcs || b.harga_tampil || 0)}/pcs)`;
              const selected =
                b.id_bahan === selectedId ||
                b.nama_bahan === selectedName ||
                b.nama_jenis === selectedName
                  ? "selected"
                  : "";
              return `<option value="${b.id_bahan}" data-nama="${(b.nama_bahan || b.nama_jenis || "").replace(/"/g, "&quot;")}" ${selected}>${label}</option>`;
            })
            .join("")
        : `<option value="" disabled>Belum ada bahan kategori ${kat} — daftarkan dulu di Kelola Bahan</option>`);
  }

  async function syncMenuNamaMode(prefIllNama = "", preferId = "") {
    const pcs = isMenuKategoriPcs();
    const input = el("menuNama");
    const select = el("menuNamaSelect");
    if (!input || !select) return;
    input.classList.toggle("d-none", pcs);
    select.classList.toggle("d-none", !pcs);
    input.required = !pcs;
    select.required = pcs;
    if (pcs) {
      await fillMenuNamaSelect(preferId, prefIllNama);
      if (preferId) select.value = preferId;
      const opt = select.selectedOptions[0];
      if (opt && opt.dataset.nama) input.value = opt.dataset.nama;
      // Auto resep 1 pcs dari bahan terpilih
      applyPcsProductResep(select.value);
    } else {
      if (prefIllNama) input.value = prefIllNama;
    }
  }

  function applyPcsProductResep(idBahan) {
    if (!idBahan || !isMenuKategoriPcs()) return;
    const wrap = document.getElementById("resepRows");
    if (!wrap) return;
    wrap.innerHTML = "";
    addResepRow({ id_bahan: idBahan, jumlah_pcs: 1 });
  }

  on("btnAddJenis", "click", () => {
    if (el("jenisEditId")) el("jenisEditId").value = "";
    el("formJenis")?.reset();
    const bentuk = el("jenisBentuk");
    if (bentuk) {
      bentuk.value = "non_cairan";
      bentuk.disabled = false;
    }
    if (el("jenisKategori")) el("jenisKategori").value = "Minuman";
    if (el("jenisSatuanBerat")) {
      el("jenisSatuanBerat").value = "kg";
      el("jenisSatuanBerat").disabled = false;
    }
    setGramPerPcsValue(250);
    toggleJenisBentukFields();
    modalJenis().show();
  });

  on("jenisBentuk", "change", toggleJenisBentukFields);
  on("jenisSatuanBerat", "change", toggleJenisBentukFields);
  on("jenisKategori", "change", toggleJenisBentukFields);
  on("jenisGramPerPcs", "change", syncGramPerPcsCustom);

  on("btnAddMenu", "click", async () => {
    await loadBahanOptions();
    document.getElementById("menuEditId").value = "";
    document.getElementById("formMenu").reset();
    document.getElementById("menuKategori").value = "Minuman";
    if (el("menuHarga")) el("menuHarga").value = "";
    if (el("menuMargin")) el("menuMargin").value = "0%";
    document.getElementById("resepRows").innerHTML = "";
    await syncMenuNamaMode();
    if (!isMenuKategoriPcs()) {
      if (bahanOptions.length) addResepRow();
      else recalculateMenuPricing();
    }
    modalMenu().show();
  });

  on("menuKategori", "change", async () => {
    await loadBahanOptions();
    document.getElementById("resepRows").innerHTML = "";
    await syncMenuNamaMode();
    if (!isMenuKategoriPcs()) {
      if (bahanOptions.length) addResepRow();
      else recalculateMenuPricing();
    }
  });

  on("menuNamaSelect", "change", () => {
    const sel = el("menuNamaSelect");
    const opt = sel?.selectedOptions?.[0];
    if (opt?.dataset?.nama && el("menuNama")) el("menuNama").value = opt.dataset.nama;
    applyPcsProductResep(sel?.value || "");
  });

  document
    .getElementById("btnAddResepRow")
    .addEventListener("click", () => addResepRow());
  document.getElementById("resepRows").addEventListener("click", (e) => {
    if (e.target.closest(".btn-del-resep")) {
      e.target.closest(".resep-row").remove();
      recalculateMenuPricing();
    }
  });
  document.getElementById("resepRows").addEventListener("change", (e) => {
    if (e.target.closest(".resep-bahan") || e.target.closest(".resep-qty"))
      recalculateMenuPricing();
  });
  document.getElementById("resepRows").addEventListener("input", (e) => {
    if (e.target.closest(".resep-qty")) recalculateMenuPricing();
  });
  on("menuHarga", "input", recalculateMenuPricing);
  on("menuHarga", "change", recalculateMenuPricing);

  on("formJenis", "submit", async (e) => {
    e.preventDefault();
    const payload = {
      nama_jenis: el("jenisNama")?.value.trim() || "",
      kategori: el("jenisKategori")?.value || "Minuman",
      bentuk_bahan: el("jenisBentuk")?.value || "non_cairan",
      deskripsi: el("jenisDeskripsi")?.value.trim() || "",
      status: el("jenisStatus")?.value || "aktif",
    };
    try {
      if (isJenisCairanSelected()) {
        payload.harga_per_pack = parseNumberInput(
          el("jenisHargaPerPack")?.value,
        );
        payload.kg_per_pack = parseNumberInput(el("jenisKgPerPack")?.value);
        if (payload.harga_per_pack <= 0)
          throw new Error("Harga per pack wajib diisi");
        if (payload.kg_per_pack <= 0)
          throw new Error("Berat kg per pack wajib diisi");
      } else if (isJenisPcsSelected()) {
        payload.satuan_berat = "pcs";
        payload.harga_per_pcs = parseNumberInput(el("jenisHargaPerPcs")?.value);
        payload.gram_per_pcs = getGramPerPcsValue();
        if (payload.harga_per_pcs <= 0)
          throw new Error("Harga per pcs wajib diisi");
        if (payload.gram_per_pcs <= 0)
          throw new Error("Isi per pcs (gram) wajib diisi");
      } else {
        payload.satuan_berat = "kg";
        payload.harga_per_kg = parseNumberInput(el("jenisHargaPerKg")?.value);
        if (payload.harga_per_kg <= 0)
          throw new Error("Harga per kg wajib diisi");
      }
      const id = el("jenisEditId")?.value || "";
      if (id) await CafeAPI.put("/jenis-bahan/" + id, payload);
      else await CafeAPI.post("/jenis-bahan", payload);
      showToast("Jenis bahan disimpan");
      modalJenis().hide();
      loadJenis();
    } catch (err) {
      showToast(err.message, "danger");
    }
  });

  document.getElementById("formMenu").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const pricing = recalculateMenuPricing();
      let namaProduk = menuNama.value.trim();
      if (isMenuKategoriPcs()) {
        const opt = el("menuNamaSelect")?.selectedOptions?.[0];
        namaProduk = (opt?.dataset?.nama || namaProduk || "").trim();
        if (!el("menuNamaSelect")?.value)
          throw new Error("Pilih nama/kemasan produk dari dropdown");
      }
      const resep = [...document.querySelectorAll(".resep-row")].map((row) => {
        const idBahan = row.querySelector(".resep-bahan").value;
        const bahan = getBahanById(idBahan);
        const qty = parseFloat(row.querySelector(".resep-qty").value) || 0;
        if (isBahanPcs(bahan) || isMenuKategoriPcs()) {
          return { id_bahan: idBahan, jumlah_pcs: qty, satuan: "pcs" };
        }
        return { id_bahan: idBahan, jumlah_gram: Math.round(qty), satuan: "gram" };
      });
      if (!resep.length)
        throw new Error("Resep bahan wajib diisi minimal 1 baris");
      if (pricing.harga <= 0)
        throw new Error("Harga jual wajib diisi");
      const payload = {
        nama_menu: namaProduk,
        kategori: menuKategori.value.trim(),
        harga_jual: pricing.harga,
        bahan_resep: resep,
        status: menuStatus.value,
      };
      const id = menuEditId.value;
      if (id) await CafeAPI.put("/menu/" + id, payload);
      else await CafeAPI.post("/menu", payload);
      showToast("Produk disimpan");
      modalMenu().hide();
      loadMenu();
    } catch (err) {
      showToast(err.message, "danger");
    }
  });

  on("jenisBody", "click", async (e) => {
    const edit = e.target.closest("[data-edit-jenis]");
    const del = e.target.closest("[data-del-jenis]");
    if (edit) {
      const r = JSON.parse(edit.getAttribute("data-edit-jenis"));
      if (el("jenisEditId")) el("jenisEditId").value = r.id_jenis;
      if (el("jenisNama")) el("jenisNama").value = r.nama_jenis;
      if (el("jenisKategori"))
        el("jenisKategori").value = r.kategori || "Minuman";
      if (el("jenisBentuk"))
        el("jenisBentuk").value = r.bentuk_bahan || "non_cairan";
      if (el("jenisSatuanBerat"))
        el("jenisSatuanBerat").value = r.satuan_berat || "kg";
      if (el("jenisHargaPerPack"))
        el("jenisHargaPerPack").value = r.harga_per_pack || "";
      if (el("jenisKgPerPack"))
        el("jenisKgPerPack").value = r.kg_per_pack || "";
      if (el("jenisHargaPerKg"))
        el("jenisHargaPerKg").value = r.harga_per_kg || "";
      if (el("jenisHargaPerPcs"))
        el("jenisHargaPerPcs").value = r.harga_per_pcs || "";
      setGramPerPcsValue(r.gram_per_pcs || 250);
      if (el("jenisDeskripsi")) el("jenisDeskripsi").value = r.deskripsi || "";
      if (el("jenisStatus")) el("jenisStatus").value = r.status;
      toggleJenisBentukFields();
      modalJenis().show();
    }
    if (del) {
      if (confirm("Hapus jenis bahan?")) {
        await CafeAPI.delete("/jenis-bahan/" + del.dataset.delJenis);
        loadJenis();
      }
    }
  });

  document.getElementById("menuBody").addEventListener("click", async (e) => {
    const edit = e.target.closest("[data-edit-menu]");
    const del = e.target.closest("[data-del-menu]");
    if (edit) {
      await loadBahanOptions();
      const r = JSON.parse(edit.getAttribute("data-edit-menu"));
      menuEditId.value = r.id_menu;
      menuNama.value = r.nama_menu;
      const kat = r.kategori || "Minuman";
      menuKategori.value = KATEGORI_PCS.has(kat) || ["Makanan", "Minuman"].includes(kat)
        ? kat
        : "Minuman";
      menuStatus.value = r.status;
      if (el("menuHarga"))
        el("menuHarga").value = r.harga_jual != null ? r.harga_jual : "";
      resepRows.innerHTML = "";
      const firstResep = (r.bahan_resep || [])[0] || {};
      await syncMenuNamaMode(r.nama_menu, firstResep.id_bahan || "");
      if (!isMenuKategoriPcs()) {
        (r.bahan_resep || []).forEach((x) => addResepRow(x));
        if (!(r.bahan_resep || []).length) recalculateMenuPricing();
      } else if ((r.bahan_resep || []).length) {
        resepRows.innerHTML = "";
        (r.bahan_resep || []).forEach((x) => addResepRow(x));
      }
      modalMenu().show();
    }
    if (del) {
      if (confirm("Hapus produk?")) {
        await CafeAPI.delete("/menu/" + del.dataset.delMenu);
        loadMenu();
      }
    }
  });

  const modalPembayaran = () =>
    bootstrap.Modal.getOrCreateInstance(
      document.getElementById("modalPembayaran"),
    );

  async function loadPembayaran() {
    const res = await CafeAPI.get("/data-pembayaran");
    document.getElementById("pembayaranBody").innerHTML = (res.data.items || [])
      .map(
        (r) => `
      <tr><td>${r.id_pembayaran}</td><td>${r.metode.toUpperCase()}</td><td>${r.label || "-"}</td>
      <td>${r.nomor_rekening || "-"}${r.nama_rekening ? "<br><small>" + r.nama_rekening + "</small>" : ""}</td>
      <td>${r.gambar_url ? '<img src="' + r.gambar_url + '" height="40" />' : "-"}</td>
      <td><span class="badge ${r.status === "aktif" ? "bg-success" : "bg-secondary"}">${r.status}</span></td>
      <td><button class="btn btn-sm btn-outline-primary" data-edit-pay='${JSON.stringify(r).replace(/'/g, "&#39;")}'>Edit</button>
      <button class="btn btn-sm btn-outline-danger" data-del-pay="${r.id_pembayaran}">Hapus</button></td></tr>`,
      )
      .join("");
  }

  async function uploadPayImage(file) {
    if (!file) return payGambarUrl.value || "";
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/data-pembayaran/upload", {
      method: "POST",
      body: fd,
      credentials: "include",
    });
    const json = await res.json();
    if (!res.ok || !json.success)
      throw new Error(json.error || json.message || "Upload gagal");
    return json.data.gambar_url;
  }

  document.getElementById("btnAddPembayaran").addEventListener("click", () => {
    pembayaranEditId.value = "";
    formPembayaran.reset();
    payGambarUrl.value = "";
    payGambarPreview.innerHTML = "";
    payMetode.disabled = false;
    modalPembayaran().show();
  });

  payGambarFile.addEventListener("change", () => {
    const f = payGambarFile.files[0];
    payGambarPreview.innerHTML = f
      ? `<img src="${URL.createObjectURL(f)}" height="80" />`
      : "";
  });

  formPembayaran.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const gambar = await uploadPayImage(payGambarFile.files[0]);
      const payload = {
        metode: payMetode.value,
        label: payLabel.value.trim(),
        nomor_rekening: payRekening.value.trim(),
        nama_rekening: payNamaRek.value.trim(),
        gambar_url: gambar || payGambarUrl.value.trim(),
        keterangan: payKeterangan.value.trim(),
        status: payStatus.value,
      };
      const id = pembayaranEditId.value;
      if (id) await CafeAPI.put("/data-pembayaran/" + id, payload);
      else await CafeAPI.post("/data-pembayaran", payload);
      showToast("Data pembayaran disimpan");
      modalPembayaran().hide();
      loadPembayaran();
    } catch (err) {
      showToast(err.message, "danger");
    }
  });

  document
    .getElementById("pembayaranBody")
    .addEventListener("click", async (e) => {
      const edit = e.target.closest("[data-edit-pay]");
      const del = e.target.closest("[data-del-pay]");
      if (edit) {
        const r = JSON.parse(edit.getAttribute("data-edit-pay"));
        pembayaranEditId.value = r.id_pembayaran;
        payMetode.value = r.metode;
        payMetode.disabled = true;
        payLabel.value = r.label || "";
        payRekening.value = r.nomor_rekening || "";
        payNamaRek.value = r.nama_rekening || "";
        payGambarUrl.value = r.gambar_url || "";
        payKeterangan.value = r.keterangan || "";
        payStatus.value = r.status || "aktif";
        payGambarPreview.innerHTML = r.gambar_url
          ? `<img src="${r.gambar_url}" height="80" />`
          : "";
        modalPembayaran().show();
      }
      if (del && confirm("Hapus data pembayaran?")) {
        await CafeAPI.delete("/data-pembayaran/" + del.dataset.delPay);
        loadPembayaran();
      }
    });

  const modalJenisKeu = () =>
    bootstrap.Modal.getOrCreateInstance(
      document.getElementById("modalJenisKeu"),
    );

  function renderJenisKeuRow(r) {
    const tipeBadge =
      r.tipe === "otomatis"
        ? '<span class="badge bg-info text-dark">Otomatis</span>'
        : '<span class="badge bg-secondary">Manual</span>';
    const canEdit = r.tipe !== "otomatis";
    const actions = canEdit
      ? `<button class="btn btn-sm btn-outline-primary" data-edit-jk='${JSON.stringify(r).replace(/'/g, "&#39;")}'>Edit</button>
         <button class="btn btn-sm btn-outline-danger" data-del-jk="${r.id_jenis}">Hapus</button>`
      : '<small class="text-muted">Sistem</small>';
    return `<tr><td>${r.id_jenis}</td><td>${r.nama_jenis}</td><td>${tipeBadge}</td><td>${r.deskripsi || "-"}</td>
      <td><span class="badge ${r.status === "aktif" ? "bg-success" : "bg-secondary"}">${r.status}</span></td><td>${actions}</td></tr>`;
  }

  async function loadJenisKeuangan() {
    const [pg, pm] = await Promise.all([
      CafeAPI.get("/jenis-pengeluaran"),
      CafeAPI.get("/jenis-pemasukan"),
    ]);
    document.getElementById("jenisPgBody").innerHTML = (pg.data.items || [])
      .map(renderJenisKeuRow)
      .join("");
    document.getElementById("jenisPmBody").innerHTML = (pm.data.items || [])
      .map(renderJenisKeuRow)
      .join("");
  }

  function openJenisKeuModal(kind, data = null) {
    jenisKeuTipeData.value = kind;
    modalJenisKeuTitle.textContent =
      kind === "pg" ? "Jenis Pengeluaran" : "Jenis Pemasukan";
    if (data) {
      jenisKeuEditId.value = data.id_jenis;
      jenisKeuNama.value = data.nama_jenis;
      jenisKeuNama.readOnly = data.tipe === "otomatis";
      jenisKeuDeskripsi.value = data.deskripsi || "";
      jenisKeuStatus.value = data.status || "aktif";
    } else {
      jenisKeuEditId.value = "";
      formJenisKeu.reset();
      jenisKeuNama.readOnly = false;
    }
    modalJenisKeu().show();
  }

  document
    .getElementById("btnAddJenisPg")
    .addEventListener("click", () => openJenisKeuModal("pg"));
  document
    .getElementById("btnAddJenisPm")
    .addEventListener("click", () => openJenisKeuModal("pm"));

  formJenisKeu.addEventListener("submit", async (e) => {
    e.preventDefault();
    const kind = jenisKeuTipeData.value;
    const base = kind === "pg" ? "/jenis-pengeluaran" : "/jenis-pemasukan";
    const payload = {
      nama_jenis: jenisKeuNama.value.trim(),
      deskripsi: jenisKeuDeskripsi.value.trim(),
      status: jenisKeuStatus.value,
    };
    const id = jenisKeuEditId.value;
    try {
      if (id) await CafeAPI.put(base + "/" + id, payload);
      else await CafeAPI.post(base, payload);
      showToast("Jenis keuangan disimpan");
      modalJenisKeu().hide();
      loadJenisKeuangan();
    } catch (err) {
      showToast(err.message, "danger");
    }
  });

  function bindJenisKeuTable(bodyId) {
    document.getElementById(bodyId).addEventListener("click", async (e) => {
      const edit = e.target.closest("[data-edit-jk]");
      const del = e.target.closest("[data-del-jk]");
      const kind = bodyId === "jenisPgBody" ? "pg" : "pm";
      const base = kind === "pg" ? "/jenis-pengeluaran" : "/jenis-pemasukan";
      if (edit)
        openJenisKeuModal(kind, JSON.parse(edit.getAttribute("data-edit-jk")));
      if (del && confirm("Hapus jenis ini?")) {
        await CafeAPI.delete(base + "/" + del.dataset.delJk);
        loadJenisKeuangan();
      }
    });
  }
  bindJenisKeuTable("jenisPgBody");
  bindJenisKeuTable("jenisPmBody");

  toggleJenisBentukFields();
  loadJenis();
  loadMenu();
  loadPembayaran();
  loadJenisKeuangan();
})();
