from django.db import transaction
from django.db.models.signals import post_save
from django.db.models.signals import pre_save
from django.dispatch import receiver
from notifications.producers import create_announcement_notifications

from .models import Announcement
from .utils import send_priority_notifications


@receiver(pre_save, sender=Announcement)
def cache_previous_announcement_status(sender, instance, **kwargs):
    del sender, kwargs
    instance.previous_status = None
    if instance.pk:
        instance.previous_status = (
            Announcement.objects.filter(pk=instance.pk)
            .values_list("status", flat=True)
            .first()
        )


@receiver(post_save, sender=Announcement)
def trigger_urgent_announcement(sender, instance, created, **kwargs):
    """
    Signal to check if an announcement is urgent and trigger the async task.
    We check if it was just created, or if 'is_urgent' was changed to True (simplification: we trigger if it's urgent).
    For a more robust solution, we'd check if 'is_urgent' specifically changed.
    """  # noqa: E501
    if instance.is_urgent and instance.status in [
        Announcement.StatusChoices.SENT,
        Announcement.StatusChoices.SCHEDULED,
    ]:
        send_priority_notifications(instance.id)

    previous_status = getattr(instance, "previous_status", None)
    became_sent = (
        instance.status == Announcement.StatusChoices.SENT
        and previous_status != Announcement.StatusChoices.SENT
    )

    if (created and instance.status == Announcement.StatusChoices.SENT) or became_sent:
        transaction.on_commit(
            lambda: create_announcement_notifications(instance),
        )
