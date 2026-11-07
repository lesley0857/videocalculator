from django.http import JsonResponse
from django.views import View


class DevicesListView(View):
    """
    List user registered devices.
    """
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        devices = request.user.devices.all()
        data = [{'fingerprint': d.device_fingerprint, 'trusted': d.is_trusted, 'last_active': d.last_active} for d in devices]
        return JsonResponse({'devices': data})

