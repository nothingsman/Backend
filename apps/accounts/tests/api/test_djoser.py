from http import HTTPStatus
from unittest.mock import Mock

import pytest
from accounts.models import User
from rest_framework.test import APIClient


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture(autouse=True)
def mock_async_email(monkeypatch: pytest.MonkeyPatch) -> Mock:
    delayed_task = Mock()
    monkeypatch.setattr("accounts.email.send_email_task.delay", delayed_task)
    return delayed_task


@pytest.mark.django_db
def test_user_signup_accepts_extended_profile_fields(api_client: APIClient):
    payload = {
        "email": "new-user@example.com",
        "password": "strong-password-123",
        "name": "New User",
        "father_name": "John Doe",
        "grandfather_name": "James Doe",
        "phone_number": "+15555550123",
        "address": "123 Main Street",
    }

    response = api_client.post("/auth/users/", payload, format="json")

    assert response.status_code == HTTPStatus.CREATED

    user = User.objects.get(email=payload["email"])
    assert user.name == payload["name"]
    assert user.father_name == payload["father_name"]
    assert user.grandfather_name == payload["grandfather_name"]
    assert user.phone_number == payload["phone_number"]
    assert user.address == payload["address"]
    assert user.check_password(payload["password"])


@pytest.mark.django_db
def test_user_signup_allows_address_to_be_omitted(api_client: APIClient):
    payload = {
        "email": "new-user-no-address@example.com",
        "password": "strong-password-123",
        "name": "New User",
        "father_name": "John Doe",
        "grandfather_name": "James Doe",
        "phone_number": "+15555550124",
    }

    response = api_client.post("/auth/users/", payload, format="json")

    assert response.status_code == HTTPStatus.CREATED

    user = User.objects.get(email=payload["email"])
    assert user.address == ""


@pytest.mark.django_db
def test_user_signup_does_not_require_username(api_client: APIClient):
    payload = {
        "email": "new-user-no-username@example.com",
        "password": "strong-password-123",
        "name": "No Username",
    }

    response = api_client.post("/auth/users/", payload, format="json")

    assert response.status_code == HTTPStatus.CREATED
    assert User.objects.filter(email=payload["email"]).exists()


@pytest.mark.django_db
def test_user_signup_allows_role_selection(api_client: APIClient):
    payload = {
        "email": "org-owner@example.com",
        "password": "strong-password-123",
        "name": "Org Owner",
        "role": User.Role.ORGANIZATION,
    }

    response = api_client.post("/auth/users/", payload, format="json")

    assert response.status_code == HTTPStatus.CREATED
    assert response.data["role"] == User.Role.ORGANIZATION

    user = User.objects.get(email=payload["email"])
    assert user.role == User.Role.ORGANIZATION


@pytest.mark.django_db
def test_user_signup_rejects_privileged_fields(api_client: APIClient):
    payload = {
        "email": "privileged@example.com",
        "password": "strong-password-123",
        "name": "Privileged User",
        "is_superuser": True,
    }

    response = api_client.post("/auth/users/", payload, format="json")

    assert response.status_code == HTTPStatus.BAD_REQUEST
    error = response.data["errors"][0]
    assert error["field"] == "is_superuser"
    assert error["detail"] == "This field may not be set during signup."
    assert not User.objects.filter(email=payload["email"]).exists()
