"""issue_status_history, issue_updates, notifications

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-14

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    issue_status = postgresql.ENUM(name="issue_status", create_type=False)
    notification_channel = postgresql.ENUM(
        "inapp", "email", name="notification_channel", create_type=False
    )
    notification_channel.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "issue_status_history",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "issue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("issues.id", ondelete="CASCADE", name="fk_ish_issue_id_issues"),
            nullable=False,
        ),
        sa.Column("from_status", issue_status),
        sa.Column("to_status", issue_status, nullable=False),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_ish_actor_id_users"),
        ),
        sa.Column("note", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ish_issue_idx", "issue_status_history", ["issue_id", "created_at"])

    op.create_table(
        "issue_updates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "issue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("issues.id", ondelete="CASCADE", name="fk_issue_updates_issue_id_issues"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_issue_updates_author_id_users"),
            nullable=False,
        ),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("photo_key", sa.String),
        sa.Column("is_internal", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("issue_updates_issue_idx", "issue_updates", ["issue_id", "created_at"])

    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_notifications_user_id_users"),
            nullable=False,
        ),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("body", sa.Text),
        sa.Column(
            "issue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("issues.id", name="fk_notifications_issue_id_issues"),
        ),
        sa.Column("channel", notification_channel, server_default="inapp", nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("emailed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "notifications_inbox_idx",
        "notifications",
        ["user_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("read_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("issue_updates")
    op.drop_table("issue_status_history")
    postgresql.ENUM(name="notification_channel").drop(op.get_bind(), checkfirst=True)
