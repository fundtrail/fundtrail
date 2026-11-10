"""Sign-in: verify the Supabase access token on each request and find the user.

The browser signs in with Supabase Auth (Google) and sends `Authorization: Bearer <token>`.
New Supabase projects sign user tokens with asymmetric keys, published as a JSON Web Key
Set (JWKS) at `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`. The backend fetches it,
caches it, and fetches it again when a token names a key ID (`kid`) it doesn't have, so a
key rotation needs no restart. Only an older project that still uses the shared JWT secret
sets SUPABASE_JWT_SECRET; then tokens are checked with HS256 against it instead.
The signature, the audience ("authenticated"), the issuer (the project's auth URL) and the
expiry are always checked.
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


def jwks_url(supabase_url: str) -> str:
    return f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


class SupabaseTokenVerifier:
    def __init__(
        self,
        supabase_url: str,
        *,
        jwt_secret: str | None = None,
        signing_key: Callable[[str], Any] | None = None,
        jwks_client: jwt.PyJWKClient | None = None,
    ):
        """`signing_key(token)` returns the key for a token. By default it comes from the
        project's JWKS through `jwks_client` (made here unless a test passes one): the key
        set is cached for five minutes and fetched again on a `kid` it doesn't have."""
        base = supabase_url.rstrip("/")
        self._issuer = f"{base}/auth/v1"
        self._secret = jwt_secret
        if signing_key is None and jwt_secret is None:
            client = jwks_client or jwt.PyJWKClient(
                jwks_url(supabase_url), cache_jwk_set=True, lifespan=300
            )
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
