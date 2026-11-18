from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_field_reviews"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

TABLE_NAME = "field_reviews"
INDEX_NAME = "ix_field_reviews_field_id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE_NAME not in inspector.get_table_names():
        op.create_table(
            TABLE_NAME,
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "field_id",
                sa.Integer(),
                sa.ForeignKey("parsed_fields.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if TABLE_NAME in inspect(bind).get_table_names():
        indexes = {index["name"] for index in inspect(bind).get_indexes(TABLE_NAME)}
        if INDEX_NAME not in indexes:
            op.create_index(INDEX_NAME, TABLE_NAME, ["field_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE_NAME not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes(TABLE_NAME)}
    if INDEX_NAME in indexes:
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
