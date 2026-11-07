"""
Notification services.
Keep business logic out of views.
"""
from typing import Any
from django.core.mail import send_mail
from .models import Notification, NotificationType


def send_email_notification(user: Any, subject: str, message: str, from_email: str = None) -> Notification:
    """
    Sends an email and records the notification event.
    """
    send_mail(
        subject=subject,
        message=message,
        from_email=from_email,
        recipient_list=[user.email],
        fail_silently=True,
    )
    return Notification.objects.create(
        user=user,
        notification_type=NotificationType.EMAIL,
        subject=subject,
        body=message,
    )

