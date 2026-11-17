"""Database-backed pricing lookup and orchestration around the pure cost engine."""
import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.pricing.engines.production_cost import ProductionCostEngine, decimal_value
from apps.pricing.contracts import validate_talking_flyer_contract, validate_video_generation_contract
from apps.pricing.models import (CostEstimate, CreditPackage, ExchangeRate, ModelPricing, OperationPricing,
    ProductionOverheadPricing, ProductionTool, ProductionToolPricing, SubscriptionPlan)
from apps.video_registry.models import AccessRoute, Capability, Provider, ProviderOffering, Specialty, VideoModel, Workflow
from apps.video_registry.services import validate_catalogue_selection, validate_model_configuration

ESTIMATE_INPUT_SEMANTICS = (
    'Calculation inputs are user-supplied costing assumptions; optional attempt counts are not provider-observed usage.'
)


def parse_datetime(value, name='as_of'):
    if value in (None, ''):
        return timezone.now()
    if not isinstance(value, str):
        raise ValueError(f'{name} must be an ISO-8601 timestamp.')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError(f'{name} must be an ISO-8601 timestamp.')
    if timezone.is_naive(parsed):
        raise ValueError(f'{name} must include a timezone.')
    return parsed


def _effective(queryset, at):
    return queryset.filter(is_active=True, effective_from__lte=at).filter(Q(effective_until__isnull=True) | Q(effective_until__gt=at))


def get_model_pricing_records(*, video_model_id=None, workflow_slug=None, access_route_id=None, at=None):
    at = at or timezone.now()
    queryset = _effective(ModelPricing.objects.select_related('video_model__provider', 'workflow'), at)
    if video_model_id:
        try:
            video_model_id = UUID(str(video_model_id))
        except (TypeError, ValueError):
            raise ValueError('video_model_id must be a registered model UUID.')
        queryset = queryset.filter(video_model_id=video_model_id)
    if access_route_id:
        try:
            access_route_id = UUID(str(access_route_id))
        except (TypeError, ValueError):
            raise ValueError('access_route must be a registered route UUID.')
        queryset = queryset.filter(access_route_id=access_route_id)
    if workflow_slug:
        if not Workflow.objects.filter(slug=workflow_slug, is_active=True).exists():
            raise ValueError('Unknown workflow filter.')
        queryset = queryset.filter(Q(workflow__slug=workflow_slug) | Q(workflow__isnull=True))
    return list(queryset.order_by('video_model__provider__name', 'video_model__name', 'video_model__version', 'workflow__slug', 'method'))


def get_model_pricing_for_version(video_model: VideoModel, workflow: Workflow | None, at: datetime, record_id=None, configuration=None, access_route=None):
    configuration = configuration or {}
    queryset = _effective(ModelPricing.objects.filter(video_model=video_model).select_related('workflow'), at)
    queryset = queryset.filter(access_route=access_route) if access_route else queryset.filter(access_route__isnull=True)
    if record_id:
        try:
            record = queryset.get(pk=record_id)
        except (ModelPricing.DoesNotExist, ValidationError, ValueError):
            raise ValueError('Selected pricing record is unavailable for this model version and date.')
        if record.workflow_id not in (None, workflow.pk if workflow else None) or record.configuration != configuration or record.access_route_id != (access_route.pk if access_route else None):
            raise ValueError('Selected pricing record does not apply to this workflow, configuration, or access route.')
        return record
    if workflow:
        exact = list(queryset.filter(workflow=workflow, configuration=configuration))
        if len(exact) > 1:
            raise ValueError('Multiple active pricing methods apply; select pricing_record_id explicitly.')
        if exact:
            return exact[0]
    generic = list(queryset.filter(workflow__isnull=True, configuration=configuration))
    if len(generic) > 1:
        raise ValueError('Multiple active pricing methods apply; select pricing_record_id explicitly.')
    return generic[0] if generic else None


def get_exchange_rates(*, at=None):
    at = at or timezone.now()
    rows = ExchangeRate.objects.filter(effective_at__lte=at).order_by('base_currency', 'quote_currency', '-effective_at')
    latest = {}
    for row in rows:
        latest.setdefault((row.base_currency, row.quote_currency), row)
    return list(latest.values())


def _evidence(record):
    return [{
        'source_url': record.source_url,
        'description': record.evidence_description,
        'checked_at': record.checked_at.isoformat() if record.checked_at else None,
        'verification_status': record.verification_status,
    }]


