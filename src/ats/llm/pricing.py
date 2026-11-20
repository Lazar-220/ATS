"""Price of a run, from token counts. Rates are per million tokens, in US dollars."""

from dataclasses import dataclass
from datetime import date

from ats.llm.types import LLMUsage

# Cached input costs 10% of the input price (§6.1). Usage reports how many input tokens were
# served from the provider's prompt cache; the rest is billed at the full input rate.
CACHED_INPUT_SHARE = 0.10


@dataclass(frozen=True)
class Rate:
    label: str
    input_per_m: float
    output_per_m: float
    # The first day this rate no longer applies; None if it has no known end.
    until: date | None = None
    # The day these figures were last confirmed against their source (prices change, §6.1);
    # None when the source gives no date.
    checked: date | None = None

    @property
    def cached_input_per_m(self) -> float:
        return self.input_per_m * CACHED_INPUT_SHARE


# gemini-3.6-flash: the owner gave these rates (2026-11-17). gemini-3.8-flash: §6.1 of the plan,
# introductory price only; what follows is unknown, so it is not guessed.
RATES: dict[str, tuple[Rate, ...]] = {
    "gemini-3.6-flash": (
        Rate(
            "introductory, through 2026-12-31",
            0.75,
            3.75,
            until=date(2027, 1, 1),
            checked=date(2026, 11, 17),
        ),
        Rate("from 2027-01-01", 1.50, 7.50, checked=date(2026, 11, 17)),
    ),
    # The plan's figure; it names no date it was read on.
    "gemini-3.8-flash": (Rate("introductory, through 2026-12-31", 0.75, 3.75),),
}


def cost_usd(
    rate: Rate, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0
) -> float:
    """Output tokens already include thinking tokens, which are billed as output."""
    cached = min(cached_input_tokens, input_tokens)
    return (
        (input_tokens - cached) * rate.input_per_m
        + cached * rate.cached_input_per_m
        + output_tokens * rate.output_per_m
    ) / 1_000_000


def rate_on(model: str, day: date) -> Rate | None:
    """The rate in force on `day`, or None for a model with no known price."""
    for rate in RATES.get(model, ()):
        if rate.until is None or day < rate.until:
            return rate
    return None


def usage_cost_parts(model: str, usage: LLMUsage, day: date) -> dict[str, float] | None:
    """Input, output and total price of one call; None for a model with no known price.

    A cache hit reports no tokens, so it costs 0.
    """
    rate = rate_on(model, day)
    if rate is None:
        return None
    output = cost_usd(rate, 0, usage.output_tokens)
    total = cost_usd(rate, usage.input_tokens, usage.output_tokens, usage.cached_input_tokens)
    return {"input": total - output, "output": output, "total": total}


def usage_cost(model: str, usage: LLMUsage, day: date) -> float | None:
    parts = usage_cost_parts(model, usage, day)
    return None if parts is None else parts["total"]
