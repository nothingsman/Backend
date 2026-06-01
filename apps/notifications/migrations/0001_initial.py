import uuid

from django.conf import settings
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                ("notifiable_id", models.CharField(max_length=64)),
                ("title", models.CharField(max_length=255)),
                ("message", models.TextField()),
                ("data", models.JSONField(blank=True, default=dict)),
                ("read_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                (
                    "notifiable_type",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=models.deletion.CASCADE,
                        related_name="notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["recipient"], name="notificatio_recipie_be3f1a_idx"),
                    models.Index(fields=["read_at"], name="notificatio_read_at_6329f9_idx"),
                    models.Index(fields=["created_at"], name="notificatio_created_46ad24_idx"),
                    models.Index(
                        fields=["notifiable_type", "notifiable_id"],
                        name="notificatio_notifia_c4c036_idx",
                    ),
                ],
            },
        ),
    ]
