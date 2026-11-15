import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator


class CreateUserRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=8, max_length=20)
    nid: str = Field(min_length=8, max_length=30)
    password: str = Field(min_length=8, max_length=128)
    role_names: list[str] = Field(default_factory=lambda: ["viewer"], min_length=1)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, password: str) -> str:
        if len(password.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return password

    @field_validator("role_names")
    @classmethod
    def validate_unique_roles(cls, role_names: list[str]) -> list[str]:
        if len(role_names) != len(set(role_names)):
            raise ValueError("Role names must be unique")
        return role_names


class AssignRolesRequest(BaseModel):
    role_names: list[str] = Field(min_length=1)

    @field_validator("role_names")
    @classmethod
    def validate_unique_roles(cls, role_names: list[str]) -> list[str]:
        if len(role_names) != len(set(role_names)):
            raise ValueError("Role names must be unique")
        return role_names


class UserResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: EmailStr
    phone: str
    is_active: bool
    roles: list[str]
    permissions: list[str]
