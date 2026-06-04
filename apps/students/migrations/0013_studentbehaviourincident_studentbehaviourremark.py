import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("students", "0012_alter_parent_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudentBehaviourIncident",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                ("title", models.CharField(max_length=255, verbose_name="Title")),
                ("description", models.TextField(verbose_name="Description")),
                (
                    "severity",
                    models.CharField(
                        choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High")],
                        default="MEDIUM",
                        max_length=20,
                        verbose_name="Severity",
                    ),
                ),
                ("occurred_at", models.DateTimeField(verbose_name="Occurred At")),
                (
                    "source",
                    models.CharField(
                        default="Teacher Incident",
                        max_length=100,
                        verbose_name="Source",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="behaviour_incidents",
                        to="students.student",
                        verbose_name="Student",
                    ),
                ),
                (
                    "teacher",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="student_behaviour_incidents",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Teacher",
                    ),
                ),
            ],
            options={
                "verbose_name": "Student Behaviour Incident",
                "verbose_name_plural": "Student Behaviour Incidents",
                "ordering": ["-occurred_at", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="StudentBehaviourRemark",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                ("title", models.CharField(max_length=255, verbose_name="Title")),
                ("description", models.TextField(verbose_name="Description")),
                (
                    "severity",
                    models.CharField(
                        choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High")],
                        default="LOW",
                        max_length=20,
                        verbose_name="Severity",
                    ),
                ),
                ("occurred_at", models.DateTimeField(verbose_name="Occurred At")),
                (
                    "source",
                    models.CharField(
                        default="Teacher Remark",
                        max_length=100,
                        verbose_name="Source",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="behaviour_remarks",
                        to="students.student",
                        verbose_name="Student",
                    ),
                ),
                (
                    "teacher",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="student_behaviour_remarks",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Teacher",
                    ),
                ),
            ],
            options={
                "verbose_name": "Student Behaviour Remark",
                "verbose_name_plural": "Student Behaviour Remarks",
                "ordering": ["-occurred_at", "-created_at"],
            },
        ),
    ]
