"""
app.py
Flask web application for Kupas — download & study ebooks from
buku.kemendikdasmen.go.id.
"""

import os
import logging

from flask import Flask, flash, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

from kupas import download_ebook, generate_questions

app = Flask(__name__)

_secret_key = os.getenv("FLASK_SECRET_KEY", "")
if not _secret_key:
    logging.warning(
        "FLASK_SECRET_KEY is not set. Using an insecure default — set this variable in production."
    )
    _secret_key = "kupas-insecure-default-key"
app.secret_key = _secret_key

EBOOKS_DIR = os.getenv("EBOOKS_DIR", "ebooks")
os.makedirs(EBOOKS_DIR, exist_ok=True)


@app.route("/")
def index():
    ebooks = sorted(os.listdir(EBOOKS_DIR))
    return render_template("index.html", ebooks=ebooks)


@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url", "").strip()
    if not url:
        flash("URL tidak boleh kosong.", "danger")
        return redirect(url_for("index"))
    try:
        filename = download_ebook(url, EBOOKS_DIR)
        flash(f"Ebook berhasil diunduh: {filename}", "success")
    except Exception as exc:
        flash(f"Gagal mengunduh ebook: {exc}", "danger")
    return redirect(url_for("index"))


@app.route("/ebooks/<path:filename>")
def get_ebook(filename):
    safe = secure_filename(filename)
    return send_from_directory(EBOOKS_DIR, safe)


@app.route("/generate", methods=["POST"])
def generate():
    filename = request.form.get("ebook", "").strip()
    if not filename:
        flash("Pilih ebook terlebih dahulu.", "danger")
        return redirect(url_for("index"))

    safe = secure_filename(filename)
    ebook_path = os.path.join(EBOOKS_DIR, safe)

    if not os.path.isfile(ebook_path):
        flash("File ebook tidak ditemukan.", "danger")
        return redirect(url_for("index"))

    try:
        questions = generate_questions(ebook_path)
        return render_template("questions.html", questions=questions, ebook=safe)
    except Exception as exc:
        flash(f"Gagal generate soal: {exc}", "danger")
        return redirect(url_for("index"))


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
    app.run(debug=debug, host="0.0.0.0", port=8000)
