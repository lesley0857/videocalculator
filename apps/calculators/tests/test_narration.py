import json
from decimal import Decimal
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.calculators.engines.narration import NarrationEngine
from apps.calculators.services.narration import (
    MAX_WPM,
    MIN_WPM,
    SPEED_PRESETS,
    calculate_duration,
    calculate_narration,
    count_words,
    normalize_text,
    validate_wpm,
)


class NarrationTextProcessingTests(SimpleTestCase):
    """
    Unit tests for text normalisation and word counting rules.
    """
    def test_empty_and_whitespace_only(self):
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text("   "), "")
        self.assertEqual(normalize_text("\t\n\r  "), "")
        self.assertEqual(count_words(""), 0)
        self.assertEqual(count_words("   "), 0)
        self.assertEqual(count_words("\n\t  "), 0)

    def test_single_word(self):
        self.assertEqual(normalize_text("Hello"), "Hello")
        self.assertEqual(count_words("Hello"), 1)
        self.assertEqual(count_words("   Hello   "), 1)

    def test_multiple_words(self):
        self.assertEqual(count_words("Hello world"), 2)

    def test_multiple_spaces(self):
        self.assertEqual(normalize_text("Hello    world"), "Hello world")
        self.assertEqual(count_words("Hello    world"), 2)

    def test_tabs_and_newlines(self):
        text = "Hello\t\tworld\nthis\nis\ra\ttest"
        self.assertEqual(normalize_text(text), "Hello world this is a test")
        self.assertEqual(count_words(text), 6)

    def test_leading_and_trailing_whitespace(self):
        text = "   \n\t  Start of sentence and end.  \t\n "
        self.assertEqual(normalize_text(text), "Start of sentence and end.")
        self.assertEqual(count_words(text), 5)

    def test_attached_punctuation(self):
        # Punctuation attached to words must not create extra words
        text = "Hello, world! Are you ready? (Yes, I am.)"
        self.assertEqual(count_words(text), 8)

    def test_hyphenated_words(self):
        # Deterministic token rule: whitespace-separated tokens
        text = "Well-known technology state-of-the-art"
        self.assertEqual(count_words(text), 3)


