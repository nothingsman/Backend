from __future__ import annotations

from unittest import mock

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from media.models import MediaFile
from media.models import StatusChoices
from media.tests.factories import MediaFileFactory

pytestmark = pytest.mark.django_db
CONFIRMED_FILE_SIZE = 1024


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_user():
    return UserFactory()


@pytest.fixture
def authenticated_client(api_client, authenticated_user):
    api_client.force_authenticate(user=authenticated_user)
    return api_client


class TestUploadInitiation:
    def test_upload_requires_authentication(self, api_client):
        response = api_client.post(
            "/api/media/upload",
            {"file_name": "test.pdf", "content_type": "application/pdf"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["errors"][0]["code"] == "not_authenticated"

    def test_upload_creates_media_file(self, authenticated_client, authenticated_user):
        with mock.patch(
            "media.api.views.S3StorageClient.create_multipart_upload",
        ) as mock_create:
            mock_create.return_value = "upload-123"

            response = authenticated_client.post(
                "/api/media/upload",
                {"file_name": "test.pdf", "content_type": "application/pdf"},
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()["data"]
        assert "id" in data
        assert "key" in data
        assert data["upload_id"] == "upload-123"

        media = MediaFile.objects.get(id=data["id"])
        assert media.file_name == "test.pdf"
        assert media.content_type == "application/pdf"
        assert media.status == StatusChoices.PENDING
        assert media.uploaded_by == authenticated_user

    def test_upload_fingerprinting_returns_existing(
        self,
        authenticated_client,
        authenticated_user,
    ):
        with mock.patch(
            "media.api.views.MediaUploadViewSet._generate_fingerprint",
            return_value="same-fingerprint",
        ):
            with mock.patch(
                "media.api.views.S3StorageClient.create_multipart_upload",
            ) as mock_create:
                mock_create.return_value = "upload-1"

                response1 = authenticated_client.post(
                    "/api/media/upload",
                    {"file_name": "test.pdf", "content_type": "application/pdf"},
                    format="json",
                )

            first_id = response1.json()["data"]["id"]

            with mock.patch(
                "media.api.views.S3StorageClient.create_multipart_upload",
            ) as mock_create:
                mock_create.return_value = "upload-2"

                response2 = authenticated_client.post(
                    "/api/media/upload",
                    {"file_name": "test.pdf", "content_type": "application/pdf"},
                    format="json",
                )

        assert response2.status_code == status.HTTP_200_OK
        second_id = response2.json()["data"]["id"]
        assert str(first_id) == str(second_id)
        assert response2.json()["data"]["upload_id"] == "upload-2"
        assert MediaFile.objects.filter(uploaded_by=authenticated_user).count() == 1

    def test_upload_validates_file_name(self, authenticated_client):
        response = authenticated_client.post(
            "/api/media/upload",
            {"file_name": "", "content_type": "application/pdf"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        error = response.json()["errors"][0]
        assert error["field"] == "file_name"

    def test_upload_sanitizes_file_name(self, authenticated_client):
        with mock.patch(
            "media.api.views.S3StorageClient.create_multipart_upload",
        ) as mock_create:
            mock_create.return_value = "upload-123"

            response = authenticated_client.post(
                "/api/media/upload",
                {"file_name": "/path/to/file.pdf", "content_type": "application/pdf"},
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        media = MediaFile.objects.get(id=response.json()["data"]["id"])
        assert media.file_name == "file.pdf"


class TestMultipartPartUrl:
    def test_part_url_requires_authentication(self, api_client):
        media = MediaFileFactory(status=StatusChoices.PENDING)
        response = api_client.post(
            f"/api/media/{media.id}/multipart/part-url",
            {"upload_id": "upload-123", "part_number": 1},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_part_url_is_self_scoped(self, authenticated_client):
        other_user = UserFactory()
        media = MediaFileFactory(uploaded_by=other_user, status=StatusChoices.PENDING)

        response = authenticated_client.post(
            f"/api/media/{media.id}/multipart/part-url",
            {"upload_id": "upload-123", "part_number": 1},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_part_url_returns_presigned_url(
        self,
        authenticated_client,
        authenticated_user,
    ):
        media = MediaFileFactory(
            uploaded_by=authenticated_user,
            status=StatusChoices.PENDING,
        )

        with mock.patch(
            "media.api.views.S3StorageClient.get_presigned_part_url",
        ) as mock_part_url:
            mock_part_url.return_value = "https://s3.example.com/part-url"

            response = authenticated_client.post(
                f"/api/media/{media.id}/multipart/part-url",
                {"upload_id": "upload-123", "part_number": 1},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["presigned_url"] == "https://s3.example.com/part-url"


class TestMultipartCompletion:
    def test_complete_requires_authentication(self, api_client):
        media = MediaFileFactory(status=StatusChoices.PENDING)
        response = api_client.post(
            f"/api/media/{media.id}/multipart/complete",
            {
                "upload_id": "upload-123",
                "parts": [{"part_number": 1, "etag": "etag-1"}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_complete_is_self_scoped(self, authenticated_client):
        other_user = UserFactory()
        media = MediaFileFactory(uploaded_by=other_user, status=StatusChoices.PENDING)

        response = authenticated_client.post(
            f"/api/media/{media.id}/multipart/complete",
            {
                "upload_id": "upload-123",
                "parts": [{"part_number": 1, "etag": "etag-1"}],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_complete_verifies_object_exists(
        self,
        authenticated_client,
        authenticated_user,
    ):
        media = MediaFileFactory(
            uploaded_by=authenticated_user,
            status=StatusChoices.PENDING,
        )

        with (
            mock.patch(
                "media.api.views.S3StorageClient.complete_multipart_upload",
            ) as mock_complete,
            mock.patch(
                "media.api.views.S3StorageClient.head_object",
            ) as mock_head,
        ):
            mock_complete.return_value = {"ETag": "complete-etag"}
            mock_head.return_value = {
                "exists": True,
                "etag": "abc123def456",
                "size": CONFIRMED_FILE_SIZE,
                "content_type": "application/pdf",
            }

            response = authenticated_client.post(
                f"/api/media/{media.id}/multipart/complete",
                {
                    "upload_id": "upload-123",
                    "parts": [{"part_number": 1, "etag": "etag-1"}],
                },
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["status"] == StatusChoices.UPLOADED

        media.refresh_from_db()
        assert media.status == StatusChoices.UPLOADED
        assert media.etag == "abc123def456"
        assert media.size == CONFIRMED_FILE_SIZE

    def test_complete_fails_if_verification_fails(
        self,
        authenticated_client,
        authenticated_user,
    ):
        media = MediaFileFactory(
            uploaded_by=authenticated_user,
            status=StatusChoices.PENDING,
        )

        with (
            mock.patch(
                "media.api.views.S3StorageClient.complete_multipart_upload",
            ) as mock_complete,
            mock.patch(
                "media.api.views.S3StorageClient.head_object",
            ) as mock_head,
        ):
            mock_complete.return_value = {"ETag": "complete-etag"}
            mock_head.return_value = {
                "exists": False,
                "etag": None,
                "size": None,
                "content_type": None,
            }

            response = authenticated_client.post(
                f"/api/media/{media.id}/multipart/complete",
                {
                    "upload_id": "upload-123",
                    "parts": [{"part_number": 1, "etag": "etag-1"}],
                },
                format="json",
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["errors"][0]["code"] == "storage_object_missing"

        media.refresh_from_db()
        assert media.status == StatusChoices.FAILED

    def test_complete_fails_if_storage_completion_errors(
        self,
        authenticated_client,
        authenticated_user,
    ):
        media = MediaFileFactory(
            uploaded_by=authenticated_user,
            status=StatusChoices.PENDING,
        )

        with mock.patch(
            "media.api.views.S3StorageClient.complete_multipart_upload",
            side_effect=RuntimeError("boom"),
        ):
            response = authenticated_client.post(
                f"/api/media/{media.id}/multipart/complete",
                {
                    "upload_id": "upload-123",
                    "parts": [{"part_number": 1, "etag": "etag-1"}],
                },
                format="json",
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["errors"][0]["code"] == "multipart_completion_failed"

        media.refresh_from_db()
        assert media.status == StatusChoices.FAILED


class TestMultipartAbort:
    def test_abort_requires_authentication(self, api_client):
        media = MediaFileFactory(status=StatusChoices.PENDING)
        response = api_client.post(
            f"/api/media/{media.id}/multipart/abort",
            {"upload_id": "upload-123"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_abort_is_self_scoped(self, authenticated_client):
        other_user = UserFactory()
        media = MediaFileFactory(uploaded_by=other_user, status=StatusChoices.PENDING)

        response = authenticated_client.post(
            f"/api/media/{media.id}/multipart/abort",
            {"upload_id": "upload-123"},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_abort_marks_media_failed(
        self,
        authenticated_client,
        authenticated_user,
    ):
        media = MediaFileFactory(
            uploaded_by=authenticated_user,
            status=StatusChoices.PENDING,
        )

        with mock.patch(
            "media.api.views.S3StorageClient.abort_multipart_upload",
        ) as mock_abort:
            mock_abort.return_value = True

            response = authenticated_client.post(
                f"/api/media/{media.id}/multipart/abort",
                {"upload_id": "upload-123"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"data": None, "message": "Multipart upload aborted"}

        media.refresh_from_db()
        assert media.status == StatusChoices.FAILED


class TestMediaRetrieval:
    def test_retrieve_requires_authentication(self, api_client):
        media = MediaFileFactory()
        response = api_client.get(f"/api/media/{media.id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_retrieve_self_scoped(self, authenticated_client, authenticated_user):
        media = MediaFileFactory(uploaded_by=authenticated_user)

        response = authenticated_client.get(f"/api/media/{media.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert str(data["id"]) == str(media.id)

    def test_retrieve_not_found_for_other_users(
        self,
        authenticated_client,
    ):
        other_user = UserFactory()
        media = MediaFileFactory(uploaded_by=other_user)

        response = authenticated_client.get(f"/api/media/{media.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert str(data["id"]) == str(media.id)
        assert str(data["uploaded_by"]) == str(other_user.id)

    def test_retrieve_includes_download_url_when_uploaded(
        self,
        authenticated_client,
        authenticated_user,
    ):
        media = MediaFileFactory(
            uploaded_by=authenticated_user,
            status=StatusChoices.UPLOADED,
        )

        with mock.patch(
            "media.api.views.S3StorageClient.get_download_url",
        ) as mock_download:
            mock_download.return_value = "https://s3.example.com/download-url"

            response = authenticated_client.get(f"/api/media/{media.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["download_url"] == "https://s3.example.com/download-url"


class TestDownloadUrl:
    def test_download_url_requires_authentication(self, api_client):
        media = MediaFileFactory()
        response = api_client.get(f"/api/media/{media.id}/url")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_download_url_is_available_to_other_authenticated_users(
        self,
        authenticated_client,
    ):
        other_user = UserFactory()
        media = MediaFileFactory(
            uploaded_by=other_user,
            status=StatusChoices.UPLOADED,
        )

        with mock.patch(
            "media.api.views.S3StorageClient.get_download_url",
        ) as mock_download:
            mock_download.return_value = "https://s3.example.com/download-url"

            response = authenticated_client.get(f"/api/media/{media.id}/url")

        assert response.status_code == status.HTTP_200_OK
        assert (
            response.json()["data"]["download_url"]
            == "https://s3.example.com/download-url"
        )

    def test_download_url_requires_uploaded_status(
        self,
        authenticated_client,
        authenticated_user,
    ):
        media = MediaFileFactory(
            uploaded_by=authenticated_user,
            status=StatusChoices.PENDING,
        )

        response = authenticated_client.get(f"/api/media/{media.id}/url")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestMediaDeletion:
    def test_delete_requires_authentication(self, api_client):
        media = MediaFileFactory()
        response = api_client.delete(f"/api/media/{media.id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_soft_deletes_media(
        self,
        authenticated_client,
        authenticated_user,
    ):
        media = MediaFileFactory(uploaded_by=authenticated_user)

        response = authenticated_client.delete(f"/api/media/{media.id}")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"data": None, "message": "Media deleted"}

        media.refresh_from_db()
        assert media.status == StatusChoices.DELETED

    def test_delete_not_found_for_other_users(
        self,
        authenticated_client,
        authenticated_user,
    ):
        other_user = UserFactory()
        media = MediaFileFactory(uploaded_by=other_user)

        response = authenticated_client.delete(f"/api/media/{media.id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
