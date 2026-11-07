import json
from decimal import Decimal
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.calculators.engines.clip_planning import UniversalClipPlanningEngine
from apps.calculators.services.clip_planning import (
    ClipOption,
    normalize_clip_options,
    optimize_clip_sequence,
    calculate_plan_summary_metrics,
    DEFAULT_STANDARD_DURATIONS,
    MIN_CLIP_DURATION,
    MAX_CLIP_DURATION,
    MAX_UNIQUE_CLIP_OPTIONS,
)


class ClipCapacityCalculationTests(SimpleTestCase):
    """
    Tests for clip capacity calculation (floor(available_narration_duration * WPM / 60)).
    """
    def test_standard_durations_capacity_at_150_wpm(self):
        # 150 WPM = 2.5 words/second
        # 5s -> floor(5 * 2.5) = 12
        # 8s -> floor(8 * 2.5) = 20
        # 10s -> floor(10 * 2.5) = 25
        # 15s -> floor(15 * 2.5) = 37
        # 20s -> floor(20 * 2.5) = 50
        # 30s -> floor(30 * 2.5) = 75
        expected = {
            5: 12,
            8: 20,
            10: 25,
            15: 37,
            20: 50,
            30: 75,
        }
        for dur, expected_cap in expected.items():
            opt = ClipOption(duration_seconds=dur)
            self.assertEqual(opt.word_capacity(150), expected_cap)

    def test_custom_durations_capacity(self):
        # 12s at 150 WPM -> floor(12 * 2.5) = 30 words
        opt = ClipOption(duration_seconds=12)
        self.assertEqual(opt.word_capacity(150), 30)

        # 6s at 120 WPM (2 words/s) -> floor(6 * 2) = 12 words
        opt2 = ClipOption(duration_seconds=6)
        self.assertEqual(opt2.word_capacity(120), 12)

    def test_reserved_duration_reduces_capacity(self):
        # 10s clip with 0.5s reserved = 9.5s available
        # At 150 WPM (2.5 w/s): 9.5 * 2.5 = 23.75 -> floor = 23 words
        opt = ClipOption(duration_seconds=10, reserved_seconds=Decimal("0.50"))
        self.assertEqual(opt.word_capacity(150), 23)

    def test_fractional_reserved_duration(self):
        # 5s clip with 1.25s reserved = 3.75s available
        # At 120 WPM (2 w/s): 3.75 * 2 = 7.5 -> floor = 7 words
        opt = ClipOption(duration_seconds=5, reserved_seconds=Decimal("1.25"))
        self.assertEqual(opt.word_capacity(120), 7)

    def test_zero_capacity_when_reserved_equals_or_exceeds_duration(self):
        # Usable <= 0 -> 0 capacity
        opt = ClipOption(duration_seconds=5, reserved_seconds=Decimal("5.00"))
        self.assertEqual(opt.word_capacity(150), 0)


class ClipOptionsNormalizationTests(SimpleTestCase):
    """
    Tests for normalizing, validating, and deduplicating clip options.
    """
    def test_default_options_when_none_or_empty(self):
        defaults = normalize_clip_options(None)
        self.assertEqual(len(defaults), 6)
        durations = [o.duration_seconds for o in defaults]
        self.assertEqual(sorted(durations), sorted(DEFAULT_STANDARD_DURATIONS))

    def test_deduplicates_identical_options(self):
        raw = [
            {"duration_seconds": 10, "reserved_seconds": 0},
            {"duration_seconds": 10, "reserved_seconds": 0},
            {"duration_seconds": 5, "reserved_seconds": 0},
        ]
        norm = normalize_clip_options(raw)
        self.assertEqual(len(norm), 2)
        self.assertEqual([o.duration_seconds for o in norm], [10, 5])

    def test_same_duration_different_reserved_retained(self):
        raw = [
            {"duration_seconds": 10, "reserved_seconds": 0},
            {"duration_seconds": 10, "reserved_seconds": 0.5},
        ]
        norm = normalize_clip_options(raw)
        self.assertEqual(len(norm), 2)

    def test_rejects_negative_or_zero_duration(self):
        with self.assertRaises(ValueError):
            normalize_clip_options([{"duration_seconds": 0}])
        with self.assertRaises(ValueError):
            normalize_clip_options([{"duration_seconds": -5}])

    def test_rejects_fractional_generated_duration(self):
        with self.assertRaises(ValueError):
            normalize_clip_options([{"duration_seconds": 7.5}])

    def test_rejects_duration_exceeding_max(self):
        with self.assertRaises(ValueError):
            normalize_clip_options([{"duration_seconds": MAX_CLIP_DURATION + 1}])

    def test_rejects_reserved_exceeding_or_equal_duration(self):
        with self.assertRaises(ValueError):
            normalize_clip_options([{"duration_seconds": 10, "reserved_seconds": 10}])
        with self.assertRaises(ValueError):
            normalize_clip_options([{"duration_seconds": 10, "reserved_seconds": 12}])

    def test_rejects_negative_reserved_duration(self):
        with self.assertRaises(ValueError):
            normalize_clip_options([{"duration_seconds": 10, "reserved_seconds": -0.5}])


