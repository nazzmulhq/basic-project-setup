# FastAPI Enterprise Architecture Blueprint

An async FastAPI service using SQLAlchemy 2, PostgreSQL through PgBouncer, RBAC,
AES-256-GCM encrypted PII, Redis Cluster-backed JWT sessions, Tantivy-py full-text
search, and a transactional outbox.

## Architecture

```text
BOOT
 FastAPI lifespan
   ├─ Direct PostgreSQL connection -> advisory lock -> Alembic upgrade to head
   ├─ Initialize Redis Cluster and the persistent Tantivy index
   ├─ Idempotent seed -> permissions, roles, bootstrap administrator
   ├─ Populate an empty search index from PostgreSQL
   └─ Recover and publish outbox backlog -> start relay worker

REQUEST
 HTTP -> Router -> FastAPI dependencies (JWT, Redis blocklist, live RBAC)
       -> Service -> Repository -> AsyncSession -> PgBouncer -> PostgreSQL
                    ├─ user data and outbox event commit atomically
                    ├─ best-effort profile/RBAC cache updates
                    └─ Tantivy full-text search

OUTBOX
 PostgreSQL FOR UPDATE SKIP LOCKED -> Tantivy document upsert/delete
   ├─ success -> PUBLISHED
   └─ failure -> exponential retry -> DEAD_LETTER after 10 attempts
```

FastAPI's native `Depends()` and `Annotated` provide dependency injection; no
additional DI framework is used. A request database session is injected into the
repositories and services. PostgreSQL is authoritative for user and authorization
state; Redis supports token revocation and caching. User changes and their outbox
records are committed in the same PostgreSQL transaction, while the background
relay synchronizes search documents to the on-disk Tantivy index.

## Project structure

```text
.
├── app/
│   ├── main.py                     # FastAPI app, lifespan, router registration, health endpoint
│   ├── api/v1/
│   │   ├── auth.py                 # Login, refresh, logout, current identity routes
│   │   └── users.py                # User and role routes
│   ├── schemas/
│   │   ├── auth.py                 # Authentication request/response models
│   │   └── user.py                 # User and role request/response models
│   ├── services/
│   │   ├── auth_service.py         # Authentication, token lifecycle, and auth service dependency
│   │   └── user_service.py         # User business rules and user service dependency
│   ├── repositories/
│   │   ├── user_repository.py      # User queries, persistence, and repository dependency
│   │   ├── rbac_repository.py      # Role/permission queries and repository dependency
│   │   └── outbox_repository.py    # Outbox event staging and repository dependency
│   ├── models/
│   │   ├── base.py                 # SQLAlchemy declarative base
│   │   ├── user.py                 # User entity and encrypted PII columns
│   │   ├── rbac.py                 # Role, permission, and association tables
│   │   └── outbox.py               # Transactional outbox event
│   ├── core/
│   │   ├── dependencies.py         # Current principal and auth/RBAC checks
│   │   ├── session.py              # Async SQLAlchemy engine, session factory, DB dependency
│   │   ├── config.py               # Environment-backed application settings
│   │   ├── security/
│   │   │   ├── aead.py             # AES-GCM encryption and blind indexes
│   │   │   ├── jwt.py              # JWT creation and Redis key helpers
│   │   │   └── password.py         # bcrypt hashing and verification
│   │   ├── redis_cluster.py        # Redis Cluster client lifecycle
│   │   ├── tantivy_search.py       # Persistent Tantivy index and search operations
│   │   └── migration_runner.py    # Startup Alembic upgrade and advisory lock
│   ├── db/seeder.py                # Idempotent RBAC/admin seed and search index setup
│   └── workers/outbox_relay.py     # Transactional outbox to Tantivy relay
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                   # Reviewed, version-controlled schema migrations
├── tests/
│   ├── conftest.py                 # Test environment settings
│   ├── test_application.py         # Route registration test
│   ├── test_security.py            # Encryption, password, and JWT tests
│   └── test_tantivy_search.py      # Tantivy indexing, search, update, and persistence tests
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml
└── README.md
```

## Complete request example: router → service → repository → database

