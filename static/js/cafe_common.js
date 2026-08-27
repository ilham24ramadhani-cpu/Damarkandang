/* Cafe Damarkandang — shared API & UI helpers */

const CafeAPI = {
  _controllers: new Map(),

  async request(path, method = 'GET', body = null, options = {}) {
    const key = options.key || (method === 'GET' ? path.split('?')[0] : null);
    if (key && this._controllers.has(key)) {
      try { this._controllers.get(key).abort(); } catch (_) { /* ignore */ }
    }
    const controller = new AbortController();
    if (key) this._controllers.set(key, controller);

    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      signal: controller.signal,
    };
    if (body) opts.body = JSON.stringify(body);

    try {
      const res = await fetch('/api' + path, opts);
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.success === false) {
        throw new Error(data.error || data.message || 'Permintaan gagal');
      }
      return data;
    } catch (err) {
      if (err && err.name === 'AbortError') {
        const abortErr = new Error('Request dibatalkan');
        abortErr.name = 'AbortError';
        throw abortErr;
      }
      throw err;
    } finally {
      if (key && this._controllers.get(key) === controller) {
        this._controllers.delete(key);
      }
    }
  },

  get(path, options) { return this.request(path, 'GET', null, options); },
  post(path, body, options) { return this.request(path, 'POST', body, options); },
  put(path, body, options) { return this.request(path, 'PUT', body, options); },
  delete(path, options) { return this.request(path, 'DELETE', null, options); },
};

function formatRupiah(n) {
  const val = Math.round(Number(n) || 0);
  return 'Rp' + val.toLocaleString('id-ID');
}

function formatGram(n) {
  const val = Math.round(Number(n) || 0);
  return val.toLocaleString('id-ID') + ' gram';
}

function parseNumberInput(val) {
  if (val == null) return 0;
  const s = String(val).replace(/\./g, '').replace(/,/g, '.').replace(/[^\d.-]/g, '');
  const n = parseFloat(s);
  return Number.isFinite(n) ? n : 0;
}

function showToast(message, type = 'success') {
  if (!message || message === 'Request dibatalkan') return;
  const container = document.getElementById('toastContainer');
  if (!container) return alert(message);
  const id = 'toast-' + Date.now();
  const bg = type === 'success' ? 'text-bg-success' : type === 'danger' ? 'text-bg-danger' : 'text-bg-warning';
  container.insertAdjacentHTML('beforeend', `
    <div id="${id}" class="toast align-items-center ${bg} border-0" role="alert">
      <div class="d-flex"><div class="toast-body">${message}</div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>
    </div>`);
  const el = document.getElementById(id);
  const toast = new bootstrap.Toast(el, { delay: 3500 });
  toast.show();
  el.addEventListener('hidden.bs.toast', () => el.remove());
}

function stokBadgeClass(status) {
  if (status === 'menipis') return 'stok-badge-menipis';
  if (status === 'habis') return 'stok-badge-habis';
  return 'stok-badge-normal';
}

function renderPagination(container, page, total, perPage, onChange) {
  const pages = Math.max(1, Math.ceil(total / perPage));
  container.innerHTML = '';
  if (pages <= 1) return;
  const ul = document.createElement('ul');
  ul.className = 'pagination pagination-sm mb-0';
  // Batasi tombol halaman agar DOM tidak membengkak
  const maxButtons = 7;
  let start = Math.max(1, page - Math.floor(maxButtons / 2));
  let end = Math.min(pages, start + maxButtons - 1);
  start = Math.max(1, end - maxButtons + 1);
  for (let p = start; p <= end; p++) {
    const li = document.createElement('li');
    li.className = 'page-item' + (p === page ? ' active' : '');
    li.innerHTML = `<a class="page-link" href="#">${p}</a>`;
    li.addEventListener('click', (e) => { e.preventDefault(); if (p !== page) onChange(p); });
    ul.appendChild(li);
  }
  container.appendChild(ul);
}

/** Toggle HTML5 required — hindari error field tersembunyi saat mode edit. */
function setFieldsRequired(fieldIds, required) {
  fieldIds.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (required) el.setAttribute('required', 'required');
    else el.removeAttribute('required');
  });
}

function setBlocksVisible(blockMap) {
  Object.entries(blockMap).forEach(([id, visible]) => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('d-none', !visible);
  });
}

function debounce(fn, wait = 300) {
  let timer = null;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), wait);
  };
}

function isAbortError(err) {
  return err && (err.name === 'AbortError' || err.message === 'Request dibatalkan');
}

/** Wrapper load: abaikan AbortError, tampilkan error lain. */
function safeLoad(promise, toastOnError = true) {
  return promise.catch((err) => {
    if (isAbortError(err)) return null;
    if (toastOnError) showToast(err.message || 'Gagal memuat', 'danger');
    throw err;
  });
}

window.CafeAPI = CafeAPI;
window.formatRupiah = formatRupiah;
window.formatGram = formatGram;
window.parseNumberInput = parseNumberInput;
window.showToast = showToast;
window.stokBadgeClass = stokBadgeClass;
window.renderPagination = renderPagination;
window.setFieldsRequired = setFieldsRequired;
window.setBlocksVisible = setBlocksVisible;
window.debounce = debounce;
window.isAbortError = isAbortError;
window.safeLoad = safeLoad;
