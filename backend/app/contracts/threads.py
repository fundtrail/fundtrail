"""Review threads (docs/contracts.md section 10).

Every charge can have a thread, and so can a record with a problem. Messages
live in their own table, outside the records, and are never edited. A message
changes nothing on its own: anything the agent wants changed is a record that
waits. The evidence report leaves messages out.
"""

from pydantic import model_validator

from .base import Id, Model, Text, UtcDatetime
from .records import Author


class ThreadMessage(Model):
    id: Id
    workspace_id: Id
    grant_id: Id
    charge_id: Id | None = None  # the thread is about exactly one charge or one record
    record_id: Id | None = None
    author: Author
    author_user_id: Id | None = None  # set exactly when author is "user"
    run_id: Id | None = None  # the run that wrote it, set exactly when author is "agent"
    text: Text
    written_at: UtcDatetime  # the workspace clock's "now"

    @model_validator(mode="after")
    def _rules(self):
        if (self.charge_id is None) == (self.record_id is None):
            raise ValueError("a thread is about exactly one charge or one record")
        if (self.author == Author.USER) != (self.author_user_id is not None):
            raise ValueError("author_user_id is set exactly when author is 'user'")
        if (self.author == Author.AGENT) != (self.run_id is not None):
            raise ValueError("run_id is set exactly when author is 'agent'")
        return self
