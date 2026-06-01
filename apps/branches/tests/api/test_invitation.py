from __future__ import annotations

from unittest.mock import patch

import pytest
from accounts.models import User
from accounts.tests.factories import UserFactory
from branches.api.views import BranchAdminCompleteInvitationView
from branches.api.views import BranchAdminInviteView
from branches.models import BranchAdmin
from branches.tests.factories import BranchAdminFactory
from branches.tests.factories import BranchFactory
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIRequestFactory


@pytest.mark.django_db
class TestBranchAdminInviteView:
    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    @patch("accounts.email.send_email_task.delay")
    def test_invite_success(
        self,
        mock_send_email,
        api_rf: APIRequestFactory,
        settings,
    ):
        settings.FRONTEND_BRANCH_ADMIN_DOMAIN = "https://branches.kelem.app"
        settings.FRONTEND_ROLE_DOMAINS = {
            **settings.FRONTEND_ROLE_DOMAINS,
            User.Role.BRANCH_ADMIN: settings.FRONTEND_BRANCH_ADMIN_DOMAIN,
        }
        user = UserFactory()
        branch = BranchFactory(school__organization__owner=user)

        view = BranchAdminInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "email": "newadmin@example.com",
                "name": "New",
                "father_name": "Admin",
                "grandfather_name": "Test",
                "role_title": "Branch Manager",
                "branch": branch.id,
            },
        )
        request.user = user

        response = view(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["message"] == "Invitation sent successfully."
        assert response.data["invitation_url"].startswith(
            settings.FRONTEND_BRANCH_ADMIN_DOMAIN,
        )
        assert "/complete-invitation/" in response.data["invitation_url"]

        # Verify user created
        new_user = User.objects.by_email("newadmin@example.com").get()
        assert new_user.name == "New"
        assert new_user.role == User.Role.BRANCH_ADMIN
        assert new_user.is_active is False

        # Verify branch admin created
        admin = BranchAdmin.objects.get(user=new_user)
        assert admin.branch == branch
        assert admin.status == BranchAdmin.Status.INACTIVE

        # Verify email task called
        assert mock_send_email.called

    def test_invite_not_owner_permission_denied(self, api_rf: APIRequestFactory):
        user = UserFactory()
        other_user = UserFactory()
        branch = BranchFactory(school__organization__owner=other_user)

        view = BranchAdminInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "email": "newadmin@example.com",
                "name": "New",
                "father_name": "Admin",
                "grandfather_name": "Test",
                "role_title": "Branch Manager",
                "branch": branch.id,
            },
        )
        request.user = user

        response = view(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # The error format is {'errors': [{'code': 'invalid', 'detail': '...', 'field': 'branch'}]} # noqa: E501
        assert "errors" in response.data
        assert response.data["errors"][0]["field"] == "branch"

    @patch("accounts.email.send_email_task.delay")
    def test_reinvite_updates_existing_inactive_branch_admin(
        self,
        mock_send_email,
        api_rf: APIRequestFactory,
    ):
        owner = UserFactory()
        old_branch = BranchFactory(school__organization__owner=owner)
        new_branch = BranchFactory(school__organization__owner=owner)
        user = UserFactory(
            email="existingadmin@example.com",
            role=User.Role.BRANCH_ADMIN,
            is_active=False,
            name="Old",
            father_name="Branch",
            grandfather_name="Admin",
        )
        admin = BranchAdminFactory(
            user=user,
            organization=old_branch.organization,
            branch=old_branch,
            role_title="Old Title",
            status=BranchAdmin.Status.ACTIVE,
        )

        view = BranchAdminInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "email": "existingadmin@example.com",
                "name": "Updated",
                "father_name": "Branch",
                "grandfather_name": "Lead",
                "role_title": "Branch Manager",
                "branch": new_branch.id,
            },
        )
        request.user = owner

        response = view(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["invitation_url"].startswith(
            settings.FRONTEND_DOMAIN,
        )
        assert "/complete-invitation/" in response.data["invitation_url"]
        user.refresh_from_db()
        admin.refresh_from_db()
        assert User.objects.by_email("existingadmin@example.com").count() == 1
        assert user.name == "Updated"
        assert user.father_name == "Branch"
        assert user.grandfather_name == "Lead"
        assert user.is_active is False
        assert user.verified_at is None
        assert admin.organization == new_branch.organization
        assert admin.branch == new_branch
        assert admin.role_title == "Branch Manager"
        assert admin.status == BranchAdmin.Status.INACTIVE
        assert mock_send_email.called

    def test_invite_rejects_existing_active_branch_admin(
        self,
        api_rf: APIRequestFactory,
    ):
        owner = UserFactory()
        branch = BranchFactory(school__organization__owner=owner)
        user = UserFactory(
            email="activeadmin@example.com",
            role=User.Role.BRANCH_ADMIN,
            is_active=True,
        )
        BranchAdminFactory(
            user=user,
            organization=branch.organization,
            branch=branch,
            status=BranchAdmin.Status.ACTIVE,
        )

        view = BranchAdminInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "email": "activeadmin@example.com",
                "name": "Active",
                "father_name": "Branch",
                "grandfather_name": "Admin",
                "role_title": "Branch Manager",
                "branch": branch.id,
            },
        )
        request.user = owner

        response = view(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "errors" in response.data
        assert response.data["errors"][0]["field"] == "email"

    def test_invite_rejects_existing_user_with_wrong_role(
        self,
        api_rf: APIRequestFactory,
    ):
        owner = UserFactory()
        branch = BranchFactory(school__organization__owner=owner)
        UserFactory(
            email="wrongrole@example.com",
            role=User.Role.TEACHER,
            is_active=False,
        )

        view = BranchAdminInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "email": "wrongrole@example.com",
                "name": "Wrong",
                "father_name": "Role",
                "grandfather_name": "User",
                "role_title": "Branch Manager",
                "branch": branch.id,
            },
        )
        request.user = owner

        response = view(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "errors" in response.data
        assert response.data["errors"][0]["field"] == "email"

    @patch("accounts.email.send_email_task.delay", side_effect=RuntimeError("boom"))
    def test_invite_rolls_back_reinvite_when_email_send_fails(
        self,
        mock_send_email,
        api_rf: APIRequestFactory,
    ):
        owner = UserFactory()
        original_branch = BranchFactory(school__organization__owner=owner)
        target_branch = BranchFactory(school__organization__owner=owner)
        user = UserFactory(
            email="rollbackadmin@example.com",
            role=User.Role.BRANCH_ADMIN,
            is_active=False,
            name="Original",
            father_name="Branch",
            grandfather_name="Admin",
        )
        admin = BranchAdminFactory(
            user=user,
            organization=original_branch.organization,
            branch=original_branch,
            role_title="Original Title",
            status=BranchAdmin.Status.ACTIVE,
        )

        view = BranchAdminInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "email": "rollbackadmin@example.com",
                "name": "Updated",
                "father_name": "Branch",
                "grandfather_name": "Lead",
                "role_title": "Updated Title",
                "branch": target_branch.id,
            },
        )
        request.user = owner

        with pytest.raises(RuntimeError, match="boom"):
            view(request)

        assert mock_send_email.called
        user.refresh_from_db()
        admin.refresh_from_db()
        assert user.name == "Original"
        assert admin.branch == original_branch
        assert admin.role_title == "Original Title"


