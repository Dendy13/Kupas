"""
kupas/config.py
Centralized configuration — single source of truth for all env vars.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/kupas")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
GCP_REGION: str = os.getenv("GCP_REGION", "asia-southeast1")
CATALOG_API_URL: str = os.getenv("CATALOG_API_URL", "https://api.buku.cloudapp.web.id/getPenggerakTextBooks")
DETAIL_API_URL: str = os.getenv("DETAIL_API_URL", "https://api.buku.cloudapp.web.id/getDetails")
PDF_STORAGE_DIR: Path = Path(os.getenv("PDF_STORAGE_DIR", "kupas/storage/pdf"))
ADMIN_USER: str = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "changeme")
ENV_FILE_PATH: Path = Path(os.path.abspath(os.getenv("ENV_FILE_PATH", ".env")))

_raw_cors = os.getenv("ADMIN_CORS_ORIGINS", "")
ADMIN_CORS_ORIGINS: list[str] = [o.strip() for o in _raw_cors.split(",") if o.strip()]

_raw_api_keys = os.getenv("API_KEYS", "")
VALID_API_KEYS: set[str] = {k.strip() for k in _raw_api_keys.split(",") if k.strip()}

_raw_origins = os.getenv("ALLOWED_ORIGINS", "https://kupas.dendyfajark.page")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# Ollama / Qwen
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434/v1")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
USE_OLLAMA: bool = os.getenv("USE_OLLAMA", "true").lower() == "true"
OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "120"))
