# Deployment Notes

## Arsitektur (1 VPS, 2 Service)

```
Internet
   │
  Nginx (port 80/443)
   ├── api.domain.com  → proxy ke 127.0.0.1:8000  (API utama)
   └── admin.domain.com → proxy ke 127.0.0.1:8001  (Admin panel)
```

### Jalankan 2 proses Uvicorn

```bash
# API utama (bisa diakses publik lewat Nginx)
uvicorn kupas.api.main:app --host 127.0.0.1 --port 8000 --workers 2

# Admin panel (hanya localhost, JANGAN bind ke 0.0.0.0)
uvicorn kupas.admin.main:app --host 127.0.0.1 --port 8001
```

Atau gunakan **Docker Compose** (lihat bagian bawah) untuk menjalankan keduanya sekaligus.

---

## Cara Akses Admin (bind ke localhost, tidak ada di internet)

### Opsi 1 — SSH Tunnel ✅ (Paling mudah, recommended untuk akses sesekali)

```bash
ssh -L 8001:127.0.0.1:8001 user@IP_VPS
```

Lalu buka di browser lokal: `http://localhost:8001`

- Tidak perlu setup apapun
- Traffic terenkripsi lewat SSH
- Admin **tidak pernah expose ke internet**

### Opsi 2 — Tailscale/WireGuard (Recommended untuk tim / akses rutin)

```bash
# Install Tailscale di VPS dan laptop
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Bind Admin ke interface Tailscale saja. Hanya device dalam VPN yang bisa akses.

### Opsi 3 — Nginx + IP Whitelist (Untuk IP statis)

```nginx
location / {
    allow 1.2.3.4;   # IP kamu (harus statis)
    deny all;
    proxy_pass http://127.0.0.1:8001;
}
```

---

## Admin JSON API (`/api/v1/`)

Admin panel menyediakan JSON API yang juga dilindungi HTTP Basic Auth (kredensial sama dengan UI web).
Berguna untuk automasi atau integrasi skrip.

```bash
# Contoh dengan curl (ganti user:pass sesuai .env)
curl -u admin:password http://localhost:8001/api/v1/stats
curl -u admin:password http://localhost:8001/api/v1/books
curl -u admin:password -X POST http://localhost:8001/api/v1/books/nama-slug/download
curl -u admin:password -X POST http://localhost:8001/api/v1/books/nama-slug/extract
curl -u admin:password -X DELETE http://localhost:8001/api/v1/books/nama-slug
```

---

## Docker Compose

Cara deploy tercepat — tidak perlu install Python/PostgreSQL manual di host.

```bash
cp .env.example .env
# Edit .env: DATABASE_URL, ADMIN_PASSWORD, GEMINI_API_KEY, dll.
docker compose up -d --build
```

Service yang berjalan:
- `kupas-api` → port `8000` (2 worker)
- `kupas-admin` → port `127.0.0.1:8001` (localhost-only)

Volume `pdf_storage` di-share antar kedua container sehingga PDF yang diunduh lewat admin langsung tersedia untuk API.

```bash
# Isi database setelah pertama kali up
docker compose exec kupas-api python -m kupas.crawler.fetch_catalog
docker compose exec kupas-api python -m kupas.crawler.download_pdf
docker compose exec kupas-api python -m kupas.processor.extract_text
```

---

## Ringkasan Pilihan

| Situasi                        | Cara                    |
|-------------------------------|-------------------------|
| Deploy cepat / satu perintah  | **Docker Compose**      |
| Akses admin sesekali / dev    | **SSH Tunnel**          |
| Tim kecil, akses rutin        | **Tailscale**           |
| IP statis, produksi           | **Nginx + IP whitelist**|
