import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("DIRECT_DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("AES_256_MASTER_KEY_B64", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
os.environ.setdefault("BLIND_INDEX_KEY_B64", "ZmVkY2JhOTg3NjU0MzIxMGZlZGNiYTk4NzY1NDMyMTA=")
os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-that-is-at-least-32-bytes")
os.environ.setdefault("DEFAULT_ADMIN_EMAIL", "admin@example.test")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "test-only-password-not-for-use")
os.environ.setdefault("DEFAULT_ADMIN_PHONE", "+10000000000")
os.environ.setdefault("DEFAULT_ADMIN_NID", "test-only-nid")