def serialize_model_pricing(record):
    return {
        'id': str(record.pk), 'video_model_id': str(record.video_model_id),
        'provider': record.video_model.provider.name, 'model': record.video_model.name,
        'version': record.video_model.version, 'workflow': record.workflow.slug if record.workflow else None,
        'model_family': record.video_model.family or None,
        'offering': {'id': str(record.access_route.offering_id), 'name': record.access_route.offering.name} if record.access_route_id else None,
        'access_route': {'id': str(record.access_route_id), 'name': record.access_route.name,
            'route_type': record.access_route.route_type} if record.access_route_id else None,
        'method': record.method, 'rate': str(record.rate), 'unit': record.unit, 'currency': record.currency,
        'configuration': record.configuration,
        'minimum_billable_seconds': str(record.minimum_billable_seconds) if record.minimum_billable_seconds is not None else None,
        'billing_increment_seconds': str(record.billing_increment_seconds) if record.billing_increment_seconds is not None else None,
        'failed_attempt_billing': record.failed_attempt_billing,
        'effective_from': record.effective_from.isoformat(), 'effective_until': record.effective_until.isoformat() if record.effective_until else None,
        'verification_status': record.verification_status, 'evidence': _evidence(record),
    }


def serialize_exchange_rate(record):
    return {'id': str(record.pk), 'base_currency': record.base_currency, 'quote_currency': record.quote_currency,
            'rate': str(record.rate), 'effective_at': record.effective_at.isoformat(), 'source': record.source,
            'verification_status': record.verification_status}


def _package_snapshot(record):
    return {'id': str(record.pk), 'name': record.name, 'credit_quantity': str(record.credit_quantity), 'price': str(record.price), 'currency': record.currency}


def _plan_snapshot(record):
    return {'id': str(record.pk), 'provider_id': str(record.provider_id),
            'provider_offering_id': str(record.provider_offering_id) if record.provider_offering_id else None,
            'name': record.name, 'slug': record.slug, 'period': record.period, 'period_days': record.period_days,
            'subscription_price': str(record.subscription_price), 'currency': record.currency,
            'included_credits': str(record.included_credits) if record.included_credits is not None else None,
            'included_quantity': str(record.included_quantity) if record.included_quantity is not None else None,
            'included_unit': record.included_unit, 'allocation_method': record.allocation_method,
            'expected_monthly_projects': record.expected_monthly_projects,
            'expected_monthly_hours': str(record.expected_monthly_hours) if record.expected_monthly_hours is not None else None,
            'additional_credit_quantity': str(record.additional_credit_quantity) if record.additional_credit_quantity is not None else None,
            'additional_credit_price': str(record.additional_credit_price) if record.additional_credit_price is not None else None,
            'verification_status': record.verification_status, 'effective_from': record.effective_from.isoformat(),
            'effective_until': record.effective_until.isoformat() if record.effective_until else None}


def _pricing_snapshot(record):
    result = serialize_model_pricing(record)
    return {key: result[key] for key in (
        'id', 'method', 'rate', 'unit', 'currency', 'minimum_billable_seconds',
        'billing_increment_seconds', 'failed_attempt_billing', 'configuration', 'offering', 'access_route', 'verification_status', 'evidence')}


def _tool_price_snapshot(record):
    return {'id': str(record.pk), 'name': record.name, 'cost_type': record.cost_type, 'method': record.method,
        'rate': str(record.rate), 'currency': record.currency, 'unit': record.unit,
        'subscription_plan_id': str(record.subscription_plan_id) if record.subscription_plan_id else None,
        'included_quantity': str(record.included_quantity) if record.included_quantity is not None else None,
        'allocation_method': record.allocation_method, 'expected_monthly_projects': record.expected_monthly_projects,
        'expected_monthly_hours': str(record.expected_monthly_hours) if record.expected_monthly_hours is not None else None,
        'verification_status': record.verification_status, 'evidence': _evidence(record),
        'effective_from': record.effective_from.isoformat(),
        'effective_until': record.effective_until.isoformat() if record.effective_until else None}


def _canonical_plan_tool_snapshot(plan, allocation_record=None):
    period_days = 365 if plan.period == SubscriptionPlan.Period.ANNUAL else (plan.period_days if plan.period == SubscriptionPlan.Period.CUSTOM else 30)
    monthly_rate = Decimal(plan.subscription_price)
    if plan.period == SubscriptionPlan.Period.ANNUAL:
        monthly_rate /= Decimal('12')
    elif plan.period == SubscriptionPlan.Period.CUSTOM:
        monthly_rate *= Decimal('30') / Decimal(period_days)
    evidence = _evidence(plan)
    if allocation_record:
        evidence += _evidence(allocation_record)
    return {'id': str(plan.pk), 'subscription_plan_id': str(plan.pk), 'name': plan.name,
        'cost_type': ProductionToolPricing.CostType.SUBSCRIPTION,
        'method': ProductionToolPricing.Method.MONTHLY_SUBSCRIPTION,
        'rate': str(monthly_rate), 'monthly_rate': str(monthly_rate), 'cash_price': str(plan.subscription_price),
        'period': plan.period, 'period_days': period_days, 'currency': plan.currency,
        'unit': 'month', 'allocation_method': plan.allocation_method or (allocation_record.allocation_method if allocation_record else ''),
        'expected_monthly_projects': plan.expected_monthly_projects or (allocation_record.expected_monthly_projects if allocation_record else None),
        'expected_monthly_hours': str(plan.expected_monthly_hours or (allocation_record.expected_monthly_hours if allocation_record else '')) or None,
        'included_quantity': str(plan.included_quantity) if plan.included_quantity is not None else None,
        'included_credits': str(plan.included_credits) if plan.included_credits is not None else None,
        'included_unit': plan.included_unit, 'verification_status': plan.verification_status,
        'evidence': evidence, 'effective_from': plan.effective_from.isoformat(),
        'effective_until': plan.effective_until.isoformat() if plan.effective_until else None,
        'offering_id': str(plan.provider_offering_id) if plan.provider_offering_id else None}


