from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.timeutil import is_valid_timezone
from app.schemas.common import ORMModel


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    is_admin: bool
    timezone: str
    locale: str
    last_seen_at: datetime | None
    previous_seen_at: datetime | None


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    display_name: str | None = Field(default=None, max_length=200)


class EmailVerifyIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class EmailResendIn(BaseModel):
    email: EmailStr


class AuthConfigOut(BaseModel):
    registration_open: bool


class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class AdminUserOut(ORMModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    is_admin: bool
    is_active: bool
    email_verified_at: datetime | None
    created_at: datetime
    last_login_at: datetime | None


class AdminUserUpdate(BaseModel):
    is_active: bool


class LoginOut(BaseModel):
    token: str
    expires_at: datetime
    user: UserOut


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordResetConfirmIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class AccountUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, pattern=r"^(fr|en)$")

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is not None and not is_valid_timezone(v):
            raise ValueError("Fuseau horaire IANA inconnu (ex. Europe/Paris, Africa/Dakar).")
        return v
