"""
Product domain services.
Keep business logic out of views.
"""
from typing import List
from .models import Product


def get_active_products() -> List[Product]:
    """
    Retrieves all currently active products available on the platform.
    """
    return list(Product.objects.filter(is_active=True))


def get_product_by_slug(slug: str) -> Product:
    """
    Retrieves a single active product by slug.
    """
    return Product.objects.get(slug=slug, is_active=True)

