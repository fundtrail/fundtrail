"""Shared base model and conventions for every contract model.

- IDs are strings. User IDs are Supabase auth UUIDs written as strings.
- Timestamps are timezone-aware and stored in UTC.
- Money is an integer number of cents, in US dollars. Credits are negative.
- Dates are calendar dates with no time.
"""

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    """Contract models reject unknown fields and can't be changed after creation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
