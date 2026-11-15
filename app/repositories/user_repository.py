import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security.aead import aead_cipher
from app.core.session import DBSessionDeps
from app.models.rbac import Role
from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all(self, limit: int = 50, offset: int = 0) -> Sequence[User]:
        stmt = (
            select(User)
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        stmt = (
            select(User)
            .where(User.email_bidx == aead_cipher.blind_index(email))
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        stmt = select(User).where(User.phone_bidx == aead_cipher.blind_index(phone))
        return (await self.db.execute(stmt)).scalar_one_or_none()

    def stage_user(
        self,
        *,
        full_name: str,
        email: str,
        phone: str,
        nid: str,
        password_hash: str,
        roles: list[Role],
    ) -> User:
        user = User(
            full_name=full_name,
            email_encrypted=email,
            phone_encrypted=phone,
            nid_encrypted=nid,
            email_bidx=aead_cipher.blind_index(email),
            phone_bidx=aead_cipher.blind_index(phone),
            password_hash=password_hash,
            roles=roles,
        )
        self.db.add(user)
        return user


def get_user_repository(db: DBSessionDeps) -> UserRepository:
    return UserRepository(db)


UserRepositoryDeps = Annotated[UserRepository, Depends(get_user_repository)]
