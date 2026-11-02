"""add task queue indexes

Revision ID: b3d1f0a7c2e4
Revises: 92202bff8f1c
Create Date: 2026-11-02 10:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3d1f0a7c2e4"
down_revision: str | None = "92202bff8f1c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_tasks_pullable",
        "tasks",
        [sa.text("priority DESC"), "created_at"],
        sqlite_where=sa.text("status = 'pending'"),
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_tasks_lease",
        "tasks",
        ["lease_expires_at"],
        sqlite_where=sa.text("locked_by IS NOT NULL"),
        postgresql_where=sa.text("locked_by IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_lease", table_name="tasks")
    op.drop_index("ix_tasks_pullable", table_name="tasks")
