"""
Universal Clip Planning Service.

Independent of specific AI video generation providers (Runway, Kling, Veo, Sora, etc.).
Receives configurable clip-duration options and speech timing metrics to compute the
globally optimal combination of clip durations using Dynamic Programming.

Optimisation Priorities:
------------------------
1. FIRST:  Minimise the total number of generated clips.
2. SECOND: Among solutions with equal clip count, minimise total generated video duration.
3. THIRD:  If tied, minimise total reserved duration.
4. FOURTH: Deterministic tie-breaking: prefer longer clip options first when all previous
           values are equal, retaining the first equally optimal solution.
"""

from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from apps.calculators.services.narration import validate_wpm


# ---------------------------------------------------------------------------
# Domain Constants
# ---------------------------------------------------------------------------

DEFAULT_STANDARD_DURATIONS: List[int] = [5, 8, 10, 15, 20, 30]

MIN_CLIP_DURATION: int = 1
MAX_CLIP_DURATION: int = 600
MAX_UNIQUE_CLIP_OPTIONS: int = 50
MAX_PLAN_CLIPS: int = 1000
MAX_WORDS_LIMIT: int = 50000

_TWO_DP = Decimal("0.01")
_SIXTY = Decimal("60")


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClipOption:
    """
    Normalized clip duration option.
    """
    duration_seconds: int
    reserved_seconds: Decimal = Decimal("0.00")
    label: str = ""

    def __post_init__(self):
        if not self.label:
            lbl = f"{self.duration_seconds}s"
            if self.reserved_seconds > Decimal("0"):
                lbl += f" ({self.reserved_seconds}s reserved)"
            object.__setattr__(self, "label", lbl)

    @property
    def available_narration_duration(self) -> Decimal:
        """Usable narration time after subtracting reserved duration."""
        return Decimal(self.duration_seconds) - self.reserved_seconds

    def word_capacity(self, wpm: int) -> int:
        """
        Calculates maximum complete words that fit into this clip.
        floor(available_narration_duration * WPM / 60)
        """
        if self.available_narration_duration <= Decimal("0"):
            return 0
        w = Decimal(wpm)
        words_decimal = (self.available_narration_duration * w) / _SIXTY
        return int(words_decimal)  # Integer floor


# ---------------------------------------------------------------------------
# Validation & Normalisation Helpers
# ---------------------------------------------------------------------------

def normalize_clip_options(raw_options: Optional[List[Dict[str, Any]]]) -> List[ClipOption]:
    """
    Validates, normalises, and deduplicates clip duration options.
    Defaults to DEFAULT_STANDARD_DURATIONS if None or empty.

    Raises ValueError for invalid duration, negative reserved time, or options
    where reserved_seconds >= duration_seconds.
    """
    if raw_options is None or len(raw_options) == 0:
        return [
            ClipOption(duration_seconds=d, reserved_seconds=Decimal("0.00"))
            for d in DEFAULT_STANDARD_DURATIONS
        ]

    if not isinstance(raw_options, list):
        raise ValueError("clip_options must be a list of clip option objects.")

    parsed_options: List[ClipOption] = []
    seen: set = set()

    for idx, opt in enumerate(raw_options):
        if not isinstance(opt, dict):
            raise ValueError(f"Clip option at index {idx} must be a dictionary.")

        dur_raw = opt.get("duration_seconds")
        if dur_raw is None:
            raise ValueError(f"Clip option at index {idx} is missing 'duration_seconds'.")

        try:
            # Enforce positive whole integer
            dur_float = float(dur_raw)
            if not dur_float.is_integer() or dur_float <= 0:
                raise ValueError()
            dur = int(dur_float)
        except Exception:
            raise ValueError(
                f"Clip duration must be a positive whole number of seconds (1-{MAX_CLIP_DURATION}), got: {dur_raw!r}."
            )

        if dur < MIN_CLIP_DURATION:
            raise ValueError(
                f"Clip duration must be at least {MIN_CLIP_DURATION} second(s), got: {dur}."
            )
        if dur > MAX_CLIP_DURATION:
            raise ValueError(
                f"Clip duration cannot exceed {MAX_CLIP_DURATION} seconds, got: {dur}."
            )

        # Reserved seconds
        res_raw = opt.get("reserved_seconds", 0)
        try:
            res_dec = Decimal(str(res_raw)).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)
        except Exception:
            raise ValueError(
                f"Reserved duration must be a valid number of seconds, got: {res_raw!r}."
            )

        if res_dec < Decimal("0"):
            raise ValueError(
                f"Reserved duration cannot be negative, got: {res_dec}."
            )
        if res_dec >= Decimal(dur):
            raise ValueError(
                f"Reserved duration ({res_dec}s) must be strictly less than clip duration ({dur}s)."
            )

        label = str(opt.get("label", "")).strip()
        key = (dur, res_dec)
        if key not in seen:
            seen.add(key)
            parsed_options.append(
                ClipOption(
                    duration_seconds=dur,
                    reserved_seconds=res_dec,
                    label=label,
                )
            )

    if len(parsed_options) > MAX_UNIQUE_CLIP_OPTIONS:
        raise ValueError(
            f"Maximum unique clip options exceeded (limit: {MAX_UNIQUE_CLIP_OPTIONS}, got: {len(parsed_options)})."
        )

    # Sort deterministically: descending by duration_seconds, then ascending by reserved_seconds
    parsed_options.sort(key=lambda o: (-o.duration_seconds, o.reserved_seconds))
    return parsed_options


