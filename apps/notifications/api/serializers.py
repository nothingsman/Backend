from announcements.models import Announcement
from assessments.models import Assessment
from assessments.models import AssessmentResult
from attendance.models import Attendance
from messaging.models import ChatMessage
from notifications.models import Notification
from rest_framework import serializers
from student_insights.models import StudentInsight

NOTIFIABLE_TYPE_NAMES = (
    (Announcement, "announcement"),
    (ChatMessage, "chat_message"),
    (Assessment, "assessment"),
    (AssessmentResult, "assessment_result"),
    (Attendance, "attendance"),
    (StudentInsight, "student_insight"),
)


def get_public_notifiable_type(obj) -> str:
    for model, public_name in NOTIFIABLE_TYPE_NAMES:
        if isinstance(obj, model):
            return public_name
    return obj.__class__.__name__.lower()


class NotificationSerializer(serializers.ModelSerializer):
    notifiable = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "data",
            "read_at",
            "created_at",
            "notifiable",
        ]

    def get_notifiable(self, obj):
        target = obj.notifiable
        if target is None:
            return {
                "type": obj.notifiable_type.model,
                "id": obj.notifiable_id,
            }

        return {
            "type": get_public_notifiable_type(target),
            "id": str(target.pk),
        }
