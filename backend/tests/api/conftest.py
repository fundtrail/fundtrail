from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import router
from app.db.platform import Platform
from tests.db.platform_fixtures import (  # noqa: F401 - fixtures
    Signer,
    new_auth_user,
    platform,
    platform_database_url,
    signer,
)


@dataclass
class Api:
    client: TestClient
    platform: Platform
    user_id: str
    headers: dict[str, str]

    def as_other_user(self, tokens: Signer) -> dict[str, str]:
        other = new_auth_user(self.platform)
        return {"Authorization": f"Bearer {tokens.token(other, 'other@university.example')}"}


@pytest.fixture
def api(platform: Platform, signer: Signer) -> Iterator[Api]:  # noqa: F811 - fixtures
    app = FastAPI()
    app.include_router(router)
    app.state.platform = platform
    app.state.verifier = signer.verifier()
    user_id = new_auth_user(platform)
    headers = {"Authorization": f"Bearer {signer.token(user_id, 'pat@university.example')}"}
    with TestClient(app) as client:
        yield Api(client=client, platform=platform, user_id=user_id, headers=headers)
