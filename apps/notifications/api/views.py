from django.utils import timezone
from notifications.api.serializers import NotificationSerializer
from notifications.models import Notification
from rest_framework import mixins
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet


class NotificationPagination(PageNumberPagination):
    page_size_query_param = "limit"
    page_query_param = "page"


class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    serializer_class = NotificationSerializer
    pagination_class = NotificationPagination
    lookup_field = "id"

    def get_queryset(self):
        queryset = Notification.objects.select_related("notifiable_type").filter(
            recipient=self.request.user,
        )
        notification_type = self.request.query_params.get("type")
        if notification_type == "read":
            queryset = queryset.filter(read_at__isnull=False)
        elif notification_type == "unread":
            queryset = queryset.filter(read_at__isnull=True)
        return queryset.order_by("-created_at")

    @action(detail=True, methods=["post"], url_path="mark-as-read")
    def mark_as_read(self, request, *args, **kwargs):
        notification = self.get_object()
        notification.mark_as_read()
        serializer = self.get_serializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request, *args, **kwargs):
        updated_count = (
            self.get_queryset()
            .filter(read_at__isnull=True)
            .update(
                read_at=timezone.now(),
                updated_at=timezone.now(),
            )
        )
        return Response({"updated_count": updated_count}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="counter")
    def counter(self, request, *args, **kwargs):
        unread_count = self.get_queryset().filter(read_at__isnull=True).count()
        return Response({"unread_count": unread_count}, status=status.HTTP_200_OK)
