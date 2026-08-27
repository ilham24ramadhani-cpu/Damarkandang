from flask import Flask, render_template, request, jsonify, redirect, url_for, make_response, session, send_from_directory  # pyright: ignore[reportMissingImports]
from flask_cors import CORS  # pyright: ignore[reportMissingModuleSource]
from pymongo import MongoClient  # pyright: ignore[reportMissingImports]
from werkzeug.utils import secure_filename  # pyright: ignore[reportMissingImports]
import os
import uuid
from os.path import join, dirname, exists, abspath
from dotenv import load_dotenv  # pyright: ignore[reportMissingImports]
from bson import ObjectId  # pyright: ignore[reportMissingImports]
import jwt  # pyright: ignore[reportMissingImports]
import hashlib
import re
from datetime import datetime, timedelta
from urllib.parse import quote_plus
import base64

app = Flask(__name__)
_APP_ROOT_DIR = abspath(dirname(__file__))
PRODUKSI_TAHAPAN_UPLOAD_DIR = join(_APP_ROOT_DIR, 'static', 'uploads', 'produksi_tahapan')
ALLOWED_PRODUKSI_FOTO_EXT = {'.jpg', '.jpeg', '.png', '.webp'}
MAX_PRODUKSI_FOTO_BYTES = 5 * 1024 * 1024  # 5 MB
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'SPARTA')
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # 7 days session
# Cookie settings for session
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Allows cookies to be sent with same-site requests
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_PATH'] = '/'  # Cookie available for all paths

CORS(app, supports_credentials=True)  # Enable CORS with credentials for session

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME = os.environ.get("DB_NAME")
SECRET_KEY = os.environ.get("SECRET_KEY", "SPARTA")

# Clean and encode MongoDB URI
if MONGODB_URI:
    MONGODB_URI = MONGODB_URI.strip().strip('"').strip("'")
    if '@' in MONGODB_URI and 'mongodb+srv://' in MONGODB_URI:
        try:
            parts = MONGODB_URI.split('@')
            if len(parts) == 2:
                auth_part = parts[0]
                if '://' in auth_part:
                    protocol = auth_part.split('://')[0] + '://'
                    user_pass = auth_part.split('://')[1]
                    if ':' in user_pass:
                        username, password = user_pass.split(':', 1)
                        password = password.strip('<>')
                        password_encoded = quote_plus(password)
                        MONGODB_URI = f'{protocol}{username}:{password_encoded}@{parts[1]}'
        except:
            pass

def _extract_db_name_from_mongodb_uri(uri: str):
    """
    Ambil nama database dari MongoDB URI (bagian setelah '/' sebelum '?').
    Contoh:
      mongodb+srv://.../DB_DAMARKANDANG?retryWrites=true -> DB_DAMARKANDANG
    """
    if not uri:
        return None
    u = str(uri).strip()
    # buang fragment/query dulu
    if '?' in u:
        u = u.split('?', 1)[0]
    # jika tidak ada '/', tidak ada db name eksplisit
    if '/' not in u:
        return None
    tail = u.rsplit('/', 1)[-1].strip()
    return tail or None

def _sanitize_db_name(name: str):
    """
    MongoDB db name tidak boleh mengandung spasi.
    Railway kadang menyuntikkan env dengan spasi/quote tak sengaja.
    """
    if name is None:
        return None
    s = str(name).strip().strip('"').strip("'").strip()
    if not s:
        return None
    if " " in s:
        fixed = "_".join(s.split())
        print(f"⚠️ DB_NAME mengandung spasi: {s!r}. Menggunakan: {fixed!r}")
        s = fixed
    return s

# Pastikan DB_NAME konsisten dengan nama db di URI (MongoDB sensitif case untuk create DB).
_db_from_uri = _extract_db_name_from_mongodb_uri(MONGODB_URI) if MONGODB_URI else None
if _db_from_uri:
    if not DB_NAME:
        DB_NAME = _db_from_uri
    else:
        # Jika hanya beda huruf besar/kecil, pakai yang dari URI agar tidak memicu DatabaseDifferCase.
        if str(DB_NAME).strip().lower() == str(_db_from_uri).strip().lower() and str(DB_NAME).strip() != str(_db_from_uri).strip():
            print(f"⚠️ DB_NAME beda case dengan URI: DB_NAME={DB_NAME} URI_DB={_db_from_uri}. Menggunakan URI_DB.")
            DB_NAME = _db_from_uri

# Sanitasi akhir (trim + hilangkan spasi) sebelum dipakai di client[DB_NAME]
DB_NAME = _sanitize_db_name(DB_NAME)

client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=8080,
    connectTimeoutMS=8000,
    socketTimeoutMS=20000,
    maxPoolSize=50,
    minPoolSize=1,
    retryWrites=True,
    compressors='zlib',
)
db = client[DB_NAME]
try:
    client.admin.command('ping')
    print("DEBUG: KONEKSI BERHASIL!")
except Exception as e:
    print(f"DEBUG: KONEKSI GAGAL KARENA: {e}")

TOKEN_KEY = 'mytoken'

# Helper function to convert ObjectId to string in dict
# Optimized version for better performance
def json_serialize(data):
    """Optimized JSON serialization for MongoDB documents"""
    if isinstance(data, ObjectId):
        return str(data)
    if isinstance(data, list):
        # Use list comprehension for better performance
        return [json_serialize(item) for item in data]
    if isinstance(data, dict):
        # Use dict comprehension for better performance
        return {key: json_serialize(value) for key, value in data.items()}
    # Handle datetime and other types that might need conversion
    if hasattr(data, 'isoformat'):  # datetime objects
        return data.isoformat()
    return data

def parse_bool_payload(val, default=False):
    """Parse boolean dari JSON (bool, angka, atau string)."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ('true', '1', 'yes', 'on')
    return default


def _ensure_produksi_tahapan_upload_dir():
    os.makedirs(PRODUKSI_TAHAPAN_UPLOAD_DIR, exist_ok=True)


def _sanitize_foto_tahapan_path(val):
    """
    Validasi path foto tahapan produksi (hanya URL relatif dari folder upload server).
    """
    if not val or not isinstance(val, str):
        return None
    s = val.strip()
    prefix = '/static/uploads/produksi_tahapan/'
    if not s.startswith(prefix):
        return None
    tail = s[len(prefix):]
    if not tail or '..' in tail or '/' in tail:
        return None
    if not all(c.isalnum() or c in '._-' for c in tail):
        return None
    return s


def _save_uploaded_foto_tahapan_produksi_file():
    """
    Simpan multipart field 'file' ke static/uploads/produksi_tahapan/.
    Returns (rel_url, None) atau (None, error_message).
    """
    if 'file' not in request.files:
        return None, 'Tidak ada berkas'
    f = request.files['file']
    if not f or f.filename == '':
        return None, 'Tidak ada berkas'
    orig = secure_filename(f.filename) or 'foto'
    ext = os.path.splitext(orig)[1].lower()
    if ext not in ALLOWED_PRODUKSI_FOTO_EXT:
        return None, 'Format gambar tidak didukung (jpg, jpeg, png, webp)'
    _ensure_produksi_tahapan_upload_dir()
    new_name = f'{uuid.uuid4().hex}{ext}'
    abs_path = join(PRODUKSI_TAHAPAN_UPLOAD_DIR, new_name)
    f.save(abs_path)
    try:
        sz = os.path.getsize(abs_path)
    except OSError:
        return None, 'Gagal menyimpan berkas'
    if sz > MAX_PRODUKSI_FOTO_BYTES:
        try:
            os.remove(abs_path)
        except OSError:
            pass
        return None, 'Ukuran gambar maksimal 5 MB'
    if sz < 32:
        try:
            os.remove(abs_path)
        except OSError:
            pass
        return None, 'Berkas gambar tidak valid'
    rel_url = f'/static/uploads/produksi_tahapan/{new_name}'
    return rel_url, None


# Helper function to get next ID for a collection
def get_next_id(collection_name):
    counter_collection = db.counters
    counter = counter_collection.find_one_and_update(
        {'_id': collection_name},
        {'$inc': {'seq': 1}},
        upsert=True,
        return_document=True
    )
    return counter['seq']

# Helper function to preview next ID without incrementing (for UI display)
def get_next_id_preview(collection_name):
    counter = db.counters.find_one({'_id': collection_name})
    seq = counter['seq'] if counter else 0
    return seq + 1

# Helper function to generate idBahan (format BHN001, BHN002, ...)
def generate_id_bahan():
    next_seq = get_next_id_preview('bahan')
    return f"BHN{str(next_seq).zfill(3)}"

# Helper function to generate idProduksi (format PRD-YYYYMM-XXXX)
def generate_id_produksi():
    """Generate next idProduksi. Atomically increments counter."""
    yyyymm = datetime.now().strftime('%Y%m')
    counter_key = f'produksi_{yyyymm}'
    seq = get_next_id(counter_key)
    return f"PRD-{yyyymm}-{str(seq).zfill(4)}"

def get_next_id_produksi_preview():
    """Preview next idProduksi without incrementing (for UI display)."""
    yyyymm = datetime.now().strftime('%Y%m')
    counter_key = f'produksi_{yyyymm}'
    seq = get_next_id_preview(counter_key)
    return f"PRD-{yyyymm}-{str(seq).zfill(4)}"

def _int_proses_id(v):
    try:
        if v is None or v == '':
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _find_data_proses_doc(*, id_proses=None, nama=None):
    if id_proses is not None:
        pid = _int_proses_id(id_proses)
        if pid is None:
            return None
        return db.dataProses.find_one({'id': pid})
    n = (nama or '').strip()
    if n:
        return db.dataProses.find_one({'nama': n})
    return None


def _resolve_proses_dari_payload(data):
    """
    idProses (disarankan) atau prosesPengolahan (legacy).
    Return (master_doc, id_as_int, nama_master) atau (None, None, None, error_str).
    """
    if not isinstance(data, dict):
        return None, None, None, 'payload tidak valid'
    raw_id = data.get('idProses')
    if raw_id is not None and str(raw_id).strip() != '':
        master = _find_data_proses_doc(id_proses=raw_id)
        if not master:
            return None, None, None, f'idProses tidak ditemukan di master: {raw_id}'
        ip = _int_proses_id(master.get('id'))
        nm = (master.get('nama') or '').strip()
        return master, ip, nm, None
    pn = str(data.get('prosesPengolahan') or '').strip()
    if pn:
        master = _find_data_proses_doc(nama=pn)
        if not master:
            return None, None, None, f'Proses pengolahan "{pn}" tidak terdaftar di master data'
        return master, _int_proses_id(master.get('id')), (master.get('nama') or '').strip(), None
    return None, None, None, 'Wajib menyediakan idProses atau prosesPengolahan'


def _resolve_proses_query_param_proses(raw):
    """
    Query ?proses= untuk API bahan: angka → id master; lainnya → nama (legacy).
    Return (master_or_none, id_int_or_none, nama_str, error_str_or_none).
    """
    s = (raw or '').strip()
    if not s:
        return None, None, '', 'Parameter proses kosong'
    if s.isdigit():
        master = _find_data_proses_doc(id_proses=int(s))
        if not master:
            return None, None, '', f'idProses {s} tidak ditemukan'
        ip = _int_proses_id(master.get('id'))
        nm = (master.get('nama') or '').strip()
        return master, ip, nm, None
    master = _find_data_proses_doc(nama=s)
    if not master:
        return None, None, '', f'Proses "{s}" tidak ditemukan di master'
    return master, _int_proses_id(master.get('id')), (master.get('nama') or '').strip(), None


def _produksi_same_jalur(produksi_doc, id_proses, nama_proses):
    """
    Cocokkan dokumen produksi dengan jalur master.
    Dokumen baru memakai idProses; lama bisa hanya punya nama.
    """
    if produksi_doc is None:
        return False
    ip_filter = _int_proses_id(id_proses)
    nama = (nama_proses or '').strip() if nama_proses else ''
    restrict = ip_filter is not None or bool(nama)
    if not restrict:
        return True
    pid = _int_proses_id(produksi_doc.get('idProses'))
    if ip_filter is not None and pid is not None:
        return pid == ip_filter
    if ip_filter is not None and pid is None and nama:
        return (produksi_doc.get('prosesPengolahan') or '').strip() == nama
    if nama:
        return (produksi_doc.get('prosesPengolahan') or '').strip() == nama
    return False


def validate_sequential_tahapan_dengan_master(master_proses, status_tahapan_baru, status_tahapan_lama=None):
    """
    Validasi urutan tahapan memakai dokumen master dataProses yang sudah di-resolve.
    """
    label = (master_proses.get('nama') or '').strip() if master_proses else ''
    try:
        if not master_proses:
            return False, 'Master proses pengolahan tidak ada'
        
        tahapan_status = master_proses.get('tahapanStatus', {})
        
        # Mapping tahapan untuk validasi (nilai kanonik = kunci di tahapanStatus master)
        # Urutan kunci penting: label yang lebih panjang (Pertama/Kedua) harus sebelum
        # 'Pengupasan Kulit Tanduk (Hulling)' agar pengecekan `key in status` tidak salah map.
        tahapan_map = {
            'Sortasi Cherry atau Buah Kopi': 'Sortasi',
            'Sortasi Buah': 'Sortasi',  # Kompatibilitas nama lama
            'Pengeringan Awal Pertama': 'Pengeringan Awal Pertama',
            'Pengeringan Awal Pertama (Para - Para)': 'Pengeringan Awal Pertama',
            'Fermentasi': 'Fermentasi',
            'Pulping': 'Pulping',
            'Pencucian': 'Pencucian',
            'Pengeringan Awal': 'Pengeringan Awal',
            'Pengeringan Awal (Para - Para)': 'Pengeringan Awal',
            'Pengeringan Awal kedua (Para - Para)': 'Pengeringan Awal',
            'Fermentasi 2': 'Fermentasi 2',
            'Pulping 2': 'Pulping 2',
            'Pengeringan Akhir': 'Pengeringan Akhir',
            'Pengeringan Akhir (Pengeringan Lantai)': 'Pengeringan Akhir',
            'Pengupasan Kulit Tanduk (Hulling) Pertama': 'Pulping 2',
            'Pengupasan Kulit Tanduk (Hulling) Kedua': 'Hulling',
            'Pengupasan Kulit Tanduk (Hulling)': 'Hulling',
            'Hand Sortasi atau Sortasi Biji Kopi': 'Hand Sortasi',
            'Roasting': 'Roasting',  # legacy (data lama)
            'Grinding': 'Grinding',
            'Pengemasan': 'Pengemasan'
        }
        
        # Daftar urutan tahapan (sesuai urutan logis proses basah → pengeringan para-para → siklus kedua → pengeringan lantai → …)
        urutan_tahapan = [
            'Sortasi', 'Pengeringan Awal Pertama', 'Fermentasi', 'Pulping', 'Pencucian',
            'Pengeringan Awal', 'Fermentasi 2', 'Pulping 2', 'Pengeringan Akhir',
            'Hulling', 'Hand Sortasi', 'Grinding', 'Pengemasan',
        ]
        
        # Mapping urutan tahapan untuk mendapatkan index
        urutan_map = {tahapan: idx for idx, tahapan in enumerate(urutan_tahapan)}
        
        # Normalisasi status tahapan baru
        status_baru_normalized = None
        for key, value in tahapan_map.items():
            if key in status_tahapan_baru or status_tahapan_baru == key:
                status_baru_normalized = value
                break
        
        if not status_baru_normalized:
            # Jika tidak ditemukan di map, coba langsung
            status_baru_normalized = status_tahapan_baru
        
        # Validasi: tahapan baru harus ada di konfigurasi master (kecuali Pengemasan yang selalu tersedia)
        if status_baru_normalized != 'Pengemasan':
            if not tahapan_status.get(status_baru_normalized, False):
                return False, f'Tahapan "{status_tahapan_baru}" tidak tersedia untuk proses pengolahan "{label}"'
        
        # Jika ini adalah update (ada status lama), validasi sequential
        if status_tahapan_lama:
            # Normalisasi status lama
            status_lama_normalized = None
            for key, value in tahapan_map.items():
                if key in status_tahapan_lama or status_tahapan_lama == key:
                    status_lama_normalized = value
                    break
            
            if not status_lama_normalized:
                status_lama_normalized = status_tahapan_lama
            
            # Cari index tahapan lama dan baru
            try:
                index_lama = urutan_tahapan.index(status_lama_normalized)
                index_baru = urutan_tahapan.index(status_baru_normalized)
                
                # Tidak boleh mundur ke tahapan sebelumnya. Tahapan **sama** diperbolehkan
                # agar bisa simpan edit (tambah ID bahan, berat, catatan) tanpa memajukan proses.
                if index_baru < index_lama:
                    return False, (
                        f'Tidak dapat mengubah tahapan dari "{status_tahapan_lama}" ke "{status_tahapan_baru}". '
                        'Tidak boleh kembali ke tahapan sebelumnya.'
                    )
                
                # Jika tidak maju tahapan, tidak perlu cek loncat
                if index_baru == index_lama:
                    return True, None
                
                # Validasi: tidak boleh loncat tahapan (hanya saat maju)
                if index_baru - index_lama > 1:
                    tahapan_terlewat = urutan_tahapan[index_lama + 1:index_baru]
                    # Filter hanya tahapan yang ada di konfigurasi master
                    tahapan_terlewat_valid = [t for t in tahapan_terlewat if tahapan_status.get(t, False) or t == 'Pengemasan']
                    if tahapan_terlewat_valid:
                        return False, f'Tidak dapat melompati tahapan. Tahapan yang terlewat: {", ".join(tahapan_terlewat_valid)}'
            except ValueError:
                # Jika tahapan tidak ditemukan di urutan, skip validasi sequential
                pass
        
        return True, None
    except Exception as e:
        return False, f'Error validasi tahapan: {str(e)}'


def validate_sequential_tahapan(proses_pengolahan, status_tahapan_baru, status_tahapan_lama=None):
    """
    Legacy: lookup master dari nama string lalu validasi urutan tahapan.
    """
    nama = (proses_pengolahan or '').strip()
    master = _find_data_proses_doc(nama=nama)
    if not master:
        return False, f'Proses pengolahan "{nama}" tidak ditemukan di master data'
    return validate_sequential_tahapan_dengan_master(master, status_tahapan_baru, status_tahapan_lama)


def _clean_detail_kloter_list(detail_kloter):
    """Normalize detailKloter: only rows with berat > 0, renumber kloter."""
    detail_kloter_clean = []
    if not detail_kloter or not isinstance(detail_kloter, list):
        return detail_kloter_clean
    for k in detail_kloter:
        berat = float(k.get('berat', 0) or 0)
        if berat > 0:
            detail_kloter_clean.append({
                'kloter': len(detail_kloter_clean) + 1,
                'berat': berat,
                'keterangan': k.get('keterangan', '') or ''
            })
    return detail_kloter_clean


def _normalize_proses_bahan_payload(proses_bahan_raw):
    """
    Validate prosesBahan[] against master dataProses.
    Prefer idProses per baris; fallback prosesPengolahan (nama).
    Returns (clean_list, total_berat, error_message).
    """
    if not proses_bahan_raw or not isinstance(proses_bahan_raw, list) or len(proses_bahan_raw) == 0:
        return None, 0, 'prosesBahan wajib berisi minimal satu proses dengan kloter timbangan'
    seen_ids = set()
    seen_nama = set()
    proses_bahan_clean = []
    for item in proses_bahan_raw:
        if not isinstance(item, dict):
            return None, 0, 'Setiap baris proses harus berupa objek'
        raw_id = item.get('idProses')
        master = None
        if raw_id is not None and str(raw_id).strip() != '':
            master = _find_data_proses_doc(id_proses=raw_id)
            if not master:
                return None, 0, f'idProses {raw_id} tidak terdaftar di master data'
        else:
            pn = (item.get('prosesPengolahan') or '').strip()
            if not pn:
                return None, 0, 'Setiap baris wajib idProses atau prosesPengolahan'
            master = _find_data_proses_doc(nama=pn)
            if not master:
                return None, 0, f'Proses pengolahan "{pn}" tidak terdaftar di master data'
        pid = _int_proses_id(master.get('id'))
        if pid is None:
            return None, 0, 'Master proses tidak memiliki id numerik'
        pname = (master.get('nama') or '').strip()
        if pid in seen_ids:
            return None, 0, f'Proses id {pid} tidak boleh duplikat pada satu bahan'
        seen_ids.add(pid)
        if pname in seen_nama:
            return None, 0, f'Proses "{pname}" tidak boleh duplikat pada satu bahan'
        seen_nama.add(pname)
        dk = _clean_detail_kloter_list(item.get('detailKloter') or item.get('kloter') or [])
        if not dk:
            return None, 0, f'Minimal satu kloter dengan berat > 0 untuk proses "{pname}"'
        subtotal = sum(k['berat'] for k in dk)
        proses_bahan_clean.append({
            'idProses': pid,
            'prosesPengolahan': pname,
            'detailKloter': dk,
            'jumlahBeratProses': round(subtotal, 4)
        })
    total = sum(x['jumlahBeratProses'] for x in proses_bahan_clean)
    return proses_bahan_clean, total, None


def _id_bahan_list_from_produksi(doc):
    """Daftar id bahan pada dokumen produksi (idBahanList atau legacy idBahan)."""
    if not doc:
        return []
    lst = doc.get('idBahanList')
    if isinstance(lst, list) and len(lst) > 0:
        out = []
        for x in lst:
            s = str(x or '').strip()
            if s:
                out.append(s)
        return out
    ib = doc.get('idBahan')
    if ib:
        return [str(ib).strip()]
    return []


def _alokasi_map_from_produksi(doc):
    """Map idBahan -> berat terpakai dari alokasiBeratBahan atau legacy beratAwal tunggal."""
    if not doc:
        return {}
    rows = doc.get('alokasiBeratBahan')
    if isinstance(rows, list) and len(rows) > 0:
        m = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            bid = str(r.get('idBahan') or '').strip()
            if not bid:
                continue
            m[bid] = m.get(bid, 0) + float(r.get('berat', 0) or 0)
        return m
    ib = doc.get('idBahan')
    if ib:
        return {str(ib).strip(): float(doc.get('beratAwal', 0) or 0)}
    return {}


def _total_digunakan_bahan_proses(id_bahan, id_proses=None, nama_proses=None):
    """
    Total berat terpakai untuk satu id_bahan.
    Jika id_proses atau nama_proses diisi: filter produksi ke jalur proses tersebut.
    Tanpa filter: pool legacy semua produksi yang memakai id_bahan.
    """
    total = 0.0
    id_bahan = str(id_bahan or '').strip()
    if not id_bahan:
        return 0.0
    ip = _int_proses_id(id_proses)
    nq = (nama_proses or '').strip() if nama_proses else ''
    restrict = ip is not None or bool(nq)
    for p in db.produksi.find({}):
        if restrict and not _produksi_same_jalur(p, ip, nq):
            continue
        m = _alokasi_map_from_produksi(p)
        total += float(m.get(id_bahan, 0) or 0)
    return total


def _all_id_bahan_terpakai_produksi(exclude_id_produksi_str=None):
    """Kumpulan id bahan yang sudah muncul di dokumen produksi (untuk bahan legacy tanpa prosesBahan: satu id hanya satu produksi)."""
    used = set()
    ex = (exclude_id_produksi_str or '').strip() or None
    for p in db.produksi.find({}, {'idBahan': 1, 'idBahanList': 1, 'idProduksi': 1}):
        if ex and (p.get('idProduksi') or '') == ex:
            continue
        used.update(_id_bahan_list_from_produksi(p))
    return used


def _produksi_filter_by_bahan_id(id_bahan):
    """Query MongoDB untuk produksi yang memakai id_bahan (tunggal atau dalam daftar)."""
    id_bahan = str(id_bahan or '').strip()
    return {'$or': [{'idBahan': id_bahan}, {'idBahanList': id_bahan}]}


def _status_tambah_bahan_dikunci(status_tahapan):
    """
    Mulai tahap Pengemasan, penambahan ID bahan tidak diizinkan.
    """
    s = (status_tahapan or '').strip()
    if not s:
        return False
    return 'Pengemasan' in s


def _sisa_bahan_line(bahan_doc, id_bahan, proses_pengolahan=None, id_proses=None):
    """
    Sisa berat untuk kombinasi idBahan + proses (atau legacy: satu pool per idBahan).
    id_proses atau nama (proses_pengolahan) — id diprioritaskan.
    Returns (sisa_float, error_message or None).
    """
    lines = bahan_doc.get('prosesBahan') or []
    if lines:
        ip = _int_proses_id(id_proses)
        nq = (proses_pengolahan or '').strip()
        if ip is None and not nq:
            return None, 'prosesPengolahan atau idProses wajib untuk bahan yang memiliki pemisahan proses'
        line = None
        if ip is not None:
            line = next(
                (
                    l for l in lines
                    if isinstance(l, dict) and _int_proses_id(l.get('idProses')) == ip
                ),
                None,
            )
        if line is None and nq:
            line = next(
                (
                    l for l in lines
                    if isinstance(l, dict) and (l.get('prosesPengolahan') or '').strip() == nq
                ),
                None,
            )
        if not line:
            return None, (
                f'Proses id {ip} "{nq}" tidak terdaftar pada bahan ini'
                if ip is not None
                else f'Proses "{nq}" tidak terdaftar pada bahan ini'
            )
        line_ip = _int_proses_id(line.get('idProses'))
        line_nama = (line.get('prosesPengolahan') or '').strip()
        used = _total_digunakan_bahan_proses(
            id_bahan,
            id_proses=line_ip,
            nama_proses=line_nama,
        )
        cap = float(line.get('jumlahBeratProses', 0) or 0)
        return max(0.0, cap - used), None
    # Legacy: satu pool stok per idBahan
    cap = float(bahan_doc.get('jumlah', 0) or 0)
    used = _total_digunakan_bahan_proses(id_bahan)
    return max(0.0, cap - used), None


def _proses_bahan_stok_equivalent(old_lines, new_lines):
    """True jika setiap jalur punya idProses/nama + jumlahBeratProses yang sama (abaikan detail kloter)."""
    def norm(lst):
        if not isinstance(lst, list):
            return []
        out = []
        for x in lst:
            if not isinstance(x, dict):
                continue
            ip = _int_proses_id(x.get('idProses'))
            pn = (x.get('prosesPengolahan') or '').strip()
            try:
                w = round(float(x.get('jumlahBeratProses', 0) or 0), 4)
            except (TypeError, ValueError):
                w = 0.0
            sort_id = ip if ip is not None else -1
            out.append((sort_id, pn, w))
        return sorted(out)

    return norm(old_lines) == norm(new_lines)


def _cascade_remove_id_bahan_dari_produksi_setelah_master_bahan_diubah(id_bahan):
    """
    Setelah master bahan diubah (proses/berat/id/jumlah), lepaskan ID bahan tersebut
    dari semua dokumen produksi yang memakainya: hapus dari idBahanList & alokasi,
    kurangi beratAwal, sesuaikan berat terkini/akhir. Setara centang dibuka / harus
    dipilih ulang di form produksi agar sesuai perubahan master.
    """
    id_bahan = str(id_bahan or '').strip()
    if not id_bahan:
        return {'matched': 0, 'updated': 0}
    matched = 0
    updated = 0
    for p in db.produksi.find(_produksi_filter_by_bahan_id(id_bahan)):
        matched += 1
        ids = _id_bahan_list_from_produksi(p)
        if id_bahan not in ids:
            continue
        amap = _alokasi_map_from_produksi(p)
        removed_w = float(amap.get(id_bahan, 0) or 0)
        new_ids = [x for x in ids if x != id_bahan]
        alok_rows = p.get('alokasiBeratBahan')
        new_alok = []
        if isinstance(alok_rows, list):
            for r in alok_rows:
                if not isinstance(r, dict):
                    continue
                bid = str(r.get('idBahan', '') or '').strip()
                if not bid or bid == id_bahan:
                    continue
                try:
                    bw = float(r.get('berat', 0) or 0)
                except (TypeError, ValueError):
                    bw = 0.0
                new_alok.append({'idBahan': bid, 'berat': bw})
        old_bw = float(p.get('beratAwal', 0) or 0)
        new_bw = max(0.0, round(old_bw - removed_w, 4))
        primary = new_ids[0] if new_ids else ''
        fields = {
            'idBahanList': new_ids,
            'idBahan': primary,
            'alokasiBeratBahan': new_alok,
            'beratAwal': new_bw,
            'bahanMasterBerubahLepasOtomatis': True,
            'bahanMasterBerubahLepasPada': datetime.now().isoformat(),
        }
        try:
            bt_f = float(p.get('beratTerkini'))
        except (TypeError, ValueError):
            bt_f = None
        if bt_f is not None:
            if new_bw <= 1e-6:
                fields['beratTerkini'] = 0.0
            elif bt_f > new_bw:
                fields['beratTerkini'] = new_bw
        try:
            ba_f = float(p.get('beratAkhir')) if p.get('beratAkhir') is not None else None
        except (TypeError, ValueError):
            ba_f = None
        if ba_f is not None:
            if new_bw <= 1e-6:
                fields['beratAkhir'] = None
            elif ba_f > new_bw:
                fields['beratAkhir'] = round(min(ba_f, new_bw), 4)
        db.produksi.update_one(
            {'_id': p['_id']},
            {
                '$set': fields,
                '$unset': {
                    'bahanMasterAlokasiDisesuaikan': '',
                    'bahanMasterAlokasiDisesuaikanPada': '',
                },
            },
        )
        updated += 1
    if updated:
        print(
            f"✅ [CASCADE BAHAN→PRODUKSI] idBahan={id_bahan}: "
            f"melepaskan dari {updated} dokumen produksi (dari {matched} kandidat)."
        )
    return {'matched': matched, 'updated': updated}


def _cascade_rename_master_proses_pengolahan(old_nama, new_nama, master_id_proses=None):
    """
    Saat nama proses di dataProses diubah, perbarui semua salinan string nama lama
    (produksi, bahan.prosesBahan, pemesanan, hasilProduksi) agar validasi master
    seperti validate_sequential_tahapan tidak gagal dengan 'tidak ditemukan'.

    Selain kesamaan string persis di DB, nama yang sama setelah .strip()
    (mis. spasi depan/belakang) juga diselaraskan.
    """
    old_nama = (old_nama or '').strip()
    new_nama = (new_nama or '').strip()
    if not old_nama or not new_nama or old_nama == new_nama:
        return {
            'produksi_updated': 0,
            'bahan_updated': 0,
            'pemesanan_updated': 0,
            'hasilProduksi_updated': 0,
            'denorm_via_idProses': {'produksi': 0, 'hasilProduksi': 0, 'bahan': 0},
        }
    stats = {
        'produksi_updated': 0,
        'bahan_updated': 0,
        'pemesanan_updated': 0,
        'hasilProduksi_updated': 0,
        'denorm_via_idProses': {'produksi': 0, 'hasilProduksi': 0, 'bahan': 0},
    }
    mid = _int_proses_id(master_id_proses)
    if mid is not None:
        rden = db.produksi.update_many(
            {'idProses': mid},
            {'$set': {'prosesPengolahan': new_nama}},
        )
        stats['denorm_via_idProses']['produksi'] = int(rden.modified_count or 0)
        rh = db.hasilProduksi.update_many(
            {'idProses': mid},
            {'$set': {'prosesPengolahan': new_nama}},
        )
        stats['denorm_via_idProses']['hasilProduksi'] = int(rh.modified_count or 0)
        for bdoc in db.bahan.find({'prosesBahan': {'$elemMatch': {'idProses': mid}}}):
            blines = list(bdoc.get('prosesBahan') or [])
            chb = False
            for row in blines:
                if isinstance(row, dict) and _int_proses_id(row.get('idProses')) == mid:
                    row['prosesPengolahan'] = new_nama
                    chb = True
            if chb:
                db.bahan.update_one({'_id': bdoc['_id']}, {'$set': {'prosesBahan': blines}})
                stats['denorm_via_idProses']['bahan'] += 1
    rx_trim = re.compile(r'^\s*%s\s*$' % re.escape(old_nama))

    r_prod = db.produksi.update_many(
        {'prosesPengolahan': old_nama},
        {'$set': {'prosesPengolahan': new_nama}},
    )
    r_prod2 = db.produksi.update_many(
        {'prosesPengolahan': rx_trim},
        {'$set': {'prosesPengolahan': new_nama}},
    )
    stats['produksi_updated'] = int(
        (r_prod.modified_count or 0) + (r_prod2.modified_count or 0)
    )

    r_hasil = db.hasilProduksi.update_many(
        {'prosesPengolahan': old_nama},
        {'$set': {'prosesPengolahan': new_nama}},
    )
    r_hasil2 = db.hasilProduksi.update_many(
        {'prosesPengolahan': rx_trim},
        {'$set': {'prosesPengolahan': new_nama}},
    )
    stats['hasilProduksi_updated'] = int(
        (r_hasil.modified_count or 0) + (r_hasil2.modified_count or 0)
    )

    def _apply_bahan_proses_lines():
        bahan_queries = (
            {'prosesBahan.prosesPengolahan': old_nama},
            {'prosesBahan': {'$elemMatch': {'prosesPengolahan': rx_trim}}},
        )
        seen_ids = set()
        for query in bahan_queries:
            for doc in db.bahan.find(query):
                did = doc.get('_id')
                if did in seen_ids:
                    continue
                lines = list(doc.get('prosesBahan') or [])
                changed = False
                for line in lines:
                    if not isinstance(line, dict):
                        continue
                    if (line.get('prosesPengolahan') or '').strip() == old_nama:
                        line['prosesPengolahan'] = new_nama
                        changed = True
                if changed:
                    db.bahan.update_one({'_id': did}, {'$set': {'prosesBahan': lines}})
                    stats['bahan_updated'] += 1
                    seen_ids.add(did)

    _apply_bahan_proses_lines()

    pem_queries = (
        {
            '$or': [
                {'prosesPengolahan': old_nama},
                {'kloter.prosesPengolahan': old_nama},
                {'items.prosesPengolahan': old_nama},
            ]
        },
        {
            '$or': [
                {'prosesPengolahan': rx_trim},
                {'kloter': {'$elemMatch': {'prosesPengolahan': rx_trim}}},
                {'items': {'$elemMatch': {'prosesPengolahan': rx_trim}}},
            ]
        },
    )
    pem_seen = set()
    for pem_filter in pem_queries:
        for doc in db.pemesanan.find(pem_filter):
            pid = doc.get('_id')
            if pid in pem_seen:
                continue
            set_fields = {}
            if (doc.get('prosesPengolahan') or '').strip() == old_nama:
                set_fields['prosesPengolahan'] = new_nama
            for arr_key in ('kloter', 'items'):
                arr = doc.get(arr_key)
                if not isinstance(arr, list):
                    continue
                new_arr = []
                row_changed = False
                for row in arr:
                    if isinstance(row, dict) and (row.get('prosesPengolahan') or '').strip() == old_nama:
                        new_row = dict(row)
                        new_row['prosesPengolahan'] = new_nama
                        new_arr.append(new_row)
                        row_changed = True
                    else:
                        new_arr.append(row)
                if row_changed:
                    set_fields[arr_key] = new_arr
            if set_fields:
                db.pemesanan.update_one({'_id': pid}, {'$set': set_fields})
                stats['pemesanan_updated'] += 1
                pem_seen.add(pid)

    total = (
        stats['produksi_updated']
        + stats['bahan_updated']
        + stats['pemesanan_updated']
        + stats['hasilProduksi_updated']
    )
    dn = stats.get('denorm_via_idProses')
    if isinstance(dn, dict):
        total += sum(int(v or 0) for v in dn.values())
    if total:
        dprod = dn.get('produksi') if isinstance(dn, dict) else 0
        dhasil = dn.get('hasilProduksi') if isinstance(dn, dict) else 0
        dbah = dn.get('bahan') if isinstance(dn, dict) else 0
        print(
            f"✅ [RENAME PROSES] '{old_nama}' → '{new_nama}': "
            f"produksi={stats['produksi_updated']}, bahan={stats['bahan_updated']}, "
            f"pemesanan={stats['pemesanan_updated']}, hasilProduksi={stats['hasilProduksi_updated']}, "
            f"denormId(prod/hasil/bahan)={dprod}/{dhasil}/{dbah}"
        )
    return stats


def _last_snapshot_pengeringan_awal(produksi_lama):
    """
    Ambil kadar air & berat terkini acuan dari Pengeringan Awal terakhir
    (dokumen saat ini jika sedang di tahap itu, atau entri history terbaru).
    Dipakai saat validasi Pengeringan Akhir setelah tahap antara (mis. hulling pertama / Pulping 2).
    """
    if not produksi_lama:
        return None, None
    st = (produksi_lama.get('statusTahapan') or '')
    if 'Pengeringan Awal' in st and produksi_lama.get('kadarAir') is not None:
        try:
            ka = float(produksi_lama['kadarAir'])
        except (TypeError, ValueError):
            ka = None
        try:
            bt = float(produksi_lama['beratTerkini']) if produksi_lama.get('beratTerkini') is not None else None
        except (TypeError, ValueError):
            bt = None
        if ka is not None:
            return ka, bt
    hist = produksi_lama.get('historyTahapan') or []
    if not isinstance(hist, list):
        return None, None
    for entry in reversed(hist):
        if not isinstance(entry, dict):
            continue
        nama = (entry.get('namaTahapan') or entry.get('statusTahapanSebelumnya') or '')
        if 'Pengeringan Awal' not in nama:
            continue
        ka = entry.get('kadarAir')
        bt = entry.get('beratTerkini')
        if ka is None:
            continue
        try:
            ka_f = float(ka)
        except (TypeError, ValueError):
            continue
        try:
            bt_f = float(bt) if bt is not None else None
        except (TypeError, ValueError):
            bt_f = None
        return ka_f, bt_f
    return None, None


# Helper function untuk validasi khusus tahapan Pengeringan Awal dan Akhir
def validate_pengeringan_tahapan(status_tahapan_baru, kadar_air_baru, berat_terkini_baru, produksi_lama=None):
    """
    Validasi khusus untuk tahapan Pengeringan Awal dan Pengeringan Akhir.
    
    Args:
        status_tahapan_baru: Status tahapan baru
        kadar_air_baru: Kadar air baru (wajib untuk Pengeringan Awal & Akhir)
        berat_terkini_baru: Berat terkini baru
        produksi_lama: Data produksi lama (untuk validasi Pengeringan Akhir)
    
    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        # Normalisasi status tahapan
        status_normalized = status_tahapan_baru
        if 'Pengeringan Awal' in status_tahapan_baru:
            status_normalized = 'Pengeringan Awal'
        elif 'Pengeringan Akhir' in status_tahapan_baru:
            status_normalized = 'Pengeringan Akhir'
        
        # Validasi kadar air wajib untuk Pengeringan Awal & Akhir
        if status_normalized in ['Pengeringan Awal', 'Pengeringan Akhir']:
            if not kadar_air_baru or kadar_air_baru < 0 or kadar_air_baru > 100:
                return False, f'Kadar air wajib diisi untuk tahapan {status_normalized} (0-100%)'
        
        # Validasi khusus untuk Pengeringan Akhir
        if status_normalized == 'Pengeringan Akhir':
            # Harus ada produksi lama untuk validasi (hanya untuk update mode)
            if not produksi_lama:
                # Untuk create mode, Pengeringan Akhir tidak bisa langsung dipilih (harus melalui Pengeringan Awal dulu)
                # Validasi sequential akan menangani ini
                return True, None  # Biarkan validasi sequential menangani
            
            status_lama = (produksi_lama.get('statusTahapan') or '').strip()
            # Alur lama: langsung setelah Pengeringan Awal. Alur baru: setelah hulling pertama (Pulping 2).
            sl = status_lama
            boleh_dari_awal = 'Pengeringan Awal' in sl
            boleh_dari_pulping2 = (
                sl == 'Pulping 2'
                or 'Pulping 2' in sl
                or 'Pengupasan Kulit Tanduk (Hulling) Pertama' in sl
            )
            if not (boleh_dari_awal or boleh_dari_pulping2):
                return False, (
                    'Pengeringan Akhir hanya dapat dipilih jika tahapan sebelumnya '
                    'adalah Pengeringan Awal atau Pengupasan Kulit Tanduk (Hulling) Pertama (sesuai alur yang dikonfigurasi).'
                )

            kadar_air_awal, berat_terkini_awal = _last_snapshot_pengeringan_awal(produksi_lama)

            # Validasi kadar air Pengeringan Akhir harus lebih kecil dari acuan Pengeringan Awal (jika ada)
            if kadar_air_awal is not None:
                if kadar_air_baru >= kadar_air_awal:
                    return False, f'Kadar air Pengeringan Akhir ({kadar_air_baru}%) harus lebih kecil dari kadar air Pengeringan Awal ({kadar_air_awal}%)'

            # Validasi berat terkini Pengeringan Akhir ≤ acuan berat setelah Pengeringan Awal (jika ada)
            if berat_terkini_awal is not None:
                if berat_terkini_baru > berat_terkini_awal:
                    return False, f'Berat terkini Pengeringan Akhir ({berat_terkini_baru} kg) tidak boleh lebih besar dari berat terkini Pengeringan Awal ({berat_terkini_awal} kg)'
        
        return True, None
    except Exception as e:
        return False, f'Error validasi tahapan pengeringan: {str(e)}'

