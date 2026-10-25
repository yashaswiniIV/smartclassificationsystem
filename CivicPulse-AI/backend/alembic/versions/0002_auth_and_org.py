"""users, sessions, departments, categories, wards

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-13

"""

import geoalchemy2
import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    user_role = postgresql.ENUM("citizen", "official", "admin", name="user_role", create_type=False)
    user_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "departments",
        sa.Column("id", sa.SmallInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("name_hi", sa.String),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("name", name="uq_departments_name"),
    )

    op.create_table(
        "wards",
        sa.Column("id", sa.SmallInteger, sa.Identity(), primary_key=True),
        sa.Column("ward_code", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("zone", sa.String),
        sa.Column(
            "geom",
            geoalchemy2.Geometry("MULTIPOLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.UniqueConstraint("ward_code", name="uq_wards_ward_code"),
    )
    op.create_index("wards_geom_gix", "wards", ["geom"], postgresql_using="gist")

    op.create_table(
        "categories",
        sa.Column("id", sa.SmallInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "department_id",
            sa.SmallInteger,
            sa.ForeignKey("departments.id", name="fk_categories_department_id_departments"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.SmallInteger,
            sa.ForeignKey("categories.id", name="fk_categories_parent_id_categories"),
        ),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("name_hi", sa.String),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(384)),
        sa.Column("severity_weight", sa.SmallInteger, server_default="3", nullable=False),
        sa.Column("sla_hours", sa.Integer, server_default="168", nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("name", name="uq_categories_name"),
        sa.CheckConstraint(
            "severity_weight BETWEEN 1 AND 5", name="ck_categories_severity_weight_range"
        ),
    )

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("role", user_role, server_default="citizen", nullable=False),
        sa.Column("email", postgresql.CITEXT, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("full_name", sa.String, nullable=False),
        sa.Column("phone", sa.String),
        sa.Column("preferred_language", sa.String(2), server_default="en", nullable=False),
        sa.Column(
            "department_id",
            sa.SmallInteger,
            sa.ForeignKey("departments.id", name="fk_users_department_id_departments"),
        ),
        sa.Column(
            "is_department_head", sa.Boolean, server_default=sa.text("false"), nullable=False
        ),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "official_wards",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_official_wards_user_id_users"),
            primary_key=True,
        ),
        sa.Column(
            "ward_id",
            sa.SmallInteger,
            sa.ForeignKey("wards.id", name="fk_official_wards_ward_id_wards"),
            primary_key=True,
        ),
    )

    op.create_table(
        "sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_sessions_user_id_users"),
            nullable=False,
        ),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False),
        sa.Column("user_agent", sa.String),
        sa.Column("ip", postgresql.INET),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("sessions_user_idx", "sessions", ["user_id"])
    op.create_index("sessions_family_idx", "sessions", ["family_id"])
    op.create_index("sessions_token_hash_idx", "sessions", ["token_hash"])


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("official_wards")
    op.drop_table("users")
    op.drop_table("categories")
    op.drop_index("wards_geom_gix", table_name="wards")
    op.drop_table("wards")
    op.drop_table("departments")
    postgresql.ENUM(name="user_role").drop(op.get_bind(), checkfirst=True)
