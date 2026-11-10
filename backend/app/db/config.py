"""Settings the platform reads from the environment."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    # Postgres. On Supabase this is the session pooler's connection string (port 5432 on
    # the pooler host): it works over IPv4 and keeps LISTEN/NOTIFY, which the job worker uses.
    database_url: str = field(repr=False)  # it carries the database password
    # The Supabase project URL, for token keys, Storage and Realtime pings.
    supabase_url: str | None = None
    # The service role key: Storage and Realtime calls from the backend only.
    supabase_service_role_key: str | None = field(default=None, repr=False)
    # Only for a project still on the legacy shared JWT secret. Without it, tokens are
    # checked against the project's published signing keys.
    supabase_jwt_secret: str | None = field(default=None, repr=False)
    # How many grants the worker runs at once. Runs for one grant always go one at a time.
    worker_concurrency: int = 2
    # "inline" runs the job worker inside the API process; "off" leaves it to its own process.
    worker_mode: str = "inline"
    # Local development only: accept tokens from Supabase's email sign-in, so the app runs
    # on a local stack with no Google credentials. Refused for a project that isn't local.
    dev_email_signin: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is not set")
        return cls(
            database_url=url,
            supabase_url=os.environ.get("SUPABASE_URL") or None,
            supabase_service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or None,
            supabase_jwt_secret=os.environ.get("SUPABASE_JWT_SECRET") or None,
            worker_concurrency=int(os.environ.get("WORKER_CONCURRENCY", "2")),
            worker_mode=os.environ.get("WORKER_MODE", "inline"),
            dev_email_signin=os.environ.get("FUNDTRAIL_DEV_EMAIL_SIGNIN", "") == "1",
        )
