from django.http import JsonResponse
from django.views import View

from apps.video_registry import services
from apps.video_registry.services import (
    offerings_for_selection, plans_for_selection, providers_for_specialty,
    routes_for_selection, serialize_offering_selection, serialize_plan_selection,
    serialize_provider_selection, serialize_route_selection, serialize_specialty,
)


class SpecialtyListView(View):
    def get(self, request):
        if request.GET:
            return JsonResponse({'error': 'Specialty listing does not accept filters.'}, status=400)
        return JsonResponse({'results': [serialize_specialty(item) for item in services.get_active_specialties()]})


class SpecialtyProviderListView(View):
    def get(self, request, specialty_slug):
        if request.GET:
            return JsonResponse({'error': 'Unsupported provider filter.'}, status=400)
        try:
            rows = providers_for_specialty(specialty_slug)
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=404)
        return JsonResponse({'specialty': specialty_slug, 'results': [serialize_provider_selection(item) for item in rows]})


class OfferingListView(View):
    def get(self, request):
        if set(request.GET) != {'specialty', 'provider'}:
            return JsonResponse({'error': 'specialty and provider filters are required.'}, status=400)
        try:
            rows = offerings_for_selection(specialty_slug=request.GET['specialty'], provider_slug=request.GET['provider'])
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=404)
        return JsonResponse({'results': [serialize_offering_selection(item) for item in rows]})


class PlanListView(View):
    def get(self, request):
        if set(request.GET) != {'specialty', 'offering'}:
            return JsonResponse({'error': 'specialty and offering filters are required.'}, status=400)
        try:
            rows = plans_for_selection(specialty_slug=request.GET['specialty'], offering_id=request.GET['offering'])
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=404)
        return JsonResponse({'results': [serialize_plan_selection(item) for item in rows]})


class AccessRouteListView(View):
    def get(self, request):
        if not {'specialty', 'offering'}.issubset(request.GET) or set(request.GET) - {'specialty', 'offering', 'model'}:
            return JsonResponse({'error': 'specialty and offering filters are required; model is optional.'}, status=400)
        try:
            rows = routes_for_selection(specialty_slug=request.GET['specialty'], offering_id=request.GET['offering'], model_id=request.GET.get('model'))
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=404)
        return JsonResponse({'results': [serialize_route_selection(item) for item in rows]})
class ProviderListView(View):
    def get(self, request):
        providers = services.get_active_providers()
        return JsonResponse({'results': [{
            'name': item.name,
            'slug': item.slug,
            'website_url': item.website_url,
            'documentation_url': item.documentation_url,
            'description': item.description,
            'category': item.category,
            'support_url': item.support_url,
            'status': item.status,
        } for item in providers]})


class ProviderDetailView(View):
    def get(self, request, provider_slug):
        provider = services.get_provider(provider_slug)
        if provider is None:
            return JsonResponse({'error': 'Provider not found.'}, status=404)
        return JsonResponse({'name': provider.name, 'slug': provider.slug,
            'website_url': provider.website_url, 'documentation_url': provider.documentation_url,
            'description': provider.description, 'category': provider.category,
            'support_url': provider.support_url, 'status': provider.status})


class ModelListView(View):
    def get(self, request):
        unknown = set(request.GET) - {'workflow', 'capability', 'specialty', 'provider', 'offering', 'access_route'}
        if unknown:
            return JsonResponse({'error': f'Unsupported filter: {sorted(unknown)[0]}.'}, status=400)
        try:
            models = services.filter_models(
                workflow=request.GET.get('workflow'),
                capability=request.GET.get('capability'),
                specialty_slug=request.GET.get('specialty'), provider_slug=request.GET.get('provider'),
                offering_id=request.GET.get('offering'), route_id=request.GET.get('access_route'),
            )
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=400)
        return JsonResponse({'results': [services.serialize_model(item, include_capabilities=False) for item in models]})


class ModelDetailView(View):
    def get(self, request, provider_slug, model_slug):
        version = request.GET.get('version')
        if set(request.GET) - {'version'}:
            return JsonResponse({'error': 'Only the version query parameter is supported.'}, status=400)
        model = services.get_model(provider_slug, model_slug, version)
        if model is None:
            return JsonResponse({'error': 'Model or version not found.'}, status=404)
        return JsonResponse(services.serialize_model(model))


class ModelCapabilityView(View):
    def get(self, request, provider_slug, model_slug):
        model = services.get_model(provider_slug, model_slug, request.GET.get('version'))
        if model is None:
            return JsonResponse({'error': 'Model or version not found.'}, status=404)
        return JsonResponse({'model': {'provider': provider_slug, 'slug': model_slug, 'version': model.version},
            'verification_status': model.verification_status,
            'capabilities': [services.serialize_capability(item) for item in model.capabilities.all()]})


class RegistryTestInterfaceView(View):
    """Minimal HTML index that links to the read-only API testing workflow."""
    def get(self, request):
        return JsonResponse({'endpoints': {
            'providers': request.build_absolute_uri('/api/video-registry/providers/'),
            'models': request.build_absolute_uri('/api/video-registry/models/'),
            'filter_by_workflow': request.build_absolute_uri('/api/video-registry/models/?workflow=text-to-video'),
            'filter_by_capability': request.build_absolute_uri('/api/video-registry/models/?capability=native_audio'),
        }, 'note': 'Use these read-only JSON endpoints to inspect registry records.'})
