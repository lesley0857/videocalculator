"""
Payment business logic services.
Isolated completely from external provider SDKs and HTTP views.
"""
from decimal import Decimal
from typing import Optional
from apps.orders.models import Order
from apps.orders.services import mark_order_as_paid
from .models import Payment, PaymentStatus


def initiate_payment(order: Order, provider: str, amount: Decimal, currency: str = 'USD') -> Payment:
    """
    Records an initial payment attempt for an order in the domain.
    """
    return Payment.objects.create(
        order=order,
        provider=provider,
        amount=amount,
        currency=currency,
        status=PaymentStatus.INITIATED,
    )


def record_payment_success(payment: Payment, reference_id: str, metadata: Optional[dict] = None) -> Payment:
    """
    Business logic executing upon confirmed payment success:
    marks payment as SUCCESSFUL, updates order status to PAID.
    """
    payment.status = PaymentStatus.SUCCESSFUL
    payment.reference_id = reference_id
    if metadata:
        payment.metadata = metadata
    payment.save(update_fields=['status', 'reference_id', 'metadata', 'updated_at'])

    # Cascade to order domain
    mark_order_as_paid(payment.order)
    return payment


def record_payment_failure(payment: Payment, failure_reason: Optional[dict] = None) -> Payment:
    """
    Business logic executing upon confirmed payment failure.
    """
    payment.status = PaymentStatus.FAILED
    if failure_reason:
        payment.metadata.update({'failure': failure_reason})
    payment.save(update_fields=['status', 'metadata', 'updated_at'])
    return payment

