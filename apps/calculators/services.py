"""
Calculator domain orchestration services.
Bridges calculation requests with storage without leaking math into views.
"""
from typing import Any, Dict, Optional
from apps.products.models import Product
from .models import CalculationRecord


def save_calculation_record(
    product: Product,
    inputs: Dict[str, Any],
    results: Dict[str, Any],
    user: Optional[Any] = None,
) -> CalculationRecord:
    """
    Persists a completed calculation record.
    """
    return CalculationRecord.objects.create(
        user=user if user and user.is_authenticated else None,
        product=product,
        inputs=inputs,
        results=results,
    )

