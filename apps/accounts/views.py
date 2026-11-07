from django.http import JsonResponse
from django.views import View


class ProfilePlaceholderView(View):
    """
    Placeholder view for account profile.
    Delegates any operations to account services.
    """
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'authenticated': False}, status=401)
        return JsonResponse({
            'authenticated': True,
            'email': request.user.email,
            'full_name': request.user.get_full_name(),
        })

