(function () {
  let page = 1;
  const perPage = 10;
  let deleteId = null;
  let allBahan = [];
  let jenisById = new Map();
  const ADD_KG_FIELDS = ["idJenis", "jumlahMasuk"];
  const ADD_PCS_FIELDS = ["idJenis", "jumlahPcs"];
  const ADD_CAIRAN_FIELDS = ["idJenis", "jumlahPack"];
  const modal = bootstrap.Modal.getOrCreateInstance(
    document.getElementById("modalForm"),
  );
  const modalDelete = bootstrap.Modal.getOrCreateInstance(
    document.getElementById("modalDelete"),
  );

  function getSelectedJenis() {
    const id = document.getElementById("idJenis").value;
    return jenisById.get(id);
  }

  function isCairanMode() {
    const jenis = getSelectedJenis();
    return !!(jenis && jenis.bentuk_bahan === "cairan");
  }

  function isPcsMode() {
    const jenis = getSelectedJenis();
    return !!(jenis && jenis.bentuk_bahan !== "cairan" && jenis.satuan_berat === "pcs");
  }

  function hargaLabel(row) {
    if (row.satuan_berat === "pcs" && row.harga_per_pcs) {
      const isi = row.gram_per_pcs ? ` (${row.gram_per_pcs}g)` : "";
      return `${formatRupiah(row.harga_per_pcs)}/pcs${isi}`;
    }
    return `${formatRupiah(row.harga_per_kg || row.harga_terakhir)}/kg`;
  }

  function setAddMode(isAdd) {
    setBlocksVisible({
      wrapJenisBaru: isAdd,
      wrapJenisEdit: !isAdd,
      wrapStokMasuk: isAdd,
      wrapStokEdit: !isAdd,
      wrapHargaPerKg: false,
    });
    if (isAdd) updateInputMode();
    else {
      setBlocksVisible({
        wrapStokMasukNonCairan: false,
        wrapStokMasukPcs: false,
        wrapStokMasukCairan: false,
      });
      setFieldsRequired(ADD_KG_FIELDS, false);
      setFieldsRequired(ADD_PCS_FIELDS, false);
      setFieldsRequired(ADD_CAIRAN_FIELDS, false);
    }
    document.getElementById("modalTitle").textContent = isAdd
      ? "Tambah Bahan"
      : "Edit Bahan";
  }

  function updateInputMode() {
    const cairan = isCairanMode();
    const pcs = !cairan && isPcsMode();
    const j = getSelectedJenis();
    setBlocksVisible({
      wrapStokMasukNonCairan: !cairan && !pcs,
      wrapStokMasukPcs: pcs,
      wrapStokMasukCairan: cairan,
      wrapHargaPerKg: false,
    });
    setFieldsRequired(ADD_KG_FIELDS, !cairan && !pcs);
    setFieldsRequired(ADD_PCS_FIELDS, pcs);
    setFieldsRequired(ADD_CAIRAN_FIELDS, cairan);
    if (cairan) {
      document.getElementById("infoKgPerPack").textContent =
        `${j?.kg_per_pack || 0} kg/pack`;
      document.getElementById("infoHargaPerPack").textContent = formatRupiah(
        j?.harga_per_pack || 0,
      );
    } else if (pcs && j) {
      document.getElementById("infoGramPerPcs").textContent =
        `${j.gram_per_pcs || 0} gram/pcs`;
      document.getElementById("infoHargaPerPcs").textContent = formatRupiah(
        j.harga_per_pcs || 0,
      );
    } else if (j) {
      document.getElementById("infoHargaPerKg").textContent = formatRupiah(
        j.harga_per_kg || 0,
      );
      document.getElementById("infoHargaSuffix").textContent = "/kg";
    }
    updatePreviewMasuk();
  }

  async function loadJenisOptions() {
    const [jenisRes, bahanRes] = await Promise.all([
      CafeAPI.get("/jenis-bahan?active_only=1&per_page=200"),
      CafeAPI.get("/bahan?active_only=1&per_page=500&light=1"),
    ]);
    allBahan = bahanRes.data.items || [];
    jenisById = new Map(
      (jenisRes.data.items || []).map((j) => [j.id_jenis, j]),
    );
    const bahanByJenis = new Map(allBahan.map((b) => [b.id_jenis, b]));
    const sel = document.getElementById("idJenis");
    sel.innerHTML = '<option value="">Pilih jenis bahan...</option>';
    (jenisRes.data.items || []).forEach((j) => {
      let tag = "";
      if (j.bentuk_bahan === "cairan") tag = " [Cairan]";
      else if (j.satuan_berat === "pcs" || ["Kopral", "Roasted", "Skincare"].includes(j.kategori))
        tag = ` [${j.kategori || "Pcs"}]`;
      else tag = j.kategori ? ` [${j.kategori}]` : " [Kg]";
      const suffix = bahanByJenis.has(j.id_jenis) ? " — tambah stok" : "";
      sel.innerHTML += `<option value="${j.id_jenis}">${j.nama_jenis}${tag}${suffix}</option>`;
    });
    updateInputMode();
  }

  function stokLabel(row) {
    const gram = formatGram(row.stok_gram);
    if (row.satuan_berat === "pcs" && row.gram_per_pcs > 0) {
      const pcs = Math.round((Number(row.stok_gram) || 0) / row.gram_per_pcs * 100) / 100;
      return `${pcs} pcs <small class="text-muted">(${gram})</small>`;
    }
    return gram;
  }

  async function loadData() {
    const search = document.getElementById("searchInput").value.trim();
    const status = document.getElementById("statusFilter").value || "aktif";
    const q = new URLSearchParams({ page, per_page: perPage, search, status });
    const res = await CafeAPI.get("/bahan?" + q);
    const tbody = document.getElementById("tableBody");
    tbody.innerHTML = "";
    (res.data.items || []).forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><code>${row.id_bahan}</code></td>
        <td><strong>${row.nama_jenis || row.nama_bahan}</strong></td>
        <td><span class="badge bg-secondary">${row.kategori || "-"}</span></td>
        <td>${stokLabel(row)}</td>
        <td>${hargaLabel(row)}</td>
        <td>${formatRupiah(row.total_pengeluaran || 0)}</td>
        <td><span class="badge ${stokBadgeClass(row.stok_status)}">${row.stok_status_label}</span></td>
        <td>
          <button class="btn btn-sm btn-outline-primary btn-edit" data-id="${row.id_bahan}"><i class="bi bi-pencil"></i></button>
          <button class="btn btn-sm btn-outline-danger btn-del" data-id="${row.id_bahan}"><i class="bi bi-trash"></i></button>
        </td>`;
      tbody.appendChild(tr);
    });
    renderPagination(
      document.getElementById("pagination"),
      page,
      res.data.total,
      perPage,
      (p) => {
        page = p;
        loadData();
      },
    );
  }

  function updatePreviewMasuk() {
    if (isCairanMode()) {
      const j = getSelectedJenis();
      const packs = parseNumberInput(
        document.getElementById("jumlahPack").value,
      );
      const gram = Math.round(packs * (j?.kg_per_pack || 0) * 1000);
      const total = Math.round(packs * (j?.harga_per_pack || 0));
      document.getElementById("previewGramCairan").textContent =
        formatGram(gram);
      document.getElementById("previewTotalCairan").textContent =
        formatRupiah(total);
      return;
    }
    if (isPcsMode()) {
      const j = getSelectedJenis();
      const pcs = parseNumberInput(document.getElementById("jumlahPcs").value);
      const gram = Math.round(pcs * (j?.gram_per_pcs || 0));
      const total = Math.round(pcs * (j?.harga_per_pcs || 0));
      document.getElementById("previewGramPcs").textContent = formatGram(gram);
      document.getElementById("previewTotalPcs").textContent =
        formatRupiah(total);
      if (j) {
        document.getElementById("infoGramPerPcs").textContent =
          `${j.gram_per_pcs || 0} gram/pcs`;
        document.getElementById("infoHargaPerPcs").textContent = formatRupiah(
          j.harga_per_pcs || 0,
        );
      }
      return;
    }
    const j = getSelectedJenis();
    const jumlah = parseNumberInput(
      document.getElementById("jumlahMasuk").value,
    );
    const satuan = document.getElementById("satuanMasuk").value;
    const hargaKg = j?.harga_per_kg || 0;
    const gram =
      satuan === "kg" ? Math.round(jumlah * 1000) : Math.round(jumlah);
    const kg = gram / 1000;
    const total = Math.round(kg * hargaKg);
    document.getElementById("previewGramMasuk").textContent = formatGram(gram);
    document.getElementById("previewTotalMasuk").textContent =
      formatRupiah(total);
    if (j) {
      document.getElementById("infoHargaPerKg").textContent =
        formatRupiah(hargaKg);
      document.getElementById("infoHargaSuffix").textContent = "/kg";
    }
  }

  function resetForm() {
    document.getElementById("editId").value = "";
    document.getElementById("jumlahMasuk").value = "";
    document.getElementById("jumlahPack").value = "";
    document.getElementById("jumlahPcs").value = "";
    document.getElementById("satuanMasuk").value = "kg";
    document.getElementById("status").value = "aktif";
    setAddMode(true);
    updatePreviewMasuk();
    loadJenisOptions();
  }

  document
    .querySelector('[data-bs-target="#modalForm"]')
    .addEventListener("click", resetForm);
  document
    .getElementById("idJenis")
    .addEventListener("change", updateInputMode);
  ["jumlahMasuk", "satuanMasuk", "jumlahPack", "jumlahPcs"].forEach((id) => {
    const node = document.getElementById(id);
    if (!node) return;
    node.addEventListener("input", updatePreviewMasuk);
    node.addEventListener("change", updatePreviewMasuk);
  });
  document.getElementById("searchInput").addEventListener(
    "input",
    debounce(() => {
      page = 1;
      loadData();
    }, 300),
  );
  document.getElementById("statusFilter").addEventListener("change", () => {
    page = 1;
    loadData();
  });

  document.getElementById("tableBody").addEventListener("click", async (e) => {
    const editBtn = e.target.closest(".btn-edit");
    const delBtn = e.target.closest(".btn-del");
    if (editBtn) {
      const res = await CafeAPI.get("/bahan/" + editBtn.dataset.id);
      const row = res.data;
      document.getElementById("editId").value = row.id_bahan;
      document.getElementById("jenisLabel").value =
        row.nama_jenis || row.nama_bahan;
      document.getElementById("stokSaatIni").value = formatGram(row.stok_gram);
      document.getElementById("status").value = row.status;
      setAddMode(false);
      modal.show();
    }
    if (delBtn) {
      deleteId = delBtn.dataset.id;
      const row = (await CafeAPI.get("/bahan/" + deleteId)).data;
      document.getElementById("deleteLabel").textContent =
        row.nama_jenis || row.nama_bahan || "bahan";
      document.getElementById("deleteIdLabel").textContent = deleteId;
      modalDelete.show();
    }
  });

  document
    .getElementById("btnConfirmDelete")
    .addEventListener("click", async () => {
      try {
        const res = await CafeAPI.delete("/bahan/" + deleteId);
        showToast(res.message);
        modalDelete.hide();
        loadData();
      } catch (err) {
        showToast(err.message, "danger");
      }
    });

  document.getElementById("formData").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("editId").value;
    const payload = {
      status: document.getElementById("status").value,
    };
    try {
      if (id) {
        await CafeAPI.put("/bahan/" + id, payload);
      } else {
        payload.id_jenis = document.getElementById("idJenis").value;
        if (!payload.id_jenis) throw new Error("Pilih jenis bahan");
        if (isCairanMode()) {
          const jumlahPack = parseNumberInput(
            document.getElementById("jumlahPack").value,
          );
          if (jumlahPack <= 0)
            throw new Error("Jumlah pack harus lebih dari 0");
          payload.jumlah_pack = jumlahPack;
        } else if (isPcsMode()) {
          const jumlahPcs = parseNumberInput(
            document.getElementById("jumlahPcs").value,
          );
          if (jumlahPcs <= 0) throw new Error("Jumlah pcs harus lebih dari 0");
          payload.jumlah_pcs = jumlahPcs;
        } else {
          const jumlah = parseNumberInput(
            document.getElementById("jumlahMasuk").value,
          );
          if (jumlah <= 0)
            throw new Error("Jumlah bahan masuk harus lebih dari 0");
          payload.jumlah = jumlah;
          payload.satuan = document.getElementById("satuanMasuk").value;
        }
        await CafeAPI.post("/bahan", payload);
      }
      showToast("Bahan berhasil disimpan");
      modal.hide();
      loadData();
    } catch (err) {
      showToast(err.message, "danger");
    }
  });

  setAddMode(true);
  loadData();
})();
