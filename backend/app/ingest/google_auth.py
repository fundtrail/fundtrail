"""One-time OAuth (Open Authorization) sign-in for the app's own Google account.

    uv run python -m app.ingest.google_auth CLIENT_SECRET_JSON TOKEN_FILE

Opens a browser to sign in as the app's account and writes the authorized-user file
to TOKEN_FILE, readable only by you. Keep TOKEN_FILE outside the repo and point
`GOOGLE_TOKEN_FILE` at it. Nothing secret is printed.
"""

import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from .google_clients import SCOPES


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    client_secret, token_file = Path(argv[0]).expanduser(), Path(argv[1]).expanduser()
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    credentials = flow.run_local_server(port=0)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(token_file, 0o600)  # os.open's mode applies only to a new file
    with os.fdopen(fd, "w") as out:
        out.write(credentials.to_json())  # type: ignore[union-attr]
    print(f"Wrote the token file to {token_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