# ---------------------------------------------------------------------------
# Optimisation Algorithm (Dynamic Programming)
# ---------------------------------------------------------------------------

# Cost tuple: (clip_count, total_generated_duration, total_reserved_duration)
CostTuple = Tuple[int, int, Decimal]


def optimize_clip_sequence(
    word_count: int,
    wpm: int,
    clip_options: List[ClipOption],
) -> List[ClipOption]:
    """
    Finds the optimal combination of clip options to cover word_count narration words.

    Optimisation priorities:
    1. Minimise total clip count
    2. Minimise total generated duration
    3. Minimise total reserved duration
    4. Deterministic tie-breaking: prefer longer clips first

    Returns list of chosen ClipOption instances in recommended execution order.
    Raises ValueError if no valid plan can be constructed or if plan exceeds MAX_PLAN_CLIPS.
    """
    if word_count == 0:
        return []

    if word_count > MAX_WORDS_LIMIT:
        raise ValueError(f"Narration word count exceeds platform safety limit of {MAX_WORDS_LIMIT} words.")

    validated_wpm = validate_wpm(wpm)

    # Filter out options with zero complete-word capacity
    usable_options = [opt for opt in clip_options if opt.word_capacity(validated_wpm) > 0]
    if not usable_options:
        raise ValueError(
            "No available clip option can accommodate even one word at the specified speaking speed."
        )

    # Sort options: longer duration first for deterministic tie-breaking
    usable_options.sort(key=lambda o: (-o.duration_seconds, o.reserved_seconds))

    max_single_cap = max(opt.word_capacity(validated_wpm) for opt in usable_options)
    dp_limit = word_count + max_single_cap

    # dp[capacity] = (cost_tuple, parent_capacity, chosen_option)
    # Using None for unreachable states
    dp: List[Optional[Tuple[CostTuple, int, Optional[ClipOption]]]] = [None] * (dp_limit + 1)
    dp[0] = ((0, 0, Decimal("0.00")), -1, None)

    for c in range(word_count):
        state = dp[c]
        if state is None:
            continue
        curr_cost = state[0]
        curr_clips, curr_gen, curr_res = curr_cost

        if curr_clips >= MAX_PLAN_CLIPS:
            continue

        for opt in usable_options:
            cap = opt.word_capacity(validated_wpm)
            next_c = c + cap
            if next_c > dp_limit:
                continue

            new_cost: CostTuple = (
                curr_clips + 1,
                curr_gen + opt.duration_seconds,
                curr_res + opt.reserved_seconds,
            )

            existing = dp[next_c]
            if existing is None or new_cost < existing[0]:
                dp[next_c] = (new_cost, c, opt)

    # Find the optimal solution covering at least word_count words
    best_c: Optional[int] = None
    best_cost: Optional[CostTuple] = None

    for c in range(word_count, dp_limit + 1):
        state = dp[c]
        if state is not None:
            cost = state[0]
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_c = c

    if best_c is None or best_cost is None:
        raise ValueError("Could not find a feasible clip plan to accommodate the complete narration.")

    if best_cost[0] > MAX_PLAN_CLIPS:
        raise ValueError(
            f"The calculated plan requires {best_cost[0]} clips, which exceeds the maximum limit of {MAX_PLAN_CLIPS} clips."
        )

    # Reconstruct optimal sequence
    sequence: List[ClipOption] = []
    curr = best_c
    while curr > 0:
        entry = dp[curr]
        if entry is None or entry[2] is None:
            break
        sequence.append(entry[2])
        curr = entry[1]

    # Reverse to restore forward chronological order
    sequence.reverse()

    # Verify total capacity is sufficient
    total_capacity = sum(opt.word_capacity(validated_wpm) for opt in sequence)
    if total_capacity < word_count:
        raise ValueError("Algorithm integrity failure: total allocated clip capacity is less than narration word count.")

    return sequence


