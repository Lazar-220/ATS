"""Price of a run, from token counts. Rates are per million tokens, in US dollars."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Rate:
    label: str
    input_per_m: float
    output_per_m: float
    # The first day this rate no longer applies; None if it has no known end.
    until: date | None = None


# gemini-3.6-flash: the owner gave these rates (2026-11-17). gemini-3.8-flash: §6.1 of the plan,
# introductory price only; what follows is unknown, so it is not guessed.
RATES: dict[str, tuple[Rate, ...]] = {
    "gemini-3.6-flash": (
        Rate("introductory, through 2026-12-31", 0.75, 3.75, until=date(2027, 1, 1)),
        Rate("from 2027-01-01", 1.50, 7.50),
    ),
    "gemini-3.8-flash": (Rate("introductory, through 2026-12-31", 0.75, 3.75),),
}


def cost_usd(rate: Rate, input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * rate.input_per_m + output_tokens * rate.output_per_m) / 1_000_000


def rate_on(model: str, day: date) -> Rate | None:
    """The rate in force on `day`, or None for a model with no known price."""
    for rate in RATES.get(model, ()):
        if rate.until is None or day < rate.until:
            return rate
    return None
