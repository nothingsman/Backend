import io
from datetime import date
from unittest import mock

import pandas as pd
import pytest
from academics.models import AcademicYear
from academics.tests.factories import GradeFactory
from academics.tests.factories import SectionFactory
from accounts.models import User
from accounts.tests.factories import UserFactory
from branches.tests.factories import BranchFactory
from django.utils import timezone
from organizations.tests.factories import OrganizationFactory
from rest_framework import status
from rest_framework.test import APIClient
from students.models import Parent
from students.models import ParentStudentLink
from students.models import Student
from students.models import StudentAcademicYearSection

from core.models import ImportJob
from media.tests.factories import MediaFileFactory

IMPORTED_STUDENT_COUNT = 2
CURRENT_SECTION_ORG_ERROR = "Current section must belong to the selected organization."


def create_csv_media(*, user, file_name: str, content: bytes):
    media_file = MediaFileFactory(
        uploaded_by=user,
        file_name=file_name,
        content_type="text/csv",
    )
    return media_file, mock.patch(
        "core.tasks.S3StorageClient.get_object_bytes",
        return_value=content,
    )


@pytest.mark.django_db
class TestStudentAndParentBulkImport:
    @pytest.fixture
    def api_client(self):
        return APIClient()

    @pytest.fixture
    def user(self):
        return UserFactory(is_superuser=True)

    @pytest.fixture
    def organization(self, user):
        return OrganizationFactory(owner=user)

    @pytest.fixture
    def branch(self, organization):
        return BranchFactory(school__organization=organization)

    @pytest.fixture
    def section(self, organization, branch):
        academic_year = AcademicYear.objects.get(
            organization=organization,
            branch=branch,
            is_current=True,
        )
        grade = GradeFactory(organization=organization, branch=branch, name="Grade 9")
        return SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            name="Section A",
            academic_year=academic_year,
        )

    def test_parent_bulk_import_success(self, api_client, user, organization, branch):
        api_client.force_authenticate(user=user)

        data = {
            "name": ["Parent One", "Parent Two"],
            "father_name": ["FParent One", "FParent Two"],
            "grandfather_name": ["GParent One", "GParent Two"],
            "email": ["parent1@example.com", "parent2@example.com"],
            "phone_number": ["+251911111111", "+251911222222"],
            "secondary_phone_number": ["", "+251911333333"],
            "occupation": ["Merchant", "Doctor"],
        }
        df = pd.DataFrame(data)
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        media_file, storage_mock = create_csv_media(
            user=user,
            file_name="parents.csv",
            content=csv_buf.getvalue().encode("utf-8"),
        )

        payload = {
            "organization": str(organization.id),
            "branch": str(branch.id),
            "file": str(media_file.id),
        }

        with storage_mock:
            response = api_client.post(
                "/api/parents/bulk-import/",
                payload,
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

        parent_user = User.objects.get(email="parent1@example.com")
        assert parent_user.role == User.Role.PARENT
        assert parent_user.name == "Parent One"
        assert parent_user.father_name == "FParent One"
        assert parent_user.grandfather_name == "GParent One"
        assert parent_user.phone_number == "+251911111111"
        assert parent_user.is_active is False
        assert parent_user.verified_at is None

        parent_profile = Parent.objects.get(user=parent_user)
        assert parent_profile.is_active is False
        assert parent_profile.secondary_phone_number == ""
        assert parent_profile.occupation == "Merchant"
        assert list(parent_profile.organizations.values_list("id", flat=True)) == [
            organization.id,
        ]
        assert list(parent_profile.branches.values_list("id", flat=True)) == [
            branch.id,
        ]

    def test_parent_bulk_import_deactivates_existing_parent_user(
        self,
        api_client,
        user,
        organization,
        branch,
    ):
        api_client.force_authenticate(user=user)

        existing_user = UserFactory(
            email="existing.parent@example.com",
            phone_number="+251911444444",
            role=User.Role.PARENT,
            is_active=True,
        )
        existing_user.verified_at = timezone.now()
        existing_user.save(update_fields=["verified_at"])
        parent_profile = Parent.objects.create(user=existing_user, is_active=True)

        data = {
            "name": ["Existing Parent"],
            "father_name": ["Father Existing"],
            "grandfather_name": ["Grand Existing"],
            "email": ["existing.parent@example.com"],
            "phone_number": ["+251911444444"],
        }
        df = pd.DataFrame(data)
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        media_file, storage_mock = create_csv_media(
            user=user,
            file_name="parents_existing.csv",
            content=csv_buf.getvalue().encode("utf-8"),
        )

        payload = {
            "organization": str(organization.id),
            "branch": str(branch.id),
            "file": str(media_file.id),
        }

        with storage_mock:
            response = api_client.post(
                "/api/parents/bulk-import/",
                payload,
                format="json",
            )

        assert response.status_code == status.HTTP_202_ACCEPTED

        existing_user.refresh_from_db()
        parent_profile.refresh_from_db()
        assert existing_user.is_active is False
        assert existing_user.verified_at is None
        assert parent_profile.is_active is False

    def test_parent_bulk_import_validation_error_rolls_back_everything(
        self,
        api_client,
        user,
        organization,
        branch,
    ):
        api_client.force_authenticate(user=user)

        UserFactory(phone_number="+251955555555")

        data = {
            "name": ["Parent One"],
            "father_name": ["FParent One"],
            "grandfather_name": ["GParent One"],
            "email": ["conflict@example.com"],
            "phone_number": ["+251955555555"],
            "secondary_phone_number": [""],
            "occupation": ["Merchant"],
        }
        df = pd.DataFrame(data)
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        media_file, storage_mock = create_csv_media(
            user=user,
            file_name="parents_error.csv",
            content=csv_buf.getvalue().encode("utf-8"),
        )

        payload = {
            "organization": str(organization.id),
            "branch": str(branch.id),
            "file": str(media_file.id),
        }

        with storage_mock:
            response = api_client.post(
                "/api/parents/bulk-import/",
                payload,
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

        assert Parent.objects.count() == 0
        assert User.objects.filter(email="conflict@example.com").exists() is False

        job = ImportJob.objects.last()
        assert job.module == "parents"
        assert job.status == ImportJob.Status.FAILED
        assert job.errors == [
            {
                "row": 2,
                "errors": {
                    "phone_number": [
                        (
                            "A user with this phone number exists but is not a "
                            "Parent (role: )."
                        ),
                    ],
                },
            },
        ]

    def test_student_bulk_import_success(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)

        # Pre-create parent to test linking
        parent_user = UserFactory(email="parent@example.com", role=User.Role.PARENT)
        parent_profile = Parent.objects.create(user=parent_user)
        parent_profile.organizations.add(organization)
        parent_profile.branches.add(branch)

        data = {
            "first_name": ["Alice", "Bob"],
            "last_name": ["Green", "Brown"],
            "gender": ["FEMALE", "MALE"],
            "date_of_birth": ["2015-05-20", "2016-06-18"],
            "roll_no": ["R501", ""],
            "section_name": ["Section A", ""],
            "grade_name": ["Grade 9", ""],
            "admission_date": ["2023-09-01", ""],
            "parent_emails": ["parent@example.com", ""],
            "relationship_types": ["MOTHER", ""],
        }
        df = pd.DataFrame(data)
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        media_file, storage_mock = create_csv_media(
            user=user,
            file_name="students.csv",
            content=csv_buf.getvalue().encode("utf-8"),
        )

        payload = {
            "organization": str(organization.id),
            "branch": str(branch.id),
            "file": str(media_file.id),
        }

        with storage_mock:
            response = api_client.post(
                "/api/students/bulk-import/",
                payload,
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

        alice = Student.objects.get(roll_no="R501", current_section=section)
        assert alice.first_name == "Alice"
        assert alice.last_name == "Green"
        assert alice.gender == "FEMALE"
        assert str(alice.date_of_birth) == "2015-05-20"
        assert alice.admission_date == date(2023, 9, 1)
        assert StudentAcademicYearSection.objects.filter(
            student=alice,
            academic_year=section.academic_year,
            section=section,
        ).exists()

        bob = Student.objects.get(first_name="Bob", current_section=None)
        assert bob.last_name == "Brown"
        assert bob.gender == "MALE"
        assert str(bob.date_of_birth) == "2016-06-18"
        assert bob.admission_date == timezone.now().date()
        assert bob.roll_no.startswith("STU-")
        assert StudentAcademicYearSection.objects.filter(
            student=bob,
            academic_year=section.academic_year,
            section=None,
        ).exists()

        # Verify parent links
        student_alice = Student.objects.get(roll_no="R501")
        assert ParentStudentLink.objects.filter(
            student=student_alice,
            parent=parent_profile,
            relationship_type="MOTHER",
        ).exists()
        link = ParentStudentLink.objects.get(
            student=student_alice,
            parent=parent_profile,
        )
        assert link.is_primary_contact is False

    def test_student_bulk_import_validation_error_rolls_back_everything(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)

        data = {
            "first_name": ["Alice", "Bob"],
            "last_name": ["Green", "Brown"],
            "gender": ["FEMALE", "MALE"],
            "date_of_birth": ["2015-05-20", "2016-06-18"],
            "roll_no": ["R700", "R700"],
            "section_name": ["Section A", "Section A"],
            "grade_name": ["Grade 9", "Grade 9"],
            "admission_date": ["2023-09-01", "2023-09-02"],
        }
        df = pd.DataFrame(data)
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        media_file, storage_mock = create_csv_media(
            user=user,
            file_name="students_error.csv",
            content=csv_buf.getvalue().encode("utf-8"),
        )

        payload = {
            "organization": str(organization.id),
            "branch": str(branch.id),
            "file": str(media_file.id),
        }

        with storage_mock:
            response = api_client.post(
                "/api/students/bulk-import/",
                payload,
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

        assert Student.objects.count() == 0
        assert ParentStudentLink.objects.count() == 0

        job = ImportJob.objects.last()
        assert job.module == "students"
        assert job.status == ImportJob.Status.FAILED
        assert job.errors == [
            {
                "row": 3,
                "errors": {
                    "roll_no": [
                        "Duplicate roll number in this section within the sheet.",
                    ],
                },
            },
        ]

    def test_student_bulk_import_uses_request_current_section(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)

        other_grade = GradeFactory(
            organization=organization,
            branch=branch,
            name="Grade 10",
        )
        other_section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=other_grade,
            name="Section B",
            academic_year=section.academic_year,
        )

        data = {
            "first_name": ["Alice", "Bob"],
            "last_name": ["Green", "Brown"],
            "gender": ["FEMALE", "MALE"],
            "date_of_birth": ["2015-05-20", "2016-06-18"],
            "roll_no": ["R801", "R802"],
            "section_name": ["Section A", ""],
            "grade_name": ["Grade 9", ""],
        }
        df = pd.DataFrame(data)
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        media_file, storage_mock = create_csv_media(
            user=user,
            file_name="students_override.csv",
            content=csv_buf.getvalue().encode("utf-8"),
        )

        payload = {
            "organization": str(organization.id),
            "branch": str(branch.id),
            "file": str(media_file.id),
            "current_section": str(other_section.id),
        }

        with storage_mock:
            response = api_client.post(
                "/api/students/bulk-import/",
                payload,
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

        assert ImportJob.objects.get(module="students").current_section == other_section
        assert (
            Student.objects.filter(current_section=other_section).count()
            == IMPORTED_STUDENT_COUNT
        )
        assert Student.objects.filter(current_section=section).count() == 0
        assert (
            StudentAcademicYearSection.objects.filter(
                academic_year=other_section.academic_year,
                section=other_section,
            ).count()
            == IMPORTED_STUDENT_COUNT
        )

    def test_student_bulk_import_rejects_request_current_section_from_other_branch(
        self,
        api_client,
        user,
        organization,
        branch,
    ):
        api_client.force_authenticate(user=user)

        other_branch = BranchFactory(school__organization=organization)
        other_grade = GradeFactory(
            organization=organization,
            branch=other_branch,
            name="Grade 11",
        )
        other_section = SectionFactory(
            organization=organization,
            branch=other_branch,
            grade=other_grade,
            academic_year=AcademicYear.objects.get(
                organization=organization,
                branch=other_branch,
                is_current=True,
            ),
        )
        media_file = MediaFileFactory(
            uploaded_by=user,
            file_name="students.csv",
            content_type="text/csv",
        )

        response = api_client.post(
            "/api/students/bulk-import/",
            {
                "organization": str(organization.id),
                "branch": str(branch.id),
                "file": str(media_file.id),
                "current_section": str(other_section.id),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {
            "errors": [
                {
                    "code": "invalid",
                    "detail": "Current section must belong to the selected branch.",
                    "field": "current_section",
                },
            ],
        }

    def test_student_bulk_import_rejects_request_section_from_other_organization(
        self,
        api_client,
        user,
        organization,
        branch,
    ):
        api_client.force_authenticate(user=user)

        other_user = UserFactory(is_superuser=True)
        other_organization = OrganizationFactory(owner=other_user)
        other_grade = GradeFactory(
            organization=organization,
            branch=branch,
            name="Grade 12",
        )
        other_section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=other_grade,
            academic_year=AcademicYear.objects.get(
                organization=organization,
                branch=branch,
                is_current=True,
            ),
        )
        other_section.organization = other_organization
        other_section.save(update_fields=["organization"])
        media_file = MediaFileFactory(
            uploaded_by=user,
            file_name="students.csv",
            content_type="text/csv",
        )

        response = api_client.post(
            "/api/students/bulk-import/",
            {
                "organization": str(organization.id),
                "branch": str(branch.id),
                "file": str(media_file.id),
                "current_section": str(other_section.id),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {
            "errors": [
                {
                    "code": "invalid",
                    "detail": CURRENT_SECTION_ORG_ERROR,
                    "field": "current_section",
                },
            ],
        }

    def test_student_bulk_import_rolls_back_with_request_current_section(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)

        data = {
            "first_name": ["Alice", "Bob"],
            "last_name": ["Green", "Brown"],
            "gender": ["FEMALE", "MALE"],
            "date_of_birth": ["2015-05-20", "2016-06-18"],
            "roll_no": ["R900", "R900"],
        }
        df = pd.DataFrame(data)
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        media_file, storage_mock = create_csv_media(
            user=user,
            file_name="students_request_section_error.csv",
            content=csv_buf.getvalue().encode("utf-8"),
        )

        with storage_mock:
            response = api_client.post(
                "/api/students/bulk-import/",
                {
                    "organization": str(organization.id),
                    "branch": str(branch.id),
                    "file": str(media_file.id),
                    "current_section": str(section.id),
                },
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

        assert Student.objects.count() == 0
        job = ImportJob.objects.last()
        assert job.status == ImportJob.Status.FAILED
        assert job.errors == [
            {
                "row": 3,
                "errors": {
                    "roll_no": [
                        "Duplicate roll number in this section within the sheet.",
                    ],
                },
            },
        ]

    def test_student_bulk_import_rejects_duplicate_roll_number_in_overridden_section(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)

        Student.objects.create(
            organization=organization,
            branch=branch,
            first_name="Existing",
            last_name="Student",
            gender="MALE",
            date_of_birth=date(2014, 1, 1),
            roll_no="R999",
            current_section=section,
            admission_date=date(2024, 1, 1),
        )

        data = {
            "first_name": ["Alice"],
            "last_name": ["Green"],
            "gender": ["FEMALE"],
            "date_of_birth": ["2015-05-20"],
            "roll_no": ["R999"],
            "section_name": [""],
            "grade_name": [""],
        }
        df = pd.DataFrame(data)
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        media_file, storage_mock = create_csv_media(
            user=user,
            file_name="students_duplicate_section.csv",
            content=csv_buf.getvalue().encode("utf-8"),
        )

        with storage_mock:
            response = api_client.post(
                "/api/students/bulk-import/",
                {
                    "organization": str(organization.id),
                    "branch": str(branch.id),
                    "file": str(media_file.id),
                    "current_section": str(section.id),
                },
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

        job = ImportJob.objects.last()
        assert job.status == ImportJob.Status.FAILED
        assert job.errors == [
            {
                "row": 2,
                "errors": {
                    "roll_no": ["Roll number already exists in this section."],
                },
            },
        ]
