from django.contrib import admin
from .models import AnalyticsEvent


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ('event_name', 'user', 'created_at')
    list_filter = ('event_name', 'created_at')
    search_fields = ('event_name', 'user__email')

