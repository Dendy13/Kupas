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
- **Node.js 18+** — untuk menjalankan `frontend-next` (Next.js)
- **PostgreSQL 14+** (berjalan secara lokal atau di server)
- **Docker & Docker Compose** *(opsional — untuk deployment satu perintah)*
- *(Opsional)* **Google Gemini API Key** — untuk fitur ringkasan & soal latihan AI

---

## Struktur Proyek

```
Kupas/
├── frontend-next/              # ✅ Frontend aktif — Next.js 15 + TypeScript + Tailwind CSS
│   ├── app/                    #    Halaman & layout (App Router)
│   ├── components/             #    Komponen React
│   ├── types/                  #    TypeScript types
│   ├── next.config.mjs
│   └── package.json
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
├── frontend/                   # ⚠️  Legacy — static HTML satu halaman (vanilla JS)
│   └── index.html              #    Hanya untuk referensi; gunakan frontend-next
├── deploy/
│   ├── DEPLOYMENT_NOTES.md     # Panduan deployment VPS
│   └── nginx-example.conf      # Contoh konfigurasi Nginx
├── Dockerfile                  # Docker image (python:3.11-slim)
├── docker-compose.yml          # Orkestrasi container (API + Admin)
├── run_dev.sh                  # Skrip dev lokal (kedua service + --reload)
├── requirements.txt
└── .env.example
```

> **`frontend/` vs `frontend-next/`**
>
> | | `frontend/` | `frontend-next/` |
> |---|---|---|
> | **Status** | ⚠️ Legacy | ✅ Aktif |
> | **Teknologi** | HTML + CSS + vanilla JS (1 file) | Next.js 15, TypeScript, Tailwind CSS |
> | **Deployment** | Serve statis / Nginx `root` | Vercel / Node.js standalone |
> | **Konfigurasi** | Variabel di dalam `index.html` | `.env.local` → `NEXT_PUBLIC_API_URL` |
>
> **`frontend/` sudah tidak digunakan secara aktif.** Seluruh pengembangan dan deployment menggunakan `frontend-next/`. Direktori `frontend/` boleh dihapus dari repositori untuk menghindari kebingungan:
> ```bash
> git rm -r frontend/
> git commit -m "remove: hapus frontend legacy (diganti frontend-next)"
> ```

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

### 6. Jalankan frontend (frontend-next)

Masuk ke direktori `frontend-next`, install dependensi, lalu jalankan dev server:

```bash
cd frontend-next
npm install
npm run dev
```

Buka **http://localhost:3000**.

Buat file `.env.local` dari contoh yang tersedia:

```bash
cp .env.local.example .env.local
```

Edit `.env.local` dan arahkan ke API lokal kamu:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

> Pastikan API sudah berjalan di port 8000 karena frontend mengakses `/books` dan `/generate/{slug}`.

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

Cara paling mudah untuk menjalankan Kupas di server atau lokal tanpa perlu setup Python & PostgreSQL manual. Docker Compose sudah menyertakan service PostgreSQL — **tidak perlu instalasi database terpisah**.

#### 1. Siapkan `.env`

```bash
cp .env.example .env
nano .env  # sesuaikan GEMINI_API_KEY, ADMIN_PASSWORD, dan kredensial database
```

Pastikan variabel berikut sesuai di `.env`:

```env
# Kredensial PostgreSQL (harus sama di DATABASE_URL dan POSTGRES_* vars)
POSTGRES_USER=kupas_user
POSTGRES_PASSWORD=ganti_dengan_password_aman
POSTGRES_DB=kupas

# Gunakan nama service 'postgres' sebagai host (bukan localhost)
DATABASE_URL=postgresql+asyncpg://kupas_user:ganti_dengan_password_aman@postgres:5432/kupas

# (Opsional) CORS origins untuk Admin JSON API
ADMIN_CORS_ORIGINS=https://admin.domain-kamu.com
```

| Variabel | Keterangan | Default |
|---|---|---|
| `POSTGRES_USER` | Username PostgreSQL (digunakan oleh service `postgres`) | `kupas_user` |
| `POSTGRES_PASSWORD` | Password PostgreSQL | *(harus diisi)* |
| `POSTGRES_DB` | Nama database PostgreSQL | `kupas` |
| `DATABASE_URL` | Koneksi database — gunakan `postgres` (nama service) sebagai host | — |
| `GEMINI_API_KEY` | API key Google Gemini (opsional) | *(kosong → `/generate` tidak aktif)* |
| `GEMINI_MODEL` | Model Gemini yang digunakan | `gemini-1.5-flash` |
| `CATALOG_API_URL` | Endpoint API katalog Kemdikdasmen | sudah diisi di `.env.example` |
| `DETAIL_API_URL` | Endpoint API detail buku | sudah diisi di `.env.example` |
| `PDF_STORAGE_DIR` | Folder penyimpanan PDF di dalam container | `kupas/storage/pdf` |
| `ADMIN_USER` | Username login admin panel | `admin` |
| `ADMIN_PASSWORD` | Password login admin panel | *(harus diisi)* |
| `ADMIN_CORS_ORIGINS` | Origin CORS yang diizinkan untuk JSON API admin (koma-separated) | *(kosong = tidak ada CORS)* |
| `ENV_FILE_PATH` | Path ke file `.env` yang dikelola admin panel | `.env` |

