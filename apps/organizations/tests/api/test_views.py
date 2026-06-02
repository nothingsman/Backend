from __future__ import annotations

from datetime import date
from datetime import datetime

import pytest
from academics.tests.factories import AcademicYearFactory
from academics.tests.factories import GradeFactory
from academics.tests.factories import SectionFactory
from academics.tests.factories import SubjectFactory
from accounts.tests.factories import UserFactory
from assessments.models import Assessment
from assessments.models import HomeworkConfirmation
from branches.tests.factories import BranchAdminFactory
from branches.tests.factories import BranchFactory
from django.utils import timezone
from organizations.api.views import OrganizationViewSet
from organizations.services.etrade import VerificationOutcome
from organizations.tests.factories import OrganizationFactory
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.test import APIRequestFactory
from students.tests.factories import ParentFactory
from students.tests.factories import StudentFactory
from teachers.models import Teacher
from teachers.models import TeacherSubjectAssignment

from media.models import StatusChoices
from media.tests.factories import MediaFileFactory

UNSET = object()


def _create_homework_confirmation(  # noqa: PLR0913
    *,
    organization,
    branch,
    parent_user,
    student,
    year: int,
    is_confirmed: bool = True,
    confirmed_by=None,
    confirmed_at=UNSET,
) -> HomeworkConfirmation:
    teacher_user = UserFactory(role="TEACHER")
    teacher = Teacher.objects.create(
        user=teacher_user,
        organization=organization,
        branch=branch,
        employee_id=f"EMP-{teacher_user.id}",
    )
    academic_year = AcademicYearFactory(
        organization=organization,
        branch=branch,
        name=f"{year}/{year + 1}-{teacher_user.id}",
        start_date=date(year, 9, 1),
        end_date=date(year + 1, 6, 30),
    )
    grade = GradeFactory(
        organization=organization,
        branch=branch,
    )
    section = SectionFactory(
        organization=organization,
        branch=branch,
        grade=grade,
        academic_year=academic_year,
    )
    subject = SubjectFactory(
        organization=organization,
        branch=branch,
        grade=grade,
    )
    assignment = TeacherSubjectAssignment.objects.create(
        teacher=teacher,
        organization=organization,
        subject=subject,
        section=section,
        academic_year=academic_year,
    )
    assessment = Assessment.objects.create(
        organization=organization,
        branch=branch,
        teacher_assignment=assignment,
        title=f"Homework {year}",
        task_type=Assessment.TaskType.HOMEWORK,
        total_marks=10,
        due_date=date(year, 10, 1),
    )
    if confirmed_at is UNSET:
        confirmed_at = datetime(
            year,
            10,
            15,
            12,
            0,
            0,
            tzinfo=timezone.get_current_timezone(),
        )
    return HomeworkConfirmation.objects.create(
        organization=organization,
        branch=branch,
        section=section,
        assessment=assessment,
        student=student,
        is_confirmed=is_confirmed,
        confirmed_by=confirmed_by if confirmed_by is not None else parent_user,
        confirmed_at=confirmed_at,
        feedback="Completed",
    )


