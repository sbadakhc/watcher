"""
Authentication for Watcher.

Basic auth for review queue access + simple user registration/login.
Passwords are hashed with bcrypt. Reviewer credentials come from Vault.
"""

import hashlib
import secrets
from typing import Optional

from config import AUTH_PASSWORD, AUTH_USERNAME


# ---------------------------------------------------------------------------
# Password hashing (no bcrypt dependency, use PBKDF2)
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    """Hash password with PBKDF2-HMAC-SHA256."""
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"pbkdf2_sha256${salt}${hashed.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    """Verify password against stored hash."""
    try:
        parts = stored.split("$")
        if len(parts) != 3 or parts[0] != "pbkdf2_sha256":
            return False
        salt = parts[1]
        expected_hash = parts[2]
        actual_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
        return secrets.compare_digest(expected_hash, actual_hash)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Basic auth
# ---------------------------------------------------------------------------


def verify_basic_auth(username: str, password: str) -> bool:
    """Verify basic auth credentials against Vault-managed secrets.

    The platform provisions AUTH_PASSWORD as a plaintext secret; compare in
    constant time. A pbkdf2_sha256$... value is also accepted for operators
    who store a pre-hashed credential in Vault instead.
    """
    if not AUTH_PASSWORD:
        return False
    if username != AUTH_USERNAME:
        return False
    if AUTH_PASSWORD.startswith("pbkdf2_sha256$"):
        return _verify_password(password, AUTH_PASSWORD)
    return secrets.compare_digest(password.encode(), AUTH_PASSWORD.encode())


# ---------------------------------------------------------------------------
# User auth (for registration/login)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return _hash_password(password)


def check_password(password: str, stored: str) -> bool:
    return _verify_password(password, stored)
