"""
Abstract interface for payment gateway providers.
All external provider integrations must implement this interface.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict


class BasePaymentGateway(ABC):
    """
    Abstract gateway interface isolating external provider SDKs
    from the internal payment domain services.
    """

    @abstractmethod
    def create_checkout_session(self, order_id: str, amount: str, currency: str) -> Dict[str, Any]:
        """
        Initiate a checkout session with the external provider.
        """
        pass

    @abstractmethod
    def handle_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """
        Validate and parse an incoming webhook event.
        """
        pass

