"""Read-only query and presentation services for the public video registry API."""
from django.db.models import Prefetch, QuerySet, Q

from apps.video_registry.models import AccessRoute, Capability, Evidence, Provider, ProviderOffering, Specialty, VideoModel, Workflow


def _models_queryset() -> QuerySet:
    return VideoModel.objects.select_related('provider').prefetch_related(
        'workflows',
        Prefetch('capabilities', queryset=Capability.objects.select_related('workflow').prefetch_related('evidence')),
        'evidence',
        'offerings', 'access_routes__offering',
    )


def get_active_providers() -> list[Provider]:
    return list(Provider.objects.filter(status=Provider.Status.ACTIVE).order_by('name'))


def get_active_specialties():
    return list(Specialty.objects.filter(is_active=True).order_by('display_order', 'name'))


def _active_effective(queryset, at=None):
    from django.db.models import Q
    from django.utils import timezone
    at = at or timezone.now()
    return queryset.filter(is_active=True, effective_from__lte=at).filter(Q(effective_until__isnull=True) | Q(effective_until__gt=at))


def providers_for_specialty(specialty_slug):
    specialty = Specialty.objects.filter(slug=specialty_slug, is_active=True).first()
    if specialty is None:
        raise ValueError('Unknown or inactive specialty.')
    return list(Provider.objects.filter(status=Provider.Status.ACTIVE, specialties=specialty,
        offerings__is_active=True, offerings__specialties=specialty).distinct().order_by('name'))


def offerings_for_selection(*, specialty_slug, provider_slug):
    specialty = Specialty.objects.filter(slug=specialty_slug, is_active=True).first()
    provider = Provider.objects.filter(slug=provider_slug, status=Provider.Status.ACTIVE).first()
    if specialty is None or provider is None:
        raise ValueError('Unknown or inactive specialty or provider.')
    if not provider.specialties.filter(pk=specialty.pk).exists():
        return []
    return list(ProviderOffering.objects.filter(provider=provider, is_active=True, specialties=specialty).order_by('name'))


def plans_for_selection(*, specialty_slug, offering_id, at=None):
    from apps.pricing.models import SubscriptionPlan
    specialty = Specialty.objects.filter(slug=specialty_slug, is_active=True).first()
    offering = ProviderOffering.objects.filter(pk=offering_id, is_active=True, provider__status=Provider.Status.ACTIVE).first()
    if specialty is None or offering is None:
        raise ValueError('Unknown or inactive specialty or offering.')
    if not offering.specialties.filter(pk=specialty.pk).exists():
        return []
    return list(_active_effective(SubscriptionPlan.objects.filter(provider_offering=offering).filter(
        Q(specialties=specialty) | Q(specialties__isnull=True, provider_offering__specialties=specialty)), at).distinct().order_by('name'))


def routes_for_selection(*, specialty_slug, offering_id, model_id=None):
    specialty = Specialty.objects.filter(slug=specialty_slug, is_active=True).first()
    offering = ProviderOffering.objects.filter(pk=offering_id, is_active=True, provider__status=Provider.Status.ACTIVE).first()
    if specialty is None or offering is None:
        raise ValueError('Unknown or inactive specialty or offering.')
    queryset = AccessRoute.objects.filter(offering=offering, is_active=True)
    if not offering.specialties.filter(pk=specialty.pk).exists():
        return []
    if model_id:
        queryset = queryset.filter(video_models__pk=model_id, video_models__status=VideoModel.Status.ACTIVE)
    return list(queryset.distinct().order_by('name'))


