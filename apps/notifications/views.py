from django.http import JsonResponse
from django.views import View


class NotificationsListView(View):
    """
    List user notifications.
    """
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        notifications = request.user.notifications.all()
        data = [{'subject': n.subject, 'read': n.is_read, 'sent_at': n.sent_at} for n in notifications]
        return JsonResponse({'notifications': data})

