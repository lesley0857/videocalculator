from django.http import JsonResponse
from django.views import View


class EntitlementsListView(View):
    """
    Returns user entitlements list.
    """
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        entitlements = request.user.entitlements.filter(is_active=True)
        data = [{'product': e.product.name, 'valid': e.is_valid()} for e in entitlements]
        return JsonResponse({'entitlements': data})

