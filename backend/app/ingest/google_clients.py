"""The real Gmail and Drive clients, for the one Google account the app owns (decision 0025).

They run only in the smoke test and in a deployment with Google set up. The
credentials are an authorized-user file made once by `python -m app.ingest.google_auth`,
found through the `GOOGLE_TOKEN_FILE` environment variable. Nothing here prints them.

Gmail: the first check records the mailbox's current history ID, and later checks
read the messages added since, with `users.history.list`. If that history has
expired, the check falls back to the last week of the inbox, and the checker's
list of messages it has seen keeps them from arriving twice.
https://developers.google.com/workspace/gmail/api/guides/sync

Drive: the folder and the folders inside it are listed on every check with
`files.list`. Drive's change feed says it covers files shared with the account, but
its guide doesn't say a file added inside a shared folder always appears there, so
listing the folder is the reliable way.
https://developers.google.com/workspace/drive/api/guides/manage-changes
"""

import base64
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .sources import FOLDER, DriveEntry, RawMessage

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

_FALLBACK_QUERY = "in:inbox newer_than:7d"


def load_credentials(token_file: str | None = None) -> Credentials:
    path = token_file or os.environ.get("GOOGLE_TOKEN_FILE")
    if not path:
        raise RuntimeError("GOOGLE_TOKEN_FILE is not set")
    return Credentials.from_authorized_user_file(str(Path(path).expanduser()), SCOPES)


class GmailMailbox:
    def __init__(self, credentials: Credentials) -> None:
        self._gmail: Any = build("gmail", "v1", credentials=credentials, cache_discovery=False)

    def _users(self) -> Any:
        return self._gmail.users()

    def _history_id(self) -> str:
        return str(self._users().getProfile(userId="me").execute()["historyId"])

    def _raw(self, message_id: str) -> RawMessage | None:
        try:
            body = self._users().messages().get(userId="me", id=message_id, format="raw").execute()
        except HttpError as error:
            if error.resp.status == 404:
                return None  # deleted before it was read
            raise
        return RawMessage(message_id, base64.urlsafe_b64decode(body["raw"]))

    def _added_since(self, cursor: str) -> tuple[list[str], str]:
        ids: list[str] = []
        latest = cursor
        token = None
        while True:
            page = (
                self._users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=cursor,
                    historyTypes=["messageAdded"],
                    labelId="INBOX",
                    pageToken=token,
                )
                .execute()
            )
            for record in page.get("history", []):
                for added in record.get("messagesAdded", []):
                    ids.append(added["message"]["id"])
            latest = str(page.get("historyId", latest))
            token = page.get("nextPageToken")
            if not token:
                return ids, latest

    def _recent(self) -> list[str]:
        ids: list[str] = []
        token = None
        while True:
            page = (
                self._users()
                .messages()
                .list(userId="me", q=_FALLBACK_QUERY, pageToken=token)
                .execute()
            )
            ids.extend(m["id"] for m in page.get("messages", []))
            token = page.get("nextPageToken")
            if not token:
                return list(reversed(ids))  # oldest first

    def fetch_new(self, cursor: str | None) -> tuple[list[RawMessage], str]:
        if not cursor:
            return [], self._history_id()
        try:
            ids, latest = self._added_since(cursor)
        except HttpError as error:
            if error.resp.status != 404:
                raise
            ids, latest = self._recent(), self._history_id()  # the history expired
        messages = [m for m in (self._raw(i) for i in dict.fromkeys(ids)) if m is not None]
        return messages, latest


class GoogleDrive:
    def __init__(self, credentials: Credentials) -> None:
        self._drive: Any = build("drive", "v3", credentials=credentials, cache_discovery=False)

    def _children(self, folder_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        token = None
        while True:
            page = (
                self._drive.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime, md5Checksum)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    pageToken=token,
                )
                .execute()
            )
            items.extend(page.get("files", []))
            token = page.get("nextPageToken")
            if not token:
                return items

    def list_tree(self, folder_id: str) -> list[DriveEntry]:
        entries: list[DriveEntry] = []
        pending, seen = [folder_id], {folder_id}
        while pending:
            for item in self._children(pending.pop()):
                if item["mimeType"] == FOLDER:
                    if item["id"] not in seen:
                        seen.add(item["id"])
                        pending.append(item["id"])
                    continue
                if item["mimeType"] == "application/vnd.google-apps.shortcut":
                    continue  # a shortcut points elsewhere; the file itself isn't in the folder
                entries.append(
                    DriveEntry(
                        id=item["id"],
                        name=item["name"],
                        mime_type=item["mimeType"],
                        modified_time=datetime.fromisoformat(item["modifiedTime"]),
                        md5=item.get("md5Checksum"),
                    )
                )
        return entries

    def download(self, file_id: str) -> bytes:
        return self._drive.files().get_media(fileId=file_id, supportsAllDrives=True).execute()

    def export_pdf(self, file_id: str) -> bytes:
        # Drive limits an export to 10 MB:
        # https://developers.google.com/workspace/drive/api/reference/rest/v3/files/export
        return self._drive.files().export(fileId=file_id, mimeType="application/pdf").execute()