# ==================== AUTHENTICATION & SESSION HELPERS ====================

def check_auth_session():
    """Check if user is authenticated via sessionStorage"""
    # Since we're using sessionStorage on client-side, we'll check via request headers or cookies
    # For now, we'll allow access and let client-side auth-guard handle it
    # This function can be extended to check server-side session if needed
    return True

def get_user_role_from_session():
    """Get user role from session (can be extended for server-side sessions)"""
    # Currently handled client-side via sessionStorage
    return None

# ==================== BRAND ASSETS (invoice, dll.) ====================

@app.route('/brand-assets/logo.png')
def brand_logo_damarkandang():
    """Logo Damarkandang untuk invoice/PDF."""
    static_img = join(_APP_ROOT_DIR, 'static', 'img')
    if exists(join(static_img, 'logo.png')):
        return send_from_directory(static_img, 'logo.png', mimetype='image/png')
    img_dir = join(_APP_ROOT_DIR, 'Image')
    if exists(join(img_dir, 'logo.png')):
        return send_from_directory(img_dir, 'logo.png', mimetype='image/png')
    return jsonify({'error': 'Logo tidak ditemukan'}), 404


# ==================== MAIN ROUTES ====================

@app.route('/')
def welcome():
    """Welcome page - entry point for all users"""
    return render_template('welcome.html')

@app.route('/login')
def login():
    """Login page - Admin"""
    return render_template('login.html')

@app.route('/login/karyawan')
def login_karyawan():
    """Login page - Karyawan"""
    return render_template('login_karyawan.html')

@app.route('/login/owner')
def login_owner():
    """Login page - Owner"""
    return render_template('login_owner.html')

@app.route('/register')
def register():
    """Registration page"""
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    """Dashboard - Admin (requires auth)"""
    # Debug: Log session state
    print(f"🔍 Dashboard access check:")
    print(f"   Session keys: {list(session.keys())}")
    print(f"   user_id in session: {'user_id' in session}")
    print(f"   username: {session.get('username', 'NOT SET')}")
    print(f"   role: {session.get('role', 'NOT SET')}")
    print(f"   Request origin: {request.headers.get('Origin', 'N/A')}")
    print(f"   Request host: {request.headers.get('Host', 'N/A')}")
    
    # Server-side session check - if not logged in, redirect to welcome
    if 'user_id' not in session or not session.get('username') or not session.get('role'):
        print("❌ Session check failed - redirecting to welcome")
        return redirect(url_for('welcome'))
    # Role check - only Admin can access this dashboard
    if session.get('role') != 'Admin':
        print(f"❌ Role check failed - User role: {session.get('role')}, Required: Admin")
        return redirect(url_for('welcome'))
    
    print(f"✅ Dashboard access granted for {session.get('username')}")
    # Auth check will also be done client-side via auth-guard.js for additional protection
    return render_template('index.html')

@app.route('/dashboard/karyawan')
def dashboard_karyawan():
    """Dashboard - Karyawan (requires auth)"""
    # Server-side session check - if not logged in, redirect to welcome
    if 'user_id' not in session or not session.get('username') or not session.get('role'):
        return redirect(url_for('welcome'))
    # Role check - only Karyawan can access this dashboard
    if session.get('role') != 'Karyawan':
        return redirect(url_for('welcome'))
    # Auth check will also be done client-side via auth-guard.js for additional protection
    return render_template('index_karyawan.html')

@app.route('/dashboard/owner')
def dashboard_owner():
    """Dashboard - Owner (requires auth)"""
    # Server-side session check - if not logged in, redirect to welcome
    if 'user_id' not in session or not session.get('username') or not session.get('role'):
        return redirect(url_for('welcome'))
    # Role check - only Owner can access this dashboard
    if session.get('role') != 'Owner':
        return redirect(url_for('welcome'))
    # Auth check will also be done client-side via auth-guard.js for additional protection
    return render_template('index_owner.html')

# ==================== MANAGEMENT ROUTES ====================

@app.route('/kelola/pengguna')
def kelola_pengguna():
    """User management page"""
    from app.config import CAFE_NAME
    return render_template('pengguna/index.html', cafe_name=CAFE_NAME, active_menu='pengguna')

@app.route('/kelola/bahan')
def kelola_bahan():
    """Kelola bahan baku cafe"""
    return redirect(url_for('cafe_pages.bahan_page'))

@app.route('/kelola/bahan/karyawan')
def kelola_bahan_karyawan():
    return redirect(url_for('cafe_pages.bahan_page'))

@app.route('/kelola/produksi')
def kelola_produksi():
    """Fitur produksi Argopuro tidak dipakai di cafe Damarkandang."""
    return redirect(url_for('dashboard'))

@app.route('/kelola/produksi/karyawan')
def kelola_produksi_karyawan():
    """Karyawan cafe diarahkan ke penjualan, bukan input produksi."""
    return redirect(url_for('kelola_pemesanan'))

@app.route('/kelola/hasil-produksi')
def kelola_hasil_produksi():
    """Redirect: stok otomatis dari produksi tahap Pengemasan, tidak ada input hasil produksi manual."""
    return redirect(url_for('kelola_stok'))

@app.route('/kelola/hasil-produksi/karyawan')
def kelola_hasil_produksi_karyawan():
    """Hapus: fitur hasil produksi tidak tersedia untuk karyawan."""
    return redirect(url_for('dashboard_karyawan'))

@app.route('/kelola/pemasok')
def kelola_pemasok():
    return redirect(url_for('dashboard'))

@app.route('/kelola/stok')
def kelola_stok():
    """Stok bahan baku cafe"""
    from app.config import CAFE_NAME
    return render_template('stok/index.html', cafe_name=CAFE_NAME, active_menu='stok')

@app.route('/kelola/keuangan')
def kelola_keuangan():
    from app.config import CAFE_NAME
    return render_template(
        'keuangan/unified.html',
        cafe_name=CAFE_NAME,
        active_menu='keuangan',
    )

@app.route('/kelola/data')
def kelola_data():
    from app.config import CAFE_NAME
    return render_template('kelola_data/cafe_master.html', cafe_name=CAFE_NAME, active_menu='kelola-data')

@app.route('/kelola/sanitasi')
def kelola_sanitasi():
    return redirect(url_for('dashboard'))

@app.route('/kelola/sanitasi/karyawan')
def kelola_sanitasi_karyawan():
    return redirect(url_for('dashboard_karyawan'))

@app.route('/kelola/laporan')
def kelola_laporan():
    """Rekapan & laporan cafe Damarkandang"""
    from app.config import CAFE_NAME
    return render_template('laporan/index.html', cafe_name=CAFE_NAME, active_menu='laporan')

@app.route('/kelola/laporan/owner')
def kelola_laporan_owner():
    """Laporan cafe untuk Owner"""
    from app.config import CAFE_NAME
    return render_template('laporan/index.html', cafe_name=CAFE_NAME, active_menu='laporan')

@app.route('/kelola/pemesanan')
def kelola_pemesanan():
    from app.config import CAFE_NAME
    return render_template('kasir/dashboard.html', cafe_name=CAFE_NAME, active_menu='kasir')

@app.route('/kelola/pemesanan/tambah')
def kelola_pemesanan_tambah():
    from app.config import CAFE_NAME
    return render_template('kasir/tambah.html', cafe_name=CAFE_NAME, active_menu='kasir')

@app.route('/profile')
def profile():
    """Profile page"""
    return render_template('profile.html')

@app.route('/profile/karyawan')
def profile_karyawan():
    """Profile page - Karyawan"""
    return render_template('profile_karyawan.html')

@app.route('/profile/owner')
def profile_owner():
    """Profile page - Owner"""
    return render_template('profile_owner.html')

@app.route('/pengaturan')
def pengaturan():
    """Settings page"""
    return render_template('pengaturan.html')

@app.route('/pengaturan/karyawan')
def pengaturan_karyawan():
    """Settings page - Karyawan"""
    return render_template('pengaturan_karyawan.html')

