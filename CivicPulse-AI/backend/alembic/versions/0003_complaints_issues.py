"""issues, complaints, complaint_media + public-code sequences

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-13

"""

import geoalchemy2
import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    issue_status = postgresql.ENUM(
        "open",
        "acknowledged",
        "assigned",
        "in_progress",
        "resolved",
        "closed",
        "reopened",
        "rejected",
        name="issue_status",
        create_type=False,
    )
    processing_status = postgresql.ENUM(
        "queued",
        "processing",
        "triaged",
        "needs_manual_triage",
        "rejected",
        name="processing_status",
        create_type=False,
    )
    cv_status = postgresql.ENUM(
        "pending", "done", "failed", "skipped", name="cv_status", create_type=False
    )
    moderation_status = postgresql.ENUM(
        "pending", "approved", "flagged", name="moderation_status", create_type=False
    )
    for enum in (issue_status, processing_status, cv_status, moderation_status):
        enum.create(op.get_bind(), checkfirst=True)

    # Human-friendly public reference codes (CP-2026-000123 / ISS-2026-00042).
    op.execute("CREATE SEQUENCE IF NOT EXISTS complaint_code_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS issue_code_seq")

    op.create_table(
        "issues",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("public_code", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column(
            "category_id",
            sa.SmallInteger,
            sa.ForeignKey("categories.id", name="fk_issues_category_id_categories"),
            nullable=False,
        ),
        sa.Column(
            "department_id",
            sa.SmallInteger,
            sa.ForeignKey("departments.id", name="fk_issues_department_id_departments"),
            nullable=False,
        ),
        sa.Column(
            "ward_id",
            sa.SmallInteger,
            sa.ForeignKey("wards.id", name="fk_issues_ward_id_wards"),
            nullable=False,
        ),
        sa.Column(
            "centroid",
            geoalchemy2.Geography("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("status", issue_status, server_default="open", nullable=False),
        sa.Column("priority_score", sa.REAL, server_default="0", nullable=False),
        sa.Column("priority_factors", postgresql.JSONB),
        sa.Column("complaint_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("upvote_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("first_reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_breached", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column(
            "assigned_to",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_issues_assigned_to_users"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_note", sa.Text),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("reopen_count", sa.SmallInteger, server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("public_code", name="uq_issues_public_code"),
    )
    op.create_index("issues_centroid_gix", "issues", ["centroid"], postgresql_using="gist")
    op.create_index(
        "issues_queue_idx", "issues", ["department_id", "status", sa.text("priority_score DESC")]
    )
    op.create_index("issues_ward_status_idx", "issues", ["ward_id", "status"])

    op.create_table(
        "complaints",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("public_code", sa.String, nullable=False),
        sa.Column(
            "citizen_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_complaints_citizen_id_users"),
            nullable=False,
        ),
        sa.Column(
            "issue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("issues.id", name="fk_complaints_issue_id_issues"),
        ),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("language", sa.String(2)),
        sa.Column(
            "location",
            geoalchemy2.Geography("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("address_text", sa.String),
        sa.Column(
            "ward_id",
            sa.SmallInteger,
            sa.ForeignKey("wards.id", name="fk_complaints_ward_id_wards"),
        ),
        sa.Column(
            "category_id",
            sa.SmallInteger,
            sa.ForeignKey("categories.id", name="fk_complaints_category_id_categories"),
        ),
        sa.Column(
            "ai_category_id",
            sa.SmallInteger,
            sa.ForeignKey("categories.id", name="fk_complaints_ai_category_id_categories"),
        ),
        sa.Column("ai_category_confidence", sa.REAL),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(384)),
        sa.Column("processing_status", processing_status, server_default="queued", nullable=False),
        sa.Column(
            "declined_intercept", sa.Boolean, server_default=sa.text("false"), nullable=False
        ),
        sa.Column("submitted_via", sa.String, server_default="web", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("public_code", name="uq_complaints_public_code"),
    )
    op.create_index("complaints_location_gix", "complaints", ["location"], postgresql_using="gist")
    op.create_index("complaints_issue_idx", "complaints", ["issue_id"])
    op.create_index(
        "complaints_citizen_idx", "complaints", ["citizen_id", sa.text("created_at DESC")]
    )
    op.create_index(
        "complaints_embedding_idx",
        "complaints",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "complaint_media",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "complaint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "complaints.id",
                ondelete="CASCADE",
                name="fk_complaint_media_complaint_id_complaints",
            ),
            nullable=False,
        ),
        sa.Column("object_key", sa.String, nullable=False),
        sa.Column("mime", sa.String, nullable=False),
        sa.Column("bytes", sa.Integer, nullable=False),
        sa.Column("width", sa.Integer),
        sa.Column("height", sa.Integer),
        sa.Column("exif_gps", geoalchemy2.Geography("POINT", srid=4326, spatial_index=False)),
        sa.Column("cv_status", cv_status, server_default="pending", nullable=False),
        sa.Column("cv_result", postgresql.JSONB),
        sa.Column("moderation", moderation_status, server_default="pending", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("complaint_media_complaint_idx", "complaint_media", ["complaint_id"])


def downgrade() -> None:
    op.drop_table("complaint_media")
    op.drop_table("complaints")
    op.drop_table("issues")
    op.execute("DROP SEQUENCE IF EXISTS issue_code_seq")
    op.execute("DROP SEQUENCE IF EXISTS complaint_code_seq")
    for name in ("moderation_status", "cv_status", "processing_status", "issue_status"):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
