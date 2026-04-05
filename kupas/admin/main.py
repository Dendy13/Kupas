"""
kupas/admin/main.py
Kupas Admin Panel — separate FastAPI application.

Run:
    uvicorn kupas.admin.main:app --port 8001

Proxy via Nginx (admin.kupas.id → port 8001):
    server {
        listen 80;
        server_name admin.kupas.id;
        location / { proxy_pass http://127.0.0.1:8001; }
    }

All endpoints require HTTP Basic Authentication.
Credentials are read from ADMIN_USER / ADMIN_PASSWORD environment variables.
"""

import ipaddress
import logging
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, AsyncGenerator
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Form, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from sqlalchemy import func, select

from kupas.config import (
    ADMIN_USER,
    ADMIN_PASSWORD,
    PDF_STORAGE_DIR,
    ADMIN_CORS_ORIGINS,
    ENV_FILE_PATH,
)
from kupas.models import Book, Chapter
from kupas.database import engine, create_tables, get_session

logger = logging.getLogger(__name__)

# Env vars exposed in the Settings UI — (key, label, is_sensitive)
MANAGED_ENV_VARS: list[tuple[str, str, bool]] = [
    ("DATABASE_URL", "Database URL (PostgreSQL)", True),
    ("GEMINI_API_KEY", "Google Gemini API Key", True),
    ("GEMINI_MODEL", "Gemini Model Name", False),
    ("CATALOG_API_URL", "Catalog API URL", False),
    ("DETAIL_API_URL", "Detail API URL", False),
    ("PDF_STORAGE_DIR", "PDF Storage Directory", False),
    ("ADMIN_USER", "Admin Username", False),
    ("ADMIN_PASSWORD", "Admin Password", True),
    ("ENV_FILE_PATH", "Path to .env File", False),
]

# Slugs reserved by admin routes — disallowed as book slugs
_RESERVED_SLUGS = {"add", "new", "delete", "edit", "list"}

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

_security = HTTPBasic()


