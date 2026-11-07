from decimal import Decimal
from django.test import SimpleTestCase

from apps.calculators.services.clip_planning import ClipOption
from apps.calculators.services.narration_segmentation import (
    segment_narration,
    is_sentence_end_word,
)


class NarrationSegmentationTests(SimpleTestCase):
    """
    Tests for narration segmentation, sentence boundary awareness, and text integrity.
    """
    def test_empty_narration_returns_empty_segments(self):
        segments, val = segment_narration("", 150, [ClipOption(duration_seconds=10)])
        self.assertEqual(segments, [])
        self.assertTrue(val["is_valid"])

    def test_single_clip_segmentation(self):
        text = "Welcome to our talking flyer showcase. Discover great deals today."
        # 10 words at 150 WPM (cap 25 for 10s clip)
        clip = ClipOption(duration_seconds=10)
        segments, val = segment_narration(text, 150, [clip])

        self.assertEqual(len(segments), 1)
        seg = segments[0]
        self.assertEqual(seg["sequence_number"], 1)
        self.assertEqual(seg["start_word_index"], 1)
        self.assertEqual(seg["end_word_index"], 10)
        self.assertEqual(seg["word_count"], 10)
        self.assertEqual(seg["narration_text"], text)
        self.assertTrue(val["is_valid"])
        self.assertTrue(val["reconstructed_text_matches"])

    def test_multiple_clips_sentence_boundary_preference(self):
        # 150 WPM -> 10s clip has capacity 25 words.
        # Create a text where a sentence ends at word 22 (within 20% of 25 = words 20-25).
        # Sentence 1 has 22 words. Sentence 2 has 10 words. Total = 32 words.
        # Two 10s clips (total cap 50).
        part1 = "One two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty twenty-one done."
        part2 = "Now we begin the second sentence here."
        text = f"{part1} {part2}"
        words = text.split()
        self.assertEqual(len(part1.split()), 22)
        self.assertEqual(len(words), 29)

        clips = [ClipOption(duration_seconds=10), ClipOption(duration_seconds=10)]
        segments, val = segment_narration(
            text,
            150,
            clips,
            sentence_boundary_preference=True,
            sentence_boundary_tolerance=0.20,
        )

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["word_count"], 22)
        self.assertEqual(segments[0]["narration_text"], part1)
        self.assertEqual(segments[1]["word_count"], 7)
        self.assertEqual(segments[1]["narration_text"], part2)
        self.assertTrue(val["is_valid"])
        self.assertTrue(val["reconstructed_text_matches"])

    def test_sentence_boundary_fallback_when_outside_tolerance(self):
        # Sentence ends at word 10, but clip capacity is 25 words.
        # Tolerance 20% of 25 = 5 words (window: words 20 to 25).
        # Since word 10 is far outside window, segmenter takes max capacity (25 words).
        words = [f"word{i}" for i in range(1, 35)]
        words[9] = "sentence."  # 10th word
        text = " ".join(words)

        clips = [ClipOption(duration_seconds=10), ClipOption(duration_seconds=10)]
        segments, val = segment_narration(
            text,
            150,
            clips,
            sentence_boundary_preference=True,
            sentence_boundary_tolerance=0.20,
        )

        self.assertEqual(len(segments), 2)
        # Clip 1 takes max capacity 25 words
        self.assertEqual(segments[0]["word_count"], 25)
        self.assertEqual(segments[1]["word_count"], 9)
        self.assertTrue(val["is_valid"])
        self.assertTrue(val["reconstructed_text_matches"])

    def test_sentence_boundary_does_not_starve_subsequent_clips(self):
        # Narration: 40 words.
        # Clips: two 10s clips (cap 25 each, total cap 50).
        # Suppose a sentence ends at word 12.
        # If clip 1 took 12 words, clip 2 would need to take 40 - 12 = 28 words, which exceeds clip 2's capacity (25)!
        # The segmenter must enforce min_take = 40 - 25 = 15 words, so it CANNOT break at word 12.
        words = [f"word{i}" for i in range(1, 41)]
        words[11] = "early."  # 12th word
        text = " ".join(words)

        clips = [ClipOption(duration_seconds=10), ClipOption(duration_seconds=10)]
        segments, val = segment_narration(
            text,
            150,
            clips,
            sentence_boundary_preference=True,
            sentence_boundary_tolerance=0.60,
        )

        self.assertEqual(len(segments), 2)
        # Clip 1 must take at least 15 words and at most 25 words
        self.assertGreaterEqual(segments[0]["word_count"], 15)
        self.assertLessEqual(segments[0]["word_count"], 25)
        # Clip 2 must not exceed 25 words
        self.assertLessEqual(segments[1]["word_count"], 25)
        self.assertTrue(val["is_valid"])
        self.assertTrue(val["reconstructed_text_matches"])

    def test_preserves_punctuation_and_hyphenation(self):
        text = "Hello, world! We offer state-of-the-art AI-powered flyers. Are you ready? (Yes, absolutely!)"
        clips = [ClipOption(duration_seconds=10)]
        segments, val = segment_narration(text, 150, clips)

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["narration_text"], text)
        self.assertTrue(val["is_valid"])
        self.assertTrue(val["reconstructed_text_matches"])

    def test_is_sentence_end_word_helper(self):
        self.assertTrue(is_sentence_end_word("done."))
        self.assertTrue(is_sentence_end_word("really?"))
        self.assertTrue(is_sentence_end_word("wow!"))
        self.assertTrue(is_sentence_end_word("wait..."))
        self.assertTrue(is_sentence_end_word('"quoted."'))
        self.assertTrue(is_sentence_end_word("'quoted?'"))
        self.assertFalse(is_sentence_end_word("middle"))
        self.assertFalse(is_sentence_end_word("word,with,comma"))
        self.assertFalse(is_sentence_end_word(""))

