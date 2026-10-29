"""reports table

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-15

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("scope", sa.String, server_default="city", nullable=False),
        sa.Column("stats", postgresql.JSONB, nullable=False),
        sa.Column("content_md", sa.Text),
        sa.Column("pdf_key", sa.String),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("reports_created_idx", "reports", [sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_table("reports")
