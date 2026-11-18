"""components, component_specs, agent_runs, spec_review_log, app_settings

Explicit, idempotent: each table/index is only created when missing so that
databases previously bootstrapped with create_all upgrade cleanly.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0003_components_specs_runs"
down_revision = "0002_field_reviews"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    return {index["name"] for index in inspect(op.get_bind()).get_indexes(table)}


def _ensure_index(name: str, table: str, columns, unique: bool = False) -> None:
    if name not in _indexes(table):
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    existing = _tables()

    if "components" not in existing:
        op.create_table(
            "components",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("manufacturer", sa.String(255), nullable=False),
            sa.Column("part_number", sa.String(255), nullable=False),
            sa.Column("category", sa.String(64), nullable=True),
            sa.Column("package", sa.String(255), nullable=True),
            sa.Column("pin_count", sa.Integer(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
    _ensure_index("ix_components_id", "components", ["id"])
    _ensure_index("ix_components_manufacturer", "components", ["manufacturer"])
    _ensure_index("ix_components_part_number", "components", ["part_number"])
    _ensure_index("ix_components_category", "components", ["category"])
    _ensure_index("ix_components_document_id", "components", ["document_id"])
    _ensure_index("ix_components_updated_at", "components", ["updated_at"])
    # Expression index: inspectors don't list it on SQLite, so rely on IF NOT EXISTS (SQLite + PostgreSQL).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_components_manufacturer_part "
        "ON components (lower(manufacturer), lower(part_number))"
    )

    if "component_specs" not in existing:
        op.create_table(
            "component_specs",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("component_id", sa.Integer(), sa.ForeignKey("components.id", ondelete="CASCADE"), nullable=False),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
            sa.Column("job_id", sa.String(64), nullable=True),
            sa.Column("parameter", sa.String(128), nullable=False),
            sa.Column("label", sa.String(255), nullable=True),
            sa.Column("category", sa.String(32), nullable=False, server_default="other"),
            sa.Column("condition_type", sa.String(32), nullable=False, server_default="general"),
            sa.Column("value_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("unit", sa.String(32), nullable=True),
            sa.Column("min_value", sa.Float(), nullable=True),
            sa.Column("typ_value", sa.Float(), nullable=True),
            sa.Column("max_value", sa.Float(), nullable=True),
            sa.Column("test_condition", sa.Text(), nullable=True),
            sa.Column("page_number", sa.Integer(), nullable=True),
            sa.Column("source_text", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
            sa.Column("extraction_method", sa.String(32), nullable=False, server_default="deterministic"),
            sa.Column("validation_status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("reviewer_comment", sa.Text(), nullable=True),
            sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    for column in ("id", "component_id", "document_id", "job_id", "parameter", "category", "condition_type", "validation_status"):
        _ensure_index(f"ix_component_specs_{column}", "component_specs", [column])

    if "agent_runs" not in existing:
        op.create_table(
            "agent_runs",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("job_id", sa.String(64), nullable=False),
            sa.Column("agent", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
        )
    for column in ("id", "job_id", "agent"):
        _ensure_index(f"ix_agent_runs_{column}", "agent_runs", [column])

    if "spec_review_log" not in existing:
        op.create_table(
            "spec_review_log",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("spec_id", sa.Integer(), sa.ForeignKey("component_specs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("action", sa.String(16), nullable=False),
            sa.Column("old_value", sa.JSON(), nullable=True),
            sa.Column("new_value", sa.JSON(), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    for column in ("id", "spec_id", "created_at"):
        _ensure_index(f"ix_spec_review_log_{column}", "spec_review_log", [column])

    if "app_settings" not in existing:
        op.create_table(
            "app_settings",
            sa.Column("key", sa.String(128), primary_key=True, nullable=False),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    # Never drop user data automatically.
    pass
