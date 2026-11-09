"""Users, workspaces and grants."""

from typing import Literal

from pydantic import AwareDatetime

from .base import Model


class User(Model):
    id: str  # the Supabase auth user ID
    email: str
    name: str | None = None


class Workspace(Model):
    id: str
    name: str
    owner_id: str
    # The workspace clock's "now". None means the workspace runs on the real date.
    clock_now: AwareDatetime | None = None
    created_at: AwareDatetime


class Grant(Model):
    id: str
    workspace_id: str
    funder: Literal["NSF"] = "NSF"  # only NSF for now; more funders get added here
    # Filled in from the award letter once it's read. The terms themselves are records.
    award_number: str | None = None
    title: str | None = None
    created_at: AwareDatetime
