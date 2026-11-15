import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security.aead import aead_cipher
from app.core.security.password import hash_password
from app.core.tantivy_search import TantivyUserIndex, user_search_document
from app.models.outbox import OutboxEvent
from app.models.rbac import Permission, Role
from app.models.user import User

logger = logging.getLogger(__name__)

DEFAULT_PERMISSIONS = {
    "users:read": "View and search users",
    "users:write": "Create users",
    "users:delete": "Deactivate users",
    "roles:manage": "Assign roles to users",
}
DEFAULT_ROLES = {
    "super_admin": list(DEFAULT_PERMISSIONS),
    "manager": ["users:read", "users:write"],
    "viewer": ["users:read"],
}


async def run_initial_seed(db: AsyncSession, search_index: TantivyUserIndex) -> None:
    permissions: dict[str, Permission] = {}
    for codename, description in DEFAULT_PERMISSIONS.items():
        permission = (
            await db.execute(select(Permission).where(Permission.codename == codename))
        ).scalar_one_or_none()
        if permission is None:
            permission = Permission(codename=codename, description=description)
            db.add(permission)
            await db.flush()
        permissions[codename] = permission

    roles: dict[str, Role] = {}
    for name, permission_names in DEFAULT_ROLES.items():
        role = (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
        if role is None:
            role = Role(name=name, description=f"Default {name} role")
            db.add(role)
        role.permissions = [permissions[name] for name in permission_names]
        roles[name] = role
    await db.flush()

    admin_bidx = aead_cipher.blind_index(settings.default_admin_email)
    admin = (
        await db.execute(select(User).where(User.email_bidx == admin_bidx))
    ).scalar_one_or_none()
    if admin is None:
        admin = User(
            full_name="System SuperAdmin",
            email_encrypted=settings.default_admin_email,
            phone_encrypted=settings.default_admin_phone,
            nid_encrypted=settings.default_admin_nid.get_secret_value(),
            email_bidx=admin_bidx,
            phone_bidx=aead_cipher.blind_index(settings.default_admin_phone),
            password_hash=hash_password(settings.default_admin_password.get_secret_value()),
            is_active=True,
            roles=[roles["super_admin"]],
        )
        db.add(admin)
        await db.flush()
        db.add(
            OutboxEvent(
                aggregate_type="user",
                aggregate_id=str(admin.id),
                event_type="UPSERT",
                search_index="users_v1",
                payload=user_search_document(admin),
            )
        )
        logger.info("Seeded bootstrap administrator and queued its search-index event")
    await db.commit()
    if await search_index.is_empty():
        users = (
            await db.execute(select(User).options(selectinload(User.roles)).order_by(User.id))
        ).scalars().all()
        await search_index.rebuild([user_search_document(user) for user in users])
        logger.info("Rebuilt Tantivy user index with %d users", len(users))
