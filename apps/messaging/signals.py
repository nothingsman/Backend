from django.db.models.signals import post_save
from django.dispatch import receiver
from messaging.models import ChatMessage
from notifications.producers import create_chat_message_notification


@receiver(post_save, sender=ChatMessage)
def create_message_notification(sender, instance, created, **kwargs):
    del sender, kwargs
    if created:
        create_chat_message_notification(instance)
