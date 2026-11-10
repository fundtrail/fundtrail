"""Supabase Storage and Realtime over their HTTP APIs, with the service role key.

The key never leaves the backend and is never logged.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from app.contracts.evidence import STORAGE_BUCKET

log = logging.getLogger(__name__)


def _headers(key: str) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {key}"}


class SupabaseStorage:
    """The private bucket the originals live in (contracts.md section 7)."""

    def __init__(self, url: str, service_role_key: str, bucket: str = STORAGE_BUCKET):
        self._base = f"{url.rstrip('/')}/storage/v1"
        self._bucket = bucket
        self._client = httpx.Client(headers=_headers(service_role_key), timeout=60)

    def _object(self, kind: str, path: str) -> str:
        return f"{self._base}/{kind}/{self._bucket}/{quote(path, safe='/')}"

    def put(self, path: str, data: bytes, media_type: str, /) -> None:
        response = self._client.post(
            self._object("object", path),
            content=data,
            headers={"Content-Type": media_type, "x-upsert": "false"},
        )
        response.raise_for_status()

    def get(self, path: str, /) -> bytes:
        response = self._client.get(self._object("object/authenticated", path))
        response.raise_for_status()
        return response.content

    def signed_url(self, path: str, expires_in: int, /) -> str:
        response = self._client.post(
            self._object("object/sign", path), json={"expiresIn": expires_in}
        )
        response.raise_for_status()
        return f"{self._base}{response.json()['signedURL']}"


class SupabasePinger:
    """A "something changed" message on a private Realtime channel. Supabase doesn't
    promise delivery, so a failed ping is logged and dropped; the screen refetches when
    it connects or reconnects."""

    def __init__(self, url: str, service_role_key: str):
        self._endpoint = f"{url.rstrip('/')}/realtime/v1/api/broadcast"
        self._client = httpx.Client(headers=_headers(service_role_key), timeout=5)

    def ping(self, topic: str, event: str, payload: dict[str, Any], /) -> None:
        message = {"topic": topic, "event": event, "payload": payload, "private": True}
        try:
            self._client.post(self._endpoint, json={"messages": [message]}).raise_for_status()
        except httpx.HTTPError as error:
            log.warning("ping %s %s not sent: %s", topic, event, type(error).__name__)
