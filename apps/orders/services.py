"""
Order domain services.
Keep business logic out of views.
"""
from decimal import Decimal
from typing import Any
from .models import Order, OrderStatus


def create_order(user: Any, total_amount: Decimal, currency: str = 'USD') -> Order:
    """
    Creates a new order in pending status.
    """
    return Order.objects.create(
        user=user,
        total_amount=total_amount,
        currency=currency,
        status=OrderStatus.PENDING,
    )


def mark_order_as_paid(order: Order) -> Order:
    """
    Updates order status to PAID.
    """
    order.status = OrderStatus.PAID
    order.save(update_fields=['status', 'updated_at'])
    return order

