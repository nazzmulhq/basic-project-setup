from app.main import app


def test_authentication_and_rbac_routes_are_registered() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/refresh" in paths
    assert "/api/v1/auth/logout" in paths
    assert "/api/v1/users/{user_id}/roles" in paths
    assert "/api/v1/users/{user_id}" in paths
