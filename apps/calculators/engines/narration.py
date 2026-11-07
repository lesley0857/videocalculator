"""
Narration engine for the Talking Flyer Calculator.

Implements BaseCalculationEngine. Delegates all arithmetic to the
narration service so the engine remains independently testable.

Input schema
------------
{
    "text": str,          # raw narration text (required)
    "wpm":  int | str,    # words per minute   (required)
}

Output schema
-------------
{
    "word_count":        int,
    "wpm":               int,
    "normalized_text":   str,
    "duration_seconds":  Decimal,
    "duration_minutes":  Decimal,
    "minutes_part":      int,
    "seconds_part":      int,
    "duration_display":  str,   # "MM:SS"
    "duration_readable": str,   # "1 minute 35 seconds"
}

Raises
------
ValueError  for invalid WPM (propagated from narration service).
"""

from typing import Any, Dict

from apps.calculators.engines.base import BaseCalculationEngine
from apps.calculators.services.narration import calculate_narration


class NarrationEngine(BaseCalculationEngine):
    """
    Calculation engine for narration speech-timing.

    Fully stateless; safe to instantiate once and reuse.
    """

    def calculate(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the narration calculation.

        Parameters
        ----------
        inputs : dict
            Must contain 'text' (str) and 'wpm' (int or numeric string).

        Returns
        -------
        dict  — structured narration result (see module docstring).

        Raises
        ------
        ValueError  if 'wpm' is missing, non-numeric, or out of range.
        KeyError    if required keys are absent from inputs.
        """
        text = inputs.get("text", "")
        wpm = inputs.get("wpm")
        if wpm is None:
            raise KeyError("'wpm' is required in inputs.")
        return calculate_narration(text=text, wpm=wpm)

