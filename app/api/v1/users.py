import uuid

from fastapi import APIRouter, Query, status

from app.core.dependencies import CurrentPrincipalDeps, require_permissions, require_roles
from app.schemas.user import AssignRolesRequest, CreateUserRequest, UserResponse
from app.services.user_service import UserServiceDeps

router = APIRouter(prefix="/users", tags=["Users & RBAC"])


@router.get(
    "",
    response_model=list[UserResponse],
    summary="List Users (Paginated)",
    description=(
        "Retrieve paginated list of users with decrypted contact fields and RBAC roles "
        "(requires 'users:read' permission)."
    ),
    response_description="Paginated list of users retrieved successfully.",
    dependencies=[require_permissions("users:read")],
)
async def get_users(
    service: UserServiceDeps,
    limit: int = Query(
        50, ge=1, le=200, description="Maximum number of user records to return (1-200)."
    ),
    offset: int = Query(0, ge=0, description="Number of user records to skip for pagination."),
) -> list[UserResponse]:
    return await service.get_users(limit=limit, offset=offset)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create User",
    description=(
        "Register a new user with AEAD-encrypted PII, assign roles, and stage in outbox for "
        "Tantivy search (requires 'users:write' permission)."
    ),
    response_description="User created and indexed successfully.",
    dependencies=[require_permissions("users:write")],
)
async def create_user(
    payload: CreateUserRequest,
    service: UserServiceDeps,
    principal: CurrentPrincipalDeps,
) -> UserResponse:
    can_manage_roles = "super_admin" in principal.roles or "roles:manage" in principal.permissions
    return await service.create_user(payload, can_manage_roles=can_manage_roles)


@router.get(
    "/search",
    summary="Search Users",
    description=(
        "Full-text search users across indexed attributes using Tantivy search engine "
        "(requires 'users:read' permission)."
    ),
    response_description="Matching user search results returned.",
    dependencies=[require_permissions("users:read")],
)
async def search_users(
    service: UserServiceDeps,
    q: str = Query(
        ..., min_length=2, max_length=100, description="Search keyword or query string."
    ),
) -> list[dict]:
    return await service.search_users(q)


@router.put(
    "/{user_id}/roles",
    response_model=UserResponse,
    summary="Update User Roles",
    description=(
        "Replace roles for a specific user, invalidating RBAC caches and syncing outbox "
        "(requires 'super_admin' role and 'roles:manage' permission)."
    ),
    response_description="User roles updated and caches invalidated successfully.",
    dependencies=[require_roles("super_admin"), require_permissions("roles:manage")],
)
async def update_user_roles(
    user_id: uuid.UUID,
    payload: AssignRolesRequest,
    service: UserServiceDeps,
) -> UserResponse:
    return await service.assign_roles(user_id, payload.role_names)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate User",
    description=(
        "Soft-delete/deactivate user, clear caches, and queue search index removal "
        "(requires 'users:delete' permission)."
    ),
    response_description="User deactivated successfully (no content).",
    dependencies=[require_permissions("users:delete")],
)
async def deactivate_user(user_id: uuid.UUID, service: UserServiceDeps) -> None:
    await service.deactivate_user(user_id)
