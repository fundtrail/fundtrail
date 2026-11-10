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


# The sign-in methods in a Supabase session token's `amr` claim that mean an email
# sign-in: a password, a one-time code or link, or an email invite, recovery or
# email-change link.
EMAIL_METHODS = frozenset(
    {"password", "otp", "magiclink", "email/signup", "email_change", "invite", "recovery"}
)


def _email_session(claims: dict[str, Any]) -> bool:
    """Whether this session was signed in by email. Read from the token's `amr` claim (the
    methods behind this session), not `app_metadata.provider`, which is only the method the
    user first signed up with."""
    amr = claims.get("amr") or []
    methods = {(m.get("method") if isinstance(m, dict) else m) for m in amr}  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    return bool(methods & EMAIL_METHODS)


def is_local(supabase_url: str) -> bool:
    """Whether the Supabase URL is a local development stack (the Supabase CLI's)."""
    from urllib.parse import urlparse

    host = (urlparse(supabase_url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost")


class DevEmailSignInRefused(RuntimeError):
    """FUNDTRAIL_DEV_EMAIL_SIGNIN is set for a Supabase project that isn't local."""


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
        allow_email_signin: bool = False,
    ):
        """`signing_key(token)` returns the key for a token. By default it comes from the
        project's JWKS through `jwks_client` (made here unless a test passes one): the key
        set is cached for five minutes and fetched again on a `kid` it doesn't have, at
        most once every 30 seconds (PyJWT's cooldown, which also stops made-up key IDs from
        fetching on every request). A token signed with a key rotated in during those 30
        seconds is refused until then; Supabase publishes a standby key before signing with
        it, so that's unlikely."""
        base = supabase_url.rstrip("/")
        self._issuer = f"{base}/auth/v1"
        # Email sign-in is for local development only: the app signs people in with Google.
        if allow_email_signin and not is_local(supabase_url):
            raise DevEmailSignInRefused(
                "FUNDTRAIL_DEV_EMAIL_SIGNIN is only for a local Supabase stack; "
                "unset it for this project."
            )
        self._allow_email = allow_email_signin
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
        if not self._allow_email and _email_session(claims):
            raise InvalidToken("email sign-in is only for local development")
        return _user(claims)
