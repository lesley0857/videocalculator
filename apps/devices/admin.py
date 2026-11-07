from django.contrib import admin
from .models import Device


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'device_fingerprint', 'is_trusted', 'ip_address', 'last_active')
    list_filter = ('is_trusted', 'last_active')
    search_fields = ('user__email', 'device_fingerprint', 'ip_address')

