import base64
import hashlib
import hmac
import json
import secrets
import time

from .config import settings


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


# --- Passwords (salted SHA-256; swap for argon2/bcrypt in production) ------

def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split(":", 1)
    except ValueError:
        return False
    candidate = hashlib.sha256((salt + password).encode()).hexdigest()
    return hmac.compare_digest(candidate, digest)


# --- JWT (HMAC-SHA256, no external dependency) -----------------------------

def create_jwt(payload: dict, expires_minutes: int | None = None) -> str:
    header = {"alg": settings.jwt_algorithm, "typ": "JWT"}
    body = dict(payload)
    now = int(time.time())
    body["iat"] = now
    body["exp"] = now + (expires_minutes or settings.token_expiry_minutes) * 60
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(body, separators=(",", ":")).encode())
    )
    signature = hmac.new(settings.jwt_secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + _b64url(signature)


def decode_jwt(token: str) -> dict | None:
    try:
        head, body, sig = token.split(".")
        signing_input = f"{head}.{body}"
        expected = hmac.new(settings.jwt_secret.encode(), signing_input.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig)):
            return None
        payload = json.loads(_b64url_decode(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def authenticate(authorization: str | None, roles: set[str]) -> dict | None:
    """Return the JWT payload if the bearer token is valid and role is allowed."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    payload = decode_jwt(token)
    if not payload or payload.get("role") not in roles:
        return None
    return payload


# --- OTP (simulated gateway; production would use SMS delivery) ------------

_otp_store: dict[str, tuple[str, float]] = {}
OTP_TTL_SECONDS = 300


def issue_otp(phone: str) -> str:
    code = f"{secrets.randbelow(10000):04d}"
    _otp_store[phone] = (code, time.time() + OTP_TTL_SECONDS)
    return code


def verify_otp(phone: str, code: str) -> bool:
    item = _otp_store.get(phone)
    if not item:
        return False
    expected, expiry = item
    if time.time() > expiry:
        _otp_store.pop(phone, None)
        return False
    if hmac.compare_digest(expected, (code or "").strip()):
        _otp_store.pop(phone, None)
        return True
    return False
