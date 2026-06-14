"""
Configuration module for Watcher Moderation Service.

Reads settings from environment variables and Vault secrets mounted at /run/secrets.
All secrets are read at import time; failures are fatal.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Secret helpers
# ---------------------------------------------------------------------------


# Security: support DB_PASSWORD_FILE and AUTH_PASSWORD_FILE env vars
# (used when password is mounted from Vault secrets via Docker Compose)
DB_PASSWORD_FILE = os.getenv("DB_PASSWORD_FILE", "")
AUTH_PASSWORD_FILE = os.getenv("AUTH_PASSWORD_FILE", "")

def _read_secret(name: str, default: str = "") -> str:
    """Read a secret from the Vault shared volume, or fall back to env var."""
    secret_path = Path(f"/run/secrets/{name}")
    if secret_path.exists():
        return secret_path.read_text().strip()
    return os.getenv(name.upper().replace("-", "_"), default)


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
# Model names are case-sensitive in Ollama; must match 'ollama list' output exactly
# qwen2.5:7b provides much better JSON reliability than qwen3:4B for structured output
TEXT_MODEL = os.getenv("TEXT_MODEL", "qwen2.5:7b")
VISION_MODEL = os.getenv("VISION_MODEL", "qwen2.5vl:3b")

# ---------------------------------------------------------------------------
# PostgreSQL (dedicated watcher database, public schema)
# ---------------------------------------------------------------------------

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "watcher")
DB_USER = os.getenv("DB_USER", "watcher")
# Try file path first, then Vault secret, then direct env var
if DB_PASSWORD_FILE and Path(DB_PASSWORD_FILE).exists():
    DB_PASSWORD = Path(DB_PASSWORD_FILE).read_text().strip()
else:
    DB_PASSWORD = _read_secret("watcher-db-password")
    if not DB_PASSWORD:
        DB_PASSWORD = os.getenv("DB_PASSWORD", "")

AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")

if AUTH_PASSWORD_FILE and Path(AUTH_PASSWORD_FILE).exists():
    AUTH_PASSWORD = Path(AUTH_PASSWORD_FILE).read_text().strip()
else:
    AUTH_PASSWORD = _read_secret("watcher-auth-password")
    if not AUTH_PASSWORD:
        AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")

# Pre-seeded user accounts (for demo — no registration)
USER_PASSWORD = _read_secret("watcher-user-password")
if not USER_PASSWORD:
    USER_PASSWORD = os.getenv("USER_PASSWORD", "")

ADMIN_PASSWORD = _read_secret("watcher-admin-password")
if not ADMIN_PASSWORD:
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

PORT = int(os.getenv("PORT", "9104"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
AUTO_APPROVE_THRESHOLD = float(os.getenv("AUTO_APPROVE_THRESHOLD", "0.95"))
REVIEW_THRESHOLD = float(os.getenv("REVIEW_THRESHOLD", "0.70"))

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate() -> None:
    """Raise ValueError if critical configuration is missing."""
    missing: list[str] = []
    if not DB_PASSWORD:
        missing.append("DB_PASSWORD or /run/secrets/watcher-db-password")
    if not AUTH_PASSWORD:
        missing.append("AUTH_PASSWORD or /run/secrets/watcher-auth-password")
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