class UniversalClipOptimizationTests(SimpleTestCase):
    """
    Tests for DP clip planning algorithm priorities and tie-breaking.
    """
    def setUp(self):
        self.standard_options = [
            ClipOption(duration_seconds=d) for d in DEFAULT_STANDARD_DURATIONS
        ]

    def test_empty_narration_returns_empty_sequence(self):
        plan = optimize_clip_sequence(word_count=0, wpm=150, clip_options=self.standard_options)
        self.assertEqual(plan, [])

    def test_prompt_example_238_words_at_150_wpm(self):
        # 238 words at 150 WPM
        # Min clips is 4: [30, 30, 30, 8] -> capacity: 75*3 + 20 = 245 >= 238, duration: 98s
        seq = optimize_clip_sequence(word_count=238, wpm=150, clip_options=self.standard_options)
        self.assertEqual(len(seq), 4)
        total_duration = sum(o.duration_seconds for o in seq)
        self.assertEqual(total_duration, 98)
        durations = [o.duration_seconds for o in seq]
        self.assertEqual(sorted(durations, reverse=True), [30, 30, 30, 8])

    def test_priority_1_minimises_total_clip_count(self):
        # Suppose target words = 30 at 150 WPM (2.5 w/s).
        # Opt 1: 15s (cap 37) -> 1 clip, 15s
        # Opt 2: 5s (cap 12) -> would take 3 clips, 15s
        # Opt 3: 10s (cap 25) -> would take 2 clips, 15s
        options = [
            ClipOption(duration_seconds=5),
            ClipOption(duration_seconds=10),
            ClipOption(duration_seconds=15),
        ]
        seq = optimize_clip_sequence(word_count=30, wpm=150, clip_options=options)
        self.assertEqual(len(seq), 1)
        self.assertEqual(seq[0].duration_seconds, 15)

    def test_priority_2_minimises_generated_duration_among_equal_clips(self):
        # Target = 20 words at 150 WPM (2.5 w/s).
        # Options:
        # Opt A: 8s (cap 20 words) -> 1 clip, 8s
        # Opt B: 10s (cap 25 words) -> 1 clip, 10s
        # Opt C: 30s (cap 75 words) -> 1 clip, 30s
        # All can do 1 clip. Opt A has min duration 8s.
        options = [
            ClipOption(duration_seconds=30),
            ClipOption(duration_seconds=10),
            ClipOption(duration_seconds=8),
        ]
        seq = optimize_clip_sequence(word_count=20, wpm=150, clip_options=options)
        self.assertEqual(len(seq), 1)
        self.assertEqual(seq[0].duration_seconds, 8)

    def test_priority_3_minimises_reserved_duration_when_clips_and_duration_tie(self):
        # Target = 10 words at 150 WPM.
        # Opt A: 5s clip, 1.0s reserved -> usable 4.0s (cap 10 words), duration 5s, reserved 1.0s
        # Opt B: 5s clip, 0.5s reserved -> usable 4.5s (cap 11 words), duration 5s, reserved 0.5s
        # Both achieve 1 clip, 5s duration. Opt B has lower reserved duration (0.5s < 1.0s).
        options = [
            ClipOption(duration_seconds=5, reserved_seconds=Decimal("1.00")),
            ClipOption(duration_seconds=5, reserved_seconds=Decimal("0.50")),
        ]
        seq = optimize_clip_sequence(word_count=10, wpm=150, clip_options=options)
        self.assertEqual(len(seq), 1)
        self.assertEqual(seq[0].reserved_seconds, Decimal("0.50"))

    def test_repeated_use_of_single_clip_duration(self):
        # Only 10s clips available (cap 25 words at 150 WPM).
        # Need 70 words -> requires 3 clips (cap 75 words).
        options = [ClipOption(duration_seconds=10)]
        seq = optimize_clip_sequence(word_count=70, wpm=150, clip_options=options)
        self.assertEqual(len(seq), 3)
        self.assertTrue(all(o.duration_seconds == 10 for o in seq))

    def test_unsorted_options_handled_cleanly(self):
        unsorted_opts = [
            ClipOption(duration_seconds=15),
            ClipOption(duration_seconds=5),
            ClipOption(duration_seconds=30),
            ClipOption(duration_seconds=8),
        ]
        seq = optimize_clip_sequence(word_count=35, wpm=150, clip_options=unsorted_opts)
        self.assertEqual(len(seq), 1)
        self.assertEqual(seq[0].duration_seconds, 15)


