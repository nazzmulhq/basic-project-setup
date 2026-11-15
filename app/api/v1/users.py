import uuid

from fastapi import APIRouter, Query, status

from app.core.dependencies import CurrentPrincipalDeps, require_permissions, require_roles
from app.schemas.user import AssignRolesRequest, CreateUserRequest, UserResponse
from app.services.user_service import UserServiceDeps

router = APIRouter(prefix="/users", tags=["Users & RBAC"])


@router.get(
    "",
    response_model=list[UserResponse],
    dependencies=[require_permissions("users:read")],
)
async def get_users(
    service: UserServiceDeps,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[UserResponse]:
    return await service.get_users(limit=limit, offset=offset)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permissions("users:write")],
)
async def create_user(
    payload: CreateUserRequest,
    service: UserServiceDeps,
    principal: CurrentPrincipalDeps,
) -> UserResponse:
    can_manage_roles = "super_admin" in principal.roles or "roles:manage" in principal.permissions
    return await service.create_user(payload, can_manage_roles=can_manage_roles)


@router.get("/search", dependencies=[require_permissions("users:read")])
async def search_users(
    service: UserServiceDeps, q: str = Query(..., min_length=2, max_length=100)
) -> list[dict]:
    return await service.search_users(q)


@router.put(
    "/{user_id}/roles",
    response_model=UserResponse,
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
    dependencies=[require_permissions("users:delete")],
)
async def deactivate_user(user_id: uuid.UUID, service: UserServiceDeps) -> None:
    await service.deactivate_user(user_id)
