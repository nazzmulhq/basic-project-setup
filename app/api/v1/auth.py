from fastapi import APIRouter

from app.core.dependencies import CurrentPrincipalDeps
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshTokenRequest, TokenResponse
from app.services.auth_service import AuthServiceDeps

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User Login",
    description=(
        "Authenticate user using email and password, returning JWT access and refresh token pair."
    ),
    response_description="Access and refresh tokens issued successfully.",
)
async def login(payload: LoginRequest, auth_service: AuthServiceDeps) -> TokenResponse:
    return await auth_service.login(payload.email, payload.password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh Access Token",
    description=(
        "Exchange a valid single-use refresh token for a newly rotated access "
        "and refresh token pair."
    ),
    response_description="Tokens refreshed successfully.",
)
async def refresh_token(
    payload: RefreshTokenRequest, auth_service: AuthServiceDeps
) -> TokenResponse:
    return await auth_service.refresh_tokens(payload.refresh_token)


@router.post(
    "/logout",
    summary="User Logout",
    description=(
        "Revoke the current access token via Redis blocklist and delete the active refresh session."
    ),
    response_description="Successfully logged out.",
)
async def logout(
    principal: CurrentPrincipalDeps,
    auth_service: AuthServiceDeps,
    payload: LogoutRequest | None = None,
) -> dict[str, str]:
    return await auth_service.logout(
        principal.user_id,
        principal.jti,
        principal.access_expires_at,
        payload.refresh_token if payload else None,
    )


@router.get(
    "/me",
    summary="Current User Principal",
    description=(
        "Retrieve currently authenticated user's ID, assigned roles, and granted permissions."
    ),
    response_description="Authenticated principal details returned.",
)
async def get_me(principal: CurrentPrincipalDeps) -> dict[str, object]:
    return {
        "user_id": principal.user_id,
        "roles": principal.roles,
        "permissions": principal.permissions,
    }
