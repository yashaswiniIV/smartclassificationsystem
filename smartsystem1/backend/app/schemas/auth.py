from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    preferred_language: str = Field(default="en", pattern="^(en|hi)$")


class VerifyEmailIn(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r"^\d{6}$")


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UpdateMeIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    preferred_language: str | None = Field(default=None, pattern="^(en|hi)$")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    preferred_language: str
    phone: str | None
    department_id: int | None
    is_department_head: bool
    email_verified_at: datetime | None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
