from django.http import JsonResponse
from django.views import View


class OrderListView(View):
    """
    Placeholder view for user orders.
    """
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        orders = request.user.orders.all()
        data = [{'id': str(o.id), 'amount': str(o.total_amount), 'status': o.status} for o in orders]
        return JsonResponse({'orders': data})

