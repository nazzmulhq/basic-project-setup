import base64
import binascii
import os
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(alias="DATABASE_URL")
    direct_database_url: str = Field(alias="DIRECT_DATABASE_URL")
    redis_cluster_nodes: list[str] = Field(default=["localhost:6379"], alias="REDIS_CLUSTER_NODES")
    redis_password: SecretStr | None = Field(default=None, alias="REDIS_PASSWORD")
    search_index_path: str = Field(default=".data/tantivy", alias="SEARCH_INDEX_PATH")
    aes_256_master_key_b64: SecretStr = Field(alias="AES_256_MASTER_KEY_B64")
    blind_index_key_b64: SecretStr = Field(alias="BLIND_INDEX_KEY_B64")
    jwt_secret: SecretStr = Field(alias="JWT_SECRET")
    access_token_expire_minutes: int = Field(default=15, gt=0, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, gt=0, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    default_admin_email: str = Field(alias="DEFAULT_ADMIN_EMAIL")
    default_admin_password: SecretStr = Field(alias="DEFAULT_ADMIN_PASSWORD")
    default_admin_phone: str = Field(alias="DEFAULT_ADMIN_PHONE")
    default_admin_nid: SecretStr = Field(alias="DEFAULT_ADMIN_NID")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @field_validator("redis_password", mode="before")
    @classmethod
    def normalize_empty_optional_values(cls, value):
        return None if value == "" else value

    @field_validator("aes_256_master_key_b64", "blind_index_key_b64")
    @classmethod
    def validate_key(cls, value: SecretStr) -> SecretStr:
        try:
            decoded = base64.b64decode(value.get_secret_value(), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Encryption keys must be valid Base64") from exc
        if len(decoded) != 32:
            raise ValueError("AES and blind-index keys must each decode to exactly 32 bytes")
        return value

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes")
        return value

    @model_validator(mode="after")
    def validate_different_encryption_keys(self) -> "Settings":
        if (
            self.aes_256_master_key_b64.get_secret_value()
            == self.blind_index_key_b64.get_secret_value()
        ):
            raise ValueError("AES_256_MASTER_KEY_B64 and BLIND_INDEX_KEY_B64 must differ")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings.model_validate(dict(os.environ))


settings = get_settings()
