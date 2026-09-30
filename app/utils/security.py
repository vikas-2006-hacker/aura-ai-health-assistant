from __future__ import annotations

from passlib.context import CryptContext

# Use a secure PBKDF2-based scheme to avoid native bcrypt backend issues
# (works reliably across platforms and Python versions).
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return a secure hash for the provided plaintext password."""
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against the stored hash."""
    return pwd_context.verify(password, password_hash)
