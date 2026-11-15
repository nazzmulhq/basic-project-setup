import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import settings
from app.core.redis_cluster import RedisClusterClient

ALGORITHM = "HS256"


def create_token_pair(user_id: str, roles: list[str], permissions: list[str]) -> dict[str, Any]:
    now = datetime.now(UTC)
    access_jti = str(uuid.uuid4())
    refresh_jti = str(uuid.uuid4())
    access_ttl = settings.access_token_expire_minutes * 60
    refresh_ttl = settings.refresh_token_expire_days * 86400
    claims = {"sub": user_id, "roles": roles, "permissions": permissions}
    access_token = jwt.encode(
        {
            **claims,
            "jti": access_jti,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(seconds=access_ttl),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm=ALGORITHM,
    )
    refresh_token = jwt.encode(
        {
            "sub": user_id,
            "jti": refresh_jti,
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(seconds=refresh_ttl),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm=ALGORITHM,
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_jti": access_jti,
        "refresh_jti": refresh_jti,
        "access_ttl": access_ttl,
        "refresh_ttl": refresh_ttl,
    }


def decode_jwt(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[ALGORITHM],
        options={"require": ["exp", "iat", "sub", "jti", "type"]},
    )


def refresh_key(user_id: str, jti: str) -> str:
    return f"auth:{{{user_id}}}:rt:{jti}"


def blocklist_key(user_id: str, jti: str) -> str:
    return f"auth:{{{user_id}}}:bl:{jti}"


def rbac_key(user_id: str) -> str:
    return f"auth:{{{user_id}}}:rbac"


async def persist_refresh_session(
    redis: RedisClusterClient, user_id: str, jti: str, ttl_seconds: int
) -> None:
    await redis.set(refresh_key(user_id, jti), "active", ex=ttl_seconds)
