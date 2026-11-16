en_catalog = {
    "swagger": {
        "title": "FastAPI Enterprise Architecture Blueprint",
        "description": (
            "Enterprise-grade FastAPI backend featuring RBAC, AES-256 GCM encrypted PII, "
            "Tantivy search, Redis caching, Outbox pattern, and Multi-language (i18n) support."
        ),
        "tags": {
            "Authentication": (
                "User authentication, JWT token issuance, refresh rotation, and logout."
            ),
            "Users & RBAC": (
                "User administration, RBAC role assignments, and Tantivy full-text search."
            ),
            "Health": "Health probe and service readiness status.",
        },
        "routes": {
            ("/health", "get"): {
                "summary": "Health Check",
                "description": (
                    "Check application health and ensure critical services are operational."
                ),
                "responses": {
                    "200": "Service is healthy and operational.",
                },
            },
            ("/api/v1/auth/login", "post"): {
                "summary": "User Login",
                "description": (
                    "Authenticate user using email and password, returning JWT access and "
                    "refresh token pair."
                ),
                "responses": {
                    "200": "Authentication successful. Access and refresh tokens issued.",
                    "401": "Invalid email or password.",
                    "422": "Validation error in request payload.",
                },
            },
            ("/api/v1/auth/refresh", "post"): {
                "summary": "Refresh Access Token",
                "description": (
                    "Exchange a valid single-use refresh token for a newly rotated access "
                    "and refresh token pair."
                ),
                "responses": {
                    "200": "Tokens refreshed successfully.",
                    "401": "Invalid, expired, or revoked refresh token.",
                    "422": "Validation error in request payload.",
                },
            },
            ("/api/v1/auth/logout", "post"): {
                "summary": "User Logout",
                "description": (
                    "Revoke the current access token via Redis blocklist and delete the "
                    "active refresh session."
                ),
                "responses": {
                    "200": "Successfully logged out.",
                    "400": "Invalid refresh token supplied.",
                    "401": "Invalid, expired, or missing access token.",
                },
            },
            ("/api/v1/auth/me", "get"): {
                "summary": "Current User Principal",
                "description": (
                    "Retrieve currently authenticated user's ID, assigned roles, and "
                    "granted permissions."
                ),
                "responses": {
                    "200": "Authenticated principal details returned.",
                    "401": "Unauthorized or invalid access token.",
                },
            },
            ("/api/v1/users", "get"): {
                "summary": "List Users (Paginated)",
                "description": (
                    "Retrieve paginated list of users with decrypted fields and RBAC roles "
                    "(requires 'users:read' permission)."
                ),
                "parameters": {
                    "limit": "Maximum number of user records to return (1-200).",
                    "offset": "Number of user records to skip for pagination.",
                },
                "responses": {
                    "200": "Paginated list of users retrieved successfully.",
                    "401": "Unauthorized: Access token missing or invalid.",
                    "403": "Forbidden: Missing required 'users:read' permission.",
                },
            },
            ("/api/v1/users", "post"): {
                "summary": "Create User",
                "description": (
                    "Register a new user with AEAD-encrypted PII, assign roles, and stage in "
                    "outbox for Tantivy search (requires 'users:write' permission)."
                ),
                "responses": {
                    "201": "User created and indexed successfully.",
                    "400": "One or more role names are invalid.",
                    "401": "Unauthorized: Access token missing or invalid.",
                    "403": "Forbidden: Only a role manager can assign roles during user creation.",
                    "409": "Conflict: Email or phone number is already registered.",
                    "422": "Validation error in user creation payload.",
                },
            },
            ("/api/v1/users/search", "get"): {
                "summary": "Search Users",
                "description": (
                    "Full-text search users across indexed attributes using Tantivy search engine "
                    "(requires 'users:read' permission)."
                ),
                "parameters": {
                    "q": "Search keyword or query string (2 to 100 characters).",
                },
                "responses": {
                    "200": "Matching user search results returned.",
                    "400": "Invalid search query syntax.",
                    "401": "Unauthorized: Access token missing or invalid.",
                    "403": "Forbidden: Missing required 'users:read' permission.",
                },
            },
            ("/api/v1/users/{user_id}/roles", "put"): {
                "summary": "Update User Roles",
                "description": (
                    "Replace roles for a specific user, invalidating RBAC caches and syncing "
                    "outbox (requires 'super_admin' role and 'roles:manage' permission)."
                ),
                "parameters": {
                    "user_id": "UUID of the user whose roles are being updated.",
                },
                "responses": {
                    "200": "User roles updated and caches invalidated successfully.",
                    "400": "One or more role names are invalid.",
                    "401": "Unauthorized: Access token missing or invalid.",
                    "403": "Forbidden: Requires super_admin role and roles:manage permission.",
                    "404": "User not found.",
                },
            },
            ("/api/v1/users/{user_id}", "delete"): {
                "summary": "Deactivate User",
                "description": (
                    "Soft-delete/deactivate user, clear caches, and queue search index removal "
                    "(requires 'users:delete' permission)."
                ),
                "parameters": {
                    "user_id": "UUID of the user to deactivate.",
                },
                "responses": {
                    "204": "User deactivated successfully (no content).",
                    "401": "Unauthorized: Access token missing or invalid.",
                    "403": "Forbidden: Missing required 'users:delete' permission.",
                    "404": "User not found.",
                },
            },
        },
        "common_parameters": {
            "limit": "Maximum number of records to return (1-200).",
            "offset": "Number of records to skip for pagination.",
            "q": "Search query string.",
            "user_id": "Target user UUID.",
            "lang": "Language code for localized response (e.g., 'en', 'bn').",
        },
        "common_responses": {
            "200": "Successful operation.",
            "201": "Resource created successfully.",
            "204": "Operation succeeded with no content.",
            "400": "Bad Request: Invalid payload or parameters.",
            "401": "Unauthorized: Missing, invalid, or expired authentication token.",
            "403": "Forbidden: Insufficient privileges or missing required permissions.",
            "404": "Not Found: The requested resource does not exist.",
            "409": "Conflict: Resource conflict (e.g. duplicate unique value).",
            "422": "Validation Error: Request payload failed validation.",
            "500": "Internal Server Error.",
        },
    },
    "messages": {
        # Auth & Tokens
        "Invalid email or password": "Invalid email or password",
        "Invalid or expired access token": "Invalid or expired access token",
        "Invalid or expired refresh token": "Invalid or expired refresh token",
        "Token has been revoked": "Token has been revoked",
        "Refresh token has been revoked or used": "Refresh token has been revoked or used",
        "User inactive or not found": "User inactive or not found",
        "Invalid refresh token": "Invalid refresh token",
        "Successfully logged out": "Successfully logged out",
        "Access token required": "Access token required",
        "Not a refresh token": "Not a refresh token",
        # User & RBAC
        "User not found": "User not found",
        "Only a role manager can assign roles during user creation": (
            "Only a role manager can assign roles during user creation"
        ),
        "Email already registered": "Email already registered",
        "Phone already registered": "Phone already registered",
        "Email or phone already registered": "Email or phone already registered",
        "One or more role names are invalid": "One or more role names are invalid",
        "Invalid search query": "Invalid search query",
        "Missing required permissions: {permissions}": (
            "Missing required permissions: {permissions}"
        ),
        "Required one of roles: {roles}": "Required one of roles: {roles}",
        # Validation
        "Password must be at most 72 UTF-8 bytes": "Password must be at most 72 UTF-8 bytes",
        "Role names must be unique": "Role names must be unique",
        # Health
        "ok": "ok",
    },
}
