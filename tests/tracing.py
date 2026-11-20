"""A Langfuse tracer that exports into memory, for tests that look at what would be sent."""

import uuid
from typing import Any

from langfuse import Langfuse
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ats.observability import LangfuseTracer


class MemoryTracing:
    def __init__(self) -> None:
        self.exporter = InMemorySpanExporter()
        # The SDK shares its machinery between clients with the same public key; a fresh key
        # per instance keeps one test's spans out of another's.
        self.client = Langfuse(
            public_key=f"pk-test-{uuid.uuid4().hex}",
            secret_key="sk-test",
            base_url="http://127.0.0.1:9",
            span_exporter=self.exporter,
        )
        self.tracer = LangfuseTracer(self.client)

    def spans(self) -> list[ReadableSpan]:
        self.client.flush()
        return list(self.exporter.get_finished_spans())

    def by_name(self, name: str) -> ReadableSpan:
        found = [span for span in self.spans() if span.name == name]
        assert len(found) == 1, f"expected one span named {name!r}, got {len(found)}"
        return found[0]

    def everything_sent(self) -> str:
        """Every name, attribute key and value of every span, as one string to search."""
        parts: list[str] = []
        for span in self.spans():
            parts.append(span.name)
            attributes: Any = span.attributes or {}
            for key, value in attributes.items():
                parts.append(f"{key}={value}")
            for event in span.events:
                parts.append(event.name)
                parts.extend(f"{k}={v}" for k, v in (event.attributes or {}).items())
        return "\n".join(parts)
