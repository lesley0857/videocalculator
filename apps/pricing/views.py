import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import urlencode
from django.views import View

from apps.pricing.models import CostEstimate, OperationPricing, SubscriptionPlan
from apps.pricing.services import (
    ESTIMATE_INPUT_SEMANTICS,
    estimate_production_cost, get_exchange_rates, get_model_pricing_records,
    get_test_interface_data, parse_datetime, serialize_exchange_rate,
    serialize_model_pricing,
)
from apps.video_registry.models import Specialty, VideoModel
from apps.workspace.models import Project


class ModelPricingListView(View):
    def get(self, request):
        unknown = set(request.GET) - {'video_model_id', 'workflow', 'access_route', 'as_of'}
        if unknown:
            return JsonResponse({'error': f'Unsupported filter: {sorted(unknown)[0]}.'}, status=400)
        try:
            at = parse_datetime(request.GET.get('as_of'))
            records = get_model_pricing_records(video_model_id=request.GET.get('video_model_id'), workflow_slug=request.GET.get('workflow'), access_route_id=request.GET.get('access_route'), at=at)
        except (ValueError, TypeError) as exc:
            return JsonResponse({'error': str(exc)}, status=400)
        return JsonResponse({'as_of': at.isoformat(), 'results': [serialize_model_pricing(item) for item in records]})


class ModelPricingDetailView(View):
    def get(self, request, video_model_id):
        unknown = set(request.GET) - {'workflow', 'access_route', 'as_of'}
        if unknown:
            return JsonResponse({'error': f'Unsupported filter: {sorted(unknown)[0]}.'}, status=400)
        try:
            at = parse_datetime(request.GET.get('as_of'))
            VideoModel.objects.get(pk=video_model_id)
            records = get_model_pricing_records(video_model_id=video_model_id, workflow_slug=request.GET.get('workflow'), access_route_id=request.GET.get('access_route'), at=at)
        except VideoModel.DoesNotExist:
            return JsonResponse({'error': 'Registered model version not found.'}, status=404)
        except (ValueError, TypeError) as exc:
            return JsonResponse({'error': str(exc)}, status=400)
        return JsonResponse({'video_model_id': str(video_model_id), 'as_of': at.isoformat(), 'results': [serialize_model_pricing(item) for item in records]})


class ExchangeRateListView(View):
    def get(self, request):
        if set(request.GET) - {'as_of'}:
            return JsonResponse({'error': 'Only the as_of filter is supported.'}, status=400)
        try:
            at = parse_datetime(request.GET.get('as_of'))
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=400)
        return JsonResponse({'as_of': at.isoformat(), 'convention': 'rate is quote-currency units for one base-currency unit', 'results': [serialize_exchange_rate(item) for item in get_exchange_rates(at=at)]})


class OperationPricingListView(View):
    def get(self, request):
        if set(request.GET) - {'operation_key', 'as_of'}:
            return JsonResponse({'error': 'Unsupported operation pricing filter.'}, status=400)
        try:
            at = parse_datetime(request.GET.get('as_of'))
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=400)
        queryset = OperationPricing.objects.filter(is_active=True, effective_from__lte=at).filter(
            Q(effective_until__isnull=True) | Q(effective_until__gt=at)).select_related('provider')
        if request.GET.get('operation_key'):
            queryset = queryset.filter(operation_key=request.GET['operation_key'])
        results = [{'id': str(item.pk), 'operation_key': item.operation_key, 'label': item.label,
                    'provider': item.provider.name if item.provider else None,
                    'provider_id': str(item.provider_id) if item.provider_id else None, 'method': item.method,
                    'rate': str(item.rate), 'unit': item.unit, 'currency': item.currency,
                    'effective_from': item.effective_from.isoformat(), 'effective_until': item.effective_until.isoformat() if item.effective_until else None,
                    'failed_attempt_billing': item.failed_attempt_billing, 'verification_status': item.verification_status,
                    'source_url': item.source_url, 'evidence_description': item.evidence_description}
                   for item in queryset.order_by('operation_key', 'provider__name', '-effective_from')]
        return JsonResponse({'as_of': at.isoformat(), 'results': results})


