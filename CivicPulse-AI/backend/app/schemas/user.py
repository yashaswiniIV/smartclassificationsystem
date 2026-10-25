from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import UserRole


class InviteIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    role: UserRole = UserRole.official
    department_id: int | None = None
    ward_ids: list[int] = []
    is_department_head: bool = False
    # Admin sets an initial password; the official can change it after first login.
    password: str = Field(min_length=8, max_length=128)


class StaffOut(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    department_id: int | None
    is_department_head: bool
