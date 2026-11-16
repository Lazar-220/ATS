"""One real call to the model. Never runs automatically: `uv run pytest -m llm`.

Costs one request of the free quota (about 20 a day). The posting is synthetic.
"""

from pathlib import Path

import pytest

from ats.llm.cache import ResponseCache
from ats.llm.gemini import GeminiTransport
from ats.llm.managed import ManagedLLMClient
from ats.llm.ratelimit import RateLimiter
from ats.pipeline.requirements import extract_requirements
from ats.settings import get_settings

pytestmark = pytest.mark.llm

POSTING = """Senior Backend Developer (synthetic posting for tests)

About us: we build payment software for small shops.

Requirements
- Java
- 3 years of experience in Java
- A university degree and 3 years of experience in software development
- Good written English

Nice to have
- Docker is a plus

We offer a flexible schedule and a laptop.
"""


def test_the_real_model_splits_and_links_the_requirements(tmp_path: Path) -> None:
    settings = get_settings()
    if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value():
        pytest.skip("LLM_API_KEY is not set")
    client = ManagedLLMClient(
        GeminiTransport(settings.llm_api_key.get_secret_value()),
        model=settings.llm_model,
        limiter=RateLimiter(settings.llm_rpm),
        cache=ResponseCache(tmp_path),  # empty, so the first call is a real one
    )

    first = extract_requirements(client, POSTING)
    for req in first.output.requirements:
        print(req)
    print(first.usage)

    by_text = {req.text.lower(): req for req in first.output.requirements}
    java = next(r for t, r in by_text.items() if t.strip(" .") == "java")
    java_years = next(r for t, r in by_text.items() if "years" in t and "java" in t)
    assert java_years.parent == java.id
    assert java_years.min_months == 36

    # "a degree and 3 years of experience" must be two requirements, neither the other's child.
    degree = [r for t, r in by_text.items() if "degree" in t]
    experience = [r for t, r in by_text.items() if "years" in t and "software" in t]
    assert len(degree) == 1 and len(experience) == 1
    assert degree[0].id != experience[0].id
    assert "degree" not in experience[0].text.lower()

    docker = next(r for t, r in by_text.items() if "docker" in t)
    assert docker.kind == "nice_to_have"
    assert not first.usage.cache_hit

    again = extract_requirements(client, POSTING)
    assert again.usage.cache_hit
    assert again.output == first.output
