"""ai_jobs, corrections, issue_upvotes

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-14

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ai_job_status = postgresql.ENUM(
        "queued", "running", "succeeded", "failed", name="ai_job_status", create_type=False
    )
    correction_kind = postgresql.ENUM(
        "recategorize",
        "detach",
        "merge",
        "priority_override",
        "reject",
        name="correction_kind",
        create_type=False,
    )
    ai_job_status.create(op.get_bind(), checkfirst=True)
    correction_kind.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("job_type", sa.String, nullable=False),
        sa.Column(
            "complaint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaints.id", name="fk_ai_jobs_complaint_id_complaints"),
        ),
        sa.Column("status", ai_job_status, server_default="queued", nullable=False),
        sa.Column("attempts", sa.SmallInteger, server_default="0", nullable=False),
        sa.Column("model", sa.String),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("confidence", sa.REAL),
        sa.Column("error", sa.Text),
        sa.Column("payload", postgresql.JSONB),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ai_jobs_complaint_idx", "ai_jobs", ["complaint_id"])

    op.create_table(
        "corrections",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "complaint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("complaints.id", name="fk_corrections_complaint_id_complaints"),
            nullable=False,
        ),
        sa.Column(
            "official_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_corrections_official_id_users"),
            nullable=False,
        ),
        sa.Column("kind", correction_kind, nullable=False),
        sa.Column("before", postgresql.JSONB, nullable=False),
        sa.Column("after", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "issue_upvotes",
        sa.Column(
            "issue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("issues.id", ondelete="CASCADE", name="fk_issue_upvotes_issue_id_issues"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_issue_upvotes_user_id_users"),
            primary_key=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("issue_upvotes")
    op.drop_table("corrections")
    op.drop_table("ai_jobs")
    postgresql.ENUM(name="correction_kind").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="ai_job_status").drop(op.get_bind(), checkfirst=True)
