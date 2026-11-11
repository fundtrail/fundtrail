from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.api.auth import InvalidToken, SupabaseTokenVerifier
from tests.api.conftest import Api
from tests.db.platform_fixtures import SUPABASE_URL, Signer


def test_a_good_token_names_the_user(signer: Signer) -> None:
    user = signer.verifier().verify(signer.token("u-1", "pat@university.example"))
    assert (user.id, user.email, user.name) == ("u-1", "pat@university.example", "Pat Example")


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"aud": "anon"},
        {"iss": "https://elsewhere.supabase.example/auth/v1"},
        {"sub": ""},
    ],
)
def test_a_bad_token_is_refused(signer: Signer, overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidToken):
        signer.verifier().verify(signer.token("u-1", "pat@university.example", **overrides))


def test_a_token_signed_by_another_key_is_refused(signer: Signer) -> None:
    other = Signer(ec.generate_private_key(ec.SECP256R1()))
    with pytest.raises(InvalidToken):
        signer.verifier().verify(other.token("u-1", "pat@university.example"))


def test_the_legacy_shared_secret_works_when_set() -> None:
    secret = "a-test-secret-that-is-long-enough-for-hs256"
    token = jwt.encode(
        {
            "sub": "u-2",
            "email": "sam@university.example",
            "aud": "authenticated",
            "iss": f"{SUPABASE_URL}/auth/v1",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        secret,
        algorithm="HS256",
    )
    assert SupabaseTokenVerifier(SUPABASE_URL, jwt_secret=secret).verify(token).id == "u-2"


def test_requests_without_a_good_token_get_401(api: Api) -> None:
    assert api.client.get("/workspaces").status_code == 401
    response = api.client.get("/workspaces", headers={"Authorization": "Bearer nonsense"})
    assert response.status_code == 401


def test_the_first_request_adds_the_user_and_their_workspace(api: Api) -> None:
    """Ruling 64: the first request makes the user's workspace, named after them, with its
    Sample accountant; a second request makes nothing more."""
    [workspace] = api.client.get("/workspaces", headers=api.headers).json()
    assert workspace["name"] == "Pat Example's workspace"
    assert workspace["owner_id"] == api.user_id
    assert api.client.get("/workspaces", headers=api.headers).json() == [workspace]
    with api.platform.pool.connection() as conn:
        roles = conn.execute(
            """select role from public.workspace_members where workspace_id = %s
               order by role""",
            (workspace["id"],),
        ).fetchall()
        assert [r["role"] for r in roles] == ["owner", "sample"]
    with api.platform.pool.connection() as conn:
        row = conn.execute("select email, name from public.users where id = %s", (api.user_id,))
        assert row.fetchone() == {"email": "pat@university.example", "name": "Pat Example"}


def test_anything_outside_the_users_workspaces_is_404(api: Api, signer: Signer) -> None:
    workspace = api.client.post("/workspaces", json={"name": "Lab"}, headers=api.headers).json()
    grant = api.client.post(
        f"/workspaces/{workspace['id']}/grants",
        files={"file": ("award_letter.txt", b"Award SYN-1", "text/plain")},
        headers=api.headers,
    ).json()
    other = api.as_other_user(signer)
    theirs = api.client.get("/workspaces", headers=other).json()
    assert [w["id"] for w in theirs if w["id"] == workspace["id"]] == []
    assert (
        api.client.post(
            f"/workspaces/{workspace['id']}/grants",
            files={"file": ("a.txt", b"x", "text/plain")},
            headers=other,
        ).status_code
        == 404
    )
    for path in ("records", "runs", "charges"):
        assert api.client.get(f"/grants/{grant['id']}/{path}", headers=other).status_code == 404
    assert api.client.get("/grants/no-such-grant/records", headers=api.headers).status_code == 404


def test_a_valid_token_for_a_user_supabase_no_longer_has_is_401(api: Api, signer: Signer) -> None:
    import uuid

    gone = str(uuid.uuid4())  # never in auth.users
    headers = {"Authorization": f"Bearer {signer.token(gone, 'gone@university.example')}"}
    assert api.client.get("/workspaces", headers=headers).status_code == 401


def test_settings_never_print_the_keys() -> None:
    from app.db.config import Settings

    settings = Settings(
        database_url="postgresql://u:db-password@host/db",
        supabase_service_role_key="service-role-secret",
        supabase_jwt_secret="jwt-secret",
    )
    shown = repr(settings)
    assert "service-role-secret" not in shown and "jwt-secret" not in shown
    assert "db-password" not in shown


def test_tokens_are_checked_against_the_projects_jwks_and_a_new_key_is_fetched() -> None:
    """A key rotation: a token signed with a key the cached set doesn't have makes the
    verifier fetch the set again, with no restart."""
    import json

    from jwt.algorithms import ECAlgorithm

    from app.api.auth import jwks_url

    first = ec.generate_private_key(ec.SECP256R1())
    second = ec.generate_private_key(ec.SECP256R1())

    def jwk(key: ec.EllipticCurvePrivateKey, kid: str) -> dict[str, object]:
        public = json.loads(ECAlgorithm.to_jwk(key.public_key()))
        return public | {"kid": kid, "alg": "ES256", "use": "sig"}

    published = {"keys": [jwk(first, "k1")]}
    fetches: list[str] = []

    class LocalJwks(jwt.PyJWKClient):
        def fetch_data(self) -> object:
            fetches.append(self.uri)
            return published

    client = LocalJwks(jwks_url(SUPABASE_URL), cooldown_duration=0)
    verifier = SupabaseTokenVerifier(SUPABASE_URL, jwks_client=client)

    def token(key: ec.EllipticCurvePrivateKey, kid: str) -> str:
        claims = {
            "sub": "u-3",
            "email": "sam@university.example",
            "aud": "authenticated",
            "iss": f"{SUPABASE_URL}/auth/v1",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        }
        return jwt.encode(claims, key, algorithm="ES256", headers={"kid": kid})

    assert verifier.verify(token(first, "k1")).id == "u-3"
    assert verifier.verify(token(first, "k1")).id == "u-3"
    assert fetches == [f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"]  # cached
    published["keys"].append(jwk(second, "k2"))
    assert verifier.verify(token(second, "k2")).id == "u-3"
    assert len(fetches) == 2  # fetched again for the new kid
    with pytest.raises(InvalidToken):
        verifier.verify(token(ec.generate_private_key(ec.SECP256R1()), "k3"))


def _amr(*methods: str) -> list[dict[str, object]]:
    return [{"method": m, "timestamp": 1700000000} for m in methods]


def test_email_sign_in_is_refused_unless_turned_on_for_a_local_stack(signer: Signer) -> None:
    """The session's own methods (`amr`) decide, not the method the user first signed up with."""
    from app.api.auth import DevEmailSignInRefused

    # Signed up with Google, then signed in with a password: an email session, refused.
    password = signer.token(
        "u-4", "dev@university.example", app_metadata={"provider": "google"}, amr=_amr("password")
    )
    with pytest.raises(InvalidToken):
        signer.verifier().verify(password)
    # Signed up by email, then signed in with Google: a Google session, accepted.
    oauth = signer.token(
        "u-5", "pat@university.example", app_metadata={"provider": "email"}, amr=_amr("oauth")
    )
    assert signer.verifier().verify(oauth).id == "u-5"
    # On a local stack with the flag on, an email session is accepted.
    public = signer.key.public_key()
    local = SupabaseTokenVerifier(
        "http://127.0.0.1:54321", signing_key=lambda _t: public, allow_email_signin=True
    )
    local_token = jwt.encode(
        {
            "sub": "u-4",
            "email": "dev@university.example",
            "aud": "authenticated",
            "iss": "http://127.0.0.1:54321/auth/v1",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "amr": _amr("otp"),
        },
        signer.key,
        algorithm="ES256",
    )
    assert local.verify(local_token).id == "u-4"
    with pytest.raises(DevEmailSignInRefused):
        SupabaseTokenVerifier(SUPABASE_URL, allow_email_signin=True)


def test_the_server_refuses_to_start_with_tracing_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.agent import TracingTurnedOn
    from app.api import lifespan

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    app = FastAPI(lifespan=lifespan)
    with pytest.raises(TracingTurnedOn), TestClient(app):
        pass
