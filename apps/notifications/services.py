from django.contrib.contenttypes.models import ContentType
from notifications.models import Notification


def create_notification(
    recipient,
    notifiable,
    title,
    message,
    data=None,
) -> Notification:
    return Notification.objects.create(
        recipient=recipient,
        notifiable_type=ContentType.objects.get_for_model(
            notifiable,
            for_concrete_model=False,
        ),
        notifiable_id=str(notifiable.pk),
        title=title,
        message=message,
        data=data or {},
    )


def create_notification_once(  # noqa: PLR0913
    recipient,
    notifiable,
    title,
    message,
    *,
    event_key: str,
    data=None,
) -> Notification:
    notifiable_type = ContentType.objects.get_for_model(
        notifiable,
        for_concrete_model=False,
    )
    notifiable_id = str(notifiable.pk)
    payload = {"event_key": event_key, **(data or {})}

    existing = Notification.objects.filter(
        recipient=recipient,
        notifiable_type=notifiable_type,
        notifiable_id=notifiable_id,
        data__event_key=event_key,
    ).first()
    if existing is not None:
        return existing

    return Notification.objects.create(
        recipient=recipient,
        notifiable_type=notifiable_type,
        notifiable_id=notifiable_id,
        title=title,
        message=message,
        data=payload,
    )
