"""document.mask_spans: the map between masked text and raw text

Revision ID: 0003
Revises: 0002

Masking (phase 1.4a) replaces name, email, phone and address with placeholders. The judge
quotes masked text, and the interface highlights raw text, so the list of replaced raw ranges
is stored with `masked_text`, in the same transaction. Nullable: postings and CVs not yet
parsed have none.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE document ADD COLUMN mask_spans jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE document DROP COLUMN mask_spans")
