"""Rename the outbox target from the former search service field.

Revision ID: 0002_search_index
Revises: 0001_initial
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_search_index"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("outbox_events", "es_index", new_column_name="search_index")


def downgrade() -> None:
    op.alter_column("outbox_events", "search_index", new_column_name="es_index")
