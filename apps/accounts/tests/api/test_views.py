from __future__ import annotations

from http import HTTPStatus

import pytest
from accounts.api.views import UserViewSet
from accounts.models import User
from rest_framework.test import APIClient
from rest_framework.test import APIRequestFactory


class TestUserViewSet:
    @pytest.fixture
    def api_client(self) -> APIClient:
        return APIClient()

    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    def test_get_queryset(self, user: User, api_rf: APIRequestFactory):
        other_user = type(user).objects.create_user(
            email="other@example.com",
            password="test-pass",  # noqa: S106
        )
        view = UserViewSet()
        request = api_rf.get("/fake-url/")
        request.user = user

        view.request = request

        queryset = view.get_queryset()

        assert list(queryset) == [user]
        assert other_user not in queryset

    def test_me(self, user: User, api_rf: APIRequestFactory):
        request = api_rf.get("/fake-url/")
        request.user = user

        response = UserViewSet.as_view({"get": "me"})(request)

        assert response.data == {
            "id": str(user.id),
            "name": user.name,
            "father_name": user.father_name,
            "grandfather_name": user.grandfather_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "address": user.address,
            "role": user.role,
            "verified_at": user.verified_at,
            "created_at": user.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": user.updated_at.isoformat().replace("+00:00", "Z"),
        }

    @pytest.mark.django_db
    def test_partial_update_allows_role(self, user: User, api_client: APIClient):
        api_client.force_authenticate(user=user)

        response = api_client.patch(
            f"/api/users/{user.id}/",
            {"role": User.Role.ORGANIZATION},
            format="json",
        )

        assert response.status_code == HTTPStatus.OK

        user.refresh_from_db()
        assert user.role == User.Role.ORGANIZATION
        assert response.data["role"] == User.Role.ORGANIZATION
