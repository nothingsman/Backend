import pytest
from announcements.tests.factories import AnnouncementFactory
from django.contrib.contenttypes.models import ContentType
from messaging.tests.factories import ChatMessageFactory
from notifications.models import Notification
from notifications.services import create_notification


@pytest.mark.django_db
def test_notification_helpers_and_ordering():
    announcement = AnnouncementFactory()
    first = create_notification(
        recipient=announcement.organization.owner,
        notifiable=announcement,
        title="Older",
        message="Older message",
    )
    second = create_notification(
        recipient=announcement.organization.owner,
        notifiable=announcement,
        title="Newer",
        message="Newer message",
    )

    first.mark_as_read()
    first.refresh_from_db()
    assert first.is_read is True
    assert first.is_unread is False
    assert first.read_at is not None

    first.mark_as_unread()
    first.refresh_from_db()
    assert first.is_read is False
    assert first.is_unread is True
    assert first.read_at is None

    ordered_ids = list(Notification.objects.values_list("id", flat=True))
    assert ordered_ids == [second.id, first.id]


@pytest.mark.django_db
def test_notification_generic_relation_round_trip_for_announcement_and_chat_message():
    announcement = AnnouncementFactory()
    announcement_notification = create_notification(
        recipient=announcement.organization.owner,
        notifiable=announcement,
        title="Announcement",
        message="Announcement body",
    )

    message = ChatMessageFactory()
    chat_notification = create_notification(
        recipient=message.thread.teacher.user,
        notifiable=message,
        title="Chat",
        message="Chat body",
    )

    assert announcement_notification.notifiable == announcement
    assert chat_notification.notifiable == message


@pytest.mark.django_db
def test_create_notification_sets_content_type_string_id_and_default_data():
    announcement = AnnouncementFactory()

    notification = create_notification(
        recipient=announcement.organization.owner,
        notifiable=announcement,
        title="Created",
        message="Body",
    )

    assert notification.notifiable_type == ContentType.objects.get_for_model(
        announcement,
        for_concrete_model=False,
    )
    assert notification.notifiable_id == str(announcement.pk)
    assert notification.data == {}
