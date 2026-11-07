"""
Calculation history and session models.
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.products.models import Product


class CalculationRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='calculations',
        null=True,
        blank=True,
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='calculations',
    )
    inputs = models.JSONField(_('inputs payload'), default=dict)
    results = models.JSONField(_('results payload'), default=dict)
    created_at = models.DateTimeField(_('calculated at'), auto_now_add=True)

    class Meta:
        verbose_name = _('calculation record')
        verbose_name_plural = _('calculation records')
        ordering = ['-created_at']

    def __str__(self):
        return f"Calculation {self.id} ({self.product.name})"

