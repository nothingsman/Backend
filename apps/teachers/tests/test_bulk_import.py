import io
from datetime import date
from unittest import mock
from uuid import UUID

import pandas as pd
import pytest
from accounts.models import User
from accounts.tests.factories import UserFactory
from branches.tests.factories import BranchFactory
from django.utils import timezone
from organizations.tests.factories import OrganizationFactory
from rest_framework import status
from rest_framework.test import APIClient
from teachers.models import Teacher

from core.models import ImportJob
from media.tests.factories import MediaFileFactory

FAILED_IMPORT_ROW = 2


def create_media(*, user, file_name: str, content_type: str, content: bytes):
    media_file = MediaFileFactory(
        uploaded_by=user,
        file_name=file_name,
        content_type=content_type,
    )
    return media_file, mock.patch(
        "core.tasks.S3StorageClient.get_object_bytes",
        return_value=content,
    )


@pytest.mark.django_db
class TestTeacherBulkImport:
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

    def test_teacher_bulk_import_csv_success(
        self,
        api_client,
        user,
        organization,
        branch,
    ):
        api_client.force_authenticate(user=user)

        data = {
            "name": ["John Doe", "Jane Smith"],
            "father_name": ["Richard Doe", "William Smith"],
            "grandfather_name": ["Robert Doe", "James Smith"],
            "email": ["johndoe@example.com", "janesmith@example.com"],
            "phone_number": ["+251911111111", "+251922222222"],
            "employee_id": ["EMP-1001", "EMP-1002"],
            "joining_date": ["2024-09-01", "2024-09-02"],
            "specialization": ["Math", "Physics"],
            "bio": ["Math teacher bio", "Physics teacher bio"],
        }
        df = pd.DataFrame(data)
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        media_file, storage_mock = create_media(
            user=user,
            file_name="teachers.csv",
            content_type="text/csv",
            content=csv_buf.getvalue().encode("utf-8"),
        )

        payload = {
            "organization": str(organization.id),
            "branch": str(branch.id),
            "file": str(media_file.id),
        }

        with storage_mock:
            response = api_client.post(
                "/api/teachers/bulk-import/",
                payload,
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data["detail"] == "Bulk import process started."

        john = User.objects.get(email="johndoe@example.com")
        assert john.role == User.Role.TEACHER
        assert john.name == "John Doe"
        assert john.father_name == "Richard Doe"
        assert john.grandfather_name == "Robert Doe"
        assert john.phone_number == "+251911111111"

        teacher = Teacher.objects.get(user=john)
        assert teacher.organization == organization
        assert teacher.branch == branch
        assert teacher.employee_id == "EMP-1001"
        assert teacher.joining_date == date(2024, 9, 1)
        assert teacher.specialization == "Math"
        assert teacher.bio == "Math teacher bio"

        jane = User.objects.get(email="janesmith@example.com")
        assert jane.role == User.Role.TEACHER
        jane_teacher = Teacher.objects.get(user=jane)
        assert jane_teacher.employee_id == "EMP-1002"
        assert jane_teacher.specialization == "Physics"
        assert jane_teacher.bio == "Physics teacher bio"

    def test_teacher_bulk_import_excel_success(
        self,
        api_client,
        user,
        organization,
        branch,
    ):
        api_client.force_authenticate(user=user)

        data = {
            "name": ["Robert Doe"],
            "father_name": ["Richard Doe"],
            "grandfather_name": ["William Doe"],
            "email": ["robert@example.com"],
            "phone_number": ["+251933333333"],
            "employee_id": ["EMP-2001"],
            "joining_date": ["2024-09-03"],
            "specialization": ["Biology"],
            "bio": ["Biology teacher"],
        }
        df = pd.DataFrame(data)
        excel_buf = io.BytesIO()
        df.to_excel(excel_buf, index=False)
        media_file, storage_mock = create_media(
            user=user,
            file_name="teachers.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content=excel_buf.getvalue(),
        )

        payload = {
            "organization": str(organization.id),
            "branch": str(branch.id),
            "file": str(media_file.id),
        }

        with storage_mock:
            response = api_client.post(
                "/api/teachers/bulk-import/",
                payload,
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

        robert = User.objects.get(email="robert@example.com")
        assert robert.role == User.Role.TEACHER
        teacher = Teacher.objects.get(user=robert)
        assert teacher.organization == organization
        assert teacher.branch == branch
        assert teacher.employee_id == "EMP-2001"
        assert teacher.joining_date == date(2024, 9, 3)
        assert teacher.specialization == "Biology"
        assert teacher.bio == "Biology teacher"

    def test_teacher_bulk_import_generates_employee_id_and_defaults_joining_date(
        self,
        api_client,
        user,
        organization,
        branch,
        monkeypatch,
    ):
        api_client.force_authenticate(user=user)

        monkeypatch.setattr(
            "teachers.services.bulk_import.uuid.uuid4",
            lambda: UUID("12345678-1234-5678-1234-567812345678"),
        )

        data = {
            "name": ["Generated ID"],
            "father_name": ["Guardian"],
            "grandfather_name": ["Ancestor"],
            "email": ["generated@example.com"],
            "phone_number": ["+251944444444"],
            "employee_id": [""],
            "joining_date": [""],
            "specialization": ["Chemistry"],
            "bio": ["Generated teacher bio"],
        }
        df = pd.DataFrame(data)
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        media_file, storage_mock = create_media(
            user=user,
            file_name="teachers_generated.csv",
            content_type="text/csv",
            content=csv_buf.getvalue().encode("utf-8"),
        )

        payload = {
            "organization": str(organization.id),
            "branch": str(branch.id),
            "file": str(media_file.id),
        }

        with storage_mock:
            response = api_client.post(
                "/api/teachers/bulk-import/",
                payload,
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

        teacher = Teacher.objects.get(user__email="generated@example.com")
        assert teacher.employee_id == "EMP-12345678"
        assert teacher.joining_date == timezone.now().date()
        assert teacher.specialization == "Chemistry"
        assert teacher.bio == "Generated teacher bio"
        assert teacher.user.role == User.Role.TEACHER

    def test_teacher_bulk_import_validation_error(
        self,
        api_client,
        user,
        organization,
        branch,
    ):
        api_client.force_authenticate(user=user)

        # Create a conflicting user so the import hits email validation.
        UserFactory(email="duplicate@example.com")

        data = {
            "name": ["John Doe", "Jane Smith"],
            "father_name": ["Richard Doe", "William Smith"],
            "grandfather_name": ["Robert Doe", "James Smith"],
            "email": [
                "duplicate@example.com",
                "janesmith2@example.com",
            ],  # duplicate email
            "phone_number": [
                "+251944444444",
                "+251944444444",
            ],  # duplicate phone inside sheet
        }
        df = pd.DataFrame(data)
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        media_file, storage_mock = create_media(
            user=user,
            file_name="teachers_error.csv",
            content_type="text/csv",
            content=csv_buf.getvalue().encode("utf-8"),
        )

        payload = {
            "organization": str(organization.id),
            "branch": str(branch.id),
            "file": str(media_file.id),
        }

        with storage_mock:
            response = api_client.post(
                "/api/teachers/bulk-import/",
                payload,
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

        assert Teacher.objects.count() == 0
        assert User.objects.filter(email="janesmith2@example.com").exists() is False

        # Verify the import job failed
        job = ImportJob.objects.last()
        assert job.status == ImportJob.Status.FAILED
        assert job.errors is not None
        assert job.errors[0]["row"] == FAILED_IMPORT_ROW
        assert "email" in job.errors[0]["errors"]

    def test_import_status_is_scoped_to_authorized_user(
        self,
        api_client,
        user,
        organization,
        branch,
    ):
        media_file = MediaFileFactory(
            uploaded_by=user,
            file_name="teachers.csv",
            content_type="text/csv",
        )
        job = ImportJob.objects.create(
            file=media_file,
            module="teachers",
            organization=organization,
            branch=branch,
            created_by=user,
        )

        outsider = UserFactory()
        api_client.force_authenticate(user=outsider)

        response = api_client.get(f"/api/import-status/{job.id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
