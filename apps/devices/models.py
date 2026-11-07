"""
Device tracking models for session and device security.
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Device(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='devices',
    )
    device_fingerprint = models.CharField(_('device fingerprint'), max_length=255, db_index=True)
    user_agent = models.CharField(_('user agent'), max_length=512, blank=True)
    ip_address = models.GenericIPAddressField(_('IP address'), null=True, blank=True)
    last_active = models.DateTimeField(_('last active'), auto_now=True)
    is_trusted = models.BooleanField(_('is trusted'), default=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)

    class Meta:
        verbose_name = _('device')
        verbose_name_plural = _('devices')
        unique_together = ('user', 'device_fingerprint')
        ordering = ['-last_active']

    def __str__(self):
        return f"Device {self.device_fingerprint[:8]} ({self.user.email})"

