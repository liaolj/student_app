from __future__ import annotations

import hashlib
import os
import secrets


def _salt_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 390000)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    hashed = _salt_password(password, salt)
    return f"{salt.hex()}${hashed.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(hash_hex)
    return secrets.compare_digest(_salt_password(password, salt), expected)


def generate_random_password(length: int = 12) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789@#%&"
    return "".join(secrets.choice(alphabet) for _ in range(length))