@pytest.mark.django_db
class TestOrganizationViewSet:
    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    @pytest.fixture
    def api_client(self) -> APIClient:
        return APIClient()

    def test_get_queryset_scopes_to_request_owner(self, api_rf: APIRequestFactory):
        user = UserFactory()
        owned_organization = OrganizationFactory(owner=user)
        foreign_organization = OrganizationFactory()
        view = OrganizationViewSet()
        request = api_rf.get("/fake-url/")
        request.user = user

        view.request = request

        queryset = view.get_queryset()

        assert list(queryset) == [owned_organization]
        assert foreign_organization not in queryset

    def test_create_returns_verified_response(
        self,
        api_client: APIClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = UserFactory()
        api_client.force_authenticate(user=user)

        monkeypatch.setattr(
            "organizations.services.organization_creation.verify_organization_registration",
            lambda **_: VerificationOutcome(
                verification_status="verified",
                organization_status="ACTIVE",
                verification_failure_reason="",
                verification_match_source="license_lookup",
                verified_name="Example Trading PLC",
                verified_license_no="LIC-123",
                verified_tin_number="1234567890",
            ),
        )

        response = api_client.post(
            "/api/organizations/",
            {
                "name": "Example Trading PLC",
                "trade_name": "Example Trading",
                "tin_number": "1234567890",
                "license_no": "LIC-123",
                "client_full_name": "Owner Name",
                "business_address": "Addis Ababa",
                "business_phone_number": "0911000000",
                "client_phone_number": "0911000001",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["tin_number"] == "1234567890"
        assert response.data["status"] == "ACTIVE"
        assert response.data["verification_status"] == "verified"
        assert response.data["verification_failure_reason"] == ""
        assert response.data["requires_manual_verification"] is False

    def test_create_accepts_business_license_media_reference(
        self,
        api_client: APIClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = UserFactory()
        api_client.force_authenticate(user=user)
        media = MediaFileFactory(
            uploaded_by=user,
            status=StatusChoices.UPLOADED,
            content_type="image/png",
        )

        monkeypatch.setattr(
            "organizations.services.organization_creation.verify_organization_registration",
            lambda **_: VerificationOutcome(
                verification_status="verified",
                organization_status="ACTIVE",
                verification_failure_reason="",
                verification_match_source="license_lookup",
                verified_name="Example Trading PLC",
                verified_license_no="LIC-123",
                verified_tin_number="1234567890",
            ),
        )

        response = api_client.post(
            "/api/organizations/",
            {
                "name": "Example Trading PLC",
                "trade_name": "Example Trading",
                "tin_number": "1234567890",
                "license_no": "LIC-123",
                "client_full_name": "Owner Name",
                "business_address": "Addis Ababa",
                "business_phone_number": "0911000000",
                "client_phone_number": "0911000001",
                "business_license_image": str(media.id),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert str(response.data["business_license_image"]) == str(media.id)

    def test_create_returns_pending_manual_review_when_inconclusive(
        self,
        api_client: APIClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = UserFactory()
        api_client.force_authenticate(user=user)

        monkeypatch.setattr(
            "organizations.services.organization_creation.verify_organization_registration",
            lambda **_: VerificationOutcome(
                verification_status="pending_manual_review",
                organization_status="PENDING",
                verification_failure_reason="organization_details_did_not_match_etrade_records",
                verification_match_source="",
                verified_name="",
                verified_license_no="",
                verified_tin_number="",
            ),
        )

        response = api_client.post(
            "/api/organizations/",
            {
                "name": "Example Trading PLC",
                "trade_name": "Example Trading",
                "tin_number": "1234567890",
                "license_no": "LIC-123",
                "client_full_name": "Owner Name",
                "business_address": "Addis Ababa",
                "business_phone_number": "0911000000",
                "client_phone_number": "0911000001",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "PENDING"
        assert response.data["verification_status"] == "pending_manual_review"
        assert (
            response.data["verification_failure_reason"]
            == "organization_details_did_not_match_etrade_records"
        )
        assert response.data["requires_manual_verification"] is True

    def test_create_returns_verification_unavailable_when_service_fails(
        self,
        api_client: APIClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = UserFactory()
        api_client.force_authenticate(user=user)

        monkeypatch.setattr(
            "organizations.services.organization_creation.verify_organization_registration",
            lambda **_: VerificationOutcome(
                verification_status="verification_unavailable",
                organization_status="PENDING",
                verification_failure_reason="etrade_service_unavailable",
                verification_match_source="",
                verified_name="",
                verified_license_no="",
                verified_tin_number="",
            ),
        )

        response = api_client.post(
            "/api/organizations/",
            {
                "name": "Example Trading PLC",
                "trade_name": "Example Trading",
                "tin_number": "1234567890",
                "license_no": "LIC-123",
                "client_full_name": "Owner Name",
                "business_address": "Addis Ababa",
                "business_phone_number": "0911000000",
                "client_phone_number": "0911000001",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "PENDING"
        assert response.data["verification_status"] == "verification_unavailable"
        assert (
            response.data["verification_failure_reason"] == "etrade_service_unavailable"
        )
        assert response.data["requires_manual_verification"] is True

    def test_analytics_returns_totals_and_yearly_series(
        self,
        api_client: APIClient,
    ) -> None:
        owner = UserFactory()
        organization = OrganizationFactory(owner=owner)
        branch = BranchFactory(school__organization=organization)
        other_organization = OrganizationFactory()

        student_2023_a = StudentFactory(
            organization=organization,
            branch=branch,
            admission_date=date(2023, 9, 1),
        )
        student_2023_b = StudentFactory(
            organization=organization,
            branch=branch,
            admission_date=date(2023, 10, 1),
        )
        student_2024 = StudentFactory(
            organization=organization,
            branch=branch,
            admission_date=date(2024, 9, 1),
        )
        student_no_admission_date = StudentFactory(
            organization=organization,
            branch=branch,
            admission_date=None,
        )
        StudentFactory(
            organization=other_organization,
            admission_date=date(2025, 1, 1),
        )

        BranchAdminFactory(organization=organization, branch=branch)
        BranchAdminFactory(organization=organization, branch=branch)
        BranchAdminFactory(
            branch=BranchFactory(school__organization=other_organization),
        )

        Teacher.objects.create(
            user=UserFactory(role="TEACHER"),
            organization=organization,
            branch=branch,
            employee_id="EMP-1",
        )
        Teacher.objects.create(
            user=UserFactory(role="TEACHER"),
            organization=organization,
            branch=branch,
            employee_id="EMP-2",
        )
        Teacher.objects.create(
            user=UserFactory(role="TEACHER"),
            organization=other_organization,
            branch=BranchFactory(school__organization=other_organization),
            employee_id="EMP-3",
        )

        engaged_parent = ParentFactory(
            organizations=[organization],
            branches=[branch],
        )
        second_parent = ParentFactory(
            organizations=[organization],
            branches=[branch],
        )
        ParentFactory(organizations=[other_organization])

        _create_homework_confirmation(
            organization=organization,
            branch=branch,
            parent_user=engaged_parent.user,
            student=student_2023_a,
            year=2023,
        )
        _create_homework_confirmation(
            organization=organization,
            branch=branch,
            parent_user=engaged_parent.user,
            student=student_2024,
            year=2024,
        )
        _create_homework_confirmation(
            organization=organization,
            branch=branch,
            parent_user=second_parent.user,
            student=student_2023_b,
            year=2023,
        )
        _create_homework_confirmation(
            organization=organization,
            branch=branch,
            parent_user=engaged_parent.user,
            student=student_no_admission_date,
            year=2024,
            is_confirmed=False,
        )
        _create_homework_confirmation(
            organization=organization,
            branch=branch,
            parent_user=engaged_parent.user,
            student=student_no_admission_date,
            year=2024,
            confirmed_by=UserFactory(role="TEACHER"),
        )
        _create_homework_confirmation(
            organization=organization,
            branch=branch,
            parent_user=engaged_parent.user,
            student=student_no_admission_date,
            year=2024,
            confirmed_at=None,
        )

        api_client.force_authenticate(user=owner)
        response = api_client.get(f"/api/organizations/{organization.id}/analytics/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["organization_id"] == str(organization.id)
        assert response.data["totals"] == {
            "students": 4,
            "branch_admins": 2,
            "teachers": Teacher.objects.filter(organization=organization).count(),
            "parents": 2,
        }
        assert response.data["student_enrollment_growth"] == [
            {"year": 2023, "count": 2},
            {"year": 2024, "count": 1},
        ]
        assert response.data["parent_engagement"] == [
            {"year": 2023, "count": 2},
            {"year": 2024, "count": 1},
        ]

    def test_analytics_returns_404_for_non_owner(
        self,
        api_client: APIClient,
    ) -> None:
        organization = OrganizationFactory()
        api_client.force_authenticate(user=UserFactory())

        response = api_client.get(f"/api/organizations/{organization.id}/analytics/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_analytics_returns_empty_series_for_organization_without_data(
        self,
        api_client: APIClient,
    ) -> None:
        owner = UserFactory()
        organization = OrganizationFactory(owner=owner)
        api_client.force_authenticate(user=owner)

        response = api_client.get(f"/api/organizations/{organization.id}/analytics/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["totals"] == {
            "students": 0,
            "branch_admins": 0,
            "teachers": 0,
            "parents": 0,
        }
        assert response.data["student_enrollment_growth"] == []
        assert response.data["parent_engagement"] == []
