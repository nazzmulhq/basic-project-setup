import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_cluster import RedisClusterClient, RedisClusterDeps
from app.core.security.jwt import (
    blocklist_key,
    create_token_pair,
    decode_jwt,
    persist_refresh_session,
    rbac_key,
    refresh_key,
)
from app.core.security.password import verify_password
from app.core.session import DBSessionDeps
from app.models.user import User
from app.repositories.user_repository import UserRepository, UserRepositoryDeps
from app.schemas.auth import TokenResponse


class AuthService:
    def __init__(
        self, user_repository: UserRepository, db: AsyncSession, redis: RedisClusterClient
    ) -> None:
        self.user_repository = user_repository
        self.db = db
        self.redis = redis

    async def login(self, email: str, password: str) -> TokenResponse:
        user = await self.user_repository.get_by_email(email)
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await self._issue_tokens(user)

    async def refresh_tokens(self, token: str) -> TokenResponse:
        try:
            claims = decode_jwt(token)
            if claims.get("type") != "refresh":
                raise ValueError("Not a refresh token")
            user_id = str(uuid.UUID(claims["sub"]))
            jti = str(uuid.UUID(claims["jti"]))
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token") from exc

        # GETDEL makes refresh-token rotation single-use, including concurrent requests.
        if await self.redis.getdel(refresh_key(user_id, jti)) != "active":
            raise HTTPException(status_code=401, detail="Refresh token has been revoked or used")
        user = await self.user_repository.get_by_id(uuid.UUID(user_id))
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User inactive or not found")
        return await self._issue_tokens(user)

    async def logout(
        self, user_id: str, access_jti: str, access_expires_at: int, refresh_token: str | None
    ) -> dict[str, str]:
        ttl_seconds = max(1, access_expires_at - int(datetime.now(UTC).timestamp()))
        await self.redis.set(blocklist_key(user_id, access_jti), "revoked", ex=ttl_seconds)
        if refresh_token:
            try:
                claims = decode_jwt(refresh_token)
                if claims.get("type") == "refresh" and claims.get("sub") == user_id:
                    await self.redis.delete(refresh_key(user_id, str(uuid.UUID(claims["jti"]))))
            except (jwt.PyJWTError, KeyError, TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Invalid refresh token")
        return {"detail": "Successfully logged out"}

    async def _issue_tokens(self, user: User) -> TokenResponse:
        tokens = create_token_pair(str(user.id), user.role_names, user.permission_codenames)
        await persist_refresh_session(
            self.redis, str(user.id), tokens["refresh_jti"], tokens["refresh_ttl"]
        )
        await self.redis.set(
            rbac_key(str(user.id)),
            json.dumps({"roles": user.role_names, "permissions": user.permission_codenames}),
            ex=tokens["refresh_ttl"],
        )
        return TokenResponse(
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            roles=user.role_names,
            permissions=user.permission_codenames,
        )


def get_auth_service(
    user_repository: UserRepositoryDeps,
    db: DBSessionDeps,
    redis: RedisClusterDeps,
) -> AuthService:
    return AuthService(user_repository, db, redis)


AuthServiceDeps = Annotated[AuthService, Depends(get_auth_service)]