@pytest.mark.django_db
class TestBranchAdminCompleteInvitationView:
    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    def test_complete_success(self, api_rf: APIRequestFactory):
        user = UserFactory(role=User.Role.BRANCH_ADMIN, is_active=False)
        branch_admin = BranchAdminFactory(user=user, status=BranchAdmin.Status.INACTIVE)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        view = BranchAdminCompleteInvitationView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "uid": uid,
                "token": token,
                "new_password": "new_secure_password",
            },
        )

        response = view(request)

        assert response.status_code == status.HTTP_200_OK
        assert (
            response.data["message"]
            == "Password set and account activated successfully."
        )

        # Verify password changed, is_active, and verified_at set
        user.refresh_from_db()
        assert user.check_password("new_secure_password")
        assert user.is_active is True
        assert user.verified_at is not None

        # Verify branch admin status
        branch_admin.refresh_from_db()
        assert branch_admin.status == BranchAdmin.Status.ACTIVE

    def test_complete_invalid_token(self, api_rf: APIRequestFactory):
        user = UserFactory(role=User.Role.BRANCH_ADMIN, is_active=False)
        BranchAdminFactory(user=user, status=BranchAdmin.Status.INACTIVE)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = "invalid-token"  # noqa: S105

        view = BranchAdminCompleteInvitationView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "uid": uid,
                "token": token,
                "new_password": "new_secure_password",
            },
        )

        response = view(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "errors" in response.data
        assert response.data["errors"][0]["field"] == "token"

    def test_complete_rejects_non_invited_user(self, api_rf: APIRequestFactory):
        user = UserFactory(is_active=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        view = BranchAdminCompleteInvitationView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "uid": uid,
                "token": token,
                "new_password": "new_secure_password",
            },
        )

        response = view(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "errors" in response.data
        assert response.data["errors"][0]["field"] == "uid"
