from ats.llm.demo import create_demo_client
from ats.llm.factory import create_llm_client
from ats.llm.types import LLMRequest
from ats.pipeline.requirements import RequirementList
from ats.settings import Settings


def test_the_real_provider_is_the_default_and_a_missing_key_still_fails() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.llm_provider == "gemini"
    try:
        create_llm_client(settings)
    except RuntimeError as exc:
        assert "LLM_API_KEY" in str(exc)
    else:
        raise AssertionError("a missing key must not fall back to the demo client")


def test_the_demo_client_takes_requirements_from_the_posting_lines() -> None:
    request = LLMRequest(
        system="s",
        user="<posting>\nShort\nExperience with Python and SQL\n</posting>",
        thinking_level="low",
        prompt_version="requirements_v1",
    )
    result = create_demo_client().generate(request, RequirementList)
    assert [r.text for r in result.output.requirements] == ["Experience with Python and SQL"]