def require_auth(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    ok_user = secrets.compare_digest(credentials.username.encode(), ADMIN_USER.encode())
    ok_pass = secrets.compare_digest(credentials.password.encode(), ADMIN_PASSWORD.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kredensial tidak valid.",
            headers={"WWW-Authenticate": 'Basic realm="Kupas Admin"'},
        )
    return credentials.username


Auth = Annotated[str, Depends(require_auth)]

# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await create_tables()
    yield
    await engine.dispose()


app = FastAPI(
    title="Kupas Admin",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ADMIN_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ---------------------------------------------------------------------------
# JSON API router — /api/v1/
# ---------------------------------------------------------------------------

api_router = APIRouter(prefix="/api/v1")


# Pydantic schemas for JSON responses
class BookSchema(BaseModel):
    id: int
    slug: str
    title: str | None
    author: str | None
    subject: str | None
    grade: str | None
    cover_url: str | None
    pdf_url: str | None
    pdf_path: str | None

    model_config = {"from_attributes": True}


class StatsSchema(BaseModel):
    total_books: int
    pdfs_downloaded: int
    pdfs_missing: int
    total_chapters: int
    books_extracted: int


@api_router.get("/stats", response_model=StatsSchema, summary="Admin stats (JSON)")
async def api_stats(_: Auth) -> StatsSchema:
    async with get_session() as session:
        total = (
            await session.execute(select(func.count()).select_from(Book))
        ).scalar_one()
        pdfs = (
            await session.execute(
                select(func.count()).select_from(Book).where(Book.pdf_path.isnot(None))
            )
        ).scalar_one()
        chapters = (
            await session.execute(select(func.count()).select_from(Chapter))
        ).scalar_one()
        extracted = (
            await session.execute(
                select(func.count(func.distinct(Chapter.book_id)))
            )
        ).scalar_one()
    return StatsSchema(
        total_books=total,
        pdfs_downloaded=pdfs,
        pdfs_missing=total - pdfs,
        total_chapters=chapters,
        books_extracted=extracted,
    )


@api_router.get("/books", response_model=list[BookSchema], summary="List books (JSON)")
async def api_list_books(_: Auth) -> list[BookSchema]:
    async with get_session() as session:
        result = await session.execute(select(Book).order_by(Book.title))
        books = result.scalars().all()
    return [BookSchema.model_validate(b) for b in books]


@api_router.post(
    "/books/{slug}/download",
    summary="Trigger PDF download (JSON)",
)
async def api_trigger_download(
    slug: str, _: Auth, background_tasks: BackgroundTasks
) -> JSONResponse:
    async with get_session() as session:
        book = (
            await session.execute(select(Book).where(Book.slug == slug))
        ).scalar_one_or_none()
        if book is None:
            raise HTTPException(status_code=404, detail=f"Book '{slug}' not found.")
        if not book.pdf_url:
            raise HTTPException(
                status_code=422, detail=f"Book '{slug}' has no pdf_url set."
            )
    background_tasks.add_task(_bg_download, slug)
    return JSONResponse({"status": "accepted", "slug": slug, "action": "download"})


@api_router.post(
    "/books/{slug}/extract",
    summary="Trigger chapter extraction (JSON)",
)
async def api_trigger_extract(
    slug: str, _: Auth, background_tasks: BackgroundTasks
) -> JSONResponse:
    async with get_session() as session:
        book = (
            await session.execute(select(Book).where(Book.slug == slug))
        ).scalar_one_or_none()
        if book is None:
            raise HTTPException(status_code=404, detail=f"Book '{slug}' not found.")
        if not book.pdf_path or not Path(book.pdf_path).exists():
            raise HTTPException(
                status_code=422,
                detail=f"PDF for '{slug}' has not been downloaded yet.",
            )
    background_tasks.add_task(_bg_extract, slug)
    return JSONResponse({"status": "accepted", "slug": slug, "action": "extract"})


@api_router.delete("/books/{slug}", summary="Delete a book (JSON)")
async def api_delete_book(slug: str, _: Auth) -> JSONResponse:
    async with get_session() as session:
        book = (
            await session.execute(select(Book).where(Book.slug == slug))
        ).scalar_one_or_none()
        if book is None:
            raise HTTPException(status_code=404, detail=f"Book '{slug}' not found.")

        chapters = (
            await session.execute(
                select(Chapter).where(Chapter.book_id == book.id)
            )
        ).scalars().all()
        for ch in chapters:
            await session.delete(ch)
        await session.delete(book)
        await session.commit()
    return JSONResponse({"status": "deleted", "slug": slug})


app.include_router(api_router)

# ---------------------------------------------------------------------------
# .env file helpers
# ---------------------------------------------------------------------------


def _read_env_file() -> dict[str, str]:
    """Parse the .env file and return all key=value pairs as a dict."""
    result: dict[str, str] = {}
    try:
        for raw in ENV_FILE_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return result


def _write_env_file(updates: dict[str, str]) -> None:
    """Rewrite the .env file, updating only the keys present in *updates*."""
    lines: list[str] = []
    written: set[str] = set()

    if ENV_FILE_PATH.exists():
        for raw in ENV_FILE_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, _ = line.partition("=")
                k = k.strip()
                if k in updates:
                    lines.append(f"{k}={updates[k]}")
                    written.add(k)
                else:
                    lines.append(raw)
            else:
                lines.append(raw)

    # Append any keys that were not already present in the file
    for k, v in updates.items():
        if k not in written:
            lines.append(f"{k}={v}")

    ENV_FILE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# PDF download helper
# (admin-provided URLs — SSRF-safe but no host whitelist, admin is trusted)
# ---------------------------------------------------------------------------


def _validate_pdf_url(url: str) -> None:
    """Raise ValueError for non-http(s) schemes or private/loopback IPs."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL harus menggunakan skema http atau https.")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("URL tidak memiliki host yang valid.")
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        raise ValueError("URL menuju host lokal tidak diizinkan.")
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        # host is a domain name, not an IP address — allowed
        return
    if addr.is_private or addr.is_loopback or addr.is_link_local:
        raise ValueError("URL menuju alamat IP privat tidak diizinkan.")


async def _stream_download(slug: str, pdf_url: str) -> Path:
    """Stream-download a PDF and save it to storage. Returns the local path."""
    PDF_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    dest = PDF_STORAGE_DIR / f"{slug}.pdf"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Kupas/1.0; educational use)"}
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        async with client.stream("GET", pdf_url, headers=headers) as resp:
            resp.raise_for_status()
            with dest.open("wb") as fh:
                async for chunk in resp.aiter_bytes(8192):
                    fh.write(chunk)
    return dest


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------


async def _bg_download(slug: str) -> None:
    """Download the PDF for a book that already has pdf_url set."""
    async with get_session() as session:
        result = await session.execute(select(Book).where(Book.slug == slug))
        book = result.scalar_one_or_none()
        if not book or not book.pdf_url:
            return
        try:
            dest = await _stream_download(slug, book.pdf_url)
            book.pdf_path = str(dest)
            await session.commit()
            logger.info("Downloaded PDF for '%s' → %s", slug, dest)
        except Exception:
            logger.exception("Failed to download PDF for '%s'", slug)


async def _bg_extract(slug: str) -> None:
    """Extract chapters from the downloaded PDF for a book."""
    from kupas.processor.extract_text import process_book

    await process_book(slug)


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f1f5f9; color: #0f172a; display: flex; min-height: 100vh;
}
/* Sidebar */
.sidebar {
  width: 220px; min-height: 100vh; background: #1e293b;
  display: flex; flex-direction: column; flex-shrink: 0;
}
.sidebar .brand {
  padding: 1.25rem; font-size: 1.1rem; font-weight: 700;
  color: #f8fafc; border-bottom: 1px solid #334155;
}
.sidebar .brand span { color: #38bdf8; }
.sidebar nav a {
  display: block; padding: .6rem 1.25rem; color: #94a3b8;
  text-decoration: none; font-size: .875rem;
  border-left: 3px solid transparent;
}
.sidebar nav a:hover, .sidebar nav a.active {
  color: #f8fafc; background: #334155; border-left-color: #38bdf8;
}
.sidebar .footer {
  padding: .75rem 1.25rem; font-size: .72rem; color: #475569;
  border-top: 1px solid #334155; margin-top: auto;
}
/* Main layout */
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.topbar {
  background: #fff; border-bottom: 1px solid #e2e8f0;
  padding: .75rem 1.5rem; display: flex; align-items: center;
}
.topbar h1 { font-size: 1.05rem; font-weight: 600; }
.content { padding: 1.5rem; }
/* Alert */
.alert {
  padding: .7rem 1rem; border-radius: .45rem;
  margin-bottom: 1rem; font-size: .875rem;
}
.alert-success { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
.alert-error   { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
.alert-info    { background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }
.alert-warning { background: #fef9c3; color: #854d0e; border: 1px solid #fde68a; }
/* Stats grid */
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 1rem; margin-bottom: 1.5rem;
}
.stat {
  background: #fff; border: 1px solid #e2e8f0; border-radius: .65rem;
  padding: 1.1rem 1rem; text-align: center;
}
.stat .val { font-size: 1.8rem; font-weight: 700; color: #2563eb; }
.stat .lbl { font-size: .78rem; color: #64748b; margin-top: .2rem; }
/* Card */
.card {
  background: #fff; border: 1px solid #e2e8f0; border-radius: .65rem;
  padding: 1.25rem; margin-bottom: 1.25rem;
}
.card-title {
  font-size: .95rem; font-weight: 600; margin-bottom: 1rem;
  padding-bottom: .5rem; border-bottom: 1px solid #f1f5f9;
}
/* Table */
.tbl-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .83rem; }
th {
  background: #f8fafc; color: #64748b; font-weight: 600;
  text-align: left; padding: .55rem .7rem;
  border-bottom: 2px solid #e2e8f0; white-space: nowrap;
}
td { padding: .5rem .7rem; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f8fafc; }
/* Badge */
.badge {
  display: inline-block; padding: .15rem .5rem;
  border-radius: 999px; font-size: .72rem; font-weight: 600;
}
.ok  { background: #dcfce7; color: #166534; }
.no  { background: #fee2e2; color: #991b1b; }
/* Buttons */
.btn {
  display: inline-block; padding: .38rem .85rem; border-radius: .4rem;
  font-size: .8rem; font-weight: 500; cursor: pointer;
  border: none; text-decoration: none;
}
.btn:hover { filter: brightness(90%); }
.btn-primary   { background: #2563eb; color: #fff; }
.btn-success   { background: #16a34a; color: #fff; }
.btn-warning   { background: #d97706; color: #fff; }
.btn-danger    { background: #dc2626; color: #fff; }
.btn-secondary { background: #e2e8f0; color: #0f172a; }
.btn:disabled  { opacity: .45; cursor: not-allowed; filter: none; }
/* Form grid */
.fg {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1rem; margin-bottom: 1rem;
}
.f { display: flex; flex-direction: column; gap: .3rem; }
.f label { font-size: .8rem; font-weight: 500; color: #374151; }
.f input, .f select {
  padding: .42rem .6rem; border: 1px solid #d1d5db;
  border-radius: .35rem; font-size: .85rem; width: 100%;
  outline: none; background: #fff;
}
.f input:focus, .f select:focus {
  border-color: #2563eb; box-shadow: 0 0 0 2px rgba(37,99,235,.15);
}
.f .hint { font-size: .72rem; color: #6b7280; }
.full { grid-column: 1 / -1; }
/* Password input with toggle */
.pw { position: relative; }
.pw input { padding-right: 2.4rem; }
.pw button {
  position: absolute; right: .4rem; top: 50%; transform: translateY(-50%);
  background: none; border: none; cursor: pointer;
  color: #6b7280; font-size: .75rem; padding: 0;
}
/* Settings table */
.settings-tbl td:first-child { font-weight: 500; white-space: nowrap; width: 200px; }
.settings-tbl td:nth-child(2) { color: #6b7280; font-size: .8rem; width: 240px; }
.settings-tbl input {
  width: 100%; padding: .38rem .55rem;
  border: 1px solid #d1d5db; border-radius: .35rem;
  font-size: .83rem; outline: none;
}
.settings-tbl input:focus { border-color: #2563eb; }
"""

_JS = r"""
// Password show/hide toggle
document.querySelectorAll('.pw button').forEach(btn => {
  btn.addEventListener('click', () => {
    const inp = btn.previousElementSibling;
    inp.type = inp.type === 'password' ? 'text' : 'password';
    btn.textContent = inp.type === 'password' ? '\uD83D\uDC41' : '\uD83D\uDE48';
  });
});

// Auto-generate slug from title
const titleEl = document.getElementById('title');
const slugEl  = document.getElementById('slug');
if (titleEl && slugEl) {
  titleEl.addEventListener('input', () => {
    if (!slugEl.dataset.m) {
      slugEl.value = titleEl.value.toLowerCase()
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9 -]/g, '').trim()
        .replace(/\s+/g, '-').replace(/-+/g, '-')
        .replace(/^-+|-+$/g, '');
    }
  });
  slugEl.addEventListener('input', () => { slugEl.dataset.m = '1'; });
}
"""


def _esc(text: str) -> str:
    """HTML-escape a string for safe inclusion in HTML attributes and text."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _page(
    title: str,
    body: str,
    active: str,
    msg: str = "",
    msg_type: str = "success",
) -> HTMLResponse:
    alert_html = (
        f'<div class="alert alert-{_esc(msg_type)}">{_esc(msg)}</div>' if msg else ""
    )
    nav_items = [
        ("📊 Dashboard", "/", "dash"),
        ("📚 Daftar Buku", "/books", "books"),
        ("➕ Tambah Buku", "/books/add", "add"),
        ("⚙️ Pengaturan", "/settings", "settings"),
    ]
    nav_html = "".join(
        f'<a href="{href}" class="{"active" if nid == active else ""}">{label}</a>'
        for label, href, nid in nav_items
    )
    return HTMLResponse(
        f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{_esc(title)} · Kupas Admin</title>
  <style>{_CSS}</style>
</head>
<body>
  <aside class="sidebar">
    <div class="brand">🔐 <span>Kupas</span> Admin</div>
    <nav>{nav_html}</nav>
    <div class="footer">Kupas Admin v0.1.0</div>
  </aside>
  <div class="main">
    <div class="topbar"><h1>{_esc(title)}</h1></div>
    <div class="content">{alert_html}{body}</div>
  </div>
  <script>{_JS}</script>
</body>
</html>"""
    )


def _redirect(url: str, msg: str = "", msg_type: str = "success") -> RedirectResponse:
    if msg:
        params = urlencode({"msg": msg, "type": msg_type})
        url = f"{url}?{params}"
    return RedirectResponse(url, status_code=303)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    _: Auth,
    msg: str = "",
    msg_type: str = Query(default="success", alias="type"),
) -> HTMLResponse:
    async with get_session() as session:
        total = (
            await session.execute(select(func.count()).select_from(Book))
        ).scalar_one()
        pdfs = (
            await session.execute(
                select(func.count()).select_from(Book).where(Book.pdf_path.isnot(None))
            )
        ).scalar_one()
        chapters = (
            await session.execute(select(func.count()).select_from(Chapter))
        ).scalar_one()
        extracted = (
            await session.execute(
                select(func.count(func.distinct(Chapter.book_id)))
            )
        ).scalar_one()

    body = f"""
    <div class="stats">
      <div class="stat"><div class="val">{total}</div><div class="lbl">Total Buku</div></div>
      <div class="stat"><div class="val">{pdfs}</div><div class="lbl">PDF Tersimpan</div></div>
      <div class="stat"><div class="val">{total - pdfs}</div><div class="lbl">PDF Belum Ada</div></div>
      <div class="stat"><div class="val">{chapters}</div><div class="lbl">Total Chapter</div></div>
      <div class="stat"><div class="val">{extracted}</div><div class="lbl">Buku Terekstrak</div></div>
    </div>
    <div class="card">
      <div class="card-title">Aksi Cepat</div>
      <a href="/books/add" class="btn btn-primary">➕ Tambah Buku</a>
      &nbsp;&nbsp;
      <a href="/books" class="btn btn-secondary">📚 Daftar Buku</a>
      &nbsp;&nbsp;
      <a href="/settings" class="btn btn-secondary">⚙️ Pengaturan</a>
    </div>"""
    return _page("Dashboard", body, "dash", msg, msg_type)


