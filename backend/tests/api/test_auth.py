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


def test_the_first_request_adds_the_user(api: Api) -> None:
    assert api.client.get("/workspaces", headers=api.headers).json() == []
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
    assert api.client.get("/workspaces", headers=other).json() == []
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
