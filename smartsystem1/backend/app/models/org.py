from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    name_hi: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class Ward(Base):
    __tablename__ = "wards"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    ward_code: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    zone: Mapped[str | None] = mapped_column(String)
    geom: Mapped[object] = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False))


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String, unique=True)
    name_hi: Mapped[str | None] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
    severity_weight: Mapped[int] = mapped_column(SmallInteger, server_default="3")
    sla_hours: Mapped[int] = mapped_column(Integer, server_default="168")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    __table_args__ = (
        CheckConstraint("severity_weight BETWEEN 1 AND 5", name="severity_weight_range"),
    )
