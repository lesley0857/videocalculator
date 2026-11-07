from django.http import JsonResponse
from django.views import View
from .services import get_active_products


class ProductListView(View):
    """
    Lists available products, delegating query to product service.
    """
    def get(self, request, *args, **kwargs):
        products = get_active_products()
        data = [{'name': p.name, 'slug': p.slug, 'description': p.description} for p in products]
        return JsonResponse({'products': data})

