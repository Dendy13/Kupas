# Kupas

**Kupas** adalah platform edukasi berbasis web untuk menjelajahi, mengunduh, dan mempelajari ebook dari [buku.kemendikdasmen.go.id](https://buku.kemendikdasmen.go.id).

Fitur utama:
- 📚 **Katalog buku** — jelajahi buku resmi Kemdikdasmen berdasarkan jenjang & mata pelajaran
- 🤖 **Ringkasan & soal latihan** — generate otomatis menggunakan Google Gemini AI
- 🔌 **REST API** berbasis FastAPI dengan database PostgreSQL
- 🕷️ **Pipeline crawler** — ambil katalog, unduh PDF, dan ekstrak teks per bab
- 🔐 **Admin panel** — kelola buku, unduh PDF, dan ekstrak bab lewat UI web (port 8001) atau JSON API (`/api/v1/`)
- 🐳 **Docker Compose** — deploy satu perintah dengan `docker compose up`

---

## Prasyarat

Pastikan kamu sudah menginstal:

- **Python 3.11+**
- **PostgreSQL 14+** (berjalan secara lokal atau di server)
- **Docker & Docker Compose** *(opsional — untuk deployment satu perintah)*
- *(Opsional)* **Google Gemini API Key** — untuk fitur ringkasan & soal latihan AI

---

## Struktur Proyek

```
Kupas/
├── frontend/
│   └── index.html              # Antarmuka web (static HTML)
├── kupas/
│   ├── __init__.py             # Helper: download_ebook, generate_questions
│   ├── api/
│   │   └── main.py             # FastAPI REST API (port 8000)
│   ├── admin/
│   │   └── main.py             # Admin panel & JSON API (port 8001)
│   ├── crawler/
│   │   ├── fetch_catalog.py    # Ambil katalog buku dari API Kemdikdasmen
│   │   └── download_pdf.py     # Unduh PDF ke database & storage
│   ├── processor/
│   │   └── extract_text.py     # Ekstrak teks per bab dari PDF
│   └── storage/
│       └── pdf/                # Penyimpanan file PDF
├── deploy/
│   ├── DEPLOYMENT_NOTES.md     # Panduan deployment VPS
│   └── nginx-example.conf      # Contoh konfigurasi Nginx
├── Dockerfile                  # Docker image (python:3.11-slim)
├── docker-compose.yml          # Orkestrasi container (API + Admin)
├── run_dev.sh                  # Skrip dev lokal (kedua service + --reload)
├── requirements.txt
└── .env.example
```

---

## Cara Menjalankan (Development)

### 1. Clone & siapkan environment

```bash
git clone https://github.com/Dendy13/Kupas.git
cd Kupas

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Siapkan database PostgreSQL

Buat database baru untuk Kupas:

```bash
psql -U postgres -c "CREATE DATABASE kupas;"
```

> Jika PostgreSQL menggunakan user/password berbeda, sesuaikan di langkah berikutnya.

### 3. Konfigurasi environment

Salin `.env.example` ke `.env` dan sesuaikan nilainya:

```bash
cp .env.example .env
```

Edit file `.env`:

```env
# Ganti user, password, host, dan port sesuai setup PostgreSQL kamu
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/kupas

# (Opsional) Isi dengan API key dari https://aistudio.google.com
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash

# URL API katalog Kemdikdasmen (tidak perlu diubah)
CATALOG_API_URL=https://api.buku.cloudapp.web.id/getPenggerakTextBooks
DETAIL_API_URL=https://api.buku.cloudapp.web.id/getDetails

# Folder penyimpanan PDF
PDF_STORAGE_DIR=kupas/storage/pdf

# Admin panel
ADMIN_USER=admin
ADMIN_PASSWORD=ganti_password_ini
# Daftar origin yang diizinkan mengakses Admin JSON API via CORS
# Pisahkan dengan koma. Biarkan kosong untuk memblokir semua CORS request.
ADMIN_CORS_ORIGINS=
ENV_FILE_PATH=.env
```

| Variabel | Keterangan | Default |
|---|---|---|
| `DATABASE_URL` | Koneksi ke PostgreSQL | `postgresql+asyncpg://user:password@localhost:5432/kupas` |
| `GEMINI_API_KEY` | API key Google Gemini (opsional) | *(kosong → endpoint `/generate` tidak aktif)* |
| `GEMINI_MODEL` | Model Gemini yang digunakan | `gemini-1.5-flash` |
| `CATALOG_API_URL` | Endpoint API katalog Kemdikdasmen | sudah diisi |
| `DETAIL_API_URL` | Endpoint API detail buku | sudah diisi |
| `PDF_STORAGE_DIR` | Folder penyimpanan PDF | `kupas/storage/pdf` |
| `ADMIN_USER` | Username login admin panel | `admin` |
| `ADMIN_PASSWORD` | Password login admin panel | `changeme` |
| `ADMIN_CORS_ORIGINS` | Origin CORS yang diizinkan untuk JSON API admin (koma-separated) | *(kosong = tidak ada CORS)* |
| `ENV_FILE_PATH` | Path ke file `.env` yang dikelola admin panel | `.env` |

### 4. Jalankan API & Admin Panel

**Cara cepat — gunakan skrip dev:**

```bash
chmod +x run_dev.sh
./run_dev.sh
```

Skrip ini menjalankan kedua service sekaligus dengan `--reload`:
- **API utama** → http://localhost:8000 (docs: http://localhost:8000/docs)
- **Admin panel** → http://localhost:8001 (login dengan `ADMIN_USER`/`ADMIN_PASSWORD`)

**Atau jalankan terpisah:**

```bash
# API utama
uvicorn kupas.api.main:app --reload --port 8000

# Admin panel (terminal terpisah)
uvicorn kupas.admin.main:app --reload --port 8001
```

API akan otomatis membuat tabel database saat pertama kali dijalankan.

Dokumentasi interaktif API utama tersedia di **http://localhost:8000/docs**.

### 5. Jalankan pipeline data (isi database)

```bash
# Ambil katalog buku dari API Kemdikdasmen (simpan ke database)
python -m kupas.crawler.fetch_catalog

# Unduh PDF untuk semua buku (atau satu buku tertentu)
python -m kupas.crawler.download_pdf
python -m kupas.crawler.download_pdf --slug nama-slug

# Ekstrak teks per bab dari PDF
python -m kupas.processor.extract_text
python -m kupas.processor.extract_text --slug nama-slug
```

> ⚠️ Proses download & ekstrak bisa memakan waktu cukup lama tergantung jumlah buku.

### 6. Buka frontend

Buka file `frontend/index.html` langsung di browser, atau serve dengan server statis sederhana:

```bash
python -m http.server 3000 --directory frontend
```

Lalu buka **http://localhost:3000**.

> Pastikan API sudah berjalan di port 8000 karena frontend mengakses `/books` dan `/generate/{slug}` dari origin yang sama. Untuk development, kamu bisa edit variabel `API_BASE` di bagian atas `frontend/index.html` menjadi `http://localhost:8000`.

---

## Endpoint API

### API Utama (port 8000) — publik

| Method | Path | Deskripsi |
|---|---|---|
| `GET` | `/books` | Daftar semua buku |
| `GET` | `/books/{slug}` | Detail buku beserta bab |
| `GET` | `/generate/{slug}` | Ringkasan & soal dari Gemini AI |

### Admin JSON API (port 8001 — `localhost` only) — butuh HTTP Basic Auth

| Method | Path | Deskripsi |
|---|---|---|
| `GET` | `/api/v1/stats` | Statistik agregat (buku, PDF, chapter) |
| `GET` | `/api/v1/books` | Daftar buku lengkap |
| `POST` | `/api/v1/books/{slug}/download` | Mulai unduh PDF (background task) |
| `POST` | `/api/v1/books/{slug}/extract` | Mulai ekstrak chapter (background task) |
| `DELETE` | `/api/v1/books/{slug}` | Hapus buku beserta seluruh chapter |

---

## Deployment

### 🐳 Docker Compose (Direkomendasikan untuk deploy cepat)

Cara paling mudah untuk menjalankan Kupas di server atau lokal tanpa perlu setup Python & PostgreSQL manual.

#### 1. Siapkan `.env`

```bash
cp .env.example .env
nano .env  # sesuaikan DATABASE_URL, GEMINI_API_KEY, ADMIN_PASSWORD, dsb.
```

> **Penting:** `DATABASE_URL` harus mengarah ke PostgreSQL yang bisa diakses container (bukan `localhost`).  
> Jika menggunakan PostgreSQL di host: gunakan `host.docker.internal` (Mac/Windows) atau IP lokal (Linux).  
> Contoh: `postgresql+asyncpg://kupas_user:password@host.docker.internal:5432/kupas`

#### 2. Build & jalankan

```bash
docker compose up -d --build
```

- **API utama** → http://localhost:8000
- **Admin panel** → http://127.0.0.1:8001 *(hanya localhost — akses via SSH tunnel dari server)*

#### 3. Isi database (pertama kali)

```bash
docker compose exec kupas-api python -m kupas.crawler.fetch_catalog
docker compose exec kupas-api python -m kupas.crawler.download_pdf
docker compose exec kupas-api python -m kupas.processor.extract_text
```

#### 4. Perintah berguna

```bash
docker compose logs -f          # lihat log kedua service
docker compose restart          # restart semua service
docker compose down             # stop & hapus container (volume tetap ada)
docker compose down -v          # stop & hapus container + volume PDF
```

---

### 🖥️ VPS (Tanpa Docker)

Deployment di VPS (misalnya DigitalOcean, Linode, AWS EC2) memberikan kontrol penuh dan cocok untuk aplikasi ini karena membutuhkan penyimpanan PDF dan proses crawler yang berjalan lama.

#### 1. Persiapan server

```bash
# Update package list
sudo apt update && sudo apt upgrade -y

# Install Python, pip, dan PostgreSQL
sudo apt install -y python3.11 python3.11-venv python3-pip postgresql postgresql-contrib nginx
```

#### 2. Setup database

```bash
sudo -u postgres psql -c "CREATE USER kupas_user WITH PASSWORD 'ganti_password_ini';"
sudo -u postgres psql -c "CREATE DATABASE kupas OWNER kupas_user;"
```

#### 3. Clone & konfigurasi aplikasi

```bash
git clone https://github.com/Dendy13/Kupas.git /opt/kupas
cd /opt/kupas

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env  # sesuaikan DATABASE_URL dan GEMINI_API_KEY
```

#### 4. Isi database

```bash
source .venv/bin/activate
python -m kupas.crawler.fetch_catalog
python -m kupas.crawler.download_pdf
python -m kupas.processor.extract_text
```

#### 5. Jalankan sebagai service (systemd)

Buat file `/etc/systemd/system/kupas-api.service`:

```ini
[Unit]
Description=Kupas API
After=network.target postgresql.service

[Service]
User=www-data
WorkingDirectory=/opt/kupas
EnvironmentFile=/opt/kupas/.env
ExecStart=/opt/kupas/.venv/bin/uvicorn kupas.api.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Buat file `/etc/systemd/system/kupas-admin.service`:

```ini
[Unit]
Description=Kupas Admin Panel
After=network.target postgresql.service

[Service]
User=www-data
WorkingDirectory=/opt/kupas
EnvironmentFile=/opt/kupas/.env
ExecStart=/opt/kupas/.venv/bin/uvicorn kupas.admin.main:app --host 127.0.0.1 --port 8001
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kupas-api kupas-admin
```

#### 6. Konfigurasi Nginx

Buat file `/etc/nginx/sites-available/kupas`:

```nginx
server {
    listen 80;
    server_name domain-kamu.com;  # ganti dengan domain/IP kamu

    # Serve frontend statis
    root /opt/kupas/frontend;
    index index.html;

    # Proxy ke FastAPI untuk permintaan API
    location ~ ^/(books|generate) {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/kupas /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

#### 7. (Opsional) HTTPS dengan Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d domain-kamu.com
```

---

### ▲ Vercel (Alternatif — Dengan Keterbatasan)

Vercel bisa digunakan untuk men-deploy **frontend** sebagai static site, dan **backend** sebagai serverless function. Namun ada beberapa keterbatasan penting yang perlu dipertimbangkan.

#### Cara deploy ke Vercel

**Frontend** dapat langsung di-deploy ke Vercel karena hanya berupa file HTML statis.

**Backend (FastAPI)** membutuhkan konfigurasi tambahan. Buat file `vercel.json` di root proyek:

```json
{
  "builds": [
    { "src": "kupas/api/main.py", "use": "@vercel/python" }
  ],
  "routes": [
    { "src": "/(books|generate)(.*)", "dest": "kupas/api/main.py" },
    { "src": "/(.*)", "dest": "frontend/index.html" }
  ]
}
```

Tambahkan environment variable di dashboard Vercel:
- `DATABASE_URL` — gunakan PostgreSQL eksternal (misalnya [Neon](https://neon.tech) atau [Supabase](https://supabase.com))
- `GEMINI_API_KEY`

#### ⚠️ Keterbatasan Vercel (dibanding VPS)

| Aspek | VPS | Vercel |
|---|---|---|
| **Timeout eksekusi** | Tidak terbatas | 10 detik (hobby) / 60 detik (pro) — download & ekstrak PDF akan gagal |
| **Penyimpanan file** | Bebas (disk server) | ❌ Tidak ada persistent storage — PDF tidak bisa disimpan |
| **Crawler pipeline** | Bisa dijalankan kapan saja | ❌ Tidak bisa — tidak ada background worker |
| **Database** | PostgreSQL lokal | Wajib pakai layanan eksternal berbayar/freemium |
| **Cold start** | Tidak ada | Ada (delay ~1–3 detik saat pertama request) |
| **Kontrol server** | Penuh | Tidak ada akses ke server |
| **Biaya** | Sesuai spec VPS | Gratis untuk traffic rendah, berbayar untuk lebih |

**Kesimpulan:** Vercel cocok hanya jika kamu ingin demo/prototype frontend + API sederhana dengan data yang sudah ada di database eksternal. Untuk penggunaan nyata (crawler, download PDF, proses ekstraksi), **VPS jauh lebih tepat**.

---

## Lisensi

MIT
