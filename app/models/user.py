import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security.aead import EncryptedString
from app.models.base import Base
from app.models.rbac import Role, user_roles


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(120), index=True)
    email_encrypted: Mapped[str] = mapped_column(
        EncryptedString(aad_context="users.email"), nullable=False
    )
    phone_encrypted: Mapped[str] = mapped_column(
        EncryptedString(aad_context="users.phone"), nullable=False
    )
    nid_encrypted: Mapped[str] = mapped_column(
        EncryptedString(aad_context="users.nid"), nullable=False
    )
    email_bidx: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    phone_bidx: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    roles: Mapped[list[Role]] = relationship(secondary=user_roles, lazy="selectin")

    @property
    def role_names(self) -> list[str]:
        return sorted(role.name for role in self.roles)

    @property
    def permission_codenames(self) -> list[str]:
        return sorted(
            {permission.codename for role in self.roles for permission in role.permissions}
        )
