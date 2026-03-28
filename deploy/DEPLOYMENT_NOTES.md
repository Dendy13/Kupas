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
uvicorn kupas.main:app --host 127.0.0.1 --port 8000

# Admin panel (hanya localhost, JANGAN bind ke 0.0.0.0)
uvicorn kupas.admin:app --host 127.0.0.1 --port 8001
```

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

## Ringkasan Pilihan

| Situasi                        | Cara                    |
|-------------------------------|-------------------------|
| Akses sesekali / development  | **SSH Tunnel**          |
| Tim kecil, akses rutin        | **Tailscale**           |
| IP statis, produksi           | **Nginx + IP whitelist**|
