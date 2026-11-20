"""The walkthrough with LLM_PROVIDER=fake: upload to ranked list through the API alone."""

import psycopg
import pytest
from fastapi.testclient import TestClient
from pdfs import make_pdf
from psycopg.rows import DictRow
from psycopg_pool import ConnectionPool

from ats.llm.factory import create_llm_client
from ats.llm.fake import FakeLLMClient
from ats.settings import Settings
from ats.worker import ingest, judge, position_setup
from integration.test_ingest import upload, wait_until_settled

pytestmark = pytest.mark.integration

POSTING = make_pdf(
    "Senior Python developer, Belgrade\nRequirements\nExperience with Python and PostgreSQL\n"
    "Experience leading a team of engineers\n" + "Zahtevi za poziciju razvojnog inzenjera. " * 4
)
MATCHING_CV = make_pdf(
    "Marko Petrovic\nmarko.petrovic@example.com\n+381 64 123 4567\n"
    "Backend work\nSenior Python developer at Acme Bank, 2019-2023\n"
    "Built PostgreSQL services and led a team of engineers\n" * 2
)
WEAK_CV = make_pdf(
    "Jelena Jovanovic\njelena.jovanovic@example.com\n+381 63 765 4321\n"
    "Retail work\nShop assistant at a bakery, 2018-2022\nCustomer service and cash handling\n" * 3
)
SECRETS = ["Marko", "Petrovic", "marko.petrovic", "@example.com", "381 64", "Jelena", "Jovanovic"]


def test_demo_provider_walks_from_upload_to_a_ranking_with_real_names_and_masked_llm_input(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    demo = create_llm_client(Settings(llm_provider="fake"))
    assert isinstance(demo, FakeLLMClient)  # still the LLMClient boundary, not a side door
    for module in (position_setup, ingest, judge):
        monkeypatch.setattr(module, "get_llm_client", lambda: demo)

    accepted = upload(client, POSTING, [WEAK_CV, MATCHING_CV])
    wait_until_settled(conn)

    status = client.get(f"/rankings/{accepted['request_id']}").json()
    assert status["status"] == "done"
    ranking = client.get(f"/positions/{accepted['position_id']}/ranking").json()
    names = [row["candidate_name"] for row in ranking["rows"]]
    assert names == ["Marko Petrovic", "Jelena Jovanovic"]  # the real names, best score first
    best, worst = ranking["rows"]
    assert best["score"] > worst["score"]

    detail = client.get(f"/assessments/{best['assessment_id']}").json()
    evidence = [v["evidence"] for v in detail["verdicts"] if v["evidence"] is not None]
    assert evidence, "the matching CV has at least one verified quote"
    for item in evidence:
        assert detail["cv_text"][item["char_start"] : item["char_end"]] == item["quote"]

    # The model side saw masked text only: no name, email or phone in any request.
    assert demo.calls
    for call in demo.calls:
        for secret in SECRETS:
            assert secret not in call.system + call.user, secret
