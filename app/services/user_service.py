import json
import logging
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_cluster import RedisClusterClient, RedisClusterDeps
from app.core.security.jwt import rbac_key
from app.core.security.password import hash_password
from app.core.session import DBSessionDeps
from app.core.tantivy_search import (
    TantivyUserIndex,
    TantivyUserIndexDeps,
    user_search_document,
)
from app.models.user import User
from app.repositories.outbox_repository import OutboxRepository, OutboxRepositoryDeps
from app.repositories.rbac_repository import RBACRepository, RBACRepositoryDeps
from app.repositories.user_repository import UserRepository, UserRepositoryDeps
from app.schemas.user import CreateUserRequest, UserResponse

logger = logging.getLogger(__name__)


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        rbac_repository: RBACRepository,
        outbox_repository: OutboxRepository,
        db: AsyncSession,
        redis: RedisClusterClient,
        search_index: TantivyUserIndex,
    ) -> None:
        self.repository = repository
        self.rbac_repository = rbac_repository
        self.outbox_repository = outbox_repository
        self.db = db
        self.redis = redis
        self.search_index = search_index

    async def get_users(self, limit: int = 50, offset: int = 0) -> list[UserResponse]:
        users = await self.repository.get_all(limit=limit, offset=offset)
        return [self._to_response(user) for user in users]

    async def create_user(
        self, req: CreateUserRequest, *, can_manage_roles: bool = False
    ) -> UserResponse:
        if not can_manage_roles and set(req.role_names) != {"viewer"}:
            raise HTTPException(
                status_code=403,
                detail="Only a role manager can assign roles during user creation",
            )
        if await self.repository.get_by_email(req.email):
            raise HTTPException(status_code=409, detail="Email already registered")
        if await self.repository.get_by_phone(req.phone):
            raise HTTPException(status_code=409, detail="Phone already registered")

        roles = await self.rbac_repository.get_roles_by_names(req.role_names)
        if len(roles) != len(set(req.role_names)):
            raise HTTPException(status_code=400, detail="One or more role names are invalid")

        user = self.repository.stage_user(
            full_name=req.full_name,
            email=req.email,
            phone=req.phone,
            nid=req.nid,
            password_hash=hash_password(req.password),
            roles=roles,
        )
        await self.db.flush()
        self._stage_user_index(user)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=409, detail="Email or phone already registered"
            ) from exc

        response = self._to_response(user)
        try:
            cache_payload = {
                "id": str(user.id),
                "full_name": user.full_name,
                "is_active": user.is_active,
                "roles": user.role_names,
            }
            await self.redis.set(f"user:{{{user.id}}}:profile", json.dumps(cache_payload), ex=3600)
        except Exception:
            logger.warning("User profile cache write failed for user %s", user.id, exc_info=True)
        return response

    async def assign_roles(self, user_id: uuid.UUID, role_names: list[str]) -> UserResponse:
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        roles = await self.rbac_repository.get_roles_by_names(role_names)
        if len(roles) != len(set(role_names)):
            raise HTTPException(status_code=400, detail="One or more role names are invalid")

        user.roles = roles
        self._stage_user_index(user)
        await self.db.commit()
        response = self._to_response(user)
        try:
            await self.redis.delete(rbac_key(str(user.id)))
            await self.redis.delete(f"user:{{{user.id}}}:profile")
        except Exception:
            logger.warning("RBAC cache refresh failed for user %s", user.id, exc_info=True)
        return response

    async def deactivate_user(self, user_id: uuid.UUID) -> None:
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_active = False
        self._stage_user_index(user)
        await self.db.commit()
        try:
            await self.redis.delete(rbac_key(str(user.id)), f"user:{{{user.id}}}:profile")
        except Exception:
            logger.warning("Cache invalidation failed for user %s", user.id, exc_info=True)

    async def search_users(self, query: str) -> list[dict]:
        try:
            return await self.search_index.search_users(query)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid search query") from exc

    def _stage_user_index(self, user: User) -> None:
        self.outbox_repository.stage_event(
            aggregate_type="user",
            aggregate_id=str(user.id),
            event_type="UPSERT",
            search_index="users_v1",
            payload=dict(user_search_document(user)),
        )

    @staticmethod
    def _to_response(user: User) -> UserResponse:
        return UserResponse(
            id=user.id,
            full_name=user.full_name,
            email=user.email_encrypted,
            phone=user.phone_encrypted,
            is_active=user.is_active,
            roles=user.role_names,
            permissions=user.permission_codenames,
        )


def get_user_service(
    repository: UserRepositoryDeps,
    rbac_repository: RBACRepositoryDeps,
    outbox_repository: OutboxRepositoryDeps,
    db: DBSessionDeps,
    redis: RedisClusterDeps,
    search_index: TantivyUserIndexDeps,
) -> UserService:
    return UserService(repository, rbac_repository, outbox_repository, db, redis, search_index)


UserServiceDeps = Annotated[UserService, Depends(get_user_service)]
