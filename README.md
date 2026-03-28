# Kupas

**Kupas** adalah platform edukasi berbasis web untuk mengunduh dan mempelajari ebook dari [buku.kemendikdasmen.go.id](https://buku.kemendikdasmen.go.id).

Fitur utama:
- 📥 **Download ebook** langsung dari URL PDF Kemdikdasmen
- 📂 **Kelola ebook** yang sudah tersimpan secara lokal
- 🤖 **Generate soal latihan** dari ebook menggunakan Google Gemini AI (atau soal generik jika API key tidak tersedia)
- 🔌 **REST API** berbasis FastAPI untuk integrasi dengan sistem lain

---

## Struktur Proyek

```
Kupas/
├── app.py                          # Flask web app (UI)
├── requirements.txt
├── .env.example
├── ebooks/                         # Folder penyimpanan PDF yang diunduh
├── templates/
│   ├── index.html                  # Halaman utama
│   └── questions.html              # Halaman soal latihan
└── kupas/
    ├── __init__.py                 # Helper: download_ebook, generate_questions
    ├── api/
    │   └── main.py                 # FastAPI REST API
    ├── crawler/
    │   ├── fetch_catalog.py        # Ambil katalog buku dari API Kemdikdasmen
    │   └── download_pdf.py         # Unduh PDF ke database & storage
    ├── processor/
    │   └── extract_text.py         # Ekstrak teks per bab dari PDF
    └── storage/
        └── pdf/                    # Penyimpanan PDF untuk FastAPI pipeline
```

---

## Cara Menjalankan (Flask Web App)

### 1. Siapkan environment

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Konfigurasi (opsional)

Salin `.env.example` ke `.env` dan sesuaikan nilainya:

```bash
cp .env.example .env
```

| Variabel | Keterangan | Default |
|---|---|---|
| `GEMINI_API_KEY` | API key Google Gemini untuk generate soal | *(kosong → soal generik)* |
| `GEMINI_MODEL` | Model Gemini yang digunakan | `gemini-pro` |
| `EBOOKS_DIR` | Folder penyimpanan ebook | `ebooks` |
| `FLASK_SECRET_KEY` | Secret key Flask | `kupas-secret-key` |

### 3. Jalankan aplikasi

```bash
python app.py
```

Buka browser di **http://localhost:8000**.

---

## Cara Menggunakan

1. **Download ebook** — Tempel URL PDF dari situs Kemdikdasmen ke kolom input, klik *Download*.
2. **Lihat daftar ebook** — Ebook yang sudah diunduh tampil di bagian bawah.
3. **Generate soal** — Klik tombol *Generate Soal* di samping ebook yang ingin dipelajari.

---

## REST API (FastAPI)

Selain web app, tersedia juga REST API berbasis FastAPI dengan koneksi ke database PostgreSQL.

### Menjalankan API

```bash
uvicorn kupas.api.main:app --reload --port 8001
```

### Endpoint

| Method | Path | Deskripsi |
|---|---|---|
| `GET` | `/books` | Daftar semua buku |
| `GET` | `/books/{slug}` | Detail buku beserta bab |
| `GET` | `/generate/{slug}` | Ringkasan & soal dari Gemini AI |

Dokumentasi interaktif tersedia di **http://localhost:8001/docs**.

---

## Pipeline Data (Crawler + Processor)

```bash
# 1. Ambil katalog buku dari API Kemdikdasmen
python -m kupas.crawler.fetch_catalog

# 2. Unduh PDF untuk semua buku (atau satu buku)
python -m kupas.crawler.download_pdf
python -m kupas.crawler.download_pdf --slug nama-slug

# 3. Ekstrak teks per bab dari PDF
python -m kupas.processor.extract_text
python -m kupas.processor.extract_text --slug nama-slug
```

---

## Lisensi

MIT
