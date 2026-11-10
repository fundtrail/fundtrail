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
    # Decision 0025. The short random code after the plus sign in the grant's
    # address: the app's mailbox name, a plus sign and this code.
    address_code: str | None = None
    # The Drive folder the accountant shared and pasted the link of.
    drive_folder_id: str | None = None
