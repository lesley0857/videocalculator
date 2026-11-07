from django.contrib import admin
from .models import CalculationRecord


@admin.register(CalculationRecord)
class CalculationRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'user', 'created_at')
    list_filter = ('product', 'created_at')
    search_fields = ('id', 'user__email', 'product__name')

