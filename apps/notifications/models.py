from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel
from core.models import UUIDModel


class Notification(UUIDModel, TimeStampedModel):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True,
    )
    notifiable_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
    )
    notifiable_id = models.CharField(max_length=64)
    notifiable = GenericForeignKey("notifiable_type", "notifiable_id")
    title = models.CharField(max_length=255)
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient"]),
            models.Index(fields=["read_at"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["notifiable_type", "notifiable_id"]),
        ]

    def mark_as_read(self):
        if self.read_at is None:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at", "updated_at"])

    def mark_as_unread(self):
        if self.read_at is not None:
            self.read_at = None
            self.save(update_fields=["read_at", "updated_at"])

    @property
    def is_read(self):
        return self.read_at is not None

    @property
    def is_unread(self):
        return not self.is_read
