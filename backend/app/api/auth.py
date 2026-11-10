"""Sign-in: verify the Supabase access token on each request and find the user.

The browser signs in with Supabase Auth (Google) and sends `Authorization: Bearer <token>`.
The token is checked against the project's published signing keys (asymmetric JSON Web
Token signing keys), or against the legacy shared secret when SUPABASE_JWT_SECRET is set.
Its audience must be "authenticated" and its issuer the project's auth URL.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

import jwt

from app.contracts.workspaces import User

AUDIENCE = "authenticated"
ASYMMETRIC = ["ES256", "RS256", "EdDSA"]


class InvalidToken(Exception):
    pass


class TokenVerifier(Protocol):
    def verify(self, token: str, /) -> User: ...


def _user(claims: dict[str, Any]) -> User:
    sub, email = claims.get("sub"), claims.get("email")
    if not sub or not email:
        raise InvalidToken("the token names no user")
    metadata = claims.get("user_metadata") or {}
    name = metadata.get("full_name") or metadata.get("name")
    return User(id=str(sub), email=str(email), name=str(name) if name else None)


class SupabaseTokenVerifier:
    def __init__(
        self,
        supabase_url: str,
        *,
        jwt_secret: str | None = None,
        signing_key: Callable[[str], Any] | None = None,
    ):
        """`signing_key(token)` returns the key for a token; by default it's fetched from
        the project's JSON Web Key Set (JWKS) and cached."""
        base = supabase_url.rstrip("/")
        self._issuer = f"{base}/auth/v1"
        self._secret = jwt_secret
        if signing_key is None and jwt_secret is None:
            client = jwt.PyJWKClient(f"{self._issuer}/.well-known/jwks.json", cache_keys=True)
            signing_key = lambda token: client.get_signing_key_from_jwt(token).key  # noqa: E731
        self._signing_key = signing_key

    def verify(self, token: str, /) -> User:
        try:
            if self._secret is not None:
                key: Any = self._secret
                algorithms = ["HS256"]
            else:
                assert self._signing_key is not None
                key = self._signing_key(token)
                algorithms = ASYMMETRIC
            claims = jwt.decode(
                token,
                key,
                algorithms=algorithms,
                audience=AUDIENCE,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except (jwt.PyJWTError, ValueError) as error:
            raise InvalidToken(type(error).__name__) from error
        return _user(claims)
