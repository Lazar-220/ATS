"""Writing a position's requirement rows: the shared step of position setup and HR edits."""

from typing import Any
from uuid import UUID, uuid4

import psycopg

from ats.pipeline.requirements import RequirementList

POSITION_SETUP_JOB = "position_setup"


def insert_requirements(
    conn: psycopg.Connection[Any],
    position_id: UUID,
    rubric_version: int,
    requirements: RequirementList,
) -> None:
    """Insert one rubric version. Older versions stay, so verdicts never dangle (1.1a).

    The list's `id` and `parent` labels become row ids: every row is inserted first and the
    parent links are set after, because the foreign key is checked per statement.
    """
    row_ids = {draft.id: uuid4() for draft in requirements.requirements}
    for order, draft in enumerate(requirements.requirements):
        conn.execute(
            "INSERT INTO requirement (id, position_id, rubric_version, ord, text, kind, weight, "
            "min_months) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                row_ids[draft.id],
                position_id,
                rubric_version,
                order,
                draft.text,
                draft.kind,
                draft.weight,
                draft.min_months,
            ),
        )
    for draft in requirements.requirements:
        if draft.parent is not None:
            conn.execute(
                "UPDATE requirement SET parent_id = %s WHERE id = %s",
                (row_ids[draft.parent], row_ids[draft.id]),
            )
