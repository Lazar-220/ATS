"""The only module that imports `google-genai`.

Checked against SDK 3.3.0 and the Gemini API docs: structured output is
`response_mime_type="application/json"` plus a Pydantic class as `response_schema`, and the
reasoning depth is `ThinkingConfig(thinking_level=...)`.
"""

from typing import Any

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from ats.llm.types import LLMRequest, RateLimitError, RawCompletion

HTTP_TIMEOUT_MS = 120_000


class GeminiTransport:
    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=HTTP_TIMEOUT_MS)
        )

    def complete(self, model: str, request: LLMRequest, schema: type[BaseModel]) -> RawCompletion:
        config = types.GenerateContentConfig(
            system_instruction=request.system,
            response_mime_type="application/json",
            response_schema=schema,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel(request.thinking_level.upper())
            ),
        )
        try:
            # The SDK's `contents` annotation contains Unknown members; nothing to fix on our side.
            response = self._client.models.generate_content(  # pyright: ignore[reportUnknownMemberType]
                model=model, contents=request.user, config=config
            )
        except errors.APIError as exc:
            if exc.code == 429:
                raise RateLimitError(str(exc), _retry_after_s(exc.details)) from exc  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            raise
        usage = response.usage_metadata
        # Thinking tokens are billed as output, so they count as output here.
        return RawCompletion(
            # No text (a blocked or empty answer) fails validation like any other bad output.
            text=response.text or "",
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(
                (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
                if usage
                else 0
            ),
        )


def _retry_after_s(details: Any) -> float | None:
    """The wait the provider asks for: `error.details[*].retryDelay`, for example "34s"."""
    try:
        for item in details["error"]["details"]:
            delay = item.get("retryDelay")
            if isinstance(delay, str) and delay.endswith("s"):
                return float(delay[:-1])
    except (KeyError, TypeError, ValueError, AttributeError):
        pass
    return None