class SpeakingSpeedValidationTests(SimpleTestCase):
    """
    Unit tests for speaking speed (WPM) validation and presets.
    """
    def test_all_five_presets_are_valid(self):
        expected_presets = {
            'relaxed': 120,
            'conversational': 135,
            'brisk': 150,
            'fast': 165,
            'very_fast': 180,
        }
        for key, speed in expected_presets.items():
            self.assertEqual(SPEED_PRESETS[key], speed)
            self.assertEqual(validate_wpm(speed), speed)

    def test_valid_custom_wpm(self):
        self.assertEqual(validate_wpm(140), 140)
        self.assertEqual(validate_wpm("140"), 140)
        self.assertEqual(validate_wpm(Decimal("140")), 140)

    def test_boundary_wpm(self):
        self.assertEqual(validate_wpm(MIN_WPM), 60)
        self.assertEqual(validate_wpm(MAX_WPM), 240)

    def test_zero_wpm_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            validate_wpm(0)
        self.assertIn("greater than zero", str(ctx.exception))

    def test_negative_wpm_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            validate_wpm(-10)
        self.assertIn("greater than zero", str(ctx.exception))

    def test_below_min_wpm_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            validate_wpm(59)
        self.assertIn("at least 60 WPM", str(ctx.exception))

    def test_above_max_wpm_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            validate_wpm(241)
        self.assertIn("at most 240 WPM", str(ctx.exception))

    def test_non_numeric_wpm_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            validate_wpm("fast")
        self.assertIn("whole number", str(ctx.exception))

    def test_blank_or_none_wpm_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            validate_wpm(None)
        self.assertIn("required", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_wpm("   ")
        self.assertIn("required", str(ctx.exception))


class SpeechDurationCalculationTests(SimpleTestCase):
    """
    Unit tests for speech duration arithmetic and formatting.
    Formula: duration_seconds = (word_count / wpm) * 60
    """
    def test_120_words_at_120_wpm(self):
        res = calculate_duration(word_count=120, wpm=120)
        self.assertEqual(res['duration_seconds'], Decimal("60.00"))
        self.assertEqual(res['duration_minutes'], Decimal("1.00"))
        self.assertEqual(res['duration_display'], "01:00")
        self.assertEqual(res['duration_readable'], "1 minute")

    def test_150_words_at_150_wpm(self):
        res = calculate_duration(word_count=150, wpm=150)
        self.assertEqual(res['duration_seconds'], Decimal("60.00"))
        self.assertEqual(res['duration_minutes'], Decimal("1.00"))
        self.assertEqual(res['duration_display'], "01:00")
        self.assertEqual(res['duration_readable'], "1 minute")

    def test_75_words_at_150_wpm(self):
        res = calculate_duration(word_count=75, wpm=150)
        self.assertEqual(res['duration_seconds'], Decimal("30.00"))
        self.assertEqual(res['duration_minutes'], Decimal("0.50"))
        self.assertEqual(res['duration_display'], "00:30")
        self.assertEqual(res['duration_readable'], "30 seconds")

    def test_300_words_at_150_wpm(self):
        res = calculate_duration(word_count=300, wpm=150)
        self.assertEqual(res['duration_seconds'], Decimal("120.00"))
        self.assertEqual(res['duration_minutes'], Decimal("2.00"))
        self.assertEqual(res['duration_display'], "02:00")
        self.assertEqual(res['duration_readable'], "2 minutes")

    def test_19_words_at_120_wpm(self):
        # 19 / 120 * 60 = 9.5 seconds
        res = calculate_duration(word_count=19, wpm=120)
        self.assertEqual(res['duration_seconds'], Decimal("9.50"))
        self.assertEqual(res['duration_display'], "00:09")
        self.assertEqual(res['duration_readable'], "9 seconds")

    def test_empty_narration(self):
        res = calculate_duration(word_count=0, wpm=135)
        self.assertEqual(res['duration_seconds'], Decimal("0.00"))
        self.assertEqual(res['duration_minutes'], Decimal("0.00"))
        self.assertEqual(res['duration_display'], "00:00")
        self.assertEqual(res['duration_readable'], "0 seconds")

    def test_full_pipeline_service(self):
        text = "  Hello   world! This is a test of the speech timing engine.  "
        res = calculate_narration(text=text, wpm=120)
        self.assertEqual(res['word_count'], 11)
        self.assertEqual(res['wpm'], 120)
        self.assertEqual(res['normalized_text'], "Hello world! This is a test of the speech timing engine.")
        # 11 / 120 * 60 = 5.50s
        self.assertEqual(res['duration_seconds'], Decimal("5.50"))
        self.assertEqual(res['duration_display'], "00:05")


class NarrationEngineContractTests(SimpleTestCase):
    """
    Tests ensuring NarrationEngine adheres to BaseCalculationEngine contract.
    """
    def test_engine_calculate_valid_input(self):
        engine = NarrationEngine()
        result = engine.calculate({"text": "One two three four five", "wpm": 150})
        self.assertEqual(result['word_count'], 5)
        self.assertEqual(result['wpm'], 150)
        self.assertIn('duration_seconds', result)
        self.assertIn('duration_minutes', result)
        self.assertIn('duration_display', result)
        self.assertIn('duration_readable', result)
        self.assertIn('normalized_text', result)

    def test_engine_missing_wpm_raises_key_error(self):
        engine = NarrationEngine()
        with self.assertRaises(KeyError):
            engine.calculate({"text": "Hello"})

    def test_engine_invalid_wpm_raises_value_error(self):
        engine = NarrationEngine()
        with self.assertRaises(ValueError):
            engine.calculate({"text": "Hello", "wpm": 300})


class NarrationWebEndpointTests(TestCase):
    """
    Tests for web pages and JSON calculation API.
    """
    def setUp(self):
        self.client = Client()
        self.test_page_url = reverse('calculators:talking-flyer-narration-test')
        self.api_url = reverse('calculators:narration-calculate-api')

    def test_interactive_page_loads(self):
        response = self.client.get(self.test_page_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Talking Flyer Narration")
        self.assertContains(response, "Speaking Speed (WPM)")
        self.assertContains(response, "Timing Analysis")
        self.assertContains(response, "narration.js")

    def test_api_post_valid_json(self):
        payload = {
            "text": "Welcome to our talking flyer demonstration. Enjoy the presentation!",
            "wpm": 150,
        }
        response = self.client.post(
            self.api_url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        result = data['data']
        self.assertEqual(result['word_count'], 9)
        self.assertEqual(result['wpm'], 150)
        self.assertEqual(result['duration_seconds'], 3.6)
        self.assertEqual(result['duration_seconds_formatted'], "3.60")
        self.assertEqual(result['duration_display'], "00:03")
        self.assertIn("duration_readable", result)

    def test_api_post_form_encoded(self):
        response = self.client.post(
            self.api_url,
            data={
                "text": "Quick test message.",
                "wpm": "120",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['word_count'], 3)
        self.assertEqual(data['data']['wpm'], 120)

    def test_api_post_invalid_wpm_returns_400(self):
        payload = {
            "text": "Sample text",
            "wpm": 50,  # Below min 60
        }
        response = self.client.post(
            self.api_url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn("at least 60 WPM", data['error'])

    def test_api_post_missing_wpm_returns_400(self):
        payload = {
            "text": "Sample text",
        }
        response = self.client.post(
            self.api_url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn("Speaking speed (WPM) is required", data['error'])

    def test_api_post_malformed_json_returns_400(self):
        response = self.client.post(
            self.api_url,
            data="not a valid json string {",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn("Invalid JSON payload", data['error'])

    def test_existing_calculators_index_route_still_works(self):
        response = self.client.get(reverse('calculators:index'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'calculator_interface_ready'})
