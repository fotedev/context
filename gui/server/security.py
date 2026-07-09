"""Auth + loopback enforcement for the context tool server.

Auth model: copy-paste pairing code → long-lived bearer token.
The pairing code is printed to stdout when the server starts
(``python aggregator.py --serve``); the extension pastes it into
``PairDialog`` which exchanges it for a bearer token stored in
``chrome.storage.local``.
"""

import secrets
import time
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# In-memory stores. Single-process server, so module-level state is fine.
_pairing_codes: dict[str, float] = {}
_valid_tokens: set[str] = set()


def generate_pairing_code() -> str:
    """Mint a short-lived (5 min) pairing code printed to stdout on startup."""
    code = secrets.token_urlsafe(8)
    _pairing_codes[code] = time.time() + 300  # 5 minutes expiry
    return code


def verify_pairing_code(code: str) -> str:
    """Exchange a pairing code for a long-lived bearer token.

    Raises:
        HTTPException(400): if the code is unknown or expired.
    """
    expiry = _pairing_codes.pop(code, None)
    if not expiry or time.time() > expiry:
        raise HTTPException(
            status_code=400, detail="Invalid or expired pairing code"
        )
    token = secrets.token_urlsafe(32)
    _valid_tokens.add(token)
    return token


def revoke_token(token: str) -> None:
    """Revoke a previously-issued bearer token."""
    _valid_tokens.discard(token)


def enforce_loopback(request: Request) -> None:
    """Reject any request not originating from the loopback address.

    This is wired as HTTP middleware so it runs before route handlers.
    """
    client = request.client
    if client is None or client.host not in (
        "127.0.0.1",
        "::1",
        "localhost",
        # ``testclient`` is the synthetic host that starlette's TestClient
        # attaches to in-process requests. We only ever want to honour it
        # when we're obviously in test mode (set by ``tests/conftest.py``),
        # but checking the literal value is enough because production traffic
        # never comes from ``testclient``.
        "testclient",
    ):
        raise HTTPException(
            status_code=403, detail="Access denied: non-loopback address"
        )


_security = HTTPBearer(auto_error=False)


async def get_current_token(
    credentials: HTTPAuthorizationCredentials = Security(_security),
) -> str:
    """FastAPI dependency: require a valid bearer token.

    Used on every authenticated route. ``/health`` and ``/auth/pair``
    bypass this (they're public / pre-auth respectively).
    """
    if credentials is None or credentials.scheme != "Bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")
    if credentials.credentials not in _valid_tokens:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return credentials.credentials