def validate_catalogue_selection(*, specialty_slug=None, provider_id=None, offering_id=None, plan_id=None,
                                 route_id=None, model=None, at=None):
    """Validate optional catalog identifiers for estimate APIs; blank means legacy path."""
    from apps.pricing.models import SubscriptionPlan
    if not any((specialty_slug, provider_id, offering_id, plan_id, route_id)):
        return {}
    specialty = None
    if specialty_slug:
        specialty = Specialty.objects.filter(slug=specialty_slug, is_active=True).first()
        if specialty is None:
            raise ValueError('Unknown or inactive specialty.')
    provider = Provider.objects.filter(pk=provider_id, status=Provider.Status.ACTIVE).first() if provider_id else (model.provider if model else None)
    if provider_id and provider is None:
        raise ValueError('Unknown or inactive provider.')
    if model and (model.status != VideoModel.Status.ACTIVE or model.provider.status != Provider.Status.ACTIVE):
        raise ValueError('Selected model version is inactive.')
    if provider and model and provider.pk != model.provider_id:
        raise ValueError('Selected model belongs to a different provider.')
    offering = ProviderOffering.objects.filter(pk=offering_id, is_active=True, provider__status=Provider.Status.ACTIVE).first() if offering_id else None
    if offering_id and offering is None:
        raise ValueError('Unknown or inactive provider offering.')
    if offering and provider and offering.provider_id != provider.pk:
        raise ValueError('Selected offering belongs to a different provider.')
    if offering and model and (offering.provider_id != model.provider_id or not model.offerings.filter(pk=offering.pk).exists()):
        raise ValueError('Selected offering is not associated with the selected model version.')
    if specialty:
        if provider and not provider.specialties.filter(pk=specialty.pk).exists():
            raise ValueError('Selected provider is not associated with the specialty.')
        if offering and not offering.specialties.filter(pk=specialty.pk).exists():
            raise ValueError('Selected offering is not associated with the specialty.')
        if model and (not model.offerings.filter(specialties=specialty).exists()):
            raise ValueError('Selected model version is not associated with the specialty.')
    plan = _active_effective(SubscriptionPlan.objects.filter(pk=plan_id), at).first() if plan_id else None
    if plan_id and plan is None:
        raise ValueError('Unknown or inactive subscription plan.')
    if plan and provider and plan.provider_id != provider.pk:
        raise ValueError('Selected plan belongs to a different provider.')
    if plan and offering and plan.provider_offering_id != offering.pk:
        raise ValueError('Selected plan belongs to a different offering.')
    if plan and model and plan.provider_offering_id and not model.offerings.filter(pk=plan.provider_offering_id).exists():
        raise ValueError('Selected plan offering is not associated with the selected model version.')
    if plan and specialty and plan.provider_offering_id and not (
        plan.specialties.filter(pk=specialty.pk).exists() or
        (not plan.specialties.exists() and plan.provider_offering.specialties.filter(pk=specialty.pk).exists())
    ):
        raise ValueError('Selected plan is not applicable to the specialty.')
    route = AccessRoute.objects.filter(pk=route_id, is_active=True, offering__is_active=True,
        offering__provider__status=Provider.Status.ACTIVE).first() if route_id else None
    if route_id and route is None:
        raise ValueError('Unknown or inactive access route.')
    if route and offering and route.offering_id != offering.pk:
        raise ValueError('Selected access route belongs to a different offering.')
    if route and provider and route.offering.provider_id != provider.pk:
        raise ValueError('Selected access route belongs to a different provider.')
    if route and plan and plan.provider_offering_id != route.offering_id:
        raise ValueError('Selected plan does not belong to the selected access-route offering.')
    if route and specialty and not route.offering.specialties.filter(pk=specialty.pk).exists():
        raise ValueError('Selected access route is not applicable to the specialty.')
    if route and model and (route.offering.provider_id != model.provider_id or not route.video_models.filter(pk=model.pk).exists() or not model.offerings.filter(pk=route.offering_id).exists()):
        raise ValueError('Selected access route is not associated with the selected model version.')
    if route and plan and route.subscription_plan_id not in (None, plan.pk):
        raise ValueError('Selected plan does not match the selected access route.')
    return {'specialty': specialty, 'provider': provider, 'offering': offering, 'plan': plan, 'route': route}


def get_provider(slug: str) -> Provider | None:
    return Provider.objects.filter(slug=slug).first()


def get_active_models() -> list[VideoModel]:
    return list(_models_queryset().filter(status=VideoModel.Status.ACTIVE, provider__status=Provider.Status.ACTIVE))


def get_model(provider_slug: str, model_slug: str, version: str | None = None) -> VideoModel | None:
    queryset = _models_queryset().filter(provider__slug=provider_slug, slug=model_slug)
    if version is not None:
        queryset = queryset.filter(version=version)
    else:
        queryset = queryset.filter(status=VideoModel.Status.ACTIVE).order_by('-release_date', '-version')
    return queryset.first()


