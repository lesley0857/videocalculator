from django.urls import path
from .views import PaymentWebhookPlaceholderView

app_name = 'payments'

urlpatterns = [
    path('webhook/', PaymentWebhookPlaceholderView.as_view(), name='webhook'),
]

