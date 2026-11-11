"""CORS: an allowed origin gets the headers that let a browser call the API with the
user's token; any other origin gets none."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.cors import LOCAL_ORIGINS, AllowedOriginsRefused, add_cors, allowed_origins

APP_ORIGIN = "https://fundtrail.example"


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    add_cors(app, allowed_origins({"FUNDTRAIL_ALLOWED_ORIGINS": f"{APP_ORIGIN}/, "}))
    return TestClient(app)


def _preflight(client: TestClient, origin: str) -> dict[str, str]:
    response = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    return {k.lower(): v for k, v in response.headers.items()}


def test_an_allowed_origin_may_call_with_the_token() -> None:
    client = _client()
    headers = _preflight(client, APP_ORIGIN)
    assert headers["access-control-allow-origin"] == APP_ORIGIN
    assert "access-control-allow-credentials" not in headers  # a Bearer header, not a cookie
    assert "authorization" in headers["access-control-allow-headers"].lower()
    simple = client.get("/health", headers={"Origin": APP_ORIGIN})
    assert simple.headers["access-control-allow-origin"] == APP_ORIGIN


def test_another_origin_gets_no_headers() -> None:
    client = _client()
    assert "access-control-allow-origin" not in _preflight(client, "https://elsewhere.example")
    simple = client.get("/health", headers={"Origin": "https://elsewhere.example"})
    assert "access-control-allow-origin" not in simple.headers


def test_the_local_default_needs_a_local_supabase() -> None:
    assert allowed_origins({"SUPABASE_URL": "http://127.0.0.1:54321"}) == list(LOCAL_ORIGINS)
    assert allowed_origins({"SUPABASE_URL": "https://abc.supabase.co"}) == []
    assert allowed_origins({}) == []
    listed = {"FUNDTRAIL_ALLOWED_ORIGINS": "https://a.example, https://b.example/"}
    assert allowed_origins(listed | {"SUPABASE_URL": "http://localhost:54321"}) == [
        "https://a.example",
        "https://b.example",
    ]


def test_any_origin_is_refused() -> None:
    for value in ("*", "https://a.example, *"):
        with pytest.raises(AllowedOriginsRefused):
            allowed_origins({"FUNDTRAIL_ALLOWED_ORIGINS": value})
