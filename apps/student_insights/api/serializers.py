from rest_framework import serializers
from student_insights.models import StudentInsight


class StudentInsightSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(
        source="get_category_display",
        read_only=True,
    )
    risk_band_display = serializers.CharField(
        source="get_risk_band_display",
        read_only=True,
    )
    safety_status_display = serializers.CharField(
        source="get_safety_status_display",
        read_only=True,
    )

    class Meta:
        model = StudentInsight
        fields = [
            "id",
            "student",
            "category",
            "category_display",
            "risk_band",
            "risk_band_display",
            "title",
            "message",
            "confidence_label",
            "recommended_actions",
            "safety_status",
            "safety_status_display",
            "delivery_status",
            "created_at",
            "delivered_at",
        ]


class ManualStudentInsightTriggerResponseSerializer(serializers.Serializer):
    created = serializers.BooleanField()
    reused_existing = serializers.BooleanField(required=False)
    insight_id = serializers.UUIDField(required=False)
    category = serializers.CharField(required=False)
    risk_band = serializers.CharField(required=False)
    delivery_status = serializers.CharField(required=False)
    reason_code = serializers.CharField(required=False, allow_blank=True)
    message = serializers.CharField()
    source_event_type = serializers.CharField(required=False, allow_blank=True)
    source_model = serializers.CharField(required=False, allow_blank=True)
    source_id = serializers.CharField(required=False, allow_blank=True)
