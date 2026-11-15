from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.session import DBSessionDeps
from app.models.rbac import Permission, Role


class RBACRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_roles_by_names(self, names: list[str]) -> list[Role]:
        if not names:
            return []
        stmt = select(Role).where(Role.name.in_(set(names))).options(selectinload(Role.permissions))
        return list((await self.db.execute(stmt)).scalars().unique().all())

    async def get_permissions(self) -> list[Permission]:
        return list((await self.db.execute(select(Permission))).scalars().all())


def get_rbac_repository(db: DBSessionDeps) -> RBACRepository:
    return RBACRepository(db)


RBACRepositoryDeps = Annotated[RBACRepository, Depends(get_rbac_repository)]
