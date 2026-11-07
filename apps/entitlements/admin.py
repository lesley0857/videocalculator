from django.contrib import admin
from .models import Entitlement


@admin.register(Entitlement)
class EntitlementAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'is_active', 'expires_at', 'created_at')
    list_filter = ('is_active', 'product', 'expires_at')
    search_fields = ('user__email', 'product__name')

