"""The contract every LLM caller depends on. Nothing here imports a provider SDK."""

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel

# Which levels a model accepts differs per model (gemini-3.8-flash rejects "minimal"); the
# adapter passes the value through and the provider's error says so.
type ThinkingLevel = Literal["minimal", "low", "medium", "high"]


@dataclass(frozen=True)
class LLMRequest:
    """One call. System text is the stable prefix; the data goes last in the user text (§4.5)."""

    system: str
    user: str
    thinking_level: ThinkingLevel
    # Names the prompt file the system text came from, for the call log.
    prompt_version: str


@dataclass(frozen=True)
class LLMUsage:
    # Output tokens include thinking tokens, which the provider bills as output.
    # A cache hit costs nothing, so it reports 0 tokens and `cache_hit=True`.
    input_tokens: int
    output_tokens: int
    latency_s: float
    cache_hit: bool


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    output: T
    usage: LLMUsage


class LLMClient(Protocol):
    def generate[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> LLMResult[T]:
        """Return the model's answer parsed into `schema`.

        Raises `LLMOutputInvalid` when two attempts in a row fail validation (§4.5).
        """
        ...


@dataclass(frozen=True)
class RawCompletion:
    text: str
    input_tokens: int
    output_tokens: int


class LLMError(Exception):
    pass


class RateLimitError(LLMError):
    """The provider answered 429. `retry_after_s` is its own hint, when it gave one."""

    def __init__(self, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class LLMOutputInvalid(LLMError):
    """The answer did not parse into the schema, even after one retry call."""


class Transport(Protocol):
    """One request to a provider, with no rate limiting, retry or cache around it."""

    def complete(
        self, model: str, request: LLMRequest, schema: type[BaseModel]
    ) -> RawCompletion: ...
