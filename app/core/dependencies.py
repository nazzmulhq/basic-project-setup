import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.redis_cluster import RedisClusterDeps
from app.core.security.jwt import blocklist_key, decode_jwt
from app.repositories.user_repository import UserRepositoryDeps

bearer_scheme = HTTPBearer(auto_error=True)


class AuthenticatedPrincipal:
    def __init__(
        self,
        user_id: str,
        jti: str,
        roles: list[str],
        permissions: list[str],
        access_expires_at: int,
    ) -> None:
        self.user_id = user_id
        self.jti = jti
        self.roles = roles
        self.permissions = permissions
        self.access_expires_at = access_expires_at


async def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    redis: RedisClusterDeps,
    user_repository: UserRepositoryDeps,
) -> AuthenticatedPrincipal:
    try:
        claims = decode_jwt(credentials.credentials)
        if claims.get("type") != "access":
            raise ValueError("Access token required")
        user_id = str(uuid.UUID(claims["sub"]))
        jti = str(uuid.UUID(claims["jti"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if await redis.get(blocklist_key(user_id, jti)):
        raise HTTPException(status_code=401, detail="Token has been revoked")
    user = await user_repository.get_by_id(uuid.UUID(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive or not found")

    # The database is authoritative for authorization. Cache entries are never
    # treated as grants, so failed cache invalidation cannot preserve old access.
    return AuthenticatedPrincipal(
        user_id,
        jti,
        user.role_names,
        user.permission_codenames,
        int(claims["exp"]),
    )


CurrentPrincipalDeps = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]


def require_permissions(*required_perms: str):
    async def permission_checker(
        principal: CurrentPrincipalDeps,
    ) -> AuthenticatedPrincipal:
        if "super_admin" in principal.roles:
            return principal
        missing = [
            permission for permission in required_perms if permission not in principal.permissions
        ]
        if missing:
            raise HTTPException(status_code=403, detail=f"Missing required permissions: {missing}")
        return principal

    return Depends(permission_checker)


def require_roles(*allowed_roles: str):
    async def role_checker(
        principal: CurrentPrincipalDeps,
    ) -> AuthenticatedPrincipal:
        if not any(role in principal.roles for role in allowed_roles):
            raise HTTPException(status_code=403, detail=f"Required one of roles: {allowed_roles}")
        return principal

    return Depends(role_checker)
