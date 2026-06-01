from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from accounts.models import User

if TYPE_CHECKING:
    from accounts.models import User


def test_user_get_absolute_url(user: User):
    assert user.get_absolute_url() == f"/users/{user.pk}/"


@pytest.mark.django_db
def test_user_save_normalizes_phone_number():
    user = User.objects.create_user(
        email="normalized@example.com",
        password="strong-password-123",
        phone_number="251 911 111 111",
    )

    assert user.phone_number == "+251911111111"
