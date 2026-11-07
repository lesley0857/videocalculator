"""
Payment transaction models.
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.orders.models import Order


class PaymentStatus(models.TextChoices):
    INITIATED = 'INITIATED', _('Initiated')
    SUCCESSFUL = 'SUCCESSFUL', _('Successful')
    FAILED = 'FAILED', _('Failed')
    REFUNDED = 'REFUNDED', _('Refunded')


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    provider = models.CharField(_('payment provider'), max_length=50)  # e.g., 'stripe', 'paypal'
    reference_id = models.CharField(_('provider reference id'), max_length=255, blank=True)
    amount = models.DecimalField(_('amount'), max_digits=10, decimal_places=2)
    currency = models.CharField(_('currency'), max_length=3, default='USD')
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.INITIATED,
        db_index=True,
    )
    metadata = models.JSONField(_('provider metadata'), default=dict, blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('payment')
        verbose_name_plural = _('payments')
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment {self.id} for Order {self.order_id} ({self.status})"

