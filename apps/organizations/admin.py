import sys

from accounts.email import OrganizationApprovalMagicLinkEmail
from accounts.services import create_approval_magic_link
from accounts.services import get_magic_link_email_context
from botocore.exceptions import BotoCoreError
from botocore.exceptions import ClientError
from django.contrib import admin
from django.contrib.sites.shortcuts import get_current_site
from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from organizations.models import Organization

from media.storage import S3StorageClient

sys.modules.setdefault("apps.organizations.admin", sys.modules[__name__])


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "trade_name",
        "tin_number",
        "license_no",
        "status",
        "verification_status",
        "verification_checked_at",
        "created_at",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "verification_checked_at",
        "verification_match_source",
        "verified_name",
        "verified_license_no",
        "verified_tin_number",
        "business_license_image_preview",
        "review_actions",
    )
    search_fields = (
        "name",
        "trade_name",
        "verified_name",
    )
    list_filter = (
        "status",
        "verification_status",
        "created_at",
        "verification_checked_at",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "owner",
                    "name",
                    "trade_name",
                    "tin_number",
                    "license_no",
                    "client_full_name",
                    "business_address",
                    "business_phone_number",
                    "client_phone_number",
                    "business_license_image",
                    "business_license_image_preview",
                ),
            },
        ),
        (
            "Review Status",
            {
                "fields": (
                    "status",
                    "verification_status",
                    "verification_failure_reason",
                    "verification_checked_at",
                    "verification_match_source",
                    "verified_name",
                    "verified_license_no",
                    "verified_tin_number",
                    "review_actions",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<uuid:object_id>/approve/",
                self.admin_site.admin_view(self.approve_view),
                name="organizations_organization_approve",
            ),
            path(
                "<uuid:object_id>/send-to-review/",
                self.admin_site.admin_view(self.send_to_review_view),
                name="organizations_organization_send_to_review",
            ),
        ]
        return custom_urls + urls

    @admin.display(description="Review Actions")
    def review_actions(self, obj: Organization) -> str:
        approve_url = reverse(
            "admin:organizations_organization_approve",
            kwargs={"object_id": obj.pk},
        )
        review_url = reverse(
            "admin:organizations_organization_send_to_review",
            kwargs={"object_id": obj.pk},
        )
        return format_html(
            '<a class="button" href="{}">Approve</a>&nbsp;'
            '<a class="button" href="{}">Send To Review</a>',
            approve_url,
            review_url,
        )

    @admin.display(description="Business License Preview")
    def business_license_image_preview(self, obj: Organization) -> str:
        media_file = obj.business_license_image
        if media_file is None:
            return "No business license image uploaded."

        try:
            download_url = S3StorageClient().get_download_url(media_file.key)
        except BotoCoreError, ClientError:
            return format_html(
                "{}<br><span>Preview unavailable.</span>",
                media_file.file_name,
            )

        if media_file.content_type.startswith("image/"):
            return format_html(
                (
                    '<div><img src="{}" alt="{}" '
                    'style="max-width: 100%; max-height: 480px; '
                    'border-radius: 4px;" /></div>'
                    '<div><a href="{}" target="_blank" '
                    'rel="noopener">Open full image</a></div>'
                ),
                download_url,
                media_file.file_name,
                download_url,
            )

        return format_html(
            (
                '<div>{}</div><div><a href="{}" target="_blank" '
                'rel="noopener">Open full image</a></div>'
            ),
            media_file.file_name,
            download_url,
        )

    def _sync_review_state(
        self,
        organization: Organization,
        *,
        set_checked_at: bool,
    ) -> list[str]:
        update_fields = ["status"]

        if organization.verification_status == Organization.VerificationStatus.VERIFIED:
            organization.status = Organization.Status.ACTIVE
            organization.verification_failure_reason = ""
            update_fields.append("verification_failure_reason")
        else:
            organization.status = Organization.Status.PENDING
            if (
                organization.verification_status
                == Organization.VerificationStatus.PENDING_MANUAL_REVIEW
                and not organization.verification_failure_reason
            ):
                organization.verification_failure_reason = "manual_review_required"
                update_fields.append("verification_failure_reason")

        if set_checked_at:
            organization.verification_checked_at = timezone.now()
            update_fields.append("verification_checked_at")

        return update_fields

    def _send_approval_email(
        self,
        request: HttpRequest,
        organization: Organization,
    ) -> None:
        magic_link = create_approval_magic_link(user=organization.owner)
        site = get_current_site(request)
        email_context = get_magic_link_email_context(
            user=organization.owner,
            raw_token=magic_link.raw_token,
            organization_name=organization.name,
        )
        email_context["site_name"] = site.name

        email_obj = OrganizationApprovalMagicLinkEmail(
            request,
            context=email_context,
        )
        email_obj.send([organization.owner.email])

    def save_model(self, request, obj, form, change):
        should_send_approval_email = False
        if (
            change
            and obj.verification_status == Organization.VerificationStatus.VERIFIED
        ):
            previous_status = (
                Organization.objects.filter(pk=obj.pk)
                .values_list("verification_status", flat=True)
                .first()
            )
            submitted_status = form.cleaned_data.get("status")
            should_send_approval_email = (
                previous_status != Organization.VerificationStatus.VERIFIED
                or submitted_status != Organization.Status.ACTIVE
            )

        set_checked_at = "verification_status" in form.changed_data
        self._sync_review_state(obj, set_checked_at=set_checked_at)
        super().save_model(request, obj, form, change)

        if should_send_approval_email:
            self._send_approval_email(request, obj)

    def approve_view(
        self,
        request: HttpRequest,
        object_id: str,
    ) -> HttpResponseRedirect:
        organization = get_object_or_404(Organization, pk=object_id)
        was_verified = (
            organization.verification_status == Organization.VerificationStatus.VERIFIED
        )
        organization.verification_status = Organization.VerificationStatus.VERIFIED
        update_fields = self._sync_review_state(organization, set_checked_at=True)
        organization.save(
            update_fields=["verification_status", *update_fields, "updated_at"],
        )
        if not was_verified:
            self._send_approval_email(request, organization)
        self.message_user(request, "Organization approved successfully.")
        return HttpResponseRedirect(
            reverse(
                "admin:organizations_organization_change",
                kwargs={"object_id": organization.pk},
            ),
        )

    def send_to_review_view(
        self,
        request: HttpRequest,
        object_id: str,
    ) -> HttpResponseRedirect:
        organization = get_object_or_404(Organization, pk=object_id)
        organization.verification_status = (
            Organization.VerificationStatus.PENDING_MANUAL_REVIEW
        )
        update_fields = self._sync_review_state(organization, set_checked_at=True)
        organization.save(
            update_fields=["verification_status", *update_fields, "updated_at"],
        )
        self.message_user(request, "Organization moved to manual review.")
        return HttpResponseRedirect(
            reverse(
                "admin:organizations_organization_change",
                kwargs={"object_id": organization.pk},
            ),
        )
