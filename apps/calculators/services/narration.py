"""
Narration service — speech timing for the Talking Flyer Calculator.

Word-count convention
---------------------
Words are whitespace-separated tokens after full whitespace normalisation.
Punctuation that is attached to a token does not create an additional word.

    "Hello world"      → 2 words
    "Hello    world"   → 2 words   (multiple spaces)
    "Hello\\nworld"    → 2 words   (line break)
    "Hello, world!"    → 2 words   (attached punctuation)
    "Well-known tech"  → 2 words   (hyphen within token)

Speech-duration formula
-----------------------
    duration_seconds = (word_count / wpm) × 60

Rounding convention
-------------------
All intermediate arithmetic uses Python Decimal at sufficient precision.
Values returned in the result dict are:
    duration_seconds  — Decimal, rounded to 2 decimal places (half-even)
    duration_minutes  — Decimal, rounded to 2 decimal places (half-even)
    minutes_part      — int  (floor of total minutes)
    seconds_part      — int  (floor of remaining seconds, never >= 60)

Display strings are built from the rounded values above.

WPM limits
----------
    MIN_WPM = 60
    MAX_WPM = 240

These are enforced on every calculation. Custom values outside this range
are rejected with a ValueError.
"""

import re
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_WPM: int = 60
MAX_WPM: int = 240

# Speaking-speed presets  (label → wpm)
SPEED_PRESETS: Dict[str, int] = {
    "relaxed":        120,
    "conversational": 135,
    "brisk":          150,
    "fast":           165,
    "very_fast":      180,
}

# Display metadata for each preset (used by the view / template)
SPEED_PRESET_META: list = [
    {"key": "relaxed",        "label": "Relaxed",        "wpm": 120, "description": "Slow, deliberate narration"},
    {"key": "conversational", "label": "Conversational",  "wpm": 135, "description": "Natural conversational delivery"},
    {"key": "brisk",          "label": "Brisk",           "wpm": 150, "description": "Moderately fast delivery"},
    {"key": "fast",           "label": "Fast",            "wpm": 165, "description": "Fast narration"},
    {"key": "very_fast",      "label": "Very fast",       "wpm": 180, "description": "Very fast narration"},
]

_TWO_DP = Decimal("0.01")
_SIXTY = Decimal("60")


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """
    Collapse all whitespace (spaces, tabs, line breaks) to single spaces
    and strip leading/trailing whitespace.

    Returns an empty string for blank or None input.
    """
    if not text:
        return ""
    # Replace any whitespace sequence (including tabs and newlines) with a
    # single space, then strip the ends.
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Word counting
# ---------------------------------------------------------------------------

def count_words(text: str) -> int:
    """
    Count whitespace-separated tokens in *already-normalised* text.

    Accepts raw text as well — normalisation is applied internally so the
    function is safe to call with un-normalised input.

    Returns 0 for blank input.
    """
    normalised = normalize_text(text)
    if not normalised:
        return 0
    return len(normalised.split())


# ---------------------------------------------------------------------------
# WPM validation
# ---------------------------------------------------------------------------

def validate_wpm(wpm: Any) -> int:
    """
    Validate and coerce a WPM value.

    Accepts int, float, Decimal, or numeric string.
    Raises ValueError for blank, non-numeric, zero, negative, or
    out-of-range values.

    Returns the validated WPM as a plain int.
    """
    if wpm is None or (isinstance(wpm, str) and not wpm.strip()):
        raise ValueError("Speaking speed (WPM) is required.")

    try:
        value = int(Decimal(str(wpm)))
    except Exception:
        raise ValueError(f"Speaking speed must be a whole number, got: {wpm!r}")

    if value <= 0:
        raise ValueError(f"Speaking speed must be greater than zero, got: {value}")
    if value < MIN_WPM:
        raise ValueError(
            f"Speaking speed must be at least {MIN_WPM} WPM, got: {value}"
        )
    if value > MAX_WPM:
        raise ValueError(
            f"Speaking speed must be at most {MAX_WPM} WPM, got: {value}"
        )
    return value


# ---------------------------------------------------------------------------
# Duration calculation
# ---------------------------------------------------------------------------

def calculate_duration(word_count: int, wpm: int) -> Dict[str, Any]:
    """
    Compute speech duration from word count and WPM.

    Parameters
    ----------
    word_count : int  ≥ 0
    wpm        : int  MIN_WPM ≤ wpm ≤ MAX_WPM  (pre-validated)

    Returns a dict with keys:
        duration_seconds  Decimal (2 dp)
        duration_minutes  Decimal (2 dp)
        minutes_part      int
        seconds_part      int
        duration_display  str   "MM:SS"
        duration_readable str   e.g. "1 minute 35 seconds"
    """
    if word_count == 0:
        return _zero_duration()

    wc = Decimal(word_count)
    w = Decimal(wpm)
    # Exact rational value, full precision
    exact_seconds: Decimal = (wc / w) * _SIXTY

    duration_seconds = exact_seconds.quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)
    duration_minutes = (exact_seconds / _SIXTY).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)

    total_seconds_int = int(exact_seconds)   # floor
    minutes_part = total_seconds_int // 60
    seconds_part = total_seconds_int % 60

    duration_display = f"{minutes_part:02d}:{seconds_part:02d}"
    duration_readable = _format_readable(minutes_part, seconds_part)

    return {
        "duration_seconds": duration_seconds,
        "duration_minutes": duration_minutes,
        "minutes_part":     minutes_part,
        "seconds_part":     seconds_part,
        "duration_display": duration_display,
        "duration_readable": duration_readable,
    }


def _zero_duration() -> Dict[str, Any]:
    return {
        "duration_seconds":  Decimal("0.00"),
        "duration_minutes":  Decimal("0.00"),
        "minutes_part":      0,
        "seconds_part":      0,
        "duration_display":  "00:00",
        "duration_readable": "0 seconds",
    }


def _format_readable(minutes: int, seconds: int) -> str:
    """Return a human-readable duration string, e.g. '1 minute 35 seconds'."""
    if minutes == 0:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    if seconds == 0:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return (
        f"{minutes} minute{'s' if minutes != 1 else ''} "
        f"{seconds} second{'s' if seconds != 1 else ''}"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def calculate_narration(
    text: str,
    wpm: Any,
) -> Dict[str, Any]:
    """
    Full narration calculation pipeline.

    Accepts raw (un-normalised) text and any WPM representation.
    Validates WPM and returns a structured result.

    Parameters
    ----------
    text : str   Raw narration text (may be blank).
    wpm  : Any   WPM as int, float, Decimal, or numeric string.

    Returns
    -------
    dict with keys:
        word_count        int
        wpm               int
        normalized_text   str
        duration_seconds  Decimal
        duration_minutes  Decimal
        minutes_part      int
        seconds_part      int
        duration_display  str
        duration_readable str

    Raises
    ------
    ValueError  if wpm is invalid.
    """
    validated_wpm = validate_wpm(wpm)
    normalised = normalize_text(text)
    word_count = count_words(normalised)
    timing = calculate_duration(word_count, validated_wpm)

    return {
        "word_count":       word_count,
        "wpm":              validated_wpm,
        "normalized_text":  normalised,
        **timing,
    }

