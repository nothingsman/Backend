import uuid

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("analytics", "0001_initial"),
        ("branches", "0001_initial"),
        ("organizations", "0009_alter_organization_license_no_lookup_hash_and_more"),
        ("students", "0012_alter_parent_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudentInsight",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                (
                    "source_event_type",
                    models.CharField(
                        choices=[
                            ("ASSESSMENT_RESULT", "Assessment Result"),
                            ("ATTENDANCE", "Attendance"),
                            ("ATTENDANCE_REASON", "Attendance Reason"),
                            ("CHAT_MESSAGE", "Chat Message"),
                        ],
                        max_length=32,
                        verbose_name="Source Event Type",
                    ),
                ),
                ("source_model", models.CharField(max_length=100, verbose_name="Source Model")),
                ("source_id", models.UUIDField(blank=True, null=True, verbose_name="Source ID")),
                ("dedupe_key", models.CharField(db_index=True, max_length=255, verbose_name="Dedupe Key")),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("ACADEMICS", "Academics"),
                            ("ATTENDANCE", "Attendance"),
                            ("ENGAGEMENT", "Engagement"),
                            ("COMMUNICATION", "Communication"),
                        ],
                        max_length=20,
                        verbose_name="Category",
                    ),
                ),
                (
                    "risk_band",
                    models.CharField(
                        choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High")],
                        max_length=10,
                        verbose_name="Risk Band",
                    ),
                ),
                ("title", models.CharField(max_length=255, verbose_name="Title")),
                ("message", models.TextField(blank=True, verbose_name="Message")),
                ("confidence_label", models.CharField(blank=True, max_length=20, verbose_name="Confidence Label")),
                ("recommended_actions", models.JSONField(blank=True, default=list, verbose_name="Recommended Actions")),
                ("evidence", models.JSONField(blank=True, default=dict, verbose_name="Evidence")),
                ("model_input_summary", models.JSONField(blank=True, default=dict, verbose_name="Model Input Summary")),
                ("model_output", models.JSONField(blank=True, default=dict, verbose_name="Model Output")),
                (
                    "safety_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("APPROVED", "Approved"),
                            ("FALLBACK", "Fallback"),
                            ("REJECTED", "Rejected"),
                        ],
                        default="PENDING",
                        max_length=15,
                        verbose_name="Safety Status",
                    ),
                ),
                ("safety_notes", models.JSONField(blank=True, default=list, verbose_name="Safety Notes")),
                (
                    "delivery_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("DELIVERED", "Delivered"),
                            ("SUPPRESSED", "Suppressed"),
                            ("FAILED", "Failed"),
                        ],
                        default="PENDING",
                        max_length=15,
                        verbose_name="Delivery Status",
                    ),
                ),
                ("delivered_at", models.DateTimeField(blank=True, null=True, verbose_name="Delivered At")),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="student_insights",
                        to="branches.branch",
                        verbose_name="Branch",
                    ),
                ),
                (
                    "intervention_log",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="student_insights",
                        to="analytics.interventionlog",
                        verbose_name="Intervention Log",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="student_insights",
                        to="organizations.organization",
                        verbose_name="Organization",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="student_insights",
                        to="students.student",
                        verbose_name="Student",
                    ),
                ),
            ],
            options={
                "verbose_name": "Student Insight",
                "verbose_name_plural": "Student Insights",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="studentinsight",
            index=models.Index(fields=["organization", "student", "category"], name="student_insi_organiz_1964ec_idx"),
        ),
        migrations.AddIndex(
            model_name="studentinsight",
            index=models.Index(fields=["student", "risk_band", "created_at"], name="student_insi_student_709810_idx"),
        ),
        migrations.AddIndex(
            model_name="studentinsight",
            index=models.Index(fields=["delivery_status", "created_at"], name="student_insi_deliver_485e83_idx"),
        ),
    ]
