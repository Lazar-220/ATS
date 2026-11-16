import hashlib
import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel

from ats.llm.types import LLMRequest, RawCompletion


def cache_key(model: str, request: LLMRequest, schema: type[BaseModel]) -> str:
    """Hash of everything that can change the answer: model, both prompts, level, schema.

    The prompt version is not a separate part: it names the file the system text came from,
    so a new version is a new text and so a new key.
    """
    material = json.dumps(
        {
            "model": model,
            "system": request.system,
            "user": request.user,
            "thinking_level": request.thinking_level,
            "schema": schema.model_json_schema(),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(material.encode()).hexdigest()


class ResponseCache:
    """One JSON file per key. Only answers that passed validation are stored."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def _path(self, key: str) -> Path:
        return self._directory / key[:2] / f"{key}.json"

    def get(self, key: str) -> RawCompletion | None:
        try:
            data = json.loads(self._path(key).read_text(encoding="utf-8"))
            return RawCompletion(
                text=str(data["text"]),
                input_tokens=int(data["input_tokens"]),
                output_tokens=int(data["output_tokens"]),
            )
        except (OSError, ValueError, KeyError):
            return None  # a missing or damaged entry is a miss

    def put(self, key: str, completion: RawCompletion) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Temp file plus rename: a concurrent reader never sees half an entry.
        fd, temp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "text": completion.text,
                        "input_tokens": completion.input_tokens,
                        "output_tokens": completion.output_tokens,
                    },
                    handle,
                    ensure_ascii=False,
                )
            os.replace(temp_name, target)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
