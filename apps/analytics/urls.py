from django.urls import path
from .views import AnalyticsSummaryPlaceholderView

app_name = 'analytics'

urlpatterns = [
    path('', AnalyticsSummaryPlaceholderView.as_view(), name='summary'),
]