def _overhead_price_snapshot(record):
    return {'id': str(record.pk), 'name': record.name, 'category': record.category, 'method': record.method,
        'rate': str(record.rate), 'currency': record.currency, 'unit': record.unit,
        'expected_monthly_projects': record.expected_monthly_projects,
        'expected_monthly_hours': str(record.expected_monthly_hours) if record.expected_monthly_hours is not None else None,
        'verification_status': record.verification_status, 'evidence': _evidence(record)}


def _select_operation_pricing(operation_key, provider_id, at, record_id=None):
    queryset = _effective(OperationPricing.objects.filter(operation_key=operation_key), at).select_related('provider')
    if record_id:
        try:
            record = queryset.get(pk=record_id)
        except (OperationPricing.DoesNotExist, ValueError):
            raise ValueError('Selected operation pricing is unavailable.')
        if record.provider_id not in (None, provider_id):
            raise ValueError('Selected operation pricing is for a different provider.')
        return record
    if provider_id:
        record = queryset.filter(provider_id=provider_id).first()
        if record:
            return record
    return queryset.filter(provider__isnull=True).first()


def _operation_snapshot(record):
    return {'id': str(record.pk), 'operation_key': record.operation_key, 'label': record.label, 'method': record.method,
            'rate': str(record.rate), 'unit': record.unit, 'currency': record.currency,
            'failed_attempt_billing': record.failed_attempt_billing, 'verification_status': record.verification_status,
            'evidence': _evidence(record)}


