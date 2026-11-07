import json
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

from apps.calculators.services.narration import (
    SPEED_PRESET_META,
    SPEED_PRESETS,
    calculate_narration,
)
from apps.calculators.services.clip_planning import (
    DEFAULT_STANDARD_DURATIONS,
    MIN_CLIP_DURATION,
    MAX_CLIP_DURATION,
)
from apps.calculators.engines.clip_planning import UniversalClipPlanningEngine


class CalculatorPlaceholderView(View):
    """
    Placeholder endpoint for calculators index.
    """
    def get(self, request, *args, **kwargs):
        return JsonResponse({'status': 'calculator_interface_ready'})


@method_decorator(ensure_csrf_cookie, name='dispatch')
class TalkingFlyerNarrationTestView(View):
    """
    Renders the interactive narration and speech timing test page
    for the Talking Flyer Calculator.
    """
    def get(self, request, *args, **kwargs):
        context = {
            'speed_presets': SPEED_PRESET_META,
            'default_wpm': SPEED_PRESETS['conversational'],
            'min_wpm': 60,
            'max_wpm': 240,
        }
        return render(request, 'calculators/narration_test.html', context)


class NarrationCalculateApiView(View):
    """
    JSON API endpoint for calculating narration metrics and speech duration.
    Accepts POST requests with text and wpm.
    """
    def post(self, request, *args, **kwargs):
        text = ""
        wpm = None

        content_type = request.content_type or ""
        if "application/json" in content_type:
            try:
                payload = json.loads(request.body.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return JsonResponse(
                    {
                        'success': False,
                        'error': 'Invalid JSON payload received.',
                    },
                    status=400,
                )
            text = payload.get('text', '')
            wpm = payload.get('wpm')
        else:
            text = request.POST.get('text', '')
            wpm = request.POST.get('wpm')

        if wpm is None or str(wpm).strip() == "":
            return JsonResponse(
                {
                    'success': False,
                    'error': 'Speaking speed (WPM) is required.',
                },
                status=400,
            )

        try:
            result = calculate_narration(text=text, wpm=wpm)
        except ValueError as exc:
            return JsonResponse(
                {
                    'success': False,
                    'error': str(exc),
                },
                status=400,
            )
        except Exception:
            return JsonResponse(
                {
                    'success': False,
                    'error': 'An unexpected error occurred during calculation.',
                },
                status=500,
            )

        response_data = {
            'success': True,
            'data': {
                'word_count': result['word_count'],
                'wpm': result['wpm'],
                'duration_seconds': float(result['duration_seconds']),
                'duration_seconds_formatted': str(result['duration_seconds']),
                'duration_minutes': float(result['duration_minutes']),
                'duration_minutes_formatted': str(result['duration_minutes']),
                'duration_display': result['duration_display'],
                'duration_readable': result['duration_readable'],
                'normalized_text': result['normalized_text'],
            },
        }
        return JsonResponse(response_data, status=200)


@method_decorator(ensure_csrf_cookie, name='dispatch')
class TalkingFlyerClipPlannerTestView(View):
    """
    Renders the interactive test interface for the Universal Clip Planning Engine
    and Narration Segmentation System.
    """
    def get(self, request, *args, **kwargs):
        context = {
            'speed_presets': SPEED_PRESET_META,
            'default_wpm': SPEED_PRESETS['conversational'],
            'min_wpm': 60,
            'max_wpm': 240,
            'standard_durations': DEFAULT_STANDARD_DURATIONS,
            'min_clip_duration': MIN_CLIP_DURATION,
            'max_clip_duration': MAX_CLIP_DURATION,
        }
        return render(request, 'calculators/clip_planner_test.html', context)


class ClipPlannerCalculateApiView(View):
    """
    JSON API endpoint for the Universal Clip Planning Engine.
    Accepts POST requests with narration, wpm, clip_options, and segmentation settings.
    """
    def post(self, request, *args, **kwargs):
        content_type = request.content_type or ""
        payload = {}

        if "application/json" in content_type:
            try:
                payload = json.loads(request.body.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return JsonResponse(
                    {
                        'success': False,
                        'error': 'Invalid JSON payload received.',
                    },
                    status=400,
                )
        else:
            # Support form-encoded data
            text = request.POST.get('narration', request.POST.get('text', ''))
            wpm = request.POST.get('wpm')
            clip_options_raw = request.POST.get('clip_options')
            clip_options = None
            if clip_options_raw:
                try:
                    clip_options = json.loads(clip_options_raw)
                except Exception:
                    clip_options = None

            payload = {
                'narration': text,
                'wpm': wpm,
                'clip_options': clip_options,
            }

        # Validate presence of wpm
        if payload.get('wpm') is None or str(payload.get('wpm')).strip() == "":
            return JsonResponse(
                {
                    'success': False,
                    'error': 'Speaking speed (WPM) is required.',
                },
                status=400,
            )

        try:
            engine = UniversalClipPlanningEngine()
            result = engine.calculate(payload)
            return JsonResponse(result, status=200)
        except ValueError as exc:
            return JsonResponse(
                {
                    'success': False,
                    'error': str(exc),
                },
                status=400,
            )
        except Exception:
            return JsonResponse(
                {
                    'success': False,
                    'error': 'An unexpected error occurred during clip planning.',
                },
                status=500,
            )
