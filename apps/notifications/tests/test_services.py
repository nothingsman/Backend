import pytest
from announcements.tests.factories import AnnouncementFactory
from notifications.models import Notification
from notifications.services import create_notification_once


@pytest.mark.django_db
def test_create_notification_once_reuses_existing_event_key():
    announcement = AnnouncementFactory()

    first = create_notification_once(
        recipient=announcement.organization.owner,
        notifiable=announcement,
        title="One",
        message="Body",
        event_key="announcement.sent:test",
        data={"category": "announcement"},
    )
    second = create_notification_once(
        recipient=announcement.organization.owner,
        notifiable=announcement,
        title="Two",
        message="Changed body",
        event_key="announcement.sent:test",
        data={"category": "announcement"},
    )

    assert first.id == second.id
    assert Notification.objects.count() == 1
