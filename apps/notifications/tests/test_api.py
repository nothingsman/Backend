import pytest
from accounts.tests.factories import UserFactory
from announcements.tests.factories import AnnouncementFactory
from notifications.services import create_notification
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestNotificationAPI:
    @pytest.fixture
    def api_client(self):
        return APIClient()

    @pytest.fixture
    def recipient(self):
        return UserFactory()

    @pytest.fixture
    def other_user(self):
        return UserFactory()

    @pytest.fixture
    def announcement(self):
        return AnnouncementFactory()

    def test_list_filters_to_authenticated_user_and_supports_read_filters_and_pagination(  # noqa: E501
        self,
        api_client,
        recipient,
        other_user,
        announcement,
    ):
        api_client.force_authenticate(user=recipient)
        first = create_notification(
            recipient=recipient,
            notifiable=announcement,
            title="First",
            message="One",
        )
        second = create_notification(
            recipient=recipient,
            notifiable=announcement,
            title="Second",
            message="Two",
        )
        second.mark_as_read()
        create_notification(
            recipient=other_user,
            notifiable=announcement,
            title="Other",
            message="Three",
        )

        response = api_client.get("/api/notifications/", {"limit": 1, "page": 1})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == len([first, second])
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["id"] == str(second.id)

        unread_response = api_client.get("/api/notifications/", {"type": "unread"})
        assert unread_response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in unread_response.data["results"]] == [
            str(first.id),
        ]

        read_response = api_client.get("/api/notifications/", {"type": "read"})
        assert read_response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in read_response.data["results"]] == [
            str(second.id),
        ]

    def test_mark_as_read_only_allows_the_recipient(
        self,
        api_client,
        recipient,
        other_user,
        announcement,
    ):
        notification = create_notification(
            recipient=recipient,
            notifiable=announcement,
            title="Mark me",
            message="Message",
        )

        api_client.force_authenticate(user=recipient)
        response = api_client.post(
            f"/api/notifications/{notification.id}/mark-as-read/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["read_at"] is not None

        api_client.force_authenticate(user=other_user)
        response = api_client.post(
            f"/api/notifications/{notification.id}/mark-as-read/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_mark_all_read_and_counter(
        self,
        api_client,
        recipient,
        announcement,
    ):
        create_notification(
            recipient=recipient,
            notifiable=announcement,
            title="Unread one",
            message="One",
        )
        read_notification = create_notification(
            recipient=recipient,
            notifiable=announcement,
            title="Already read",
            message="Two",
        )
        read_notification.mark_as_read()

        api_client.force_authenticate(user=recipient)

        counter_before = api_client.get("/api/notifications/counter/")
        assert counter_before.status_code == status.HTTP_200_OK
        assert counter_before.data == {"unread_count": 1}

        response = api_client.post(
            "/api/notifications/mark-all-read/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"updated_count": 1}

        counter_after = api_client.get("/api/notifications/counter/")
        assert counter_after.status_code == status.HTTP_200_OK
        assert counter_after.data == {"unread_count": 0}
