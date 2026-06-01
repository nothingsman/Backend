from __future__ import annotations

from unittest.mock import patch

import pytest
from accounts.models import User
from accounts.services import create_parent_invitation_verification_token
from accounts.services import create_parent_login_otp
from accounts.tests.factories import UserFactory
from branches.tests.factories import BranchAdminFactory
from branches.tests.factories import BranchFactory
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.test import APIRequestFactory
from students.api.views import ParentCompleteInvitationView
from students.api.views import ParentInviteView
from students.models import Parent


@pytest.mark.django_db
class TestParentInviteView:
    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    @patch("students.api.views.ParentInvitationEmail.send")
    @patch("students.api.views.send_parent_invitation_sms")
    def test_invite_success(
        self,
        mock_send_sms,
        mock_send_email,
        api_rf: APIRequestFactory,
        settings,
    ):
        settings.FRONTEND_PARENT_DOMAIN = "https://parents.kelem.app"
        settings.FRONTEND_ROLE_DOMAINS = {
            **settings.FRONTEND_ROLE_DOMAINS,
            User.Role.PARENT: settings.FRONTEND_PARENT_DOMAIN,
        }
        user = UserFactory()
        branch = BranchFactory(school__organization__owner=user)

        view = ParentInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "name": "New",
                "father_name": "Parent",
                "grandfather_name": "Test",
                "phone_number": "+251911111201",
                "email": "parent1@example.com",
                "branch": branch.id,
            },
        )
        request.user = user

        response = view(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["message"] == "Parent invitation sent successfully."
        assert response.data["invitation_url"].startswith(
            settings.FRONTEND_PARENT_DOMAIN,
        )
        assert "/complete-parent-invitation/" in response.data["invitation_url"]
        assert response.data["sms_sent"] is True

        parent_user = User.objects.get(phone_number="+251911111201")
        assert parent_user.role == User.Role.PARENT
        assert parent_user.is_active is False

        parent = Parent.objects.get(user=parent_user)
        assert parent.is_active is False
        assert branch.organization in parent.organizations.all()
        assert branch in parent.branches.all()
        mock_send_sms.assert_called_once()
        mock_send_email.assert_called_once()

    @patch("students.api.views.ParentInvitationEmail.send")
    @patch("students.api.views.send_parent_invitation_sms")
    def test_reinvite_updates_existing_inactive_parent(
        self,
        mock_send_sms,
        mock_send_email,
        api_rf: APIRequestFactory,
    ):
        owner = UserFactory()
        old_branch = BranchFactory(school__organization__owner=owner)
        new_branch = BranchFactory(school__organization__owner=owner)
        user = UserFactory(
            role=User.Role.PARENT,
            is_active=False,
            phone_number="+251911111202",
            name="Old",
            father_name="Parent",
            grandfather_name="Name",
        )
        parent = Parent.objects.create(
            user=user,
            occupation="Old Occupation",
            is_active=False,
        )
        parent.organizations.add(old_branch.organization)
        parent.branches.add(old_branch)

        view = ParentInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "name": "Updated",
                "father_name": "Parent",
                "grandfather_name": "Profile",
                "phone_number": "+251911111202",
                "occupation": "Engineer",
                "email": "parent2@example.com",
                "branch": new_branch.id,
            },
        )
        request.user = owner

        response = view(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["sms_sent"] is True
        user.refresh_from_db()
        parent.refresh_from_db()
        assert User.objects.filter(phone_number="+251911111202").count() == 1
        assert user.name == "Updated"
        assert user.is_active is False
        assert parent.occupation == "Engineer"
        assert parent.is_active is False
        assert list(parent.organizations.all()) == [new_branch.organization]
        assert list(parent.branches.all()) == [new_branch]
        mock_send_sms.assert_called_once()
        mock_send_email.assert_called_once()

    def test_invite_rejects_existing_active_parent(self, api_rf: APIRequestFactory):
        owner = UserFactory()
        branch = BranchFactory(school__organization__owner=owner)
        user = UserFactory(
            role=User.Role.PARENT,
            is_active=True,
            phone_number="+251911111203",
        )
        parent = Parent.objects.create(user=user)
        parent.organizations.add(branch.organization)
        parent.branches.add(branch)

        view = ParentInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "name": "Active",
                "father_name": "Parent",
                "grandfather_name": "User",
                "phone_number": "+251911111203",
                "branch": branch.id,
            },
        )
        request.user = owner

        response = view(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["errors"][0]["field"] == "phone_number"

    def test_invite_rejects_existing_user_with_wrong_role(
        self,
        api_rf: APIRequestFactory,
    ):
        owner = UserFactory()
        branch = BranchFactory(school__organization__owner=owner)
        UserFactory(
            role=User.Role.TEACHER,
            is_active=False,
            phone_number="+251911111204",
        )

        view = ParentInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "name": "Wrong",
                "father_name": "Role",
                "grandfather_name": "User",
                "phone_number": "+251911111204",
                "branch": branch.id,
            },
        )
        request.user = owner

        response = view(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["errors"][0]["field"] == "phone_number"

    @patch(
        "students.api.views.send_parent_invitation_sms",
        side_effect=RuntimeError("boom"),
    )
    def test_invite_rolls_back_when_sms_send_fails(
        self,
        mock_send_sms,
        api_rf: APIRequestFactory,
    ):
        owner = UserFactory()
        branch = BranchFactory(school__organization__owner=owner)

        view = ParentInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "name": "Rollback",
                "father_name": "Parent",
                "grandfather_name": "Case",
                "phone_number": "+251911111205",
                "branch": branch.id,
            },
        )
        request.user = owner

        response = view(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["sms_sent"] is False
        assert response.data["sms_error"] == "boom"
        assert mock_send_sms.called
        assert User.objects.filter(phone_number="+251911111205").exists()

    def test_invite_allows_active_branch_admin_for_own_branch(
        self,
        api_rf: APIRequestFactory,
    ):
        branch_admin_user = UserFactory()
        branch = BranchFactory()
        BranchAdminFactory(
            user=branch_admin_user,
            branch=branch,
            organization=branch.organization,
        )

        view = ParentInviteView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "name": "Branch",
                "father_name": "Admin",
                "grandfather_name": "Parent",
                "phone_number": "+251911111206",
                "branch": branch.id,
            },
        )
        request.user = branch_admin_user

        with patch("students.api.views.send_parent_invitation_sms") as mock_send_sms:
            response = view(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert mock_send_sms.called


@pytest.mark.django_db
class TestParentCompleteInvitationView:
    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    @pytest.fixture
    def api_client(self) -> APIClient:
        return APIClient()

    def test_complete_success(self, api_rf: APIRequestFactory):
        user = UserFactory(
            role=User.Role.PARENT,
            is_active=False,
            phone_number="+251911111207",
        )
        Parent.objects.create(user=user, is_active=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        verification_token = create_parent_invitation_verification_token(user=user)

        view = ParentCompleteInvitationView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "uid": uid,
                "token": token,
                "invitation_verification_token": verification_token,
                "new_password": "new_secure_password_123",
            },
        )

        response = view(request)

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.is_active is True
        assert user.verified_at is not None
        assert user.parent_profile.is_active is True
        assert user.check_password("new_secure_password_123")

    @patch("students.api.views.ParentInvitationEmail.send")
    @patch("students.api.views.send_parent_invitation_sms")
    @patch("students.api.views.send_parent_otp_sms")
    def test_invited_parent_can_request_otp_complete_invitation_and_log_in(
        self,
        mock_send_otp_sms,
        mock_send_invitation_sms,
        mock_send_email,
        api_client: APIClient,
        api_rf: APIRequestFactory,
    ):
        owner = UserFactory()
        branch = BranchFactory(school__organization__owner=owner)

        invite_request = api_rf.post(
            "/fake-url/",
            {
                "name": "Invited",
                "father_name": "Parent",
                "grandfather_name": "Flow",
                "phone_number": "+251911111212",
                "email": "invited-parent@example.com",
                "branch": branch.id,
            },
        )
        invite_request.user = owner

        invite_response = ParentInviteView.as_view()(invite_request)

        assert invite_response.status_code == status.HTTP_201_CREATED
        invited_user = User.objects.get(phone_number="+251911111212")
        assert invited_user.is_active is False
        assert invited_user.parent_profile.is_active is False

        uid = urlsafe_base64_encode(force_bytes(invited_user.pk))
        token = default_token_generator.make_token(invited_user)

        otp_response = api_client.post(
            "/api/parents/request-invitation-otp/",
            {"uid": uid, "token": token},
            format="json",
        )

        assert otp_response.status_code == status.HTTP_200_OK
        otp = invited_user.parent_login_otps.first()
        assert otp is not None
        otp_code = mock_send_otp_sms.call_args.kwargs["otp_code"]

        verify_response = api_client.post(
            "/api/parents/verify-invitation-otp/",
            {
                "uid": uid,
                "token": token,
                "otp_code": otp_code,
            },
            format="json",
        )

        assert verify_response.status_code == status.HTTP_200_OK

        complete_response = api_client.post(
            "/api/parents/complete-invitation/",
            {
                "uid": uid,
                "token": token,
                "invitation_verification_token": verify_response.data[
                    "invitation_verification_token"
                ],
                "new_password": "new_secure_password_123",
            },
            format="json",
        )

        assert complete_response.status_code == status.HTTP_200_OK
        invited_user.refresh_from_db()
        assert invited_user.is_active is True
        assert invited_user.parent_profile.is_active is True

        login_response = api_client.post(
            "/auth/jwt/create/",
            {
                "phone_number": invited_user.phone_number,
                "password": "new_secure_password_123",
            },
            format="json",
        )

        assert login_response.status_code == status.HTTP_200_OK
        assert "access" in login_response.data
        assert "refresh" in login_response.data
        assert mock_send_invitation_sms.called
        assert mock_send_otp_sms.called
        assert mock_send_email.called

    def test_complete_invalid_token(self, api_rf: APIRequestFactory):
        user = UserFactory(
            role=User.Role.PARENT,
            is_active=False,
            phone_number="+251911111208",
        )
        Parent.objects.create(user=user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        verification_token = create_parent_invitation_verification_token(user=user)

        view = ParentCompleteInvitationView.as_view()
        request = api_rf.post(
            "/fake-url/",
            {
                "uid": uid,
                "token": "invalid-token",
                "invitation_verification_token": verification_token,
                "new_password": "new_secure_password_123",
            },
        )

        response = view(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["errors"][0]["field"] == "token"

    def test_request_invitation_otp_rejects_invalid_token(
        self,
        api_client: APIClient,
    ):
        user = UserFactory(
            role=User.Role.PARENT,
            is_active=False,
            phone_number="+251911111209",
        )
        Parent.objects.create(user=user, is_active=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        response = api_client.post(
            "/api/parents/request-invitation-otp/",
            {
                "uid": uid,
                "token": "invalid-token",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["errors"][0]["field"] == "token"

    def test_verify_invitation_otp_rejects_invalid_otp(self, api_client: APIClient):
        user = UserFactory(
            role=User.Role.PARENT,
            is_active=False,
            phone_number="+251911111210",
        )
        Parent.objects.create(user=user, is_active=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        create_parent_login_otp(user=user)

        response = api_client.post(
            "/api/parents/verify-invitation-otp/",
            {
                "uid": uid,
                "token": token,
                "otp_code": "000000",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["errors"][0]["field"] == "otp_code"

    def test_complete_rejects_invalid_verification_token(
        self,
        api_client: APIClient,
    ):
        user = UserFactory(
            role=User.Role.PARENT,
            is_active=False,
            phone_number="+251911111211",
        )
        Parent.objects.create(user=user, is_active=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = api_client.post(
            "/api/parents/complete-invitation/",
            {
                "uid": uid,
                "token": token,
                "invitation_verification_token": "invalid-token",
                "new_password": "new_secure_password_123",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["errors"][0]["field"] == "invitation_verification_token"

    def test_complete_rejects_missing_verification_token(
        self,
        api_client: APIClient,
    ):
        user = UserFactory(
            role=User.Role.PARENT,
            is_active=False,
            phone_number="+251911111213",
        )
        Parent.objects.create(user=user, is_active=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = api_client.post(
            "/api/parents/complete-invitation/",
            {
                "uid": uid,
                "token": token,
                "new_password": "new_secure_password_123",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["errors"][0]["field"] == "invitation_verification_token"

    def test_complete_rejects_weak_password(self, api_client: APIClient):
        user = UserFactory(
            role=User.Role.PARENT,
            is_active=False,
            phone_number="+251911111211",
        )
        Parent.objects.create(user=user, is_active=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        verification_token = create_parent_invitation_verification_token(user=user)

        response = api_client.post(
            "/api/parents/complete-invitation/",
            {
                "uid": uid,
                "token": token,
                "invitation_verification_token": verification_token,
                "new_password": "123",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["errors"][0]["field"] == "new_password"

    @patch("students.api.views.send_parent_otp_sms")
    def test_request_invitation_otp_resend_invalidates_previous_code(
        self,
        mock_send_otp_sms,
        api_client: APIClient,
    ):
        user = UserFactory(
            role=User.Role.PARENT,
            is_active=False,
            phone_number="+251911111214",
        )
        Parent.objects.create(user=user, is_active=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        first_response = api_client.post(
            "/api/parents/request-invitation-otp/",
            {"uid": uid, "token": token},
            format="json",
        )
        assert first_response.status_code == status.HTTP_200_OK
        first_code = mock_send_otp_sms.call_args.kwargs["otp_code"]

        second_response = api_client.post(
            "/api/parents/request-invitation-otp/",
            {"uid": uid, "token": token},
            format="json",
        )
        assert second_response.status_code == status.HTTP_200_OK
        second_code = mock_send_otp_sms.call_args.kwargs["otp_code"]
        assert first_code != second_code

        stale_verify = api_client.post(
            "/api/parents/verify-invitation-otp/",
            {
                "uid": uid,
                "token": token,
                "otp_code": first_code,
            },
            format="json",
        )
        assert stale_verify.status_code == status.HTTP_400_BAD_REQUEST

        fresh_verify = api_client.post(
            "/api/parents/verify-invitation-otp/",
            {
                "uid": uid,
                "token": token,
                "otp_code": second_code,
            },
            format="json",
        )
        assert fresh_verify.status_code == status.HTTP_200_OK

    @patch("students.api.views.send_parent_otp_sms")
    def test_verify_invitation_otp_returns_verification_token(
        self,
        mock_send_otp_sms,
        api_client: APIClient,
    ):
        user = UserFactory(
            role=User.Role.PARENT,
            is_active=False,
            phone_number="+251911111215",
        )
        Parent.objects.create(user=user, is_active=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        request_response = api_client.post(
            "/api/parents/request-invitation-otp/",
            {"uid": uid, "token": token},
            format="json",
        )
        assert request_response.status_code == status.HTTP_200_OK

        otp_code = mock_send_otp_sms.call_args.kwargs["otp_code"]
        verify_response = api_client.post(
            "/api/parents/verify-invitation-otp/",
            {
                "uid": uid,
                "token": token,
                "otp_code": otp_code,
            },
            format="json",
        )

        assert verify_response.status_code == status.HTTP_200_OK
        assert verify_response.data["invitation_verification_token"]
