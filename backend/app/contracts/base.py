"""The base every contract model shares, and the conventions in docs/contracts.md.

- IDs are strings. User IDs are Supabase auth UUIDs written as strings.
- Timestamps are timezone-aware and stored in UTC. Records carry the workspace clock's "now".
- Money is an integer number of cents in US dollars. Credits are negative.
- Dates with no time are calendar dates.
- Contract models reject unknown fields and can't be changed after they're created.
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Strict, StringConstraints


class Model(BaseModel):
    """Every contract model: unknown fields are rejected, and nothing changes after creation."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


# A timezone-aware timestamp, converted to UTC.
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]

# Money: an integer number of cents. A float or a string is refused.
Cents = Annotated[int, Strict()]

# An ID, or any other text that can't be empty.
Id = Annotated[str, StringConstraints(min_length=1)]
Text = Annotated[str, StringConstraints(min_length=1)]
