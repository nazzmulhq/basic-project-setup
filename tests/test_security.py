import base64

import pytest
from cryptography.exceptions import InvalidTag
from pydantic import ValidationError

from app.core.security.aead import AEADCipher
from app.core.security.jwt import create_token_pair, decode_jwt
from app.core.security.password import hash_password, verify_password
from app.schemas.auth import LoginRequest


@pytest.fixture
def cipher() -> AEADCipher:
    key = base64.b64encode(b"a" * 32).decode()
    blind_key = base64.b64encode(b"b" * 32).decode()
    return AEADCipher(key, blind_key)


def test_aead_round_trip_and_random_nonce(cipher: AEADCipher) -> None:
    first = cipher.encrypt("sensitive-value", "users.email")
    second = cipher.encrypt("sensitive-value", "users.email")
    assert first != second
    assert cipher.decrypt(first, "users.email") == "sensitive-value"


def test_aead_authenticates_associated_data(cipher: AEADCipher) -> None:
    token = cipher.encrypt("sensitive-value", "users.email")
    with pytest.raises(InvalidTag):
        cipher.decrypt(token, "users.phone")


def test_blind_index_is_normalized_and_deterministic(cipher: AEADCipher) -> None:
    assert cipher.blind_index(" Person@Example.Test ") == cipher.blind_index("person@example.test")


def test_password_hash_verification() -> None:
    hashed = hash_password("a-long-test-password")
    assert verify_password("a-long-test-password", hashed)
    assert not verify_password("wrong-password", hashed)


def test_login_rejects_bcrypt_oversized_passwords() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email="person@example.test", password="é" * 40)


def test_jwt_token_pair_has_distinct_access_and_refresh_claims() -> None:
    tokens = create_token_pair("user-id", ["viewer"], ["users:read"])
    access = decode_jwt(tokens["access_token"])
    refresh = decode_jwt(tokens["refresh_token"])
    assert access["type"] == "access"
    assert refresh["type"] == "refresh"
    assert access["jti"] != refresh["jti"]
    assert access["permissions"] == ["users:read"]