# ---------------------------------------------------------------------------
# Book list
# ---------------------------------------------------------------------------


@app.get("/books", response_class=HTMLResponse)
async def book_list(
    _: Auth,
    msg: str = "",
    msg_type: str = Query(default="success", alias="type"),
) -> HTMLResponse:
    async with get_session() as session:
        books_result = await session.execute(select(Book).order_by(Book.title))
        books = books_result.scalars().all()

        counts_result = await session.execute(
            select(Chapter.book_id, func.count(Chapter.id)).group_by(Chapter.book_id)
        )
        ch_count: dict[int, int] = dict(counts_result.all())

    rows = ""
    for b in books:
        slug = _esc(b.slug)
        title = _esc(b.title or "—")
        author = _esc(b.author or "—")
        grade = _esc(b.grade or "—")
        subject = _esc(b.subject or "—")
        pdf_ok = bool(b.pdf_path and Path(b.pdf_path).exists())
        pdf_badge = (
            '<span class="badge ok">✓ Ada</span>'
            if pdf_ok
            else '<span class="badge no">✗ Belum</span>'
        )
        ch = ch_count.get(b.id, 0)
        ch_badge = (
            f'<span class="badge ok">{ch} chapter</span>'
            if ch > 0
            else '<span class="badge no">Belum</span>'
        )
        dl_disabled = 'disabled title="PDF sudah ada"' if pdf_ok else ""
        rows += f"""<tr>
          <td><a href="/books/{slug}" style="color:#2563eb;text-decoration:none">{title}</a></td>
          <td>{author}</td>
          <td>{grade}</td>
          <td>{subject}</td>
          <td>{pdf_badge}</td>
          <td>{ch_badge}</td>
          <td style="white-space:nowrap">
            <form method="post" action="/books/{slug}/download" style="display:inline">
              <button class="btn btn-warning" type="submit" {dl_disabled}>⬇ PDF</button>
            </form>
            <form method="post" action="/books/{slug}/extract" style="display:inline">
              <button class="btn btn-success" type="submit">🔍 Ekstrak</button>
            </form>
            <form method="post" action="/books/{slug}/delete" style="display:inline"
                  onsubmit="return confirm('Yakin hapus buku ini?')">
              <button class="btn btn-danger" type="submit">🗑</button>
            </form>
          </td>
        </tr>"""

    empty_row = (
        '<tr><td colspan="7" style="text-align:center;padding:2rem;color:#94a3b8">'
        'Belum ada buku. <a href="/books/add">Tambah sekarang →</a></td></tr>'
    )
    body = f"""
    <div style="margin-bottom:1rem">
      <a href="/books/add" class="btn btn-primary">➕ Tambah Buku</a>
    </div>
    <div class="card">
      <div class="tbl-wrap">
        <table>
          <thead>
            <tr>
              <th>Judul</th><th>Penulis</th><th>Kelas</th><th>Mapel</th>
              <th>PDF</th><th>Chapter</th><th>Aksi</th>
            </tr>
          </thead>
          <tbody>{rows if rows else empty_row}</tbody>
        </table>
      </div>
    </div>"""
    return _page("Daftar Buku", body, "books", msg, msg_type)


