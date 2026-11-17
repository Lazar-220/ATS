"""OpenRouter transport, for eval runs only (opt-in fallback after a Gemini daily quota).

Checked against the OpenRouter docs on 2026-11-17: OpenAI-compatible chat completions
(`POST /api/v1/chat/completions`, `response_format` of type `json_object`, text at
`choices[0].message.content`, tokens in `usage.prompt_tokens` / `completion_tokens`); the free
models (`:free`) allow 20 requests per minute and 50 per UTC day under 10 credits purchased;
`GET /api/v1/key` returns `data.free_model_daily_requests` with `used`, `limit` and `remaining`;
a 429 body is `{"error": {"code": 429, "message": ..., "metadata": {"error_type": ...}}}` and does
not say whether the limit is per minute or per day, so the daily case is decided by asking the
key's counters, not by reading the message.

Nothing in the API or the worker imports this module: a worker never switches models silently.
"""

import json
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import httpx
from pydantic import BaseModel

from ats.llm.types import (
    LLMError,
    LLMRequest,
    RateLimitError,
    RawCompletion,
    TransientServerError,
)

log = logging.getLogger(__name__)

BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemma-4-31b-it:free"
# The owner's rules: 20 requests per minute, never more than 50 real calls per UTC day.
RPM = 20
DAILY_CAP = 50
RETRYABLE_SERVER_CODES = frozenset({500, 503, 504})
TIMEOUT_S = 120.0


class OpenRouterTransport:
    def __init__(
        self,
        api_key: str,
        *,
        state_dir: Path,
        http: httpx.Client | None = None,
        today: Callable[[], date] = lambda: datetime.now(UTC).date(),
    ) -> None:
        self._http = http or httpx.Client(base_url=BASE_URL, timeout=TIMEOUT_S)
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._state_dir = state_dir
        self._today = today

    # --- the daily cap -------------------------------------------------------------------

    def _local_count_path(self) -> Path:
        return self._state_dir / f"openrouter_calls_{self._today().isoformat()}.count"

    def _local_count(self) -> int:
        try:
            return int(self._local_count_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0

    def _count_call(self) -> None:
        # Survives separate runs on the same day; the key's own counter is the other source.
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._local_count_path().write_text(str(self._local_count() + 1), encoding="utf-8")

    def _remote_remaining(self) -> int | None:
        """Requests left today according to `GET /key`, or None if it cannot be read."""
        try:
            response = self._http.get("/key", headers=self._headers)
            response.raise_for_status()
            counters = response.json()["data"]["free_model_daily_requests"]
            return min(int(counters["remaining"]), DAILY_CAP - int(counters["used"]))
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return None

    def remaining_today(self) -> int:
        """The smaller of the hard cap minus local calls and what the key's counter allows."""
        remaining = DAILY_CAP - self._local_count()
        remote = self._remote_remaining()
        return remaining if remote is None else min(remaining, remote)

    # --- one request ---------------------------------------------------------------------

    def complete(self, model: str, request: LLMRequest, schema: type[BaseModel]) -> RawCompletion:
        if self.remaining_today() <= 0:
            raise RateLimitError("OpenRouter free-model daily cap reached", daily=True)
        # JSON mode guarantees JSON, not this schema: the client validates and retries once.
        system = (
            f"{request.system}\n\nAnswer with one JSON object that matches this JSON schema, "
            f"and nothing else:\n{json.dumps(schema.model_json_schema())}"
        )
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": request.user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        response = self._http.post("/chat/completions", json=body, headers=self._headers)
        self._count_call()
        return self._read(response)

    def _read(self, response: httpx.Response) -> RawCompletion:
        status = response.status_code
        payload: dict[str, Any] = {}
        try:
            decoded: Any = response.json()
            if isinstance(decoded, dict):
                payload = cast(dict[str, Any], decoded)
        except ValueError:
            pass
        error: Any = payload.get("error")
        code = status
        # A provider failure can arrive as a 200 with an `error` object.
        if status == 200 and isinstance(error, dict):
            code = int(cast(dict[str, Any], error).get("code", 502))
        if code == 429:
            retry = response.headers.get("Retry-After")
            wait = float(retry) if retry and retry.replace(".", "", 1).isdigit() else None
            daily = self.remaining_today() <= 0
            raise RateLimitError(f"OpenRouter 429: {response.text[:200]}", wait, daily=daily)
        if code in RETRYABLE_SERVER_CODES:
            raise TransientServerError(f"OpenRouter {code}: {response.text[:200]}", code)
        if code >= 400:
            raise LLMError(f"OpenRouter {code}: {response.text[:200]}")
        choices: Any = payload.get("choices") or [{}]
        message: Any = choices[0].get("message") or {}
        usage: Any = payload.get("usage") or {}
        return RawCompletion(
            text=str(message.get("content") or ""),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )
