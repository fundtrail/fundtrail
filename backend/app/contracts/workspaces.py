"""Users, workspaces and grants (docs/contracts.md section 11), and sample grants (issue 165)."""

from enum import StrEnum
from typing import Literal

from .base import Id, Model, Text, UtcDatetime


class User(Model):
    id: Id  # the Supabase auth user ID
    email: Text
    name: str | None = None


class MemberRole(StrEnum):
    """A workspace member's role (issue 160). What each role may do is defined once, in code."""

    OWNER = "owner"  # the person who signs in
    SAMPLE = "sample"  # the workspace's sample accountant, created with it, with no sign-in


class Workspace(Model):
    id: Id
    name: Text
    owner_id: Id
    # Deprecated (issue 165): each sample grant has its own clock (Grant.clock_now),
    # and the workspace clock goes away. Kept until the platform (W4) moves to the
    # grant's clock; then it's removed with its column.
    clock_now: UtcDatetime | None = None


class SampleChoice(StrEnum):
    """The sample grants a user can open, in the Add a grant dropdown's order."""

    SMALL_LIVE = "small_live"  # a small sample the agent reads live
    LARGER_LIVE = "larger_live"  # a larger sample the agent reads live; needs a confirm
    LARGER_PRERUN = "larger_prerun"  # a larger sample copied from a released prerun


class GrantSample(Model):
    """What a sample grant was opened from (issue 165)."""

    sample: Id  # the sample pack's ID, for example "nitrate-sensors"
    choice: SampleChoice
    opens_at: UtcDatetime  # the simulated date the sample opens on
    prerun_id: Id | None = None  # for larger_prerun: the prerun it was copied from


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
    # Issue 165: the grant's simulated "now". Set only on sample grants; None means
    # the real date. It replaces the workspace clock.
    clock_now: UtcDatetime | None = None
    sample: GrantSample | None = None  # set only on a sample grant