#### 2. Deskripsi service

| Service | Image / Build | Port | Keterangan |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | *(internal)* | Database PostgreSQL — data disimpan di volume `postgres_data` |
| `kupas-api` | Build dari `Dockerfile` | `8000` | REST API publik (FastAPI) |
| `kupas-admin` | Build dari `Dockerfile` | `8001` *(localhost only)* | Admin panel & JSON API (Basic Auth) |

#### 3. Build & jalankan

```bash
docker compose up -d --build
```

- **API utama** → http://localhost:8000
- **Admin panel** → http://127.0.0.1:8001 *(hanya localhost — akses via SSH tunnel dari server)*

#### 4. Isi database (pertama kali)

```bash
docker compose exec kupas-api python -m kupas.crawler.fetch_catalog
docker compose exec kupas-api python -m kupas.crawler.download_pdf
docker compose exec kupas-api python -m kupas.processor.extract_text
```

#### 5. Perintah berguna

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

Frontend `frontend-next` berjalan sebagai proses Node.js tersendiri (port 3000). Nginx memproxy request ke frontend maupun ke API.

Buat file `/etc/systemd/system/kupas-frontend.service`:

```ini
[Unit]
Description=Kupas Frontend (Next.js)
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/kupas/frontend-next
Environment=NODE_ENV=production
Environment=NEXT_PUBLIC_API_URL=https://api.domain-kamu.com
ExecStart=/usr/bin/npm start
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

> Sebelumnya, build dulu frontend-nya:
> ```bash
> cd /opt/kupas/frontend-next
> npm install
> npm run build
> ```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kupas-frontend
```

Buat file `/etc/nginx/sites-available/kupas`:

```nginx
server {
    listen 80;
    server_name domain-kamu.com;  # ganti dengan domain/IP kamu

    # Proxy ke Next.js frontend
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

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

### ▲ Vercel (Frontend — Direkomendasikan untuk hosting frontend)

Vercel adalah platform yang dibuat oleh tim Next.js sehingga mendukung `frontend-next/` secara native. Deploy bisa dilakukan dalam beberapa langkah tanpa konfigurasi tambahan.

#### Prasyarat

- Backend (FastAPI) sudah berjalan dan dapat diakses publik (misalnya di VPS atau via Docker). Vercel hanya hosting frontend.

#### Langkah deploy frontend-next ke Vercel

**1. Import repositori ke Vercel**

- Buka [vercel.com/new](https://vercel.com/new) dan pilih repositori `Kupas`.

**2. Konfigurasi project**

Di halaman konfigurasi, ubah pengaturan berikut:

| Pengaturan | Nilai |
|---|---|
| **Root Directory** | `frontend-next` |
| **Framework Preset** | Next.js *(terdeteksi otomatis)* |
| **Build Command** | `npm run build` *(default)* |
| **Output Directory** | *(biarkan default)* |

**3. Tambahkan environment variable**

Klik **Environment Variables** dan tambahkan:

| Key | Value | Contoh |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | URL backend API kamu (tanpa trailing slash) | `https://api.domain-kamu.com` |

> `NEXT_PUBLIC_API_URL` harus dapat diakses dari browser pengguna (bukan hanya dari server Vercel). Pastikan backend kamu memiliki CORS yang mengizinkan domain Vercel kamu.

**4. Deploy**

Klik **Deploy**. Vercel akan otomatis build dan deploy. Setiap `git push` ke branch utama akan men-trigger redeploy otomatis.

**5. Konfigurasi CORS di backend**

Tambahkan domain Vercel kamu ke `ADMIN_CORS_ORIGINS` di `.env` (untuk Admin JSON API). Untuk API utama (port 8000), pastikan origin frontend sudah diizinkan.

Jika menggunakan VPS + Nginx, tambahkan header CORS di konfigurasi Nginx atau di kode FastAPI.

#### ⚠️ Catatan penting

- **Backend tidak di-deploy ke Vercel** — Vercel hanya untuk frontend Next.js.
- Backend (FastAPI + PostgreSQL + crawler) tetap harus berjalan di VPS atau Docker karena memerlukan persistent storage dan proses background.
- `frontend/` (HTML legacy) **tidak perlu di-deploy** — gunakan `frontend-next/` saja.

---

## Lisensi

MIT