# ---------------------------------------------------------------------------
# Timing & Metrics Calculation
# ---------------------------------------------------------------------------

def calculate_plan_summary_metrics(
    word_count: int,
    wpm: int,
    clip_options: List[ClipOption],
    segments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Computes comprehensive plan summary metrics.
    """
    total_clips = len(clip_options)
    w_dec = Decimal(wpm)

    if total_clips == 0:
        return {
            "clip_count": 0,
            "clip_sequence": [],
            "total_generated_duration_seconds": "0.00",
            "total_reserved_duration_seconds": "0.00",
            "total_usable_narration_duration_seconds": "0.00",
            "total_speech_duration_seconds": "0.00",
            "total_unused_duration_seconds": "0.00",
            "overall_utilisation_percentage": "0.00",
            "average_words_per_clip": "0.00",
            "average_generated_duration_seconds": "0.00",
            "average_speech_duration_seconds": "0.00",
        }

    total_gen = Decimal(sum(opt.duration_seconds for opt in clip_options))
    total_res = sum(opt.reserved_seconds for opt in clip_options)
    total_usable = total_gen - total_res

    # Total actual speech duration based on words
    total_speech = ((Decimal(word_count) / w_dec) * _SIXTY).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)
    total_unused = (total_gen - total_speech).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)
    if total_unused < Decimal("0.00"):
        total_unused = Decimal("0.00")

    if total_usable > Decimal("0"):
        overall_util = ((total_speech / total_usable) * Decimal("100")).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)
    else:
        overall_util = Decimal("0.00")

    clips_dec = Decimal(total_clips)
    avg_words = (Decimal(word_count) / clips_dec).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)
    avg_gen = (total_gen / clips_dec).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)
    avg_speech = (total_speech / clips_dec).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)

    clip_seq = [opt.duration_seconds for opt in clip_options]

    return {
        "clip_count": total_clips,
        "clip_sequence": clip_seq,
        "total_generated_duration_seconds": str(total_gen.quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)),
        "total_reserved_duration_seconds": str(total_res.quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)),
        "total_usable_narration_duration_seconds": str(total_usable.quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)),
        "total_speech_duration_seconds": str(total_speech),
        "total_unused_duration_seconds": str(total_unused),
        "overall_utilisation_percentage": str(overall_util),
        "average_words_per_clip": str(avg_words),
        "average_generated_duration_seconds": str(avg_gen),
        "average_speech_duration_seconds": str(avg_speech),
    }