def prepare_estimate_inputs(raw_inputs: dict) -> dict:
    if not isinstance(raw_inputs, dict):
        raise ValueError('Request body must be a JSON object.')
    forbidden = {'rate', 'price', 'unit_price', 'currency_rate', 'exchange_rate', 'exchange_rates', 'max_exchange_rate_age_days', 'resolved_snapshot'} & set(raw_inputs)
    if forbidden:
        raise ValueError('Prices and exchange rates must come from the authoritative pricing registry.')
    at = parse_datetime(raw_inputs.get('as_of'))
    calculator_type = raw_inputs.get('calculator_type', CostEstimate.CalculatorType.GENERAL)
    if calculator_type not in CostEstimate.CalculatorType.values:
        raise ValueError('calculator_type must be talking_flyer, video_generation, or general.')
    raw_tools_for_contract = raw_inputs.get('tools', [])
    if not isinstance(raw_tools_for_contract, list):
        raise ValueError('tools must be a list.')
    talking_flyer = None
    video_generation = None
    if calculator_type == CostEstimate.CalculatorType.TALKING_FLYER:
        talking_flyer = validate_talking_flyer_contract(raw_inputs.get('talking_flyer'))
    elif calculator_type == CostEstimate.CalculatorType.VIDEO_GENERATION:
        video_generation = validate_video_generation_contract(raw_inputs.get('video_generation'), raw_tools_for_contract)
    elif raw_inputs.get('talking_flyer') is not None or raw_inputs.get('video_generation') is not None:
        raise ValueError('Calculator-specific contracts require their matching calculator_type.')
    output_currency = raw_inputs.get('output_currency', 'USD')
    if not isinstance(output_currency, str) or len(output_currency) != 3 or not output_currency.isalpha() or output_currency != output_currency.upper():
        raise ValueError('output_currency must be a three-letter uppercase currency code.')
    raw_components = raw_inputs.get('components')
    if not isinstance(raw_components, list) or not raw_components:
        raise ValueError('At least one component is required.')
    if len(raw_components) > 100:
        raise ValueError('A maximum of 100 model components is allowed.')
    clip_assignments = {}
    if talking_flyer:
        clips = talking_flyer['clip_plan']['clips']
        for component_index, raw in enumerate(raw_components):
            assigned = raw.get('clip_sequences')
            if assigned is None:
                if len(raw_components) != 1:
                    raise ValueError('Each Talking Flyer model component must specify clip_sequences when multiple components are selected.')
                assigned = [clip['sequence'] for clip in clips]
            if not isinstance(assigned, list) or not assigned:
                raise ValueError(f'components[{component_index}].clip_sequences must be a non-empty list.')
            for sequence in assigned:
                if isinstance(sequence, bool) or not isinstance(sequence, int):
                    raise ValueError(f'components[{component_index}].clip_sequences must contain integer sequence numbers.')
                if sequence in clip_assignments:
                    raise ValueError('Each planned clip must be assigned to exactly one model component.')
                clip_assignments[sequence] = component_index
        if set(clip_assignments) != {clip['sequence'] for clip in clips}:
            raise ValueError('Every planned clip must be assigned to a model component.')
    components = []
    component_subscription_plan_ids = set()
    for index, raw in enumerate(raw_components):
        if not isinstance(raw, dict):
            raise ValueError(f'components[{index}] must be an object.')
        if {'rate', 'price', 'currency', 'unit_rate', 'pricing'} & set(raw):
            raise ValueError(f'components[{index}] cannot contain client-supplied prices.')
        try:
            model = VideoModel.objects.select_related('provider').get(pk=raw.get('video_model_id'))
        except (VideoModel.DoesNotExist, ValueError, ValidationError):
            raise ValueError(f'components[{index}] references an unknown model version.')
        if calculator_type != CostEstimate.CalculatorType.GENERAL and (model.status != VideoModel.Status.ACTIVE or model.provider.status != Provider.Status.ACTIVE):
            raise ValueError(f'components[{index}] references an inactive provider or model version.')
        workflow = None
        if raw.get('workflow_slug'):
            try:
                workflow = Workflow.objects.get(slug=raw['workflow_slug'], is_active=True)
            except Workflow.DoesNotExist:
                raise ValueError(f'components[{index}] references an unknown workflow.')
            if not model.workflows.filter(pk=workflow.pk).exists():
                raise ValueError(f'Workflow {workflow.slug} is not supported by the selected model version.')
        configuration = raw.get('configuration') or {}
        try:
            configuration = validate_model_configuration(model, workflow, configuration)
        except ValueError as exc:
            raise ValueError(f'components[{index}]: {exc}')
        selection = validate_catalogue_selection(specialty_slug=raw.get('specialty_slug'),
            provider_id=raw.get('provider_id'), offering_id=raw.get('offering_id'),
            plan_id=raw.get('subscription_plan_id'), route_id=raw.get('access_route_id'), model=model, at=at)
        access_route = selection.get('route')
        if configuration.get('generation_duration_seconds'):
            configured_duration = decimal_value(configuration['generation_duration_seconds'], f'components[{index}].generation_duration_seconds', minimum=Decimal('0.001'))
            clip_durations = [clip['duration_seconds'] for clip in talking_flyer['clip_plan']['clips'] if clip_assignments.get(clip['sequence']) == index] if talking_flyer else [raw.get('duration_seconds')]
            if any(duration is not None and decimal_value(duration, f'components[{index}].duration_seconds', minimum=Decimal('0.001')) != configured_duration for duration in clip_durations):
                raise ValueError(f'components[{index}] duration must match its configured generation duration.')
        pricing = get_model_pricing_for_version(model, workflow, at, raw.get('pricing_record_id'), configuration, access_route)
        snapshot = _pricing_snapshot(pricing) if pricing else None
        provider_plans = _effective(SubscriptionPlan.objects.filter(provider=model.provider), at)
        plan = None
        if selection.get('plan'):
            try:
                plan_record = provider_plans.get(pk=selection['plan'].pk)
            except SubscriptionPlan.DoesNotExist:
                raise ValueError('Subscription plan does not belong to the selected model provider or is not effective.')
            if plan_record.pk in component_subscription_plan_ids:
                raise ValueError('The same subscription plan cannot be allocated to multiple model components in one estimate.')
            plan = _plan_snapshot(plan_record)
            component_subscription_plan_ids.add(plan_record.pk)
        packages = [_package_snapshot(item) for item in _effective(CreditPackage.objects.filter(provider=model.provider), at)]
        assigned_clips = [clip for clip in (talking_flyer['clip_plan']['clips'] if talking_flyer else []) if clip_assignments.get(clip['sequence']) == index]
        requests = raw.get('generation_requests', 1)
        clip_count = raw.get('clip_count', raw.get('generation_requests', 1))
        duration = raw.get('duration_seconds')
        if assigned_clips:
            exact_durations = [clip['duration_seconds'] for clip in assigned_clips]
            exact_count = len(exact_durations)
            average_duration = sum(map(Decimal, exact_durations), Decimal('0')) / exact_count
            if 'generation_requests' in raw and int(requests) != exact_count:
                raise ValueError(f'components[{index}].generation_requests must equal its assigned clip count.')
            if 'clip_count' in raw and int(clip_count) != exact_count:
                raise ValueError(f'components[{index}].clip_count must equal its assigned clip count.')
            if duration is not None and decimal_value(duration, f'components[{index}].duration_seconds', minimum=Decimal('0.001')) != average_duration:
                raise ValueError(f'components[{index}].duration_seconds must match its assigned clips average; exact durations are preserved separately.')
            requests = clip_count = exact_count
            duration = str(average_duration)
        components.append({
            'model': {'id': str(model.pk), 'provider': model.provider.name, 'provider_id': str(model.provider_id), 'name': model.name, 'version': model.version, 'family': model.family or None},
            'workflow': {'slug': workflow.slug, 'name': workflow.name} if workflow else None,
            'specialty': {'slug': selection['specialty'].slug, 'name': selection['specialty'].name} if selection.get('specialty') else None,
            'offering': {'id': str(selection['offering'].pk), 'name': selection['offering'].name} if selection.get('offering') else None,
            'access_route': {'id': str(access_route.pk), 'name': access_route.name, 'route_type': access_route.route_type} if access_route else None,
            'configuration': configuration, 'pricing': snapshot, 'duration_seconds': duration,
            'clip_durations_seconds': [clip['duration_seconds'] for clip in assigned_clips] if assigned_clips else None,
            'generation_requests': requests, 'clip_count': clip_count,
            'retry_allowance': raw.get('retry_allowance', 0), 'actual_attempts': raw.get('actual_attempts'),
            'successful_attempts': raw.get('successful_attempts'), 'failed_attempts': raw.get('failed_attempts'),
            'credits_remaining': raw.get('credits_remaining'), 'credit_cost_basis': raw_inputs.get('credit_cost_basis', 'marginal_cash'),
            'subscription_plan': plan, 'credit_packages': packages,
        })
        for optional in ('actual_attempts', 'successful_attempts', 'failed_attempts'):
            if components[-1][optional] is None:
                del components[-1][optional]
    raw_operations = raw_inputs.get('operations', [])
    if not isinstance(raw_operations, list) or len(raw_operations) > 100:
        raise ValueError('operations must be a list with no more than 100 items.')
    operations = []
    for index, raw in enumerate(raw_operations):
        if not isinstance(raw, dict) or not raw.get('operation_key'):
            raise ValueError(f'operations[{index}] requires an operation_key.')
        if {'rate', 'price', 'currency', 'unit_rate', 'pricing'} & set(raw):
            raise ValueError(f'operations[{index}] cannot contain client-supplied prices.')
        provider_id = raw.get('provider_id')
        record = _select_operation_pricing(raw['operation_key'], provider_id, at, raw.get('pricing_record_id'))
        operations.append({'operation_key': raw['operation_key'], 'quantity': raw.get('quantity'),
                           'duration_seconds': raw.get('duration_seconds'), 'operation_requests': raw.get('operation_requests', 1),
                           'retry_allowance': raw.get('retry_allowance', 0),
                           'actual_attempts': raw.get('actual_attempts'), 'successful_attempts': raw.get('successful_attempts'),
                           'failed_attempts': raw.get('failed_attempts'),
                           'pricing': _operation_snapshot(record) if record else None})
        for optional in ('actual_attempts', 'successful_attempts', 'failed_attempts'):
            if operations[-1][optional] is None:
                del operations[-1][optional]
    production_raw = raw_inputs.get('production', {})
    if not isinstance(production_raw, dict):
        raise ValueError('production must be an object.')
    generated_duration = sum((sum((decimal_value(value, 'clip duration', minimum=Decimal('0.001')) for value in item['clip_durations_seconds']), Decimal('0')) if item.get('clip_durations_seconds') else decimal_value(item.get('duration_seconds'), 'component duration', minimum=Decimal('0')) * decimal_value(item.get('generation_requests', 1), 'generation requests', minimum=Decimal('1')) for item in components), Decimal('0'))
    default_duration = production_raw.get('desired_final_duration_seconds',
        talking_flyer['clip_plan']['total_usable_duration_seconds'] if talking_flyer else str(generated_duration))
    production = {'desired_final_duration_seconds': default_duration,
                  'expected_usable_duration_seconds': production_raw.get('expected_usable_duration_seconds',
                    talking_flyer['clip_plan']['total_usable_duration_seconds'] if talking_flyer else default_duration)}
    final_duration = decimal_value(production['desired_final_duration_seconds'], 'desired final duration', minimum=Decimal('0.001'))
    if video_generation and video_generation['target_finished_duration_seconds'] is not None and Decimal(video_generation['target_finished_duration_seconds']) != final_duration:
        raise ValueError('video_generation.target_finished_duration_seconds must match production.desired_final_duration_seconds.')
    usable_duration = decimal_value(production['expected_usable_duration_seconds'], 'expected usable duration', minimum=Decimal('0'))
    if usable_duration > final_duration:
        raise ValueError('Expected usable generated footage cannot exceed desired final video duration.')
    billable_duration = generated_duration
    if usable_duration > billable_duration:
        raise ValueError('Expected usable generated footage cannot exceed total planned generation duration.')
    project_hours = decimal_value(raw_inputs.get('project_hours', '0'), 'project hours', minimum=Decimal('0'))
    tools = []
    selected_tool_ids = set()
    raw_tools = raw_inputs.get('tools', [])
    if not isinstance(raw_tools, list) or len(raw_tools) > 20:
        raise ValueError('tools must be a list with no more than 20 items.')
    selected_plan_ids = set()
    selected_subscription_price_ids = set()
    for index, raw in enumerate(raw_tools):
        if not isinstance(raw, dict):
            raise ValueError(f'tools[{index}] must be an object.')
        if {'rate', 'price', 'currency', 'pricing'} & set(raw):
            raise ValueError(f'tools[{index}] cannot contain client-supplied prices.')
        try:
            tool_record = ProductionTool.objects.get(pk=raw.get('tool_id'), is_active=True, provider__status=Provider.Status.ACTIVE)
        except (ProductionTool.DoesNotExist, ValueError, ValidationError):
            raise ValueError(f'tools[{index}] references an unavailable production tool.')
        if str(tool_record.pk) in selected_tool_ids:
            raise ValueError('Select each production tool once and combine its activities to avoid double-counting shared subscriptions.')
        selected_tool_ids.add(str(tool_record.pk))
        tool_selection = validate_catalogue_selection(specialty_slug=raw.get('specialty_slug'),
            provider_id=raw.get('provider_id'), offering_id=raw.get('offering_id', str(tool_record.offering_id) if tool_record.offering_id else None),
            plan_id=raw.get('subscription_plan_id'), model=None, at=at)
        if raw.get('offering_id') and str(tool_record.offering_id or '') != str(raw.get('offering_id')):
            raise ValueError(f'tools[{index}] offering does not match its registered tool.')
        if tool_selection.get('provider') and tool_selection['provider'].pk != tool_record.provider_id:
            raise ValueError(f'tools[{index}] provider does not match its registered tool.')
        if tool_selection.get('specialty') and (not tool_record.offering_id or not tool_record.offering.specialties.filter(pk=tool_selection['specialty'].pk).exists()):
            raise ValueError(f'tools[{index}] requires a registered offering associated with its specialty.')
        activities = raw.get('activities', tool_record.activities)
        if not isinstance(activities, list) or not activities or set(activities) - set(tool_record.activities) or len(set(activities)) != len(activities):
            raise ValueError(f'tools[{index}] activities must be valid activities for {tool_record.name}.')
        subscription, usage = None, None
        selected_plan = tool_selection.get('plan')
        if selected_plan:
            if selected_plan.pk in component_subscription_plan_ids:
                raise ValueError('A subscription plan cannot be allocated both for model credits and as a production-tool subscription in one estimate.')
            if selected_plan.pk in selected_plan_ids:
                raise ValueError('The same canonical subscription plan cannot be allocated twice in one estimate.')
            selected_plan_ids.add(selected_plan.pk)
            if selected_plan.provider_id != tool_record.provider_id:
                raise ValueError('Selected canonical plan belongs to a different production-tool provider.')
            if tool_record.offering_id and selected_plan.provider_offering_id != tool_record.offering_id:
                raise ValueError('Selected canonical plan belongs to a different production-tool offering.')
            if selected_plan.provider_offering_id and not tool_record.offering_id:
                raise ValueError('A tool must be linked to the canonical plan offering before using that plan.')
        for field, expected, target in (('subscription_pricing_id', ProductionToolPricing.CostType.SUBSCRIPTION, 'subscription'), ('usage_pricing_id', ProductionToolPricing.CostType.USAGE, 'usage')):
            price_id = raw.get(field)
            if not price_id:
                continue
            try:
                record = _effective(ProductionToolPricing.objects.filter(tool=tool_record, cost_type=expected), at).get(pk=price_id)
            except (ProductionToolPricing.DoesNotExist, ValueError):
                raise ValueError(f'tools[{index}] selected {target} price is unavailable or ineffective.')
            if target == 'subscription':
                if record.subscription_plan_id:
                    if selected_plan and selected_plan.pk != record.subscription_plan_id:
                        raise ValueError('Selected tool subscription price and canonical plan do not match.')
                    if not selected_plan:
                        selected_plan = record.subscription_plan
                        if selected_plan.pk in component_subscription_plan_ids:
                            raise ValueError('A subscription plan cannot be allocated both for model credits and as a production-tool subscription in one estimate.')
                        if selected_plan.pk in selected_plan_ids:
                            raise ValueError('The same canonical subscription plan cannot be allocated twice in one estimate.')
                        selected_plan_ids.add(selected_plan.pk)
                if selected_plan and record.subscription_plan_id != selected_plan.pk:
                    raise ValueError('A canonical subscription plan requires its linked subscription price record.')
                if selected_plan:
                    if str(record.pk) in selected_subscription_price_ids:
                        raise ValueError('The same subscription pricing record cannot be selected twice in one estimate.')
                    selected_subscription_price_ids.add(str(record.pk))
                    subscription = _canonical_plan_tool_snapshot(selected_plan, record)
                else:
                    if str(record.pk) in selected_subscription_price_ids:
                        raise ValueError('The same subscription pricing record cannot be selected twice in one estimate.')
                    selected_subscription_price_ids.add(str(record.pk))
                    subscription = _tool_price_snapshot(record)
            else: usage = _tool_price_snapshot(record)
        if selected_plan and subscription is None:
            subscription = _canonical_plan_tool_snapshot(selected_plan, None)
        if selected_plan and raw.get('subscription_pricing_id') and not subscription.get('subscription_plan_id'):
            raise ValueError('A canonical subscription plan cannot be combined with a standalone subscription rate.')
        allowance = raw.get('included_allowance_remaining')
        configured_allowance = None
        if subscription:
            configured_allowance = subscription.get('included_quantity')
            if configured_allowance in (None, ''):
                configured_allowance = subscription.get('included_credits')
        if configured_allowance in (None, '') and usage:
            configured_allowance = usage.get('included_quantity')
        if allowance in (None, ''):
            if subscription and usage and configured_allowance in (None, ''):
                raise ValueError(f'tools[{index}] requires a configured or explicitly supplied remaining allowance.')
            allowance = configured_allowance if configured_allowance not in (None, '') else '0'
        else:
            allowance = str(decimal_value(allowance, f'tools[{index}].included_allowance_remaining', minimum=Decimal('0')))
            if configured_allowance not in (None, '') and Decimal(allowance) > Decimal(str(configured_allowance)):
                raise ValueError(f'tools[{index}] remaining allowance cannot exceed the configured plan allowance.')
        tools.append({'id': str(tool_record.pk), 'provider': tool_record.provider.name, 'name': tool_record.name,
            'activities': activities, 'subscription_pricing': subscription, 'usage_pricing': usage,
            'offering': {'id': str(tool_record.offering_id), 'name': tool_record.offering.name} if tool_record.offering_id else None,
            'specialty': {'slug': tool_selection['specialty'].slug, 'name': tool_selection['specialty'].name} if tool_selection.get('specialty') else None,
            'usage_quantity': raw.get('usage_quantity', '0'), 'included_allowance_remaining': allowance,
            'subscription_purchased_for_project': bool(raw.get('subscription_purchased_for_project')),
            'expected_monthly_projects': raw.get('expected_monthly_projects'), 'expected_monthly_hours': raw.get('expected_monthly_hours'),
            'manual_allocation': raw.get('manual_allocation')})
    if video_generation and video_generation['script_preparation_method'] == 'ai_assisted':
        script_tool = next((item for item in tools if item['id'] == video_generation['scriptwriting_tool_id']), None)
        if not script_tool or 'script' not in script_tool['activities'] or script_tool.get('specialty', {}).get('slug') != 'scriptwriting-creative-development':
            raise ValueError('AI-assisted script preparation requires a selected scriptwriting tool with the scriptwriting specialty.')
        if not script_tool.get('subscription_pricing') and not script_tool.get('usage_pricing'):
            raise ValueError('AI-assisted script preparation requires a configured subscription allocation or usage price; it cannot be treated as free.')
    overheads = []
    raw_overheads = raw_inputs.get('overheads', [])
    if not isinstance(raw_overheads, list) or len(raw_overheads) > 50:
        raise ValueError('overheads must be a list with no more than 50 items.')
    for index, raw in enumerate(raw_overheads):
        if not isinstance(raw, dict) or raw.get('category') not in ProductionOverheadPricing.Category.values:
            raise ValueError(f'overheads[{index}] requires a valid category.')
        if {'rate', 'price', 'currency', 'pricing'} & set(raw):
            raise ValueError(f'overheads[{index}] cannot contain client-supplied prices.')
        pricing = None
        if raw.get('pricing_id'):
            try:
                record = _effective(ProductionOverheadPricing.objects.filter(category=raw['category']), at).get(pk=raw['pricing_id'])
            except (ProductionOverheadPricing.DoesNotExist, ValueError):
                raise ValueError(f'overheads[{index}] selected rate is unavailable or ineffective.')
            pricing = _overhead_price_snapshot(record)
        overhead = {'category': raw['category'], 'name': raw.get('name') or (pricing or {}).get('name'),
            'pricing': pricing, 'quantity': raw.get('quantity'), 'subscription_purchased_for_project': bool(raw.get('subscription_purchased_for_project')),
            'expected_monthly_projects': raw.get('expected_monthly_projects'), 'expected_monthly_hours': raw.get('expected_monthly_hours')}
        if raw.get('user_amount') not in (None, ''):
            overhead['user_amount'] = str(decimal_value(raw['user_amount'], 'user overhead amount', minimum=Decimal('0')))
        overheads.append(overhead)
    fx = [serialize_exchange_rate(row) for row in get_exchange_rates(at=at)]
    prepared = {
        'components': components, 'operations': operations, 'tools': tools, 'overheads': overheads,
        'production': production, 'project_hours': str(project_hours), 'exchange_rates': fx,
        'output_currency': output_currency, 'as_of': at.isoformat(),
        'calculator_type': calculator_type, 'talking_flyer': talking_flyer, 'video_generation': video_generation,
        'max_exchange_rate_age_days': 7,
        'markup_percentage': raw_inputs.get('markup_percentage'),
        'target_margin_percentage': raw_inputs.get('target_margin_percentage'),
        'credit_cost_basis': raw_inputs.get('credit_cost_basis', 'marginal_cash'),
    }
    return prepared


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