# ---------------------------------------------------------------------------
# Book detail (read-only view)
# ---------------------------------------------------------------------------

# NOTE: this route must be defined AFTER /books/add to avoid slug="add" conflict.


@app.get("/books/add", response_class=HTMLResponse)
async def add_book_form(
    _: Auth,
    msg: str = "",
    msg_type: str = Query(default="success", alias="type"),
) -> HTMLResponse:
    grades = [
        "", "SD Kelas 1", "SD Kelas 2", "SD Kelas 3",
        "SD Kelas 4", "SD Kelas 5", "SD Kelas 6",
        "SMP Kelas 7", "SMP Kelas 8", "SMP Kelas 9",
        "SMA Kelas 10", "SMA Kelas 11", "SMA Kelas 12",
    ]
    grade_opts = "".join(
        f'<option value="{g}">{g or "— Pilih Kelas —"}</option>' for g in grades
    )
    body = f"""
    <div class="card">
      <div class="card-title">Tambah Buku Manual</div>
      <form method="post" action="/books">
        <div class="fg">
          <div class="f full">
            <label for="title">Judul Buku *</label>
            <input id="title" name="title" required placeholder="mis. Matematika Kelas 7">
          </div>
          <div class="f full">
            <label for="slug">Slug (ID Unik) *</label>
            <input id="slug" name="slug" required placeholder="otomatis dari judul">
            <span class="hint">Hanya huruf kecil, angka, dan tanda hubung. Diisi otomatis dari judul.</span>
          </div>
          <div class="f">
            <label for="author">Penulis</label>
            <input id="author" name="author" placeholder="mis. Kemendikdasmen">
          </div>
          <div class="f">
            <label for="grade">Kelas</label>
            <select id="grade" name="grade">{grade_opts}</select>
          </div>
          <div class="f">
            <label for="subject">Mata Pelajaran</label>
            <input id="subject" name="subject" placeholder="mis. Matematika">
          </div>
          <div class="f">
            <label for="cover_url">URL Cover (opsional)</label>
            <input id="cover_url" name="cover_url" type="url" placeholder="https://...">
          </div>
          <div class="f full">
            <label for="pdf_url">URL PDF Ebook *</label>
            <input id="pdf_url" name="pdf_url" type="url" required
                   placeholder="https://buku.kemdikbud.go.id/katalog/...">
            <span class="hint">
              Link langsung ke file PDF. Bisa dari domain mana saja
              (bukan IP lokal). Unduhan dimulai otomatis di background.
            </span>
          </div>
          <div class="f full">
            <label>
              <input type="checkbox" name="auto_download" value="1" checked>
              &nbsp;Unduh PDF otomatis setelah disimpan
            </label>
          </div>
        </div>
        <button class="btn btn-primary" type="submit">💾 Simpan Buku</button>
        &nbsp;&nbsp;
        <a href="/books" class="btn btn-secondary">Batal</a>
      </form>
    </div>"""
    return _page("Tambah Buku", body, "add", msg, msg_type)


