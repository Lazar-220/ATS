"""`LLMClient` wrapper that records every call as a Langfuse generation (phase 1.6).

It sits outside the managed client, so a cache hit is traced too (flagged as one, with zero
tokens) and the latency is what the caller waited. What it records is what the model was given
and answered: the prompts (the CV in them is masked text, §2.4) and the parsed output.
"""

from pydantic import BaseModel

from ats.llm.types import LLMClient, LLMRequest, LLMResult
from ats.observability import Tracer


class TracedLLMClient:
    def __init__(self, inner: LLMClient, tracer: Tracer, *, model: str, provider: str) -> None:
        self._inner = inner
        self._tracer = tracer
        self._model = model
        self._provider = provider

    def generate[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> LLMResult[T]:
        with self._tracer.generation(
            request.prompt_version,
            model=self._model,
            input=[
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            model_parameters={"thinking_level": request.thinking_level},
            metadata={
                "prompt_version": request.prompt_version,
                "schema": schema.__name__,
                "provider": self._provider,
            },
        ) as generation:
            result = self._inner.generate(request, schema)
            usage = result.usage
            generation.update(
                output=result.output.model_dump(mode="json"),
                usage_details={
                    "input": usage.input_tokens,
                    "output": usage.output_tokens,
                    "total": usage.input_tokens + usage.output_tokens,
                },
                metadata={
                    "prompt_version": request.prompt_version,
                    "schema": schema.__name__,
                    "provider": self._provider,
                    "cache_hit": usage.cache_hit,
                    "latency_s": round(usage.latency_s, 3),
                },
            )
            return result
