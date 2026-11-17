import json
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
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
from apps.pricing.models import ProductionOverheadPricing
from apps.pricing.services import get_test_interface_data
from apps.video_registry.models import Specialty
from apps.pricing.models import CostEstimate
from apps.pricing.services import estimate_production_cost, prepare_estimate_inputs
from apps.workspace.models import Project
from apps.workspace.services import create_project


class CalculatorPlaceholderView(View):
    """
    Placeholder endpoint for calculators index.
    """
    def get(self, request, *args, **kwargs):
        return render(request, 'calculators/index.html')


@method_decorator(ensure_csrf_cookie, name='dispatch')
class TalkingFlyerCalculatorView(View):
    def get(self, request, *args, **kwargs):
        data = get_test_interface_data()
        starting_inputs = None
        source_estimate = None
        source_id = request.GET.get('from')
        if source_id and request.user.is_authenticated:
            from apps.pricing.models import CostEstimate
            source_estimate = CostEstimate.objects.filter(pk=source_id, owner=request.user,
                calculator_type='talking_flyer').select_related('project').first()
            if source_estimate is None:
                from django.http import Http404
                raise Http404
            starting_inputs = source_estimate.inputs
        return render(request, 'calculators/talking_flyer.html', {
            'wpm_presets': (120, 135, 150, 165, 180),
            'default_wpm': 135, 'min_wpm': 60, 'max_wpm': 240,
            'standard_durations': DEFAULT_STANDARD_DURATIONS,
            'min_clip_duration': MIN_CLIP_DURATION, 'max_clip_duration': MAX_CLIP_DURATION,
            'specialties': Specialty.objects.filter(is_active=True).order_by('display_order', 'name'),
            'catalogue_tools': data['tools'], 'overheads': data['overheads'],
            'overhead_categories': list(ProductionOverheadPricing.Category.choices),
            'currencies': data['currencies'],
            'authenticated': request.user.is_authenticated,
            'starting_inputs': starting_inputs,
            'source_estimate': source_estimate,
        })


class TalkingFlyerSavePrepareView(View):
    def post(self, request, *args, **kwargs):
        if len(request.body) > 1_000_000:
            return JsonResponse({'error': 'The estimate is too large to save.'}, status=413)
        try:
            payload = json.loads(request.body.decode('utf-8'), parse_float=Decimal, parse_int=int)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({'error': 'Invalid estimate context.'}, status=400)
        if not isinstance(payload, dict) or payload.get('calculator_type') != 'talking_flyer':
            return JsonResponse({'error': 'Only a Talking Flyer estimate can be saved here.'}, status=400)
        if {'owner_id', 'project_id', 'resolved_snapshot'} & set(payload):
            return JsonResponse({'error': 'Estimate ownership and resolved prices are server controlled.'}, status=400)
        try:
            result, _ = estimate_production_cost(payload, save_snapshot=False)
            resolved = prepare_estimate_inputs(payload)
        except (ValueError, TypeError, KeyError, ValidationError) as exc:
            message = exc.messages if isinstance(exc, ValidationError) else str(exc)
            return JsonResponse({'error': message}, status=400)
        resolved_inputs = dict(payload)
        resolved_inputs['calculator_type'] = CostEstimate.CalculatorType.TALKING_FLYER
        resolved_inputs['resolved_snapshot'] = resolved
        request.session['pending_talking_flyer_inputs'] = {
            'inputs': json.loads(json.dumps(resolved_inputs, default=str)),
            'result': json.loads(json.dumps(result, default=str)),
        }
        request.session.modified = True
        next_url = '/calculators/talking-flyer/save/'
        if not request.user.is_authenticated:
            next_url = f'/accounts/login/?next={next_url}'
        return JsonResponse({'next_url': next_url})


@method_decorator(login_required, name='dispatch')
class TalkingFlyerSaveView(View):
    template_name = 'calculators/talking_flyer_save.html'

    def _context(self, request, *, error=''):
        pending = request.session.get('pending_talking_flyer_inputs')
        return {'projects': request.user.video_projects.filter(status=Project.Status.ACTIVE),
                'pending': pending is not None,
                'pending_result': pending.get('result') if pending else None,
                'error': error}

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context(request))

    def post(self, request, *args, **kwargs):
        pending = request.session.get('pending_talking_flyer_inputs')
        if not pending or not isinstance(pending.get('inputs'), dict) or not isinstance(pending.get('result'), dict):
            return render(request, self.template_name, self._context(request, error='Your pending calculation expired. Return to the calculator and calculate it again.'))
        project_id = request.POST.get('project_id', '').strip()
        project_name = request.POST.get('project_name', '').strip()
        try:
            if project_id:
                project = request.user.video_projects.filter(pk=project_id, status=Project.Status.ACTIVE).first()
                if project is None:
                    raise ValueError('Choose one of your active projects.')
            elif project_name:
                project = create_project(request.user, name=project_name)
            else:
                raise ValueError('Choose an existing project or enter a name for a new project.')
            estimate = CostEstimate.objects.create(owner=request.user, project=project,
                calculator_type=CostEstimate.CalculatorType.TALKING_FLYER,
                inputs=pending['inputs'], result=pending['result'])
        except (ValueError, TypeError, KeyError, ValidationError) as exc:
            message = '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            return render(request, self.template_name, self._context(request, error=message))
        request.session.pop('pending_talking_flyer_inputs', None)
        return redirect('workspace:estimate-detail', estimate_id=estimate.pk)


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