class ClipPlanningEngineIntegrationTests(SimpleTestCase):
    """
    Tests for UniversalClipPlanningEngine contract.
    """
    def test_engine_successful_calculation(self):
        engine = UniversalClipPlanningEngine()
        payload = {
            "narration": "This is a quick demonstration of the clip planner engine.",
            "wpm": 150,
            "clip_options": [
                {"duration_seconds": 5, "reserved_seconds": 0},
                {"duration_seconds": 10, "reserved_seconds": 0},
            ],
        }
        res = engine.calculate(payload)
        self.assertTrue(res["success"])
        self.assertIn("narration", res)
        self.assertIn("plan", res)
        self.assertIn("clips", res)
        self.assertIn("validation", res)
        self.assertTrue(res["validation"]["is_valid"])


class ClipPlannerWebEndpointTests(TestCase):
    """
    Web tests for interactive clip planner page and API endpoint.
    """
    def setUp(self):
        self.client = Client()
        self.page_url = reverse('calculators:talking-flyer-clip-planner-test')
        self.api_url = reverse('calculators:clip-planner-calculate-api')

    def test_clip_planner_page_renders_200(self):
        response = self.client.get(self.page_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Universal Clip Planning")
        self.assertContains(response, "clip_planner.js")
        self.assertContains(response, "clip_planner.css")

    def test_api_valid_post_returns_structured_plan(self):
        payload = {
            "narration": "Hello world, this is clip planning.",
            "wpm": 150,
            "clip_options": [
                {"duration_seconds": 5, "reserved_seconds": 0},
                {"duration_seconds": 10, "reserved_seconds": 0},
            ],
            "segmentation": {
                "sentence_boundary_preference": True,
                "sentence_boundary_tolerance": 0.20,
            }
        }
        response = self.client.post(
            self.api_url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["narration"]["word_count"], 6)
        self.assertEqual(data["plan"]["clip_count"], 1)
        self.assertEqual(len(data["clips"]), 1)
        self.assertTrue(data["validation"]["is_valid"])

    def test_api_empty_narration_returns_valid_zero_plan(self):
        payload = {
            "narration": "",
            "wpm": 135,
        }
        response = self.client.post(
            self.api_url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["plan"]["clip_count"], 0)
        self.assertEqual(data["clips"], [])

    def test_api_invalid_wpm_returns_400(self):
        payload = {
            "narration": "Some script",
            "wpm": 40,  # Below 60
        }
        response = self.client.post(
            self.api_url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("at least 60 WPM", data["error"])

    def test_api_invalid_clip_duration_returns_400(self):
        payload = {
            "narration": "Some script",
            "wpm": 150,
            "clip_options": [{"duration_seconds": -5}],
        }
        response = self.client.post(
            self.api_url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])

    def test_existing_narration_page_and_index_still_functional(self):
        resp_narr = self.client.get(reverse('calculators:talking-flyer-narration-test'))
        self.assertEqual(resp_narr.status_code, 200)

        resp_idx = self.client.get(reverse('calculators:index'))
        self.assertEqual(resp_idx.status_code, 200)