This example follows `GET /api/v1/users`. FastAPI validates the query parameters,
resolves the service and its dependencies, runs the permission dependency, and then
calls the router handler. The service calls the repository, which executes a
SQLAlchemy query through the injected `AsyncSession`.

### 1. Router — `app/api/v1/users.py`

```python
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
```

The route is registered under `/api/v1`, so its URL is `/api/v1/users`. Before the
handler runs, `require_permissions` resolves the current principal. The application
validates the access token, checks its Redis blocklist entry, loads the active user
and current roles/permissions from PostgreSQL, and rejects callers without
`users:read`.

### 2. Dependency wiring — repository and service modules

```python
from app.repositories.user_repository import UserRepositoryDeps
from app.services.user_service import UserServiceDeps
```

Repository dependency providers and aliases live beside their repository classes.
Likewise, `get_user_service` and `UserServiceDeps` live in
`app/services/user_service.py`; auth service wiring lives in
`app/services/auth_service.py`. `app/core/dependencies.py` is reserved for the
authenticated principal and permission/role checks.

The database session comes from `app/core/session.py`. FastAPI caches dependencies
per request, so the repository and service receive the request's shared session:

```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

### 3. Service — `app/services/user_service.py`

```python
async def get_users(self, limit: int = 50, offset: int = 0) -> list[UserResponse]:
    users = await self.repository.get_all(limit=limit, offset=offset)
    return [self._to_response(user) for user in users]


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
```

The SQLAlchemy encrypted-column type decrypts email and phone values when they are
loaded. The response schema determines which fields are returned.

### 4. Repository — `app/repositories/user_repository.py`

```python
async def get_all(self, limit: int = 50, offset: int = 0) -> Sequence[User]:
    stmt = (
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return (await self.db.execute(stmt)).scalars().all()
```

### 5. SQLAlchemy model — `app/models/user.py`

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(120), index=True)
    email_encrypted: Mapped[str] = mapped_column(
        EncryptedString(aad_context="users.email"), nullable=False
    )
    phone_encrypted: Mapped[str] = mapped_column(
        EncryptedString(aad_context="users.phone"), nullable=False
    )
    nid_encrypted: Mapped[str] = mapped_column(
        EncryptedString(aad_context="users.nid"), nullable=False
    )
    email_bidx: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    phone_bidx: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    roles: Mapped[list[Role]] = relationship(secondary=user_roles, lazy="selectin")
```

Writes follow the same layers. For `POST /api/v1/users`, `CreateUserRequest` validates
the payload, `UserService` applies business rules, `UserRepository` stages the user,
and the service commits the user and its outbox event together. The outbox relay
updates the Tantivy index asynchronously; the API does not write to the index
directly.

## Start locally with Docker Compose

Requirements: Docker Compose v2.24+ and persistent disk space for the Tantivy index.

1. Copy `.env.example` to `.env`. Set strong, unique values for the encryption keys,
   JWT secret, and bootstrap administrator password. Generate each 32-byte key with:

   ```sh
   python -c "import base64, secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
   ```

   Generate this separately for `AES_256_MASTER_KEY_B64` and `BLIND_INDEX_KEY_B64`.
   Set `JWT_SECRET` to at least 32 random bytes. Never use example credentials outside
   a disposable local environment.
2. Set `POSTGRES_PASSWORD` in `.env`. Compose uses it for PostgreSQL and PgBouncer
   and injects it into the API's database URLs. When running without Compose, put
   matching credentials in `DATABASE_URL` and `DIRECT_DATABASE_URL`.
3. Start the stack:

   ```sh
   docker compose up --build
   ```

   Compose starts PostgreSQL, PgBouncer in transaction-pooling mode, a three-primary
   Redis Cluster, and the API. The API applies migrations, seeds default RBAC data
   and the bootstrap administrator, builds the on-disk index if empty, then starts
   the outbox relay. Compose stores the Tantivy index in the `tantivy-data` volume.
4. Open `http://localhost:8000/docs`; liveness endpoint: `http://localhost:8000/health`.

The included Compose Redis setup is a local-development cluster without replicas or
authentication. Configure protected Redis nodes, replicas, TLS, persistent backups
for the Tantivy volume, and managed PostgreSQL for production. Tantivy is embedded:
run one API process per index directory; it is not a shared search server.

## Run without Docker

Use Python 3.11+, PostgreSQL, PgBouncer (transaction pooling), and Redis Cluster.
The application creates its Tantivy index under `SEARCH_INDEX_PATH` (default
`.data/tantivy`). Create a virtual environment and install the project:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` with service addresses and generated secrets, then run:

```sh
uvicorn app.main:app --reload
```

`DATABASE_URL` is the runtime PgBouncer URL; `DIRECT_DATABASE_URL` must bypass
PgBouncer and point to PostgreSQL for DDL and advisory locks. Keep the search index
directory on persistent local storage and do not share it between app processes.

## Authentication and authorization

Login with the bootstrap administrator values configured in `.env`:

```http
POST /api/v1/auth/login
Content-Type: application/json

{"email":"admin@example.test","password":"your-configured-bootstrap-password"}
```

Send the returned access token on protected routes using the bearer scheme:

```http
GET /api/v1/users
Authorization: Bearer <access-token>
```

`POST /api/v1/auth/refresh` rotates a single-use refresh token.
`POST /api/v1/auth/logout` blocklists the current access token; optionally send a
`refresh_token` body to revoke that session too. `GET /api/v1/auth/me` reports the
authenticated identity and current permissions.

Seeded roles:

| Role | Permissions |
|---|---|
| `super_admin` | `users:read`, `users:write`, `users:delete`, `roles:manage` |
| `manager` | `users:read`, `users:write` |
| `viewer` | `users:read` |

Endpoints:

| Method | Path | Required permission |
|---|---|---|
| `GET` | `/api/v1/users` | `users:read` |
| `GET` | `/api/v1/users/search?q=...` | `users:read` |
| `POST` | `/api/v1/users` | `users:write` |
| `PUT` | `/api/v1/users/{user_id}/roles` | `super_admin` and `roles:manage` |
| `DELETE` | `/api/v1/users/{user_id}` | `users:delete` |

Non-admin callers may create users only with the default `viewer` role. Role
assignment is restricted to the super administrator.

## Schema changes and automatic migration

1. Add the SQLAlchemy model and import it from `app/models/__init__.py`.
2. Generate and review a versioned migration:

   ```sh
   alembic revision --autogenerate -m "add_products"
   ```

3. Commit the reviewed migration. Every application startup takes a PostgreSQL
   advisory lock on the direct connection and runs `alembic upgrade head`.

Migrations are not generated automatically at runtime: reviewed, version-controlled
migrations avoid unsafe DDL inference in production. The initial schema is included
in `alembic/versions/0001_initial_schema.py`; the next migration renames the outbox
target column for the Tantivy-backed index.

## Security and reliability notes

- AES-256-GCM uses random 96-bit nonces, a versioned ciphertext format, and
  column-specific AAD. HMAC-SHA256 blind indexes support exact email/phone lookups
  without storing the plaintext in searchable columns. Blind indexes leak equality;
  protect access to the database and rotate keys with an explicit data migration.
- The bootstrap password is configured through the environment and stored as a
  bcrypt hash. Rotate it after first deployment. Do not put secrets in source control.
- Tantivy documents contain names and blind indexes, never raw email, phone,
  NID, or passwords. Review any future indexed fields for PII before adding them.
- PostgreSQL user changes and their outbox records commit atomically. The relay uses
  idempotent document IDs, `SKIP LOCKED`, startup recovery, retries,
  and a dead-letter state. Inspect and replay dead-letter rows operationally.
- Redis keys use `{user_id}` hash tags where a user's auth/session data must share a
  cluster slot. Token blocklists are read from the Redis primary; PostgreSQL remains
  authoritative for RBAC, and cache values never grant permissions. Redis is a
  runtime service dependency; Tantivy runs in-process, and search/index errors are
  surfaced to API requests or retried by the outbox worker.
- The `/health` endpoint is liveness-only. Configure infrastructure health probes
  and alerting for PostgreSQL, Redis, Tantivy index storage, and the outbox backlog.

## Tests and lint

```sh
pytest
ruff check .
```
