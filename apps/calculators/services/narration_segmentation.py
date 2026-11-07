"""
Narration Segmentation Service.

Segments normalised narration into sequential clips according to their complete-word
capacities, respecting sentence boundaries when feasible and verifying 100% narration
integrity.
"""

import math
import re
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Dict, List, Tuple

from apps.calculators.services.clip_planning import ClipOption

_TWO_DP = Decimal("0.01")
_SIXTY = Decimal("60")

# Sentence boundary regex recognizing terminal punctuation with optional trailing quotes
SENTENCE_END_RE = re.compile(r'(\.|\?|!|\.\.\.)["\')\]]?$')


def is_sentence_end_word(token: str) -> bool:
    """
    Checks if a token ends with sentence-terminating punctuation.
    """
    if not token:
        return False
    return bool(SENTENCE_END_RE.search(token))


def segment_narration(
    normalized_text: str,
    wpm: int,
    clip_sequence: List[ClipOption],
    sentence_boundary_preference: bool = True,
    sentence_boundary_tolerance: float = 0.20,
) -> Tuple[List[Dict[str, Any]], Dict[str, bool]]:
    """
    Segments normalised narration across a sequence of planned clips.

    Parameters
    ----------
    normalized_text : str
        Pre-normalised narration text (single whitespace separators).
    wpm : int
        Speaking speed in words per minute.
    clip_sequence : List[ClipOption]
        Ordered sequence of selected clips.
    sentence_boundary_preference : bool
        Whether to prefer breaking at sentence boundaries.
    sentence_boundary_tolerance : float
        Fraction of clip capacity at the end of the clip to scan for sentence boundaries (0.0 to 1.0).

    Returns
    -------
    Tuple[List[Dict[str, Any]], Dict[str, bool]]
        A list of segment dictionaries with metrics, and a validation integrity summary dict.

    Raises
    ------
    ValueError
        If inputs are invalid or segmentation integrity validation fails.
    """
    if not normalized_text.strip() or len(clip_sequence) == 0:
        return [], {
            "is_valid": True,
            "all_words_allocated": True,
            "word_count_matches": True,
            "capacity_respected": True,
            "reconstructed_text_matches": True,
        }

    words = normalized_text.split()
    total_words = len(words)
    total_clips = len(clip_sequence)
    w_dec = Decimal(wpm)

    # Pre-calculate complete-word capacities for all clips
    clip_capacities = [clip.word_capacity(wpm) for clip in clip_sequence]
    total_capacity = sum(clip_capacities)

    if total_capacity < total_words:
        raise ValueError(
            f"Insufficient clip capacity: clips can hold {total_capacity} words, but narration has {total_words} words."
        )

    # Suffix capacities: remaining_capacities[i] is sum of capacities from clip i+1 to end
    remaining_capacities = [0] * total_clips
    running = 0
    for idx in range(total_clips - 1, -1, -1):
        remaining_capacities[idx] = running
        running += clip_capacities[idx]

    segments: List[Dict[str, Any]] = []
    current_word_idx = 0  # 0-based index in words list

    for i, clip in enumerate(clip_sequence):
        words_remaining = total_words - current_word_idx
        if words_remaining <= 0:
            break

        cap = clip_capacities[i]
        rem_cap = remaining_capacities[i]

        # Maximum words this clip can accept
        max_take = min(cap, words_remaining)

        # Minimum words this clip MUST take so that remaining words fit in future clips
        min_take = max(1, words_remaining - rem_cap)

        if min_take > max_take:
            raise ValueError(
                f"Segmentation infeasible at clip {i + 1}: requires minimum {min_take} words, but clip capacity is {cap}."
            )

        chosen_take = max_take

        if i == total_clips - 1:
            # Last clip must absorb all remaining words
            chosen_take = words_remaining
        elif sentence_boundary_preference and max_take > min_take:
            # Determine window size for sentence boundary scan
            tol = max(0.0, min(1.0, float(sentence_boundary_tolerance)))
            window_size = max(1, math.ceil(cap * tol))
            window_start = max(min_take, max_take - window_size)

            # Search backwards from max_take to window_start for a sentence boundary
            boundary_found = False
            for take_candidate in range(max_take, window_start - 1, -1):
                word_at_end = words[current_word_idx + take_candidate - 1]
                if is_sentence_end_word(word_at_end):
                    chosen_take = take_candidate
                    boundary_found = True
                    break

            if not boundary_found:
                chosen_take = max_take

        # Extract words for this segment
        segment_words = words[current_word_idx : current_word_idx + chosen_take]
        segment_text = " ".join(segment_words)
        assigned_words = len(segment_words)

        # Calculate timing metrics
        start_pos = current_word_idx + 1
        end_pos = current_word_idx + assigned_words
        current_word_idx += assigned_words

        gen_dur = Decimal(clip.duration_seconds).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)
        res_dur = clip.reserved_seconds.quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)
        usable_dur = (Decimal(clip.duration_seconds) - clip.reserved_seconds).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)

        speech_dur = ((Decimal(assigned_words) / w_dec) * _SIXTY).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)
        unused_narr = (usable_dur - speech_dur).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)
        if unused_narr < Decimal("0.00"):
            unused_narr = Decimal("0.00")

        unused_gen = (gen_dur - speech_dur).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)
        if unused_gen < Decimal("0.00"):
            unused_gen = Decimal("0.00")

        if usable_dur > Decimal("0.00"):
            util_pct = ((speech_dur / usable_dur) * Decimal("100")).quantize(_TWO_DP, rounding=ROUND_HALF_EVEN)
        else:
            util_pct = Decimal("0.00")

        segments.append({
            "sequence_number": i + 1,
            "start_word_index": start_pos,
            "end_word_index": end_pos,
            "word_count": assigned_words,
            "narration_text": segment_text,
            "speech_duration_seconds": str(speech_dur),
            "generated_duration_seconds": str(gen_dur),
            "reserved_duration_seconds": str(res_dur),
            "usable_narration_duration_seconds": str(usable_dur),
            "unused_narration_duration_seconds": str(unused_narr),
            "unused_generated_duration_seconds": str(unused_gen),
            "utilisation_percentage": str(util_pct),
        })

    # -----------------------------------------------------------------------
    # Final Integrity Verification
    # -----------------------------------------------------------------------
    reconstructed_text = " ".join(seg["narration_text"] for seg in segments)
    reconstructed_words = sum(seg["word_count"] for seg in segments)
    all_words_allocated = (current_word_idx == total_words)
    word_count_matches = (reconstructed_words == total_words)
    reconstructed_text_matches = (reconstructed_text == normalized_text)
    capacity_respected = all(
        seg["word_count"] <= clip_capacities[idx]
        for idx, seg in enumerate(segments)
    )

    is_valid = (
        all_words_allocated
        and word_count_matches
        and reconstructed_text_matches
        and capacity_respected
    )

    if not is_valid:
        raise ValueError(
            f"Segmentation integrity verification failed: "
            f"all_words_allocated={all_words_allocated}, "
            f"word_count_matches={word_count_matches}, "
            f"capacity_respected={capacity_respected}, "
            f"reconstructed_text_matches={reconstructed_text_matches}."
        )

    validation_summary = {
        "is_valid": is_valid,
        "all_words_allocated": all_words_allocated,
        "word_count_matches": word_count_matches,
        "capacity_respected": capacity_respected,
        "reconstructed_text_matches": reconstructed_text_matches,
    }

    return segments, validation_summary

