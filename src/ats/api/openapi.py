"""Write the API's OpenAPI schema to web/openapi.json, the input of the TypeScript types.

Needs neither a database nor a running server: the schema comes from the route definitions.
"""

import json
import sys
from pathlib import Path

from ats.api.main import app

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "web" / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    # newline="" keeps LF on Windows, so the committed file is the same everywhere.
    with SCHEMA_PATH.open("w", encoding="utf-8", newline="") as out:
        out.write(render())
    sys.stdout.write(f"wrote {SCHEMA_PATH}\n")


if __name__ == "__main__":
    main()
