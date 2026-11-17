from unittest import TestCase

from apps.pricing.contracts import validate_talking_flyer_contract, validate_video_generation_contract


class CalculatorContractTests(TestCase):
    def test_talking_flyer_preserves_exact_clip_timing(self):
        contract = validate_talking_flyer_contract({
            'schema_version': 1, 'script': 'Hello there', 'word_count': 2, 'narration_wpm': 120,
            'narration_duration_seconds': '1', 'clip_plan': {'schema_version': 1, 'clips': [
                {'sequence': 1, 'word_count': 1, 'text': 'Hello', 'duration_seconds': '4',
                 'reserved_duration_seconds': '1', 'usable_duration_seconds': '3'},
                {'sequence': 2, 'word_count': 1, 'text': 'there', 'duration_seconds': '6',
                 'reserved_duration_seconds': '2', 'usable_duration_seconds': '4'},
            ]},
        })
        self.assertEqual(contract['clip_plan']['total_planned_generated_duration_seconds'], '10')
        self.assertEqual(contract['clip_plan']['total_usable_duration_seconds'], '7')
        self.assertEqual([clip['duration_seconds'] for clip in contract['clip_plan']['clips']], ['4', '6'])

    def test_talking_flyer_rejects_gaps_and_inconsistent_usable_duration(self):
        value = {'schema_version': 1, 'word_count': 1, 'narration_wpm': 120,
            'narration_duration_seconds': '1', 'clip_plan': {'schema_version': 1, 'clips': [
                {'sequence': 2, 'word_count': 1, 'duration_seconds': '4', 'reserved_duration_seconds': '1', 'usable_duration_seconds': '2'}]}}
        with self.assertRaisesRegex(ValueError, 'usable duration'):
            validate_talking_flyer_contract(value)

    def test_video_generation_script_preparation_contract(self):
        value = {'schema_version': 1, 'video_brief': 'A short product explainer',
            'target_finished_duration_seconds': '20',
            'script_preparation_method': 'ai_assisted', 'script': 'Opening scene',
            'scriptwriting_tool_id': 'tool-1', 'scenes': [{'sequence': 1, 'description': 'Product reveal', 'planned_duration_seconds': 6}]}
        result = validate_video_generation_contract(value, [{'tool_id': 'tool-1'}])
        self.assertEqual(result['scenes'][0]['planned_duration_seconds'], '6')
        with self.assertRaisesRegex(ValueError, 'priced scriptwriting tool'):
            validate_video_generation_contract(value, [])
