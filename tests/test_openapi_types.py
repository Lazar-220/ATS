from ats.api.openapi import SCHEMA_PATH, render


def test_the_committed_openapi_schema_matches_the_api() -> None:
    # web/src/api-types.ts is generated from this file and `make check` checks that step, so a
    # route change that skips `make api-types` fails here instead of breaking the browser.
    committed = SCHEMA_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == render(), "web/openapi.json is stale: run `make api-types`"
