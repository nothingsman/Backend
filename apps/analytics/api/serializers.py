from analytics.models import InterventionLog
from rest_framework import serializers


class DashboardOverviewQuerySerializer(serializers.Serializer):
    section_id = serializers.UUIDField()
    academic_year_id = serializers.UUIDField()
    subject_id = serializers.UUIDField(required=False)
    section_name = serializers.CharField(required=False, allow_blank=True)
    subject_name = serializers.CharField(required=False, allow_blank=True)


class ParentEngagementSerializer(serializers.Serializer):
    high = serializers.IntegerField(min_value=0)
    moderate = serializers.IntegerField(min_value=0)
    low = serializers.IntegerField(min_value=0)


class PerformanceDistributionSerializer(serializers.Serializer):
    A = serializers.IntegerField(min_value=0)
    B = serializers.IntegerField(min_value=0)
    C = serializers.IntegerField(min_value=0)
    F = serializers.IntegerField(min_value=0)


class DashboardOverviewResponseSerializer(serializers.Serializer):
    total_students = serializers.IntegerField(min_value=0)
    average_performance = serializers.FloatField()
    tasks_due = serializers.IntegerField(min_value=0)
    performance_distribution = PerformanceDistributionSerializer()
    parent_engagement = ParentEngagementSerializer()


class InterventionLogSerializer(serializers.ModelSerializer):
    intervention_type_display = serializers.CharField(
        source="get_intervention_type_display",
        read_only=True,
    )
    severity_display = serializers.CharField(
        source="get_severity_display",
        read_only=True,
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = InterventionLog
        fields = [
            "id",
            "organization",
            "student",
            "student_name",
            "intervention_type",
            "intervention_type_display",
            "severity",
            "severity_display",
            "status",
            "status_display",
            "source_model",
            "source_id",
            "title",
            "description",
            "resolved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_student_name(self, obj) -> str:
        return f"{obj.student.first_name} {obj.student.last_name}"


class StudentAnalyticsSummarySerializer(serializers.Serializer):
    overall_grade = serializers.FloatField()
    attendance_rate = serializers.FloatField()
    assignment_completion_rate = serializers.FloatField()
    completed_assignments = serializers.IntegerField()
    pending_assignments = serializers.IntegerField()
    missing_assignments = serializers.IntegerField()
    class_average_overall = serializers.FloatField(allow_null=True)
    class_rank = serializers.IntegerField(allow_null=True)
    class_size = serializers.IntegerField(allow_null=True)
    risk_band = serializers.ChoiceField(
        choices=["low", "medium", "high", "unknown"],
    )
    trend_direction = serializers.ChoiceField(choices=["up", "down", "steady"])
    trend_delta = serializers.FloatField()
    headline_insight = serializers.CharField(allow_null=True)


class StudentAnalyticsSubjectPerformanceSerializer(serializers.Serializer):
    subject = serializers.CharField()
    student_score = serializers.FloatField()
    class_average = serializers.FloatField()
    target_score = serializers.FloatField(allow_null=True)
    teacher_name = serializers.CharField(allow_null=True)
    color = serializers.RegexField(
        regex=r"^#[0-9A-Fa-f]{6}$",
        allow_null=True,
    )


class StudentAnalyticsTrendPointSerializer(serializers.Serializer):
    label = serializers.CharField()
    score = serializers.FloatField()
    recorded_at = serializers.DateTimeField(allow_null=True)


class StudentAnalyticsTrendSeriesSerializer(serializers.Serializer):
    subject = serializers.CharField()
    color = serializers.RegexField(
        regex=r"^#[0-9A-Fa-f]{6}$",
        allow_null=True,
    )
    points = StudentAnalyticsTrendPointSerializer(many=True)


class StudentAnalyticsGradeTrendSerializer(serializers.Serializer):
    series = StudentAnalyticsTrendSeriesSerializer(many=True)


class StudentAnalyticsHeatmapCellSerializer(serializers.Serializer):
    date = serializers.DateField(format="%Y-%m-%d")
    week = serializers.IntegerField(min_value=1, max_value=4)
    weekday = serializers.IntegerField(min_value=0, max_value=6)
    day_label = serializers.CharField()
    submission_count = serializers.IntegerField(min_value=0)


class StudentAnalyticsDataSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    generated_at = serializers.DateTimeField()
    analysis_window_label = serializers.CharField()
    summary = StudentAnalyticsSummarySerializer()
    subject_performance = StudentAnalyticsSubjectPerformanceSerializer(many=True)
    grade_trend = StudentAnalyticsGradeTrendSerializer()
    submission_heatmap = StudentAnalyticsHeatmapCellSerializer(many=True)
    recommended_actions = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
    )


class StudentAnalyticsResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = StudentAnalyticsDataSerializer()