@app.get("/books/{slug}", response_class=HTMLResponse)
async def book_detail(slug: str, _: Auth) -> HTMLResponse:
    async with get_session() as session:
        result = await session.execute(select(Book).where(Book.slug == slug))
        book = result.scalar_one_or_none()
        if book is None:
            raise HTTPException(404, "Buku tidak ditemukan.")

        chapters_result = await session.execute(
            select(Chapter)
            .where(Chapter.book_id == book.id)
            .order_by(Chapter.chapter_number)
        )
        chapters = chapters_result.scalars().all()

    pdf_info = (
        f'<span class="badge ok">✓ {_esc(book.pdf_path)}</span>'
        if book.pdf_path
        else '<span class="badge no">Belum diunduh</span>'
    )
    ch_rows = "".join(
        f"<tr><td>{ch.chapter_number}</td><td>{_esc(ch.title or '')}</td>"
        f"<td style='color:#64748b'>{len(ch.content or '')} karakter</td></tr>"
        for ch in chapters
    )
    ch_section = (
        '<div style="color:#94a3b8;text-align:center;padding:1rem">'
        "Belum ada chapter. Unduh PDF lalu klik Ekstrak.</div>"
        if not chapters
        else f'<div class="tbl-wrap"><table><thead><tr>'
        f"<th>#</th><th>Judul</th><th>Ukuran</th></tr>"
        f"</thead><tbody>{ch_rows}</tbody></table></div>"
    )
    pdf_url_cell = (
        f'<a href="{_esc(book.pdf_url)}" target="_blank" rel="noopener noreferrer">'
        f"{_esc(book.pdf_url)}</a>"
        if book.pdf_url and book.pdf_url.startswith(("http://", "https://"))
        else _esc(book.pdf_url or "—")
    )
    body = f"""
    <div class="card">
      <div class="card-title">{_esc(book.title or book.slug)}</div>
      <table class="settings-tbl">
        <tr><td>Slug</td><td><code>{_esc(book.slug)}</code></td></tr>
        <tr><td>Penulis</td><td>{_esc(book.author or '—')}</td></tr>
        <tr><td>Kelas</td><td>{_esc(book.grade or '—')}</td></tr>
        <tr><td>Mata Pelajaran</td><td>{_esc(book.subject or '—')}</td></tr>
        <tr><td>PDF URL</td><td>{pdf_url_cell}</td></tr>
        <tr><td>PDF Lokal</td><td>{pdf_info}</td></tr>
      </table>
    </div>
    <div class="card">
      <div class="card-title">Chapter ({len(chapters)})</div>
      {ch_section}
    </div>
    <div style="display:flex;gap:.75rem;align-items:center">
      <form method="post" action="/books/{_esc(book.slug)}/download" style="display:inline">
        <button class="btn btn-warning" type="submit">⬇ Unduh PDF</button>
      </form>
      <form method="post" action="/books/{_esc(book.slug)}/extract" style="display:inline">
        <button class="btn btn-success" type="submit">🔍 Ekstrak Chapter</button>
      </form>
      <a href="/books" class="btn btn-secondary">← Kembali</a>
    </div>"""
    return _page(f"Detail: {book.title or slug}", body, "books")


