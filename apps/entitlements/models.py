"""
Entitlements models.
Tracks user access rights and plan quotas for platform calculators.
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.products.models import Product


class Entitlement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='entitlements',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='entitlements',
    )
    is_active = models.BooleanField(_('is active'), default=True)
    expires_at = models.DateTimeField(_('expires at'), null=True, blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('entitlement')
        verbose_name_plural = _('entitlements')
        unique_together = ('user', 'product')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} -> {self.product.name} (Active: {self.is_active})"

    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True

