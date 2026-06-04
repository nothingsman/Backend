from http import HTTPStatus

import pytest
from django.urls import reverse

from media.tests.factories import MediaFileFactory


@pytest.mark.django_db
def test_view_media_file_with_uploader_missing_email(admin_client) -> None:
    media_file = MediaFileFactory(
        uploaded_by__email=None,
        uploaded_by__name="No Email Uploader",
    )
    url = reverse(
        "admin:media_mediafile_change",
        kwargs={"object_id": media_file.pk},
    )

    response = admin_client.get(url)

    assert response.status_code == HTTPStatus.OK
