"""
Analytics event models.
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AnalyticsEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analytics_events',
    )
    event_name = models.CharField(_('event name'), max_length=100, db_index=True)
    properties = models.JSONField(_('event properties'), default=dict, blank=True)
    created_at = models.DateTimeField(_('timestamp'), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('analytics event')
        verbose_name_plural = _('analytics events')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.event_name} at {self.created_at}"

