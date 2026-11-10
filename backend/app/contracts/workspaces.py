"""Users, workspaces and grants (docs/contracts.md section 11)."""

from typing import Literal

from .base import Id, Model, Text, UtcDatetime


class User(Model):
    id: Id  # the Supabase auth user ID
    email: Text
    name: str | None = None


class Workspace(Model):
    id: Id
    name: Text
    owner_id: Id
    clock_now: UtcDatetime | None = None  # the workspace clock's "now"; None means the real date


class Grant(Model):
    id: Id
    workspace_id: Id
    funder: Literal["NSF"] = "NSF"  # the National Science Foundation (NSF) only for now
    # Empty until the award letter is read. The terms themselves are records.
    award_number: str | None = None
    title: str | None = None
