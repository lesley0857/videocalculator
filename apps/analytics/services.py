"""
Analytics services.
Keep business logic out of views.
"""
from typing import Any, Dict, Optional
from .models import AnalyticsEvent


def track_event(event_name: str, user: Optional[Any] = None, properties: Optional[Dict[str, Any]] = None) -> AnalyticsEvent:
    """
    Records an analytics or business metric event.
    """
    return AnalyticsEvent.objects.create(
        user=user if user and user.is_authenticated else None,
        event_name=event_name,
        properties=properties or {},
    )

