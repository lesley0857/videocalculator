"""
Universal Clip Planning Calculation Engine.

Implements BaseCalculationEngine. Orchestrates narration verification (Task 003),
clip capacity computation, dynamic programming optimisation, narration segmentation,
and integrity validation.
"""

from typing import Any, Dict

from apps.calculators.engines.base import BaseCalculationEngine
from apps.calculators.services.narration import calculate_narration
from apps.calculators.services.clip_planning import (
    normalize_clip_options,
    optimize_clip_sequence,
    calculate_plan_summary_metrics,
)
from apps.calculators.services.narration_segmentation import segment_narration


class UniversalClipPlanningEngine(BaseCalculationEngine):
    """
    Stateless calculation engine for universal video clip planning
    and narration segmentation.
    """

    def calculate(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute clip planning and narration segmentation.

        Parameters
        ----------
        inputs : dict
            - narration / text : str
            - wpm : int | str
            - clip_options : optional list of dicts [{"duration_seconds": int, "reserved_seconds": float/dec}]
            - segmentation : optional dict {"sentence_boundary_preference": bool, "sentence_boundary_tolerance": float}

        Returns
        -------
        dict matching the Task 004 Structured API Result contract.
        """
        text = inputs.get("narration", inputs.get("text", ""))
        wpm = inputs.get("wpm")
        raw_options = inputs.get("clip_options")
        seg_config = inputs.get("segmentation") or {}

        # 1. Authoritative Task 003 narration calculation
        narration_res = calculate_narration(text=text, wpm=wpm)
        word_count = narration_res["word_count"]
        validated_wpm = narration_res["wpm"]
        normalized_text = narration_res["normalized_text"]
        speech_duration_str = str(narration_res["duration_seconds"])

        # 2. Parse and validate clip options
        clip_options = normalize_clip_options(raw_options)

        # 3. Handle empty narration edge-case explicitly
        if word_count == 0:
            plan_summary = calculate_plan_summary_metrics(
                word_count=0,
                wpm=validated_wpm,
                clip_options=[],
            )
            return {
                "success": True,
                "narration": {
                    "word_count": 0,
                    "wpm": validated_wpm,
                    "duration_seconds": "0.00",
                    "duration_display": "00:00",
                    "duration_readable": "0 seconds",
                    "normalized_text": "",
                },
                "plan": plan_summary,
                "clips": [],
                "validation": {
                    "is_valid": True,
                    "all_words_allocated": True,
                    "word_count_matches": True,
                    "capacity_respected": True,
                    "reconstructed_text_matches": True,
                },
            }

        # 4. Run DP clip sequence optimisation
        clip_sequence = optimize_clip_sequence(
            word_count=word_count,
            wpm=validated_wpm,
            clip_options=clip_options,
        )

        # 5. Segment narration across the selected clip sequence
        pref_sentence = bool(seg_config.get("sentence_boundary_preference", True))
        tol_sentence = float(seg_config.get("sentence_boundary_tolerance", 0.20))

        segments, validation_summary = segment_narration(
            normalized_text=normalized_text,
            wpm=validated_wpm,
            clip_sequence=clip_sequence,
            sentence_boundary_preference=pref_sentence,
            sentence_boundary_tolerance=tol_sentence,
        )

        # 6. Calculate summary metrics
        plan_summary = calculate_plan_summary_metrics(
            word_count=word_count,
            wpm=validated_wpm,
            clip_options=clip_sequence,
            segments=segments,
        )

        return {
            "success": True,
            "narration": {
                "word_count": word_count,
                "wpm": validated_wpm,
                "duration_seconds": speech_duration_str,
                "duration_display": narration_res["duration_display"],
                "duration_readable": narration_res["duration_readable"],
                "normalized_text": normalized_text,
            },
            "plan": plan_summary,
            "clips": segments,
            "validation": validation_summary,
        }

