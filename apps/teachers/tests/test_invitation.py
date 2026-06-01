from __future__ import annotations

from unittest.mock import patch

import pytest
from accounts.models import User
from accounts.tests.factories import UserFactory
from branches.models import BranchAdmin
from branches.tests.factories import BranchAdminFactory
from branches.tests.factories import BranchFactory
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIRequestFactory
from teachers.api.views import TeacherCompleteInvitationView
from teachers.api.views import TeacherInviteView
from teachers.models import Teacher


@pytest.mark.django_db
class TestTeacherInviteView:
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
        settings.FRONTEND_TEACHER_DOMAIN = "https://teachers.kelem.app"
        settings.FRONTEND_ROLE_DOMAINS = {
            **settings.FRONTEND_ROLE_DOMAINS,
            User.Role.TEACHER: settings.FRONTEND_TEACHER_DOMAIN,
        }
        user = UserFactory()
        branch = BranchFactory(school__organization__owner=user)

        view = TeacherInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "email": "newteacher@example.com",
                "name": "New",
                "father_name": "Teacher",
                "grandfather_name": "Test",
                "phone_number": "+251911111112",
                "specialization": "Mathematics",
                "branch": branch.id,
            },
        )
        request.user = user

        response = view(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["message"] == "Teacher invitation sent successfully."
        assert response.data["invitation_url"].startswith(
            settings.FRONTEND_TEACHER_DOMAIN,
        )
        assert "/complete-teacher-invitation/" in response.data["invitation_url"]

        new_user = User.objects.get(email="newteacher@example.com")
        assert new_user.name == "New"
        assert new_user.father_name == "Teacher"
        assert new_user.grandfather_name == "Test"
        assert new_user.phone_number == "+251911111112"
        assert new_user.role == User.Role.TEACHER
        assert new_user.is_active is False

        teacher = Teacher.objects.get(user=new_user)
        assert teacher.branch == branch
        assert teacher.organization == branch.organization
        assert teacher.specialization == "Mathematics"

        assert mock_send_email.called

    def test_invite_not_owner_permission_denied(self, api_rf: APIRequestFactory):
        user = UserFactory()
        other_user = UserFactory()
        branch = BranchFactory(school__organization__owner=other_user)

        view = TeacherInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "email": "newteacher@example.com",
                "name": "New",
                "father_name": "Teacher",
                "grandfather_name": "Test",
                "phone_number": "+251911111113",
                "specialization": "Mathematics",
                "branch": branch.id,
            },
        )
        request.user = user

        response = view(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "errors" in response.data
        assert response.data["errors"][0]["field"] == "branch"

    @patch("accounts.email.send_email_task.delay")
    def test_invite_allows_superuser_for_other_owners_branch(
        self,
        mock_send_email,
        api_rf: APIRequestFactory,
    ):
        superuser = UserFactory(is_superuser=True, is_staff=True)
        owner = UserFactory()
        branch = BranchFactory(school__organization__owner=owner)

        view = TeacherInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "email": "superteacher@example.com",
                "name": "Super",
                "father_name": "Teacher",
                "grandfather_name": "Test",
                "phone_number": "+251911111114",
                "specialization": "Science",
                "branch": branch.id,
            },
        )
        request.user = superuser

        response = view(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(email="superteacher@example.com").exists()
        assert Teacher.objects.filter(user__email="superteacher@example.com").exists()
        assert response.data["invitation_url"].startswith(settings.FRONTEND_DOMAIN)
        assert mock_send_email.called

    @patch("accounts.email.send_email_task.delay")
    def test_invite_allows_active_branch_admin_for_own_branch(
        self,
        mock_send_email,
        api_rf: APIRequestFactory,
    ):
        branch_admin_user = UserFactory()
        branch = BranchFactory()
        BranchAdminFactory(
            user=branch_admin_user,
            branch=branch,
            organization=branch.organization,
            status=BranchAdmin.Status.ACTIVE,
        )

        view = TeacherInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "email": "branchadminteacher@example.com",
                "name": "Branch",
                "father_name": "Admin",
                "grandfather_name": "Teacher",
                "phone_number": "+251911111115",
                "specialization": "Amharic",
                "branch": branch.id,
            },
        )
        request.user = branch_admin_user

        response = view(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(email="branchadminteacher@example.com").exists()
        assert Teacher.objects.filter(
            user__email="branchadminteacher@example.com",
            branch=branch,
        ).exists()
        assert response.data["invitation_url"].startswith(settings.FRONTEND_DOMAIN)
        assert mock_send_email.called

    @patch("accounts.email.send_email_task.delay", side_effect=RuntimeError("boom"))
    def test_invite_rolls_back_user_when_email_send_fails(
        self,
        mock_send_email,
        api_rf: APIRequestFactory,
    ):
        user = UserFactory()
        branch = BranchFactory(school__organization__owner=user)

        view = TeacherInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "email": "rollbackteacher@example.com",
                "name": "Rollback",
                "father_name": "Teacher",
                "grandfather_name": "Test",
                "phone_number": "+251911111116",
                "specialization": "Mathematics",
                "branch": branch.id,
            },
        )
        request.user = user

        with pytest.raises(RuntimeError, match="boom"):
            view(request)

        assert mock_send_email.called
        assert not User.objects.filter(email="rollbackteacher@example.com").exists()
        assert not Teacher.objects.filter(
            user__email="rollbackteacher@example.com",
        ).exists()

    @patch("accounts.email.send_email_task.delay")
    def test_reinvite_updates_existing_inactive_teacher(
        self,
        mock_send_email,
        api_rf: APIRequestFactory,
    ):
        owner = UserFactory()
        old_branch = BranchFactory(school__organization__owner=owner)
        new_branch = BranchFactory(school__organization__owner=owner)
        user = UserFactory(
            email="existingteacher@example.com",
            role=User.Role.TEACHER,
            is_active=False,
            name="Old",
            father_name="Value",
            grandfather_name="Here",
            phone_number="+251911111117",
        )
        teacher = Teacher.objects.create(
            user=user,
            organization=old_branch.organization,
            branch=old_branch,
            specialization="History",
        )

        view = TeacherInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "email": "existingteacher@example.com",
                "name": "Updated",
                "father_name": "Teacher",
                "grandfather_name": "Profile",
                "phone_number": "+251911111118",
                "specialization": "Physics",
                "branch": new_branch.id,
            },
        )
        request.user = owner

        response = view(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["invitation_url"].startswith(settings.FRONTEND_DOMAIN)
        assert "/complete-teacher-invitation/" in response.data["invitation_url"]
        user.refresh_from_db()
        teacher.refresh_from_db()
        assert User.objects.filter(email="existingteacher@example.com").count() == 1
        assert user.name == "Updated"
        assert user.father_name == "Teacher"
        assert user.grandfather_name == "Profile"
        assert user.phone_number == "+251911111118"
        assert user.is_active is False
        assert teacher.branch == new_branch
        assert teacher.organization == new_branch.organization
        assert teacher.specialization == "Physics"
        assert mock_send_email.called


@pytest.mark.django_db
class TestTeacherCompleteInvitationView:
    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    def test_complete_success(self, api_rf: APIRequestFactory):
        user = UserFactory(role=User.Role.TEACHER, is_active=False)
        branch = BranchFactory()
        Teacher.objects.create(
            user=user,
            organization=branch.organization,
            branch=branch,
            specialization="Mathematics",
        )

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        view = TeacherCompleteInvitationView.as_view()
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

        user.refresh_from_db()
        assert user.check_password("new_secure_password")
        assert user.is_active is True
        assert user.verified_at is not None

    def test_complete_invalid_token(self, api_rf: APIRequestFactory):
        branch = BranchFactory()
        user = UserFactory(role=User.Role.TEACHER, is_active=False)
        Teacher.objects.create(
            user=user,
            organization=branch.organization,
            branch=branch,
        )

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = "invalid-token"  # noqa: S105

        view = TeacherCompleteInvitationView.as_view()
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

        view = TeacherCompleteInvitationView.as_view()
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


@pytest.mark.django_db
def test_teacher_invitation_endpoints_are_present_in_openapi_schema(admin_client):
    response = admin_client.get("/api/schema/?format=json")

    assert response.status_code == status.HTTP_200_OK

    schema = response.json()
    invite_operation = schema["paths"]["/api/teachers/invite/"]["post"]
    complete_operation = schema["paths"]["/api/teachers/complete-invitation/"]["post"]
    invite_request_ref = invite_operation["requestBody"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    complete_request_ref = complete_operation["requestBody"]["content"][
        "application/json"
    ]["schema"]["$ref"]

    assert invite_request_ref.endswith("/TeacherInvite")
    assert complete_request_ref.endswith("/TeacherCompleteInvitation")


@pytest.mark.django_db
def test_complete_rejects_missing_teacher_profile():
    api_rf = APIRequestFactory()
    user = UserFactory(role=User.Role.TEACHER, is_active=False)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    view = TeacherCompleteInvitationView.as_view()
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
