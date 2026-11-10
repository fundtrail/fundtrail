"""The call to the model: claude-opus-5-5 through Anthropic's SDK, and nothing else.

No fallback to another model (answer 4): a safety refusal fails the run. Adaptive thinking (it
can't be turned off on this model), effort `high` to start (the model's default is `medium`),
streaming with the SDK's final-message helper, and prompt caching on the stable prefix.
Assistant turns go back unchanged, thinking blocks included, as this model requires.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import anthropic
from anthropic.types import Message

MODEL = "claude-opus-5-5"
EFFORT = "high"
MAX_TOKENS = 64000
MAX_TOKENS_RETRY = 128000


@dataclass
class ModelRequest:
    system: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    max_tokens: int = MAX_TOKENS
    effort: str = EFFORT


class ModelClient(Protocol):
    """Anything that answers a request with one assistant message. Tests pass a fake."""

    def __call__(self, request: ModelRequest) -> Message: ...


class AnthropicModel:
    """The real model. The SDK reads the key from the environment; it's never passed around."""

    def __init__(self, client: anthropic.Anthropic | None = None):
        self._client = client or anthropic.Anthropic(max_retries=3)

    def __call__(self, request: ModelRequest) -> Message:
        with self._client.messages.stream(
            model=MODEL,
            max_tokens=request.max_tokens,
            system=request.system,  # pyright: ignore[reportArgumentType]
            tools=request.tools,  # pyright: ignore[reportArgumentType]
            messages=request.messages,  # pyright: ignore[reportArgumentType]
            thinking={"type": "adaptive"},
            output_config={"effort": request.effort},  # pyright: ignore[reportArgumentType]
            cache_control={"type": "ephemeral"},
        ) as stream:
            return stream.get_final_message()


def is_retryable(error: Exception) -> bool:
    """Whether a failed call could work if the job is tried again later."""
    if isinstance(
        error, anthropic.APIConnectionError | anthropic.RateLimitError | anthropic.APITimeoutError
    ):
        return True
    if isinstance(error, anthropic.APIStatusError):
        return error.status_code >= 500 or error.status_code in (408, 409, 429)
    return False
