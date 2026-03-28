"""
kupas/__init__.py
Core helpers used by the Flask web app.
"""

import os
import re
from urllib.parse import urlparse

import requests
import pdfplumber

_ALLOWED_HOSTS = {
    "buku.kemendikdasmen.go.id",
    "buku.kemdikbud.go.id",
    "api.buku.cloudapp.web.id",
}


def _validate_url(url: str):
    """Raise ValueError if the URL is not from an allowed host. Returns the parsed URL."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL harus menggunakan skema http atau https.")
    host = parsed.hostname or ""
    if not any(host == allowed or host.endswith("." + allowed) for allowed in _ALLOWED_HOSTS):
        raise ValueError(
            f"URL tidak diizinkan. Domain harus salah satu dari: {', '.join(sorted(_ALLOWED_HOSTS))}"
        )
    return parsed


def download_ebook(url: str, output_dir: str) -> str:
    """
    Download a PDF from *url* and save it to *output_dir*.

    Returns the filename of the saved file.
    Raises an exception if the download fails or the response is not a PDF.
    """
    parsed = _validate_url(url)
    # Reconstruct the URL from validated components to prevent SSRF
    safe_url = parsed.geturl()
    response = requests.get(safe_url, allow_redirects=True, timeout=60)
    if response.status_code != 200:
        raise Exception("Gagal mengunduh ebook: status code %s" % response.status_code)

    # Derive filename from URL path, fall back to ebook.pdf
    filename = parsed.path.rstrip("/").split("/")[-1] or "ebook.pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "wb") as fh:
        fh.write(response.content)
    return filename


def generate_questions(ebook_path: str) -> list[str]:
    """
    Generate practice questions from a PDF ebook.

    If GEMINI_API_KEY is set the questions are produced by Google Gemini.
    Otherwise a fixed set of fallback questions is returned.
    """
    # Extract text from the first ~30 pages to stay within token limits
    pages_text: list[str] = []
    try:
        with pdfplumber.open(ebook_path) as pdf:
            for page in pdf.pages[:30]:
                text = page.extract_text() or ""
                if text.strip():
                    pages_text.append(text)
    except Exception as exc:
        raise Exception("Gagal membaca PDF: %s" % exc) from exc

    combined_text = "\n\n".join(pages_text)[:12000]  # cap to ~12 k chars

    api_key = os.getenv("GEMINI_API_KEY", "")
    if api_key:
        return _generate_with_gemini(combined_text, api_key)

    # Fallback: simple generic questions
    return [
        "Apa topik utama yang dibahas dalam ebook ini?",
        "Tuliskan ringkasan singkat isi ebook ini.",
        "Sebutkan 3 konsep penting yang kamu pelajari dari ebook ini.",
        "Bagaimana ebook ini dapat diterapkan dalam kehidupan sehari-hari?",
        "Apa kesimpulan yang dapat diambil dari ebook ini?",
    ]


def _generate_with_gemini(text: str, api_key: str) -> list[str]:
    """Call the Gemini API and return a list of question strings."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-pro")
    model = genai.GenerativeModel(model_name)

    prompt = (
        "Berdasarkan teks berikut dari sebuah ebook:\n\n"
        f"{text}\n\n"
        "Buatkan 10 soal latihan pilihan ganda berbahasa Indonesia "
        "beserta kunci jawabannya. Format setiap soal dengan nomor dan "
        "pilihan jawaban A–D."
    )

    response = model.generate_content(prompt)
    raw: str = response.text.strip()

    # Split on numbered items (1. / 1) / 1 )
    questions = [q.strip() for q in re.split(r"\n(?=\d+[\.\)])", raw) if q.strip()]
    return questions if questions else [raw]
