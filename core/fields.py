from __future__ import annotations

from datetime import date
from typing import Any

from django.db import models

from core.services.pii import decrypt_value
from core.services.pii import encrypt_value
from core.services.pii import is_encrypted_payload


class _EncryptedMixin:
    """Store field values encrypted in a text column and expose plaintext in Python."""

    description = "Encrypted field"

    def db_type(self, connection) -> str | None:
        return models.TextField().db_type(connection)

    def from_db_value(self, value: Any, expression, connection) -> Any:
        return self.to_python(value)

    def get_prep_value(self, value: Any) -> str | None:
        plaintext = self._serialize_plaintext(value)
        if plaintext in (None, ""):
            return plaintext
        return encrypt_value(plaintext)

    def to_python(self, value: Any) -> Any:
        if value in self.empty_values:
            return value
        if self._is_python_value(value):
            return value
        if isinstance(value, str) and is_encrypted_payload(value):
            value = decrypt_value(value)
        return self._deserialize_plaintext(value)

    def deconstruct(self) -> tuple[str, str, list[Any], dict[str, Any]]:
        name, path, args, kwargs = super().deconstruct()
        path = f"{self.__class__.__module__}.{self.__class__.__name__}"
        return name, path, args, kwargs

    def _is_python_value(self, value: Any) -> bool:
        return False

    def _serialize_plaintext(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return str(value)

    def _deserialize_plaintext(self, value: Any) -> Any:
        return value


class EncryptedCharField(_EncryptedMixin, models.CharField):
    pass


class EncryptedEmailField(_EncryptedMixin, models.EmailField):
    pass


class EncryptedTextField(_EncryptedMixin, models.TextField):
    pass


class EncryptedDateField(_EncryptedMixin, models.DateField):
    def _is_python_value(self, value: Any) -> bool:
        return isinstance(value, date)

    def _serialize_plaintext(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, date):
            return value.isoformat()
        python_value = models.DateField.to_python(self, value)
        if python_value is None:
            return None
        return python_value.isoformat()

    def _deserialize_plaintext(self, value: Any) -> date | None:
        if value in self.empty_values:
            return None
        return models.DateField.to_python(self, value)
