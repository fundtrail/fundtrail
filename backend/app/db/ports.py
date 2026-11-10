"""The small interfaces the platform calls, so other areas plug in and tests fake them.

- `Checks`: W2's pure checks (backend/app/checks/), plus the account groups table (#20).
- `Agent`: W1's agent (backend/app/agent/). It gets a run's inputs and returns what to save,
  or raises. It never touches the database.
- `Storage`: the private Supabase Storage bucket for originals.
- `Pinger`: the "something changed" ping on Supabase Realtime.

The default implementations import the other areas lazily, so this module loads before
they exist. Tests pass fakes instead.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.contracts.charges import Charge
from app.contracts.checks import ChecksInput, ChecksOutput, OpenQuestion, RunChecks
from app.contracts.evidence import EvidenceFile
from app.contracts.records import BudgetCategory, DefaultItem, DefaultItems, Record
from app.contracts.runs import AgentRun
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import Grant


class Checks(Protocol):
    """What the platform needs from the checks (W2) and the account groups table (#20)."""

    def run_checks(self, checks_input: ChecksInput, /) -> ChecksOutput: ...

    def default_items(self, charge: Charge, records: Sequence[Record], /) -> Sequence[DefaultItem]:
        """A charge's default checklist items, for the write check."""
        ...

    def account_categories(self, account: str, /) -> Sequence[BudgetCategory]:
        """The NSF budget categories of the ledger account's group, or none for an account
        in no group."""
        ...


def _not_yet(module: str, name: str, issue: str) -> Callable[..., Any]:
    """`module.name` from another area, or a clear error naming the issue that delivers it."""
    found = getattr(importlib.import_module(module), name, None)
    if found is None:
        raise NotImplementedError(f"{module}.{name} isn't on main yet ({issue})")
    return found


class ModuleChecks:
    """The real checks.

    - `account_categories`: the account groups table on main (#20),
      `app.checks.account_groups.lookup_account(account).nsf_categories`.
    - `run_checks` and `default_items`: `app.checks.run_checks` and `app.checks.default_items`,
      which #24 delivers. Until then they raise NotImplementedError saying so.
    """

    def run_checks(self, checks_input: ChecksInput, /) -> ChecksOutput:
        run: RunChecks = _not_yet("app.checks", "run_checks", "#24")
        return run(checks_input)

    def default_items(self, charge: Charge, records: Sequence[Record], /) -> Sequence[DefaultItem]:
        items: DefaultItems = _not_yet("app.checks", "default_items", "#24")
        return items(charge, records)

    def account_categories(self, account: str, /) -> Sequence[BudgetCategory]:
        from app.checks.account_groups import lookup_account

        found = lookup_account(account)
        return found.nsf_categories if found is not None else ()


@dataclass(frozen=True)
class AgentInput:
    """Everything one agent run works from, as it stood at the run's clock time."""

    run: AgentRun
    grant: Grant
    # Everything on the grant visible at run.clock_now. Records are in the order written,
    # replaced, waiting and rejected ones included.
    charges: list[Charge]
    files: list[EvidenceFile]
    records: list[Record]
    # For a run triggered by a charge: the charges it covers, the trigger's batch of the
    # charges that arrived at the same moment. Empty otherwise.
    charge_ids: list[str]
    # For a run started by a thread message: that thread, oldest first. Empty otherwise.
    thread: list[ThreadMessage]
    # The original bytes of a file, from private storage.
    read_file: Callable[[EvidenceFile], bytes]
    # The checks, for the write check's default items and the gate.
    checks: Checks


@dataclass(frozen=True)
class AgentResult:
    """What a finished run saves, all together.

    Records are in the order the agent wrote them, with IDs the agent gave them,
    author "agent", and written_at equal to the run's clock_now. Messages carry the run's ID.
    """

    records: list[Record] = field(default_factory=list[Record])
    messages: list[ThreadMessage] = field(default_factory=list[ThreadMessage])
    summary: str | None = None
    # The run's debug log (JSON), stored in private storage. Never shown to the accountant.
    log: bytes | None = None
    # For a thread run: open questions for the agent its gate left, outside the thread's
    # charge or record. The platform queues an ordinary run for them.
    other_open_questions: list[OpenQuestion] = field(default_factory=list[OpenQuestion])


class Agent(Protocol):
    def run(self, agent_input: AgentInput, /) -> AgentResult:
        """Do one run. Raise to fail it: nothing is saved. The platform retries it unless
        the exception has `retryable` False, and stores the exception's `log` bytes if any
        (the agent's AgentRunFailed carries both)."""
        ...


class ModuleAgent:
    """The real agent: `app.agent.run_agent(agent_input) -> AgentResult`."""

    def run(self, agent_input: AgentInput, /) -> AgentResult:
        run: Callable[[AgentInput], AgentResult] = _not_yet("app.agent", "run_agent", "#23")
        return run(agent_input)


class Storage(Protocol):
    def put(self, path: str, data: bytes, media_type: str, /) -> None: ...

    def get(self, path: str, /) -> bytes: ...

    def signed_url(self, path: str, expires_in: int, /) -> str:
        """A link to the object that works for expires_in seconds."""
        ...


class Pinger(Protocol):
    def ping(self, topic: str, event: str, payload: dict[str, Any], /) -> None:
        """Tell the screens on this topic that something changed. Never raises."""
        ...


class NoPings:
    def ping(self, topic: str, event: str, payload: dict[str, Any], /) -> None:
        return None
