from django.http import JsonResponse
from django.views import View


class PaymentWebhookPlaceholderView(View):
    """
    Placeholder endpoint for incoming webhooks.
    Actual payment processing will be implemented in future tasks.
    """
    def post(self, request, *args, **kwargs):
        return JsonResponse({'status': 'webhook_endpoint_ready'}, status=200)

