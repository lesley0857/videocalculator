from django.urls import path

from apps.video_registry.views import (
    AccessRouteListView, OfferingListView, PlanListView, SpecialtyListView, SpecialtyProviderListView,
    ModelCapabilityView, ModelDetailView, ModelListView,
    ProviderDetailView, ProviderListView, RegistryTestInterfaceView,
)

app_name = 'video_registry'

urlpatterns = [
    path('', RegistryTestInterfaceView.as_view(), name='test-interface'),
    path('specialties/', SpecialtyListView.as_view(), name='specialty-list'),
    path('specialties/<slug:specialty_slug>/providers/', SpecialtyProviderListView.as_view(), name='specialty-providers'),
    path('offerings/', OfferingListView.as_view(), name='offering-list'),
    path('plans/', PlanListView.as_view(), name='plan-list'),
    path('access-routes/', AccessRouteListView.as_view(), name='access-route-list'),
    path('providers/', ProviderListView.as_view(), name='provider-list'),
    path('providers/<slug:provider_slug>/', ProviderDetailView.as_view(), name='provider-detail'),
    path('models/', ModelListView.as_view(), name='model-list'),
    path('models/<slug:provider_slug>/<slug:model_slug>/', ModelDetailView.as_view(), name='model-detail'),
    path('models/<slug:provider_slug>/<slug:model_slug>/capabilities/', ModelCapabilityView.as_view(), name='model-capabilities'),
]
