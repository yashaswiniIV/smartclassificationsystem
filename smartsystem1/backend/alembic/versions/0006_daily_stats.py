"""daily_stats pre-aggregation table

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-15

"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_stats",
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column(
            "ward_id",
            sa.SmallInteger,
            sa.ForeignKey("wards.id", name="fk_daily_stats_ward_id_wards"),
            primary_key=True,
        ),
        sa.Column(
            "category_id",
            sa.SmallInteger,
            sa.ForeignKey("categories.id", name="fk_daily_stats_category_id_categories"),
            primary_key=True,
        ),
        sa.Column("new_complaints", sa.Integer, server_default="0", nullable=False),
        sa.Column("new_issues", sa.Integer, server_default="0", nullable=False),
        sa.Column("resolved_issues", sa.Integer, server_default="0", nullable=False),
        sa.Column("reopened_issues", sa.Integer, server_default="0", nullable=False),
        sa.Column("sla_breaches", sa.Integer, server_default="0", nullable=False),
        sa.Column("upvotes", sa.Integer, server_default="0", nullable=False),
        sa.Column("avg_resolution_hours", sa.REAL),
    )
    op.create_index("daily_stats_day_idx", "daily_stats", ["day"])


def downgrade() -> None:
    op.drop_table("daily_stats")
