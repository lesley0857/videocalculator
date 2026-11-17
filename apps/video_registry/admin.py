from django.contrib import admin
from apps.video_registry.models import (AccessRoute, Capability, CapabilityRevision, Evidence,
    Provider, ProviderOffering, Specialty, VideoModel, Workflow)


class CapabilityInline(admin.TabularInline):
    model = Capability
    extra = 0
    show_change_link = True
    fields = ('key', 'label', 'workflow', 'status', 'input_type', 'value', 'allowed_values', 'minimum_value', 'maximum_value', 'constraints', 'unit', 'is_active')


@admin.register(Specialty)
class SpecialtyAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'display_order', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')


class ModelEvidenceInline(admin.TabularInline):
    model = Evidence
    fk_name = 'model'
    extra = 0
    fields = ('classification', 'status', 'source_title', 'source_url', 'verified_at', 'verified_by')


class CapabilityEvidenceInline(admin.TabularInline):
    model = Evidence
    fk_name = 'capability'
    extra = 0
    fields = ('classification', 'status', 'source_title', 'source_url', 'verified_at', 'verified_by')


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'category', 'status', 'updated_at')
    list_filter = ('status', 'category', 'specialties')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = ((None, {'fields': ('name', 'slug', 'status', 'category', 'description', 'specialties')}),
        ('Links', {'fields': ('website_url', 'documentation_url', 'support_url')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}))


@admin.register(ProviderOffering)
class ProviderOfferingAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'offering_type', 'is_active', 'updated_at')
    list_filter = ('provider', 'offering_type', 'specialties', 'is_active')
    search_fields = ('name', 'slug', 'provider__name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('id', 'created_at', 'updated_at')

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.full_clean()


@admin.register(AccessRoute)
class AccessRouteAdmin(admin.ModelAdmin):
    list_display = ('name', 'offering', 'route_type', 'pricing_method', 'subscription_plan', 'is_active')
    list_filter = ('route_type', 'pricing_method', 'is_active', 'offering__provider')
    search_fields = ('name', 'offering__name', 'offering__provider__name')
    filter_horizontal = ('video_models',)
    readonly_fields = ('id', 'created_at', 'updated_at')

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.full_clean()


@admin.register(VideoModel)
class VideoModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'provider', 'status', 'verification_status', 'release_date')
    list_filter = ('provider', 'status', 'verification_status', 'workflows', 'offerings')
    search_fields = ('name', 'slug', 'family', 'provider__name', 'version')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')
    inlines = (CapabilityInline, ModelEvidenceInline)
    fieldsets = ((None, {'fields': ('provider', 'name', 'slug', 'family', 'version', 'description')}),
        ('Documentation and lifecycle', {'fields': ('documentation_url', 'api_documentation_url', 'release_date', 'retirement_date', 'status')}),
        ('Verification', {'fields': ('verification_status', 'admin_notes')}),
        ('Supported workflows and offerings', {'fields': ('workflows', 'offerings')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}))

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.full_clean()


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Capability)
class CapabilityAdmin(admin.ModelAdmin):
    list_display = ('model', 'key', 'workflow', 'status', 'input_type', 'is_active', 'updated_at')
    list_filter = ('status', 'key', 'workflow', 'is_active', 'model__provider')
    search_fields = ('key', 'label', 'model__name', 'model__version', 'model__provider__name')
    inlines = (CapabilityEvidenceInline,)
    readonly_fields = ('created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ('source_title', 'model', 'capability', 'classification', 'status', 'verified_at')
    list_filter = ('classification', 'status', 'model__provider')
    search_fields = ('source_title', 'source_url', 'model__name', 'model__version')
    readonly_fields = ('created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)


@admin.register(CapabilityRevision)
class CapabilityRevisionAdmin(admin.ModelAdmin):
    list_display = ('capability', 'prior_status', 'prior_value', 'prior_unit', 'recorded_at')
    readonly_fields = ('capability', 'prior_status', 'prior_value', 'prior_unit', 'recorded_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
