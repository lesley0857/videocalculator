"""
Abstract calculation engine interface.
Enforces strict separation between calculation algorithms and Django views/UI.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseCalculationEngine(ABC):
    """
    Abstract base class for all calculator calculation logic.
    """

    @abstractmethod
    def calculate(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute core computation given validated input parameters.
        Returns calculated output metrics.
        """
        pass

