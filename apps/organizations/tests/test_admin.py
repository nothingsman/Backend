from http import HTTPStatus
from unittest import mock

import pytest
from accounts.models import ApprovalLoginToken
from django.contrib import admin
from django.urls import reverse
from organizations.admin import OrganizationAdmin
from organizations.models import Organization
from organizations.tests.factories import OrganizationFactory

from media.models import StatusChoices
from media.tests.factories import MediaFileFactory


class TestOrganizationAdmin:
    def test_changelist(self, admin_client, organization: Organization):
        url = reverse("admin:organizations_organization_changelist")
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

    def test_search(self, admin_client, organization: Organization):
        url = reverse("admin:organizations_organization_changelist")
        response = admin_client.get(url, data={"q": "test"})
        assert response.status_code == HTTPStatus.OK

    def test_add(self, admin_client):
        url = reverse("admin:organizations_organization_add")
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

    def test_view_organization(self, admin_client, organization: Organization):
        url = reverse(
            "admin:organizations_organization_change",
            kwargs={"object_id": organization.pk},
        )
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

    @pytest.mark.django_db
    def test_view_organization_with_owner_missing_email(
        self,
        admin_client,
    ):
        organization = OrganizationFactory(
            owner__email=None,
            owner__name="No Email Owner",
        )
        url = reverse(
            "admin:organizations_organization_change",
            kwargs={"object_id": organization.pk},
        )

        response = admin_client.get(url)

        assert response.status_code == HTTPStatus.OK

    def test_view_organization_shows_business_license_preview(
        self,
        admin_client,
        organization: Organization,
    ):
        media = MediaFileFactory(
            uploaded_by=organization.owner,
            status=StatusChoices.UPLOADED,
            content_type="image/png",
            file_name="license.png",
            key="organizations/license.png",
        )
        organization.business_license_image = media
        organization.verification_status = (
            Organization.VerificationStatus.PENDING_MANUAL_REVIEW
        )
        organization.save(
            update_fields=["business_license_image", "verification_status"],
        )

        url = reverse(
            "admin:organizations_organization_change",
            kwargs={"object_id": organization.pk},
        )

        with mock.patch("organizations.admin.S3StorageClient") as mock_storage_client:
            mock_storage_client.return_value.get_download_url.return_value = (
                "https://cdn.example.com/license.png"
            )
            response = admin_client.get(url)
            preview_html = str(
                OrganizationAdmin(
                    Organization,
                    admin.site,
                ).business_license_image_preview(organization),
            )

        assert response.status_code == HTTPStatus.OK
        content = response.content.decode()
        assert "Business License Preview" in content
        assert 'src="https://cdn.example.com/license.png"' in preview_html
        assert 'href="https://cdn.example.com/license.png"' in preview_html
        assert "Open full image" in preview_html

    @mock.patch("accounts.email.send_email_task.delay")
    def test_approve_view(
        self,
        mock_send_email,
        admin_client,
        organization: Organization,
    ):
        organization.status = Organization.Status.PENDING
        organization.verification_status = (
            Organization.VerificationStatus.PENDING_MANUAL_REVIEW
        )
        organization.verification_failure_reason = "manual_review_required"
        organization.save()

        url = reverse(
            "admin:organizations_organization_approve",
            kwargs={"object_id": organization.pk},
        )
        response = admin_client.get(url)

        organization.refresh_from_db()

        assert response.status_code == HTTPStatus.FOUND
        assert organization.status == Organization.Status.ACTIVE
        assert (
            organization.verification_status == Organization.VerificationStatus.VERIFIED
        )
        assert organization.verification_failure_reason == ""
        assert organization.verification_checked_at is not None
        assert mock_send_email.called
        token_record = ApprovalLoginToken.objects.get(user=organization.owner)
        assert token_record.used_at is None
        email_fields = mock_send_email.call_args.kwargs["email_fields"]
        assert "organization-approval/" in email_fields["body"]

    def test_send_to_review_view(self, admin_client, organization: Organization):
        organization.status = Organization.Status.ACTIVE
        organization.verification_status = Organization.VerificationStatus.VERIFIED
        organization.verification_failure_reason = ""
        organization.save()

        url = reverse(
            "admin:organizations_organization_send_to_review",
            kwargs={"object_id": organization.pk},
        )
        response = admin_client.get(url)

        organization.refresh_from_db()

        assert response.status_code == HTTPStatus.FOUND
        assert organization.status == Organization.Status.PENDING
        assert (
            organization.verification_status
            == Organization.VerificationStatus.PENDING_MANUAL_REVIEW
        )
        assert organization.verification_failure_reason == "manual_review_required"
        assert organization.verification_checked_at is not None

    @pytest.mark.django_db
    @mock.patch("accounts.email.send_email_task.delay")
    def test_change_form_syncs_verified_status_to_active(
        self,
        mock_send_email,
        admin_client,
        organization: Organization,
    ):
        url = reverse(
            "admin:organizations_organization_change",
            kwargs={"object_id": organization.pk},
        )

        response = admin_client.post(
            url,
            {
                "owner": str(organization.owner_id),
                "name": organization.name,
                "trade_name": organization.trade_name,
                "tin_number": organization.tin_number,
                "license_no": organization.license_no,
                "client_full_name": organization.client_full_name,
                "business_address": organization.business_address,
                "business_phone_number": organization.business_phone_number,
                "client_phone_number": organization.client_phone_number,
                "business_license_image": "",
                "status": Organization.Status.PENDING,
                "verification_status": Organization.VerificationStatus.VERIFIED,
                "verification_failure_reason": "manual_review_required",
                "_save": "Save",
            },
        )

        organization.refresh_from_db()

        assert response.status_code == HTTPStatus.FOUND
        assert organization.status == Organization.Status.ACTIVE
        assert (
            organization.verification_status == Organization.VerificationStatus.VERIFIED
        )
        assert organization.verification_failure_reason == ""
        assert mock_send_email.called

    @pytest.mark.django_db
    @mock.patch("accounts.email.send_email_task.delay")
    def test_change_form_syncs_non_verified_status_to_pending(
        self,
        mock_send_email,
        admin_client,
        organization: Organization,
    ):
        organization.status = Organization.Status.ACTIVE
        organization.verification_status = Organization.VerificationStatus.VERIFIED
        organization.save()
        url = reverse(
            "admin:organizations_organization_change",
            kwargs={"object_id": organization.pk},
        )

        response = admin_client.post(
            url,
            {
                "owner": str(organization.owner_id),
                "name": organization.name,
                "trade_name": organization.trade_name,
                "tin_number": organization.tin_number,
                "license_no": organization.license_no,
                "client_full_name": organization.client_full_name,
                "business_address": organization.business_address,
                "business_phone_number": organization.business_phone_number,
                "client_phone_number": organization.client_phone_number,
                "business_license_image": "",
                "status": Organization.Status.ACTIVE,
                "verification_status": (
                    Organization.VerificationStatus.PENDING_MANUAL_REVIEW
                ),
                "verification_failure_reason": "",
                "_save": "Save",
            },
        )

        organization.refresh_from_db()

        assert response.status_code == HTTPStatus.FOUND
        assert organization.status == Organization.Status.PENDING
        assert (
            organization.verification_status
            == Organization.VerificationStatus.PENDING_MANUAL_REVIEW
        )
        assert organization.verification_failure_reason == "manual_review_required"
        assert not mock_send_email.called

    @pytest.mark.django_db
    @mock.patch("accounts.email.send_email_task.delay")
    def test_change_form_does_not_resend_email_for_already_verified_organization(
        self,
        mock_send_email,
        admin_client,
        organization: Organization,
    ):
        url = reverse(
            "admin:organizations_organization_change",
            kwargs={"object_id": organization.pk},
        )

        response = admin_client.post(
            url,
            {
                "owner": str(organization.owner_id),
                "name": organization.name,
                "trade_name": organization.trade_name,
                "tin_number": organization.tin_number,
                "license_no": organization.license_no,
                "client_full_name": organization.client_full_name,
                "business_address": organization.business_address,
                "business_phone_number": organization.business_phone_number,
                "client_phone_number": organization.client_phone_number,
                "business_license_image": "",
                "status": Organization.Status.ACTIVE,
                "verification_status": Organization.VerificationStatus.VERIFIED,
                "verification_failure_reason": "",
                "_save": "Save",
            },
        )

        assert response.status_code == HTTPStatus.FOUND
        assert not mock_send_email.called
