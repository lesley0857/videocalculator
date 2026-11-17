from django.contrib import admin

from apps.workspace.models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'status', 'created_at', 'updated_at')
    list_filter = ('status',)
    search_fields = ('name', 'owner__email')
    readonly_fields = ('id', 'created_at', 'updated_at', 'archived_at')

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return fields + (('owner',) if obj else ())
