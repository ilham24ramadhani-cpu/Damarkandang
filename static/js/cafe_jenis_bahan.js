(function () {
  let page = 1;
  const perPage = 10;
  let deleteId = null;
  const modal = bootstrap.Modal.getOrCreateInstance(
    document.getElementById("modalForm"),
  );
  const modalDelete = bootstrap.Modal.getOrCreateInstance(
    document.getElementById("modalDelete"),
  );

  function isCairanSelected() {
    return document.getElementById("bentukBahan").value === "cairan";
  }

  const KATEGORI_PCS = new Set(["Kopral", "Roasted", "Skincare"]);

  function isKategoriPcs() {
    return KATEGORI_PCS.has(document.getElementById("kategoriJenis")?.value);
  }

  function isPcsSelected() {
    if (isKategoriPcs()) return true;
    return !isCairanSelected() && document.getElementById("satuanBerat").value === "pcs";
  }

  function applyKategoriDefaults() {
    const kat = document.getElementById("kategoriJenis")?.value || "Minuman";
    const bentuk = document.getElementById("bentukBahan");
    const satuan = document.getElementById("satuanBerat");
    if (KATEGORI_PCS.has(kat)) {
      bentuk.value = "non_cairan";
      bentuk.disabled = true;
      satuan.value = "pcs";
      satuan.disabled = true;
    } else {
      bentuk.disabled = false;
      satuan.disabled = false;
    }
  }

  function syncGramCustom() {
    const sel = document.getElementById("gramPerPcs");
    const custom = document.getElementById("gramPerPcsCustom");
    const isCustom = sel.value === "custom";
    custom.classList.toggle("d-none", !isCustom);
    if (!isCustom) custom.value = "";
  }

  function getGramPerPcs() {
    const sel = document.getElementById("gramPerPcs");
    if (sel.value === "custom") {
      return parseNumberInput(document.getElementById("gramPerPcsCustom").value);
    }
    return parseNumberInput(sel.value);
  }

  function setGramPerPcs(gram) {
    const sel = document.getElementById("gramPerPcs");
    const custom = document.getElementById("gramPerPcsCustom");
    const g = String(parseInt(gram, 10) || "");
    if (["250", "500", "1000"].includes(g)) {
      sel.value = g;
      custom.classList.add("d-none");
      custom.value = "";
    } else if (g) {
      sel.value = "custom";
      custom.classList.remove("d-none");
      custom.value = g;
    } else {
      sel.value = "250";
      custom.classList.add("d-none");
      custom.value = "";
    }
  }

  function toggleBentukFields() {
    applyKategoriDefaults();
    const cairan = isCairanSelected();
    const pcs = !cairan && isPcsSelected();
    setBlocksVisible({
      wrapCairanFields: cairan,
      wrapNonCairanFields: !cairan,
      wrapHargaKg: !cairan && !pcs,
      wrapHargaPcs: !cairan && pcs,
    });
    setFieldsRequired(["hargaPerPack", "kgPerPack"], cairan);
    setFieldsRequired(["hargaPerKgMaster"], !cairan && !pcs);
    setFieldsRequired(["hargaPerPcs"], !cairan && pcs);
    syncGramCustom();
  }

  function hargaInfo(row) {
    if (row.bentuk_bahan === "cairan") {
      const kg = row.kg_per_pack != null ? `${row.kg_per_pack} kg` : "-";
      const harga = row.harga_per_pack ? formatRupiah(row.harga_per_pack) : "-";
      return `${kg}/pack · ${harga}`;
    }
    if (row.satuan_berat === "pcs") {
      const isi = row.gram_per_pcs ? `${row.gram_per_pcs}g` : "-";
      const harga = row.harga_per_pcs ? formatRupiah(row.harga_per_pcs) : "-";
      return `${isi}/pcs · ${harga}`;
    }
    return row.harga_per_kg ? `${formatRupiah(row.harga_per_kg)}/kg` : "-";
  }

  async function loadData() {
    const search = document.getElementById("searchInput").value.trim();
    const status = document.getElementById("statusFilter").value;
    const q = new URLSearchParams({ page, per_page: perPage, search, status });
    const res = await CafeAPI.get("/jenis-bahan?" + q);
    const tbody = document.getElementById("tableBody");
    tbody.innerHTML = "";
    (res.data.items || []).forEach((row) => {
      const tr = document.createElement("tr");
      const satuanTag =
        row.bentuk_bahan === "cairan"
          ? ""
          : row.satuan_berat === "pcs"
            ? " · Pcs"
            : " · Kg";
      tr.innerHTML = `
        <td>${row.id_jenis}</td>
        <td>${row.nama_jenis}</td>
        <td><span class="badge bg-secondary">${row.kategori || "Minuman"}</span></td>
        <td><span class="badge ${row.bentuk_bahan === "cairan" ? "bg-info text-dark" : "bg-light text-dark border"}">${row.bentuk_bahan_label || "Non Cairan"}${satuanTag}</span></td>
        <td>${hargaInfo(row)}</td>
        <td>${row.deskripsi || "-"}</td>
        <td><span class="badge ${row.status === "aktif" ? "bg-success" : "bg-secondary"}">${row.status}</span></td>
        <td>
          <button class="btn btn-sm btn-outline-primary btn-edit" data-id="${row.id_jenis}"><i class="bi bi-pencil"></i></button>
          <button class="btn btn-sm btn-outline-danger btn-del" data-id="${row.id_jenis}"><i class="bi bi-trash"></i></button>
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

  function resetForm() {
    document.getElementById("editId").value = "";
    document.getElementById("namaJenis").value = "";
    document.getElementById("kategoriJenis").value = "Minuman";
    document.getElementById("bentukBahan").value = "non_cairan";
    document.getElementById("bentukBahan").disabled = false;
    document.getElementById("satuanBerat").disabled = false;
    document.getElementById("satuanBerat").value = "kg";
    document.getElementById("hargaPerKgMaster").value = "";
    document.getElementById("hargaPerPcs").value = "";
    setGramPerPcs(250);
    document.getElementById("hargaPerPack").value = "";
    document.getElementById("kgPerPack").value = "";
    document.getElementById("deskripsi").value = "";
    document.getElementById("status").value = "aktif";
    document.getElementById("modalTitle").textContent = "Tambah Jenis Bahan";
    toggleBentukFields();
  }

  document
    .querySelector('[data-bs-target="#modalForm"]')
    .addEventListener("click", resetForm);
  document
    .getElementById("bentukBahan")
    .addEventListener("change", toggleBentukFields);
  document
    .getElementById("kategoriJenis")
    .addEventListener("change", toggleBentukFields);
  document
    .getElementById("satuanBerat")
    .addEventListener("change", toggleBentukFields);
  document
    .getElementById("gramPerPcs")
    .addEventListener("change", syncGramCustom);
  document.getElementById("searchInput").addEventListener("input", () => {
    page = 1;
    loadData();
  });
  document.getElementById("statusFilter").addEventListener("change", () => {
    page = 1;
    loadData();
  });

  document.getElementById("tableBody").addEventListener("click", async (e) => {
    const editBtn = e.target.closest(".btn-edit");
    const delBtn = e.target.closest(".btn-del");
    if (editBtn) {
      const id = editBtn.dataset.id;
      const rows = await CafeAPI.get("/jenis-bahan?per_page=1000");
      const row = (rows.data.items || []).find((x) => x.id_jenis === id);
      if (!row) return;
      document.getElementById("editId").value = id;
      document.getElementById("namaJenis").value = row.nama_jenis;
      document.getElementById("kategoriJenis").value = row.kategori || "Minuman";
      document.getElementById("bentukBahan").value =
        row.bentuk_bahan || "non_cairan";
      document.getElementById("satuanBerat").value = row.satuan_berat || "kg";
      document.getElementById("hargaPerKgMaster").value =
        row.harga_per_kg || "";
      document.getElementById("hargaPerPcs").value = row.harga_per_pcs || "";
      setGramPerPcs(row.gram_per_pcs || 250);
      document.getElementById("hargaPerPack").value = row.harga_per_pack || "";
      document.getElementById("kgPerPack").value = row.kg_per_pack || "";
      document.getElementById("deskripsi").value = row.deskripsi || "";
      document.getElementById("status").value = row.status;
      document.getElementById("modalTitle").textContent = "Edit Jenis Bahan";
      toggleBentukFields();
      modal.show();
    }
    if (delBtn) {
      deleteId = delBtn.dataset.id;
      modalDelete.show();
    }
  });

  document
    .getElementById("btnConfirmDelete")
    .addEventListener("click", async () => {
      try {
        const res = await CafeAPI.delete("/jenis-bahan/" + deleteId);
        showToast(res.message);
        modalDelete.hide();
        loadData();
      } catch (err) {
        showToast(err.message, "danger");
      }
    });

  document.getElementById("formData").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      nama_jenis: document.getElementById("namaJenis").value.trim(),
      kategori: document.getElementById("kategoriJenis").value,
      bentuk_bahan: document.getElementById("bentukBahan").value,
      deskripsi: document.getElementById("deskripsi").value.trim(),
      status: document.getElementById("status").value,
    };
    try {
      if (isCairanSelected()) {
        payload.harga_per_pack = parseNumberInput(
          document.getElementById("hargaPerPack").value,
        );
        payload.kg_per_pack = parseNumberInput(
          document.getElementById("kgPerPack").value,
        );
        if (payload.harga_per_pack <= 0)
          throw new Error("Harga per pack wajib diisi");
        if (payload.kg_per_pack <= 0)
          throw new Error("Berat kg per pack wajib diisi");
      } else if (isPcsSelected()) {
        payload.satuan_berat = "pcs";
        payload.harga_per_pcs = parseNumberInput(
          document.getElementById("hargaPerPcs").value,
        );
        payload.gram_per_pcs = getGramPerPcs();
        if (payload.harga_per_pcs <= 0)
          throw new Error("Harga per pcs wajib diisi");
        if (payload.gram_per_pcs <= 0)
          throw new Error("Isi per pcs (gram) wajib diisi");
      } else {
        payload.satuan_berat = "kg";
        payload.harga_per_kg = parseNumberInput(
          document.getElementById("hargaPerKgMaster").value,
        );
        if (payload.harga_per_kg <= 0)
          throw new Error("Harga per kg wajib diisi");
      }
      const id = document.getElementById("editId").value;
      if (id) await CafeAPI.put("/jenis-bahan/" + id, payload);
      else await CafeAPI.post("/jenis-bahan", payload);
      showToast("Data berhasil disimpan");
      modal.hide();
      loadData();
    } catch (err) {
      showToast(err.message, "danger");
    }
  });

  toggleBentukFields();
  loadData();
})();