# ---------------------------------------------------------------------------
# Add book (POST)
# ---------------------------------------------------------------------------


@app.post("/books")
async def add_book(
    _: Auth,
    background_tasks: BackgroundTasks,
    title: Annotated[str, Form()],
    slug: Annotated[str, Form()],
    pdf_url: Annotated[str, Form()],
    author: Annotated[str, Form()] = "",
    grade: Annotated[str, Form()] = "",
    subject: Annotated[str, Form()] = "",
    cover_url: Annotated[str, Form()] = "",
    auto_download: Annotated[str, Form()] = "",
) -> RedirectResponse:
    slug = slug.strip().lower()

    if not re.fullmatch(r"[a-z0-9]([a-z0-9\-]*[a-z0-9])?", slug):
        return _redirect(
            "/books/add",
            "Slug tidak valid. Gunakan huruf kecil, angka, dan tanda hubung.",
            "error",
        )
    if slug in _RESERVED_SLUGS:
        return _redirect(
            "/books/add",
            f"Slug '{slug}' adalah kata yang dicadangkan. Pilih nama lain.",
            "error",
        )

    try:
        _validate_pdf_url(pdf_url)
    except ValueError as exc:
        return _redirect("/books/add", f"URL PDF tidak valid: {exc}", "error")

    async with get_session() as session:
        existing = (
            await session.execute(select(Book).where(Book.slug == slug))
        ).scalar_one_or_none()
        if existing:
            return _redirect(
                "/books/add", f"Slug '{slug}' sudah digunakan.", "error"
            )

        book = Book(
            slug=slug,
            title=title.strip() or None,
            author=author.strip() or None,
            subject=subject.strip() or None,
            grade=grade.strip() or None,
            cover_url=cover_url.strip() or None,
            pdf_url=pdf_url.strip(),
        )
        session.add(book)
        await session.commit()

    if auto_download == "1":
        background_tasks.add_task(_bg_download, slug)
        return _redirect(
            "/books",
            f"Buku '{slug}' disimpan. Unduhan PDF dimulai di background.",
            "success",
        )
    return _redirect("/books", f"Buku '{slug}' berhasil disimpan.", "success")


