import base64
import hashlib
import hmac
import json
import secrets
import time

def pairing_matches(candidate: str, expected: str) -> bool:
    return hmac.compare_digest(candidate.encode(), expected.encode())

def issue_token(device_id: str, secret: str, ttl_seconds: int = 60 * 60 * 24 * 7) -> str:
    payload = {"sub": device_id, "exp": int(time.time()) + ttl_seconds, "nonce": secrets.token_urlsafe(12)}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = hmac.new(secret.encode(), encoded, hashlib.sha256).digest()
    return encoded.decode() + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

def verify_token(token: str, secret: str) -> str:
    try:
        encoded, signed = token.split(".", 1)
        expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
        received = base64.urlsafe_b64decode(signed + "=" * (-len(signed) % 4))
        if not hmac.compare_digest(expected, received):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("expired")
        return str(payload["sub"])
    except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid device token") from exc
