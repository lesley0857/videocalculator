from django.http import JsonResponse
from django.views import View


class AnalyticsSummaryPlaceholderView(View):
    """
    Analytics summary placeholder.
    """
    def get(self, request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            return JsonResponse({'error': 'Forbidden'}, status=403)
        return JsonResponse({'status': 'analytics_ready'})

