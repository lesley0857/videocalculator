from django.urls import path

from apps.pricing.views import (
    CostEstimateDetailView, CostEstimateView, ExchangeRateListView,
    ModelPricingDetailView, ModelPricingListView, OperationPricingListView, SubscriptionPlanListView,
    PricingTestInterfaceView,
)

app_name = 'pricing'
urlpatterns = [
    path('test/', PricingTestInterfaceView.as_view(), name='test-interface'),
    path('api/records/', ModelPricingListView.as_view(), name='pricing-list'),
    path('api/models/<uuid:video_model_id>/', ModelPricingDetailView.as_view(), name='model-pricing-detail'),
    path('api/exchange-rates/', ExchangeRateListView.as_view(), name='exchange-rates'),
    path('api/operations/', OperationPricingListView.as_view(), name='operation-pricing'),
    path('api/subscription-plans/', SubscriptionPlanListView.as_view(), name='subscription-plans'),
    path('api/estimate/', CostEstimateView.as_view(), name='estimate'),
    path('api/estimates/<uuid:estimate_id>/', CostEstimateDetailView.as_view(), name='estimate-detail'),
]
