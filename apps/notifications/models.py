"""
Notification log models.
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class NotificationType(models.TextChoices):
    EMAIL = 'EMAIL', _('Email')
    IN_APP = 'IN_APP', _('In App')


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    notification_type = models.CharField(
        _('type'),
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.EMAIL,
    )
    subject = models.CharField(_('subject'), max_length=255)
    body = models.TextField(_('body'))
    is_read = models.BooleanField(_('is read'), default=False)
    sent_at = models.DateTimeField(_('sent at'), auto_now_add=True)

    class Meta:
        verbose_name = _('notification')
        verbose_name_plural = _('notifications')
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.subject} -> {self.user.email}"

