import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.core.config import settings


class AEADCipher:
    def __init__(self, master_key_b64: str, blind_index_key_b64: str) -> None:
        self._aead = AESGCM(base64.b64decode(master_key_b64, validate=True))
        self._blind_key = base64.b64decode(blind_index_key_b64, validate=True)

    def encrypt(self, plaintext: str, aad: str) -> str:
        nonce = os.urandom(12)
        ciphertext = self._aead.encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))
        payload = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return f"v1:{payload}"

    def decrypt(self, token: str, aad: str) -> str:
        version, separator, encoded = token.partition(":")
        if not separator or version != "v1":
            raise ValueError("Unsupported or malformed encrypted value")
        raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
        if len(raw) < 12 + 16:
            raise ValueError("Encrypted value is too short")
        return self._aead.decrypt(raw[:12], raw[12:], aad.encode("utf-8")).decode("utf-8")

    def blind_index(self, value: str) -> str:
        normalized = value.strip().casefold().encode("utf-8")
        return hmac.new(self._blind_key, normalized, hashlib.sha256).hexdigest()


aead_cipher = AEADCipher(
    settings.aes_256_master_key_b64.get_secret_value(),
    settings.blind_index_key_b64.get_secret_value(),
)


class EncryptedString(TypeDecorator[str]):
    impl = String
    cache_ok = True

    def __init__(self, aad_context: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.aad_context = aad_context

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return aead_cipher.encrypt(value, self.aad_context)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return aead_cipher.decrypt(value, self.aad_context)