@transaction.atomic
def estimate_production_cost(raw_inputs: dict, *, save_snapshot=True, owner=None, project=None) -> tuple[dict, CostEstimate | None]:
    prepared = prepare_estimate_inputs(raw_inputs)
    result = ProductionCostEngine().calculate(prepared)
    result['calculator_type'] = prepared['calculator_type']
    if save_snapshot and (owner is None or project is None):
        raise ValueError('Saving an estimate requires an authenticated owner and project.')
    resolved_inputs = dict(raw_inputs)
    resolved_inputs['calculator_type'] = prepared['calculator_type']
    if prepared['calculator_type'] == CostEstimate.CalculatorType.VIDEO_GENERATION:
        resolved_inputs['video_generation'] = _json_safe(prepared['video_generation'])
    resolved_inputs['resolved_snapshot'] = _json_safe(prepared)
    snapshot = CostEstimate.objects.create(owner=owner, project=project, calculator_type=prepared['calculator_type'],
        inputs=_json_safe(resolved_inputs), result=_json_safe(result)) if save_snapshot else None
    return result, snapshot


def get_test_interface_data() -> dict:
    at = timezone.now()
    models = VideoModel.objects.filter(status=VideoModel.Status.ACTIVE, provider__status='active').select_related('provider').prefetch_related('workflows')
    model_data = [{'id': str(model.pk), 'name': model.name, 'slug': model.slug, 'version': model.version,
                        'provider': model.provider.name, 'provider_id': str(model.provider_id),
                        'provider_slug': model.provider.slug,
                        'workflows': [{'slug': wf.slug, 'name': wf.name} for wf in model.workflows.filter(is_active=True)]}
                       for model in models]
    tools = []
    for tool in ProductionTool.objects.filter(is_active=True, provider__status=Provider.Status.ACTIVE).select_related('provider'):
        prices = _effective(ProductionToolPricing.objects.filter(tool=tool), at)
        tools.append({'id': str(tool.pk), 'name': tool.name, 'provider': tool.provider.name,
            'provider_website_url': tool.provider.website_url or None, 'kind': tool.kind,
            'provider_id': str(tool.provider_id), 'offering_id': str(tool.offering_id) if tool.offering_id else None,
            'offering_name': tool.offering.name if tool.offering_id else None,
            'specialties': list(tool.offering.specialties.filter(is_active=True).values_list('slug', flat=True)) if tool.offering_id else [],
            'activities': tool.activities, 'pricing': [_tool_price_snapshot(row) for row in prices]})
    overheads = [_overhead_price_snapshot(row) for row in _effective(ProductionOverheadPricing.objects.all(), at)]
    return {'models': model_data, 'tools': tools, 'overheads': overheads,
            'overhead_categories': list(ProductionOverheadPricing.Category.choices),
            'providers': list(Provider.objects.filter(status=Provider.Status.ACTIVE).order_by('name').values_list('id', 'name')),
            'currencies': ['USD', 'NGN', 'EUR', 'GBP', 'CNY'],
            'plans': [{ 'id': str(item.pk), 'provider_id': str(item.provider_id), 'provider': item.provider.name, 'name': item.name }
                      for item in _effective(SubscriptionPlan.objects.select_related('provider'), at)],
            'pricing_count': _effective(ModelPricing.objects.all(), at).count(),
            'operation_count': _effective(OperationPricing.objects.all(), at).count()}
