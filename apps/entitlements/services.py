"""
Entitlement business logic services.
Keep business logic out of views.
"""
from typing import Any
from django.utils import timezone
from apps.products.models import Product
from .models import Entitlement


def grant_entitlement(user: Any, product: Product, expires_at=None) -> Entitlement:
    """
    Grants or updates user entitlement to a specific product.
    """
    entitlement, _ = Entitlement.objects.update_or_create(
        user=user,
        product=product,
        defaults={'is_active': True, 'expires_at': expires_at},
    )
    return entitlement


def user_has_product_access(user: Any, product_slug: str) -> bool:
    """
    Validates whether the user holds an active entitlement for a product slug.
    """
    if not user.is_authenticated:
        return False
    try:
        entitlement = Entitlement.objects.get(
            user=user,
            product__slug=product_slug,
            is_active=True,
        )
        return entitlement.is_valid()
    except Entitlement.DoesNotExist:
        return False