def filter_models(*, workflow: str | None = None, capability: str | None = None, specialty_slug=None,
                  provider_slug=None, offering_id=None, route_id=None) -> list[VideoModel]:
    queryset = _models_queryset().filter(status=VideoModel.Status.ACTIVE, provider__status=Provider.Status.ACTIVE)
    if workflow:
        if not Workflow.objects.filter(slug=workflow, is_active=True).exists():
            raise ValueError('Invalid workflow filter.')
        queryset = queryset.filter(workflows__slug=workflow)
    if capability:
        if not Capability.objects.filter(key=capability).exists():
            raise ValueError('Invalid capability filter.')
        queryset = queryset.filter(capabilities__key=capability, capabilities__status=Capability.Status.SUPPORTED)
    if specialty_slug:
        specialty = Specialty.objects.filter(slug=specialty_slug, is_active=True).first()
        if specialty is None:
            raise ValueError('Invalid or inactive specialty filter.')
        queryset = queryset.filter(provider__specialties=specialty, offerings__is_active=True,
            offerings__specialties=specialty)
    if provider_slug:
        if not Provider.objects.filter(slug=provider_slug, status=Provider.Status.ACTIVE).exists():
            raise ValueError('Invalid or inactive provider filter.')
        queryset = queryset.filter(provider__slug=provider_slug)
    if offering_id:
        try:
            offering = ProviderOffering.objects.get(pk=offering_id, is_active=True, provider__status=Provider.Status.ACTIVE)
        except (ProviderOffering.DoesNotExist, ValueError):
            raise ValueError('Invalid or inactive offering filter.')
        queryset = queryset.filter(offerings=offering)
    if route_id:
        try:
            route = AccessRoute.objects.get(pk=route_id, is_active=True, offering__is_active=True, offering__provider__status=Provider.Status.ACTIVE)
        except (AccessRoute.DoesNotExist, ValueError):
            raise ValueError('Invalid or inactive access route filter.')
        queryset = queryset.filter(access_routes=route, offerings=route.offering)
    return list(queryset.distinct())


def models_for_provider(provider: Provider) -> list[VideoModel]:
    return list(_models_queryset().filter(provider=provider, status=VideoModel.Status.ACTIVE))


def get_native_talking_video_models() -> list[VideoModel]:
    """Return active models explicitly marked as supporting native talking video."""
    return list(_models_queryset().filter(
        status=VideoModel.Status.ACTIVE,
        provider__status=Provider.Status.ACTIVE,
        capabilities__key='native_talking_video',
        capabilities__status=Capability.Status.SUPPORTED,
    ).distinct())


def get_models_requiring_external_tts() -> list[VideoModel]:
    return list(_models_queryset().filter(
        status=VideoModel.Status.ACTIVE,
        capabilities__key='requires_external_tts',
        capabilities__status=Capability.Status.SUPPORTED,
    ).distinct())


def get_models_requiring_external_lip_sync() -> list[VideoModel]:
    return list(_models_queryset().filter(
        status=VideoModel.Status.ACTIVE,
        capabilities__key='requires_external_lip_sync',
        capabilities__status=Capability.Status.SUPPORTED,
    ).distinct())


def _evidence_data(records):
    return [{
        'classification': item.classification,
        'status': item.status,
        'source_url': item.source_url,
        'source_title': item.source_title,
        'verified_at': item.verified_at.isoformat() if item.verified_at else None,
    } for item in records.all()]


def capability_is_verified(capability):
    evidence = capability.evidence.filter(status=Evidence.Status.CURRENT,
        classification__in=(Evidence.Classification.OFFICIAL, Evidence.Classification.TESTED),
        verified_at__isnull=False)
    if evidence.exists():
        return True
    return capability.model.evidence.filter(capability__isnull=True, status=Evidence.Status.CURRENT,
        classification__in=(Evidence.Classification.OFFICIAL, Evidence.Classification.TESTED),
        verified_at__isnull=False).exists()


def validate_model_configuration(model, workflow, configuration):
    from decimal import Decimal, InvalidOperation
    if not isinstance(configuration, dict):
        raise ValueError('configuration must be a JSON object.')
    normalized = {}
    for key, value in configuration.items():
        if not isinstance(key, str) or isinstance(value, (dict, list)) or value is None:
            raise ValueError('Configuration keys must be strings and values must be scalar.')
        rows = Capability.objects.filter(model=model, key=key, is_active=True).filter(Q(workflow=workflow) | Q(workflow__isnull=True)).order_by('-workflow_id')
        capability = rows.first()
        if capability is None and key == 'audio_mode':
            capability = Capability.objects.filter(model=model, key=str(value), is_active=True,
                status=Capability.Status.SUPPORTED).filter(Q(workflow=workflow) | Q(workflow__isnull=True)).order_by('-workflow_id').first()
        if capability is None or capability.status != Capability.Status.SUPPORTED or not capability_is_verified(capability):
            raise ValueError(f'Configuration {key}={value} is not supported by verified capability data for this model version.')
        option_values = capability.allowed_values or ([part.strip() for part in capability.value.split(',') if part.strip()] if capability.value and capability.input_type == Capability.InputType.SELECT else [])
        if capability.input_type == Capability.InputType.SELECT:
            if not option_values or str(value) not in [str(item) for item in option_values]:
                raise ValueError(f'Configuration {key} must be one of the verified allowed values.')
            normalized[key] = str(value)
        elif capability.input_type in (Capability.InputType.NUMBER,):
            try:
                number = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                raise ValueError(f'Configuration {key} must be numeric.')
            if not number.is_finite() or (capability.minimum_value is not None and number < capability.minimum_value) or (capability.maximum_value is not None and number > capability.maximum_value):
                raise ValueError(f'Configuration {key} is outside its verified range.')
            normalized[key] = str(number)
        elif capability.input_type == Capability.InputType.BOOLEAN:
            if not isinstance(value, bool):
                raise ValueError(f'Configuration {key} must be true or false.')
            normalized[key] = value
        elif capability.input_type == Capability.InputType.FLAG:
            if value not in (True, 'true', capability.key, capability.value):
                raise ValueError(f'Configuration {key} must match a supported capability flag.')
            normalized[key] = str(value)
        else:
            normalized[key] = str(value)
        if capability.constraints.get('pattern') and capability.input_type == Capability.InputType.TEXT:
            import re
            if not re.fullmatch(capability.constraints['pattern'], normalized[key]):
                raise ValueError(f'Configuration {key} does not match its verified pattern.')
    return normalized


