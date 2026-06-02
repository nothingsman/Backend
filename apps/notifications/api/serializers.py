from announcements.models import Announcement
from assessments.models import Assessment
from assessments.models import AssessmentResult
from attendance.models import Attendance
from messaging.models import ChatMessage
from notifications.models import Notification
from rest_framework import serializers


def get_public_notifiable_type(obj) -> str:
    if isinstance(obj, Announcement):
        return "announcement"
    if isinstance(obj, ChatMessage):
        return "chat_message"
    if isinstance(obj, Assessment):
        return "assessment"
    if isinstance(obj, AssessmentResult):
        return "assessment_result"
    if isinstance(obj, Attendance):
        return "attendance"
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
