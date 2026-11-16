from collections.abc import Callable

from pydantic import BaseModel

from ats.llm.types import LLMRequest, LLMResult, LLMUsage

Responder = Callable[[LLMRequest, type[BaseModel]], BaseModel]


class FakeLLMClient:
    """Stands in for the model in every test and in the eval harness's dry runs.

    Give it a `responder` that builds the answer from the request, or fixed `outputs` that
    are returned in order. Each request is kept in `calls`.
    """

    def __init__(self, *outputs: BaseModel, responder: Responder | None = None) -> None:
        self._outputs = list(outputs)
        self.responder = responder
        self.calls: list[LLMRequest] = []

    def generate[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> LLMResult[T]:
        self.calls.append(request)
        if self.responder is not None:
            output = self.responder(request, schema)
        elif self._outputs:
            output = self._outputs.pop(0)
        else:
            raise AssertionError("FakeLLMClient has no output left for this call")
        if not isinstance(output, schema):
            raise AssertionError(f"FakeLLMClient output is not a {schema.__name__}")
        return LLMResult(
            output=output,
            usage=LLMUsage(input_tokens=0, output_tokens=0, latency_s=0.0, cache_hit=False),
        )
