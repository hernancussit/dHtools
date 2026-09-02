import base64
import hmac
import hashlib
import struct
import time
import secrets
import urllib.parse

def generate_totp_secret() -> str:
    """Generates a 160-bit (20-byte) cryptographically secure Base32 secret."""
    return base64.b32encode(secrets.token_bytes(20)).decode("utf-8").replace("=", "")


def get_totp_code(secret: str, time_step: int = 30, t: float = None) -> str:
    """Generates a 6-digit TOTP code for the given timestamp (default: current time)."""
    if t is None:
        t = time.time()
    counter = int(t // time_step)
    clean_secret = secret.strip().replace(" ", "").upper()
    pad = len(clean_secret) % 8
    if pad:
        clean_secret += "=" * (8 - pad)
    key = base64.b32decode(clean_secret, casefold=True)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0f
    binary = (
        ((h[offset] & 0x7f) << 24)
        | ((h[offset + 1] & 0xff) << 16)
        | ((h[offset + 2] & 0xff) << 8)
        | (h[offset + 3] & 0xff)
    )
    code = binary % 1000000
    return f"{code:06d}"


def verify_totp_code(secret: str, code: str, window: int = 1) -> bool:
    """Verifies a 6-digit TOTP code within a +/- window of time steps (default: +/- 30s)."""
    if not secret or not code:
        return False
    clean_code = str(code).strip().replace(" ", "").replace("-", "")
    if len(clean_code) != 6 or not clean_code.isdigit():
        return False
    now = time.time()
    for w in range(-window, window + 1):
        if get_totp_code(secret, t=now + w * 30) == clean_code:
            return True
    return False


def generate_backup_codes(count: int = 8) -> list:
    """Generates a list of single-use backup recovery codes formatted like 'A1B2-C3D4'."""
    codes = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()
        formatted = f"{raw[:4]}-{raw[4:]}"
        codes.append(formatted)
    return codes


def get_totp_uri(username: str, secret: str, issuer: str = "dHtools") -> str:
    """Generates an otpauth:// URI for authenticator applications."""
    encoded_user = urllib.parse.quote(f"{issuer}:{username}")
    encoded_issuer = urllib.parse.quote(issuer)
    return f"otpauth://totp/{encoded_user}?secret={secret}&issuer={encoded_issuer}&algorithm=SHA1&digits=6&period=30"