# ---------------------------------------------------------------------------
# Download PDF (POST)
# ---------------------------------------------------------------------------


@app.post("/books/{slug}/download")
async def trigger_download(
    slug: str, _: Auth, background_tasks: BackgroundTasks
) -> RedirectResponse:
    async with get_session() as session:
        book = (
            await session.execute(select(Book).where(Book.slug == slug))
        ).scalar_one_or_none()
        if book is None:
            return _redirect("/books", "Buku tidak ditemukan.", "error")
        if not book.pdf_url:
            return _redirect(
                "/books", f"Buku '{slug}' tidak memiliki URL PDF.", "error"
            )

    background_tasks.add_task(_bg_download, slug)
    return _redirect("/books", f"Unduhan PDF untuk '{slug}' dimulai.", "info")


# ---------------------------------------------------------------------------
# Extract chapters (POST)
# ---------------------------------------------------------------------------


@app.post("/books/{slug}/extract")
async def trigger_extract(
    slug: str, _: Auth, background_tasks: BackgroundTasks
) -> RedirectResponse:
    async with get_session() as session:
        book = (
            await session.execute(select(Book).where(Book.slug == slug))
        ).scalar_one_or_none()
        if book is None:
            return _redirect("/books", "Buku tidak ditemukan.", "error")
        if not book.pdf_path or not Path(book.pdf_path).exists():
            return _redirect(
                "/books", f"PDF untuk '{slug}' belum diunduh.", "error"
            )

    background_tasks.add_task(_bg_extract, slug)
    return _redirect(
        "/books", f"Ekstraksi chapter untuk '{slug}' dimulai.", "info"
    )