def serialize_capability(capability: Capability) -> dict:
    evidence_verified = capability_is_verified(capability)
    selectable = capability.is_active and capability.status == Capability.Status.SUPPORTED and evidence_verified
    values = capability.allowed_values or ([part.strip() for part in capability.value.split(',') if part.strip()] if capability.value and capability.input_type == Capability.InputType.SELECT else [])
    return {
        'key': capability.key,
        'label': capability.label,
        'status': capability.status,
        'value': capability.value or None,
        'unit': capability.unit or None,
        'workflow': capability.workflow.slug if capability.workflow else None,
        'evidence': _evidence_data(capability.evidence),
        'configuration': {'input_type': capability.input_type, 'allowed_values': values if selectable else [],
            'minimum_value': str(capability.minimum_value) if selectable and capability.minimum_value is not None else None,
            'maximum_value': str(capability.maximum_value) if selectable and capability.maximum_value is not None else None,
            'constraints': capability.constraints if selectable else {}, 'selectable': selectable},
    }


def serialize_specialty(item):
    return {'id': str(item.pk), 'name': item.name, 'slug': item.slug, 'description': item.description}


def serialize_provider_selection(item):
    return {'id': str(item.pk), 'name': item.name, 'slug': item.slug}


def serialize_offering_selection(item):
    return {'id': str(item.pk), 'provider_id': str(item.provider_id), 'name': item.name, 'slug': item.slug,
        'description': item.description, 'offering_type': item.offering_type,
        'specialties': list(item.specialties.filter(is_active=True).values_list('slug', flat=True))}


def serialize_plan_selection(item):
    return {'id': str(item.pk), 'offering_id': str(item.provider_offering_id), 'name': item.name,
        'slug': item.slug, 'period': item.period, 'period_days': item.period_days,
        'price': str(item.subscription_price), 'currency': item.currency,
        'included_credits': str(item.included_credits) if item.included_credits is not None else None,
        'included_quantity': str(item.included_quantity) if item.included_quantity is not None else None,
        'included_unit': item.included_unit, 'verification_status': item.verification_status}


def serialize_route_selection(item):
    return {'id': str(item.pk), 'offering_id': str(item.offering_id), 'name': item.name,
        'route_type': item.route_type, 'pricing_method': item.pricing_method,
        'subscription_plan_id': str(item.subscription_plan_id) if item.subscription_plan_id else None,
        'model_version_ids': list(map(str, item.video_models.filter(status=VideoModel.Status.ACTIVE).values_list('pk', flat=True)))}


def serialize_model(model: VideoModel, *, include_capabilities: bool = True) -> dict:
    data = {
        'id': str(model.id),
        'provider': {'name': model.provider.name, 'slug': model.provider.slug},
        'name': model.name,
        'slug': model.slug,
        'family': model.family or None,
        'version': model.version,
        'description': model.description,
        'documentation_url': model.documentation_url,
        'api_documentation_url': model.api_documentation_url,
        'release_date': model.release_date.isoformat() if model.release_date else None,
        'retirement_date': model.retirement_date.isoformat() if model.retirement_date else None,
        'status': model.status,
        'verification_status': model.verification_status,
        'workflows': [{'name': item.name, 'slug': item.slug} for item in model.workflows.all() if item.is_active],
        'evidence': _evidence_data(model.evidence),
    }
    if include_capabilities:
        data['capabilities'] = [serialize_capability(item) for item in model.capabilities.all()]
    return data