class SubscriptionPlanListView(View):
    def get(self, request):
        if set(request.GET) - {'provider_id', 'as_of'}:
            return JsonResponse({'error': 'Unsupported subscription plan filter.'}, status=400)
        try:
            at = parse_datetime(request.GET.get('as_of'))
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=400)
        queryset = SubscriptionPlan.objects.filter(is_active=True, effective_from__lte=at).filter(
            Q(effective_until__isnull=True) | Q(effective_until__gt=at)).select_related('provider')
        if request.GET.get('provider_id'):
            queryset = queryset.filter(provider_id=request.GET['provider_id'])
        results = [{'id': str(item.pk), 'provider': item.provider.name, 'provider_id': str(item.provider_id),
                    'name': item.name, 'period': item.period, 'period_days': item.period_days,
                    'subscription_price': str(item.subscription_price), 'currency': item.currency,
                    'included_credits': str(item.included_credits),
                    'additional_credit_quantity': str(item.additional_credit_quantity) if item.additional_credit_quantity is not None else None,
                    'additional_credit_price': str(item.additional_credit_price) if item.additional_credit_price is not None else None,
                    'verification_status': item.verification_status}
                   for item in queryset.order_by('provider__name', 'name')]
        return JsonResponse({'as_of': at.isoformat(), 'results': results})


class CostEstimateView(View):
    def post(self, request):
        try:
            payload = json.loads(request.body.decode('utf-8'), parse_float=Decimal, parse_int=int)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)
        if not isinstance(payload, dict):
            return JsonResponse({'error': 'JSON body must be an object.'}, status=400)
        if 'owner_id' in payload:
            return JsonResponse({'error': 'Estimate owner comes from the authenticated session.'}, status=400)
        project_id = payload.get('project_id')
        project = None
        if project_id:
            if not request.user.is_authenticated:
                return JsonResponse({'error': 'Sign in before saving an estimate.'}, status=401)
            try:
                project = request.user.video_projects.filter(pk=project_id).first()
            except (ValueError, TypeError, ValidationError):
                project = None
            if project is None:
                return JsonResponse({'error': 'not_found'}, status=404)
            if project.status != Project.Status.ACTIVE:
                return JsonResponse({'error': 'Restore this project before saving a new estimate.'}, status=400)
        try:
            result, estimate = estimate_production_cost(
                payload,
                save_snapshot=project is not None,
                owner=request.user if project else None,
                project=project,
            )
        except (ValueError, TypeError, KeyError, ValidationError) as exc:
            message = exc.messages if isinstance(exc, ValidationError) else str(exc)
            return JsonResponse({'error': message}, status=400)
        response = {'input_semantics': ESTIMATE_INPUT_SEMANTICS, **result}
        if estimate:
            response['estimate_id'] = str(estimate.pk)
        return JsonResponse(response,
                            status=200 if result['status'] == 'complete' else 422)


class CostEstimateDetailView(View):
    def get(self, request, estimate_id):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'authentication_required'}, status=401)
        estimate = CostEstimate.objects.filter(owner=request.user, project__owner=request.user, pk=estimate_id).select_related('project').first()
        if estimate is None:
            return JsonResponse({'error': 'not_found'}, status=404)
        return JsonResponse({'estimate_id': str(estimate.pk), 'created_at': estimate.created_at.isoformat(),
                             'calculator_type': estimate.calculator_type,
                             'input_semantics': ESTIMATE_INPUT_SEMANTICS,
                             'input_snapshot': estimate.inputs, 'result_snapshot': estimate.result})


class PricingTestInterfaceView(View):
    def get(self, request):
        context = get_test_interface_data()
        context.update({
            'workspace_projects': request.user.video_projects.filter(status=Project.Status.ACTIVE).order_by('name')
            if request.user.is_authenticated else [],
            'resume_estimate': request.GET.get('resume') == '1',
        })
        return render(request, 'pricing/cost_test.html', context)


class VideoGenerationCalculatorView(PricingTestInterfaceView):
    def get(self, request):
        context = get_test_interface_data()
        context.update({
            'workspace_projects': request.user.video_projects.filter(status=Project.Status.ACTIVE).order_by('name')
            if request.user.is_authenticated else [],
            'resume_estimate': request.GET.get('resume') == '1',
            'video_generation_mode': True,
            'specialties': Specialty.objects.filter(is_active=True).order_by('display_order', 'name'),
            'source_estimate': None,
            'starting_inputs': None,
        })
        source_id = request.GET.get('from')
        if source_id:
            if not request.user.is_authenticated:
                next_url = f'{request.path}?from={source_id}'
                return redirect(f'/accounts/login/?{urlencode({"next": next_url})}')
            source = CostEstimate.objects.filter(pk=source_id, owner=request.user,
                calculator_type=CostEstimate.CalculatorType.VIDEO_GENERATION).first()
            if source is None:
                from django.http import Http404
                raise Http404
            context['source_estimate'] = source
            context['starting_inputs'] = source.inputs
            context['resume_estimate'] = True
        return render(request, 'pricing/cost_test.html', context)