# ---------------------------------------------------------------------------
# Delete book (POST)
# ---------------------------------------------------------------------------


@app.post("/books/{slug}/delete")
async def delete_book(slug: str, _: Auth) -> RedirectResponse:
    async with get_session() as session:
        book = (
            await session.execute(select(Book).where(Book.slug == slug))
        ).scalar_one_or_none()
        if book is None:
            return _redirect("/books", "Buku tidak ditemukan.", "error")

        chapters = (
            await session.execute(
                select(Chapter).where(Chapter.book_id == book.id)
            )
        ).scalars().all()
        for ch in chapters:
            await session.delete(ch)
        await session.delete(book)
        await session.commit()

    return _redirect("/books", f"Buku '{slug}' berhasil dihapus.", "success")


# ---------------------------------------------------------------------------
# Settings — GET
# ---------------------------------------------------------------------------


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(
    _: Auth,
    msg: str = "",
    msg_type: str = Query(default="success", alias="type"),
) -> HTMLResponse:
    current = _read_env_file()

    rows = ""
    for key, label, sensitive in MANAGED_ENV_VARS:
        value = _esc(current.get(key, ""))
        input_type = "password" if sensitive else "text"
        toggle = '<button type="button">\U0001f441</button>' if sensitive else ""
        pw_cls = "pw" if sensitive else ""
        rows += f"""<tr>
          <td><code>{_esc(key)}</code></td>
          <td>{_esc(label)}</td>
          <td>
            <div class="{pw_cls}">
              <input type="{input_type}" name="{_esc(key)}" value="{value}"
                     autocomplete="off" spellcheck="false">
              {toggle}
            </div>
          </td>
        </tr>"""

    body = f"""
    <div class="alert alert-warning">
      ⚠️ Perubahan pada file <code>.env</code> akan aktif setelah aplikasi di-<strong>restart</strong>.
      Nilai yang dikosongkan tidak akan diubah (tetap menggunakan nilai lama).
    </div>
    <div class="card">
      <div class="card-title">Environment Variables — <code>{_esc(str(ENV_FILE_PATH))}</code></div>
      <form method="post" action="/settings">
        <div class="tbl-wrap">
          <table class="settings-tbl">
            <thead><tr><th>Key</th><th>Deskripsi</th><th>Nilai</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
        <div style="margin-top:1rem">
          <button class="btn btn-primary" type="submit">💾 Simpan ke .env</button>
        </div>
      </form>
    </div>"""
    return _page("Pengaturan", body, "settings", msg, msg_type)


# ---------------------------------------------------------------------------
# Settings — POST
# ---------------------------------------------------------------------------


@app.post("/settings")
async def save_settings(_: Auth, request: Request) -> RedirectResponse:
    form = await request.form()
    allowed_keys = {key for key, _, _ in MANAGED_ENV_VARS}
    current = _read_env_file()

    updates: dict[str, str] = {}
    for key in allowed_keys:
        raw = form.get(key, "")
        value = str(raw).strip() if raw else ""
        # Keep the existing value when the field is submitted blank
        updates[key] = value if value else current.get(key, "")

    try:
        _write_env_file(updates)
    except Exception as exc:
        return _redirect("/settings", f"Gagal menyimpan: {exc}", "error")

    return _redirect(
        "/settings",
        "Perubahan disimpan ke .env. Restart aplikasi untuk menerapkan.",
        "success",
    )