@app.route('/pengaturan/owner')
def pengaturan_owner():
    """Settings page - Owner"""
    return render_template('pengaturan_owner.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint.

    Railway sering butuh respons cepat untuk readiness/liveness.
    Jadi endpoint ini akan selalu balas HTTP 200 (status 'ok') dan
    hanya menginformasikan status koneksi MongoDB secara best-effort.
    """
    # Jika env MongoDB belum diset, tetap balas 200 agar container dianggap responsive
    if not MONGODB_URI or not DB_NAME:
        return jsonify({
            'status': 'ok',
            'database': 'missing_config',
            'message': 'Backend is running, MongoDB env is not configured'
        }), 200

    # Best-effort ping Mongo dengan timeout kecil supaya tidak menggantung
    try:
        test_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=1000)
        test_client.admin.command('ping')
        return jsonify({
            'status': 'ok',
            'database': 'connected',
            'message': 'Backend is running and MongoDB is connected'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'ok',
            'database': 'disconnected',
            'error': str(e)
        }), 200


def _normalize_catatan_produksi(raw):
    """Catatan opsional pada dokumen produksi; teks dipotong aman."""
    if raw is None:
        return ''
    s = str(raw).strip()
    if len(s) > 2000:
        s = s[:2000]
    return s


def _upsert_catatan_per_tahapan(existing, nama_tahapan, catatan, tanggal_sekarang):
    """
    Menyimpan catatan per nama tahapan. Entri dengan nama tahapan yang sama diganti
    (update berulang di tahap yang sama). Saat pindah tahap, tahap lama dibekukan
    lalu tahap baru diisi dari form — teks boleh sama (mengikuti alur pembaruan).
    """
    existing = list(existing) if isinstance(existing, list) else []
    key = (nama_tahapan or '').strip()
    norm = _normalize_catatan_produksi(catatan)
    if tanggal_sekarang is not None and not isinstance(tanggal_sekarang, str):
        tgl = str(tanggal_sekarang)
    else:
        tgl = tanggal_sekarang or ''
    row = {
        'namaTahapan': key,
        'catatan': norm,
        'tanggalSekarang': tgl,
    }
    for i, r in enumerate(existing):
        nk = (r.get('namaTahapan') or r.get('tahapan') or '').strip()
        if nk == key:
            existing[i] = row
            return existing
    existing.append(row)
    return existing


# Urutan tampilan daftar produksi (GET /api/produksi): grup per tahapan, lalu idProduksi.
# Roasting disisipkan sebelum Pengemasan untuk data legacy.
_URUTAN_TAHAPAN_PRODUKSI_SORT = (
    'Sortasi', 'Pengeringan Awal Pertama', 'Fermentasi', 'Pulping', 'Pencucian',
    'Pengeringan Awal', 'Fermentasi 2', 'Pulping 2', 'Pengeringan Akhir',
    'Hulling', 'Hand Sortasi', 'Grinding', 'Roasting', 'Pengemasan',
)
_URUTAN_TAHAPAN_PRODUKSI_SORT_INDEX = {n: i for i, n in enumerate(_URUTAN_TAHAPAN_PRODUKSI_SORT)}
_PRODUKSI_STATUS_LABEL_KE_KANON_SORT = {
    'Sortasi Cherry atau Buah Kopi': 'Sortasi',
    'Sortasi Buah': 'Sortasi',
    'Pengeringan Awal Pertama (Para - Para)': 'Pengeringan Awal Pertama',
    'Pengeringan Awal Pertama': 'Pengeringan Awal Pertama',
    'Pengeringan Awal (Para - Para)': 'Pengeringan Awal',
    'Pengeringan Awal kedua (Para - Para)': 'Pengeringan Awal',
    'Pengeringan Akhir (Pengeringan Lantai)': 'Pengeringan Akhir',
    'Pengupasan Kulit Tanduk (Hulling) Pertama': 'Pulping 2',
    'Pengupasan Kulit Tanduk (Hulling) Kedua': 'Hulling',
    'Pengupasan Kulit Tanduk (Hulling)': 'Hulling',
    'Hand Sortasi atau Sortasi Biji Kopi': 'Hand Sortasi',
    'Fermentasi': 'Fermentasi',
    'Pulping': 'Pulping',
    'Pencucian': 'Pencucian',
    'Pengeringan Awal': 'Pengeringan Awal',
    'Fermentasi 2': 'Fermentasi 2',
    'Pulping 2': 'Pulping 2',
    'Pengeringan Akhir': 'Pengeringan Akhir',
    'Grinding': 'Grinding',
    'Pengemasan': 'Pengemasan',
    'Roasting': 'Roasting',
    'Hulling': 'Hulling',
    'Sortasi': 'Sortasi',
    'Hand Sortasi': 'Hand Sortasi',
}
for _n in _URUTAN_TAHAPAN_PRODUKSI_SORT:
    _PRODUKSI_STATUS_LABEL_KE_KANON_SORT.setdefault(_n, _n)
_TAHAPAN_SORT_KEYS_BY_LEN = sorted(
    _PRODUKSI_STATUS_LABEL_KE_KANON_SORT.keys(),
    key=len,
    reverse=True,
)


def _canonical_tahapan_produksi_sort(status_tahapan):
    """Normalisasi statusTahapan (label panjang atau kunci) ke nama kanonik untuk indeks urutan."""
    s = (status_tahapan or '').strip()
    if not s:
        return None
    m = _PRODUKSI_STATUS_LABEL_KE_KANON_SORT
    if s in m:
        return m[s]
    for k in _TAHAPAN_SORT_KEYS_BY_LEN:
        if k in s:
            return m[k]
    return None


def _produksi_sort_key(doc):
    """Kunci sort: urutan tahapan naik, lalu idProduksi leksikografis."""
    canon = _canonical_tahapan_produksi_sort(doc.get('statusTahapan'))
    idx = _URUTAN_TAHAPAN_PRODUKSI_SORT_INDEX.get(canon, 999)
    idp = str(doc.get('idProduksi') or '')
    return (idx, idp)


# ==================== PRODUKSI ENDPOINTS ====================

@app.route('/api/produksi/next-id', methods=['GET'])
def get_next_id_produksi():
    """Get next auto-generated idProduksi (format PRD-YYYYMM-XXXX) for preview. Does NOT increment counter."""
    try:
        id_produksi = get_next_id_produksi_preview()
        return jsonify({'idProduksi': id_produksi}), 200
    except Exception as e:
        print(f"❌ [PRODUKSI NEXT-ID] ERROR: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/produksi', methods=['GET'])
def get_produksi():
    """Get all produksi data"""
    try:
        produksi = list(db.produksi.find())
        produksi.sort(key=_produksi_sort_key)
        print(f"📊 [PRODUKSI GET] Retrieved {len(produksi)} documents from MongoDB collection 'produksi'")
        return jsonify(json_serialize(produksi)), 200
    except Exception as e:
        print(f"❌ [PRODUKSI GET] ERROR: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/produksi/<produksi_id>', methods=['GET'])
def get_produksi_by_id(produksi_id):
    """Get produksi by ID or idProduksi"""
    try:
        # Try to find by MongoDB _id first
        try:
            produksi = db.produksi.find_one({'_id': ObjectId(produksi_id)})
            if produksi:
                return jsonify(json_serialize(produksi)), 200
        except:
            pass
        
        # Try to find by idProduksi (string)
        produksi = db.produksi.find_one({'idProduksi': produksi_id})
        if produksi:
            return jsonify(json_serialize(produksi)), 200
        
        # Try to find by id (number)
        try:
            produksi = db.produksi.find_one({'id': int(produksi_id)})
            if produksi:
                return jsonify(json_serialize(produksi)), 200
        except:
            pass
        
        return jsonify({'error': 'Produksi not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _normalize_berat_terkini_detail_kloter_produksi(data):
    """Detail kloter opsional untuk berat terkini (maks. 100 baris)."""
    raw = data.get('beratTerkiniDetailKloter')
    if raw is None:
        return None, None
    if not isinstance(raw, list):
        return None, 'beratTerkiniDetailKloter harus berupa array'
    if len(raw) > 100:
        return None, 'Maksimal 100 kloter untuk pencatatan berat terkini'
    out = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            continue
        try:
            b = float(row.get('berat', 0) or 0)
        except (TypeError, ValueError):
            return None, 'Berat kloter tidak valid'
        if b < 0:
            return None, 'Berat kloter tidak boleh negatif'
        out.append({
            'kloter': int(row.get('kloter', i + 1)),
            'berat': b,
            'keterangan': (row.get('keterangan') or '').strip()
        })
    return out, None


@app.route('/api/produksi/upload-foto-tahapan', methods=['POST'])
def upload_produksi_foto_tahapan():
    """Unggah foto opsional untuk pencatatan update tahapan produksi (disimpan di static/uploads)."""
    try:
        url, err = _save_uploaded_foto_tahapan_produksi_file()
        if err:
            return jsonify({'error': err}), 400
        return jsonify({'fotoTahapan': url}), 200
    except Exception as e:
        print(f'❌ upload_produksi_foto_tahapan: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/produksi', methods=['POST'])
def create_produksi():
    """Create new produksi. idProduksi is auto-generated by backend (format PRD-YYYYMM-XXXX)."""
    try:
        data = request.json
        
        # Validate required fields (idProduksi NOT required - backend generates it)
        # idBahan / idBahanList: minimal satu ID bahan (multi-bahan satu proses)
        # kadarAir hanya wajib untuk tahapan Pengeringan Awal & Akhir
        required_fields = ['beratAwal',
                          'varietas', 'tanggalMasuk', 'tanggalSekarang',
                          'statusTahapan', 'haccp']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        if (
            ('idProses' not in data or data.get('idProses') is None or str(data.get('idProses')).strip() == '')
            and (not data.get('prosesPengolahan') or not str(data.get('prosesPengolahan')).strip())
        ):
            return jsonify({'error': 'Wajib menyediakan idProses atau prosesPengolahan'}), 400
        
        raw_list = data.get('idBahanList')
        if isinstance(raw_list, list) and len(raw_list) > 0:
            id_bahan_list = [str(x).strip() for x in raw_list if str(x).strip()]
        elif data.get('idBahan'):
            id_bahan_list = [str(data['idBahan']).strip()]
        else:
            return jsonify({'error': 'Wajib menyediakan idBahanList atau idBahan'}), 400
        
        if len(id_bahan_list) < 1:
            return jsonify({'error': 'Minimal satu ID Bahan'}), 400
        if len(id_bahan_list) != len(set(id_bahan_list)):
            return jsonify({'error': 'ID Bahan tidak boleh duplikat dalam satu produksi'}), 400
        
        master_proses_doc, pid_proses, proses_pp, err_proses = _resolve_proses_dari_payload(data)
        if err_proses:
            return jsonify({'error': err_proses}), 400
        used_globally = _all_id_bahan_terpakai_produksi(None)

        berat_awal_req = float(data['beratAwal'])
        alokasi_rows = data.get('alokasiBeratBahan')
        alokasi_clean = []
        if isinstance(alokasi_rows, list) and len(alokasi_rows) > 0:
            for r in alokasi_rows:
                if not isinstance(r, dict):
                    continue
                bid = str(r.get('idBahan') or '').strip()
                bw = float(r.get('berat', 0) or 0)
                if bid and bw > 0:
                    alokasi_clean.append({'idBahan': bid, 'berat': bw})
        elif len(id_bahan_list) == 1:
            alokasi_clean = [{'idBahan': id_bahan_list[0], 'berat': berat_awal_req}]
        else:
            return jsonify({'error': 'alokasiBeratBahan wajib jika lebih dari satu ID Bahan'}), 400
        
        ids_in_alok = {a['idBahan'] for a in alokasi_clean}
        if ids_in_alok != set(id_bahan_list):
            return jsonify({'error': 'alokasiBeratBahan harus memuat setiap ID Bahan yang dipilih tepat sekali'}), 400
        
        sum_alok = sum(a['berat'] for a in alokasi_clean)
        if abs(sum_alok - berat_awal_req) > 1e-4:
            return jsonify({'error': 'Jumlah alokasiBeratBahan harus sama dengan beratAwal'}), 400
        
        # Auto-generate idProduksi (ignore any value from frontend)
        id_produksi = generate_id_produksi()

        legacy_overlap = []
        bahan_by_id = {}
        for bid in id_bahan_list:
            bahan_one = db.bahan.find_one({'idBahan': bid})
            if not bahan_one:
                return jsonify({'error': f'Bahan tidak ditemukan: {bid}'}), 400
            bahan_by_id[bid] = bahan_one
            if not (bahan_one.get('prosesBahan') or []) and bid in used_globally:
                legacy_overlap.append(bid)
        if legacy_overlap:
            return jsonify({
                'error': 'ID bahan berikut sudah terpakai di produksi lain',
                'idBahanTerpakai': sorted(set(legacy_overlap)),
            }), 400
        
        # Validasi per bahan: proses terdaftar + sisa cukup
        for bid in id_bahan_list:
            bahan_one = bahan_by_id[bid]
            lines = bahan_one.get('prosesBahan') or []
            need = next((a['berat'] for a in alokasi_clean if a['idBahan'] == bid), 0)
            if lines:
                line = None
                if pid_proses is not None:
                    line = next(
                        (
                            l for l in lines
                            if isinstance(l, dict) and _int_proses_id(l.get('idProses')) == pid_proses
                        ),
                        None,
                    )
                if line is None:
                    line = next(
                        (l for l in lines if (l.get('prosesPengolahan') or '').strip() == proses_pp),
                        None,
                    )
                if not line:
                    return jsonify({'error': f'Proses "{proses_pp}" tidak terdaftar pada bahan {bid}'}), 400
                sisa, err = _sisa_bahan_line(bahan_one, bid, proses_pp, id_proses=pid_proses)
                if err:
                    return jsonify({'error': f'{bid}: {err}'}), 400
                if need > (sisa or 0) + 1e-4:
                    return jsonify({
                        'error': 'Sisa bahan tidak mencukupi',
                        'idBahan': bid,
                        'sisaTersedia': sisa,
                        'beratDiminta': need,
                    }), 400
            else:
                sisa, err = _sisa_bahan_line(bahan_one, bid, None)
                if err:
                    return jsonify({'error': f'{bid}: {err}'}), 400
                if need > (sisa or 0) + 1e-4:
                    return jsonify({
                        'error': 'Sisa bahan tidak mencukupi',
                        'idBahan': bid,
                        'sisaTersedia': sisa,
                        'beratDiminta': need,
                    }), 400
        
        id_bahan_primary = id_bahan_list[0]
        
        # Validasi sequential tahapan berdasarkan konfigurasi master
        is_valid, error_msg = validate_sequential_tahapan_dengan_master(
            master_proses_doc,
            data['statusTahapan'],
            None,
        )
        if not is_valid:
            return jsonify({'error': error_msg}), 400
        
        # Get and validate beratTerkini (required for every production stage)
        beratTerkini = data.get('beratTerkini')
        if not beratTerkini or beratTerkini <= 0:
            return jsonify({'error': 'Berat terkini wajib diisi dan harus lebih dari 0'}), 400
        if beratTerkini > data['beratAwal']:
            return jsonify({'error': 'Berat terkini tidak boleh lebih besar dari berat awal'}), 400
        
        detail_bt_kloter, err_detail_bt = _normalize_berat_terkini_detail_kloter_produksi(data)
        if err_detail_bt:
            return jsonify({'error': err_detail_bt}), 400
        metode_bt = data.get('metodeBeratTerkini') or 'total'
        if metode_bt not in ('total', 'kloter'):
            metode_bt = 'total'
        
        # Validasi khusus untuk tahapan Pengeringan Awal & Akhir
        kadar_air = data.get('kadarAir')
        is_valid_pengeringan, error_msg_pengeringan = validate_pengeringan_tahapan(
            data['statusTahapan'],
            kadar_air,
            beratTerkini,
            None  # Tidak ada produksi lama untuk create mode
        )
        if not is_valid_pengeringan:
            return jsonify({'error': error_msg_pengeringan}), 400
        
        # Saat Pengemasan: berat akhir + berat green beans (wajib) + berat pixel (opsional)
        beratAkhir = None
        beratGreenBeans = None
        beratPixel = None
        if 'Pengemasan' in data['statusTahapan']:
            beratAkhir = data.get('beratAkhir')
            if not beratAkhir or beratAkhir <= 0:
                return jsonify({'error': 'Berat akhir wajib diisi jika status tahapan adalah Pengemasan'}), 400
            if beratAkhir > data['beratAwal']:
                return jsonify({'error': 'Berat akhir tidak boleh lebih besar dari berat awal'}), 400
            if beratAkhir > beratTerkini:
                return jsonify({'error': 'Berat akhir tidak boleh lebih besar dari berat terkini'}), 400
            # Validasi berat green beans (wajib)
            beratGreenBeans = data.get('beratGreenBeans')
            if not beratGreenBeans or beratGreenBeans <= 0:
                return jsonify({'error': 'Berat Green Beans wajib diisi untuk tahap Pengemasan'}), 400
            if beratGreenBeans > beratAkhir:
                return jsonify({'error': 'Berat Green Beans tidak boleh lebih besar dari berat akhir'}), 400
            # Validasi berat pixel (opsional)
            beratPixel = data.get('beratPixel') or 0
            if beratPixel < 0:
                return jsonify({'error': 'Berat Produk Pixel tidak boleh bernilai negatif'}), 400
            # Total berat tidak boleh lebih dari berat akhir
            if (beratGreenBeans + beratPixel) > beratAkhir:
                return jsonify({'error': 'Total berat Green Beans + Pixel tidak boleh lebih besar dari berat akhir'}), 400
        
        # Get next ID
        new_id = get_next_id('produksi')
        
        # Tentukan kadar air: bisa diinputkan untuk semua tahapan
        # Wajib untuk Pengeringan Awal & Akhir, optional untuk lainnya
        kadar_air_value = None
        if 'kadarAir' in data and data['kadarAir'] is not None:
            # Jika ada input kadar air, gunakan nilai tersebut
            kadar_air_value = float(data.get('kadarAir', 0))
        elif 'Pengeringan' in data['statusTahapan']:
            # Untuk tahapan Pengeringan, wajib ada kadar air
            kadar_air_value = float(data.get('kadarAir', 0))
        
        # Initialize history
        # Kadar air bisa diinputkan untuk semua tahapan
        kadar_air_history = kadar_air_value
        
        historyTahapan = [{
            'namaTahapan': data['statusTahapan'],  # Nama tahapan
            'statusTahapan': data['statusTahapan'],
            'tanggal': data['tanggalSekarang'],
            'tanggalUpdate': datetime.now().isoformat(),  # Tanggal update
            'beratAwal': data['beratAwal'],
            'beratTerkini': float(beratTerkini),
            'beratAkhir': float(beratAkhir) if beratAkhir else None,
            'kadarAir': kadar_air_history  # Kadar air bisa diinputkan untuk semua tahapan
        }]
        foto_tahapan_baru = _sanitize_foto_tahapan_path(data.get('fotoTahapan'))
        if foto_tahapan_baru:
            historyTahapan[0]['fotoTahapan'] = foto_tahapan_baru
        
        catatan_norm = _normalize_catatan_produksi(data.get('catatan'))
        produksi_data = {
            'id': new_id,
            'idProduksi': id_produksi,
            'idBahan': id_bahan_primary,
            'idBahanList': id_bahan_list,
            'alokasiBeratBahan': alokasi_clean,
            'beratAwal': float(data['beratAwal']),
            'beratTerkini': float(beratTerkini),
            'beratAkhir': float(beratAkhir) if beratAkhir else None,
            'idProses': pid_proses,
            'prosesPengolahan': proses_pp,
            'kadarAir': kadar_air_value,  # Kadar air bisa diinputkan untuk semua tahapan
            'varietas': data['varietas'],
            'tanggalMasuk': data['tanggalMasuk'],
            'tanggalSekarang': data['tanggalSekarang'],
            'statusTahapan': data['statusTahapan'],
            'haccp': data['haccp'],
            'historyTahapan': historyTahapan,
            'metodeBeratTerkini': metode_bt,
            'catatan': catatan_norm,
            'catatanPerTahapan': _upsert_catatan_per_tahapan(
                [], data['statusTahapan'], catatan_norm, data.get('tanggalSekarang')
            ),
        }
        if foto_tahapan_baru:
            produksi_data['fotoTahapan'] = foto_tahapan_baru
        if detail_bt_kloter:
            produksi_data['beratTerkiniDetailKloter'] = detail_bt_kloter
        if 'Pengemasan' in data['statusTahapan']:
            produksi_data['beratGreenBeans'] = float(beratGreenBeans) if beratGreenBeans else 0
            produksi_data['beratPixel'] = float(beratPixel) if beratPixel else 0
            produksi_data['tanggalPengemasan'] = data.get('tanggalSekarang') or datetime.now().strftime('%Y-%m-%d')
        
        print(f"🔵 [PRODUKSI CREATE] Inserting to MongoDB collection 'produksi': {produksi_data}")
        result = db.produksi.insert_one(produksi_data)
        produksi_data['_id'] = result.inserted_id
        print(f"✅ [PRODUKSI CREATE] Successfully inserted! ID: {result.inserted_id}, Collection: produksi")
        return jsonify(json_serialize(produksi_data)), 201
    except Exception as e:
        print(f"❌ [PRODUKSI CREATE] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/produksi/<produksi_id>', methods=['PUT'])
def update_produksi(produksi_id):
    """Update produksi"""
    try:
        data = request.json
        foto_path_client = _sanitize_foto_tahapan_path(
            (data or {}).get('fotoTahapan')
        )
        
        # Find existing produksi
        try:
            produksi = db.produksi.find_one({'_id': ObjectId(produksi_id)})
        except:
            produksi = db.produksi.find_one({'id': int(produksi_id)}) or \
                      db.produksi.find_one({'idProduksi': produksi_id})
        
        if not produksi:
            return jsonify({'error': 'Produksi not found'}), 404
        
        # Validate required fields
        # kadarAir hanya wajib untuk tahapan Pengeringan Awal & Akhir
        required_fields = ['idProduksi', 'idBahan', 'beratAwal',
                          'varietas', 'tanggalMasuk', 'tanggalSekarang', 
                          'statusTahapan', 'haccp']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        if (
            ('idProses' not in data or data.get('idProses') is None or str(data.get('idProses')).strip() == '')
            and (not data.get('prosesPengolahan') or not str(data.get('prosesPengolahan')).strip())
        ):
            return jsonify({'error': 'Wajib menyediakan idProses atau prosesPengolahan'}), 400
        
        # Check if idProduksi already exists (excluding current)
        existing = db.produksi.find_one({
            'idProduksi': data['idProduksi'],
            '_id': {'$ne': produksi['_id']}
        })
        if existing:
            return jsonify({'error': 'ID Produksi already exists'}), 400
        
        # Edit: biasanya hanya boleh menambah id & alokasi lama tidak boleh diubah;
        # setelah master bahan berubah (bahanMasterBerubahLepasOtomatis), boleh hapus/ubah alokasi lalu centang ulang.
        old_ids = _id_bahan_list_from_produksi(produksi)
        old_set = set(old_ids)
        old_map = _alokasi_map_from_produksi(produksi)
        new_raw = data.get('idBahanList')
        if isinstance(new_raw, list) and len(new_raw) > 0:
            new_list = [str(x).strip() for x in new_raw if str(x).strip()]
        else:
            new_list = [str(data.get('idBahan') or '').strip()] if data.get('idBahan') else []
        new_set = set(new_list)
        boleh_kurangi_atau_ubah_alokasi = bool(
            produksi.get('bahanMasterBerubahLepasOtomatis')
        )
        if not boleh_kurangi_atau_ubah_alokasi and not old_set <= new_set:
            return jsonify({
                'error': 'Hanya boleh menambah ID Bahan pada produksi ini; tidak boleh menghapus bahan yang sudah tercatat',
            }), 400
        if len(new_list) != len(new_set):
            return jsonify({'error': 'idBahanList tidak boleh mengandung duplikat'}), 400

        added_ids = new_set - old_set
        st_lama = produksi.get('statusTahapan')
        st_baru = data.get('statusTahapan')
        if added_ids and (
            _status_tambah_bahan_dikunci(st_lama) or _status_tambah_bahan_dikunci(st_baru)
        ):
            return jsonify({
                'error': 'Menambah ID Bahan tidak diizinkan mulai tahap Pengemasan.',
            }), 400

        alokasi_req = data.get('alokasiBeratBahan')
        new_alok_rows = []
        if isinstance(alokasi_req, list):
            for r in alokasi_req:
                if not isinstance(r, dict):
                    continue
                bid = str(r.get('idBahan') or '').strip()
                bw = float(r.get('berat', 0) or 0)
                if bid and bw >= 0:
                    new_alok_rows.append({'idBahan': bid, 'berat': bw})
        new_map = {r['idBahan']: r['berat'] for r in new_alok_rows}
        if set(new_map.keys()) != new_set:
            return jsonify({'error': 'alokasiBeratBahan harus memuat tepat satu entri per id di idBahanList'}), 400

        for bid in old_set:
            if bid not in new_set:
                continue
            o = float(old_map.get(bid, 0) or 0)
            n = float(new_map.get(bid, 0) or 0)
            if not boleh_kurangi_atau_ubah_alokasi and abs(o - n) > 1e-3:
                return jsonify({
                    'error': f'Alokasi bahan {bid} tidak boleh diubah; hanya boleh menambah bahan baru',
                }), 400

        master_proses_doc, pid_proses, proses_pp, err_proses = _resolve_proses_dari_payload(data)
        if err_proses:
            return jsonify({'error': err_proses}), 400
        for bid in new_set:
            need = float(new_map.get(bid, 0) or 0)
            if need <= 0:
                return jsonify({'error': f'Berat alokasi untuk bahan {bid} harus lebih dari 0'}), 400
            old_w = float(old_map.get(bid, 0) or 0)
            is_new = bid not in old_set
            if not is_new and not (
                boleh_kurangi_atau_ubah_alokasi and abs(need - old_w) > 1e-5
            ):
                continue
            bahan_one = db.bahan.find_one({'idBahan': bid})
            if not bahan_one:
                return jsonify({'error': f'Bahan tidak ditemukan: {bid}'}), 400
            lines = bahan_one.get('prosesBahan') or []
            if lines:
                line = None
                if pid_proses is not None:
                    line = next(
                        (
                            l for l in lines
                            if isinstance(l, dict) and _int_proses_id(l.get('idProses')) == pid_proses
                        ),
                        None,
                    )
                if line is None:
                    line = next(
                        (l for l in lines if (l.get('prosesPengolahan') or '').strip() == proses_pp),
                        None,
                    )
                if not line:
                    return jsonify({'error': f'Proses "{proses_pp}" tidak terdaftar pada bahan {bid}'}), 400
                sisa, err = _sisa_bahan_line(bahan_one, bid, proses_pp, id_proses=pid_proses)
                if err:
                    return jsonify({'error': f'{bid}: {err}'}), 400
                room = (sisa or 0) + (old_w if bid in old_set else 0)
                if need > room + 1e-3:
                    return jsonify({
                        'error': (
                            'Sisa bahan tidak mencukupi untuk bahan tambahan'
                            if is_new
                            else 'Sisa bahan tidak mencukupi untuk alokasi baru (setelah master diubah)'
                        ),
                        'idBahan': bid,
                        'sisaTersedia': room,
                        'beratDiminta': need,
                    }), 400
            else:
                sisa, err = _sisa_bahan_line(bahan_one, bid, None)
                if err:
                    return jsonify({'error': f'{bid}: {err}'}), 400
                room = (sisa or 0) + (old_w if bid in old_set else 0)
                if need > room + 1e-3:
                    return jsonify({
                        'error': (
                            'Sisa bahan tidak mencukupi untuk bahan tambahan'
                            if is_new
                            else 'Sisa bahan tidak mencukupi untuk alokasi baru (setelah master diubah)'
                        ),
                        'idBahan': bid,
                        'sisaTersedia': room,
                        'beratDiminta': need,
                    }), 400

        berat_baru = float(data['beratAwal'])
        sum_alok = sum(float(new_map[b]) for b in new_list)
        if abs(berat_baru - sum_alok) > 1e-3:
            return jsonify({'error': 'beratAwal harus sama dengan jumlah alokasi semua ID bahan'}), 400

        # Proses pengolahan ditetapkan saat bahan masuk — tidak boleh diubah (id utama, nama legacy)
        p_id_simpan = _int_proses_id(produksi.get('idProses'))
        if p_id_simpan is not None and pid_proses is not None:
            if p_id_simpan != pid_proses:
                return jsonify({'error': 'Proses pengolahan tidak dapat diubah setelah produksi dibuat'}), 400
        elif (produksi.get('prosesPengolahan') or '').strip() != proses_pp:
            return jsonify({'error': 'Proses pengolahan tidak dapat diubah setelah produksi dibuat'}), 400
        
        # Validasi sequential tahapan berdasarkan konfigurasi master
        status_tahapan_lama = produksi.get('statusTahapan')
        is_valid, error_msg = validate_sequential_tahapan_dengan_master(
            master_proses_doc,
            data['statusTahapan'],
            status_tahapan_lama,
        )
        if not is_valid:
            return jsonify({'error': error_msg}), 400
        
        # Get and validate beratTerkini
        # Saat Pengemasan: berat terkini tidak wajib diisi (gunakan nilai terakhir dari data lama)
        # Untuk tahapan lain: berat terkini wajib diisi
        isPengemasan = 'Pengemasan' in data['statusTahapan']
        beratTerkini = data.get('beratTerkini')
        
        berat_awal_req = float(data.get('beratAwal', 0) or 0)
        alokasi_ulang_setelah_master = bool(
            produksi.get('bahanMasterBerubahLepasOtomatis') and berat_awal_req < 1e-6
        )

        if isPengemasan:
            # Saat Pengemasan: gunakan nilai dari data lama jika tidak ada di request
            if not beratTerkini or beratTerkini <= 0:
                # Ambil dari produksi lama (nilai terakhir sebelum pengemasan)
                beratTerkini = produksi.get('beratTerkini') or produksi.get('beratAwal') or 0
                if beratTerkini <= 0:
                    return jsonify({'error': 'Berat terkini tidak valid. Pastikan produksi sudah memiliki berat terkini sebelum masuk tahap Pengemasan'}), 400
        else:
            # Untuk tahapan lain: wajib diisi — kecuali menunggu alokasi ulang setelah master bahan diubah
            if alokasi_ulang_setelah_master:
                try:
                    beratTerkini = float(beratTerkini) if beratTerkini is not None else 0.0
                except (TypeError, ValueError):
                    beratTerkini = 0.0
                if beratTerkini < 0:
                    return jsonify({'error': 'Berat terkini tidak boleh negatif'}), 400
                if beratTerkini > berat_awal_req + 1e-6:
                    return jsonify({'error': 'Berat terkini tidak boleh lebih besar dari berat awal'}), 400
            else:
                if not beratTerkini or beratTerkini <= 0:
                    return jsonify({'error': 'Berat terkini wajib diisi dan harus lebih dari 0 setiap kali update tahapan'}), 400
                if beratTerkini > data['beratAwal']:
                    return jsonify({'error': 'Berat terkini tidak boleh lebih besar dari berat awal'}), 400
        
        detail_bt_kloter, err_detail_bt = _normalize_berat_terkini_detail_kloter_produksi(data)
        if err_detail_bt:
            return jsonify({'error': err_detail_bt}), 400
        metode_bt = data.get('metodeBeratTerkini') or 'total'
        if metode_bt not in ('total', 'kloter'):
            metode_bt = 'total'
        
        # Saat Pengemasan: berat akhir + berat green beans (wajib) + berat pixel (opsional)
        beratAkhir = None
        beratGreenBeans = None
        beratPixel = None
        if 'Pengemasan' in data['statusTahapan']:
            beratAkhir = data.get('beratAkhir')
            if not beratAkhir or beratAkhir <= 0:
                return jsonify({'error': 'Berat akhir wajib diisi jika status tahapan adalah Pengemasan'}), 400
            if beratAkhir > data['beratAwal']:
                return jsonify({'error': 'Berat akhir tidak boleh lebih besar dari berat awal'}), 400
            if beratAkhir > beratTerkini:
                return jsonify({'error': 'Berat akhir tidak boleh lebih besar dari berat terkini'}), 400
            # Validasi berat green beans (wajib)
            beratGreenBeans = data.get('beratGreenBeans') or produksi.get('beratGreenBeans')
            if not beratGreenBeans or beratGreenBeans <= 0:
                return jsonify({'error': 'Berat Green Beans wajib diisi untuk tahap Pengemasan'}), 400
            if beratGreenBeans > beratAkhir:
                return jsonify({'error': 'Berat Green Beans tidak boleh lebih besar dari berat akhir'}), 400
            # Validasi berat pixel (opsional)
            beratPixel = data.get('beratPixel') or produksi.get('beratPixel') or 0
            if beratPixel < 0:
                return jsonify({'error': 'Berat Produk Pixel tidak boleh bernilai negatif'}), 400
            # Total berat tidak boleh lebih dari berat akhir
            if (beratGreenBeans + beratPixel) > beratAkhir:
                return jsonify({'error': 'Total berat Green Beans + Pixel tidak boleh lebih besar dari berat akhir'}), 400
        
        # Validasi khusus untuk tahapan Pengeringan Awal & Akhir
        kadar_air = data.get('kadarAir')
        if not (alokasi_ulang_setelah_master and berat_awal_req < 1e-6):
            is_valid_pengeringan, error_msg_pengeringan = validate_pengeringan_tahapan(
                data['statusTahapan'],
                kadar_air,
                beratTerkini,
                produksi  # Ada produksi lama untuk validasi Pengeringan Akhir
            )
            if not is_valid_pengeringan:
                return jsonify({'error': error_msg_pengeringan}), 400
        
        # Update history if status changed (always record beratTerkini when updating)
        historyTahapan = produksi.get('historyTahapan', [])
        statusChanged = produksi.get('statusTahapan') != data['statusTahapan']
        beratTerkiniChanged = produksi.get('beratTerkini') != float(beratTerkini)
        kadarAirChanged = produksi.get('kadarAir') != float(kadar_air) if kadar_air else False
        
        # Add to history if status changed or if this is a weight/kadar air update for the same stage
        if statusChanged or beratTerkiniChanged or kadarAirChanged:
            # Tentukan kadar air untuk history
            # Gunakan kadar air baru jika ada, jika tidak gunakan kadar air lama
            kadar_air_history = None
            if 'kadarAir' in data and data['kadarAir'] is not None:
                kadar_air_history = float(data.get('kadarAir', 0))
            else:
                kadar_air_history = produksi.get('kadarAir')
            
            # Save current state to history before update dengan informasi lengkap
            history_entry = {
                'namaTahapan': produksi.get('statusTahapan'),  # Nama tahapan
                'statusTahapanSebelumnya': produksi.get('statusTahapan'),
                'tanggal': produksi.get('tanggalSekarang'),
                'tanggalUpdate': datetime.now().isoformat(),  # Tanggal update
                'waktu': datetime.now().isoformat(),
                'beratAwal': produksi.get('beratAwal'),
                'beratTerkini': produksi.get('beratTerkini'),
                'beratAkhir': produksi.get('beratAkhir'),
                'kadarAir': kadar_air_history,  # Kadar air (bisa diinputkan untuk semua tahapan)
                'catatan': _normalize_catatan_produksi(produksi.get('catatan')),
                'pengguna': 'System',  # TODO: Ambil dari session jika ada
                'userId': None  # TODO: Ambil dari session jika ada
            }
            
            # Jika status berubah, tambahkan informasi status baru
            if statusChanged:
                history_entry['statusTahapanBaru'] = data['statusTahapan']
                history_entry['namaTahapan'] = data['statusTahapan']  # Update nama tahapan
            if foto_path_client:
                history_entry['fotoTahapan'] = foto_path_client
            
            historyTahapan.append(history_entry)
        
        # Tentukan kadar air: bisa diinputkan untuk semua tahapan
        # Wajib untuk Pengeringan Awal & Akhir, optional untuk lainnya
        kadar_air_value = None
        if 'kadarAir' in data and data['kadarAir'] is not None:
            # Jika ada input kadar air, gunakan nilai tersebut
            kadar_air_value = float(data.get('kadarAir', 0))
        elif 'Pengeringan' in data['statusTahapan']:
            # Untuk tahapan Pengeringan, wajib ada kadar air
            kadar_air_value = float(data.get('kadarAir', 0))
        else:
            # Untuk tahapan non-pengeringan, gunakan nilai lama jika ada, atau None
            kadar_air_value = produksi.get('kadarAir')
        
        old_status = (produksi.get('statusTahapan') or '').strip()
        new_status = (data['statusTahapan'] or '').strip()
        cp = produksi.get('catatanPerTahapan')
        if not isinstance(cp, list):
            cp = []
        else:
            cp = list(cp)
        if old_status != new_status:
            cp = _upsert_catatan_per_tahapan(
                cp,
                old_status,
                produksi.get('catatan'),
                produksi.get('tanggalSekarang'),
            )
        catatan_baru = (
            _normalize_catatan_produksi(data.get('catatan'))
            if 'catatan' in data
            else _normalize_catatan_produksi(produksi.get('catatan'))
        )
        cp = _upsert_catatan_per_tahapan(
            cp, new_status, catatan_baru, data.get('tanggalSekarang')
        )

        primary_id_bahan = old_ids[0] if old_ids else (new_list[0] if new_list else data.get('idBahan'))
        update_data = {
            'idProduksi': data['idProduksi'],
            'idBahan': primary_id_bahan,
            'idBahanList': new_list,
            'alokasiBeratBahan': new_alok_rows,
            'beratAwal': float(data['beratAwal']),
            'beratTerkini': float(beratTerkini),
            'beratAkhir': float(beratAkhir) if beratAkhir else None,
            'idProses': pid_proses,
            'prosesPengolahan': proses_pp,
            'kadarAir': kadar_air_value,
            'varietas': data['varietas'],
            'tanggalMasuk': data['tanggalMasuk'],
            'tanggalSekarang': data['tanggalSekarang'],
            'statusTahapan': data['statusTahapan'],
            'haccp': data['haccp'],
            'historyTahapan': historyTahapan,
            'catatan': _normalize_catatan_produksi(data.get('catatan'))
            if 'catatan' in data
            else (produksi.get('catatan') or ''),
            'catatanPerTahapan': cp,
        }
        if foto_path_client:
            update_data['fotoTahapan'] = foto_path_client
        if not isPengemasan:
            update_data['metodeBeratTerkini'] = metode_bt
            update_data['beratTerkiniDetailKloter'] = detail_bt_kloter
        if 'Pengemasan' in data['statusTahapan']:
            update_data['beratGreenBeans'] = float(beratGreenBeans) if beratGreenBeans else 0
            update_data['beratPixel'] = float(beratPixel) if beratPixel else 0
            update_data['tanggalPengemasan'] = data.get('tanggalSekarang') or datetime.now().strftime('%Y-%m-%d')

        mongo_update = {'$set': update_data}
        if new_list and float(data['beratAwal']) > 0:
            mongo_update['$unset'] = {
                'bahanMasterBerubahLepasOtomatis': '',
                'bahanMasterBerubahLepasPada': '',
                'bahanMasterAlokasiDisesuaikan': '',
                'bahanMasterAlokasiDisesuaikanPada': '',
            }

        db.produksi.update_one({'_id': produksi['_id']}, mongo_update)

        updated = db.produksi.find_one({'_id': produksi['_id']})
        return jsonify(json_serialize(updated)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/produksi/<produksi_id>', methods=['DELETE'])
def delete_produksi(produksi_id):
    """Delete produksi"""
    try:
        # Find produksi
        try:
            produksi = db.produksi.find_one({'_id': ObjectId(produksi_id)})
        except:
            produksi = db.produksi.find_one({'id': int(produksi_id)}) or \
                      db.produksi.find_one({'idProduksi': produksi_id})
        
        if not produksi:
            return jsonify({'error': 'Produksi not found'}), 404
        
        # Tidak boleh hapus jika ada pemesanan (ordering) yang sudah diproses untuk produksi ini
        hasil_count = db.hasilProduksi.count_documents({'idProduksi': produksi.get('idProduksi')})
        if hasil_count > 0:
            return jsonify({
                'error': f'Tidak dapat menghapus produksi. Ada {hasil_count} pemesanan yang sudah diproses untuk produksi ini.'
            }), 400
        
        db.produksi.delete_one({'_id': produksi['_id']})
        return jsonify({'message': 'Produksi deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/produksi/pengemasan', methods=['GET'])
def get_produksi_pengemasan():
    """Get produksi that are in Pengemasan status with berat akhir"""
    try:
        produksi = list(db.produksi.find({
            'statusTahapan': {'$regex': 'Pengemasan', '$options': 'i'},
            'beratAkhir': {'$exists': True, '$ne': None, '$gt': 0}
        }).sort('id', 1))
        return jsonify(json_serialize(produksi)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/produksi/<produksi_id>/sisa', methods=['GET'])
def get_produksi_sisa(produksi_id):
    """Sisa pool green beans = (berat akhir − pixel) − pemesanan GB; sisa pixel terpisah."""
    try:
        produksi = db.produksi.find_one({'idProduksi': produksi_id})
        if not produksi:
            try:
                produksi = db.produksi.find_one({'_id': ObjectId(produksi_id)})
            except:
                produksi = db.produksi.find_one({'id': int(produksi_id)})
        
        if not produksi:
            return jsonify({'error': 'Produksi not found'}), 404
        
        berat_akhir = float(produksi.get('beratAkhir') or 0)
        if berat_akhir <= 0:
            return jsonify({
                'idProduksi': produksi.get('idProduksi'),
                'beratAkhir': 0,
                'totalDariOrdering': 0,
                'sisaTersedia': 0,
                'error': 'Produksi belum memiliki berat akhir'
            }), 200
        
        id_p = produksi.get('idProduksi')
        hasil_list = list(db.hasilProduksi.find({'idProduksi': id_p}))
        px = float(produksi.get('beratPixel') or 0)
        pool_gb = max(0.0, berat_akhir - px)
        total_ordering_gb = sum(
            float(h.get('beratSaatIni', 0))
            for h in hasil_list
            if h.get('isFromOrdering') in (True, 'true', 1)
            and (h.get('tipeProduk') or '').strip() == 'Green Beans'
        )
        total_ordering_px = sum(
            float(h.get('beratSaatIni', 0))
            for h in hasil_list
            if h.get('isFromOrdering') in (True, 'true', 1)
            and (h.get('tipeProduk') or '').strip() == 'Pixel'
        )
        sisa_gb = max(0, pool_gb - total_ordering_gb)
        sisa_px = max(0, px - total_ordering_px)
        # sisaTersedia = sisa pool green beans (selaras stok & pemesanan GB)
        sisa_tersedia = sisa_gb
        
        return jsonify({
            'idProduksi': produksi.get('idProduksi'),
            'beratAkhir': berat_akhir,
            'beratPixel': px,
            'poolGreenBeans': pool_gb,
            'totalDariOrderingGreenBeans': total_ordering_gb,
            'totalDariOrderingPixel': total_ordering_px,
            'sisaTersedia': sisa_tersedia,
            'sisaTersediaPixel': sisa_px,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== HASIL PRODUKSI ENDPOINTS ====================

@app.route('/api/hasil-produksi', methods=['GET'])
def get_hasil_produksi():
    """Get all hasil produksi data"""
    try:
        hasil_produksi = list(db.hasilProduksi.find().sort('id', 1))
        print(f"📊 [HASIL PRODUKSI GET] Retrieved {len(hasil_produksi)} documents from MongoDB collection 'hasilProduksi'")
        return jsonify(json_serialize(hasil_produksi)), 200
    except Exception as e:
        print(f"❌ [HASIL PRODUKSI GET] ERROR: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/hasil-produksi/<hasil_id>', methods=['GET'])
def get_hasil_produksi_by_id(hasil_id):
    """Get hasil produksi by ID"""
    try:
        try:
            hasil = db.hasilProduksi.find_one({'_id': ObjectId(hasil_id)})
        except:
            hasil = db.hasilProduksi.find_one({'id': int(hasil_id)})
        
        if not hasil:
            return jsonify({'error': 'Hasil produksi not found'}), 404
        
        return jsonify(json_serialize(hasil)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POST/PUT/DELETE hasil produksi dihapus: stok otomatis dari produksi tahap Pengemasan.
# GET tetap ada untuk kebutuhan ordering dan kompatibilitas.

@app.route('/api/hasil-produksi/produksi/<id_produksi>', methods=['GET'])
def get_hasil_produksi_by_produksi(id_produksi):
    """Get all hasil produksi by idProduksi"""
    try:
        hasil_list = list(db.hasilProduksi.find({'idProduksi': id_produksi}).sort('id', 1))
        return jsonify(json_serialize(hasil_list)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Helper function for packaging calculation
def calculate_jumlah_kemasan(berat_saat_ini, kemasan, tipe_produk_lower):
    """Calculate jumlah kemasan based on weight and packaging size"""
    # Apply 20% reduction for Pixel products (roasting shrinkage)
    efektif_berat = berat_saat_ini
    if 'pixel' in tipe_produk_lower:
        efektif_berat = berat_saat_ini * 0.8
    
    if not kemasan or efektif_berat <= 0:
        return 0
    
    # Parse ukuran kemasan to kg
    ukuran_kg = 0
    try:
        kemasan_lower = kemasan.lower().strip()
        if 'kg' in kemasan_lower:
            # Green beans: "5 kg" -> 5, "5kg" -> 5, " 5 kg " -> 5
            # Extract number before "kg"
            import re
            match = re.search(r'([\d.]+)\s*kg', kemasan_lower)
            if match:
                ukuran_kg = float(match.group(1))
            else:
                # Fallback: remove "kg" and parse
                ukuran_kg = float(kemasan_lower.replace('kg', '').strip())
        elif 'gram' in kemasan_lower or 'gr' in kemasan_lower:
            # Kopi sangrai/bubuk: "250 gram" -> 0.25 kg, "250gr" -> 0.25 kg
            import re
            match = re.search(r'([\d.]+)\s*(?:gram|gr)', kemasan_lower)
            if match:
                ukuran_kg = float(match.group(1)) / 1000
            else:
                # Fallback: remove "gram"/"gr" and parse
                ukuran_kg = float(kemasan_lower.replace('gram', '').replace('gr', '').strip()) / 1000
    except (ValueError, AttributeError) as e:
        print(f"⚠️ [CALCULATE KEMASAN] Error parsing kemasan '{kemasan}': {str(e)}")
        return 0
    
    if ukuran_kg > 0:
        # Use floor division untuk konsistensi dengan frontend
        return int(efektif_berat / ukuran_kg)
    return 0

# ==================== BAHAN ENDPOINTS ====================

def _sync_keuangan_pengeluaran_bahan_masuk(bahan_doc):
    """
    Otomatis sinkron baris keuangan untuk pembelian bahan baku.
    - Satu idBahan -> maksimal satu baris keuangan jenis "Pembelian Bahan Baku"
    - Dibuat/diupdate berdasarkan master bahan (tanggalMasuk + totalPengeluaran)
    """
    try:
        if not bahan_doc:
            return
        id_bahan = str(bahan_doc.get('idBahan') or '').strip()
        if not id_bahan:
            return

        tanggal = (bahan_doc.get('tanggalMasuk') or '').strip() or datetime.now().strftime('%Y-%m-%d')
        nilai = float(bahan_doc.get('totalPengeluaran') or 0)
        if nilai < 0:
            nilai = 0

        q = {
            'jenisPengeluaran': 'Pembelian Bahan Baku',
            'idBahanBaku': id_bahan,
        }
        existing = db.keuangan.find_one(q)
        payload = {
            'tanggal': tanggal,
            'jenisPengeluaran': 'Pembelian Bahan Baku',
            'idBahanBaku': id_bahan,
            'notes': f'Otomatis dari bahan masuk {id_bahan}',
            'nilai': round(nilai, 2),
            'source': 'bahan',  # field tambahan untuk menandai asal (tidak wajib dipakai frontend)
        }

        if existing:
            db.keuangan.update_one({'_id': existing['_id']}, {'$set': payload})
        else:
            new_id = get_next_id('keuangan')
            payload['id'] = new_id
            db.keuangan.insert_one(payload)
    except Exception as e:
        # Jangan gagalkan proses bahan hanya karena sinkron keuangan
        print(f"⚠️ [SYNC KEUANGAN<-BAHAN] ERROR: {str(e)}")

@app.route('/api/bahan-produksi', methods=['GET'])
def get_bahan():
    """Get all bahan data (produksi kopi — legacy)"""
    try:
        bahan = list(db.bahan.find({'idBahan': {'$exists': True}}).sort('id', 1))
        print(f"📊 [BAHAN GET] Retrieved {len(bahan)} documents from MongoDB collection 'bahan'")
        return jsonify(json_serialize(bahan)), 200
    except Exception as e:
        print(f"❌ [BAHAN GET] ERROR: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bahan-produksi/next-id', methods=['GET'])
def get_next_id_bahan():
    """Get next auto-generated idBahan (format BHN001, BHN002, ...)"""
    try:
        id_bahan = generate_id_bahan()
        return jsonify({'idBahan': id_bahan}), 200
    except Exception as e:
        print(f"❌ [BAHAN NEXT-ID] ERROR: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bahan-produksi/<bahan_id>', methods=['GET'])
def get_bahan_by_id(bahan_id):
    """Get bahan by ID or idBahan"""
    try:
        try:
            bahan = db.bahan.find_one({'_id': ObjectId(bahan_id)})
        except:
            bahan = db.bahan.find_one({'idBahan': bahan_id}) or \
                   db.bahan.find_one({'id': int(bahan_id)})
        
        if not bahan:
            return jsonify({'error': 'Bahan not found'}), 404
        
        return jsonify(json_serialize(bahan)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bahan-produksi', methods=['POST'])
def create_bahan():
    """Create new bahan.
    Format utama: prosesBahan[] (per proses: prosesPengolahan + detailKloter[]), hargaPerKg sekali, idBahan auto.
    Legacy single-row (idBahan + jumlah manual) tetap didukung tanpa field kualitas.
    """
    try:
        data = request.json
        
        proses_bahan_raw = data.get('prosesBahan')
        if proses_bahan_raw and isinstance(proses_bahan_raw, list) and len(proses_bahan_raw) > 0:
            harga_per_kg = float(data.get('hargaPerKg', 0) or 0)
            if harga_per_kg <= 0:
                return jsonify({'error': 'Harga per Kg wajib diisi dan harus lebih dari 0'}), 400
            
            proses_bahan_clean, total_berat, err = _normalize_proses_bahan_payload(proses_bahan_raw)
            if err:
                return jsonify({'error': err}), 400
            
            for field in ['pemasok', 'varietas', 'jenisKopi', 'tanggalMasuk']:
                if field not in data:
                    return jsonify({'error': f'Missing required field: {field}'}), 400
            
            total_pengeluaran = harga_per_kg * total_berat
            new_id = get_next_id('bahan')
            id_bahan = f"BHN{str(new_id).zfill(3)}"
            
            bahan_data = {
                'id': new_id,
                'idBahan': id_bahan,
                'pemasok': data['pemasok'],
                'jumlah': total_berat,
                'varietas': data['varietas'],
                'hargaPerKg': round(harga_per_kg, 2),
                'totalPengeluaran': round(total_pengeluaran, 2),
                'jenisKopi': data['jenisKopi'],
                'tanggalMasuk': data['tanggalMasuk'],
                'prosesBahan': proses_bahan_clean
            }
        else:
            # Legacy mode: single values (tanpa kualitas)
            required_fields = ['idBahan', 'pemasok', 'jumlah', 'varietas',
                              'hargaPerKg', 'totalPengeluaran', 'jenisKopi',
                              'tanggalMasuk']
            for field in required_fields:
                if field not in data:
                    return jsonify({'error': f'Missing required field: {field}'}), 400
            
            existing = db.bahan.find_one({'idBahan': data['idBahan']})
            if existing:
                return jsonify({'error': 'ID Bahan already exists'}), 400
            
            new_id = get_next_id('bahan')
            
            bahan_data = {
                'id': new_id,
                'idBahan': data['idBahan'],
                'pemasok': data['pemasok'],
                'jumlah': float(data['jumlah']),
                'varietas': data['varietas'],
                'hargaPerKg': float(data['hargaPerKg']),
                'totalPengeluaran': float(data['totalPengeluaran']),
                'jenisKopi': data['jenisKopi'],
                'tanggalMasuk': data['tanggalMasuk'],
            }
        
        # Check idBahan unique
        existing = db.bahan.find_one({'idBahan': bahan_data['idBahan']})
        if existing:
            return jsonify({'error': 'ID Bahan already exists'}), 400
        
        # HACCP if provided
        if 'haccp' in data:
            bahan_data['haccp'] = data['haccp']

        bahan_data['lunas'] = parse_bool_payload(data.get('lunas'), False)
        
        print(f"🔵 [BAHAN CREATE] Inserting to MongoDB collection 'bahan': {bahan_data}")
        result = db.bahan.insert_one(bahan_data)
        bahan_data['_id'] = result.inserted_id
        print(f"✅ [BAHAN CREATE] Successfully inserted! ID: {result.inserted_id}, Collection: bahan")

        # Otomatis buat/update pengeluaran keuangan untuk pembelian bahan baku
        _sync_keuangan_pengeluaran_bahan_masuk(bahan_data)

        return jsonify(json_serialize(bahan_data)), 201
    except Exception as e:
        print(f"❌ [BAHAN CREATE] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/bahan-produksi/<bahan_id>', methods=['PUT'])
def update_bahan(bahan_id):
    """Update bahan"""
    try:
        data = request.json
        
        try:
            bahan = db.bahan.find_one({'_id': ObjectId(bahan_id)})
        except:
            bahan = db.bahan.find_one({'id': int(bahan_id)}) or \
                   db.bahan.find_one({'idBahan': bahan_id})
        
        if not bahan:
            return jsonify({'error': 'Bahan not found'}), 404

        old_id_bahan = str(bahan.get('idBahan') or '').strip()
        
        # Check if idBahan already exists (excluding current)
        if 'idBahan' in data:
            existing = db.bahan.find_one({
                'idBahan': data['idBahan'],
                '_id': {'$ne': bahan['_id']}
            })
            if existing:
                return jsonify({'error': 'ID Bahan already exists'}), 400
        
        update_data = {}
        extra_unset = {}
        for field in ['idBahan', 'pemasok', 'varietas', 'jenisKopi', 'tanggalMasuk']:
            if field in data:
                update_data[field] = data[field]
        
        if 'prosesBahan' in data and isinstance(data.get('prosesBahan'), list):
            harga_per_kg = float(data.get('hargaPerKg', 0) or 0)
            if harga_per_kg <= 0:
                return jsonify({'error': 'Harga per Kg wajib diisi dan harus lebih dari 0'}), 400
            proses_bahan_clean, total_berat, err = _normalize_proses_bahan_payload(data['prosesBahan'])
            if err:
                return jsonify({'error': err}), 400
            update_data['prosesBahan'] = proses_bahan_clean
            update_data['jumlah'] = total_berat
            update_data['hargaPerKg'] = round(harga_per_kg, 2)
            update_data['totalPengeluaran'] = round(harga_per_kg * total_berat, 2)
            extra_unset['detailKloter'] = ''
            extra_unset['kualitas'] = ''
        else:
            # Legacy: detailKloter flat (bahan tanpa prosesBahan)
            detail_kloter = data.get('detailKloter') or data.get('kloter')
            if detail_kloter and isinstance(detail_kloter, list):
                harga_per_kg = float(data.get('hargaPerKg', 0) or 0)
                if harga_per_kg <= 0:
                    return jsonify({'error': 'Harga per Kg wajib diisi dan harus lebih dari 0'}), 400
                
                total_berat = 0
                detail_kloter_clean = []
                for i, k in enumerate(detail_kloter):
                    berat = float(k.get('berat', 0) or 0)
                    if berat > 0:
                        total_berat += berat
                        detail_kloter_clean.append({
                            'kloter': len(detail_kloter_clean) + 1,
                            'berat': berat,
                            'keterangan': k.get('keterangan', '') or ''
                        })
                if total_berat > 0:
                    update_data['jumlah'] = total_berat
                    update_data['hargaPerKg'] = round(harga_per_kg, 2)
                    update_data['totalPengeluaran'] = round(harga_per_kg * total_berat, 2)
                    update_data['detailKloter'] = detail_kloter_clean
            else:
                for field in ['jumlah', 'hargaPerKg', 'totalPengeluaran']:
                    if field in data:
                        update_data[field] = float(data[field])
        
        if 'haccp' in data:
            update_data['haccp'] = data['haccp']

        if 'lunas' in data:
            update_data['lunas'] = parse_bool_payload(data.get('lunas'), False)
        
        update_op = {'$set': update_data}
        if extra_unset:
            update_op['$unset'] = extra_unset

        id_bahan_untuk_cascade = str(bahan.get('idBahan') or '').strip()

        db.bahan.update_one({'_id': bahan['_id']}, update_op)

        # Catatan: prosesPengolahan pada dokumen produksi TIDAK disamakan dengan master bahan.
        # Produksi tetap mencerminkan pilihan saat dibuat. Jika struktur/berat proses bahan
        # berubah (bukan ekuivalen stok), cascade di bawah melepaskan idBahan dari produksi
        # agar batch lama tidak tertimpa dan bahan bisa dialokasikan ulang sesuai master baru.

        # Ubahan stok/master: lepaskan ID bahan dari semua produksi (centang terbuka / pilih ulang)
        cascade_stok = False
        if 'prosesBahan' in update_data:
            cascade_stok = not _proses_bahan_stok_equivalent(
                bahan.get('prosesBahan'),
                update_data['prosesBahan'],
            )
        elif 'idBahan' in update_data:
            cascade_stok = str(update_data.get('idBahan', '')).strip() != str(
                bahan.get('idBahan', '')
            ).strip()
        else:
            if 'jumlah' in update_data:
                try:
                    old_j = float(bahan.get('jumlah', 0) or 0)
                    new_j = float(update_data['jumlah'])
                    cascade_stok = abs(old_j - new_j) > 1e-4
                except (TypeError, ValueError):
                    cascade_stok = True
            elif 'detailKloter' in update_data:
                cascade_stok = True

        if cascade_stok and id_bahan_untuk_cascade:
            _cascade_remove_id_bahan_dari_produksi_setelah_master_bahan_diubah(
                id_bahan_untuk_cascade
            )

        updated = db.bahan.find_one({'_id': bahan['_id']})

        # Jika idBahan berubah, coba pindahkan referensi baris keuangan lama ke id baru
        try:
            new_id_bahan = str(updated.get('idBahan') or '').strip() if updated else ''
            if old_id_bahan and new_id_bahan and old_id_bahan != new_id_bahan:
                db.keuangan.update_many(
                    {'jenisPengeluaran': 'Pembelian Bahan Baku', 'idBahanBaku': old_id_bahan},
                    {'$set': {'idBahanBaku': new_id_bahan}},
                )
        except Exception as e:
            print(f"⚠️ [SYNC KEUANGAN ID BAHAN] ERROR: {str(e)}")

        # Otomatis update pengeluaran keuangan untuk pembelian bahan baku
        _sync_keuangan_pengeluaran_bahan_masuk(updated)

        return jsonify(json_serialize(updated)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bahan-produksi/<bahan_id>/sync-produksi-proses', methods=['POST'])
def post_sync_produksi_proses_from_bahan_master(bahan_id):
    """
    Dinonaktifkan: proses pada dokumen produksi tidak lagi diselaraskan dari master bahan.
    Renama master dilakukan lewat alur master data; alokasi bahan ke produksi diatur ulang
    lepas otomatis saat master bahan berubah (cascade) bila perlu.
    """
    try:
        try:
            bahan = db.bahan.find_one({'_id': ObjectId(bahan_id)})
        except Exception:
            bahan = db.bahan.find_one({'id': int(bahan_id)}) if str(bahan_id).isdigit() else None
        if not bahan:
            bahan = db.bahan.find_one({'idBahan': bahan_id})
        if not bahan:
            return jsonify({'error': 'Bahan not found'}), 404
        eff_id = str(bahan.get('idBahan') or '').strip()
        return jsonify({
            'ok': True,
            'skipped': True,
            'idBahan': eff_id,
            'message': (
                'Sinkron proses produksi dari master bahan tidak dilakukan. '
                'Proses pada ID produksi tetap sesuai saat dibuat; id bahan yang terdampak '
                'ubahan master dilepas otomatis bila struktur/berat proses tidak ekuivalen.'
            ),
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bahan-produksi/<bahan_id>', methods=['DELETE'])
def delete_bahan(bahan_id):
    """Delete bahan"""
    try:
        try:
            bahan = db.bahan.find_one({'_id': ObjectId(bahan_id)})
        except:
            bahan = db.bahan.find_one({'id': int(bahan_id)}) or \
                   db.bahan.find_one({'idBahan': bahan_id})
        
        if not bahan:
            return jsonify({'error': 'Bahan not found'}), 404

        id_bahan = str(bahan.get('idBahan') or '').strip()
        
        # Check if there are produksi using this bahan (tunggal atau dalam idBahanList)
        bid = bahan.get('idBahan')
        produksi_count = db.produksi.count_documents({
            '$or': [{'idBahan': bid}, {'idBahanList': bid}]
        })
        if produksi_count > 0:
            return jsonify({
                'error': f'Cannot delete bahan. There are {produksi_count} produksi using this bahan'
            }), 400
        
        db.bahan.delete_one({'_id': bahan['_id']})

        # Otomatis hapus baris keuangan terkait (pembelian bahan baku) jika ada
        try:
            if id_bahan:
                db.keuangan.delete_many({
                    'jenisPengeluaran': 'Pembelian Bahan Baku',
                    'idBahanBaku': id_bahan,
                })
        except Exception as e:
            print(f"⚠️ [DELETE KEUANGAN<-BAHAN] ERROR: {str(e)}")

        return jsonify({'message': 'Bahan deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bahan-produksi/sisa/<id_bahan>', methods=['GET'])
def get_sisa_bahan(id_bahan):
    """Sisa berat: per jalur proses (?proses=Nama) jika bahan punya prosesBahan; legacy = satu pool."""
    try:
        bahan = db.bahan.find_one({'idBahan': id_bahan})
        if not bahan:
            return jsonify({'error': 'Bahan not found'}), 404
        
        proses_q = request.args.get('proses')
        lines = bahan.get('prosesBahan') or []
        if lines:
            if not proses_q:
                return jsonify({'error': 'Parameter query proses wajib untuk bahan dengan pemisahan proses'}), 400
            _, rp_id, pname_res, err_p = _resolve_proses_query_param_proses(proses_q)
            if err_p:
                return jsonify({'error': err_p}), 400
            line = None
            if rp_id is not None:
                line = next(
                    (
                        l for l in lines
                        if isinstance(l, dict) and _int_proses_id(l.get('idProses')) == rp_id
                    ),
                    None,
                )
            if line is None:
                line = next((l for l in lines if l.get('prosesPengolahan') == proses_q), None)
                if line is None and pname_res:
                    line = next(
                        (l for l in lines if (l.get('prosesPengolahan') or '').strip() == pname_res),
                        None,
                    )
            if not line:
                return jsonify({'error': f'Proses "{proses_q}" tidak ada pada bahan ini'}), 404
            cap = float(line.get('jumlahBeratProses', 0) or 0)
            lid = _int_proses_id(line.get('idProses'))
            ln = (line.get('prosesPengolahan') or '').strip()
            td = _total_digunakan_bahan_proses(id_bahan, id_proses=lid, nama_proses=ln)
            sisa = max(0.0, cap - td)
            return jsonify({
                'idBahan': id_bahan,
                'idProses': lid if lid is not None else rp_id,
                'prosesPengolahan': pname_res or ln or proses_q,
                'totalBahan': cap,
                'totalDigunakan': td,
                'sisaTersedia': sisa
            }), 200
        
        total_digunakan = _total_digunakan_bahan_proses(id_bahan)
        cap = float(bahan.get('jumlah', 0) or 0)
        sisa = max(0.0, cap - total_digunakan)
        return jsonify({
            'idBahan': id_bahan,
            'totalBahan': cap,
            'totalDigunakan': total_digunakan,
            'sisaTersedia': sisa
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bahan-produksi/untuk-produksi', methods=['GET'])
def get_bahan_untuk_produksi():
    """
    Bahan yang boleh dipilih untuk produksi baru: punya baris proses yang diminta,
    sisa > 0 untuk jalur tersebut. Bahan legacy (tanpa prosesBahan): id belum dipakai
    produksi lain (kecuali idProduksi= mengabaikan dokumen itu). Bahan dengan prosesBahan:
    id yang sama boleh dipakai beberapa id produksi — pembatasan lewat sisa per jalur proses.
    """
    try:
        proses = request.args.get('proses', '').strip()
        exclude_id_produksi = request.args.get('idProduksi', '').strip() or None
        if not proses:
            return jsonify({'error': 'Parameter query proses wajib'}), 400
        _, rp_id, pname_res, err_r = _resolve_proses_query_param_proses(proses)
        if err_r:
            return jsonify({'error': err_r}), 400
        
        terpakai = _all_id_bahan_terpakai_produksi(exclude_id_produksi)
        out = []
        for bahan in db.bahan.find().sort('id', 1):
            bid = bahan.get('idBahan')
            if not bid:
                continue
            lines = bahan.get('prosesBahan') or []
            if not lines and bid in terpakai:
                continue
            line = None
            if lines:
                if rp_id is not None:
                    line = next(
                        (
                            l for l in lines
                            if isinstance(l, dict) and _int_proses_id(l.get('idProses')) == rp_id
                        ),
                        None,
                    )
                if line is None and pname_res:
                    line = next(
                        (l for l in lines if (l.get('prosesPengolahan') or '').strip() == pname_res),
                        None,
                    )
                if line is None:
                    line = next((l for l in lines if l.get('prosesPengolahan') == proses), None)
            if not line:
                continue
            cap = float(line.get('jumlahBeratProses', 0) or 0)
            lid = _int_proses_id(line.get('idProses'))
            ln = (line.get('prosesPengolahan') or '').strip()
            td = _total_digunakan_bahan_proses(bid, id_proses=lid or rp_id, nama_proses=ln or pname_res)
            sisa = max(0.0, cap - td)
            if sisa <= 0:
                continue
            out.append({
                'idBahan': bid,
                'idProses': lid if lid is not None else rp_id,
                'prosesPengolahan': pname_res or ln or proses,
                'sisaTersedia': sisa,
                'alokasi': cap,
                'varietas': bahan.get('varietas'),
                'tanggalMasuk': bahan.get('tanggalMasuk'),
            })
        return jsonify(json_serialize(out)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== PEMASOK ENDPOINTS ====================

@app.route('/api/pemasok', methods=['GET'])
def get_pemasok():
    """Get all pemasok data"""
    try:
        pemasok = list(db.pemasok.find().sort('id', 1))
        print(f"📊 [PEMASOK GET] Retrieved {len(pemasok)} documents from MongoDB collection 'pemasok'")
        return jsonify(json_serialize(pemasok)), 200
    except Exception as e:
        print(f"❌ [PEMASOK GET] ERROR: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pemasok/<pemasok_id>', methods=['GET'])
def get_pemasok_by_id(pemasok_id):
    """Get pemasok by ID or idPemasok"""
    try:
        try:
            pemasok = db.pemasok.find_one({'_id': ObjectId(pemasok_id)})
        except:
            pemasok = db.pemasok.find_one({'idPemasok': pemasok_id}) or \
                     db.pemasok.find_one({'id': int(pemasok_id)})
        
        if not pemasok:
            return jsonify({'error': 'Pemasok not found'}), 404
        
        return jsonify(json_serialize(pemasok)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pemasok', methods=['POST'])
def create_pemasok():
    """Create new pemasok"""
    try:
        data = request.json
        
        required_fields = ['idPemasok', 'nama', 'alamat', 'kontak', 'namaPerkebunan', 'status']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        existing = db.pemasok.find_one({'idPemasok': data['idPemasok']})
        if existing:
            return jsonify({'error': 'ID Pemasok already exists'}), 400
        
        new_id = get_next_id('pemasok')
        
        pemasok_data = {
            'id': new_id,
            'idPemasok': data['idPemasok'],
            'nama': data['nama'],
            'alamat': data['alamat'],
            'kontak': data['kontak'],
            'namaPerkebunan': data['namaPerkebunan'],
            'status': data['status']
        }
        
        print(f"🔵 [PEMASOK CREATE] Inserting to MongoDB collection 'pemasok': {pemasok_data}")
        result = db.pemasok.insert_one(pemasok_data)
        pemasok_data['_id'] = result.inserted_id
        print(f"✅ [PEMASOK CREATE] Successfully inserted! ID: {result.inserted_id}, Collection: pemasok")
        return jsonify(json_serialize(pemasok_data)), 201
    except Exception as e:
        print(f"❌ [PEMASOK CREATE] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/pemasok/<pemasok_id>', methods=['PUT'])
def update_pemasok(pemasok_id):
    """Update pemasok"""
    try:
        data = request.json
        
        try:
            pemasok = db.pemasok.find_one({'_id': ObjectId(pemasok_id)})
        except:
            pemasok = db.pemasok.find_one({'id': int(pemasok_id)}) or \
                     db.pemasok.find_one({'idPemasok': pemasok_id})
        
        if not pemasok:
            return jsonify({'error': 'Pemasok not found'}), 404
        
        if 'idPemasok' in data:
            existing = db.pemasok.find_one({
                'idPemasok': data['idPemasok'],
                '_id': {'$ne': pemasok['_id']}
            })
            if existing:
                return jsonify({'error': 'ID Pemasok already exists'}), 400
        
        update_data = {}
        for field in ['idPemasok', 'nama', 'alamat', 'kontak', 'namaPerkebunan', 'status']:
            if field in data:
                update_data[field] = data[field]
        
        db.pemasok.update_one(
            {'_id': pemasok['_id']},
            {'$set': update_data}
        )
        
        updated = db.pemasok.find_one({'_id': pemasok['_id']})
        return jsonify(json_serialize(updated)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pemasok/<pemasok_id>', methods=['DELETE'])
def delete_pemasok(pemasok_id):
    """Delete pemasok"""
    try:
        try:
            pemasok = db.pemasok.find_one({'_id': ObjectId(pemasok_id)})
        except:
            pemasok = db.pemasok.find_one({'id': int(pemasok_id)}) or \
                     db.pemasok.find_one({'idPemasok': pemasok_id})
        
        if not pemasok:
            return jsonify({'error': 'Pemasok not found'}), 404
        
        # Check if there are bahan using this pemasok
        bahan_count = db.bahan.count_documents({'pemasok': pemasok.get('nama')})
        if bahan_count > 0:
            return jsonify({
                'error': f'Cannot delete pemasok. There are {bahan_count} bahan using this pemasok'
            }), 400
        
        db.pemasok.delete_one({'_id': pemasok['_id']})
        return jsonify({'message': 'Pemasok deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== PEMBELI (MASTER DATA PEMBELI) ====================

@app.route('/api/pembeli', methods=['GET'])
def get_pembeli():
    """Daftar master pembeli."""
    try:
        rows = list(db.pembeli.find().sort('id', 1))
        print(f"📊 [PEMBELI GET] {len(rows)} dokumen")
        return jsonify(json_serialize(rows)), 200
    except Exception as e:
        print(f"❌ [PEMBELI GET] {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/pembeli/<pembeli_id>', methods=['GET'])
def get_pembeli_by_id(pembeli_id):
    try:
        try:
            doc = db.pembeli.find_one({'_id': ObjectId(pembeli_id)})
        except Exception:
            doc = None
        if not doc:
            doc = db.pembeli.find_one({'idPembeli': pembeli_id}) or \
                  db.pembeli.find_one({'id': int(pembeli_id)})
        if not doc:
            return jsonify({'error': 'Pembeli not found'}), 404
        return jsonify(json_serialize(doc)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pembeli', methods=['POST'])
def create_pembeli():
    try:
        data = request.json or {}
        required = ['nama', 'kontak', 'alamat', 'tipePembeli', 'region']
        for f in required:
            if not str(data.get(f, '')).strip():
                return jsonify({'error': f'Missing or empty field: {f}'}), 400
        tipe = (data.get('tipePembeli') or '').strip()
        if tipe not in ('Lokal', 'International', 'ecommerce'):
            return jsonify({'error': 'tipePembeli harus Lokal, International, atau ecommerce'}), 400

        numeric_id = get_next_id('pembeli')
        id_pembeli = (data.get('idPembeli') or '').strip()
        if id_pembeli:
            if db.pembeli.find_one({'idPembeli': id_pembeli}):
                return jsonify({'error': 'ID Pembeli sudah dipakai'}), 400
        else:
            id_pembeli = f"PBL{str(numeric_id).zfill(3)}"

        row = {
            'id': numeric_id,
            'idPembeli': id_pembeli,
            'nama': str(data['nama']).strip(),
            'kontak': str(data['kontak']).strip(),
            'alamat': str(data['alamat']).strip(),
            'tipePembeli': tipe,
            'region': str(data['region']).strip(),
            'createdAt': datetime.now(),
            'updatedAt': datetime.now(),
        }
        ins = db.pembeli.insert_one(row)
        row['_id'] = ins.inserted_id
        print(f"✅ [PEMBELI CREATE] {row['idPembeli']}")
        return jsonify(json_serialize(row)), 201
    except Exception as e:
        print(f"❌ [PEMBELI CREATE] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/pembeli/<pembeli_id>', methods=['PUT'])
def update_pembeli(pembeli_id):
    try:
        data = request.json or {}
        try:
            doc = db.pembeli.find_one({'_id': ObjectId(pembeli_id)})
        except Exception:
            doc = None
        if not doc:
            doc = db.pembeli.find_one({'idPembeli': pembeli_id}) or \
                  db.pembeli.find_one({'id': int(pembeli_id)})
        if not doc:
            return jsonify({'error': 'Pembeli not found'}), 404

        if 'idPembeli' in data and data['idPembeli']:
            other = db.pembeli.find_one({
                'idPembeli': data['idPembeli'],
                '_id': {'$ne': doc['_id']},
            })
            if other:
                return jsonify({'error': 'ID Pembeli sudah dipakai'}), 400

        update_data = {}
        for field in ['idPembeli', 'nama', 'kontak', 'alamat', 'tipePembeli', 'region']:
            if field in data:
                update_data[field] = data[field]
        if 'tipePembeli' in update_data:
            if update_data['tipePembeli'] not in ('Lokal', 'International', 'ecommerce'):
                return jsonify({'error': 'tipePembeli tidak valid'}), 400
        if 'region' in update_data:
            if not str(update_data['region'] or '').strip():
                return jsonify({'error': 'region tidak boleh kosong'}), 400
            update_data['region'] = str(update_data['region']).strip()
        update_data['updatedAt'] = datetime.now()
        db.pembeli.update_one({'_id': doc['_id']}, {'$set': update_data})
        updated = db.pembeli.find_one({'_id': doc['_id']})
        return jsonify(json_serialize(updated)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pembeli/<pembeli_id>', methods=['DELETE'])
def delete_pembeli(pembeli_id):
    try:
        try:
            doc = db.pembeli.find_one({'_id': ObjectId(pembeli_id)})
        except Exception:
            doc = None
        if not doc:
            doc = db.pembeli.find_one({'idPembeli': pembeli_id}) or \
                  db.pembeli.find_one({'id': int(pembeli_id)})
        if not doc:
            return jsonify({'error': 'Pembeli not found'}), 404
        id_master = doc.get('idPembeli')
        n = db.pemesanan.count_documents({'idMasterPembeli': id_master})
        if n > 0:
            return jsonify({
                'error': f'Tidak dapat menghapus: ada {n} pemesanan terkait pembeli ini',
            }), 400
        db.pembeli.delete_one({'_id': doc['_id']})
        return jsonify({'success': True, 'message': 'Pembeli dihapus'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== STOK ENDPOINTS ====================

def _stok_key(tipe, jenis_kopi, proses):
    """Key agregasi stok: hanya tipe produk, jenis kopi, proses (tanpa kemasan)."""
    def s(v):
        if v is None:
            return ''
        return str(v).strip()
    return f"{s(tipe)}|{s(jenis_kopi)}|{s(proses)}"


def _produksi_masuk_stok_hasil_pengemasan(p):
    """
    Stok hasil hanya dari batch yang menyelesaikan alur pengemasan dengan benar:
    status memuat Pengemasan, berat akhir > 0, dan tanggal pengemasan tercatat
    (field di-set saat create/update saat status pengemasan).
    """
    st = (p.get('statusTahapan') or '')
    if not st or 'pengemasan' not in st.lower():
        return False
    if float(p.get('beratAkhir', 0) or 0) <= 0:
        return False
    if not str(p.get('tanggalPengemasan') or '').strip():
        return False
    return True


def _stok_gb_pixel_tidak_lebih_dari_berat_akhir(p, tol=0.02):
    """GB + Pixel tidak boleh melebihi berat akhir (data tidak konsisten → tidak dihitung stok)."""
    ba = float(p.get('beratAkhir', 0) or 0)
    if ba <= 0:
        return False
    gb = float(p.get('beratGreenBeans', 0) or 0)
    px = float(p.get('beratPixel', 0) or 0)
    return gb + px <= ba + tol


def _proses_pengolahan_tampilan_untuk_agregasi(produksi_doc, bahan_doc):
    """
    Selaras dengan getProsesPengolahanTampilan di kelola_produksi.js / laporan:
    jika master bahan hanya punya satu baris prosesBahan, pakai nama itu untuk agregasi.
    Sehingga stok mengikuti yang tampil di UI meskipun field produksi.prosesPengolahan belum diperbarui.
    """
    if not produksi_doc:
        return ''
    lines = (bahan_doc or {}).get('prosesBahan')
    if isinstance(lines, list) and len(lines) == 1:
        only = (lines[0].get('prosesPengolahan') or '').strip()
        if only:
            return only
    return (produksi_doc.get('prosesPengolahan') or '').strip()


def _bahan_cache_get_for_produksi(produksi_doc, bahan_cache):
    """Ambil dokumen bahan (pertama) untuk produksi; isi bahan_cache."""
    ids_p = _id_bahan_list_from_produksi(produksi_doc)
    id_bahan = ids_p[0] if ids_p else produksi_doc.get('idBahan')
    if not id_bahan:
        return {}
    if id_bahan not in bahan_cache:
        bahan_cache[id_bahan] = db.bahan.find_one({'idBahan': id_bahan}) or {}
    return bahan_cache[id_bahan]


def _stok_berat_green_effective_dari_produksi(p):
    """
    Stok green beans = berat akhir − berat pixel (sisanya setelah bagian pixel).
    Selaras Σ berat akhir saat pixel=0; field beratGreenBeans di form hanya referensi/validasi.
    """
    ba = float(p.get('beratAkhir', 0) or 0)
    px = float(p.get('beratPixel', 0) or 0)
    return max(0.0, ba - px)


def _is_hasil_from_ordering_flag(h):
    v = h.get('isFromOrdering')
    return v in (True, 'true', 1, 'True')


def _compute_stok_hasil_aggregate(tipe_filter='', tanggal_filter=''):
    """
    Logika sama dengan GET /api/stok: agregasi per tipeProduk + jenisKopi + prosesPengolahan,
    setelah dikurangi hasil ordering. Mengembalikan (stok_array, ringkasan).
    """
    produksi_list = list(db.produksi.find({
        'statusTahapan': {'$regex': 'Pengemasan', '$options': 'i'},
    }))
    produksi_list = [
        p for p in produksi_list
        if _produksi_masuk_stok_hasil_pengemasan(p)
        and _stok_gb_pixel_tidak_lebih_dari_berat_akhir(p)
    ]

    if tanggal_filter:
        produksi_list = [p for p in produksi_list if (p.get('tanggalPengemasan') or '')[:10] == tanggal_filter[:10]]

    stok_map = {}
    bahan_cache = {}

    for p in produksi_list:
        bahan = _bahan_cache_get_for_produksi(p, bahan_cache)
        jenis_kopi = (bahan.get('jenisKopi') or '').strip()
        proses_pengolahan = _proses_pengolahan_tampilan_untuk_agregasi(p, bahan)

        stok_gb_batch = _stok_berat_green_effective_dari_produksi(p)
        if stok_gb_batch > 0:
            if not tipe_filter or tipe_filter == 'Green Beans':
                key_gb = _stok_key('Green Beans', jenis_kopi, proses_pengolahan)
                if key_gb not in stok_map:
                    stok_map[key_gb] = {
                        'tipeProduk': 'Green Beans',
                        'jenisKopi': jenis_kopi,
                        'prosesPengolahan': proses_pengolahan,
                        'totalBerat': 0,
                    }
                stok_map[key_gb]['totalBerat'] += stok_gb_batch

        berat_pixel = float(p.get('beratPixel', 0) or 0)
        if berat_pixel > 0:
            if not tipe_filter or tipe_filter == 'Pixel':
                key_px = _stok_key('Pixel', jenis_kopi, proses_pengolahan)
                if key_px not in stok_map:
                    stok_map[key_px] = {
                        'tipeProduk': 'Pixel',
                        'jenisKopi': jenis_kopi,
                        'prosesPengolahan': proses_pengolahan,
                        'totalBerat': 0,
                    }
                stok_map[key_px]['totalBerat'] += berat_pixel

    hasil_ordering = list(db.hasilProduksi.find({'isFromOrdering': True}))
    id_untuk_resolve = set()
    for p in produksi_list:
        ip = str(p.get('idProduksi') or '').strip()
        if ip:
            id_untuk_resolve.add(ip)
    for h in hasil_ordering:
        ip = str(h.get('idProduksi') or '').strip()
        if ip:
            id_untuk_resolve.add(ip)
    produksi_by_id = {}
    if id_untuk_resolve:
        for doc in db.produksi.find({'idProduksi': {'$in': list(id_untuk_resolve)}}):
            produksi_by_id[str(doc.get('idProduksi') or '').strip()] = doc

    for h in hasil_ordering:
        idp = str(h.get('idProduksi') or '').strip()
        pdoc = produksi_by_id.get(idp)
        tipe_p = (h.get('tipeProduk') or '').strip()
        berat_kurangi = float(h.get('beratSaatIni', 0) or 0)
        if pdoc:
            bh = _bahan_cache_get_for_produksi(pdoc, bahan_cache)
            jk = (bh.get('jenisKopi') or '').strip() or (h.get('jenisKopi') or '').strip()
            proses_eff = _proses_pengolahan_tampilan_untuk_agregasi(pdoc, bh)
        else:
            jk = (h.get('jenisKopi') or '').strip()
            proses_eff = (h.get('prosesPengolahan') or '').strip()
        key = _stok_key(tipe_p, jk, proses_eff)
        if key in stok_map:
            stok_map[key]['totalBerat'] = max(0, stok_map[key]['totalBerat'] - berat_kurangi)
        else:
            print(f"⚠️ [STOK AGREGAT] Key ordering tidak ada di stok_map (pengurangan {berat_kurangi} kg dilewati): {key}")

    stok_array = [v for v in stok_map.values() if v['totalBerat'] > 0]
    stok_array.sort(key=lambda x: (x['tipeProduk'], x['jenisKopi']))

    s_ba = sum(float(p.get('beratAkhir') or 0) for p in produksi_list)
    s_px = sum(float(p.get('beratPixel') or 0) for p in produksi_list)
    s_stok_gb_bruto = sum(_stok_berat_green_effective_dari_produksi(p) for p in produksi_list)
    s_gb_form = sum(float(p.get('beratGreenBeans') or 0) for p in produksi_list)
    tot_gb_stok = sum(
        float(v.get('totalBerat') or 0)
        for v in stok_array
        if (v.get('tipeProduk') or '').strip() == 'Green Beans'
    )
    tot_px_stok = sum(
        float(v.get('totalBerat') or 0)
        for v in stok_array
        if (v.get('tipeProduk') or '').strip() == 'Pixel'
    )
    ringkasan = {
        'jumlahBatchPengemasan': len(produksi_list),
        'sumBeratAkhir': round(s_ba, 4),
        'sumBeratPixelBruto': round(s_px, 4),
        'sumStokGreenBeansBruto': round(s_stok_gb_bruto, 4),
        'sumBeratGreenBeansDiForm': round(s_gb_form, 4),
        'totalStokGreenBeansSetelahOrdering': round(tot_gb_stok, 4),
        'totalStokPixelSetelahOrdering': round(tot_px_stok, 4),
    }
    return stok_array, ringkasan


def _batch_stok_pool_tipe(produksi_doc, tipe_produk_selected):
    if tipe_produk_selected == 'Green Beans':
        return _stok_berat_green_effective_dari_produksi(produksi_doc)
    return float(produksi_doc.get('beratPixel', 0) or 0)


def _batch_stok_tersedia_setelah_ordering(produksi_doc, tipe_produk_selected):
    """Sisa stok per batch untuk tipe produk (GB pool atau Pixel), setelah hasil ordering."""
    idp = produksi_doc.get('idProduksi')
    pool = _batch_stok_pool_tipe(produksi_doc, tipe_produk_selected)
    if pool <= 0:
        return 0.0
    hasil_list = list(db.hasilProduksi.find({'idProduksi': idp, 'tipeProduk': tipe_produk_selected}))
    total_ord = sum(
        float(h.get('beratSaatIni', 0) or 0)
        for h in hasil_list
        if _is_hasil_from_ordering_flag(h)
    )
    return max(0.0, pool - total_ord)


def _fifo_allocate_ordering_batches(pemesanan, tipe_produk_selected, jumlah_pesanan,
                                    jenis_kopi_override=None, proses_pengolahan_override=None):
    """
    Memenuhi jumlah pesanan dari batch pengemasan yang cocok (jenis kopi + proses),
    prioritas tanggal pengemasan lebih awal (FIFO).
    Mengembalikan daftar (produksi_doc, kg_diambil).
    Override jenis_kopi / proses untuk satu baris pemesanan multi-item.
    """
    ps_pem = (proses_pengolahan_override if proses_pengolahan_override is not None
              else (pemesanan.get('prosesPengolahan') or '')).strip()
    jk_pem = (jenis_kopi_override if jenis_kopi_override is not None
              else (pemesanan.get('jenisKopi') or '')).strip()
    need = float(jumlah_pesanan)
    if need <= 0:
        return []

    produksi_list = list(db.produksi.find({
        'statusTahapan': {'$regex': 'Pengemasan', '$options': 'i'},
    }))
    produksi_list = [
        p for p in produksi_list
        if _produksi_masuk_stok_hasil_pengemasan(p)
        and _stok_gb_pixel_tidak_lebih_dari_berat_akhir(p)
    ]
    bahan_cache = {}
    candidates = []
    for p in produksi_list:
        bahan = _bahan_cache_get_for_produksi(p, bahan_cache)
        jk = (bahan.get('jenisKopi') or '').strip()
        if jk != jk_pem:
            continue
        ps_disp = _proses_pengolahan_tampilan_untuk_agregasi(p, bahan)
        ps_raw = (p.get('prosesPengolahan') or '').strip()
        if ps_pem not in (ps_raw, ps_disp):
            continue
        avail = _batch_stok_tersedia_setelah_ordering(p, tipe_produk_selected)
        if avail <= 0:
            continue
        candidates.append((p, avail))

    candidates.sort(key=lambda x: (
        (x[0].get('tanggalPengemasan') or '')[:10],
        str(x[0].get('idProduksi') or ''),
    ))

    out = []
    for p, avail in candidates:
        if need <= 1e-9:
            break
        take = min(need, avail)
        if take <= 0:
            continue
        out.append((p, take))
        need -= take
    if need > 1e-6:
        raise RuntimeError('Alokasi FIFO gagal; stok agregat berubah atau data tidak konsisten')
    return out


@app.route('/api/stok', methods=['GET'])
def get_stok():
    """
    Stok Pengemasan: Green Beans = (berat akhir − pixel) per batch; Pixel = beratPixel.
    Hanya batch dengan tanggal pengemasan tercatat; GB+pixel di form tidak melebihi berat akhir.
    Kurangi pemesanan per tipe. Query: tipeProduk, tanggalPengemasan.
    """
    try:
        tipe_filter = request.args.get('tipeProduk', '').strip()
        tanggal_filter = request.args.get('tanggalPengemasan', '').strip()
        stok_array, ringkasan = _compute_stok_hasil_aggregate(tipe_filter, tanggal_filter)
        print(f"📊 [STOK GET] Aggregated {len(stok_array)} stok (filter tipe={tipe_filter or 'semua'}, tanggal={tanggal_filter or 'semua'})")
        return jsonify(json_serialize({'rows': stok_array, 'ringkasan': ringkasan})), 200
    except Exception as e:
        print(f"❌ [STOK GET] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/stok/filter-options', methods=['GET'])
def get_stok_filter_options():
    """Opsi filter stok: tipe produk (Green Beans/Pixel), tanggal pengemasan dari produksi."""
    try:
        tipe_produk_list = sorted(_get_tipe_produk_master_set())
        # Tanggal pengemasan dari produksi yang memenuhi syarat stok hasil
        produksi_list = list(db.produksi.find({
            'statusTahapan': {'$regex': 'Pengemasan', '$options': 'i'},
        }))
        tanggal_set = set()
        for p in produksi_list:
            if not _produksi_masuk_stok_hasil_pengemasan(p):
                continue
            if not _stok_gb_pixel_tidak_lebih_dari_berat_akhir(p):
                continue
            d = (p.get('tanggalPengemasan') or '')[:10]
            if d:
                tanggal_set.add(d)
        return jsonify({
            'tipeProduk': tipe_produk_list,
            'tanggalPengemasan': sorted(tanggal_set)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stok/bahan', methods=['GET'])
def get_stok_bahan():
    """Get stok bahan baku dengan perhitungan otomatis dari produksi"""
    try:
        bahan_list = list(db.bahan.find().sort('id', 1))
        produksi_list = list(db.produksi.find())
        
        # Hitung total yang digunakan per idBahan (dukung alokasi multi-bahan)
        total_digunakan_map = {}
        for p in produksi_list:
            m = _alokasi_map_from_produksi(p)
            for bid, w in m.items():
                total_digunakan_map[bid] = total_digunakan_map.get(bid, 0) + float(w or 0)
        
        # Buat array stok bahan dengan sisa tersedia
        stok_bahan_array = []
        for bahan in bahan_list:
            id_bahan = bahan.get('idBahan')
            total_bahan = float(bahan.get('jumlah', 0))
            total_digunakan = total_digunakan_map.get(id_bahan, 0)
            sisa_tersedia = max(0, total_bahan - total_digunakan)
            
            proses_lines = bahan.get('prosesBahan') or []
            ringkasan_proses = ', '.join(
                f"{x.get('prosesPengolahan', '')} ({float(x.get('jumlahBeratProses', 0) or 0):g} kg)"
                for x in proses_lines
            ) if proses_lines else ''
            stok_bahan_array.append({
                'id': bahan.get('id'),
                'idBahan': id_bahan,
                'pemasok': bahan.get('pemasok', ''),
                'varietas': bahan.get('varietas', ''),
                'jenisKopi': bahan.get('jenisKopi', ''),
                'ringkasanProses': ringkasan_proses,
                'tanggalMasuk': bahan.get('tanggalMasuk', ''),
                'totalBahan': total_bahan,
                'totalDigunakan': total_digunakan,
                'sisaTersedia': sisa_tersedia,
                'persentaseTersedia': (sisa_tersedia / total_bahan * 100) if total_bahan > 0 else 0
            })
        
        # Sort by idBahan
        stok_bahan_array.sort(key=lambda x: x.get('idBahan', ''))
        
        return jsonify(json_serialize(stok_bahan_array)), 200
    except Exception as e:
        print(f"❌ [STOK BAHAN GET] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ==================== MASTER DATA ENDPOINTS ====================

def get_master_data_endpoints(collection_name, fields):
    """Helper to create CRUD endpoints for master data"""
    
    @app.route(f'/api/{collection_name}', methods=['GET'], endpoint=f'get_all_{collection_name}')
    def get_all():
        try:
            data = list(db[collection_name].find().sort('id', 1))
            return jsonify(json_serialize(data)), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route(f'/api/{collection_name}/<item_id>', methods=['GET'], endpoint=f'get_one_{collection_name}')
    def get_one(item_id):
        try:
            try:
                item = db[collection_name].find_one({'_id': ObjectId(item_id)})
            except:
                item = db[collection_name].find_one({'id': int(item_id)}) or \
                      db[collection_name].find_one({'nama': item_id})
            
            if not item:
                return jsonify({'error': f'{collection_name} not found'}), 404
            
            return jsonify(json_serialize(item)), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route(f'/api/{collection_name}', methods=['POST'], endpoint=f'create_{collection_name}')
    def create():
        try:
            data = request.json
            
            for field in fields:
                if field not in data:
                    return jsonify({'error': f'Missing required field: {field}'}), 400
            
            # Check if nama already exists (if 'nama' is a field)
            if 'nama' in fields:
                existing = db[collection_name].find_one({'nama': data['nama']})
                if existing:
                    return jsonify({'error': 'Nama already exists'}), 400
            
            new_id = get_next_id(collection_name)
            
            item_data = {'id': new_id}
            for field in fields:
                item_data[field] = data[field]
            
            # Handle special fields like 'ukuran' for kemasan
            if 'ukuran' in fields and 'ukuran' in data:
                item_data['ukuran'] = data['ukuran']
            
            result = db[collection_name].insert_one(item_data)
            item_data['_id'] = result.inserted_id
            
            return jsonify(json_serialize(item_data)), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route(f'/api/{collection_name}/<item_id>', methods=['PUT'], endpoint=f'update_{collection_name}')
    def update(item_id):
        try:
            data = request.json
            
            try:
                item = db[collection_name].find_one({'_id': ObjectId(item_id)})
            except:
                item = db[collection_name].find_one({'id': int(item_id)}) or \
                      db[collection_name].find_one({'nama': item_id})
            
            if not item:
                return jsonify({'error': f'{collection_name} not found'}), 404
            
            if 'nama' in data and 'nama' in fields:
                existing = db[collection_name].find_one({
                    'nama': data['nama'],
                    '_id': {'$ne': item['_id']}
                })
                if existing:
                    return jsonify({'error': 'Nama already exists'}), 400
            
            update_data = {}
            for field in fields:
                if field in data:
                    update_data[field] = data[field]
            
            if 'ukuran' in data:
                update_data['ukuran'] = data['ukuran']
            
            db[collection_name].update_one(
                {'_id': item['_id']},
                {'$set': update_data}
            )
            
            updated = db[collection_name].find_one({'_id': item['_id']})
            return jsonify(json_serialize(updated)), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route(f'/api/{collection_name}/<item_id>', methods=['DELETE'], endpoint=f'delete_{collection_name}')
    def delete(item_id):
        try:
            try:
                item = db[collection_name].find_one({'_id': ObjectId(item_id)})
            except:
                item = db[collection_name].find_one({'id': int(item_id)}) or \
                      db[collection_name].find_one({'nama': item_id})
            
            if not item:
                return jsonify({'error': f'{collection_name} not found'}), 404
            
            db[collection_name].delete_one({'_id': item['_id']})
            return jsonify({'message': f'{collection_name} deleted successfully'}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

# Create master data endpoints
get_master_data_endpoints('dataJenisKopi', ['nama'])
get_master_data_endpoints('dataVarietas', ['nama'])
# dataProses menggunakan endpoint khusus karena memiliki tahapanStatus
get_master_data_endpoints('dataRoasting', ['nama'])
# dataKemasan menggunakan endpoint khusus karena memiliki stok
get_master_data_endpoints('dataProduk', ['nama'])

# ==================== DATA PROSES ENDPOINTS (Khusus dengan tahapanStatus) ====================
@app.route('/api/dataProses', methods=['GET'])
def get_all_dataProses():
    try:
        data = list(db.dataProses.find().sort('id', 1))
        return jsonify(json_serialize(data)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dataProses/<item_id>', methods=['GET'])
def get_one_dataProses(item_id):
    try:
        try:
            item = db.dataProses.find_one({'_id': ObjectId(item_id)})
        except:
            item = db.dataProses.find_one({'id': int(item_id)}) or \
                  db.dataProses.find_one({'nama': item_id})
        
        if not item:
            return jsonify({'error': 'dataProses not found'}), 404
        
        return jsonify(json_serialize(item)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dataProses', methods=['POST'])
def create_dataProses():
    try:
        data = request.json
        
        if 'nama' not in data:
            return jsonify({'error': 'Missing required field: nama'}), 400
        
        nama_clean = str(data['nama']).strip()
        if not nama_clean:
            return jsonify({'error': 'Nama tidak boleh kosong'}), 400

        # Check if nama already exists
        existing = db.dataProses.find_one({'nama': nama_clean})
        if existing:
            return jsonify({'error': 'Nama already exists'}), 400
        
        new_id = get_next_id('dataProses')
        
        item_data = {
            'id': new_id,
            'nama': nama_clean,
            'tahapanStatus': data.get('tahapanStatus', {})
        }
        
        result = db.dataProses.insert_one(item_data)
        item_data['_id'] = result.inserted_id
        
        return jsonify(json_serialize(item_data)), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dataProses/<item_id>', methods=['PUT'])
def update_dataProses(item_id):
    try:
        data = request.json
        
        try:
            item = db.dataProses.find_one({'_id': ObjectId(item_id)})
        except:
            item = db.dataProses.find_one({'id': int(item_id)}) or \
                  db.dataProses.find_one({'nama': item_id})
        
        if not item:
            return jsonify({'error': 'dataProses not found'}), 404
        
        # Check duplicate nama
        if 'nama' in data:
            nama_candidate = str(data['nama']).strip()
            if not nama_candidate:
                return jsonify({'error': 'Nama tidak boleh kosong'}), 400
            existing = db.dataProses.find_one({
                'nama': nama_candidate,
                '_id': {'$ne': item['_id']}
            })
            if existing:
                return jsonify({'error': 'Nama already exists'}), 400
        
        update_data = {}
        old_nama = (item.get('nama') or '').strip()
        if 'nama' in data:
            update_data['nama'] = nama_candidate
        if 'tahapanStatus' in data:
            update_data['tahapanStatus'] = data['tahapanStatus']

        new_nama = (update_data.get('nama') or item.get('nama') or '').strip()
        cascade_stats = None
        if 'nama' in update_data and old_nama and new_nama and new_nama != old_nama:
            cascade_stats = _cascade_rename_master_proses_pengolahan(
                old_nama, new_nama, master_id_proses=item.get('id')
            )

        db.dataProses.update_one(
            {'_id': item['_id']},
            {'$set': update_data}
        )

        updated = db.dataProses.find_one({'_id': item['_id']})
        payload = json_serialize(updated)
        if cascade_stats and isinstance(payload, dict):
            payload['referensiDiperbarui'] = cascade_stats
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dataProses/<item_id>', methods=['DELETE'])
def delete_dataProses(item_id):
    try:
        try:
            item = db.dataProses.find_one({'_id': ObjectId(item_id)})
        except:
            item = db.dataProses.find_one({'id': int(item_id)}) or \
                  db.dataProses.find_one({'nama': item_id})
        
        if not item:
            return jsonify({'error': 'dataProses not found'}), 404
        
        db.dataProses.delete_one({'_id': item['_id']})
        return jsonify({'message': 'dataProses deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== MIGRATION ENDPOINT: Update Tahapan Pengeringan ====================
@app.route('/api/migrate/tahapan-pengeringan', methods=['POST'])
def migrate_tahapan_pengeringan():
    """
    Endpoint untuk migrasi tahapan Pengeringan menjadi Pengeringan Awal dan Pengeringan Akhir.
    Hanya bisa diakses oleh admin atau melalui script khusus.
    """
    try:
        # Ambil semua dataProses
        data_proses_list = list(db.dataProses.find())
        
        updated_count = 0
        skipped_count = 0
        results = []
        
        for proses in data_proses_list:
            tahapan_status = proses.get('tahapanStatus', {})
            
            # Cek apakah ada tahapan "Pengeringan"
            has_pengeringan = tahapan_status.get('Pengeringan', False)
            
            if not has_pengeringan:
                skipped_count += 1
                continue
            
            # Hapus "Pengeringan"
            new_tahapan_status = tahapan_status.copy()
            if 'Pengeringan' in new_tahapan_status:
                del new_tahapan_status['Pengeringan']
            
            # Tambahkan "Pengeringan Awal" dan "Pengeringan Akhir"
            if has_pengeringan:
                new_tahapan_status['Pengeringan Awal'] = True
                new_tahapan_status['Pengeringan Akhir'] = True
            
            # Pastikan Natural Process tidak memiliki Fermentasi
            if proses.get('nama') == 'Natural Process':
                if 'Fermentasi' in new_tahapan_status:
                    new_tahapan_status['Fermentasi'] = False
            
            # Update di database
            db.dataProses.update_one(
                {'_id': proses['_id']},
                {'$set': {'tahapanStatus': new_tahapan_status}}
            )
            
            results.append({
                'id': proses.get('id'),
                'nama': proses.get('nama'),
                'tahapanStatus_lama': tahapan_status,
                'tahapanStatus_baru': new_tahapan_status
            })
            updated_count += 1
        
        # Verifikasi: Pastikan tidak ada lagi referensi "Pengeringan"
        remaining_pengeringan = list(db.dataProses.find({'tahapanStatus.Pengeringan': {'$exists': True}}))
        
        return jsonify({
            'success': True,
            'message': 'Migrasi tahapan Pengeringan berhasil',
            'updated_count': updated_count,
            'skipped_count': skipped_count,
            'total_proses': len(data_proses_list),
            'remaining_pengeringan': len(remaining_pengeringan),
            'results': json_serialize(results)
        }), 200
        
    except Exception as e:
        print(f"❌ [MIGRATE] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ==================== DATA KEMASAN ENDPOINTS (Khusus dengan stok) ====================
@app.route('/api/dataKemasan', methods=['GET'])
def get_all_dataKemasan():
    try:
        data = list(db.dataKemasan.find().sort('id', 1))
        return jsonify(json_serialize(data)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dataKemasan/<item_id>', methods=['GET'])
def get_one_dataKemasan(item_id):
    try:
        try:
            item = db.dataKemasan.find_one({'_id': ObjectId(item_id)})
        except:
            item = db.dataKemasan.find_one({'id': int(item_id)}) or \
                  db.dataKemasan.find_one({'nama': item_id})
        
        if not item:
            return jsonify({'error': 'dataKemasan not found'}), 404
        
        return jsonify(json_serialize(item)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dataKemasan', methods=['POST'])
def create_dataKemasan():
    try:
        data = request.json
        
        if 'nama' not in data:
            return jsonify({'error': 'Missing required field: nama'}), 400
        
        # Check if nama already exists
        existing = db.dataKemasan.find_one({'nama': data['nama']})
        if existing:
            return jsonify({'error': 'Nama already exists'}), 400
        
        new_id = get_next_id('dataKemasan')
        
        item_data = {
            'id': new_id,
            'nama': data['nama'],
            'ukuran': data.get('ukuran', ''),
            'stok': int(data.get('stok', 0))  # Default stok = 0
        }
        
        result = db.dataKemasan.insert_one(item_data)
        item_data['_id'] = result.inserted_id
        
        return jsonify(json_serialize(item_data)), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dataKemasan/<item_id>', methods=['PUT'])
def update_dataKemasan(item_id):
    try:
        data = request.json
        
        try:
            item = db.dataKemasan.find_one({'_id': ObjectId(item_id)})
        except:
            item = db.dataKemasan.find_one({'id': int(item_id)}) or \
                  db.dataKemasan.find_one({'nama': item_id})
        
        if not item:
            return jsonify({'error': 'dataKemasan not found'}), 404
        
        # Check duplicate nama
        if 'nama' in data:
            existing = db.dataKemasan.find_one({
                'nama': data['nama'],
                '_id': {'$ne': item['_id']}
            })
            if existing:
                return jsonify({'error': 'Nama already exists'}), 400
        
        update_data = {}
        if 'nama' in data:
            update_data['nama'] = data['nama']
        if 'ukuran' in data:
            update_data['ukuran'] = data['ukuran']
        if 'stok' in data:
            update_data['stok'] = int(data['stok'])
        
        db.dataKemasan.update_one(
            {'_id': item['_id']},
            {'$set': update_data}
        )
        
        updated = db.dataKemasan.find_one({'_id': item['_id']})
        return jsonify(json_serialize(updated)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dataKemasan/<item_id>', methods=['DELETE'])
def delete_dataKemasan(item_id):
    try:
        try:
            item = db.dataKemasan.find_one({'_id': ObjectId(item_id)})
        except:
            item = db.dataKemasan.find_one({'id': int(item_id)}) or \
                  db.dataKemasan.find_one({'nama': item_id})
        
        if not item:
            return jsonify({'error': 'dataKemasan not found'}), 404
        
        db.dataKemasan.delete_one({'_id': item['_id']})
        return jsonify({'message': 'dataKemasan deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== SANITASI ENDPOINTS ====================

@app.route('/api/sanitasi', methods=['GET'])
def get_sanitasi():
    """Get all sanitasi data - Optimized for performance"""
    import time
    start_time = time.time()
    
    try:
        # Optional: exclude fotos for list view (fotos can be large base64 strings)
        exclude_fotos = request.args.get('exclude_fotos', 'false').lower() == 'true'
        
        # Ensure index exists for faster sorting (only create if not exists)
        try:
            db.sanitasi.create_index('id', background=True)
        except:
            pass  # Index might already exist
        
        query_start = time.time()
        
        if exclude_fotos:
            # Exclude fotos field to reduce payload size for list view
            # Use projection to exclude fotos and _id for smaller payload
            sanitasi = list(db.sanitasi.find({}, {'fotos': 0, '_id': 0}).sort('id', 1))
            query_time = time.time() - query_start
            print(f"📊 [SANITASI GET] Retrieved {len(sanitasi)} documents (fotos excluded) in {query_time:.3f}s")
        else:
            # Exclude _id to reduce payload size
            sanitasi = list(db.sanitasi.find({}, {'_id': 0}).sort('id', 1))
            query_time = time.time() - query_start
            print(f"📊 [SANITASI GET] Retrieved {len(sanitasi)} documents in {query_time:.3f}s")
        
        # Serialize data
        serialize_start = time.time()
        serialized_data = json_serialize(sanitasi)
        serialize_time = time.time() - serialize_start
        
        total_time = time.time() - start_time
        print(f"⏱️ [SANITASI GET] Total time: {total_time:.3f}s (Query: {query_time:.3f}s, Serialize: {serialize_time:.3f}s)")
        
        return jsonify(serialized_data), 200
    except Exception as e:
        total_time = time.time() - start_time
        print(f"❌ [SANITASI GET] ERROR after {total_time:.3f}s: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/sanitasi/<sanitasi_id>', methods=['GET'])
def get_sanitasi_by_id(sanitasi_id):
    """Get sanitasi by ID"""
    try:
        try:
            sanitasi = db.sanitasi.find_one({'_id': ObjectId(sanitasi_id)})
        except:
            sanitasi = db.sanitasi.find_one({'id': int(sanitasi_id)})
        if not sanitasi:
            return jsonify({'error': 'Sanitasi not found'}), 404
        return jsonify(json_serialize(sanitasi)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sanitasi', methods=['POST'])
def create_sanitasi():
    """Create new sanitasi"""
    try:
        data = request.json
        print(f"🔵 [SANITASI CREATE] Received request: {data}")
        
        new_id = get_next_id('sanitasi')
        print(f"🔵 [SANITASI CREATE] Generated ID: {new_id}")
        
        sanitasi_data = {
            'id': new_id,
            'tanggal': data.get('tanggal'),
            'waktu': data.get('waktu'),
            'tipe': data.get('tipe'),
            'namaPetugas': data.get('namaPetugas'),
            'fotos': data.get('fotos', {}),
            'checklist': data.get('checklist', {}),
            'status': data.get('status', 'Uncomplete')
        }
        
        print(f"🔵 [SANITASI CREATE] Inserting to MongoDB collection 'sanitasi': {sanitasi_data}")
        result = db.sanitasi.insert_one(sanitasi_data)
        sanitasi_data['_id'] = result.inserted_id
        
        print(f"✅ [SANITASI CREATE] Successfully inserted! ID: {result.inserted_id}, Collection: sanitasi")
        return jsonify(json_serialize(sanitasi_data)), 201
    except Exception as e:
        print(f"❌ [SANITASI CREATE] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/sanitasi/<sanitasi_id>', methods=['PUT'])
def update_sanitasi(sanitasi_id):
    """Update sanitasi"""
    try:
        data = request.json
        try:
            sanitasi = db.sanitasi.find_one({'_id': ObjectId(sanitasi_id)})
        except:
            sanitasi = db.sanitasi.find_one({'id': int(sanitasi_id)})
        if not sanitasi:
            return jsonify({'error': 'Sanitasi not found'}), 404
        
        update_data = {}
        for field in ['tanggal', 'waktu', 'tipe', 'namaPetugas', 'fotos', 'checklist', 'status']:
            if field in data:
                update_data[field] = data[field]
        
        db.sanitasi.update_one({'_id': sanitasi['_id']}, {'$set': update_data})
        updated = db.sanitasi.find_one({'_id': sanitasi['_id']})
        return jsonify(json_serialize(updated)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sanitasi/<sanitasi_id>', methods=['DELETE'])
def delete_sanitasi(sanitasi_id):
    """Delete sanitasi"""
    try:
        try:
            sanitasi = db.sanitasi.find_one({'_id': ObjectId(sanitasi_id)})
        except:
            sanitasi = db.sanitasi.find_one({'id': int(sanitasi_id)})
        if not sanitasi:
            return jsonify({'error': 'Sanitasi not found'}), 404
        db.sanitasi.delete_one({'_id': sanitasi['_id']})
        return jsonify({'message': 'Sanitasi deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== KEUANGAN ENDPOINTS ====================

@app.route('/api/keuangan', methods=['GET'])
def get_keuangan():
    """Get all keuangan data"""
    try:
        keuangan = list(db.keuangan.find().sort('id', 1))
        print(f"📊 [KEUANGAN GET] Retrieved {len(keuangan)} documents from MongoDB collection 'keuangan'")
        return jsonify(json_serialize(keuangan)), 200
    except Exception as e:
        print(f"❌ [KEUANGAN GET] ERROR: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/keuangan/<keuangan_id>', methods=['GET'])
def get_keuangan_by_id(keuangan_id):
    """Get keuangan by ID"""
    try:
        try:
            keuangan = db.keuangan.find_one({'_id': ObjectId(keuangan_id)})
        except:
            keuangan = db.keuangan.find_one({'id': int(keuangan_id)})
        if not keuangan:
            return jsonify({'error': 'Keuangan not found'}), 404
        return jsonify(json_serialize(keuangan)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/keuangan', methods=['POST'])
def create_keuangan():
    """Create new keuangan"""
    try:
        data = request.json
        # Validasi notes wajib diisi
        notes = data.get('notes', '').strip() if data.get('notes') else ''
        if not notes:
            return jsonify({'error': 'Notes wajib diisi'}), 400
        
        new_id = get_next_id('keuangan')
        keuangan_data = {
            'id': new_id,
            'tanggal': data.get('tanggal'),
            'jenisPengeluaran': data.get('jenisPengeluaran'),
            'idBahanBaku': data.get('idBahanBaku'),
            'nilai': data.get('nilai'),
            'notes': notes
        }
        print(f"🔵 [KEUANGAN CREATE] Inserting to MongoDB collection 'keuangan': {keuangan_data}")
        result = db.keuangan.insert_one(keuangan_data)
        keuangan_data['_id'] = result.inserted_id
        print(f"✅ [KEUANGAN CREATE] Successfully inserted! ID: {result.inserted_id}, Collection: keuangan")
        return jsonify(json_serialize(keuangan_data)), 201
    except Exception as e:
        print(f"❌ [KEUANGAN CREATE] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/keuangan/<keuangan_id>', methods=['PUT'])
def update_keuangan(keuangan_id):
    """Update keuangan"""
    try:
        data = request.json
        try:
            keuangan = db.keuangan.find_one({'_id': ObjectId(keuangan_id)})
        except:
            keuangan = db.keuangan.find_one({'id': int(keuangan_id)})
        if not keuangan:
            return jsonify({'error': 'Keuangan not found'}), 404
        
        # Validasi notes wajib diisi jika ada di data
        if 'notes' in data:
            notes = data.get('notes', '').strip() if data.get('notes') else ''
            if not notes:
                return jsonify({'error': 'Notes wajib diisi'}), 400
        
        update_data = {}
        for field in ['tanggal', 'jenisPengeluaran', 'idBahanBaku', 'nilai', 'notes']:
            if field in data:
                if field == 'notes':
                    update_data[field] = data[field].strip() if data[field] else ''
                else:
                    update_data[field] = data[field]
        
        db.keuangan.update_one({'_id': keuangan['_id']}, {'$set': update_data})
        updated = db.keuangan.find_one({'_id': keuangan['_id']})
        return jsonify(json_serialize(updated)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/keuangan/<keuangan_id>', methods=['DELETE'])
def delete_keuangan(keuangan_id):
    """Delete keuangan"""
    try:
        try:
            keuangan = db.keuangan.find_one({'_id': ObjectId(keuangan_id)})
        except:
            keuangan = db.keuangan.find_one({'id': int(keuangan_id)})
        if not keuangan:
            return jsonify({'error': 'Keuangan not found'}), 404
        db.keuangan.delete_one({'_id': keuangan['_id']})
        return jsonify({'message': 'Keuangan deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== AUTHENTICATION ENDPOINTS ====================

@app.route('/api/auth/session', methods=['GET'])
def check_session():
    """Check if user has valid session - returns 200 with logged_in status"""
    try:
        if 'user_id' in session and session.get('username') and session.get('role'):
            return jsonify({
                'logged_in': True,
                'username': session.get('username'),
                'role': session.get('role'),
                'user_id': session.get('user_id'),
                'user_email': session.get('user_email', ''),
                'user_name': session.get('user_name', '')
            }), 200
        else:
            return jsonify({
                'logged_in': False,
                'message': 'No active session'
            }), 200
    except Exception as e:
        print(f"❌ Session check error: {str(e)}")
        return jsonify({
            'logged_in': False,
            'error': str(e)
        }), 500

@app.route('/api/auth/check', methods=['GET'])
def auth_check():
    """Check if user has valid session - returns 200 if logged in, 401 if not"""
    try:
        if 'user_id' in session and session.get('username') and session.get('role'):
            return jsonify({
                'logged_in': True,
                'username': session.get('username'),
                'role': session.get('role'),
                'user_id': session.get('user_id'),
                'user_email': session.get('user_email', ''),
                'user_name': session.get('user_name', '')
            }), 200
        else:
            return jsonify({
                'logged_in': False,
                'message': 'No active session'
            }), 401
    except Exception as e:
        print(f"❌ Auth check error: {str(e)}")
        return jsonify({
            'logged_in': False,
            'error': str(e)
        }), 500

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    """Logout user - clear session"""
    try:
        username = session.get('username', 'Unknown')
        session.clear()
        print(f"✅ Logout successful: User '{username}'")
        return jsonify({
            'success': True,
            'message': 'Logout berhasil'
        }), 200
    except Exception as e:
        print(f"❌ Logout error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """Login endpoint - validates username/password and returns user data"""
    try:
        data = request.json
        
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        role = data.get('role', '').strip()
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Normalize role
        normalized_role = None
        if role:
            role_lower = role.lower()
            if role_lower == 'admin':
                normalized_role = 'Admin'
            elif role_lower == 'owner':
                normalized_role = 'Owner'
            elif role_lower == 'karyawan':
                normalized_role = 'Karyawan'
        
        # Find user by username (case-insensitive)
        user = db.users.find_one({
            'username': {'$regex': f'^{username}$', '$options': 'i'}
        })
        
        if not user:
            print(f"❌ Login failed: User '{username}' not found in database")
            print(f"   Searched with regex: ^{username}$ (case-insensitive)")
            return jsonify({'error': 'Username atau password salah'}), 401
        
        print(f"✓ User found: {user.get('username')} (ID: {user.get('id')}, Role: {user.get('role')})")
        
        # Hash the provided password using SHA-256 (same as register)
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        # Get stored password from database
        stored_password = user.get('password', '')
        
        # Debug logging (do not log actual passwords, only hashes for comparison)
        print(f"   Stored password hash length: {len(stored_password)}")
        print(f"   Provided password hash length: {len(password_hash)}")
        print(f"   Hash match: {stored_password == password_hash}")
        
        # Compare hashed passwords
        if not stored_password or stored_password != password_hash:
            print(f"❌ Login failed: Password mismatch for user '{username}'")
            print(f"   Stored hash: {stored_password[:20]}..." if stored_password else "   Stored hash: (empty)")
            print(f"   Provided hash: {password_hash[:20]}...")
            return jsonify({'error': 'Username atau password salah'}), 401
        
        # Check role if provided
        if normalized_role and user.get('role') != normalized_role:
            print(f"❌ Login failed: Role mismatch for user '{username}'. Expected: {normalized_role}, Got: {user.get('role')}")
            return jsonify({'error': f'Role tidak sesuai. Halaman ini hanya untuk {normalized_role}'}), 403
        
        # Check status
        if user.get('status') != 'Aktif':
            print(f"❌ Login failed: User '{username}' is not active (status: {user.get('status')})")
            return jsonify({'error': 'Akun Anda tidak aktif. Silakan hubungi administrator'}), 403
        
        # Prepare user data to return (without password)
        user_data = {
            '_id': str(user['_id']),
            'id': user.get('id'),
            'username': user.get('username'),
            'namaLengkap': user.get('namaLengkap', ''),
            'email': user.get('email', ''),
            'role': user.get('role'),
            'status': user.get('status'),
            'noTelepon': user.get('noTelepon', ''),
            'tanggalLahir': user.get('tanggalLahir', ''),
            'jenisKelamin': user.get('jenisKelamin', ''),
            'alamat': user.get('alamat', '')
        }
        
        # Set Flask session
        session.permanent = True
        session['user_id'] = str(user['_id'])
        session['username'] = user.get('username')
        session['role'] = user.get('role')
        session['user_email'] = user.get('email', '')
        session['user_name'] = user.get('namaLengkap', '')
        
        print(f"✅ Login successful: User '{username}' (Role: {user.get('role')}) - Session created")
        print(f"   Session keys: {list(session.keys())}")
        
        response = jsonify({
            'success': True,
            'user': user_data,
            'message': 'Login berhasil'
        })
        
        # Flask handles session cookie automatically with configured settings
        # Ensure session is saved before returning response
        session.modified = True
        
        return response, 200
        
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        return jsonify({'error': f'Terjadi kesalahan saat login: {str(e)}'}), 500

# ==================== USERS ENDPOINTS ====================

@app.route('/api/users', methods=['GET'])
def get_users():
    """Get all users"""
    try:
        users = list(db.users.find().sort('id', 1))
        # Don't return password
        for user in users:
            user.pop('password', None)
        return jsonify(json_serialize(users)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<user_id>', methods=['GET'])
def get_user_by_id(user_id):
    """Get user by ID"""
    try:
        try:
            user = db.users.find_one({'_id': ObjectId(user_id)})
        except:
            user = db.users.find_one({'id': int(user_id)}) or \
                  db.users.find_one({'username': user_id})
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user.pop('password', None)
        return jsonify(json_serialize(user)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/users', methods=['POST'])
def create_user():
    """Create new user"""
    try:
        data = request.json
        
        required_fields = ['username', 'password', 'namaLengkap', 'email', 'role']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Check username uniqueness
        existing_username = db.users.find_one({'username': {'$regex': f"^{data['username']}$", '$options': 'i'}})
        if existing_username:
            return jsonify({'error': 'Username sudah digunakan'}), 400
        
        # Check email uniqueness if provided
        if data.get('email'):
            existing_email = db.users.find_one({'email': {'$regex': f"^{data['email']}$", '$options': 'i'}})
            if existing_email:
                return jsonify({'error': 'Email sudah digunakan'}), 400
        
        new_id = get_next_id('users')
        
        # Hash password using SHA-256 (consistent with login)
        password_hash = hashlib.sha256(data['password'].encode()).hexdigest()
        
        print(f"📝 Creating new user: {data['username']}")
        print(f"   Password hash length: {len(password_hash)}")
        print(f"   Hash: {password_hash[:20]}...")
        
        user_data = {
            'id': new_id,
            'username': data['username'],
            'password': password_hash,
            'namaLengkap': data['namaLengkap'],
            'email': data.get('email', ''),
            'noTelepon': data.get('noTelepon', ''),
            'tanggalLahir': data.get('tanggalLahir', ''),
            'jenisKelamin': data.get('jenisKelamin', ''),
            'alamat': data.get('alamat', ''),
            'role': data['role'],
            'status': data.get('status', 'Aktif')
        }
        
        print(f"🔵 [USERS CREATE] Inserting to MongoDB collection 'users': {user_data}")
        result = db.users.insert_one(user_data)
        print(f"✅ [USERS CREATE] Successfully inserted! ID: {result.inserted_id}, Collection: users")
        user_data['_id'] = result.inserted_id
        
        print(f"✅ User created successfully: {user_data['username']} (ID: {new_id}, _id: {user_data['_id']})")
        
        # Remove password before returning
        user_data.pop('password', None)
        
        # Auto-login after registration (set session)
        session.permanent = True
        session['user_id'] = str(result.inserted_id)
        session['username'] = user_data['username']
        session['role'] = user_data['role']
        session['user_email'] = user_data.get('email', '')
        session['user_name'] = user_data.get('namaLengkap', '')
        
        response = jsonify(json_serialize(user_data))
        # Flask handles session cookie automatically, no need to set manually
        return response, 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<user_id>', methods=['PUT'])
def update_user(user_id):
    """Update user"""
    try:
        data = request.json
        
        try:
            user = db.users.find_one({'_id': ObjectId(user_id)})
        except:
            user = db.users.find_one({'id': int(user_id)}) or \
                  db.users.find_one({'username': user_id})
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if 'username' in data:
            existing = db.users.find_one({
                'username': data['username'],
                '_id': {'$ne': user['_id']}
            })
            if existing:
                return jsonify({'error': 'Username already exists'}), 400
        
        update_data = {}
        for field in ['username', 'namaLengkap', 'email', 'noTelepon', 
                     'tanggalLahir', 'jenisKelamin', 'alamat', 'role', 'status']:
            if field in data:
                update_data[field] = data[field]
        
        if 'password' in data and data['password']:
            # Hash password using SHA-256 (consistent with register and login)
            update_data['password'] = hashlib.sha256(data['password'].encode()).hexdigest()
            print(f"📝 Password updated for user ID: {user_id}")
        
        db.users.update_one(
            {'_id': user['_id']},
            {'$set': update_data}
        )
        
        updated = db.users.find_one({'_id': user['_id']})
        updated.pop('password', None)
        return jsonify(json_serialize(updated)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete user"""
    try:
        try:
            user = db.users.find_one({'_id': ObjectId(user_id)})
        except:
            user = db.users.find_one({'id': int(user_id)}) or \
                  db.users.find_one({'username': user_id})
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        db.users.delete_one({'_id': user['_id']})
        return jsonify({'message': 'User deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== SETTINGS ENDPOINTS ====================

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get user settings"""
    try:
        settings = db.userSettings.find_one({'userId': request.args.get('userId')})
        if not settings:
            # Return default settings
            default_settings = {
                'displayName': '',
                'timezone': 'WIB',
                'language': 'id',
                'emailNotification': True,
                'systemNotification': True,
                'updateNotification': False,
                'twoFactorAuth': False,
                'publicProfile': False,
                'shareActivity': False,
                'dataRetention': 365
            }
            return jsonify(json_serialize(default_settings)), 200
        
        settings.pop('_id', None)
        return jsonify(json_serialize(settings)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['POST', 'PUT'])
def save_settings():
    """Save user settings"""
    try:
        data = request.json
        
        if 'userId' not in data:
            return jsonify({'error': 'Missing userId'}), 400
        
        # Upsert settings
        db.userSettings.update_one(
            {'userId': data['userId']},
            {'$set': data},
            upsert=True
        )
        
        settings = db.userSettings.find_one({'userId': data['userId']})
        settings.pop('_id', None)
        return jsonify(json_serialize(settings)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== LAPORAN PDF ENDPOINTS ====================

@app.route('/api/laporan/upload', methods=['POST'])
def upload_laporan_pdf():
    """Upload PDF laporan ke server dan simpan ke static/laporan/"""
    try:
        data = request.json
        
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        # Validasi required fields
        required_fields = ['pdfData', 'type', 'id']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        pdf_type = data['type']  # 'hasil-produksi', 'produksi', 'data-kemasan', dll
        item_id = data['id']
        pdf_data = data['pdfData']  # Base64 encoded PDF
        
        # Validasi PDF data (harus base64)
        if not pdf_data.startswith('data:application/pdf;base64,'):
            # Jika tidak ada prefix, tambahkan
            if not pdf_data.startswith('data:'):
                pdf_data = 'data:application/pdf;base64,' + pdf_data
        
        # Extract base64 data
        if ',' in pdf_data:
            pdf_base64 = pdf_data.split(',')[1]
        else:
            pdf_base64 = pdf_data
        
        # Decode base64 to bytes
        try:
            pdf_bytes = base64.b64decode(pdf_base64)
        except Exception as e:
            return jsonify({'error': f'Invalid base64 PDF data: {str(e)}'}), 400
        
        # Validasi bahwa ini benar-benar PDF (cek magic bytes)
        if not pdf_bytes.startswith(b'%PDF'):
            return jsonify({'error': 'Invalid PDF file format'}), 400
        
        # Buat folder static/laporan jika belum ada
        laporan_dir = join(dirname(__file__), 'static', 'laporan')
        if not exists(laporan_dir):
            os.makedirs(laporan_dir)
            print(f"✅ Created directory: {laporan_dir}")
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'laporan_{pdf_type}_{item_id}_{timestamp}.pdf'
        filepath = join(laporan_dir, filename)
        
        # Simpan file PDF
        with open(filepath, 'wb') as f:
            f.write(pdf_bytes)
        
        print(f"✅ PDF saved: {filepath}")
        
        # Generate URL untuk akses file
        # PERBAIKAN: Pastikan URL selalu benar format: /static/laporan/filename.pdf
        # Backend mengirim relative URL dan fullUrl (absolute)
        relative_url = f"/static/laporan/{filename}"
        
        # Generate absolute URL untuk QR Code
        base_url = request.url_root.rstrip('/')
        full_url = f"{base_url}{relative_url}"
        
        # Validasi URL format
        if not relative_url.startswith("/static/laporan/"):
            raise ValueError(f"Invalid relative URL format: {relative_url}")
        if not full_url.startswith("http"):
            raise ValueError(f"Invalid full URL format: {full_url}")
        
        # Log URL untuk debugging
        print(f"🔗 Generated PDF URLs:")
        print(f"  - Relative URL: {relative_url}")
        print(f"  - Full URL: {full_url}")
        print(f"  - Request host: {request.host}")
        print(f"  - Request scheme: {request.scheme}")
        
        # Simpan metadata ke MongoDB (opsional, untuk tracking)
        try:
            db.laporanPdf.insert_one({
                'type': pdf_type,
                'itemId': item_id,
                'filename': filename,
                'url': relative_url,  # Simpan relative URL
                'fullUrl': full_url,  # Simpan full URL untuk QR Code
                'createdAt': datetime.now(),
                'fileSize': len(pdf_bytes)
            })
        except Exception as e:
            print(f"⚠️ Warning: Could not save metadata to MongoDB: {str(e)}")
            # Tidak fatal, lanjutkan saja
        
        return jsonify({
            'success': True,
            'url': relative_url,  # Relative URL: /static/laporan/filename.pdf
            'fullUrl': full_url,  # Full absolute URL: http://HOST:PORT/static/laporan/filename.pdf
            'filename': filename,
            'message': 'PDF uploaded successfully'
        }), 200
        
    except Exception as e:
        print(f"❌ Error uploading PDF: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/static/laporan/<filename>')
def serve_laporan_pdf(filename):
    """Serve PDF laporan dari static/laporan/"""
    try:
        laporan_dir = join(dirname(__file__), 'static', 'laporan')
        filepath = join(laporan_dir, filename)
        
        # Security: validasi filename (prevent path traversal)
        if not filename.endswith('.pdf') or '..' in filename or '/' in filename:
            return jsonify({'error': 'Invalid filename'}), 400
        
        if not exists(filepath):
            return jsonify({'error': 'PDF not found'}), 404
        
        return send_from_directory(laporan_dir, filename, mimetype='application/pdf')
    except Exception as e:
        print(f"❌ Error serving PDF: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/laporan/list', methods=['GET'])
def list_laporan_pdf():
    """List semua PDF laporan yang tersimpan"""
    try:
        pdf_type = request.args.get('type')
        item_id = request.args.get('id')
        
        query = {}
        if pdf_type:
            query['type'] = pdf_type
        if item_id:
            query['itemId'] = item_id
        
        laporan_list = list(db.laporanPdf.find(query).sort('createdAt', -1))
        return jsonify(json_serialize(laporan_list)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== PEMESANAN ENDPOINTS ====================

def _berat_kg_dari_baris_pemesanan(it):
    """Ambil berat (kg) dari kloter/barisan: beratKg, berat, atau jumlahPesananKg."""
    if not isinstance(it, dict):
        return 0.0
    for key in ('beratKg', 'berat', 'jumlahPesananKg'):
        if key not in it or it[key] is None:
            continue
        try:
            return float(it[key])
        except (TypeError, ValueError):
            continue
    return 0.0


def _bool_coerce_lunas_default_true(raw):
    """True jika pembayaran dianggap lunas (masuk total terbayar / pemasukan). Default True untuk dokumen lama."""
    if raw is None:
        return True
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in ('false', '0', 'no', 'tidak', 'belum', 'belum lunas'):
        return False
    if s in ('true', '1', 'yes', 'ya', 'lunas'):
        return True
    return True


def _pembayaran_kloter_lunas_true(it):
    if not isinstance(it, dict):
        return True
    return _bool_coerce_lunas_default_true(it.get('pembayaranKloterLunas'))


def _termin_lunas_true(it):
    if not isinstance(it, dict):
        return True
    return _bool_coerce_lunas_default_true(it.get('terminLunas'))


def _jumlah_pembayaran_kloter_nominal(it):
    """Nominal jumlahPembayaranKloter per baris (tanpa filter lunas)."""
    if not isinstance(it, dict):
        return 0.0
    try:
        v = float(it.get('jumlahPembayaranKloter') or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, v)


def _jumlah_pembayaran_kloter_from_row(it):
    """Nominal yang masuk total terbayar: hanya jika pembayaranKloterLunas (default True)."""
    if not _pembayaran_kloter_lunas_true(it):
        return 0.0
    return _jumlah_pembayaran_kloter_nominal(it)


def _sum_jumlah_pembayaran_kloter(kloter_list):
    """Σ nominal per kloter yang sudah lunas (masuk sisa tagihan / agregat)."""
    if not kloter_list:
        return 0.0
    return round(sum(_jumlah_pembayaran_kloter_from_row(row) for row in kloter_list), 2)


def _sum_jumlah_pembayaran_kloter_semua(kloter_list):
    """Σ semua nominal per kloter (validasi tidak melebihi total)."""
    if not kloter_list:
        return 0.0
    return round(sum(_jumlah_pembayaran_kloter_nominal(row) for row in kloter_list), 2)


def _normalize_pembayaran_bertahap_baris_tambahan(data):
    """
    Array opsional pembayaran bertahap tambahan (termin / gabungan), selain nominal per baris kloter produk.
    Maksimal 30 baris. Tiap elemen: { jumlahRp: number, catatan?: str, terminLunas?: bool }.
    terminLunas=False: nominal tercatat tetapi tidak masuk total terbayar / pemasukan hingga diubah.
    Mengembalikan (list_tersimpan, pesan_error_atau_None).
    """
    raw = data.get('pembayaranBertahapBaris')
    if raw is None:
        return [], None
    if not isinstance(raw, list):
        return None, 'pembayaranBertahapBaris harus berupa array'
    if len(raw) > 30:
        return None, 'Maksimal 30 baris pembayaran bertahap tambahan'
    out = []
    for idx, it in enumerate(raw):
        if not isinstance(it, dict):
            return None, f'Baris pembayaran {idx + 1}: format tidak valid'
        try:
            jr = float(it.get('jumlahRp') or 0)
        except (TypeError, ValueError):
            return None, f'Baris pembayaran {idx + 1}: jumlahRp tidak valid'
        if jr < 0:
            return None, f'Baris pembayaran {idx + 1}: jumlahRp tidak boleh negatif'
        if jr <= 0 and not (str(it.get('catatan') or '').strip()):
            continue
        row = {'jumlahRp': round(max(0.0, jr), 2)}
        cat = (str(it.get('catatan') or '')).strip()
        if cat:
            row['catatan'] = cat[:500]
        row['terminLunas'] = _termin_lunas_true(it)
        out.append(row)
    return out, None


def _sum_pembayaran_bertahap_baris_tambahan(baris_list):
    """Σ jumlahRp hanya baris terminLunas (default True). Masuk total terbayar / sisa."""
    if not baris_list or not isinstance(baris_list, list):
        return 0.0
    s = 0.0
    for it in baris_list:
        if not isinstance(it, dict):
            continue
        if not _termin_lunas_true(it):
            continue
        try:
            s += float(it.get('jumlahRp') or 0)
        except (TypeError, ValueError):
            continue
    return round(max(0.0, s), 2)


def _sum_pembayaran_bertahap_baris_tambahan_semua(baris_list):
    """Σ semua jumlahRp (validasi batas total tagihan)."""
    if not baris_list or not isinstance(baris_list, list):
        return 0.0
    s = 0.0
    for it in baris_list:
        if not isinstance(it, dict):
            continue
        try:
            s += float(it.get('jumlahRp') or 0)
        except (TypeError, ValueError):
            continue
    return round(max(0.0, s), 2)


def _compute_pemesanan_pembayaran_kloter_agg(status_bayar, total_harga, kloter_list, baris_tambahan=None):
    """
    totalPembayaranKloter (tersimpan) = Σ yang sudah lunas: per kloter (pembayaranKloterLunas) +
    baris tambahan dengan terminLunas.
    totalPembayaranSaatIni = total harga − Σ itu (sisa tagihan).
    Validasi: jumlah semua nominal (termasuk belum lunas) tidak boleh melebihi total.
    Mengembalikan (sum_pay_lunas, sisa, error_string_atau_None).
    """
    rows = kloter_list if isinstance(kloter_list, list) else []
    sum_lunas = _sum_jumlah_pembayaran_kloter(rows)
    sum_lunas = round(sum_lunas + _sum_pembayaran_bertahap_baris_tambahan(baris_tambahan), 2)
    sum_semua = round(
        _sum_jumlah_pembayaran_kloter_semua(rows)
        + _sum_pembayaran_bertahap_baris_tambahan_semua(baris_tambahan),
        2,
    )
    th = float(total_harga or 0)
    sisa = round(max(0.0, th - sum_lunas), 2)
    sb = (status_bayar or '').strip()
    if sb == 'Pembayaran Bertahap':
        tol = _total_harga_pemesanan_tolerance(th)
        if sum_semua - th > tol:
            return None, None, 'Jumlah nominal pembayaran (termasuk yang belum lunas) tidak boleh melebihi total harga pemesanan.'
        if sum_lunas - th > tol:
            return None, None, 'Jumlah pembayaran yang sudah lunas tidak boleh melebihi total harga pemesanan.'
    return sum_lunas, sisa, None


def _get_tipe_produk_master_set():
    """Nama tipe produk dari koleksi dataProduk (Kelola Data → tab Produk)."""
    names = set()
    try:
        for doc in db.dataProduk.find():
            n = (doc.get('nama') or '').strip()
            if n:
                names.add(n)
    except Exception as e:
        print(f"⚠️ [TIPE PRODUK MASTER] {e}")
    if not names:
        names = {'Green Beans', 'Pixel'}
    return names


def _tipe_produk_valid(tp):
    tp = (tp or '').strip()
    return bool(tp) and tp in _get_tipe_produk_master_set()


# Tipe produk yang hanya untuk invoice (tidak terikat stok hasil produksi).
# Dicocokkan case-insensitive setelah normalisasi whitespace.
_INVOICE_ONLY_TIPE_PRODUK = {
    'roasted beans',
    'argopuro walida collective',
}

_TIPE_PRODUK_WS_RE = re.compile(r'[\s\u00A0]+')


def _normalize_tipe_produk_for_match(tp):
    return _TIPE_PRODUK_WS_RE.sub(' ', str(tp or '')).strip().lower()


_TIPE_PRODUK_COL_RE = re.compile(r'\bcol[a-z]*')


def _is_tipe_produk_invoice_only(tp):
    """Tipe produk hanya-invoice (tidak memotong stok hasil produksi).

    Saat ini mencakup `Roasted Beans` dan `Argopuro Walida Collective`.
    Pencocokan toleran terhadap variasi whitespace/case dan ejaan ringan
    untuk produk Argopuro Walida (mis. "Colective", "Collection").
    """
    norm = _normalize_tipe_produk_for_match(tp)
    if not norm:
        return False
    if norm in _INVOICE_ONLY_TIPE_PRODUK:
        return True
    if 'argopuro' in norm and 'walida' in norm and _TIPE_PRODUK_COL_RE.search(norm):
        return True
    return False


def _line_items_all_invoice_only(line_items):
    return bool(line_items) and all(
        _is_tipe_produk_invoice_only(x.get('tipeProduk')) for x in line_items
    )


def _line_items_stock_lines(line_items):
    return [x for x in (line_items or []) if not _is_tipe_produk_invoice_only(x.get('tipeProduk'))]


def _finalize_pemesanan_invoice_only(id_pembelian, pemesanan, line_items, tanggal_ordering):
    """
    Selesaikan pemesanan invoice-only (mis. Roasted Beans, Argopuro Walida Collective):
    tidak insert hasilProduksi, tidak mengurangi stok; catat jejak ordering untuk audit.
    """
    jumlah_total = float(sum(float(x.get('jumlahPesananKg') or 0) for x in line_items))
    multi = len(line_items) > 1
    tipe_label = 'Campuran' if multi else (line_items[0].get('tipeProduk') or '').strip()
    new_id = get_next_id('ordering')
    ordering_data = {
        'id': new_id,
        'idPembelian': id_pembelian,
        'idProduksi': '',
        'tipeProduk': tipe_label,
        'jumlahPesananKg': jumlah_total,
        'kloterRingkasan': line_items,
        'stokSebelum': None,
        'stokSesudah': None,
        'statusPemesanan': 'Complete',
        'tanggalOrdering': tanggal_ordering,
        'invoiceOnly': True,
        'createdAt': datetime.now(),
        'updatedAt': datetime.now(),
    }
    result_ordering = db.ordering.insert_one(ordering_data)
    ordering_data['_id'] = result_ordering.inserted_id
    db.pemesanan.update_one(
        {'_id': pemesanan['_id']},
        {'$set': {
            'statusPemesanan': 'Complete',
            'statusPembayaran': 'Lunas',
            'updatedAt': datetime.now(),
        }},
    )
    return ordering_data


def _normalize_pemesanan_kloter_from_body(data):
    """
    Normalisasi array `kloter` (model utama) atau `items` (kompatibel lama).
    Tiap kloter: tipeProduk, jenisKopi, prosesPengolahan, beratKg, hargaPerKg,
    subtotal; jumlahPesananKg disamakan dengan beratKg untuk alur stok/ordering.
    Opsional: jumlahPembayaranKloter (Rp) untuk pembayaran bertahap per kloter.
    Mengembalikan (list_atau_None, pesan_error_atau_None).
    """
    raw = None
    kloter_in = data.get('kloter')
    if isinstance(kloter_in, list) and len(kloter_in) > 0:
        raw = kloter_in
    else:
        items_in = data.get('items')
        if isinstance(items_in, list) and len(items_in) > 0:
            raw = items_in
    if raw is None:
        return None, None
    out = []
    for idx, it in enumerate(raw):
        if not isinstance(it, dict):
            return None, f'Kloter {idx + 1}: format tidak valid'
        tp = (it.get('tipeProduk') or '').strip()
        jk = (it.get('jenisKopi') or '').strip()
        pr = (it.get('prosesPengolahan') or '').strip()
        jm = _berat_kg_dari_baris_pemesanan(it)
        try:
            hp = float(it.get('hargaPerKg') or 0)
        except (TypeError, ValueError):
            return None, f'Kloter {idx + 1}: harga tidak valid'
        if not _tipe_produk_valid(tp):
            allowed = ', '.join(sorted(_get_tipe_produk_master_set()))
            return None, (
                f'Kloter {idx + 1}: tipeProduk tidak valid. '
                f'Pilih dari master data (Kelola Data → Produk): {allowed}'
            )
        if not jk or not pr:
            return None, f'Kloter {idx + 1}: jenis kopi dan proses pengolahan wajib diisi'
        if jm <= 0 or hp <= 0:
            return None, f'Kloter {idx + 1}: berat (kg) dan harga per kg harus lebih dari 0'
        sub = round(jm * hp, 2)
        pay = _jumlah_pembayaran_kloter_nominal(it)
        row_out = {
            'tipeProduk': tp,
            'jenisKopi': jk,
            'prosesPengolahan': pr,
            'beratKg': jm,
            'hargaPerKg': hp,
            'subtotal': sub,
            'jumlahPesananKg': jm,
        }
        if pay > 0:
            row_out['jumlahPembayaranKloter'] = round(pay, 2)
            row_out['pembayaranKloterLunas'] = _pembayaran_kloter_lunas_true(it)
        out.append(row_out)
    if not out:
        return None, 'Tidak ada kloter yang valid'
    return out, None


def _total_harga_pemesanan_tolerance(expected):
    """Selisih yang diizinkan antara total dari klien vs server (float / pembulatan kloter, nilai Rupiah besar)."""
    exp = abs(float(expected or 0))
    return max(2.0, exp * 1e-6)


def _normalize_tipe_pajak(raw):
    """penjumlahan = ditambah ke subtotal; pengurangan = mengurangi subtotal."""
    t = str(raw or 'penjumlahan').strip().lower()
    if t in ('pengurangan', 'kurang', 'minus'):
        return 'pengurangan'
    return 'penjumlahan'


def _hitung_total_pemesanan_dari_komponen(subtotal_barang, biaya_pajak, biaya_pengiriman, tipe_pajak):
    sub = max(0.0, float(subtotal_barang or 0))
    pajak = max(0.0, float(biaya_pajak or 0))
    kirim = max(0.0, float(biaya_pengiriman or 0))
    if _normalize_tipe_pajak(tipe_pajak) == 'pengurangan':
        return max(0.0, round(sub - pajak + kirim, 2))
    return round(sub + pajak + kirim, 2)


def _normalize_status_pembayaran_canonical(raw):
    """
    Samakan variasi input status pembayaran ke nilai kanonik.
    Mengembalikan salah satu dari: Lunas, Belum Lunas, Pembayaran Bertahap, atau None jika tidak dikenali.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    low = ' '.join(s.lower().replace('_', ' ').split())
    if low in ('lunas', 'paid', 'sudah bayar', 'sudah lunas', 'bayar lunas'):
        return 'Lunas'
    if low in ('belum lunas', 'belum bayar', 'unpaid', 'pending', 'belum dibayar'):
        return 'Belum Lunas'
    if 'bertahap' in low or low in ('cicilan', 'partial', 'pembayaran bertahap'):
        return 'Pembayaran Bertahap'
    if s in ('Lunas', 'Belum Lunas', 'Pembayaran Bertahap'):
        return s
    return None


def pemesanan_items_from_doc(doc):
    """Baca baris barang untuk stok/ordering: kloter[] → items[] → bentuk tunggal root."""
    if not doc:
        return []
    raw = None
    kl = doc.get('kloter')
    if isinstance(kl, list) and len(kl) > 0:
        raw = kl
    else:
        it = doc.get('items')
        if isinstance(it, list) and len(it) > 0:
            raw = it
    if raw:
        lines = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            jm = _berat_kg_dari_baris_pemesanan(row)
            try:
                hp = float(row.get('hargaPerKg') or 0)
            except (TypeError, ValueError):
                hp = 0.0
            if jm <= 0 or hp <= 0:
                continue
            lines.append({
                'tipeProduk': (row.get('tipeProduk') or '').strip(),
                'jenisKopi': (row.get('jenisKopi') or '').strip(),
                'prosesPengolahan': (row.get('prosesPengolahan') or '').strip(),
                'beratKg': jm,
                'jumlahPesananKg': jm,
                'hargaPerKg': hp,
                'subtotal': float(row.get('subtotal') or round(jm * hp, 2) or 0),
            })
        return lines
    jm = float(doc.get('jumlahPesananKg') or 0)
    hp = float(doc.get('hargaPerKg') or 0)
    if jm <= 0 or hp <= 0:
        return []
    return [{
        'tipeProduk': (doc.get('tipeProduk') or '').strip(),
        'jenisKopi': (doc.get('jenisKopi') or '').strip(),
        'prosesPengolahan': (doc.get('prosesPengolahan') or '').strip(),
        'beratKg': jm,
        'jumlahPesananKg': jm,
        'hargaPerKg': hp,
        'subtotal': round(jm * hp, 2),
    }]


@app.route('/api/pemesanan', methods=['GET'])
def get_pemesanan():
    """Get all pemesanan data"""
    try:
        # Sort by id if exists, fallback to _id for documents without id field
        try:
            pemesanan = list(db.pemesanan.find().sort('id', 1))
        except Exception:
            pemesanan = list(db.pemesanan.find())
        print(f"📊 [PEMESANAN GET] Retrieved {len(pemesanan)} documents from MongoDB collection 'pemesanan'")
        return jsonify(json_serialize(pemesanan)), 200
    except Exception as e:
        print(f"❌ [PEMESANAN GET] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/pemesanan/<pemesanan_id>', methods=['GET'])
def get_pemesanan_by_id(pemesanan_id):
    """Get pemesanan by ID"""
    try:
        try:
            pemesanan = db.pemesanan.find_one({'_id': ObjectId(pemesanan_id)})
        except:
            pemesanan = db.pemesanan.find_one({'id': int(pemesanan_id)}) or \
                       db.pemesanan.find_one({'idPembelian': pemesanan_id})
        
        if not pemesanan:
            return jsonify({'error': 'Pemesanan not found'}), 404
        
        return jsonify(json_serialize(pemesanan)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pemesanan', methods=['POST'])
def create_pemesanan():
    """
    Create new pemesanan - HANYA PENCATATAN PERMINTAAN
    Endpoint ini TIDAK BOLEH mengurangi stok.
    Stok hanya dikurangi saat proses ordering dipanggil (/api/ordering/proses).
    """
    try:
        data = request.json
        
        base_required = ['idPembelian', 'namaPembeli', 'tipePemesanan', 'totalHarga', 'statusPemesanan']
        for field in base_required:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        kloter_norm, kloter_err = _normalize_pemesanan_kloter_from_body(data)
        use_kloter = kloter_norm is not None
        if use_kloter and kloter_err:
            return jsonify({'error': kloter_err}), 400
        if not use_kloter:
            legacy_req = ['tipeProduk', 'prosesPengolahan', 'jenisKopi', 'jumlahPesananKg', 'hargaPerKg']
            for field in legacy_req:
                if field not in data:
                    return jsonify({'error': f'Missing required field: {field}'}), 400
        
        tipe_pm = (data.get('tipePemesanan') or '').strip()
        if tipe_pm not in ('Lokal', 'International', 'E-commerce'):
            return jsonify({'error': 'tipePemesanan harus Lokal, International, atau E-commerce'}), 400

        status_bayar = _normalize_status_pembayaran_canonical(
            data.get('statusPembayaran') or 'Belum Lunas'
        ) or 'Belum Lunas'
        if status_bayar not in ('Lunas', 'Belum Lunas', 'Pembayaran Bertahap'):
            return jsonify({'error': 'statusPembayaran harus Lunas, Belum Lunas, atau Pembayaran Bertahap'}), 400
        
        if tipe_pm == 'International' and not data.get('negara'):
            return jsonify({'error': 'Negara wajib diisi untuk pemesanan International'}), 400

        status_pem = (data.get('statusPemesanan') or '').strip()
        if status_pem == 'Complete':
            lines_for_complete = kloter_norm if use_kloter else [{
                'tipeProduk': (data.get('tipeProduk') or '').strip(),
            }]
            if _line_items_all_invoice_only(lines_for_complete):
                if status_bayar != 'Lunas':
                    return jsonify({
                        'error': 'Pemesanan invoice-only (mis. Roasted Beans, Argopuro Walida Collective) hanya bisa Complete jika status pembayaran Lunas.'
                    }), 400
            else:
                return jsonify({
                    'error': 'Status Complete hanya bisa dicapai melalui proses ordering. Gunakan endpoint /api/ordering/proses untuk mengurangi stok dan menyelesaikan pemesanan.'
                }), 400

        biaya_pajak = float(data.get('biayaPajak') or 0)
        if biaya_pajak < 0:
            return jsonify({'error': 'Biaya pajak tidak boleh negatif'}), 400
        biaya_pengiriman = float(data.get('biayaPengiriman') or 0)
        if biaya_pengiriman < 0:
            return jsonify({'error': 'Biaya pengiriman tidak boleh negatif'}), 400
        tipe_pajak = _normalize_tipe_pajak(data.get('tipePajak'))

        if use_kloter:
            jumlah_total_kg = sum(float(i['jumlahPesananKg']) for i in kloter_norm)
            subtotal_barang = sum(float(i['subtotal']) for i in kloter_norm)
        else:
            if float(data['jumlahPesananKg']) <= 0:
                return jsonify({'error': 'Jumlah pesanan harus lebih dari 0'}), 400
            if float(data['hargaPerKg']) <= 0:
                return jsonify({'error': 'Harga per kg harus lebih dari 0'}), 400
            jumlah_total_kg = float(data['jumlahPesananKg'])
            subtotal_barang = jumlah_total_kg * float(data['hargaPerKg'])

        total_harga_received = float(data['totalHarga'])
        calculated_total = _hitung_total_pemesanan_dari_komponen(
            subtotal_barang, biaya_pajak, biaya_pengiriman, tipe_pajak,
        )

        tol = _total_harga_pemesanan_tolerance(calculated_total)
        if abs(total_harga_received - calculated_total) > tol:
            print(f"❌ [PEMESANAN CREATE] Total harga mismatch:")
            print(f"   Received: {total_harga_received}")
            print(f"   Calculated: {calculated_total}")
            return jsonify({
                'error': 'Total harga tidak sesuai dengan perhitungan (subtotal barang ± pajak + pengiriman)',
                'received': total_harga_received,
                'calculated': calculated_total,
            }), 400
        
        existing = db.pemesanan.find_one({'idPembelian': data['idPembelian']})
        if existing:
            return jsonify({'error': 'ID Pembelian already exists'}), 400
        
        new_id = get_next_id('pemesanan')

        if use_kloter:
            first = kloter_norm[0]
            tipe_root = first['tipeProduk'] if len(kloter_norm) == 1 else 'Campuran'
            jk_root = first['jenisKopi'] if len(kloter_norm) == 1 else 'Campuran'
            pr_root = first['prosesPengolahan'] if len(kloter_norm) == 1 else 'Campuran'
            harga_avg = round(subtotal_barang / jumlah_total_kg, 4) if jumlah_total_kg > 0 else 0.0
            pemesanan_data = {
                'id': new_id,
                'idPembelian': data['idPembelian'],
                'namaPembeli': data['namaPembeli'],
                'tipePemesanan': tipe_pm,
                'negara': data.get('negara', '') if tipe_pm == 'International' else '',
                'kloter': kloter_norm,
                'tipeProduk': tipe_root,
                'jenisKopi': jk_root,
                'prosesPengolahan': pr_root,
                'jumlahPesananKg': jumlah_total_kg,
                'hargaPerKg': harga_avg,
                'tipePajak': tipe_pajak,
                'biayaPajak': biaya_pajak,
                'biayaPengiriman': biaya_pengiriman,
                'totalHarga': float(data['totalHarga']),
                'statusPemesanan': data['statusPemesanan'],
                'statusPembayaran': status_bayar,
                'tanggalPemesanan': data.get('tanggalPemesanan', datetime.now().strftime('%Y-%m-%d')),
                'createdAt': datetime.now(),
                'updatedAt': datetime.now()
            }
        else:
            pemesanan_data = {
                'id': new_id,
                'idPembelian': data['idPembelian'],
                'namaPembeli': data['namaPembeli'],
                'tipePemesanan': tipe_pm,
                'negara': data.get('negara', '') if tipe_pm == 'International' else '',
                'tipeProduk': data['tipeProduk'],
                'prosesPengolahan': data['prosesPengolahan'],
                'jenisKopi': data['jenisKopi'],
                'jumlahPesananKg': float(data['jumlahPesananKg']),
                'hargaPerKg': float(data['hargaPerKg']),
                'tipePajak': tipe_pajak,
                'biayaPajak': biaya_pajak,
                'biayaPengiriman': biaya_pengiriman,
                'totalHarga': float(data['totalHarga']),
                'statusPemesanan': data['statusPemesanan'],
                'statusPembayaran': status_bayar,
                'tanggalPemesanan': data.get('tanggalPemesanan', datetime.now().strftime('%Y-%m-%d')),
                'createdAt': datetime.now(),
                'updatedAt': datetime.now()
            }
        catatan_pm = (data.get('catatanPemesanan') or '').strip()
        if catatan_pm:
            pemesanan_data['catatanPemesanan'] = catatan_pm
        im = (data.get('idMasterPembeli') or '').strip()
        if im:
            pemesanan_data['idMasterPembeli'] = im
        kpb = (data.get('kontakPembeli') or '').strip()
        if kpb:
            pemesanan_data['kontakPembeli'] = kpb
        apb = (data.get('alamatPembeli') or '').strip()
        if apb:
            pemesanan_data['alamatPembeli'] = apb

        baris_tb, baris_err = _normalize_pembayaran_bertahap_baris_tambahan(data)
        if baris_err:
            return jsonify({'error': baris_err}), 400
        pemesanan_data['pembayaranBertahapBaris'] = baris_tb

        klist_agg = pemesanan_data.get('kloter') or pemesanan_data.get('items') or []
        sum_pay, sisa_bayar, agg_err = _compute_pemesanan_pembayaran_kloter_agg(
            status_bayar, pemesanan_data['totalHarga'], klist_agg, baris_tb
        )
        if agg_err:
            return jsonify({'error': agg_err}), 400
        pemesanan_data['totalPembayaranKloter'] = sum_pay
        pemesanan_data['totalPembayaranSaatIni'] = sisa_bayar
        
        print(f"🔵 [PEMESANAN CREATE] Inserting to MongoDB collection 'pemesanan': {pemesanan_data}")
        result = db.pemesanan.insert_one(pemesanan_data)
        pemesanan_data['_id'] = result.inserted_id
        print(f"✅ [PEMESANAN CREATE] Successfully inserted! ID: {result.inserted_id}, Collection: pemesanan")
        return jsonify(json_serialize(pemesanan_data)), 201
    except Exception as e:
        print(f"❌ [PEMESANAN CREATE] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/pemesanan/<pemesanan_id>', methods=['PUT'])
def update_pemesanan(pemesanan_id):
    """
    Update pemesanan - HANYA PENCATATAN PERMINTAAN
    Endpoint ini TIDAK BOLEH mengurangi stok.
    Untuk mengurangi stok, gunakan endpoint /api/ordering/proses.
    """
    try:
        data = request.json
        
        try:
            pemesanan = db.pemesanan.find_one({'_id': ObjectId(pemesanan_id)})
        except:
            pemesanan = db.pemesanan.find_one({'id': int(pemesanan_id)}) or \
                       db.pemesanan.find_one({'idPembelian': pemesanan_id})
        
        if not pemesanan:
            return jsonify({'error': 'Pemesanan not found'}), 404
        
        # Validate if updating idPembelian
        if 'idPembelian' in data:
            existing = db.pemesanan.find_one({
                'idPembelian': data['idPembelian'],
                '_id': {'$ne': pemesanan['_id']}
            })
            if existing:
                return jsonify({'error': 'ID Pembelian already exists'}), 400
        
        # Validate International requires negara
        tipe_pemesanan = data.get('tipePemesanan', pemesanan.get('tipePemesanan'))
        if tipe_pemesanan == 'International' and not data.get('negara') and not pemesanan.get('negara'):
            return jsonify({'error': 'Negara wajib diisi untuk pemesanan International'}), 400
        
        update_data = {}
        for field in ['idPembelian', 'namaPembeli', 'tipePemesanan', 'negara', 'tipeProduk',
                     'prosesPengolahan', 'jenisKopi', 'jumlahPesananKg', 'hargaPerKg',
                     'tipePajak', 'biayaPajak', 'biayaPengiriman', 'totalHarga', 'statusPemesanan', 'tanggalPemesanan', 'idMasterPembeli',
                     'kontakPembeli', 'alamatPembeli', 'statusPembayaran', 'catatanPemesanan']:
            if field in data:
                if field in ['jumlahPesananKg', 'hargaPerKg', 'totalHarga', 'biayaPajak', 'biayaPengiriman']:
                    if field in ('biayaPajak', 'biayaPengiriman'):
                        update_data[field] = float(data[field] or 0)
                    else:
                        update_data[field] = float(data[field])
                elif field == 'catatanPemesanan':
                    update_data[field] = (data[field] or '').strip()
                elif field == 'tipePajak':
                    update_data[field] = _normalize_tipe_pajak(data[field])
                else:
                    update_data[field] = data[field]

        unset_legacy_items = False
        if 'kloter' in data or 'items' in data:
            kloter_norm, kloter_err = _normalize_pemesanan_kloter_from_body(data)
            if kloter_err:
                return jsonify({'error': kloter_err}), 400
            if not kloter_norm:
                return jsonify({'error': 'kloter kosong atau tidak valid'}), 400
            update_data['kloter'] = kloter_norm
            unset_legacy_items = True
            jum = sum(float(i['jumlahPesananKg']) for i in kloter_norm)
            subb = sum(float(i['subtotal']) for i in kloter_norm)
            first = kloter_norm[0]
            update_data['jumlahPesananKg'] = jum
            update_data['hargaPerKg'] = round(subb / jum, 4) if jum > 0 else 0.0
            update_data['tipeProduk'] = first['tipeProduk'] if len(kloter_norm) == 1 else 'Campuran'
            update_data['jenisKopi'] = first['jenisKopi'] if len(kloter_norm) == 1 else 'Campuran'
            update_data['prosesPengolahan'] = first['prosesPengolahan'] if len(kloter_norm) == 1 else 'Campuran'

        _total_keys = ('totalHarga', 'jumlahPesananKg', 'hargaPerKg', 'tipePajak', 'biayaPajak', 'biayaPengiriman', 'kloter', 'items')
        if any(k in update_data for k in _total_keys):
            if 'kloter' in update_data:
                sub_lines = sum(float(i.get('subtotal', 0) or 0) for i in update_data['kloter'])
            elif 'items' in update_data:
                sub_lines = sum(float(i.get('subtotal', 0) or 0) for i in update_data['items'])
            else:
                j = float(update_data.get('jumlahPesananKg', pemesanan.get('jumlahPesananKg', 0)))
                hk = float(update_data.get('hargaPerKg', pemesanan.get('hargaPerKg', 0)))
                sub_lines = j * hk
            pj = float(update_data.get('biayaPajak', pemesanan.get('biayaPajak', 0)) or 0)
            pg = float(update_data.get('biayaPengiriman', pemesanan.get('biayaPengiriman', 0)) or 0)
            tpj = _normalize_tipe_pajak(
                update_data.get('tipePajak', pemesanan.get('tipePajak', 'penjumlahan')),
            )
            update_data['tipePajak'] = tpj
            th = float(update_data.get('totalHarga', pemesanan.get('totalHarga', 0)))
            if pj < 0:
                return jsonify({'error': 'Biaya pajak tidak boleh negatif'}), 400
            if pg < 0:
                return jsonify({'error': 'Biaya pengiriman tidak boleh negatif'}), 400
            expected = _hitung_total_pemesanan_dari_komponen(sub_lines, pj, pg, tpj)
            tol = _total_harga_pemesanan_tolerance(expected)
            if abs(th - expected) > tol:
                return jsonify({
                    'error': 'Total harga tidak sesuai (subtotal barang ± pajak + pengiriman)',
                    'expected': expected,
                    'received': th,
                }), 400

        if 'statusPembayaran' in update_data:
            sb = _normalize_status_pembayaran_canonical(update_data.get('statusPembayaran'))
            if not sb:
                return jsonify({'error': 'statusPembayaran tidak valid'}), 400
            update_data['statusPembayaran'] = sb
        
        if 'tipePemesanan' in update_data:
            tt = (update_data.get('tipePemesanan') or '').strip()
            if tt not in ('Lokal', 'International', 'E-commerce'):
                return jsonify({'error': 'tipePemesanan tidak valid'}), 400
            if tt != 'International':
                update_data['negara'] = ''

        if 'pembayaranBertahapBaris' in data:
            baris_tb_up, baris_err_up = _normalize_pembayaran_bertahap_baris_tambahan(data)
            if baris_err_up:
                return jsonify({'error': baris_err_up}), 400
            update_data['pembayaranBertahapBaris'] = baris_tb_up
        
        # ==================== ATURAN STATUS (BISNIS) ====================
        # - statusPemesanan hanya boleh Complete jika statusPembayaran = Lunas
        # - Jika statusPembayaran bukan Lunas, statusPemesanan harus Ordering (tidak boleh Complete)
        old_status_pem = (pemesanan.get('statusPemesanan') or '').strip()
        old_status_bayar = _normalize_status_pembayaran_canonical(pemesanan.get('statusPembayaran')) or (pemesanan.get('statusPembayaran') or 'Belum Lunas')
        new_status_pem = (update_data.get('statusPemesanan', old_status_pem) or '').strip()
        new_status_bayar = update_data.get('statusPembayaran', old_status_bayar)

        # --- Pembayaran bertahap: sisa tagihan > 0 → tidak boleh Complete atau Lunas ---
        merged_k_val = update_data.get('kloter')
        if merged_k_val is None:
            merged_k_val = pemesanan.get('kloter') or pemesanan.get('items') or []
        merged_th_val = float(update_data.get('totalHarga', pemesanan.get('totalHarga', 0)))
        pending_bayar_val = update_data.get('statusPembayaran', old_status_bayar)
        pending_bayar_val = _normalize_status_pembayaran_canonical(pending_bayar_val) or pending_bayar_val
        merged_baris_val = update_data.get('pembayaranBertahapBaris')
        if merged_baris_val is None:
            merged_baris_val = pemesanan.get('pembayaranBertahapBaris') or []
        _sum_early, sisa_val, e_agg_early = _compute_pemesanan_pembayaran_kloter_agg(
            pending_bayar_val, merged_th_val, merged_k_val, merged_baris_val
        )
        if e_agg_early:
            return jsonify({'error': e_agg_early}), 400
        tol_sisa = 1.0
        bertahap_konteks = (
            old_status_bayar == 'Pembayaran Bertahap' or pending_bayar_val == 'Pembayaran Bertahap'
        )
        if bertahap_konteks and sisa_val > tol_sisa:
            if new_status_pem == 'Complete':
                return jsonify({
                    'error': (
                        'Pemesanan dengan pembayaran bertahap masih memiliki sisa tagihan. '
                        'Lunasi hingga sisa Rp 0 untuk dapat menyelesaikan pemesanan (Complete).'
                    )
                }), 400
            if pending_bayar_val == 'Lunas':
                return jsonify({
                    'error': (
                        'Pemesanan dengan pembayaran bertahap masih memiliki sisa tagihan. '
                        'Status pembayaran tidak dapat diubah ke Lunas sebelum sisa Rp 0.'
                    )
                }), 400

        # Jika dokumen sudah Complete, pembayaran harus tetap Lunas (jangan bisa diturunkan).
        if old_status_pem == 'Complete' and new_status_bayar != 'Lunas':
            return jsonify({
                'error': 'Status pembayaran untuk pemesanan yang sudah Complete harus Lunas.'
            }), 400

        # Jika mencoba set Complete tapi pembayaran bukan Lunas => tolak.
        if new_status_pem == 'Complete' and new_status_bayar != 'Lunas':
            return jsonify({
                'error': 'Status pemesanan hanya bisa Complete jika status pembayaran Lunas.'
            }), 400

        # Validasi Complete: tidak boleh pertama kali jadi Complete tanpa jalur ordering/hasil stok.
        # Mengizinkan simpan lain (mis. statusPembayaran) jika dokumen ini sudah Complete sebelumnya
        # atau ada bukti pemotongan stok — menghindari error saat koleksi ordering tidak sinkron dengan pemesanan.
        if 'statusPemesanan' in update_data and update_data['statusPemesanan'] == 'Complete':
            id_pb = pemesanan.get('idPembelian')
            ordering = db.ordering.find_one({'idPembelian': id_pb}) if id_pb else None
            has_hasil_pb = False
            if id_pb:
                has_hasil_pb = db.hasilProduksi.count_documents({
                    'idPembelian': id_pb,
                    'isFromOrdering': {'$in': [True, 1]},
                }) > 0

            transitioning_to_complete = old_status_pem != 'Complete'

            if not ordering:
                lines_complete_check = []
                if isinstance(merged_k_val, list) and merged_k_val:
                    for row in merged_k_val:
                        if isinstance(row, dict):
                            lines_complete_check.append({
                                'tipeProduk': (row.get('tipeProduk') or '').strip(),
                            })
                if not lines_complete_check:
                    lines_complete_check = pemesanan_items_from_doc(pemesanan)
                invoice_only_complete = _line_items_all_invoice_only(lines_complete_check)
                safe_complete = (
                    old_status_pem == 'Complete'
                    or has_hasil_pb
                    or invoice_only_complete
                )
                if transitioning_to_complete and not safe_complete:
                    return jsonify({
                        'error': 'Status Complete hanya bisa dicapai melalui proses ordering. Gunakan endpoint /api/ordering/proses untuk mengurangi stok dan menyelesaikan pemesanan.'
                    }), 400
                if transitioning_to_complete and invoice_only_complete and new_status_bayar != 'Lunas':
                    return jsonify({
                        'error': 'Pemesanan invoice-only (mis. Roasted Beans, Argopuro Walida Collective) hanya bisa Complete jika status pembayaran Lunas.'
                    }), 400
            else:
                # Dokumen ordering ada → pemesanan selesai dari sisi stok → lunas (perilaku bisnis tetap).
                update_data['statusPembayaran'] = 'Lunas'

        # Agregat pembayaran per kloter (Σ per baris; sisa = total − Σ)
        eff_bayar = update_data.get('statusPembayaran', pemesanan.get('statusPembayaran'))
        eff_bayar = _normalize_status_pembayaran_canonical(eff_bayar) or (eff_bayar or 'Belum Lunas')
        merged_total = float(update_data.get('totalHarga', pemesanan.get('totalHarga', 0)))
        merged_kloter = update_data.get('kloter')
        if merged_kloter is None:
            merged_kloter = pemesanan.get('kloter') or pemesanan.get('items') or []
        merged_baris_fin = update_data.get('pembayaranBertahapBaris')
        if merged_baris_fin is None:
            merged_baris_fin = pemesanan.get('pembayaranBertahapBaris') or []
        sum_pay, sisa_bayar, agg_err = _compute_pemesanan_pembayaran_kloter_agg(
            eff_bayar, merged_total, merged_kloter, merged_baris_fin
        )
        if agg_err:
            return jsonify({'error': agg_err}), 400
        update_data['totalPembayaranKloter'] = sum_pay
        update_data['totalPembayaranSaatIni'] = sisa_bayar
        
        update_data['updatedAt'] = datetime.now()

        update_payload = {'$set': update_data}
        if unset_legacy_items:
            update_payload['$unset'] = {'items': ''}

        db.pemesanan.update_one(
            {'_id': pemesanan['_id']},
            update_payload
        )
        
        updated = db.pemesanan.find_one({'_id': pemesanan['_id']})
        return jsonify(json_serialize(updated)), 200
    except Exception as e:
        print(f"❌ [PEMESANAN UPDATE] ERROR: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pemesanan/<pemesanan_id>', methods=['DELETE'])
def delete_pemesanan(pemesanan_id):
    """Delete pemesanan"""
    try:
        print(f"🗑️ [DELETE PEMESANAN] Attempting to delete: {pemesanan_id}")
        
        # Try multiple ways to find pemesanan
        pemesanan = None
        
        # 1. Try ObjectId first (if it's a valid ObjectId string)
        try:
            pemesanan = db.pemesanan.find_one({'_id': ObjectId(pemesanan_id)})
            if pemesanan:
                print(f"✅ [DELETE PEMESANAN] Found by ObjectId: {pemesanan_id}")
        except:
            pass
        
        # 2. Try idPembelian (string match - most common case)
        if not pemesanan:
            pemesanan = db.pemesanan.find_one({'idPembelian': pemesanan_id})
            if pemesanan:
                print(f"✅ [DELETE PEMESANAN] Found by idPembelian: {pemesanan_id}")
        
        # 3. Try id (integer) only if pemesanan_id is numeric
        if not pemesanan:
            try:
                id_int = int(pemesanan_id)
                pemesanan = db.pemesanan.find_one({'id': id_int})
                if pemesanan:
                    print(f"✅ [DELETE PEMESANAN] Found by id (int): {pemesanan_id}")
            except ValueError:
                # pemesanan_id is not numeric, skip this attempt
                pass
        
        if not pemesanan:
            print(f"❌ [DELETE PEMESANAN] Pemesanan not found: {pemesanan_id}")
            return jsonify({'error': 'Pemesanan not found'}), 404
        
        # Validasi: Tidak bisa delete jika status = "Complete"
        if pemesanan.get('statusPemesanan') == 'Complete':
            print(f"⚠️ [DELETE PEMESANAN] Cannot delete - status is Complete")
            return jsonify({'error': 'Tidak dapat menghapus pemesanan yang sudah Complete. Pemesanan sudah diproses dan stok sudah dikurangi.'}), 400
        
        # Check if there's ordering associated
        id_pembelian = pemesanan.get('idPembelian')
        ordering_count = db.ordering.count_documents({'idPembelian': id_pembelian})
        if ordering_count > 0:
            print(f"⚠️ [DELETE PEMESANAN] Cannot delete - has {ordering_count} ordering(s)")
            return jsonify({'error': 'Tidak dapat menghapus pemesanan yang sudah memiliki proses ordering'}), 400
        
        # Delete pemesanan
        result = db.pemesanan.delete_one({'_id': pemesanan['_id']})
        if result.deleted_count > 0:
            print(f"✅ [DELETE PEMESANAN] Successfully deleted: {pemesanan_id}")
            return jsonify({'success': True, 'message': 'Pemesanan deleted successfully'}), 200
        else:
            print(f"⚠️ [DELETE PEMESANAN] Delete operation returned 0 deleted count")
            return jsonify({'error': 'Failed to delete pemesanan'}), 500
            
    except Exception as e:
        print(f"❌ [DELETE PEMESANAN] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ==================== ORDERING ENDPOINTS ====================

@app.route('/api/ordering', methods=['GET'])
def get_ordering():
    """Get all ordering data"""
    try:
        ordering = list(db.ordering.find().sort('id', 1))
        print(f"📊 [ORDERING GET] Retrieved {len(ordering)} documents from MongoDB collection 'ordering'")
        return jsonify(json_serialize(ordering)), 200
    except Exception as e:
        print(f"❌ [ORDERING GET] ERROR: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ordering/<ordering_id>', methods=['GET'])
def get_ordering_by_id(ordering_id):
    """Get ordering by ID"""
    try:
        try:
            ordering = db.ordering.find_one({'_id': ObjectId(ordering_id)})
        except:
            ordering = db.ordering.find_one({'id': int(ordering_id)})
        
        if not ordering:
            return jsonify({'error': 'Ordering not found'}), 404
        
        return jsonify(json_serialize(ordering)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ordering/proses', methods=['POST'])
def proses_ordering():
    """
    PROSES ORDERING - SATU-SATUNYA ENDPOINT YANG MENGURANGI STOK
    Endpoint ini adalah titik eksekusi gudang yang mengurangi stok secara nyata.
    Tanpa idProduksi: stok diambil dari agregat Kelola Stok (tipe + jenis kopi + proses),
    dialokasikan FIFO ke batch pengemasan. Dengan idProduksi: perilaku lama per batch.
    """
    try:
        data = request.json or {}
        
        if 'idPembelian' not in data:
            return jsonify({'error': 'Missing required field: idPembelian'}), 400
        
        pemesanan = db.pemesanan.find_one({'idPembelian': data['idPembelian']})
        if not pemesanan:
            return jsonify({'error': 'Pemesanan not found'}), 404

        sb_order = _normalize_status_pembayaran_canonical(pemesanan.get('statusPembayaran')) or (
            pemesanan.get('statusPembayaran') or ''
        )
        if sb_order == 'Pembayaran Bertahap':
            klist_o = pemesanan.get('kloter') or pemesanan.get('items') or []
            th_o = float(pemesanan.get('totalHarga') or 0)
            baris_o = pemesanan.get('pembayaranBertahapBaris') or []
            _s_o, sisa_o, _e_o = _compute_pemesanan_pembayaran_kloter_agg(
                'Pembayaran Bertahap', th_o, klist_o, baris_o
            )
            if sisa_o > 1.0:
                return jsonify({
                    'error': (
                        'Pemesanan pembayaran bertahap masih memiliki sisa tagihan. '
                        'Lunasi hingga sisa Rp 0 sebelum proses ordering (stok / Complete).'
                    ),
                    'sisaTagihan': sisa_o,
                }), 400
        
        id_pb = data['idPembelian']
        existing_ordering = db.ordering.find_one({'idPembelian': id_pb})
        if existing_ordering:
            # Jejak pengurangan stok: hasilProduksi untuk pembelian ini (biasanya isFromOrdering=True)
            hp_loose = db.hasilProduksi.count_documents({'idPembelian': id_pb})
            hp_strict = db.hasilProduksi.count_documents({
                'idPembelian': id_pb,
                'isFromOrdering': {'$in': [True, 1]},
            })
            cur_status = (pemesanan.get('statusPemesanan') or '').strip()

            if hp_loose > 0:
                # Stok sudah pernah dialokasikan untuk ID pembelian ini — jangan proses ulang (hindari double deduction)
                if cur_status != 'Complete':
                    sb_fix = _normalize_status_pembayaran_canonical(pemesanan.get('statusPembayaran')) or (
                        pemesanan.get('statusPembayaran') or ''
                    )
                    klist_fix = pemesanan.get('kloter') or pemesanan.get('items') or []
                    th_fix = float(pemesanan.get('totalHarga') or 0)
                    sisa_fix = 0.0
                    if sb_fix == 'Pembayaran Bertahap':
                        baris_fix = pemesanan.get('pembayaranBertahapBaris') or []
                        _sf, sisa_fix, _ef = _compute_pemesanan_pembayaran_kloter_agg(
                            'Pembayaran Bertahap', th_fix, klist_fix, baris_fix
                        )
                    skip_lunas_complete = sb_fix == 'Pembayaran Bertahap' and sisa_fix > 1.0
                    if skip_lunas_complete:
                        print(
                            f"⚠️ [ORDERING PROSES] Lewati sinkron Complete/Lunas untuk {id_pb}: "
                            f"pembayaran bertahap masih ada sisa tagihan ({sisa_fix})."
                        )
                    else:
                        db.pemesanan.update_one(
                            {'_id': pemesanan['_id']},
                            {'$set': {
                                'statusPemesanan': 'Complete',
                                'statusPembayaran': 'Lunas',
                                'updatedAt': datetime.now(),
                            }},
                        )
                        print(
                            f"✅ [ORDERING PROSES] Sinkron status pemesanan → Complete untuk {id_pb} "
                            f"(ordering ada, hasilProduksi={hp_loose}, isFromOrdering match={hp_strict})"
                        )
                ord_doc = db.ordering.find_one({'idPembelian': id_pb})
                return jsonify({
                    'success': True,
                    'message': (
                        'Pemesanan sudah pernah diproses; status diselaraskan dengan data ordering.'
                        if cur_status != 'Complete'
                        else 'Pemesanan sudah selesai diproses sebelumnya.'
                    ),
                    'ordering': json_serialize(ord_doc),
                    'alreadyProcessed': True,
                    'statusRepaired': cur_status != 'Complete',
                }), 200

            # Hanya baris ordering tanpa hasilProduksi — data tidak lengkap; hapus agar bisa diproses ulang
            del_ord = db.ordering.delete_many({'idPembelian': id_pb})
            print(
                f"⚠️ [ORDERING PROSES] Menghapus {del_ord.deleted_count} ordering orphan untuk {id_pb} "
                "(tidak ada hasilProduksi terkait)"
            )

        line_items = pemesanan_items_from_doc(pemesanan)
        if not line_items:
            return jsonify({'error': 'Pemesanan tidak memiliki barang'}), 400

        tanggal_ordering = data.get('tanggalOrdering', datetime.now().strftime('%Y-%m-%d'))

        if _line_items_all_invoice_only(line_items):
            ordering_data = _finalize_pemesanan_invoice_only(
                id_pb, pemesanan, line_items, tanggal_ordering
            )
            return jsonify({
                'success': True,
                'message': 'Pemesanan invoice-only (tidak terikat stok) diselesaikan, stok tidak dikurangi.',
                'ordering': json_serialize(ordering_data),
                'invoiceOnly': True,
                'jumlahDikurangi': 0,
            }), 201
        id_produksi_payload = data.get('idProduksi')
        use_single_batch = id_produksi_payload is not None and str(id_produksi_payload).strip() != ''

        tipe_from_req = (data.get('tipeProduk') or pemesanan.get('tipeProduk') or '').strip()
        if tipe_from_req in ('Green Beans', 'Pixel'):
            tipe_produk_selected = tipe_from_req
        elif line_items:
            tipe_produk_selected = (line_items[0].get('tipeProduk') or '').strip()
        else:
            tipe_produk_selected = ''
        if not _tipe_produk_valid(tipe_produk_selected):
            allowed = ', '.join(sorted(_get_tipe_produk_master_set()))
            return jsonify({
                'error': f'Tipe produk tidak valid. Pilih dari master data: {allowed}'
            }), 400

        tipe_produk_pemesanan = (pemesanan.get('tipeProduk') or '').strip()
        multi_barang = len(line_items) > 1
        if not multi_barang and tipe_produk_pemesanan and tipe_produk_pemesanan not in ('Campuran',):
            if tipe_produk_selected != tipe_produk_pemesanan:
                return jsonify({
                    'error': 'Tipe produk tidak sesuai',
                    'tipeProdukStok': tipe_produk_selected,
                    'tipeProdukPemesanan': tipe_produk_pemesanan
                }), 400

        jumlah_pesanan_total = float(sum(float(x.get('jumlahPesananKg') or 0) for x in line_items))

        if use_single_batch:
            if len(line_items) != 1:
                return jsonify({
                    'error': 'Pemesanan beberapa barang tidak mendukung pemilihan satu id produksi. Kosongkan id produksi untuk alokasi otomatis (FIFO).'
                }), 400
            it0 = line_items[0]
            if _is_tipe_produk_invoice_only(it0.get('tipeProduk')):
                return jsonify({
                    'error': 'Tipe produk invoice-only (mis. Roasted Beans, Argopuro Walida Collective) tidak memerlukan pemilihan batch produksi (tanpa pengurangan stok).'
                }), 400
            jumlah_pesanan = float(it0['jumlahPesananKg'])
            tipe_produk_selected = (it0.get('tipeProduk') or tipe_produk_selected).strip()
            if not _tipe_produk_valid(tipe_produk_selected):
                allowed = ', '.join(sorted(_get_tipe_produk_master_set()))
                return jsonify({
                    'error': f'Tipe produk baris tidak valid. Pilih dari master data: {allowed}'
                }), 400
            # --- Cabang lama: satu id produksi eksplisit ---
            produksi = db.produksi.find_one({'idProduksi': id_produksi_payload})
            if not produksi:
                return jsonify({'error': 'Produksi not found'}), 400
            
            if tipe_produk_selected == 'Green Beans':
                berat_produk = _stok_berat_green_effective_dari_produksi(produksi)
            else:
                berat_produk = float(produksi.get('beratPixel', 0) or 0)
            
            if berat_produk <= 0:
                return jsonify({'error': f'Produksi belum memiliki berat {tipe_produk_selected}'}), 400
            
            ids_prod = _id_bahan_list_from_produksi(produksi)
            jenis_set = set()
            bahan = None
            for bid in ids_prod:
                bh = db.bahan.find_one({'idBahan': bid})
                if bh:
                    jenis_set.add((bh.get('jenisKopi') or '').strip())
                    if bahan is None:
                        bahan = bh
            if not bahan:
                return jsonify({'error': 'Bahan tidak ditemukan untuk produksi ini'}), 404
            if len(jenis_set) > 1:
                return jsonify({'error': 'Produksi menggabungkan bahan dengan jenis kopi berbeda'}), 400
            
            proses_tampilan = _proses_pengolahan_tampilan_untuk_agregasi(produksi, bahan)
            ps_pem = (it0.get('prosesPengolahan') or '').strip()
            ps_raw = (produksi.get('prosesPengolahan') or '').strip()
            if ps_pem not in (ps_raw, proses_tampilan):
                return jsonify({
                    'error': 'Proses pengolahan tidak sesuai',
                    'prosesProduksi': ps_raw,
                    'prosesTampilan': proses_tampilan,
                    'prosesPemesanan': ps_pem
                }), 400
            
            if (bahan.get('jenisKopi') or '').strip() != (it0.get('jenisKopi') or '').strip():
                return jsonify({
                    'error': 'Jenis kopi tidak sesuai',
                    'jenisKopiProduksi': bahan.get('jenisKopi'),
                    'jenisKopiPemesanan': it0.get('jenisKopi')
                }), 400
            
            hasil_produksi_list = list(db.hasilProduksi.find({
                'idProduksi': id_produksi_payload,
                'tipeProduk': tipe_produk_selected,
                'isFromOrdering': True
            }))
            total_dari_ordering = sum(float(h.get('beratSaatIni', 0)) for h in hasil_produksi_list)
            stok_tersedia = max(0, berat_produk - total_dari_ordering)
            
            print(f"📦 [ORDERING PROSES] (per-batch) idProduksi={id_produksi_payload}, tipe={tipe_produk_selected}, stok_tersedia={stok_tersedia}, jumlah={jumlah_pesanan}")
            
            if stok_tersedia < jumlah_pesanan:
                return jsonify({
                    'error': 'Stok tidak mencukupi',
                    'stokTersedia': stok_tersedia,
                    'jumlahPesanan': jumlah_pesanan,
                    'kekurangan': jumlah_pesanan - stok_tersedia
                }), 400
            
            hasil_produksi_id = get_next_id('hasilProduksi')
            hasil_produksi_data = {
                'id': hasil_produksi_id,
                'idProduksi': str(id_produksi_payload).strip(),
                'idBahan': produksi.get('idBahan'),
                'tipeProduk': tipe_produk_selected,
                'kemasan': pemesanan.get('kemasan', ''),
                'jenisKopi': it0.get('jenisKopi'),
                'prosesPengolahan': it0.get('prosesPengolahan'),
                'levelRoasting': pemesanan.get('levelRoasting', ''),
                'tanggal': tanggal_ordering,
                'beratSaatIni': jumlah_pesanan,
                'jumlah': 0,
                'isFromOrdering': True,
                'idPembelian': data['idPembelian']
            }
            
            new_id = get_next_id('ordering')
            ordering_data = {
                'id': new_id,
                'idPembelian': data['idPembelian'],
                'idProduksi': id_produksi_payload,
                'tipeProduk': tipe_produk_selected,
                'jumlahPesananKg': jumlah_pesanan,
                'stokSebelum': stok_tersedia,
                'stokSesudah': stok_tersedia - jumlah_pesanan,
                'statusPemesanan': 'Complete',
                'tanggalOrdering': tanggal_ordering,
                'createdAt': datetime.now(),
                'updatedAt': datetime.now()
            }
            
            print(f"🔵 [ORDERING PROSES] Inserting ordering log: {ordering_data}")
            result_ordering = db.ordering.insert_one(ordering_data)
            ordering_data['_id'] = result_ordering.inserted_id
            
            print(f"🔵 [ORDERING PROSES] Inserting hasilProduksi: {hasil_produksi_data}")
            result_hasil = db.hasilProduksi.insert_one(hasil_produksi_data)
            hasil_produksi_data['_id'] = result_hasil.inserted_id
            
            db.pemesanan.update_one(
                {'idPembelian': data['idPembelian']},
                {'$set': {
                    'statusPemesanan': 'Complete',
                    'statusPembayaran': 'Lunas',
                    'updatedAt': datetime.now()
                }}
            )
            
            return jsonify({
                'success': True,
                'message': 'Ordering berhasil diproses, stok telah dikurangi',
                'ordering': json_serialize(ordering_data),
                'stokSebelum': stok_tersedia,
                'stokSesudah': stok_tersedia - jumlah_pesanan,
                'jumlahDikurangi': jumlah_pesanan
            }), 201
        
        # --- Cabang agregat: FIFO per baris (satu atau beberapa kombinasi tipe/jenis/proses) ---
        tipe_ordering_label = 'Campuran' if multi_barang else tipe_produk_selected
        stok_rows_all, _ = _compute_stok_hasil_aggregate('', '')
        stok_remaining_by_key = {}
        inserted_hasil_ids = []
        all_prod_ids_order = []
        first_stok_before = None
        last_stok_after = None

        try:
            for idx, it in enumerate(line_items):
                tipe_sel = (it.get('tipeProduk') or '').strip()
                if not _tipe_produk_valid(tipe_sel):
                    allowed = ', '.join(sorted(_get_tipe_produk_master_set()))
                    raise ValueError(
                        f'Baris {idx + 1}: tipeProduk tidak valid. '
                        f'Pilih dari master data: {allowed}'
                    )
                if _is_tipe_produk_invoice_only(tipe_sel):
                    continue
                jum_baris = float(it.get('jumlahPesananKg') or 0)
                if jum_baris <= 0:
                    raise ValueError(f'Baris {idx + 1}: jumlah (kg) tidak valid')
                jk_it = (it.get('jenisKopi') or '').strip()
                pr_it = (it.get('prosesPengolahan') or '').strip()
                if not jk_it or not pr_it:
                    raise ValueError(f'Baris {idx + 1}: jenis kopi dan proses wajib diisi')

                key_pem = _stok_key(tipe_sel, jk_it, pr_it)
                if key_pem not in stok_remaining_by_key:
                    stok_tersedia = 0.0
                    for r in stok_rows_all:
                        rk = _stok_key(r.get('tipeProduk'), r.get('jenisKopi'), r.get('prosesPengolahan'))
                        if rk == key_pem:
                            stok_tersedia = float(r.get('totalBerat', 0) or 0)
                            break
                    stok_remaining_by_key[key_pem] = stok_tersedia
                stok_tersedia = stok_remaining_by_key[key_pem]

                if idx == 0:
                    first_stok_before = stok_tersedia

                if stok_tersedia < jum_baris - 1e-9:
                    raise ValueError(
                        f'Baris {idx + 1}: stok tidak mencukupi (tersedia {stok_tersedia:g} kg, butuh {jum_baris:g} kg)'
                    )

                try:
                    allocations = _fifo_allocate_ordering_batches(
                        pemesanan, tipe_sel, jum_baris,
                        jenis_kopi_override=jk_it,
                        proses_pengolahan_override=pr_it,
                    )
                except RuntimeError as re:
                    raise ValueError(f'Baris {idx + 1}: {str(re)}') from re

                if not allocations:
                    raise ValueError(f'Baris {idx + 1}: tidak ada batch pengemasan yang cocok')

                for produksi, kg in allocations:
                    hasil_produksi_id = get_next_id('hasilProduksi')
                    hasil_produksi_data = {
                        'id': hasil_produksi_id,
                        'idProduksi': str(produksi.get('idProduksi') or '').strip(),
                        'idBahan': produksi.get('idBahan'),
                        'tipeProduk': tipe_sel,
                        'kemasan': pemesanan.get('kemasan', ''),
                        'jenisKopi': jk_it,
                        'prosesPengolahan': pr_it,
                        'levelRoasting': pemesanan.get('levelRoasting', ''),
                        'tanggal': tanggal_ordering,
                        'beratSaatIni': float(kg),
                        'jumlah': 0,
                        'isFromOrdering': True,
                        'idPembelian': data['idPembelian'],
                    }
                    ins = db.hasilProduksi.insert_one(hasil_produksi_data)
                    inserted_hasil_ids.append(ins.inserted_id)
                    ip = str(produksi.get('idProduksi') or '').strip()
                    if ip:
                        all_prod_ids_order.append(ip)

                stok_remaining_by_key[key_pem] = stok_tersedia - jum_baris
                last_stok_after = stok_remaining_by_key[key_pem]

            stock_lines_needed = _line_items_stock_lines(line_items)
            if stock_lines_needed and not inserted_hasil_ids:
                raise ValueError(
                    'Tidak ada stok yang dapat dialokasikan untuk barang yang terikat stok. '
                    'Periksa ketersediaan stok di Kelola Stok.'
                )

            id_produksi_gabung = ','.join(dict.fromkeys(all_prod_ids_order))
            new_id = get_next_id('ordering')
            ordering_data = {
                'id': new_id,
                'idPembelian': data['idPembelian'],
                'idProduksi': id_produksi_gabung,
                'tipeProduk': tipe_ordering_label,
                'jumlahPesananKg': jumlah_pesanan_total,
                'kloterRingkasan': line_items,
                'stokSebelum': first_stok_before if first_stok_before is not None else 0.0,
                'stokSesudah': last_stok_after if last_stok_after is not None else 0.0,
                'statusPemesanan': 'Complete',
                'tanggalOrdering': tanggal_ordering,
                'createdAt': datetime.now(),
                'updatedAt': datetime.now(),
            }

            print(f"🔵 [ORDERING PROSES] Inserting ordering (FIFO multi-baris): {ordering_data}")
            result_ordering = db.ordering.insert_one(ordering_data)
            ordering_data['_id'] = result_ordering.inserted_id

            db.pemesanan.update_one(
                {'idPembelian': data['idPembelian']},
                {'$set': {
                    'statusPemesanan': 'Complete',
                    'statusPembayaran': 'Lunas',
                    'updatedAt': datetime.now(),
                }},
            )

            return jsonify({
                'success': True,
                'message': 'Ordering berhasil diproses, stok telah dikurangi (semua barang)',
                'ordering': json_serialize(ordering_data),
                'stokSebelum': first_stok_before,
                'stokSesudah': last_stok_after,
                'jumlahDikurangi': jumlah_pesanan_total,
                'idProduksiAlokasi': id_produksi_gabung,
            }), 201

        except ValueError as ve:
            if inserted_hasil_ids:
                db.hasilProduksi.delete_many({'_id': {'$in': inserted_hasil_ids}})
            return jsonify({'error': str(ve)}), 400
        except Exception:
            if inserted_hasil_ids:
                db.hasilProduksi.delete_many({'_id': {'$in': inserted_hasil_ids}})
            raise
        
    except Exception as e:
        print(f"❌ [ORDERING PROSES] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ordering', methods=['POST'])
def create_ordering():
    """
    DEPRECATED: Gunakan /api/ordering/proses untuk proses ordering yang mengurangi stok.
    Endpoint ini tetap ada untuk backward compatibility tapi akan redirect ke proses_ordering.
    """
    return proses_ordering()

@app.route('/api/ordering/<ordering_id>', methods=['PUT'])
def update_ordering(ordering_id):
    """Update ordering"""
    try:
        data = request.json
        
        try:
            ordering = db.ordering.find_one({'_id': ObjectId(ordering_id)})
        except:
            ordering = db.ordering.find_one({'id': int(ordering_id)})
        
        if not ordering:
            return jsonify({'error': 'Ordering not found'}), 404
        
        update_data = {}
        for field in ['statusPemesanan', 'tanggalOrdering']:
            if field in data:
                update_data[field] = data[field]
        
        update_data['updatedAt'] = datetime.now()
        
        db.ordering.update_one(
            {'_id': ordering['_id']},
            {'$set': update_data}
        )
        
        # Update pemesanan status if changed
        if 'statusPemesanan' in update_data:
            new_status = update_data['statusPemesanan']
            old_status = ordering.get('statusPemesanan', '')
            
            # Jika status berubah menjadi "Complete", pastikan stok sudah dikurangi
            if new_status == 'Complete' and old_status != 'Complete':
                # Validasi: Pastikan hasilProduksi dengan isFromOrdering sudah dibuat
                hasil_produksi_ordering = db.hasilProduksi.find_one({
                    'idProduksi': ordering['idProduksi'],
                    'idPembelian': ordering['idPembelian'],
                    'isFromOrdering': True
                })
                
                if not hasil_produksi_ordering:
                    # Jika belum ada, buat hasilProduksi record untuk tracking pengurangan stok
                    print(f"⚠️ [ORDERING UPDATE] HasilProduksi dari ordering belum ditemukan, membuat baru...")
                    produksi = db.produksi.find_one({'idProduksi': ordering['idProduksi']})
                    pemesanan = db.pemesanan.find_one({'idPembelian': ordering['idPembelian']})
                    
                    if produksi and pemesanan:
                        hasil_produksi_id = get_next_id('hasilProduksi')
                        hasil_produksi_data = {
                            'id': hasil_produksi_id,
                            'idProduksi': ordering['idProduksi'],
                            'idBahan': produksi.get('idBahan'),
                            'tipeProduk': pemesanan.get('tipeProduk'),
                            'kemasan': pemesanan.get('kemasan', ''),
                            'jenisKopi': pemesanan.get('jenisKopi'),
                            'prosesPengolahan': pemesanan.get('prosesPengolahan'),
                            'levelRoasting': pemesanan.get('levelRoasting', ''),
                            'tanggal': ordering.get('tanggalOrdering', datetime.now().strftime('%Y-%m-%d')),
                            'beratSaatIni': ordering.get('jumlahPesananKg', 0),
                            'jumlah': 0,
                            'isFromOrdering': True,
                            'idPembelian': ordering['idPembelian']
                        }
                        db.hasilProduksi.insert_one(hasil_produksi_data)
                        print(f"✅ [ORDERING UPDATE] Created hasilProduksi record for Complete status")
            
            # Update pemesanan status
            pem_set = {
                'statusPemesanan': new_status,
                'updatedAt': datetime.now(),
            }
            if new_status == 'Complete':
                pem_set['statusPembayaran'] = 'Lunas'
            db.pemesanan.update_one(
                {'idPembelian': ordering['idPembelian']},
                {'$set': pem_set}
            )
            print(f"✅ [ORDERING UPDATE] Updated pemesanan status to: {new_status}")
        
        updated = db.ordering.find_one({'_id': ordering['_id']})
        return jsonify(json_serialize(updated)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ordering/<ordering_id>', methods=['DELETE'])
def delete_ordering(ordering_id):
    """Delete ordering - Reverse stock reduction"""
    try:
        try:
            ordering = db.ordering.find_one({'_id': ObjectId(ordering_id)})
        except:
            ordering = db.ordering.find_one({'id': int(ordering_id)})
        
        if not ordering:
            return jsonify({'error': 'Ordering not found'}), 404
        
        # Hapus semua hasilProduksi ordering untuk pembelian ini (bisa beberapa batch FIFO)
        del_res = db.hasilProduksi.delete_many({
            'idPembelian': ordering.get('idPembelian'),
            'isFromOrdering': True,
        })
        print(f"🗑️ [ORDERING DELETE] Removed {del_res.deleted_count} hasilProduksi (ordering) rows")
        
        # Delete ordering
        db.ordering.delete_one({'_id': ordering['_id']})
        
        # Revert pemesanan status to Ordering
        db.pemesanan.update_one(
            {'idPembelian': ordering['idPembelian']},
            {'$set': {
                'statusPemesanan': 'Ordering',
                'updatedAt': datetime.now()
            }}
        )
        
        return jsonify({'success': True, 'message': 'Ordering deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pemesanan/stok', methods=['GET'])
def get_stok_for_pemesanan():
    """
    Stok untuk halaman pemesanan: sama dengan agregasi GET /api/stok (Kelola Stok),
    per kombinasi tipe produk + jenis kopi + proses pengolahan — bukan per id produksi.
    """
    try:
        print(f"🔵 [STOK PEMESANAN] GET /api/pemesanan/stok - Request received")
        
        if db is None:
            print(f"❌ [STOK PEMESANAN] Database connection not available")
            return jsonify({'error': 'Database connection not available', 'success': False}), 500
        
        rows, _ = _compute_stok_hasil_aggregate('', '')
        stok_list = []
        for r in rows:
            tb = float(r.get('totalBerat', 0) or 0)
            stok_list.append({
                'tipeProduk': r.get('tipeProduk', ''),
                'jenisKopi': r.get('jenisKopi', ''),
                'prosesPengolahan': r.get('prosesPengolahan', ''),
                'totalBerat': tb,
                'stokTersedia': tb,
            })
        
        print(f"✅ [STOK PEMESANAN] Returning {len(stok_list)} aggregated stok rows (selaras /api/stok)")
        return jsonify(json_serialize(stok_list)), 200
    except Exception as e:
        print(f"❌ [STOK PEMESANAN] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'success': False,
            'data': []
        }), 500

import os

# Modul Kelola Bahan & Keuangan — Cafe Damarkandang
from app import init_cafe_module
init_cafe_module(app, db, client)

if __name__ == "__main__":
    # Railway akan otomatis mengisi variabel PORT ini
    port_raw = (
        os.environ.get("PORT")
        or os.environ.get("RAILWAY_HTTP_PORT")
        or os.environ.get("RAILWAY_TCP_PORT")
        or "5003"
    )
    port = int(port_raw)
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', '1') == '1')