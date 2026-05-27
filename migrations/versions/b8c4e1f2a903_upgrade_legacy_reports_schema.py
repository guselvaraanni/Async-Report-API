"""upgrade legacy reports schema

Revision ID: b8c4e1f2a903
Revises: a70986e2aa61
Create Date: 2026-05-27 22:00:00.000000

Adds v1 columns to pre-existing reports table (legacy installs created
reports before Flask-Migrate was introduced).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "b8c4e1f2a903"
down_revision = "a70986e2aa61"
branch_labels = None
depends_on = None


def _reports_columns(bind):
    return {c["name"] for c in inspect(bind).get_columns("reports")}


def upgrade():
    bind = op.get_bind()
    cols = _reports_columns(bind)

    if "file_url" in cols and "file_path" not in cols:
        with op.batch_alter_table("reports", schema=None) as batch_op:
            batch_op.alter_column(
                "file_url",
                new_column_name="file_path",
                existing_type=sa.String(length=1000),
                existing_nullable=True,
            )
        cols = _reports_columns(bind)

    if "file_path" not in cols:
        op.add_column(
            "reports",
            sa.Column("file_path", sa.String(length=1000), nullable=True),
        )
        cols = _reports_columns(bind)

    if "requested_rows" not in cols:
        op.add_column(
            "reports",
            sa.Column(
                "requested_rows",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
        cols = _reports_columns(bind)

    if "progress_pct" not in cols:
        op.add_column(
            "reports",
            sa.Column(
                "progress_pct",
                sa.Float(),
                nullable=True,
                server_default="0",
            ),
        )
        cols = _reports_columns(bind)

    if "cancel_requested_at" not in cols:
        op.add_column(
            "reports",
            sa.Column("cancel_requested_at", sa.DateTime(), nullable=True),
        )

    # Backfill requested_rows for rows created under legacy schema
    op.execute(
        sa.text(
            """
            UPDATE reports
            SET requested_rows = COALESCE(rows_processed, 0)
            WHERE requested_rows = 0 AND COALESCE(rows_processed, 0) > 0
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE reports
            SET progress_pct = LEAST(100.0, (rows_processed / requested_rows) * 100.0)
            WHERE requested_rows > 0
            """
        )
    )

    # Indexes (ignore if already present — MySQL will error; use inspector)
    insp = inspect(bind)
    existing_indexes = {idx["name"] for idx in insp.get_indexes("reports")}

    index_specs = [
        ("ix_reports_cancel_requested_at", ["cancel_requested_at"]),
        ("ix_reports_completed_at", ["completed_at"]),
        ("ix_reports_created_at", ["created_at"]),
        ("ix_reports_started_at", ["started_at"]),
        ("ix_reports_status", ["status"]),
        ("ix_reports_task_id", ["task_id"]),
    ]

    with op.batch_alter_table("reports", schema=None) as batch_op:
        for name, columns in index_specs:
            if name not in existing_indexes:
                batch_op.create_index(name, columns, unique=(name == "ix_reports_task_id"))


def downgrade():
    bind = op.get_bind()
    cols = _reports_columns(bind)

    insp = inspect(bind)
    existing_indexes = {idx["name"] for idx in insp.get_indexes("reports")}

    with op.batch_alter_table("reports", schema=None) as batch_op:
        for name in (
            "ix_reports_cancel_requested_at",
            "ix_reports_completed_at",
            "ix_reports_created_at",
            "ix_reports_started_at",
            "ix_reports_status",
            "ix_reports_task_id",
        ):
            if name in existing_indexes:
                batch_op.drop_index(name)

    if "cancel_requested_at" in cols:
        op.drop_column("reports", "cancel_requested_at")
    if "progress_pct" in cols:
        op.drop_column("reports", "progress_pct")
    if "requested_rows" in cols:
        op.drop_column("reports", "requested_rows")

    if "file_path" in cols and "file_url" not in cols:
        with op.batch_alter_table("reports", schema=None) as batch_op:
            batch_op.alter_column(
                "file_path",
                new_column_name="file_url",
                existing_type=sa.String(length=1000),
                existing_nullable=True,
            )
