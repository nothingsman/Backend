from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from core.api.exceptions import error_response
from core.api.mixins import ApiEnvelopeMixin
from core.api.serializers import ApiErrorResponseSerializer
from core.api.serializers import EmptyDataResponseSerializer
from media.models import MediaFile
from media.models import StatusChoices
from media.storage import S3StorageClient

from .serializers import DownloadUrlResponseEnvelopeSerializer
from .serializers import DownloadUrlResponseSerializer
from .serializers import MediaFileResponseEnvelopeSerializer
from .serializers import MediaFileSerializer
from .serializers import MultipartAbortRequestSerializer
from .serializers import MultipartCompleteRequestSerializer
from .serializers import MultipartPartUrlRequestSerializer
from .serializers import MultipartPartUrlResponseEnvelopeSerializer
from .serializers import MultipartPartUrlResponseSerializer
from .serializers import MultipartStatusResponseEnvelopeSerializer
from .serializers import MultipartStatusResponseSerializer
from .serializers import UploadInitSerializer
from .serializers import UploadResponseEnvelopeSerializer
from .serializers import UploadResponseSerializer

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from rest_framework.request import Request


@extend_schema_view(
    retrieve=extend_schema(
        responses={
            status.HTTP_200_OK: MediaFileResponseEnvelopeSerializer,
            status.HTTP_404_NOT_FOUND: ApiErrorResponseSerializer,
        },
    ),
    destroy=extend_schema(
        responses={
            status.HTTP_200_OK: EmptyDataResponseSerializer,
            status.HTTP_404_NOT_FOUND: ApiErrorResponseSerializer,
        },
    ),
)
class MediaUploadViewSet(ApiEnvelopeMixin, GenericViewSet):
    permission_classes = [IsAuthenticated]
    queryset = MediaFile.objects.select_related("uploaded_by")
    owner_scoped_actions = {
        "get_multipart_part_url",
        "complete_multipart_upload",
        "abort_multipart_upload",
        "destroy",
    }

    def _get_storage_client(self) -> S3StorageClient:
        return S3StorageClient()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.none()

        if self.action in self.owner_scoped_actions:
            return self.queryset.filter(uploaded_by=self.request.user)

        return self.queryset

    def get_serializer_class(self):
        if self.action == "upload":
            return UploadInitSerializer
        if self.action == "get_multipart_part_url":
            return MultipartPartUrlRequestSerializer
        if self.action == "complete_multipart_upload":
            return MultipartCompleteRequestSerializer
        if self.action == "abort_multipart_upload":
            return MultipartAbortRequestSerializer
        if self.action == "get_download_url":
            return DownloadUrlResponseSerializer
        return MediaFileSerializer

    def _generate_storage_key(self, media_id: str, file_name: str) -> str:
        user_id = self.request.user.id
        safe_name = "".join(c for c in file_name if c.isalnum() or c in "._- ")
        return f"media/{user_id}/{media_id}/{safe_name}"

    def _get_upload_expires_in(self) -> int:
        return settings.MEDIA_UPLOAD_SETTINGS["PRESIGNED_URL_TTL"]

    def _build_upload_response(
        self,
        media: MediaFile,
        upload_id: str,
    ) -> dict[str, str | int]:
        return {
            "id": media.id,
            "key": media.key,
            "upload_id": upload_id,
            "expires_in": self._get_upload_expires_in(),
        }

    def _mark_upload_failed(self, media: MediaFile) -> None:
        media.status = StatusChoices.FAILED
        media.save(update_fields=["status"])

    def _build_status_response(self, media: MediaFile) -> dict[str, str | int]:
        return {
            "id": media.id,
            "status": media.status,
            "etag": media.etag or "",
            "size": media.size or 0,
        }

    def _verify_uploaded_object(self, media: MediaFile) -> Response | None:
        client = self._get_storage_client()
        try:
            obj_info = client.head_object(media.key)
        except Exception:
            logger.exception(
                "Failed to verify object: media_id=%s",
                media.id,
            )
            self._mark_upload_failed(media)
            return error_response(
                detail="Failed to verify upload in storage",
                code="upload_verification_failed",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if not obj_info["exists"]:
            logger.warning(
                "Object not found in storage: media_id=%s, key=%s",
                media.id,
                media.key,
            )
            self._mark_upload_failed(media)
            return error_response(
                detail="Object not found in storage",
                code="storage_object_missing",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        media.status = StatusChoices.UPLOADED
        media.etag = obj_info["etag"]
        media.size = obj_info["size"]
        media.save(update_fields=["status", "etag", "size"])
        return None

    @extend_schema(
        request=UploadInitSerializer,
        responses={
            status.HTTP_200_OK: UploadResponseEnvelopeSerializer,
            status.HTTP_201_CREATED: UploadResponseEnvelopeSerializer,
            status.HTTP_400_BAD_REQUEST: ApiErrorResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request: Request) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_name = serializer.validated_data["file_name"]
        content_type = serializer.validated_data["content_type"]

        settings_dict = settings.MEDIA_UPLOAD_SETTINGS
        bucket = settings_dict["BUCKET_NAME"]

        media = MediaFile.objects.create(
            bucket=bucket,
            file_name=file_name,
            content_type=content_type,
            status=StatusChoices.PENDING,
            uploaded_by=request.user,
        )

        media.key = self._generate_storage_key(str(media.id), file_name)
        media.save(update_fields=["key"])

        client = self._get_storage_client()
        upload_id = client.create_multipart_upload(
            media.key,
            content_type=content_type,
        )

        logger.info(
            "Upload initiated: user=%s, media_id=%s, key=%s",
            request.user.id,
            media.id,
            media.key,
        )

        response_data = self._build_upload_response(media, upload_id)
        response_serializer = UploadResponseSerializer(response_data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=MultipartPartUrlRequestSerializer,
        responses={
            status.HTTP_200_OK: MultipartPartUrlResponseEnvelopeSerializer,
            status.HTTP_400_BAD_REQUEST: ApiErrorResponseSerializer,
            status.HTTP_404_NOT_FOUND: ApiErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["post"], url_path="multipart/part-url")
    def get_multipart_part_url(
        self,
        request: Request,
        pk: str | None = None,
    ) -> Response:
        media = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if media.status != StatusChoices.PENDING:
            return error_response(
                detail="Multipart upload is not available for this media item",
                code="upload_not_pending",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        upload_id = serializer.validated_data["upload_id"]
        part_number = serializer.validated_data["part_number"]
        expires_in = self._get_upload_expires_in()
        presigned_url = self._get_storage_client().get_presigned_part_url(
            media.key,
            upload_id=upload_id,
            part_number=part_number,
            expires_in=expires_in,
        )
        response_data = {
            "presigned_url": presigned_url,
            "expires_in": expires_in,
        }
        response_serializer = MultipartPartUrlResponseSerializer(response_data)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=MultipartCompleteRequestSerializer,
        responses={
            status.HTTP_200_OK: MultipartStatusResponseEnvelopeSerializer,
            status.HTTP_400_BAD_REQUEST: ApiErrorResponseSerializer,
            status.HTTP_404_NOT_FOUND: ApiErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["post"], url_path="multipart/complete")
    def complete_multipart_upload(
        self,
        request: Request,
        pk: str | None = None,
    ) -> Response:
        media = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if media.status == StatusChoices.DELETED:
            return error_response(
                detail="Media has been deleted",
                code="media_deleted",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if media.status != StatusChoices.PENDING:
            return error_response(
                detail="Multipart upload is not available for this media item",
                code="upload_not_pending",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            self._get_storage_client().complete_multipart_upload(
                media.key,
                upload_id=serializer.validated_data["upload_id"],
                parts=[
                    {
                        "PartNumber": part["part_number"],
                        "ETag": part["etag"],
                    }
                    for part in serializer.validated_data["parts"]
                ],
            )
        except Exception:
            logger.exception(
                "Failed to complete multipart upload: media_id=%s",
                media.id,
            )
            self._mark_upload_failed(media)
            return error_response(
                detail="Failed to complete multipart upload",
                code="multipart_completion_failed",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        verification_error = self._verify_uploaded_object(media)
        if verification_error is not None:
            return verification_error

        logger.info(
            "Multipart upload completed: media_id=%s, size=%s, etag=%s",
            media.id,
            media.size,
            media.etag,
        )

        response_serializer = MultipartStatusResponseSerializer(
            self._build_status_response(media),
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=MultipartAbortRequestSerializer,
        responses={
            status.HTTP_200_OK: EmptyDataResponseSerializer,
            status.HTTP_400_BAD_REQUEST: ApiErrorResponseSerializer,
            status.HTTP_404_NOT_FOUND: ApiErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["post"], url_path="multipart/abort")
    def abort_multipart_upload(
        self,
        request: Request,
        pk: str | None = None,
    ) -> Response:
        media = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if media.status != StatusChoices.PENDING:
            return error_response(
                detail="Multipart upload is not available for this media item",
                code="upload_not_pending",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            self._get_storage_client().abort_multipart_upload(
                media.key,
                upload_id=serializer.validated_data["upload_id"],
            )
        except Exception:
            logger.exception(
                "Failed to abort multipart upload: media_id=%s",
                media.id,
            )
            return error_response(
                detail="Failed to abort multipart upload",
                code="multipart_abort_failed",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        self._mark_upload_failed(media)
        return Response(
            {"data": None, "message": "Multipart upload aborted"},
            status=status.HTTP_200_OK,
        )

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        media = self.get_object()
        serializer = MediaFileSerializer(media, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        request=None,
        responses={
            status.HTTP_200_OK: DownloadUrlResponseEnvelopeSerializer,
            status.HTTP_400_BAD_REQUEST: ApiErrorResponseSerializer,
            status.HTTP_404_NOT_FOUND: ApiErrorResponseSerializer,
            status.HTTP_500_INTERNAL_SERVER_ERROR: ApiErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["get"], url_path="url")
    def get_download_url(self, request: Request, pk: str | None = None) -> Response:
        media = self.get_object()

        if media.status != StatusChoices.UPLOADED:
            return error_response(
                detail="File not yet uploaded",
                code="file_not_uploaded",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        client = self._get_storage_client()
        try:
            download_url = client.get_download_url(media.key)
            return Response({"download_url": download_url}, status=status.HTTP_200_OK)
        except Exception:
            logger.exception(
                "Failed to generate download URL: media_id=%s",
                media.id,
            )
            return error_response(
                detail="Failed to generate download URL",
                code="download_url_failed",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        media = self.get_object()
        media.status = StatusChoices.DELETED
        media.save(update_fields=["status"])

        logger.info("Media marked deleted: media_id=%s", media.id)
        return Response(
            {"data": None, "message": "Media deleted"},
            status=status.HTTP_200_OK,
        )
