from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.app.database import Base
import backend.app.models

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    Base.metadata.create_all(bind=bind)

    inspector = inspect(bind)
    if "analysis_jobs" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("analysis_jobs")}
        additions = []
        if "attempts" not in columns:
            additions.append(sa.Column("attempts", sa.Integer, nullable=False, server_default="0"))
        if "max_attempts" not in columns:
            additions.append(sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"))
        if "started_at" not in columns:
            additions.append(sa.Column("started_at", sa.DateTime, nullable=True))
        if "finished_at" not in columns:
            additions.append(sa.Column("finished_at", sa.DateTime, nullable=True))
        if "cancel_requested" not in columns:
            additions.append(
                sa.Column("cancel_requested", sa.Boolean, nullable=False, server_default=sa.false())
            )
        if additions:
            with op.batch_alter_table("analysis_jobs") as batch_op:
                for column in additions:
                    batch_op.add_column(column)


def downgrade() -> None:
    pass
